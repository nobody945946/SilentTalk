"""Measure the chat work gate: for a line that calls the character, does it
ask for work that stays within the chat (lookups, code written not run,
articles, posted images or files, translations)? A miss means the character
answers in person; a false alarm sends chat - or a request to touch the
computer, which the "public" scope then cannot do - to the Agent.

Runs the product's own question (LocalReplyModel.chat_task's gate, the
machine-spirit card) against a model served here with EdgeAgent's own server
arguments. Data: chat_task_eval.jsonl (EVAL ONLY, written with Claude).

  .venv/bin/python scripts/dev/chat_task_eval.py [--model GGUF] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from dataclasses import replace
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
EDGE_AGENT_ROOT = Path.home() / "EdgeAgent"
sys.path[:0] = [str(PROJECT_DIR), str(EDGE_AGENT_ROOT)]

from edge_agent.runtime import build_server_args  # noqa: E402

from silenttalk.copilot import llm  # noqa: E402
from silenttalk.copilot.persona import persona_from_dict  # noqa: E402
from silenttalk.copilot.types import ConversationTurn  # noqa: E402

SERVER = PROJECT_DIR / ".runtime/tools/llama.cpp-b11193-src/build-cuda/bin/llama-server"
MODEL = PROJECT_DIR / ".runtime/models/llm/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"
CARD = PROJECT_DIR / ".runtime/dev/chardata-ms1/personas.jsonl"
DATA = Path(__file__).with_name("chat_task_eval.jsonl")
PORT = 18413
OWNER_ID = 1


def serve(model: Path) -> subprocess.Popen:
    args = build_server_args(str(SERVER), model, port=PORT, context_size=8192, threads=8,
                             gpu_layers=99, low_vram=True, slots=1)
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(600):
        if process.poll() is not None:
            raise SystemExit("llama-server exited while loading")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2):
                return process
        except OSError:
            time.sleep(1)
    process.terminate()
    raise SystemExit("llama-server did not become ready")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()]
    meta, items = rows[0]["meta"], rows[1:]
    speaker = meta["speaker"]
    card = json.loads(CARD.read_text(encoding="utf-8").splitlines()[0])
    persona = replace(persona_from_dict(card), nickname="機魂、馬基納")
    model = llm.LocalReplyModel(args.model, port=PORT, context_size=8192, agent_dispatch=True,
                                owner_id=OWNER_ID, owner_name=speaker, ai_honesty="machine")
    model.set_persona(persona)
    process = serve(args.model)
    records = []
    try:
        for item in items:
            turns = [ConversationTurn(7, speaker, item["text"], via="voice")]
            started = time.monotonic()
            gate = model.gate_messages(turns=turns, question="chat_task")
            said = model._request_gate(gate, False) == "是"
            records.append({"id": item["id"], "task": item["task"], "said_task": said,
                            "ms": round((time.monotonic() - started) * 1000)})
    finally:
        process.terminate()
        process.wait(timeout=60)
    summary = {
        "model": args.model.name,
        "items": len(records),
        "correct": sum(r["said_task"] == r["task"] for r in records) / len(records),
        "work_missed": [r["id"] for r in records if r["task"] and not r["said_task"]],
        "sent_to_agent_wrongly": [r["id"] for r in records if not r["task"] and r["said_task"]],
        "ms_median": sorted(r["ms"] for r in records)[len(records) // 2],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "records": records},
                                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
