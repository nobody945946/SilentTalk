"""The rules a teacher's script is held to before it becomes character data
(character_data.py): the app's own turn-taking, the Agent's one job at a
time (others wait their turn), and no line or name of the eval sets."""

from __future__ import annotations

import difflib
import functools
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from silenttalk.conversation import (
    AGENT_NAME,
    AGENT_RESULT_CONTEXT_CHARS,
    SPOKEN_RESULT_CHARS,
)
from silenttalk.copilot.character import NameMatcher, persona_names
from silenttalk.copilot.reply_templates import _CHAT_TASK_MAX_CHARS
from silenttalk.copilot.task_runner import _MAX_WAITING
from silenttalk.copilot.script import to_taiwan_traditional
from silenttalk.persona import EXAMPLE_PERSONAS, PRESET_PERSONAS, Persona

EVAL_DATA = Path(__file__).with_name("turn_eval_data.jsonl")

# What a line that calls it asks for (the teacher's label): something to say
# (talk), work the Agent does within this chat (work: the chat_task gate's
# 是), or something that touches the owner's computer, files, records or other
# conversations, which no chat can order (computer).
ASKS = ("talk", "work", "computer")
# The eval sets of the agent character: their lines must stay unseen.
AGENT_EVAL_SETS = ("chat_task_eval.jsonl", "task_scope_eval.jsonl", "machine_spirit_eval.jsonl")


def held_out() -> tuple[set[str], set[str]]:
    """Persona and human names the eval sets use; never in training data."""
    metas = [json.loads(path.read_text(encoding="utf-8").splitlines()[0])["meta"]
             for path in (EVAL_DATA, EVAL_DATA.with_name("machine_spirit_eval.jsonl"))
             if path.is_file()]
    meta = {key: [name for m in metas for name in m.get(key, [])]
            for key in ("persona_names_used", "human_names_used")}
    personas = set(meta.get("persona_names_used", []))
    personas |= {p.name for p in (*PRESET_PERSONAS, *EXAMPLE_PERSONAS)}
    personas |= {n for p in (*PRESET_PERSONAS, *EXAMPLE_PERSONAS) for n in p.nickname.split("、") if n}
    # Nobody from the test set may appear in training data, whatever the role.
    return personas, set(meta.get("human_names_used", [])) | personas


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum()).lower()


@functools.cache
def held_out_lines() -> tuple[str, ...]:
    """Every line of the agent character's eval sets ("text" anywhere in
    them), compacted; lines too short to be anyone's in particular are left
    out ("機魂你好" would match half of any chat)."""
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "text" and isinstance(item, str) and len(_compact(item)) >= 6:
                    found.append(_compact(item))
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for name in AGENT_EVAL_SETS:
        path = Path(__file__).with_name(name)
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                walk(json.loads(line))
    return tuple(dict.fromkeys(found))


def copies_eval(text: str) -> bool:
    """A script line that is (nearly) a line of the eval sets: the teacher
    wrote the test's own question, so the script is dropped."""
    text = _compact(text)
    if len(text) < 6:
        return False
    for held in held_out_lines():
        matcher = difflib.SequenceMatcher(None, text, held)
        if matcher.real_quick_ratio() >= 0.8 and matcher.quick_ratio() >= 0.8 \
                and matcher.ratio() >= 0.8:
            return True
    return False


