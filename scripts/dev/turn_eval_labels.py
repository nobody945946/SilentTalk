"""Cross-check turn_eval_data.jsonl labels with a local open-weight model (HANDOFF M1).

Usage (from the repo root; starts and stops its own llama-server):
    python scripts/dev/turn_eval_labels.py                       # Qwen3-30B-A3B, port 18400
    python scripts/dev/turn_eval_labels.py --n-cpu-moe 30 --port 18401
    python scripts/dev/turn_eval_labels.py --url http://127.0.0.1:18400   # server already up

For every decision point the model sees the persona sheet, the engagement
mode and the conversation so far, and answers 是/否 (grammar-constrained):
should the character speak now? Agreement is computed on `speak`/`silent`
labels (`either` is reported but not scored). Disagreements are written to
.runtime/dev/turn_eval/label_check.json for a human-style re-read: genuinely
ambiguous -> "either", unclear writing -> rewrite the line, model wrong -> keep.

The GPU on the dev box is shared: the expert weights of the first --n-cpu-moe
layers stay in RAM, which keeps VRAM around 8 GB. Only ids and numbers are
printed.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import turn_eval  # noqa: E402

PROJECT_DIR = turn_eval.PROJECT_DIR
TEACHER = PROJECT_DIR / ".runtime" / "models" / "teacher" / "Qwen3-30B-A3B-Instruct-2507-UD-Q4_K_XL.gguf"
OUT_PATH = turn_eval.OUT_DIR / "label_check.json"

SYSTEM = """你在幫忙標註 Discord 語音聊天的測試資料。頻道裡有一個 AI 扮演的角色「{name}」，和幾個真人朋友一起用語音聊天；角色聽得到所有人說的話，也可以開口講話。
對話是語音辨識的結果：可能有同音錯字（包括名字被聽錯，例如把角色的名字聽成同音的別的字）、幾乎沒有標點。標「（打字）」的是聊天室的文字訊息；標「（@{name}）」代表那則訊息在 Discord 上直接 @ 了角色或回覆了角色的訊息。標「（角色）」的是角色自己說過的話。

角色的參與程度：{engagement}

你的工作：聽完最後一句之後，判斷角色現在該不該開口說話。只回答「是」或「否」。

