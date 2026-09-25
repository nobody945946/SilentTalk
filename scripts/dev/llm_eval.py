"""LLM reply score: format, script, and whether each lane keeps its intent.

Usage (from the repo root, llama-server on PATH, model in .runtime/models/llm):
    python scripts/dev/llm_eval.py
    python scripts/dev/llm_eval.py --model Qwen3-4B-Q4_K_M.gguf --runs 3

Replies are sampled (temperature 0.65), so compare averages over >= 2 runs.
Targets and the 2026-09-25 baseline for Qwen3-1.7B-Q4_K_M are printed at the end.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

from opencc import OpenCC

from silenttalk.config import CopilotConfig
from silenttalk.copilot.smoke import (
    LLM_SCENES,
    build_reply_model,
    run_scenes,
)
from silenttalk.copilot.types import REPLY_LANES

_TO_TRADITIONAL = OpenCC("s2tw")
# Lane-intent heuristics: an AGREE reply should not be a question; ASK should.
TARGETS = {
    "lanes_filled": ("≥", 0.95),
    "simplified": ("≤", 0.0),
    "agree_is_question": ("≤", 0.20),
    "ask_is_question": ("≥", 0.90),
    "median_seconds": ("≤", 3.0),
}


def is_question(text: str) -> bool:
    return text.rstrip().endswith(("？", "?", "嗎", "呢"))


async def evaluate(model_file: str | None, runs: int) -> dict[str, float]:
    model = build_reply_model(PROJECT_DIR, CopilotConfig(), model_file)
    await model.start()
    try:
        results = []
        for run in range(runs):
            print(f"\n######## run {run + 1}/{runs}")
            for result in await run_scenes(model, LLM_SCENES):
                results.append(result)
                print(f"\n>> {result.trigger}  ({result.seconds:.2f}s)")
                for lane in REPLY_LANES:
                    text = result.suggestions.text_for(lane)
                    print(f"   {lane.key.upper()} {lane.label:<6} {text or '—'}")
    finally:
        await model.stop()

    lanes = [
        (lane, r.suggestions.text_for(lane)) for r in results for lane in REPLY_LANES
    ]
    filled = [text for _, text in lanes if text]
    agree = [text for lane, text in lanes if lane.code == "AGREE" and text]
    ask = [text for lane, text in lanes if lane.code == "ASK" and text]
    return {
        "lanes_filled": len(filled) / len(lanes),
        "simplified": sum(_TO_TRADITIONAL.convert(t) != t for t in filled)
        / max(1, len(filled)),
        "agree_is_question": sum(map(is_question, agree)) / max(1, len(agree)),
        "ask_is_question": sum(map(is_question, ask)) / max(1, len(ask)),
        "median_seconds": statistics.median(r.seconds for r in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--model", help="file name in .runtime/models/llm (default: config default)"
    )
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()

    scores = asyncio.run(evaluate(args.model, max(1, args.runs)))
    print("\n==== SCORE (target)")
    all_met = True
    for name, value in scores.items():
        op, target = TARGETS[name]
        met = value >= target if op == "≥" else value <= target
        all_met &= met
        print(f"{name:<18} {value:6.2f}   {op} {target:<5} {'OK' if met else 'MISS'}")
    print("ALL TARGETS MET" if all_met else "SOME TARGETS MISSED")
    return 0 if all_met else 1


if __name__ == "__main__":
    raise SystemExit(main())
