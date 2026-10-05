"""Fine-tune a small reply model on character_data.py output (LoRA, one GPU).

Usage (needs the separate training venv, see handoff/dev-box.md):
    .runtime/train-venv/bin/python scripts/dev/train_lora.py \
        --base .runtime/hf/gemma-4-E2B-it-qat --out .runtime/dev/lora/gemma4-e2b

Then convert the adapter for llama.cpp (convert_lora_to_gguf.py ships in the
llama.cpp source tree of the same build as llama-server):
    python <llama.cpp>/convert_lora_to_gguf.py --base <hf snapshot dir> \
        --outtype f16 --outfile persona-lora.gguf .runtime/dev/lora/gemma4-e2b

Rows are chats ({"messages": [...], "tools": [...]?, "train": "last"|"all"}).
"last" (the default, character data) trains on the final assistant message;
"all" (Agent trajectories) trains on every assistant turn, tool calls
included, never on tool results; with "train_from": n only on the turns from
message n on (the Agent's tool list grows mid-task, so the turns before were
written under fewer tools and are trained in a row of their own). Each trained span is exactly what the
model writes after the prompt the server builds for that turn
(scripts/dev/template_parity.py checks the two templates agree).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import provenance  # scripts/dev

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA = PROJECT_DIR / ".runtime" / "dev" / "distill" / "replies.jsonl"
TARGET_MODULES = (
    r"^(?!.*(vision|audio)).*layers\.\d+\."
    r"(self_attn\.(q|k|v|o)_proj|mlp\.(gate|up|down)_proj)$"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="HF model id or local path")
    parser.add_argument("--out", required=True)
    parser.add_argument("--data", default=str(DATA))
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--holdout", type=float, default=0.03)
    parser.add_argument("--max-steps", type=int, default=-1, help="dry runs only")
    parser.add_argument(
        "--max-length", type=int, default=2048, help="tokens; longer rows are truncated"
    )
    parser.add_argument(
        "--4bit",
        dest="four_bit",
        action="store_true",
        help="QLoRA: load the base in 4-bit (nf4); E4B in bf16 does not fit next to other tenants",
    )
    parser.add_argument(
        "--liger",
        action="store_true",
        help="fused linear + cross-entropy (liger-kernel): long Agent rows never "
        "materialize logits over a 250k vocabulary for every token",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="build everything, show which tokens are trained on, one short forward; no training",
    )
    args = parser.parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    # Only files whose rules are known and the same throughout (provenance.py).
    stamp = provenance.read_stamp(Path(args.data))
    if stamp is None:
        raise SystemExit(f"{args.data} has no version stamp ({provenance.sidecar(Path(args.data)).name}); "
                         "train only on files made by the stamped data steps")
    print(f"data {args.data}: {stamp}")
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    rows = [
        json.loads(line)
        for line in Path(args.data).read_text(encoding="utf-8").splitlines()
    ]
    random.Random(0).shuffle(rows)
    tokenized, broken, quiet = [], 0, 0
    for row in rows:
        try:
            item = tokenize_row(tokenizer, row)
        except ValueError:
            broken += 1
            continue
        quiet += item.pop("narration_dropped", 0)
        tokenized.append(item)
    # The trainer cuts long rows from the right, which would train on half an
    # answer with no end marker: drop them instead, and say how many.
    lengths = [len(r["input_ids"]) for r in tokenized]
    kept = [r for r in tokenized if len(r["input_ids"]) <= args.max_length]
    print(
        f"longest row {max(lengths)} tokens; "
        f"{len(tokenized) - len(kept)} rows over --max-length {args.max_length} dropped; "
        f"{broken} rows whose template does not extend its prompts dropped; "
        f"{quiet} rows trained without narration on tool-call turns"
    )
    split = max(1, int(len(kept) * args.holdout))
    train = Dataset.from_list(kept[split:])
    evaluation = Dataset.from_list(kept[:split])
    print(f"train {len(train)}  eval {len(evaluation)}")

    quantized: dict = {}
    if args.four_bit:
        from transformers import BitsAndBytesConfig

        quantized = {
            "quantization_config": BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            ),
            "device_map": {"": 0},
        }
    model = AutoModelForCausalLM.from_pretrained(
        args.base, dtype=torch.bfloat16, attn_implementation="sdpa", **quantized
    )
    # Text only: Gemma 4 also ships vision/audio towers (~0.9 GiB) that a
    # text forward never calls. Drop them before the trainer moves the model
    # to a GPU that other services share.
    inner = getattr(model, "model", None)
    for name in ("vision_tower", "audio_tower", "embed_vision", "embed_audio"):
        if inner is not None and getattr(inner, name, None) is not None:
            setattr(inner, name, None)
    if args.four_bit:
        # Not peft.prepare_model_for_kbit_training: it casts every
        # non-quantized parameter to float32, and Gemma 4's per-layer
        # embedding tables alone then need 8.75 GiB more. They stay bf16 and
        # frozen; only the inputs need gradients for checkpointing to work.
        model.enable_input_require_grads()
    config = SFTConfig(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=10,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=True,
        bf16=True,
        use_cpu=not torch.cuda.is_available(),  # CPU only for pipeline dry runs
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="no",
        report_to=[],
        completion_only_loss=True,
        max_length=args.max_length,
        use_liger_kernel=args.liger,
    )
    trainer = SFTTrainer(
        model=model,
        args=config,
        train_dataset=train,
        eval_dataset=evaluation,
        processing_class=tokenizer,
        peft_config=LoraConfig(
            r=args.rank,
            lora_alpha=args.rank * 2,
            lora_dropout=0.05,
            # Text layers only: Gemma 4 checkpoints also carry vision and
            # audio towers, which llama.cpp does not load for this use.
            target_modules=TARGET_MODULES,
            task_type="CAUSAL_LM",
        ),
    )
    if args.check:
        return check(trainer, tokenizer)
    trainer.train()
    trainer.save_model(args.out)
    print(f"saved adapter to {args.out}")
    return 0


def wire_to_template(messages: list[dict]) -> list[dict]:
    """OpenAI wire messages -> what HF chat templates expect: tool-call
    arguments as objects (llama-server parses the JSON string the same way)."""
    result = []
    for message in messages:
        calls = message.get("tool_calls")
        if calls:
            message = {**message, "tool_calls": [
                {**call, "function": {**call["function"], "arguments": json.loads(
                    call["function"]["arguments"] or "{}")}}
                if isinstance(call["function"].get("arguments"), str) else call
                for call in calls]}
        result.append(message)
    return result


def tokenize_row(tokenizer, row: dict) -> dict[str, list[int]]:
    """input_ids of the whole chat and a completion_mask marking the trained
    assistant turns. Raises ValueError when a turn's prompt is not a prefix of
    the chat in text and in tokens (the span would not be what the model
    writes at inference).

    Gemma 4's template moves the text of a turn that also calls tools behind
    the tool results once they exist, so that turn is never a prefix of the
    finished chat. Then the narration on tool-call turns ("讓我先看一下…") is
    left out and the calls themselves are trained; final answers keep their
    text. Templates that keep the order (Qwen) are rendered as recorded."""
    messages = wire_to_template(row["messages"])
    try:
        return _tokenize(tokenizer, messages, row)
    except ValueError:
        quiet = [{**m, "content": ""} if m["role"] == "assistant" and m.get("tool_calls") else m
                 for m in messages]
        if quiet == messages:
            raise
        out = _tokenize(tokenizer, quiet, row)
        return {**out, "narration_dropped": 1}


def _tokenize(tokenizer, messages: list[dict], row: dict) -> dict[str, list[int]]:
    tools = row.get("tools")

    def render(part: list[dict], prompt: bool) -> str:
        return tokenizer.apply_chat_template(
            part, tools=tools, tokenize=False, add_generation_prompt=prompt,
            enable_thinking=False)

    def ids(text: str) -> list[int]:
        # The template writes BOS as text where the model wants one.
        return tokenizer(text, add_special_tokens=False)["input_ids"]

    turns = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
    if row.get("train", "last") == "last":
        turns = turns[-1:]
    else:
        turns = [i for i in turns if i >= row.get("train_from", 0)]
    if not turns or turns[-1] != len(messages) - 1 and row.get("train", "last") == "last":
        raise ValueError("the last message must be the trained answer")
    full = render(messages, False)
    full_ids = ids(full)
    mask = [0] * len(full_ids)
    for index in turns:
        prompt, upto = render(messages[:index], True), render(messages[: index + 1], False)
        prompt_ids, upto_ids = ids(prompt), ids(upto)
        if not (full.startswith(upto) and upto.startswith(prompt)
                and full_ids[: len(upto_ids)] == upto_ids
                and upto_ids[: len(prompt_ids)] == prompt_ids):
            raise ValueError("chat template does not extend the prompt")
        # The answer ends with the template's end-of-turn marker (Gemma:
        # <turn|>, Qwen: <|im_end|>), which llama.cpp stops on.
        for position in range(len(prompt_ids), len(upto_ids)):
            mask[position] = 1
    return {"input_ids": full_ids, "completion_mask": mask}


def check(trainer, tokenizer) -> int:
    """Print the tokens the loss is computed on (must be exactly the answer
    lines plus the end-of-turn marker) and run one short forward pass."""
    import torch

    row = trainer.train_dataset[0]
    ids = row["input_ids"]
    # TRL turned completion_mask into labels (-100 = not trained).
    labels = row["labels"]
    positions = [i for i, label in enumerate(labels) if label != -100]
    spans, start = [], None
    for i in range(len(labels) + 1):
        inside = i < len(labels) and labels[i] != -100
        if inside and start is None:
            start = i
        if not inside and start is not None:
            spans.append((start, i))
            start = None
    print(f"tokens: {len(ids)}, trained on: {len(positions)} in {len(spans)} span(s)")
    for a, b in spans:
        print("TRAINED >>>" + tokenizer.decode(ids[a:b]) + "<<<")
    end = tokenizer.convert_tokens_to_ids(["<turn|>", "<|im_end|>"])
    if not spans or any(not any(t in end for t in ids[a:b]) for a, b in spans):
        print("MASK WRONG: every trained span must end its turn with the end-of-turn marker")
        return 1
    model = trainer.model
    sample = torch.tensor([ids[-64:]], device=model.device)
    with torch.no_grad():
        logits = model(input_ids=sample).logits
    print(f"forward ok: logits {tuple(logits.shape)}")
    return 0 if positions else 1


if __name__ == "__main__":
    raise SystemExit(main())