【角色人設】
{sheet}"""

ENGAGEMENT = {
    "called": "「被叫才回」——只有在有人叫它、直接問它、要它做事、或是在回應它剛才說的話時才開口。"
              "別人彼此之間的對話、只是提到它但不是在跟它說話、別人的私事，都不開口。",
    "active": "「會主動加入」——有人叫它、問它、要它做事、或在回應它剛才說的話時要開口；"
              "此外，話題是它有興趣或懂的、或有人在問在場所有人時，也可以自己插話。"
              "但別人在私下聊心事、或明顯是兩個人之間的對話時不插嘴。",
}

QUESTION = "最後一句是：{speaker}：{text}\n角色「{name}」現在該開口說話嗎？只回答「是」或「否」。"
GRAMMAR = 'root ::= "是" | "否"'


def render_line(line: dict[str, Any], name: str) -> str:
    if line.get("self"):
        return f"{name}（角色）：{line['text']}"
    marks = ""
    if line.get("via") == "text":
        marks += "（打字）"
    if line.get("mention"):
        marks += f"（@{name}）"
    return f"{line['speaker']}{marks}：{line['text']}"


def ask(url: str, system: str, user: str) -> tuple[str, float | None]:
    payload = {
        "model": "local",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "cache_prompt": True,
        "temperature": 0.0,
        "max_tokens": 4,
        "grammar": GRAMMAR,
        "logprobs": True,
        "top_logprobs": 5,
    }
    request = urllib.request.Request(
        url + "/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        body = json.loads(response.read().decode("utf-8"))
    choice = body["choices"][0]
    answer = str(choice["message"]["content"] or "").strip()
    p_yes = None
    try:
        first = choice["logprobs"]["content"][0]
        probs = {c["token"]: math.exp(c["logprob"]) for c in first.get("top_logprobs", [])}
        yes, no = probs.get("是", 0.0), probs.get("否", 0.0)
        if yes + no > 0:
            p_yes = round(yes / (yes + no), 3)
    except (KeyError, IndexError, TypeError):
        pass
    return answer, p_yes


def start_server(args: argparse.Namespace) -> subprocess.Popen[bytes]:
    turn_eval.ensure_llama_server_on_path()
    command = [
        "llama-server", "--model", str(TEACHER), "--host", "127.0.0.1",
        "--port", str(args.port), "--ctx-size", str(args.ctx), "--parallel", "1",
        "--n-gpu-layers", "99", "--n-cpu-moe", str(args.n_cpu_moe),
        "--threads", str(args.threads), "--jinja", "--flash-attn", "on",
    ]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"llama-server pid {process.pid} port {args.port} n-cpu-moe {args.n_cpu_moe}", flush=True)
    url = f"http://127.0.0.1:{args.port}"
    deadline = time.time() + 600
    while time.time() < deadline:
        if process.poll() is not None:
            raise SystemExit(f"llama-server exited with {process.returncode}")
        try:
            with urllib.request.urlopen(url + "/health", timeout=2) as response:
                if response.status == 200:
                    return process
        except OSError:
            pass
        time.sleep(2)
    process.terminate()
    raise SystemExit("llama-server did not become healthy")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data", type=Path, default=turn_eval.DATA_PATH)
    parser.add_argument("--url", help="use a server that is already running")
    parser.add_argument("--port", type=int, default=18400)
    parser.add_argument("--n-cpu-moe", type=int, default=30)
    parser.add_argument("--ctx", type=int, default=8192)
    parser.add_argument("--threads", type=int, default=max(4, (os.cpu_count() or 8) - 4))
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--only", help="comma-separated conversation ids")
    args = parser.parse_args()

    from silenttalk.copilot import persona as persona_module

    test_set = turn_eval.load_test_set(args.data)
    if args.only:
        wanted = set(args.only.split(","))
        test_set.conversations = [c for c in test_set.conversations if c.id in wanted]
    process = None if args.url else start_server(args)
    url = args.url or f"http://127.0.0.1:{args.port}"
    results: list[dict[str, Any]] = []
    started = time.time()
    try:
        for conv in test_set.conversations:
            persona = turn_eval.resolve_persona(persona_module, test_set, conv.persona_id)
            system = SYSTEM.format(
                name=persona.name, engagement=ENGAGEMENT[conv.engagement],
                sheet=persona.render_system_block(),
            )
            for index, line in enumerate(conv.lines):
                if line.get("self"):
                    continue
                chat = "\n".join(render_line(l, persona.name) for l in conv.lines[: index + 1])
                user = "對話：\n" + chat + "\n\n" + QUESTION.format(
                    speaker=line["speaker"], text=line["text"], name=persona.name
                )
                answer, p_yes = ask(url, system, user)
                results.append({
                    "conv": conv.id, "index": index, "expect": line["expect"],
                    "tags": line["tags"], "qwen": "speak" if answer == "是" else "silent",
                    "p_yes": p_yes,
                })
            print(f"  {conv.id}: done", flush=True)
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(20)
            except subprocess.TimeoutExpired:
                process.kill()

    scored = [r for r in results if r["expect"] != "either"]
    agree = sum(r["qwen"] == r["expect"] for r in scored)
    either = [r for r in results if r["expect"] == "either"]
    disagreements = [r for r in scored if r["qwen"] != r["expect"]]
    summary = {
        "decision_points": len(results),
        "scored": len(scored),
        "agreement": round(agree / len(scored), 4) if scored else None,
        "speak_agree": sum(r["qwen"] == "speak" for r in scored if r["expect"] == "speak"),
        "speak_total": sum(r["expect"] == "speak" for r in scored),
        "silent_agree": sum(r["qwen"] == "silent" for r in scored if r["expect"] == "silent"),
        "silent_total": sum(r["expect"] == "silent" for r in scored),
        "either_qwen_speak": sum(r["qwen"] == "speak" for r in either),
        "either_total": len(either),
        "seconds": round(time.time() - started, 1),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"summary": summary, "disagreements": disagreements, "results": results},
        ensure_ascii=False, indent=1,
    ), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print(f"disagreements {len(disagreements)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
