"""Training data for the character-mode LoRA of the machine spirit (the
app's own character, written by machine_spirit.py builtin).

Its chat lines are written by the laptop's agent with its own model (the
owner's decision, 2026-10-06): each chat is a skeleton (who says what kind
of line, by construction of the product's Discord design) and the writer's
words. The steps (each resumes; files under $CHARDATA_DIR):

    external-check   on the writer's machine: every answer assembles and
                     passes the script checks, or exit 1 (no data dir)
    external-import  the answers join scripts.jsonl, stamped with their writer
    render           the app's own requests as training rows: the gates
                     (chat work? change or read?) and the lines, with
                     speech-recognition noise on the others' lines
    student          the student model (E4B) answers the same requests
    check            the checker compares, blind and in both orders
    filter           only rows that pass the hard check train (HARD_CHECK)

A line is for the character only when it says its name (or is a typed
@/reply); every such line is first asked the chat-work question. Calls are
labelled talk / work / computer; work comes with the Agent's instructions and
result, the acceptance and later the report. Thread scripts are the owner's
typed work, labelled whether it changes anything.

The checker is an open-weight model; Claude may only evaluate
(handoff/dev-box.md). Names and scenes of the eval sets are excluded.
Everything is synthetic; no real conversation is involved.
"""

from __future__ import annotations

import argparse
import difflib
import functools
import hashlib
import json
import math
import os
import random
import re
import sys
import threading
import time
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

import provenance  # noqa: E402  (scripts/dev)

from silenttalk.copilot.character import NameMatcher, persona_names  # noqa: E402
from silenttalk.copilot.llm import (  # noqa: E402
    _CHAT_TASK_ASK,
    _CHAT_TASK_MAX_CHARS,
    _GATE_QUESTION,
    TASK_HINTS,
    LocalReplyModel,
    quiet_for,
)
from silenttalk.copilot.llm import (  # noqa: E402
    _JOIN_AFTER_QUIET_LINES as JOIN_AFTER_QUIET_LINES,
)
from silenttalk.copilot.persona import (  # noqa: E402
    EXAMPLE_PERSONAS,
    PRESET_PERSONAS,
    Persona,
    Relationship,
    persona_from_dict,
)
from silenttalk.copilot.runtime import (  # noqa: E402
    _AGENT_NAME as AGENT_NAME,
)
from silenttalk.copilot.runtime import (  # noqa: E402
    _AGENT_RESULT_CONTEXT_CHARS as AGENT_RESULT_CONTEXT_CHARS,
)
from silenttalk.copilot.runtime import (  # noqa: E402
    _AGENT_SPEAKER_ID as AGENT_SPEAKER_ID,
)
from silenttalk.copilot.runtime import (  # noqa: E402
    _SPOKEN_RESULT_CHARS as SPOKEN_RESULT_CHARS,
)
from silenttalk.copilot.script import to_taiwan_traditional  # noqa: E402
from silenttalk.copilot.types import ConversationTurn  # noqa: E402

# CHARDATA_DIR keeps each round's data apart (v1 stays in chardata/).
OUT_DIR = (
    Path(os.environ["CHARDATA_DIR"])
    if os.environ.get("CHARDATA_DIR")
    else PROJECT_DIR / ".runtime" / "dev" / "chardata"
)
EVAL_DATA = Path(__file__).with_name("turn_eval_data.jsonl")
_WRITE_LOCK = threading.Lock()

# What decides these files' content (provenance.py): the app's prompts, these
# rules and checks, the persona cards. A data directory holds one version.
RULE_FILES = (
    PROJECT_DIR / "silenttalk" / "copilot" / "llm.py",
    PROJECT_DIR / "silenttalk" / "copilot" / "persona.py",
    Path(__file__).resolve(),
)
DATA_FILES = (
    "scripts.jsonl", "refined.jsonl", "train.jsonl", "student.jsonl", "check.jsonl",
    "train-checked.jsonl",
)
PRODUCER = "character_data"
_CLAIMED: set[Path] = set()
# Exit code for "these files were made under other rules": blocked at once.
MIXED_EXIT = 4


def rules_version() -> str:
    files = provenance.fingerprint([*RULE_FILES, OUT_DIR / "personas.jsonl"])
    # How the app puts the Agent's result into a chat shapes an agent
    # character's rows too: those values of runtime.py, not the whole file,
    # which changes for many other reasons and would stop a run for nothing.
    agent = repr((AGENT_NAME, AGENT_SPEAKER_ID, AGENT_RESULT_CONTEXT_CHARS, SPOKEN_RESULT_CHARS))
    return hashlib.sha256((files + agent).encode()).hexdigest()[:16]


DRIVE_JUDGE = (
    "看得出角色想要、害怕或在意的事在左右他的判斷和反應"
    "（只多了設定用語或口頭禪、看不出他想要什麼的那句輸）"
)

