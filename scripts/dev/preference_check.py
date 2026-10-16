"""Check train_lora.py's preference training on CPU with a tiny model and the
real tokenizer, before a GPU spends hours on it:

1. completion_logp is the sum of the trained tokens' log-probabilities (the
   loss with num_items_in_batch=1), as the logits say;
2. preference_train starts at DPO's log 2 (the reference is the model as it
   was) and ends preferring the chosen reply of a pair it trained on.

    .runtime/train-venv/bin/python scripts/dev/preference_check.py --base .runtime/hf/gemma-4-E4B-it-qat
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_lora  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="the base whose tokenizer and chat template rows use")
    args = parser.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoTokenizer, LlamaConfig, LlamaForCausalLM

    torch.manual_seed(0)
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    prompt = [{"role": "system", "content": "你是助理。"}, {"role": "user", "content": "幫我整理下載資料夾"}]
    chosen = train_lora.tokenize_row(tokenizer, {"messages": [*prompt, {"role": "assistant", "content": "好，我先列出裡面的檔案。"}]})
    rejected = train_lora.tokenize_row(tokenizer, {"messages": [*prompt, {"role": "assistant", "content": "我再想想。我再想想。我再想想。"}]})
    model = LlamaForCausalLM(LlamaConfig(vocab_size=len(tokenizer), hidden_size=32, intermediate_size=64,
                                         num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=1))
    model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj", "v_proj", "up_proj"],
                                             task_type="CAUSAL_LM"))

    model.eval()
    with torch.no_grad():
        summed = train_lora.completion_logp(model, chosen, fused=False).item()
        ids = torch.tensor([chosen["input_ids"]])
        logprobs = torch.log_softmax(model(input_ids=ids).logits[0, :-1].float(), dim=-1)
        manual = sum(logprobs[i - 1, chosen["input_ids"][i]].item()
                     for i, m in enumerate(chosen["completion_mask"]) if m)
    trained = sum(chosen["completion_mask"])
    print(f"completion_logp {summed:.4f}, from the logits {manual:.4f} ({trained} trained tokens)")
    if not math.isclose(summed, manual, rel_tol=1e-3, abs_tol=1e-3):
        print("LOGP WRONG: the sum of the trained tokens' log-probabilities must match the logits")
        return 1

    pair = (chosen, rejected)
    result = train_lora.preference_train(model, [pair], [pair], beta=0.1, lr=5e-2, epochs=30, accum=1,
                                         fused=False)
    if not (result["right"] == 1.0 and result["loss"] < math.log(2) - 0.05):
        print("PREFERENCE WRONG: after training on a pair the model must prefer its chosen reply")
        return 1
    print("preference training ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
