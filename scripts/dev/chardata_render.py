"""The render step (character_data.py render): every checked script as the
app's own requests, each a training row labelled by construction (the gates,
the Agent's instructions, the character's lines), into train.jsonl."""

from __future__ import annotations

import argparse
import json
import random
import re
from typing import Any

import chardata_store as store
from chardata_requests import (
    OWN_KINDS,
    agent_points,
    chat_task_request,
    conversation,
    decision_points,
    line_request,
    reply_model,
)

from silenttalk.conversation import ConversationTurn
from silenttalk.copilot.llm import LocalReplyModel
from silenttalk.copilot.reply_parsing import quiet_for
from silenttalk.copilot.reply_templates import (
    _JOIN_AFTER_QUIET_LINES as JOIN_AFTER_QUIET_LINES,
)
from silenttalk.persona import Persona

# "I am an AI" in any wording a character slips into; refine once let
# "我是一段會說話的字" through.
_AI_CLAIM = re.compile(
    r"(我是|我只是|身為|我不過是)(一個|一段|一串|個)?\s*"
    r"(AI|人工智慧|機器人|語言模型|模型|程式|代碼|程式碼|虛擬|會說話的字|文字|數據)",
    re.I,
)
# A machine character may call itself a machine, never an AI or a program.
_AI_CLAIM_MACHINE = re.compile(
    r"(我是|我只是|身為|我不過是)(一個|一段|一串|個)?\s*"
    r"(AI|人工智慧|語言模型|模型|程式|代碼|程式碼|聊天機器人|會說話的字|數據)",
    re.I,
)
_ASSISTANT = re.compile(
    r"(以下是|```|def |import |步驟一|第一步[，,：:]|好的，我來幫你)"
)
# An answer (talk, or computer work turned down) hands nothing to the Agent,
# so it may not promise work: "我去查" there is a promise nobody keeps
# (laptop round 11).
_PROMISE = re.compile(
    r"((我|等我|讓我)(去|來|再)?(幫你|幫妳)?(查|搜|找找)|(交給|讓|叫|請)思考機|思考機(去|會|來|幫))"
)


def usable(line: str, spec: dict[str, Any], args: argparse.Namespace) -> bool:
    if not line or len(line) > args.max_chars or line.upper().startswith("SKIP"):
        return False
    claim = _AI_CLAIM_MACHINE if spec["honesty"] == "machine" else _AI_CLAIM
    if spec["honesty"] != "admit" and claim.search(line):
        return False
    return not _ASSISTANT.search(line)


def make_render(args: argparse.Namespace) -> None:
    personas = {p["id"]: p for p in store.read_rows(store.OUT_DIR / "personas.jsonl")}
    scripts = store.read_rows(store.OUT_DIR / "scripts.jsonl")
    refined = {
        (r["script"], r["index"], r["kind"]): r["line"]
        for r in store.read_rows(store.OUT_DIR / "refined.jsonl")
    }
    rng = random.Random(4000)
    gate_yes, gate_no, replies, tasks = [], [], [], []
    for number, script in enumerate(scripts):
        raw = personas[script["spec"]["persona_id"]]
        noisy_script = dict(script, stt_variants=raw.get("stt_variants", []))
        persona, turns = conversation(noisy_script, store.persona_of(raw), noisy=True)
        spec = script["spec"]
        model = reply_model(persona, spec)
        # Today's concerns sit in the system prompt, as in the app.
        model.set_agenda(script.get("concerns", []))
        rows = (agent_rows if spec.get("agent") else listener_rows)(
            model, script, number, persona, raw, turns, refined, args
        )
        # The checker of an agent character's lines needs to know its owner.
        extra = {"owner": spec["owner"]} if spec.get("agent") else {}
        # Quiet spells the character ended by opening a topic: the app's lull.
        for index, line in enumerate(script["lines"]):
            if not line.get("quiet") or not usable(line["t"], spec, args):
                continue
            messages = line_request(model, script, turns, index=index, kind="lull")
            rows.append(
                {
                    "script": number,
                    "index": index,
                    "engagement": spec["engagement"],
                    "persona_id": persona.id,
                    "role": raw.get("role", ""),
                    **extra,
                    "kind": "lull",
                    "messages": messages
                    + [{"role": "assistant", "content": line["t"]}],
                }
            )
        for row in rows:
            if row["kind"].startswith("gate"):
                (gate_yes if row["messages"][-1]["content"] == "是" else gate_no).append(row)
            else:
                (tasks if row["kind"] == "task_text" else replies).append(row)
    # A small model copies whatever opener dominates its lines; the teacher
    # sometimes offers nothing but "欸…", so cap it here.
    rng.shuffle(replies)
    opener = [
        r for r in replies if r["messages"][-1]["content"].startswith(("欸", "誒"))
    ]
    others = [r for r in replies if r not in opener]
    replies = others + opener[: int(len(others) * 0.12)]
    # Real chats are mostly lines not meant for the character; keep that
    # lean without letting "否" swamp the gate.
    rng.shuffle(gate_no)
    gate_no = gate_no[: len(gate_yes) * 2]
    rows = gate_yes + gate_no + replies + tasks
    rows = [
        r
        for r in rows
        if sum(len(m["content"]) for m in r["messages"]) <= args.max_prompt_chars
    ]
    rng.shuffle(rows)
    out = store.OUT_DIR / "train.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            row["key"] = store.row_key(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    store.stamp(out)
    lines = [r["messages"][-1]["content"] for r in replies]
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    print(
        f"render: {len(gate_yes)} gate 是, {len(gate_no)} gate 否, {len(replies)} lines, "
        f"{len(tasks)} task instructions -> {len(rows)} rows in {out} {kinds}",
        flush=True,
    )
    if lines:
        print(
            f"  lines starting with 欸: {sum(l.startswith('欸') for l in lines) / len(lines):.0%}, "
            f"mean length {sum(map(len, lines)) / len(lines):.1f}",
            flush=True,
        )