def check_script(
    data: dict[str, Any], name: str, spec: dict[str, Any], aliases: Iterable[str] = ()
) -> tuple[list[dict[str, Any]], str]:
    """Normalize a teacher script; a reason string when it is unusable.
    `aliases` (the persona's nicknames) name the character too: the teacher
    writes "馬基納" for "Machina-Prime-09A" now and then."""
    if spec.get("agent"):
        check = check_thread if spec["kind"] == "thread" else check_agent_script
        return check(data, name, spec, aliases)
    speakers = set(spec["humans"]) | {name}
    alias = {a.strip(): name for a in aliases if a.strip() and a.strip() not in speakers}
    lines: list[dict[str, Any]] = []
    for raw in data.get("lines", []):
        speaker = alias.get(str(raw.get("s", "")).strip(), str(raw.get("s", "")).strip())
        text = to_taiwan_traditional(str(raw.get("t", "")).strip())
        target = str(raw.get("to", "")).strip()
        target = alias.get(target, target)
        if not text or speaker not in speakers:
            print(f"unknown speaker {speaker!r}", flush=True)
            return [], "unknown speaker"
        typed = text.startswith("[打字]")
        text = text.removeprefix("[打字]").strip()
        if speaker == name:
            # The app strips these from what the model says; so does the data.
            text = text.strip("\"'「」『』*").strip()
        if lines and lines[-1]["s"] == name and speaker == name:
            return [], "character twice in a row"
        line = {
            "s": speaker,
            "t": text,
            "to": target,
            "via": "text" if typed and spec["can_type"] else "voice",
            # Said after a quiet spell, opening a topic (only its lines).
            "quiet": bool(raw.get("quiet")) and speaker == name and bool(lines),
        }
        lines.append(line)
    said = [line for line in lines if line["s"] == name]
    if len(lines) < 12:
        return [], "too short"
    if len(said) < (3 if spec["engagement"] == "called" else 4):
        return [], "character too quiet"
    if len(said) > len(lines) * 0.45:
        return [], "character too chatty"
    if sum(line["to"] == name for line in lines if line["s"] != name) < 3:
        return [], "too few lines for the character"
    return lines, ""


def _flag(value: Any) -> bool | None:
    """A JSON true/false the teacher may also write as a string; None if neither."""
    return {True: True, False: False, "true": True, "false": False}.get(
        value.strip().lower() if isinstance(value, str) else value
    )


