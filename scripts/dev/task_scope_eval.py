"""Measure the task scope gate: does the work the owner typed in his Agent
thread ask to change anything (files, settings, running programs)? A "no"
sends the task to the Agent read-only, where EdgeAgent refuses every change.

Runs the product's own questions (LocalReplyModel, the machine-spirit card)
against a model served here with EdgeAgent's own server arguments. Data:
task_scope_eval.jsonl (EVAL ONLY, written with Claude).

  .venv/bin/python scripts/dev/task_scope_eval.py [--model GGUF] [--out FILE]
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
from silenttalk.copilot.persona import Relationship, persona_from_dict  # noqa: E402
from silenttalk.copilot.types import ConversationTurn  # noqa: E402

SERVER = PROJECT_DIR / ".runtime/tools/llama.cpp-b11193-src/build-cuda/bin/llama-server"
MODEL = PROJECT_DIR / ".runtime/models/llm/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"
CARD = PROJECT_DIR / ".runtime/dev/chardata-ms1/personas.jsonl"
DATA = Path(__file__).with_name("task_scope_eval.jsonl")
PORT = 18412
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
    owner = meta["owner"]
    card = json.loads(CARD.read_text(encoding="utf-8").splitlines()[0])
    persona = persona_from_dict(card)
    persona = replace(persona, relationships=(
        Relationship(owner, card["owner_relation"]), *persona.relationships))
    model = llm.LocalReplyModel(args.model, port=PORT, context_size=8192, agent_dispatch=True,
                                owner_id=OWNER_ID, owner_name=owner, ai_honesty="machine")
    model.set_persona(persona)
    process = serve(args.model)
    records = []
    try:
        for item in items:
            lines = [*item.get("context", []), item["text"]]
            turns = [ConversationTurn(OWNER_ID, owner, line, via="text", created_at=float(i))
                     for i, line in enumerate(lines)]
            started = time.monotonic()
            scope = model._request_gate(
                model._owner_question(turns, "called", llm._TASK_SCOPE_QUESTION), False)
            records.append({"id": item["id"], "changes": item["changes"],
                            "said_changes": scope == "是",
                            "ms": round((time.monotonic() - started) * 1000)})
    finally:
        process.terminate()
        process.wait(timeout=60)
    reads = [r for r in records if not r["changes"]]
    changes = [r for r in records if r["changes"]]
    summary = {
        "model": args.model.name,
        "items": len(records),
        "correct": sum(r["said_changes"] == r["changes"] for r in records) / len(records),
        # Reads taken as changes: the task runs as before (changes ask the owner).
        "reads_taken_as_changes": [r["id"] for r in reads if r["said_changes"]],
        # Changes taken as reads: the Agent cannot do them and says so; the owner asks again.
        "changes_taken_as_reads": [r["id"] for r in changes if not r["said_changes"]],
        "ms_median": sorted(r["ms"] for r in records)[len(records) // 2],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "records": records},
                                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
