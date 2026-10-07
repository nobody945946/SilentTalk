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
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT_DIR), str(Path(__file__).resolve().parent)]

from eval_server import MODEL, serve  # noqa: E402

from silenttalk.conversation import ConversationTurn  # noqa: E402
from silenttalk.copilot import llm  # noqa: E402
from silenttalk.persona import MACHINE_SPIRIT  # noqa: E402

DATA = Path(__file__).with_name("task_scope_eval.jsonl")
PORT = 18412
OWNER_ID = 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--lora",
        type=Path,
        help="the adapter the product would load (applied to this question)",
    )
    args = parser.parse_args()
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()]
    meta, items = rows[0]["meta"], rows[1:]
    owner = meta["owner"]
    # The card the app ships, as the app sends it.
    persona = MACHINE_SPIRIT
    model = llm.LocalReplyModel(
        args.model,
        port=PORT,
        context_size=8192,
        agent_dispatch=True,
        owner_id=OWNER_ID,
        owner_name=owner,
        ai_honesty="machine",
    )
    model.set_persona(persona)
    process = serve(args.model, PORT, args.lora)
    records = []
    try:
        for item in items:
            lines = [*item.get("context", []), item["text"]]
            turns = [
                ConversationTurn(OWNER_ID, owner, line, via="text", created_at=float(i))
                for i, line in enumerate(lines)
            ]
            started = time.monotonic()
            scope = model.transport.request_gate(
                model.task_scope_messages(turns=turns, engagement="called"),
                args.lora is not None,
            )
            records.append(
                {
                    "id": item["id"],
                    "changes": item["changes"],
                    "said_changes": scope == "是",
                    "ms": round((time.monotonic() - started) * 1000),
                }
            )
    finally:
        process.terminate()
        process.wait(timeout=60)
    reads = [r for r in records if not r["changes"]]
    changes = [r for r in records if r["changes"]]
    summary = {
        "model": args.model.name,
        "lora": args.lora.name if args.lora else None,
        "items": len(records),
        "correct": sum(r["said_changes"] == r["changes"] for r in records)
        / len(records),
        # Reads taken as changes: the task runs as before (changes ask the owner).
        "reads_taken_as_changes": [r["id"] for r in reads if r["said_changes"]],
        # Changes taken as reads: the Agent cannot do them and says so; the owner asks again.
        "changes_taken_as_reads": [r["id"] for r in changes if not r["said_changes"]],
        "ms_median": sorted(r["ms"] for r in records)[len(records) // 2],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.out:
        args.out.write_text(
            json.dumps(
                {"summary": summary, "records": records}, ensure_ascii=False, indent=1
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