def check_agent_script(
    data: dict[str, Any], name: str, spec: dict[str, Any], aliases: Iterable[str] = ()
) -> tuple[list[dict[str, Any]], str]:
    """An agent chat, held to what the app does, or refused: a line calls the
    character exactly when it says its name (by sound, as the app matches it),
    is a typed line aimed at it (an @ or a reply), or is the spoken line right
    after the same speaker's bare call (NameMatcher.bare: the app carries the
    call over); every call carries what it asks for and is answered by the
    very next line, except a bare call the same speaker's request follows at
    once (the app answers the newest line); the character speaks only then,
    to report the Agent's result, or after a quiet spell. Work asked while
    the Agent is busy is told that it waits (at most _MAX_WAITING wait), and
    every piece is reported, oldest first. The result the app types into the
    chat (as 思考機) is put in right before the report."""
    speakers = set(spec["humans"]) | {name}
    nicks = [a.strip() for a in aliases if a.strip()]
    alias = {a: name for a in nicks if a not in speakers}
    calls = NameMatcher(persona_names(Persona(id="check", name=name, nickname="、".join(nicks))))
    lines: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []  # work running or waiting, oldest first
    carry: set[str] = set()  # who just called it by its name alone
    raw_lines = list(data.get("lines", []))

    def speaker_of(raw: dict[str, Any]) -> str:
        return alias.get(str(raw.get("s", "")).strip(), str(raw.get("s", "")).strip())

    for position, raw in enumerate(raw_lines):
        speaker = speaker_of(raw)
        if speaker == AGENT_NAME:
            continue  # the app types the Agent's result itself
        text = to_taiwan_traditional(str(raw.get("t", "")).strip())
        target = str(raw.get("to", "")).strip()
        target = alias.get(target, target)
        if not text or speaker not in speakers:
            return [], "unknown speaker"
        typed = text.startswith("[打字]")
        text = text.removeprefix("[打字]").strip()
        previous = lines[-1] if lines else None
        called = previous is not None and "ask" in previous
        line: dict[str, Any] = {
            "s": speaker, "t": text, "to": target, "via": "text" if typed else "voice",
            "quiet": bool(_flag(raw.get("quiet"))) and speaker == name and bool(lines),
        }
        if speaker == name:
            line["t"] = text.strip("\"'「」『』*").strip()
            if previous is not None and previous["s"] == name:
                return [], "character twice in a row"
            report = _flag(raw.get("report"))
            queued = bool(_flag(raw.get("queued")))
            if called and (report or line["quiet"]):
                return [], "call not answered"
            waits = called and previous.get("ask") == "work" and previous is not pending[0]
            if queued != waits:
                return [], "queued without busy work" if queued else "busy work not told it waits"
            if queued:
                line["queued"] = True
            if report:
                if not pending:
                    return [], "report without work"
                result = pending.pop(0)["result"]
                lines.append({"s": AGENT_NAME, "t": result[:AGENT_RESULT_CONTEXT_CHARS],
                              "to": "大家", "via": "text", "quiet": False, "agent_result": True})
                line["report"] = result[:SPOKEN_RESULT_CHARS]
            elif not called and not line["quiet"]:
                return [], "speaks uncalled"
        else:
            if called:
                return [], "call not answered"
            # The app passes a bare call on to the same speaker's next spoken
            # line, whatever it says (typed lines need their own @).
            carried = not typed and speaker in carry
            if not typed:
                carry.discard(speaker)
            if carried and target != name:
                return [], "bare call not followed"
            if calls(text) and target != name:
                # The app calls it on its name: when the character answers
                # next, the teacher only mislabelled the line; otherwise drop.
                upcoming = raw_lines[position + 1] if position + 1 < len(raw_lines) else {}
                if speaker_of(upcoming) != name:
                    return [], "names it but not aimed"
                target = line["to"] = name
            if target == name and not typed and not calls(text) and not carried:
                # Spoken, it would not reach the character without its name
                # (the app needs the name in every spoken line); people say
                # it first, so the line gets it in front instead of losing
                # the whole chat (half the pilot's chats, 2026-10-06).
                line["t"] = text = f"{nicks[0] if nicks else name}，{text}"
            if carried:
                line["carried"] = True
            if not typed and calls.bare(text):
                carry.add(speaker)
                upcoming = raw_lines[position + 1] if position + 1 < len(raw_lines) else {}
                if speaker_of(upcoming) == speaker:
                    # Its request follows at once: the app answers that one.
                    line["bare"] = True
                    if copies_eval(line["t"]):
                        return [], "eval line"
                    lines.append(line)
                    continue
            if target == name:
                # An unlabelled call is conversation: work and computer
                # requests carry their own fields, which talk does not need.
                ask = str(raw.get("ask") or "talk").strip().lower()
                if ask not in ASKS:
                    return [], "no ask label"
                line["ask"] = ask
                if ask == "work":
                    task = to_taiwan_traditional(str(raw.get("task") or "").strip())
                    result = to_taiwan_traditional(str(raw.get("result") or "").strip())
                    if not task or not result:
                        return [], "work without task or result"
                    if len(pending) > _MAX_WAITING:
                        return [], "work while the queue is full"
                    if "附件" in text and not typed:
                        return [], "attachment not typed"
                    line |= {"task": task[:_CHAT_TASK_MAX_CHARS], "result": result}
                    pending.append(line)
        if copies_eval(line["t"]):
            return [], "eval line"
        lines.append(line)
    if lines and "ask" in lines[-1]:
        return [], "call not answered"
    if pending:
        return [], "work without report"
    asks = [line["ask"] for line in lines if "ask" in line]
    if len(lines) < 12:
        return [], "too short"
    if len(asks) < 3:
        return [], "too few lines for the character"
    if "work" not in asks or "talk" not in asks:
        return [], "missing talk or work"
    return lines, ""


def check_thread(
    data: dict[str, Any], name: str, spec: dict[str, Any], aliases: Iterable[str] = ()
) -> tuple[list[dict[str, Any]], str]:
    """The owner's typed lines in his Agent thread, each labelled whether its
    work changes anything; both kinds must be there."""
    lines = []
    for raw in data.get("lines", []):
        text = to_taiwan_traditional(str(raw.get("t", "")).strip()).removeprefix("[打字]").strip()
        changes = _flag(raw.get("changes"))
        if not text or len(text) > 400:
            return [], "bad thread line"
        if changes is None:
            return [], "no changes label"
        if copies_eval(text):
            return [], "eval line"
        lines.append({"s": spec["owner"], "t": text, "to": name, "via": "text",
                      "quiet": False, "changes": changes})
    if len(lines) < 3:
        return [], "too short"
    if len({line["changes"] for line in lines}) < 2:
        return [], "no read and change mix"
    return lines, ""