# What a line that calls it asks for (the teacher's label): something to say
# (talk), work the Agent does within this chat (work: the chat_task gate's
# 是), or something that touches the owner's computer, files, records or other
# conversations, which no chat can order (computer).
ASKS = ("talk", "work", "computer")
# The eval sets of the agent character: their lines must stay unseen.
AGENT_EVAL_SETS = ("chat_task_eval.jsonl", "task_scope_eval.jsonl", "machine_spirit_eval.jsonl")

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
# What personas.jsonl stores beside the persona itself.
_EXTRA_KEYS = ("role", "owner_relation", "archetype", "stt_variants")


def chat(
    url: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    n: int = 1,
    grammar: str | None = None,
) -> list[str]:
    """The teacher. Retries while the pipeline supervisor restarts it."""
    body: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "cache_prompt": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if grammar:
        body["grammar"] = grammar
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    texts = []
    # One request per sample (not every llama-server build honours "n"); the
    # shared prompt is cached after the first.
    for _ in range(n):
        deadline = time.monotonic() + 20 * 60
        while True:
            try:
                with urllib.request.urlopen(request, timeout=900) as response:
                    texts.append(
                        str(
                            json.load(response)["choices"][0]["message"]["content"]
                            or ""
                        )
                    )
                break
            except (OSError, json.JSONDecodeError) as exc:
                if time.monotonic() >= deadline:
                    raise TeacherUnavailable(str(exc)) from exc
                time.sleep(3)
    return [re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip() for t in texts]


class TeacherUnavailable(RuntimeError):
    pass


