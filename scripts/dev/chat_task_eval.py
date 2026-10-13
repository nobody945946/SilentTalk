"""Measure the chat work gate: for a line that calls the character, does it
ask for work that stays within the chat (lookups, code written not run,
articles, posted images or files, translations)? A miss means the character
answers in person; a false alarm sends chat - or a request to touch the
computer, which the "public" scope then cannot do - to the Agent.

Runs the product's own question (LocalReplyModel.chat_task's gate, the
machine-spirit card) against a model served here with EdgeAgent's own server
arguments. Data: chat_task_eval.jsonl (EVAL ONLY, written with Claude): one
spoken line each, or (spec v3) a few lines of chat whose last is asked about.

  .venv/bin/python scripts/dev/chat_task_eval.py [--model GGUF] [--out FILE]
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

DATA = Path(__file__).with_name("chat_task_eval.jsonl")
PORT = 18413
OWNER_ID = 1


def chat_of(item: dict, speaker: str, name: str) -> list[ConversationTurn]:
    """The chat an item asks about: one spoken line, or its turns (the last is
    the line asked about; "self" ones are the character's own)."""
    if "text" in item:
        return [ConversationTurn(7, speaker, item["text"], via="voice")]
    ids = {speaker: 7}
    return [ConversationTurn(0, name, turn["text"], is_self=True, via="voice") if turn.get("self")
            else ConversationTurn(ids.setdefault(turn["speaker"], 7 + len(ids)), turn["speaker"],
                                  turn["text"], via="voice")
            for turn in item["turns"]]


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
    speaker = meta["speaker"]
    # The card the app ships, as the app sends it.
    persona = MACHINE_SPIRIT
    model = llm.LocalReplyModel(
        args.model,
        port=PORT,
        context_size=8192,
        agent_dispatch=True,
        owner_id=OWNER_ID,
        owner_name=speaker,
        ai_honesty="machine",
    )
    model.set_persona(persona)
    process = serve(args.model, PORT, args.lora)
    records = []
    try:
        for item in items:
            turns = chat_of(item, speaker, persona.name)
            started = time.monotonic()
            gate = model.gate_messages(turns=turns, question="chat_task")
            said = model.transport.request_gate(gate, args.lora is not None) == "是"
            records.append(
                {
                    "id": item["id"],
                    "task": item["task"],
                    "said_task": said,
                    "ms": round((time.monotonic() - started) * 1000),
                }
            )
    finally:
        process.terminate()
        process.wait(timeout=60)
    summary = {
        "model": args.model.name,
        "lora": args.lora.name if args.lora else None,
        "items": len(records),
        "correct": sum(r["said_task"] == r["task"] for r in records) / len(records),
        "work_missed": [r["id"] for r in records if r["task"] and not r["said_task"]],
        "sent_to_agent_wrongly": [
            r["id"] for r in records if not r["task"] and r["said_task"]
        ],
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
