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

--pairs adds what the owner asked for on 2026-10-10: after the rows, the
student's wrong reply and the teacher's right one to the same request
(EdgeAgent bench/dataset.py --pairs: {"messages", "tools", "chosen",
"rejected", "thinking"}) train by preference (DPO, the adapter after the rows
as the reference; preference_train). The adapter after the rows alone is kept
as <out>-sft, a candidate for the same gate.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import provenance  # scripts/dev

PROJECT_DIR = Path(__file__).resolve().parents[2]
TARGET_MODULES = (
    r"^(?!.*(vision|audio)).*layers\.\d+\."
    r"(self_attn\.(q|k|v|o)_proj|mlp\.(gate|up|down)_proj)$"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="HF model id or local path")
    parser.add_argument("--out", required=True)
    parser.add_argument("--data", nargs="+", required=True, help="one or more stamped row files")
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--holdout", type=float, default=0.03)
    parser.add_argument("--max-steps", type=int, default=-1, help="dry runs only")
    parser.add_argument("--epoch-copies", action="store_true",
                        help="also keep the adapter after each earlier epoch (<out>-e1, ...): a less trained "
                             "candidate for the same gate, at no extra training")
    parser.add_argument(
        "--max-length", type=int, default=2048, help="tokens; longer rows are dropped, never cut"
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
        "--offload-activations",
        action="store_true",
        help="keep what the backward pass needs (each layer's input, 6 GiB at 32K tokens) "
        "in RAM instead of on the GPU; long Agent rows need it",
    )
    parser.add_argument("--pairs", nargs="+", default=[],
                        help="stamped wrong/right pair files: preference training after the rows")
    parser.add_argument("--pref-beta", type=float, default=0.1, help="DPO's beta")
    parser.add_argument("--pref-lr", type=float, default=1e-5)
    parser.add_argument("--pref-epochs", type=int, default=1)
    parser.add_argument(
        "--check",
        action="store_true",
        help="build everything, show which tokens are trained on, one short forward; no training",
    )
    args = parser.parse_args()

    import os

    # Long rows allocate activations of many sizes; without this the cache
    # fragments and a 32K row runs out with a gigabyte reserved but unused.
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    # Only files whose rules are known and the same throughout (provenance.py).
    # Several files train one adapter (the machine spirit's lines and the
    # Agent's tool work: the product loads one); each keeps its own stamp.
    rows = []
    for data in args.data:
        rows += stamped(data, "data", "rows")
    pairs = []
    for data in args.pairs:
        pairs += stamped(data, "pairs", "pairs")
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    random.Random(0).shuffle(rows)
    results = tokenize_rows(args.base, rows, args.max_length)
    broken = sum(r == "broken" for r in results)
    tokenized = [r for r in results if isinstance(r, dict)]
    quiet = sum(item.pop("narration_dropped", 0) for item in tokenized)
    # The trainer cuts long rows from the right, which would train on half an
    # answer with no end marker: drop them instead, and say how many.
    lengths = [len(r["input_ids"]) for r in tokenized]
    kept = [r for r in tokenized if len(r["input_ids"]) <= args.max_length]
    long = sum(r == "long" for r in results) + len(tokenized) - len(kept)
    print(
        f"longest row {max(lengths)} tokens; "
        f"{long} rows over --max-length {args.max_length} dropped; "
        f"{broken} rows whose template does not extend its prompts dropped; "
        f"{quiet} rows trained without narration on tool-call turns"
    )
    split = max(1, int(len(kept) * args.holdout))
    train = Dataset.from_list(kept[split:])
    evaluation = Dataset.from_list(kept[:split])
    print(f"train {len(train)}  eval {len(evaluation)}")
    preferred = tokenize_pairs(args.base, pairs, args.max_length) if pairs else []

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
    from transformers import AttentionInterface

    AttentionInterface.register("window_sdpa", window_attention)
    model = AutoModelForCausalLM.from_pretrained(
        args.base, dtype=torch.bfloat16, attn_implementation="window_sdpa", **quantized
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
        # The per-layer embedding table (vocab x layers x 256: 5.25 GiB in
        # bf16) is a frozen lookup. On the GPU it left a 32K-token row no room
        # for its activations; in RAM only the looked-up rows go to the GPU.
        tables = [name for name, _ in model.named_modules() if name.endswith(".embed_tokens_per_layer")]
        for name in tables:
            parent, _, attribute = name.rpartition(".")
            lookup_in_ram(model.get_submodule(parent), attribute)
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
        activation_offloading=args.offload_activations,
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
        return check(trainer, tokenizer) or check_pairs(preferred, tokenizer)
    if args.epoch_copies:
        trainer.add_callback(epoch_copies(args.out, args.epochs))
    trainer.train()
    if torch.cuda.is_available():
        print(f"peak GPU memory {torch.cuda.max_memory_allocated() / 2**30:.1f} GiB")
    if preferred:
        trainer.save_model(f"{args.out}-sft")
        print(f"saved the rows-only adapter to {args.out}-sft")
        split = max(1, int(len(preferred) * args.holdout))
        preference_train(trainer.model, preferred[split:], preferred[:split], beta=args.pref_beta, lr=args.pref_lr,
                         epochs=args.pref_epochs, accum=args.grad_accum, fused=args.liger,
                         context=getattr(trainer, "maybe_activation_offload_context", None))
        if torch.cuda.is_available():
            print(f"peak GPU memory {torch.cuda.max_memory_allocated() / 2**30:.1f} GiB")
    trainer.save_model(args.out)
    print(f"saved adapter to {args.out}")
    return 0


def stamped(data: str, label: str, kind: str) -> list[dict]:
    """A data file's lines, if it carries a version stamp (provenance.py)."""
    stamp = provenance.read_stamp(Path(data))
    if stamp is None:
        raise SystemExit(f"{data} has no version stamp ({provenance.sidecar(Path(data)).name}); "
                         "train only on files made by the stamped data steps")
    part = [json.loads(line) for line in Path(data).read_text(encoding="utf-8").splitlines()]
    print(f"{label} {data}: {len(part)} {kind}, {stamp}")
    return part


def tokenize_pairs(base: str, pairs: list[dict], max_length: int) -> list[tuple[dict, dict]]:
    """Each pair as two rows, the request with the chosen and with the rejected
    reply, trained on that reply only; a pair either of whose rows is over
    --max-length or not rendered as the server would is dropped."""
    random.Random(0).shuffle(pairs)
    sides = [{"messages": [*pair["messages"], pair[side]], "tools": pair.get("tools"), "train": "last",
              "thinking": pair.get("thinking", False)} for pair in pairs for side in ("chosen", "rejected")]
    results = tokenize_rows(base, sides, max_length)
    kept = [(c, r) for c, r in zip(results[::2], results[1::2], strict=True)
            if isinstance(c, dict) and isinstance(r, dict)
            and len(c["input_ids"]) <= max_length and len(r["input_ids"]) <= max_length]
    print(f"pairs {len(kept)} of {len(pairs)} (the rest over --max-length {max_length} or not rendered as served)")
    return kept


def epoch_copies(out: str, epochs: float):
    """A callback saving the adapter at the end of every epoch but the last, next to the final one."""
    from transformers import TrainerCallback

    class EpochCopies(TrainerCallback):
        def on_epoch_end(self, args, state, control, model=None, **kwargs):
            epoch = round(state.epoch)
            if epoch < epochs and model is not None:
                model.save_pretrained(f"{out}-e{epoch}")
                print(f"saved the epoch-{epoch} adapter to {out}-e{epoch}", flush=True)

    return EpochCopies()


def window_attention(module, query, key, value, attention_mask, dropout=0.0, scaling=None,
                     sliding_window=None, **kwargs):
    """Attention for training on whole rows without a length x length mask.

    Under "sdpa" a 32K-token row got a materialized 32K x 32K mask (0.9 GiB),
    and Gemma 4's sliding-window layers (5 of every 6, a 512-token window)
    computed attention over the whole row: a step took 105 s, now 40 s. Here a
    sliding-window layer cuts the row into window-sized blocks and each block
    attends only to itself and the block before it, masked to the window;
    other layers use sdpa's causal kernel. The model gets no attention mask
    (this name has no mask function), which is right because TRL pads on the
    right: under causal attention no real token sees the padding.
    check() compares this with sdpa under transformers' own window mask."""
    import torch
    from transformers.integrations.sdpa_attention import (
        repeat_kv,
        sdpa_attention_forward,
    )

    if not sliding_window:
        return sdpa_attention_forward(module, query, key, value, None, dropout, scaling, **kwargs)
    batch, heads, length, dim = query.shape
    if key.shape[2] != length:
        raise ValueError("window attention is for training on whole rows, not a cache")
    groups = getattr(module, "num_key_value_groups", 1)
    key, value = repeat_kv(key, groups), repeat_kv(value, groups)
    width = sliding_window
    blocks = -(-length // width)

    def split(x):  # [B, H, L, D] -> [B * blocks, H, width, D]
        x = torch.nn.functional.pad(x, (0, 0, 0, blocks * width - length))
        return x.view(batch, heads, blocks, width, dim).transpose(1, 2).reshape(
            batch * blocks, heads, width, dim)

    def with_previous(x):  # each block after the one before it: [B * blocks, H, 2 * width, D]
        x = split(x).view(batch, blocks, heads, width, dim)
        previous = torch.nn.functional.pad(x, (0, 0, 0, 0, 0, 0, 1, 0))[:, :-1]
        return torch.cat([previous, x], dim=3).view(batch * blocks, heads, 2 * width, dim)

    # Query i of block b is token b*width+i; key j is token (b-1)*width+j. The
    # window lets a query see itself and the width-1 tokens before it.
    i = torch.arange(width, device=query.device)[:, None]
    j = torch.arange(2 * width, device=query.device)[None, :]
    mask = ((j > i) & (j <= i + width)).expand(blocks, width, 2 * width).clone()
    mask[0, :, :width] = False  # the first block has no block before it
    mask = mask[:, None].repeat(batch, 1, 1, 1)
    output = torch.nn.functional.scaled_dot_product_attention(
        split(query), with_previous(key), with_previous(value), attn_mask=mask,
        dropout_p=dropout, scale=scaling)
    output = output.view(batch, blocks, heads, width, dim).transpose(2, 3)
    return output.reshape(batch, blocks * width, heads, dim)[:, :length], None


def check_window_attention() -> float:
    """Largest difference between window_attention and sdpa under
    transformers' sliding-window causal mask, on random float32 inputs whose
    length is not a multiple of the window."""
    import torch
    from transformers.integrations.sdpa_attention import sdpa_attention_forward
    from transformers.masking_utils import sliding_window_causal_mask_function

    torch.manual_seed(0)
    width, length = 64, 64 * 5 + 17
    module = torch.nn.Module()
    module.num_key_value_groups, module.is_causal = 4, True
    query = torch.randn(2, 8, length, 32)
    key, value = torch.randn(2, 2, length, 32), torch.randn(2, 2, length, 32)
    allowed = sliding_window_causal_mask_function(width)
    positions = torch.arange(length)
    reference_mask = allowed(0, 0, positions[:, None], positions[None, :])[None, None]
    reference, _ = sdpa_attention_forward(module, query, key, value, reference_mask, scaling=0.2)
    windowed, _ = window_attention(module, query, key, value, None, scaling=0.2, sliding_window=width)
    return (reference - windowed).abs().max().item()


def lookup_in_ram(parent, attribute: str) -> None:
    """Replace parent.<attribute>, a frozen embedding table, with a lookup
    that keeps the table in RAM: ids go there, rows come back to the ids'
    device. The table is not a registered submodule, so the trainer moving
    the model to the GPU leaves it where it is."""
    import torch

    class RamLookup(torch.nn.Module):
        def __init__(self, table: torch.nn.Module) -> None:
            super().__init__()
            object.__setattr__(self, "table", table.to("cpu"))

        def forward(self, ids: torch.Tensor) -> torch.Tensor:
            return self.table(ids.to("cpu")).to(ids.device)

    setattr(parent, attribute, RamLookup(getattr(parent, attribute)))


# Characters per token is about 3-4 for code and 1-2 for Chinese: a row with
# more than this many characters per allowed token is over the limit for sure.
CHARS_PER_TOKEN_CEILING = 6
_TOKENIZER = None


def _row_chars(row: dict) -> int:
    return sum(len(str(m.get("content") or "")) + sum(len(str(c.get("function", {}).get("arguments") or ""))
                                                       for c in m.get("tool_calls") or [])
               for m in row["messages"])


def _start_worker(base: str) -> None:
    global _TOKENIZER
    from transformers import AutoTokenizer

    _TOKENIZER = AutoTokenizer.from_pretrained(base)


def _tokenize_job(job: tuple[dict, int]) -> dict | str:
    row, max_length = job
    if _row_chars(row) > max_length * CHARS_PER_TOKEN_CEILING:
        return "long"
    try:
        return tokenize_row(_TOKENIZER, row)
    except ValueError:
        return "broken"


def tokenize_rows(base: str, rows: list[dict], max_length: int) -> list[dict | str]:
    """Every row tokenized (tokenize_row) in worker processes, or "long" /
    "broken". Rendering each turn's prefix makes a long agent row take about
    a second; tens of thousands of them need all the cores."""
    import multiprocessing
    import os

    workers = max(1, min(16, (os.cpu_count() or 2) - 2))
    jobs = [(row, max_length) for row in rows]
    with multiprocessing.get_context("spawn").Pool(workers, _start_worker, (base,)) as pool:
        return pool.map(_tokenize_job, jobs, chunksize=4)


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
    # A row with the teacher's reasoning (EdgeAgent bench/dataset.py marks it
    # "thinking") is rendered as the server renders a thinking request: the
    # template's think switch on, each reply after the last user message with
    # its reasoning channel. Other rows as before, thinking off.
    thinking = bool(row.get("thinking"))

    def render(part: list[dict], prompt: bool) -> str:
        return tokenizer.apply_chat_template(
            part, tools=tools, tokenize=False, add_generation_prompt=prompt,
            enable_thinking=thinking)

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
        # <turn|>, or <|tool_response> after a tool call; Qwen: <|im_end|>),
        # which llama.cpp stops on (its end-of-generation tokens).
        for position in range(len(prompt_ids), len(upto_ids)):
            mask[position] = 1
    return {"input_ids": full_ids, "completion_mask": mask}


def completion_logp(model, item: dict, fused: bool):
    """The sum of the log-probabilities of a row's trained tokens. With liger
    (--liger) its fused loss never makes the logits, also outside training
    (skip_logits); num_items_in_batch=1 makes either loss the sum."""
    import torch

    ids = torch.tensor([item["input_ids"]], device=model.device)
    labels = ids.masked_fill(torch.tensor([item["completion_mask"]], device=model.device) == 0, -100)
    extra = {"skip_logits": True} if fused else {}
    return -model(input_ids=ids, labels=labels, num_items_in_batch=1, **extra).loss


def preference_train(model, pairs: list[tuple[dict, dict]], held: list[tuple[dict, dict]], *, beta: float,
                     lr: float, epochs: int, accum: int, fused: bool, context=None) -> dict[str, float]:
    """DPO on (chosen, rejected) rows, the model as it is now the reference.
    The loss -log sigmoid(z), z = beta * ((chosen - its reference) - (rejected -
    its reference)) in log-probabilities, has the gradient -beta * sigmoid(-z)
    * (d chosen - d rejected): z is measured without gradients first, then
    each side's forward and backward runs alone, so a step holds one row's
    activations, as the rows' training does, and not two. Prints the held
    pairs' loss and how many prefer the chosen reply, before and after."""
    import contextlib
    import math

    import torch

    context = context or contextlib.nullcontext()

    def softplus(x: float) -> float:  # log(1 + e^x), for any x
        return max(x, 0.0) + math.log1p(math.exp(-abs(x)))

    def measure(items):
        model.eval()
        with torch.no_grad():
            return [(completion_logp(model, c, fused).item(), completion_logp(model, r, fused).item())
                    for c, r in items]

    def report(name: str, now, reference) -> dict[str, float]:
        zs = [beta * ((pc - rc) - (pr - rr)) for (pc, pr), (rc, rr) in zip(now, reference, strict=True)]
        loss = sum(softplus(-z) for z in zs) / max(1, len(zs))
        right = sum(z > 0 for z in zs) / max(1, len(zs))
        print(f"{name}: loss {loss:.4f}, prefers the chosen reply {right:.0%} of {len(zs)}", flush=True)
        return {"loss": loss, "right": right}

    reference, held_reference = measure(pairs), measure(held)
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=lr, weight_decay=0.0)
    order = list(range(len(pairs)))
    window: list[float] = []
    for epoch in range(epochs):
        random.Random(epoch).shuffle(order)
        for n, k in enumerate(order, 1):
            chosen, rejected = pairs[k]
            ((pc, pr),) = measure([pairs[k]])
            rc, rr = reference[k]
            z = beta * ((pc - rc) - (pr - rr))
            weight = beta * math.exp(-softplus(z))  # beta * sigmoid(-z)
            window.append(softplus(-z))
            model.train()
            for row, sign in ((chosen, -1.0), (rejected, 1.0)):
                with context:
                    (sign * weight / accum * completion_logp(model, row, fused)).backward()
            if n % accum == 0 or n == len(order):
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                print(f"preference epoch {epoch + 1} pair {n}/{len(order)}: loss {sum(window) / len(window):.4f}",
                      flush=True)
                window = []
    model.train()
    if held:
        report("held pairs before", held_reference, held_reference)
        return report("held pairs after", measure(held), held_reference)
    return {}


def check_pairs(preferred: list[tuple[dict, dict]], tokenizer) -> int:
    """The trained span of a pair's two rows: the chosen and the rejected
    reply each, ending its turn."""
    if not preferred:
        return 0
    end = tokenizer.convert_tokens_to_ids(["<turn|>", "<|tool_response>", "<|im_end|>"])
    for name, item in zip(("CHOSEN", "REJECTED"), preferred[0], strict=True):
        span = [t for t, m in zip(item["input_ids"], item["completion_mask"], strict=True) if m]
        print(f"{name} >>>" + tokenizer.decode(span)[-600:] + "<<<")
        if not any(t in end for t in span):
            print("MASK WRONG: a pair's reply must end its turn with the end-of-turn marker")
            return 1
    return 0


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
    end = tokenizer.convert_tokens_to_ids(["<turn|>", "<|tool_response>", "<|im_end|>"])
    if not spans or any(not any(t in end for t in ids[a:b]) for a, b in spans):
        print("MASK WRONG: every trained span must end its turn with the end-of-turn marker")
        return 1
    difference = check_window_attention()
    print(f"window attention vs sdpa: max difference {difference:.1e}")
    if difference > 1e-4:
        print("WINDOW ATTENTION WRONG: it must match sdpa under the sliding-window mask")
        return 1
    model = trainer.model
    sample = torch.tensor([ids[-64:]], device=model.device)
    with torch.no_grad():
        logits = model(input_ids=sample).logits
    print(f"forward ok: logits {tuple(logits.shape)}")
    return 0 if positions else 1


if __name__ == "__main__":
    raise SystemExit(main())
