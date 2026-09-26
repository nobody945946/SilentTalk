"""Fine-tune a small reply model on distill_data.py output (LoRA, one GPU).

Usage (needs the separate training venv, see HANDOFF.md):
    .runtime/train-venv/bin/python scripts/dev/train_lora.py \
        --base Qwen/Qwen3-4B-Instruct-2507 --out .runtime/dev/lora/qwen3-4b-2507

Then convert the adapter for llama.cpp (convert_lora_to_gguf.py ships in the
llama.cpp source tree of the same build as llama-server):
    python <llama.cpp>/convert_lora_to_gguf.py --base <hf snapshot dir> \
        --outtype f16 --outfile persona-lora.gguf .runtime/dev/lora/qwen3-4b-2507

One generic adapter is trained on many synthetic character sheets, so it
works for whatever persona the user writes; it is not per-persona.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA = PROJECT_DIR / ".runtime" / "dev" / "distill" / "replies.jsonl"


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
    args = parser.parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    tokenizer = AutoTokenizer.from_pretrained(args.base)

    def render(row: dict) -> dict[str, str]:
        # Render exactly like llama-server --jinja with enable_thinking off, so
        # the adapter sees the same tokens at inference time. Loss is on the
        # completion (the four lines) only.
        *prompt, answer = row["messages"]
        text = tokenizer.apply_chat_template(
            prompt, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        return {"prompt": text, "completion": answer["content"] + tokenizer.eos_token}

    rows = [json.loads(line) for line in Path(args.data).read_text(encoding="utf-8").splitlines()]
    random.Random(0).shuffle(rows)
    split = max(1, int(len(rows) * args.holdout))
    train = Dataset.from_list([render(r) for r in rows[split:]])
    evaluation = Dataset.from_list([render(r) for r in rows[:split]])
    print(f"train {len(train)}  eval {len(evaluation)}")
    print(train[0]["prompt"][-300:] + train[0]["completion"])

    model = AutoModelForCausalLM.from_pretrained(
        args.base, torch_dtype=torch.bfloat16, attn_implementation="sdpa"
    )
    config = SFTConfig(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=True,
        bf16=True,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="no",
        report_to=[],
        completion_only_loss=True,
        max_length=2048,
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
            target_modules="all-linear",
            task_type="CAUSAL_LM",
        ),
    )
    trainer.train()
    trainer.save_model(args.out)
    print(f"saved adapter to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