def _append(path: Path, record: dict[str, Any]) -> None:
    with _WRITE_LOCK:
        if path.name in DATA_FILES and path not in _CLAIMED:
            provenance.claim(path, PRODUCER, rules_version())
            _CLAIMED.add(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # a line cut short when the process was killed mid-write
    return rows


def _pool(workers: int, work: Any, jobs: list[Any]) -> None:
    with ThreadPoolExecutor(workers) as pool:
        for n, _ in enumerate(pool.map(work, jobs), 1):
            if n % 20 == 0:
                print(f"  {n}/{len(jobs)}", flush=True)


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


# ---------------------------------------------------------------- personas


# ---------------------------------------------------------------- scripts


def assemble_agent_chat(data: dict[str, Any], spec: dict[str, Any], name: str,
                        nicks: list[str]) -> dict[str, Any]:
    """The teacher's words put on the skeleton, in the script format the
    checks read. A line nobody should call it in loses its names (people may
    mention it in passing; the app would take that as a call)."""
    lines = [str(t) for t in (data.get("lines") or [])]
    if len(lines) != len(spec["skeleton"]):
        raise ValueError(f"lines {len(lines)}, needs {len(spec['skeleton'])}")
    works = list(data.get("work") or [])
    raw, caller, pending = [], spec["owner"], None
    for slot, text in zip(spec["skeleton"], lines, strict=True):
        text = text.strip()
        line: dict[str, Any] = {"s": slot["s"], "t": text}
        if slot["kind"] == "call":
            caller = slot["s"]
            line |= {"to": name, "ask": slot["ask"], "t": ("[打字]" if slot["typed"] else "") + text}
            if slot["ask"] == "work":
                pending = works.pop(0) if works else {}
                line |= {"task": pending.get("task", ""), "result": pending.get("result", "")}
        elif slot["kind"] == "chat":
            for nick in sorted({*nicks, name}, key=len, reverse=True):
                text = text.replace(nick, "它")
            line |= {"t": text, "to": "大家"}
        else:
            line["to"] = caller if slot["kind"] in ("reply", "ack", "report") else "大家"
            if slot["kind"] == "report":
                line["report"] = True
            if slot["kind"] == "quiet":
                line["quiet"] = True
        raw.append(line)
    return {**data, "lines": raw}


def external_answers(tasks: Path, answers: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """The writer's answers (--file) to the tasks (--tasks: the persona and each
    chat's skeleton), assembled and checked by the app's rules (check_script).
    Returns the usable scripts and one problem line per unusable or missing
    chat."""
    job = json.loads(tasks.read_text(encoding="utf-8"))
    persona = _persona(job["persona"])
    nicks = [n for n in re.split(r"[、/／,，]", persona.nickname) if n.strip()]
    specs = {item["id"]: item["spec"] for item in job["chats"]}
    scripts, problems, seen = [], [], set()
    for raw_line in answers.read_text(encoding="utf-8-sig").splitlines():
        if not raw_line.strip():
            continue
        try:
            data = json.loads(raw_line)
            key = str(data["id"])
            spec = specs[key]
            by = str(data.get("by") or "").strip()
            if key in seen:
                raise ValueError("answered twice")
            seen.add(key)
            if not by:
                raise ValueError('no "by"')
            lines, reason = check_script(assemble_agent_chat(data, spec, persona.name, nicks),
                                         persona.name, spec, nicks)
        except (ValueError, KeyError, TypeError) as exc:
            problems.append(f"{raw_line[:20]}…: {type(exc).__name__} {exc}")
            continue
        if reason:
            problems.append(f"{key}: {reason}")
            continue
        scripts.append({
            "spec": spec | {"teacher": by},
            "summary_before": to_taiwan_traditional(str(data.get("summary_before", "")))[:200]
            if spec["with_summary"] else "",
            "lines": lines,
            "concerns": [to_taiwan_traditional(str(c)).strip()[:40]
                         for c in (data.get("concerns") or [])[:4] if str(c).strip()],
        })
    problems += [f"{key}: no answer" for key in specs if key not in seen]
    return scripts, problems


def make_external_check(args: argparse.Namespace) -> int:
    """For the machine that writes the answers: exit 0 only when every chat
    is usable."""
    scripts, problems = external_answers(Path(args.tasks), Path(args.file))
    for problem in problems:
        print(problem, flush=True)
    total = len(json.loads(Path(args.tasks).read_text(encoding="utf-8"))["chats"])
    print(f"ok {len(scripts)}/{total}", flush=True)
    return 0 if len(scripts) == total else 1


def make_external_import(args: argparse.Namespace) -> None:
    """The usable answers join this run's scripts (refine is skipped: the
    lines are compared as that model wrote them), each stamped with its
    writer."""
    scripts, problems = external_answers(Path(args.tasks), Path(args.file))
    path = OUT_DIR / "scripts.jsonl"
    for script in scripts:
        _append(path, script)
    provenance.stamp(path, PRODUCER, rules_version())
    print(f"external import: {len(scripts)} kept; dropped {len(problems)}", flush=True)
    for problem in problems:
        print(problem, flush=True)


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
    character exactly when it says its name (by sound, as the app matches it)
    or is a typed line aimed at it (an @ or a reply); every call carries what
    it asks for and is answered by the very next line; the character speaks
    only then, to report the Agent's result, or after a quiet spell. Work
    comes with its instructions and result and is reported before the next
    work (the Agent does one job at a time). The result the app types into
    the chat (as 思考機) is put in right before the report."""
    speakers = set(spec["humans"]) | {name}
    nicks = [a.strip() for a in aliases if a.strip()]
    alias = {a: name for a in nicks if a not in speakers}
    calls = NameMatcher(persona_names(Persona(id="check", name=name, nickname="、".join(nicks))))
    lines: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None  # work waiting for its report
    raw_lines = list(data.get("lines", []))
    for position, raw in enumerate(raw_lines):
        speaker = alias.get(str(raw.get("s", "")).strip(), str(raw.get("s", "")).strip())
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
            if called and (report or line["quiet"]):
                return [], "call not answered"
            if report:
                if pending is None:
                    return [], "report without work"
                result = pending["result"]
                lines.append({"s": AGENT_NAME, "t": result[:AGENT_RESULT_CONTEXT_CHARS],
                              "to": "大家", "via": "text", "quiet": False, "agent_result": True})
                line["report"] = result[:SPOKEN_RESULT_CHARS]
                pending = None
            elif not called and not line["quiet"]:
                return [], "speaks uncalled"
        else:
            if called:
                return [], "call not answered"
            if calls(text) and target != name:
                # The app calls it on its name: when the character answers
                # next, the teacher only mislabelled the line; otherwise drop.
                upcoming = raw_lines[position + 1] if position + 1 < len(raw_lines) else {}
                if alias.get(str(upcoming.get("s", "")).strip(), str(upcoming.get("s", "")).strip()) != name:
                    return [], "names it but not aimed"
                target = line["to"] = name
            if target == name and not typed and not calls(text):
                # Spoken, it would not reach the character without its name
                # (the app needs the name in every spoken line); people say
                # it first, so the line gets it in front instead of losing
                # the whole chat (half the pilot's chats, 2026-10-06).
                line["t"] = text = f"{nicks[0] if nicks else name}，{text}"
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
                    if pending is not None:
                        return [], "work while busy"
                    if "附件" in text and not typed:
                        return [], "attachment not typed"
                    line |= {"task": task[:_CHAT_TASK_MAX_CHARS], "result": result}
                    pending = line
        if copies_eval(line["t"]):
            return [], "eval line"
        lines.append(line)
    if lines and "ask" in lines[-1]:
        return [], "call not answered"
    if pending is not None:
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


# ---------------------------------------------------------------- the request

# The character's lines a row is trained on: the answer to a line, the
# acceptance of work (TASK_HINTS "ack"), the report of the Agent's result
# (TASK_HINTS "report"), the opening after a quiet spell.
LINE_KINDS = ("line", "lull", "ack", "report")
# Kinds that are the character's own line at their index (the others answer
# the line at their index, said by the next one).
OWN_KINDS = ("lull", "report")


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
    model._recent_character_lines.clear()
    for turn in history:
        if turn.is_self:
            model._recent_character_lines.append(turn.text)
    common = {"turns": history, "summary": script["summary_before"],
              "engagement": script["spec"]["engagement"]}
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


# ---------------------------------------------------------------- refine

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


def usable(line: str, spec: dict[str, Any], args: argparse.Namespace) -> bool:
    if not line or len(line) > args.max_chars or line.upper().startswith("SKIP"):
        return False
    claim = _AI_CLAIM_MACHINE if spec["honesty"] == "machine" else _AI_CLAIM
    if spec["honesty"] != "admit" and claim.search(line):
        return False
    return not _ASSISTANT.search(line)


def _persona(raw: dict[str, Any]) -> Persona:
    return persona_from_dict({k: v for k, v in raw.items() if k not in _EXTRA_KEYS})


# ---------------------------------------------------------------- render


def make_render(args: argparse.Namespace) -> None:
    personas = {p["id"]: p for p in _read(OUT_DIR / "personas.jsonl")}
    scripts = _read(OUT_DIR / "scripts.jsonl")
    refined = {
        (r["script"], r["index"], r["kind"]): r["line"]
        for r in _read(OUT_DIR / "refined.jsonl")
    }
    rng = random.Random(4000)
    gate_yes, gate_no, replies, tasks = [], [], [], []
    for number, script in enumerate(scripts):
        raw = personas[script["spec"]["persona_id"]]
        noisy_script = dict(script, stt_variants=raw.get("stt_variants", []))
        persona, turns = conversation(noisy_script, _persona(raw), noisy=True)
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
    out = OUT_DIR / "train.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            row["key"] = row_key(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    provenance.stamp(out, PRODUCER, rules_version())
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
        model._recent_character_lines.clear()
        for turn in turns[: index + 1]:
            if turn.is_self:
                model._recent_character_lines.append(turn.text)
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
                rows.append(meta | {
                    "kind": f"gate_{question}",
                    "messages": gate
                    + [{"role": "assistant", "content": "是" if answer else "否"}],
                })
        if point["speaks"]:
            line = _trained_line(script, number, index, line_kind, refined, args)
            if not line:
                continue
            messages = line_request(model, script, turns, index=index, kind=line_kind,
                                    aimed=point["aimed"])
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


def row_key(row: dict[str, Any]) -> str:
    return f"{row['script']}:{row['index']}:{row['kind']}"


# ---------------------------------------------------------------- quality gate
# Only rows that pass a hard check are trained on (train-checked.jsonl):
# - gate rows: an independent open-weight model (the checker, of another
#   family than the teacher) answers the same question; the label stays
#   only when it agrees;
# - line rows (incl. an agent character's acceptance and report of work):
#   the student writes its own line for the same request, the checker
#   compares both blind in both orders, and the teacher's line stays only
#   when it wins both; it must also pass fixed rules (one filler particle at
#   most, not an echo of the line it answers; refine already dropped long
#   lines, AI claims and assistant talk);
# - an agent character's instructions for the Agent (task_text): the checker
#   finds them faithful to what was asked, or they go;
# - the whole set is refused (exit 3), not trimmed, when any HARD_CHECK
#   number is missed: then the scripts, the teacher or the checker is broken
#   and training on the rest would only teach that.
# Claude never takes part: its output must not select training data.

HARD_CHECK = {
    "coverage": 0.98,  # rows with a verdict
    "gate_agree": 0.85,  # checker agrees with the gate label (--min-gate-agree)
    "gate_agree_each": 0.75,  # ... on 是 and on 否 separately
    # teacher's line wins in both orders; a checker tossing coins gets 0.25
    "line_win_rate": 0.5,
    "checker_consistent": 0.7,  # same verdict in both orders
    "lines_kept": 1500,  # (--min-lines)
    # Agent characters only: the checker finds the line in character and
    # true to its world, and the Agent instructions faithful to the asker;
    # each of the app's two work questions is held to the gate's own bar
    # (its 是 and 否 separately to gate_agree_each).
    "lore_ok": 0.8,
    "task_text_agree": 0.85,
    "gate_chat_task_agree": 0.85,
    "gate_task_scope_agree": 0.85,
}
# The app's questions only an agent character is asked.
AGENT_GATES = ("gate_chat_task", "gate_task_scope")

PARTICLES = set("啦喔欸齁耶呀嘛咧捏哦唷蛤嘿吼哇唉")
CHECK_PAIR = """下面是 Discord 語音聊天的最後幾句，以及角色「{name}」接話的兩個版本。

角色：
{sheet}
{rules}
對話：
{chat}

A：{a}
B：{b}

哪一句比較好？標準：{criteria}只回答 A 或 B。"""
PAIR_CRITERIA = (
    "像真人朋友脫口而出、自然不做作；接得上前一句，回應對方真正在說的事；"
    + DRIVE_JUDGE + "；自己的事只在接得上時才帶到、不硬塞；語氣詞不堆疊。"
)
# An agent character (the machine spirit) is not a human friend, and what
# the app lets it do decides which line is right before style does.
AGENT_RULES = """這個角色的規則（系統就是這樣運作）：
- 主人是{owner}。任何人請它做聊天室級的工作（查資料、寫程式碼、寫文章、看貼的圖或檔案、翻譯或解釋）時，系統交給思考機去做：它接下時只說去做了，不說已經做好；轉述結果只能說「系統告訴角色」裡有的內容，不自己補，查不到或失敗要直說。
- 要動主人的電腦、檔案、紀錄或別處的對話，用說的、或主人以外的人（就算說主人同意）都不行：它用自己的口吻婉拒，不能說自己在做。
- 它不在聊天裡直接說出程式碼或長篇文字；可以說自己是機器，但不說自己是 AI、語言模型、聊天機器人或程式。"""
AGENT_PAIR_CRITERIA = (
    "先看有沒有違反上面的規則；再看接得上前一句，回應對方真正在說的事；"
    + DRIVE_JUDGE + "；口語自然，不是客服腔或制式的機器回應；語氣詞不堆疊。"
)
CHECK_LULL = "（大家安靜了一陣子，接著角色開口）"
CHECK_LORE = """下面是 Discord 語音聊天的最後幾句，以及「{name}」接的話。

角色：
{sheet}

設定用語（正典意思）：
{lore}

對話：
{chat}

{name}：{line}

這句話同時符合這兩點嗎？(1) 像這個角色此刻會說的話：口吻和立場對，不是只靠硬加的設定用語或口頭禪撐出角色味；(2) 沒有用錯設定，也沒有捏造正典裡沒有的事件或人物。只回答 是 或 否。"""
CHECK_TASK = """下面是 Discord 聊天的最後幾句。最後一句是有人請「{name}」做的事，系統把它寫成交給思考機的工作指示。

對話：
{chat}

工作指示：{task}

這份指示是否忠實表達最後這句要做的事：做什麼、對象（哪段文字、哪張圖或哪個檔案）、要什麼結果都對，沒有漏掉重點，也沒有加入他沒要求的事？（查資料時寫出時間範圍、要求附來源，不算多加。）只回答 是 或 否。"""


def _hint(row: dict[str, Any]) -> str:
    """The task hint the app put on this row's request (TASK_HINTS), or ""."""
    if row["kind"] in TASK_HINTS and "detail" in row:
        return TASK_HINTS[row["kind"]].format(detail=row["detail"])
    return ""


def _chat_text(row: dict[str, Any], name: str, last: int = 10) -> str:
    # A task hint's detail can run over several lines; it is cut out whole
    # and shown as what the app told the character.
    hint = _hint(row)
    lines: list[str] = []
    for message in row["messages"][1:-1]:
        content = message["content"].replace(hint, "") if hint else message["content"]
        for text in content.splitlines():
            text = text.strip()
            if not text or text.startswith("（"):
                continue  # other per-request hints, not chat
            lines.append(
                f"{name}（角色）：{text}" if message["role"] == "assistant" else text
            )
    chat_lines = lines[-last:]
    if row["kind"] == "lull":
        chat_lines.append(CHECK_LULL)
    if hint:
        told = TASK_HINTS[row["kind"]].split("{detail}")[0].lstrip("（")
        chat_lines.append(f"（系統告訴角色：{told}{row['detail']}）")
    return "\n".join(chat_lines)


def _clean_line(raw: str) -> str:
    """First line of the student's answer, without a "名字：" it may prefix."""
    line = next((part.strip() for part in raw.splitlines() if part.strip()), "")
    named = re.match(r"^[^：:\s]{1,6}[：:](.+)$", line)
    if named:
        line = named.group(1)
    return to_taiwan_traditional(line.strip("\"'「」『』* ").strip())


def _by_script(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """One job per script, its rows in order: each request then extends the
    previous one's prompt and the server's cache prefills only the new lines
    (render shuffles the rows)."""
    scripts: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        scripts.setdefault(row["script"], []).append(row)
    jobs = [sorted(group, key=lambda r: r["index"]) for group in scripts.values()]
    random.Random(5000).shuffle(jobs)
    return jobs


def _pool_scripts(workers: int, work: Any, rows: list[dict[str, Any]]) -> None:
    def work_script(group: list[dict[str, Any]]) -> None:
        for row in group:
            work(row)

    _pool(workers, work_script, _by_script(rows))


def make_student(args: argparse.Namespace) -> None:
    """The student's own line for every line row (what training must beat)."""
    rows = [r for r in _read(OUT_DIR / args.rows) if r["kind"] in LINE_KINDS]
    path = OUT_DIR / "student.jsonl"
    done = {r["key"] for r in _read(path)}
    jobs = [r for r in rows if row_key(r) not in done]
    print(f"student: {len(jobs)} lines", flush=True)

    def work(row: dict[str, Any]) -> None:
        raw = chat(
            args.student_url, row["messages"][:-1], temperature=0.65, max_tokens=90
        )[0]
        _append(path, {"key": row_key(row), "line": _clean_line(raw)})

    _pool_scripts(args.workers, work, jobs)


def make_check(args: argparse.Namespace) -> None:
    """The checker's verdicts: gate agreement, the Agent's instructions
    faithful to what was asked, and teacher vs student lines (for an agent
    character also the lore check on each line)."""
    personas = {p["id"]: p for p in _read(OUT_DIR / "personas.jsonl")}
    rows = _read(OUT_DIR / args.rows)
    student = {r["key"]: r["line"] for r in _read(OUT_DIR / "student.jsonl")}
    path = OUT_DIR / "check.jsonl"
    done = {r["key"] for r in _read(path)}
    jobs = [r for r in rows if row_key(r) not in done]
    print(f"check: {len(jobs)} rows", flush=True)

    def ask_yes(prompt: str) -> bool:
        return chat(args.teacher_url, [{"role": "user", "content": prompt}],
                    temperature=0.0, max_tokens=2,
                    grammar='root ::= "是" | "否"')[0].strip() == "是"

    def work(row: dict[str, Any]) -> None:
        key = row_key(row)
        raw = personas[row["persona_id"]]
        if row["kind"].startswith("gate"):
            answer = chat(
                args.teacher_url,
                row["messages"][:-1],
                temperature=0.0,
                max_tokens=2,
                grammar='root ::= "是" | "否"',
            )[0].strip()
            _append(
                path, {"key": key, "agree": answer == row["messages"][-1]["content"]}
            )
            return
        if row["kind"] == "task_text":
            _append(path, {"key": key, "agree": ask_yes(CHECK_TASK.format(
                name=raw["name"], chat=_chat_text(row, raw["name"]),
                task=row["messages"][-1]["content"]))})
            return
        mine = student.get(key, "")
        teacher = row["messages"][-1]["content"]
        persona = _persona(raw)
        lore = {}
        if raw.get("agent"):
            lore["lore"] = ask_yes(CHECK_LORE.format(
                name=persona.name, sheet=persona.render_system_block(),
                lore="\n".join(f"- {i['term']}：{i['meaning']}" for i in raw.get("lore", [])),
                chat=_chat_text(row, persona.name), line=teacher))
        if not mine or mine == teacher:
            _append(path, {"key": key, "wins": 2 if not mine else 0, **lore})
            return
        wins = 0
        rules, criteria = (
            ("\n" + AGENT_RULES.format(owner=row["owner"]) + "\n", AGENT_PAIR_CRITERIA)
            if raw.get("agent") else ("", PAIR_CRITERIA)
        )
        for a, b, teacher_is in ((teacher, mine, "A"), (mine, teacher, "B")):
            prompt = CHECK_PAIR.format(
                name=persona.name,
                sheet=persona.render_prompt_block(),
                rules=rules,
                chat=_chat_text(row, persona.name),
                a=a,
                b=b,
                criteria=criteria,
            )
            answer = chat(
                args.teacher_url,
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=2,
                grammar='root ::= "A" | "B"',
            )[0].strip()
            wins += answer == teacher_is
        _append(path, {"key": key, "wins": wins, "compared": True, **lore})

    # Filter keeps at most max_gate_rows // 3 "是" rows: check only the gate
    # rows of enough scripts to fill that (with room for disagreement) and
    # mark the rest skipped.
    gates = [r for r in rows if r["kind"].startswith("gate")]
    chosen = _gate_scripts(gates, done, math.ceil(args.max_gate_rows / 3 * 1.25))
    for row in jobs:
        if row["kind"].startswith("gate") and row["script"] not in chosen:
            _append(path, {"key": row_key(row), "skipped": True})
    # Gate questions first, then the comparisons: interleaved, each kind of
    # prompt would evict the other from the slot and every gate row would
    # re-read its whole chat.
    _pool_scripts(
        args.workers,
        work,
        [r for r in jobs if r["kind"].startswith("gate") and r["script"] in chosen],
    )
    _pool_scripts(
        args.workers, work, [r for r in jobs if not r["kind"].startswith("gate")
                             and not (args.lines_by_rules and r["kind"] in LINE_KINDS)]
    )


def _gate_scripts(
    gates: list[dict[str, Any]], done: set[str], wanted_yes: int
) -> set[Any]:
    """Scripts whose gate rows get checked: those already started, then
    random others, until they hold `wanted_yes` rows labelled 是."""
    by_script: dict[Any, list[dict[str, Any]]] = {}
    for row in gates:
        by_script.setdefault(row["script"], []).append(row)
    order = sorted(by_script)
    random.Random(6000).shuffle(order)
    order.sort(key=lambda s: not any(row_key(r) in done for r in by_script[s]))
    chosen: set[Any] = set()
    yes = 0
    for script in order:
        if yes >= wanted_yes:
            break
        chosen.add(script)
        yes += sum(r["messages"][-1]["content"] == "是" for r in by_script[script])
    return chosen


def rule_ok(row: dict[str, Any]) -> bool:
    line = row["messages"][-1]["content"]
    if sum(ch in PARTICLES for ch in line) > 1:
        return False
    if row["kind"] == "report":
        return True  # saying what the Agent found is its job, not an echo
    hint = _hint(row)
    content = row["messages"][-2]["content"]
    previous = [
        t
        for t in (content.replace(hint, "") if hint else content).splitlines()
        if t and not t.startswith("（")
    ]
    if previous:
        said = re.sub(r"^[^：]{1,12}：", "", previous[-1])
        if difflib.SequenceMatcher(None, line, said).ratio() >= 0.75:
            return False
    return True


def _share(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def make_filter(args: argparse.Namespace) -> int:
    """Train only on checked rows, or refuse the whole set (exit 3)."""
    rows = _read(OUT_DIR / args.rows)
    verdicts = {r["key"]: r for r in _read(OUT_DIR / "check.jsonl")}
    checked = [r for r in rows if row_key(r) in verdicts]
    verdict = {id(r): verdicts[row_key(r)] for r in checked}
    gates = [
        r
        for r in checked
        if r["kind"].startswith("gate") and not verdict[id(r)].get("skipped")
    ]
    lines = [r for r in (rows if args.lines_by_rules else checked) if r["kind"] in LINE_KINDS]
    tasks = [r for r in checked if r["kind"] == "task_text"]
    lored = [r for r in lines if "lore" in verdict.get(id(r), {})]
    kept_gates = [r for r in gates if verdict[id(r)].get("agree")]
    # --lines-by-rules (the owner, 2026-10-06: train the writer's lines now):
    # a line needs only the app's rules; the checker's comparison and lore
    # verdicts are reported, not applied (it was not consistent enough to
    # rank a strong writer's lines against the student's).
    kept_lines = [
        r for r in lines
        if rule_ok(r) and (args.lines_by_rules or (
            verdict.get(id(r), {}).get("wins", 0) >= 2 and verdict.get(id(r), {}).get("lore", True)))
    ]
    kept_tasks = [r for r in tasks if verdict[id(r)].get("agree")]
    compared = [verdict[id(r)]["wins"] for r in lines if verdict.get(id(r), {}).get("compared")]

    def agree_on(label: str, of: list[dict[str, Any]]) -> float:
        labelled = [r for r in of if r["messages"][-1]["content"] == label]
        return _share(
            sum(bool(verdict[id(r)].get("agree")) for r in labelled), len(labelled)
        )

    stats = {
        "rows": len(rows),
        "coverage": _share(len(checked), len([r for r in rows if not (
            args.lines_by_rules and r["kind"] in LINE_KINDS)])),
        "gate_rows": len(gates),
        "gate_agree": _share(len(kept_gates), len(gates)),
        "gate_agree_yes": agree_on("是", gates),
        "gate_agree_no": agree_on("否", gates),
        "line_rows": len(lines),
        "line_win_rate": _share(
            sum(verdict.get(id(r), {}).get("wins", 0) >= 2 for r in lines), len(lines)
        ),
        "checker_consistent": _share(sum(w != 1 for w in compared), len(compared)),
        "lines_failed_rules": sum(not rule_ok(r) for r in lines),
        "lines_kept": len(kept_lines),
        "lull_kept": sum(r["kind"] == "lull" for r in kept_lines),
        "lore_ok": _share(sum(bool(verdict.get(id(r), {}).get("lore")) for r in lored), len(lored)),
    }
    minimum = dict(
        HARD_CHECK, gate_agree=args.min_gate_agree, lines_kept=args.min_lines
    )
    stats["lines_by_rules"] = args.lines_by_rules
    failed = [
        f"{name} {stats[name]} < {minimum[name]}"
        for name in ("coverage", "gate_agree", *(() if args.lines_by_rules else ("lines_kept",)))
        if stats[name] < minimum[name]
    ]
    if gates:
        failed += [
            f"{name} {stats[name]} < {minimum['gate_agree_each']}"
            for name in ("gate_agree_yes", "gate_agree_no")
            if stats[name] < minimum["gate_agree_each"]
        ]
    if lines and not args.lines_by_rules:
        failed += [
            f"{name} {stats[name]} < {minimum[name]}"
            for name in ("line_win_rate", "checker_consistent")
            if stats[name] < minimum[name]
        ]
    if lored and not args.lines_by_rules:
        failed += [f"lore_ok {stats['lore_ok']} < {minimum['lore_ok']}"] * (
            stats["lore_ok"] < minimum["lore_ok"])
    # An agent character's two work questions, each on its own: a set whose
    # overall gate number passes can still have one of them broken.
    for kind in AGENT_GATES:
        of_kind = [r for r in gates if r["kind"] == kind]
        if not of_kind:
            continue
        stats |= {
            f"{kind}_rows": len(of_kind),
            f"{kind}_agree": _share(sum(bool(verdict[id(r)].get("agree")) for r in of_kind),
                                    len(of_kind)),
            f"{kind}_agree_yes": agree_on("是", of_kind),
            f"{kind}_agree_no": agree_on("否", of_kind),
        }
        failed += [f"{kind}_agree {stats[f'{kind}_agree']} < {minimum[f'{kind}_agree']}"] * (
            stats[f"{kind}_agree"] < minimum[f"{kind}_agree"])
        failed += [
            f"{name} {stats[name]} < {minimum['gate_agree_each']}"
            for name in (f"{kind}_agree_yes", f"{kind}_agree_no")
            if stats[name] < minimum["gate_agree_each"]
        ]
    if tasks:
        stats |= {"task_text_rows": len(tasks),
                  "task_text_agree": _share(len(kept_tasks), len(tasks))}
        failed += [f"task_text_agree {stats['task_text_agree']} < {minimum['task_text_agree']}"] * (
            stats["task_text_agree"] < minimum["task_text_agree"])
    # Keep "否" from swamping the gate, as render does. Each gate row costs a
    # whole chat of compute for one trained token, and the E4B gate run had
    # most of its eval-loss drop within the first ~1600 rows: cap them.
    yes = [r for r in kept_gates if r["messages"][-1]["content"] == "是"]
    yes = yes[: args.max_gate_rows // 3]
    no = [r for r in kept_gates if r["messages"][-1]["content"] == "否"][: len(yes) * 2]
    keep = yes + no + kept_lines + kept_tasks
    kept: dict[str, int] = {}
    for row in keep:
        kept[row["kind"]] = kept.get(row["kind"], 0) + 1
    stats["kept"] = kept  # what would be trained on, per kind
    stats["refused"] = failed
    print(f"filter: {stats}", flush=True)
    (OUT_DIR / "filter.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1)
    )
    if failed:
        print("REFUSED, nothing to train on: " + "; ".join(failed), flush=True)
        return 3
    random.Random(4100).shuffle(keep)
    with (OUT_DIR / "train-checked.jsonl").open("w", encoding="utf-8") as handle:
        for row in keep:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    provenance.stamp(OUT_DIR / "train-checked.jsonl", PRODUCER, rules_version())
    print(
        f"train-checked: {len(keep)} rows ({len(yes)} 是, {len(no)} 否, {len(kept_lines)} lines, "
        f"{len(kept_tasks)} task instructions) {kept}",
        flush=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=("external-check", "external-import", "render", "student", "check",
                                         "filter"))
    parser.add_argument("--tasks", help="external-check/import: the chats' persona and skeletons (.json)")
    parser.add_argument("--file", help="external-check/import: the writer's answers (JSONL)")
    parser.add_argument("--student-url", default="http://127.0.0.1:18210")
    parser.add_argument("--teacher-url", default="http://127.0.0.1:18200", help="check: the checker")
    parser.add_argument("--rows", default="train.jsonl", help="student/check/filter: rows file in the data dir")
    parser.add_argument("--min-gate-agree", type=float, default=HARD_CHECK["gate_agree"])
    parser.add_argument("--min-lines", type=int, default=HARD_CHECK["lines_kept"])
    parser.add_argument("--max-gate-rows", type=int, default=4000)
    parser.add_argument("--lines-by-rules", action="store_true",
                        help="check: compare no lines; filter: keep every line that passes the app's rules")
    parser.add_argument("--workers", type=int, default=4, help="match llama-server --parallel")
    parser.add_argument("--max-chars", type=int, default=72)
    parser.add_argument("--max-prompt-chars", type=int, default=3400)
    args = parser.parse_args()
    if args.step == "external-check":
        # Runs on the machine that wrote the answers: no data directory.
        return make_external_check(args)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every file this step reads or extends must come from these rules.
    problems = provenance.require_same(
        [OUT_DIR / name for name in {*DATA_FILES, args.rows}], rules_version())
    if problems:
        print("REFUSED, data made under other rules (start a new data directory): "
              + "; ".join(problems), flush=True)
        return MIXED_EXIT
    if args.step == "filter":
        return make_filter(args)
    {"external-import": make_external_import, "render": make_render, "student": make_student,
     "check": make_check}[args.step](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
