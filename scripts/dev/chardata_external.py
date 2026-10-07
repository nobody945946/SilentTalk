"""The writer's answers (character_data.py external-check / external-import):
each chat's words put on its skeleton, held to the script rules where they
were written, and the usable ones joined to this run's scripts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import chardata_store as store
from chardata_scripts import check_script

from silenttalk.copilot.script import to_taiwan_traditional


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
    persona = store.persona_of(job["persona"])
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
    path = store.OUT_DIR / "scripts.jsonl"
    for script in scripts:
        store.append_row(path, script)
    store.stamp(path)
    print(f"external import: {len(scripts)} kept; dropped {len(problems)}", flush=True)
    for problem in problems:
        print(problem, flush=True)
