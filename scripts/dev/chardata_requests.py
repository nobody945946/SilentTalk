"""What the app asks at each point of a checked script (character_data.py):
the points themselves, the chat as the app holds it (with speech-recognition
noise on the others' spoken lines), and the requests LocalReplyModel makes
there, so render trains on exactly what the app sends."""

from __future__ import annotations

import json
import random
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from silenttalk.conversation import AGENT_NAME, AGENT_SPEAKER_ID, ConversationTurn
from silenttalk.copilot.llm import LocalReplyModel
from silenttalk.copilot.reply_templates import (
    _CHAT_TASK_ASK,
    _GATE_QUESTION,
    TASK_HINTS,
)
from silenttalk.persona import Persona, Relationship

# Speech-recognition confusions seen in this app's STT tests, plus common
# homophones; applied rarely, to the others' spoken lines only.
CONFUSIONS = (
    ("在", "再"),
    ("再", "在"),
    ("的", "得"),
    ("那", "哪"),
    ("做", "作"),
    ("已經", "以經"),
    ("打野", "達也"),
    ("補師", "不是"),
    ("好", "號"),
    ("吧", "八"),
    ("欸", "誒"),
    ("什麼", "甚麼"),
    ("是不是", "4不4"),
    ("幹嘛", "幹麻"),
    ("沒有", "沒又"),
)
PUNCTUATION = re.compile(r"[，。！？、,.!?~～…「」]")

# The character's lines a row is trained on: the answer to a line, the
# acceptance of work (TASK_HINTS "ack"), the report of the Agent's result
# (TASK_HINTS "report"), the opening after a quiet spell.
LINE_KINDS = ("line", "lull", "ack", "report")
# Kinds that are the character's own line at their index (the others answer
# the line at their index, said by the next one).
OWN_KINDS = ("lull", "report")


# ---------------------------------------------------------------- labels


