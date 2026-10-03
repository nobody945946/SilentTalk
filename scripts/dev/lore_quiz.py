"""How much Warhammer 40,000 background a model knows (evaluation only).

Each question of lore_quiz_data.QUIZ is asked twice with the options in two
different seeded orders, answer constrained to one letter, thinking off. A
question counts as known only when both answers are right (chance: 1/16).

    .venv/bin/python scripts/dev/lore_quiz.py --model .runtime/models/llm/Qwen3.5-4B-Q4_K_M.gguf
    .venv/bin/python scripts/dev/lore_quiz.py --model ... --ngl 99      # on the GPU
Results append to .runtime/dev/lore-quiz.jsonl (scores only).
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lore_quiz_data import QUIZ  # noqa: E402

SERVER = ROOT / ".runtime/tools/llama.cpp-b11193-src/build-cuda/bin/llama-server"
RESULTS = ROOT / ".runtime/dev/lore-quiz.jsonl"
LETTERS = "ABCD"
SYSTEM = "你熟悉《戰鎚40K》(Warhammer 40,000) 的背景設定。回答選擇題，只輸出一個字母。"


def orders(index: int) -> list[list[int]]:
    rng = random.Random(1000 + index)
    first = rng.sample(range(4), 4)
    second = first[::-1] if first[::-1] != first else rng.sample(range(4), 4)
    return [first, second]


def ask(port: int, question: str, options: list[str]) -> str:
    text = question + "\n" + "\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(options))
    body = json.dumps({
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": text + "\n只回答 A、B、C 或 D。"}],
        "temperature": 0.0, "max_tokens": 2, "grammar": 'root ::= "A" | "B" | "C" | "D"',
        "chat_template_kwargs": {"enable_thinking": False}}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", body,
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=1800) as response:
        return json.loads(response.read())["choices"][0]["message"]["content"].strip()[:1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--ngl", type=int, default=0, help="GPU layers (0 = CPU)")
    parser.add_argument("--threads", type=int, default=12)
    parser.add_argument("--port", type=int, default=18220)
    parser.add_argument("--parallel", type=int, default=4)
    args = parser.parse_args()
    server = subprocess.Popen(
        [str(SERVER), "--model", str(args.model), "--host", "127.0.0.1", "--port",
         str(args.port), "--ctx-size", str(1024 * args.parallel), "--parallel",
         str(args.parallel), "--n-gpu-layers", str(args.ngl), "--threads",
         str(args.threads), "--jinja", "--fit", "off"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started = time.monotonic()
    try:
        deadline = time.monotonic() + 1200
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/health", timeout=2):
                    break
            except OSError:
                if server.poll() is not None or time.monotonic() > deadline:
                    raise SystemExit("server did not start") from None
                time.sleep(3)
        jobs = [(i, order) for i in range(len(QUIZ)) for order in orders(i)]

        def run(job: tuple[int, list[int]]) -> tuple[int, bool]:
            index, order = job
            question, options, correct = QUIZ[index]
            answer = ask(args.port, question, [options[k] for k in order])
            return index, LETTERS.index(answer) == order.index(correct) if answer in LETTERS else False

        with ThreadPoolExecutor(args.parallel) as pool:
            results = list(pool.map(run, jobs))
    finally:
        server.terminate()
        server.wait(timeout=60)
    per_question: dict[int, list[bool]] = {}
    for index, right in results:
        per_question.setdefault(index, []).append(right)
    known = sum(all(v) for v in per_question.values())
    row = {"model": args.model.name, "questions": len(QUIZ),
           "known_both_orders": round(known / len(QUIZ), 3),
           "answer_accuracy": round(sum(r for _, r in results) / len(results), 3),
           "seconds": round(time.monotonic() - started)}
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