def listener_rows(
    model: LocalReplyModel,
    script: dict[str, Any],
    number: int,
    persona: Persona,
    raw: dict[str, Any],
    turns: list[ConversationTurn],
    refined: dict[tuple[int, int, str], str],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    """An ordinary character's rows, in order: at every line, "is this for
    you" (and, in "active" mode, "would joining in be natural"), and its line
    where it speaks."""
    spec = script["spec"]
    rows: list[dict[str, Any]] = []
    for point in decision_points(script, persona.name):
        index = point["index"]
        model.prompts.recent_lines.clear()
        for turn in turns[: index + 1]:
            if turn.is_self:
                model.prompts.recent_lines.append(turn.text)
        history = turns[: index + 1]
        meta = {
            "script": number,
            "index": index,
            "engagement": spec["engagement"],
            "persona_id": persona.id,
            "role": raw.get("role", ""),
        }
        line_kind = "line"
        if point["speaks"]:
            meta["line_source"] = (
                "refined" if (number, index, line_kind) in refined else "script"
            )
        # The same questions the app asks (LocalReplyModel.character_turn):
        # "is this line for you" on every line, and in "active" mode,
        # after a quiet stretch, "would joining in now be natural".
        if not point["mention"]:
            asked = [("called", point["aimed"])]
            if (
                spec["engagement"] == "active"
                and not point["aimed"]
                and quiet_for(history) >= JOIN_AFTER_QUIET_LINES
            ):
                asked.append(("active", point["speaks"]))
            for question, answer in asked:
                gate = model.gate_messages(
                    turns=history,
                    summary=script["summary_before"],
                    engagement=spec["engagement"],
                    question=question,
                )
                if gate is None:
                    continue
                rows.append(
                    meta
                    | {
                        "kind": f"gate_{question}",
                        "messages": gate
                        + [{"role": "assistant", "content": "是" if answer else "否"}],
                    }
                )
        if point["speaks"]:
            line = _trained_line(script, number, index, line_kind, refined, args)
            if not line:
                continue
            messages = line_request(
                model, script, turns, index=index, kind=line_kind, aimed=point["aimed"]
            )
            rows.append(
                meta
                | {
                    "kind": line_kind,
                    "messages": messages + [{"role": "assistant", "content": line}],
                }
            )
    return rows


def _trained_line(
    script: dict[str, Any], number: int, index: int, kind: str,
    refined: dict[tuple[int, int, str], str], args: argparse.Namespace,
) -> str:
    """The line a row trains on: the refined one, or (not refined, stopped
    early) the teacher's own script line if it passes the same checks as the
    candidates; "" when neither does."""
    spec = script["spec"]
    line = refined.get((number, index, kind))
    if line and not usable(line, spec, args):
        line = None  # filters grew since it was refined
    if not line:
        line = script["lines"][index if kind in OWN_KINDS else index + 1]["t"]
        if not usable(line, spec, args):
            return ""
    if kind == "line" and spec.get("agent") and _PROMISE.search(line):
        return ""
    return line


def agent_rows(
    model: LocalReplyModel,
    script: dict[str, Any],
    number: int,
    persona: Persona,
    raw: dict[str, Any],
    turns: list[ConversationTurn],
    refined: dict[tuple[int, int, str], str],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    """An agent character's rows, in order, each the request the app makes
    there (LocalReplyModel): chat_task's question and its instructions, the
    character's lines (character_turn: an answer, or a task hint), and in the
    owner's thread task_from_owner's change-or-read question."""
    spec = script["spec"]
    base = {"script": number, "engagement": spec["engagement"], "persona_id": persona.id,
            "role": raw.get("role", ""), "owner": spec["owner"]}
    rows: list[dict[str, Any]] = []
    for point in agent_points(script, persona.name):
        index, kind = point["index"], point["kind"]
        meta = {"script": number, "index": index} | base
        history = turns[: index + 1]
        if kind in ("gate_chat_task", "task_text"):
            gate = model.gate_messages(turns=history, summary=script["summary_before"],
                                       engagement=spec["engagement"], question="chat_task")
            if gate is None:
                continue
            if kind == "gate_chat_task":
                messages, answer = gate, "是" if point["answer"] else "否"
            else:
                messages, answer = chat_task_request(gate), point["detail"]
        elif kind == "gate_task_scope":
            # The owner's own typed lines only (owner_messages), as the app asks.
            messages = model.task_scope_messages(turns=history, engagement=spec["engagement"])
            if messages is None:
                continue
            answer = "是" if point["answer"] else "否"
        else:
            answer = _trained_line(script, number, index, kind, refined, args)
            if not answer:
                continue
            meta["line_source"] = "refined" if (number, index, kind) in refined else "script"
            if "detail" in point:
                meta["detail"] = point["detail"]
            messages = line_request(model, script, turns, index=index, kind=kind, aimed=True,
                                    detail=point.get("detail", ""))
        rows.append(meta | {"kind": kind,
                            "messages": messages + [{"role": "assistant", "content": answer}]})
    return rows