def decision_points(script: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Every line from someone else, with whether the character speaks next.

    A point whose label contradicts the line's own addressee is dropped as
    ambiguous: in "called" mode the character answers exactly the lines
    aimed at it; in "active" mode it must answer those and may add others.
    """
    lines, engagement = script["lines"], script["spec"]["engagement"]
    points = []
    for index, line in enumerate(lines):
        if line["s"] == name:
            continue
        # A line followed by a quiet spell got no answer: the character's
        # next line opens a topic of its own instead.
        speaks = (
            index + 1 < len(lines)
            and lines[index + 1]["s"] == name
            and not lines[index + 1].get("quiet")
        )
        aimed = line["to"] == name
        if aimed != speaks and (engagement == "called" or aimed):
            continue
        points.append(
            {
                "index": index,
                "speaks": speaks,
                "aimed": aimed,
                "mention": aimed and line["via"] == "text",
            }
        )
    return points


def agent_points(script: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """What the app asks at each line of an agent script (check_agent_script
    and check_thread made them consistent), in order. A line that calls the
    character: the chat-work question, then for work the Agent's instructions
    and the character's acceptance, otherwise its answer. A line of the
    character's carrying the Agent's result: its report. A line the owner
    typed in his thread: whether the work changes anything."""
    points: list[dict[str, Any]] = []
    for index, line in enumerate(script["lines"]):
        ask = line.get("ask")
        if ask:
            points.append({"index": index, "kind": "gate_chat_task", "answer": ask == "work"})
            if ask == "work":
                points += [{"index": index, "kind": "task_text", "detail": line["task"]},
                           {"index": index, "kind": "ack", "detail": line["task"]}]
            else:
                points.append({"index": index, "kind": "line"})
        elif line.get("report"):
            points.append({"index": index, "kind": "report", "detail": line["report"]})
        elif "changes" in line:
            points.append({"index": index, "kind": "gate_task_scope", "answer": line["changes"]})
    return points


# ---------------------------------------------------------------- the chat


def conversation(
    script: dict[str, Any], persona: Persona, noisy: bool
) -> tuple[Persona, list[ConversationTurn]]:
    """The persona as the app would hold it (with relationships), and the chat
    as turns; `noisy` applies speech-recognition noise to spoken lines."""
    spec = script["spec"]
    persona = replace(
        persona, relationships=tuple(Relationship(w, r) for w, r in spec["relations"])
    )
    rng = random.Random(hash_seed(script))
    ids = {h: n + 1 for n, h in enumerate(spec["humans"])}
    turns = []
    for line in script["lines"]:
        if line["s"] == persona.name:
            turns.append(
                ConversationTurn(
                    0, persona.name, line["t"], is_self=True, via=line["via"]
                )
            )
            continue
        if line.get("agent_result"):
            # The Agent's result, typed into the chat by the app (runtime.py).
            turns.append(ConversationTurn(AGENT_SPEAKER_ID, AGENT_NAME, line["t"], via="text"))
            continue
        text = line["t"]
        if noisy and line["via"] == "voice":
            text = stt_noise(text, persona, script, rng)
        turns.append(ConversationTurn(ids[line["s"]], line["s"], text, via=line["via"]))
    return persona, turns


def hash_seed(script: dict[str, Any]) -> int:
    return sum(ord(c) for c in json.dumps(script["lines"][:3], ensure_ascii=False))


def stt_noise(
    text: str, persona: Persona, script: dict[str, Any], rng: random.Random
) -> str:
    if rng.random() < 0.85:
        text = PUNCTUATION.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
    variants = script.get("stt_variants") or []
    if variants and rng.random() < 0.25:
        for name in [persona.name, *persona.nickname.split("、")]:
            if len(name) >= 2 and name in text:
                text = text.replace(name, rng.choice(variants), 1)
                break
    if rng.random() < 0.12:
        right, wrong = rng.choice(CONFUSIONS)
        text = text.replace(right, wrong, 1)
    return text


# ---------------------------------------------------------------- the request


def reply_model(persona: Persona, spec: dict[str, Any]) -> LocalReplyModel:
    model = LocalReplyModel(
        Path("unused.gguf"),
        can_type=spec["can_type"],
        ai_honesty=spec["honesty"],
        agent_dispatch=bool(spec.get("agent")),
        # conversation() numbers the humans from 1 in spec order.
        owner_id=spec["humans"].index(spec["owner"]) + 1 if spec.get("agent") else None,
        owner_name=spec["owner"] if spec.get("agent") else "",
    )
    model.set_persona(persona)
    return model


def line_request(
    model: LocalReplyModel,
    script: dict[str, Any],
    turns: list[ConversationTurn],
    *,
    index: int,
    kind: str,
    aimed: bool = False,
    detail: str = "",
) -> list[dict[str, str]]:
    """What the app sends for the character's line at this point: the one
    source for refine (choosing the line) and render (training on it), so the
    two never see different prompts. "line" answers the line at `index`;
    "ack" accepts the work it asked for (`detail`: the Agent's instructions);
    "lull" is the character's own line at `index`, opening a topic after a
    quiet spell; "report" is its own line at `index`, after the Agent's
    result was typed into the chat (`detail`: what it is told of it)."""
    own = kind in OWN_KINDS
    history = turns[:index] if own else turns[: index + 1]
    # Today's concerns sit in the system prompt, as in the app.
    model.set_agenda(script.get("concerns", []))
    model.prompts.recent_lines.clear()
    for turn in history:
        if turn.is_self:
            model.prompts.recent_lines.append(turn.text)
    common = {
        "turns": history,
        "summary": script["summary_before"],
        "engagement": script["spec"]["engagement"],
    }
    if kind == "lull":
        return model.character_messages(**common, lull=True)
    if kind in TASK_HINTS:
        return model.character_messages(**common, task_hint=(kind, detail))
    return model.character_messages(**common, addressed=aimed, joining=not aimed)


def chat_task_request(gate: list[dict[str, str]]) -> list[dict[str, str]]:
    """The app's request for the Agent's instructions (LocalReplyModel.chat_task):
    the chat-work question's request with the question swapped for the ask."""
    return gate[:-1] + [{
        "role": "user",
        "content": gate[-1]["content"].removesuffix(_GATE_QUESTION["chat_task"]) + _CHAT_TASK_ASK,
    }]


def row_hint(row: dict[str, Any]) -> str:
    """The task hint the app put on this row's request (TASK_HINTS), or ""."""
    if row["kind"] in TASK_HINTS and "detail" in row:
        return TASK_HINTS[row["kind"]].format(detail=row["detail"])
    return ""
