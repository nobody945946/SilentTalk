"""The filter step (character_data.py filter): the hard check that decides
which checked rows train (train-checked.jsonl), or refuses the whole set."""

from __future__ import annotations

import argparse
import difflib
import json
import random
import re
from typing import Any

import chardata_store as store
from chardata_requests import LINE_KINDS, row_hint

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


def rule_ok(row: dict[str, Any]) -> bool:
    line = row["messages"][-1]["content"]
    if sum(ch in PARTICLES for ch in line) > 1:
        return False
    if row["kind"] == "report":
        return True  # saying what the Agent found is its job, not an echo
    hint = row_hint(row)
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
    rows = store.read_rows(store.OUT_DIR / args.rows)
    verdicts = {r["key"]: r for r in store.read_rows(store.OUT_DIR / "check.jsonl")}
    checked = [r for r in rows if store.row_key(r) in verdicts]
    verdict = {id(r): verdicts[store.row_key(r)] for r in checked}
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
    (store.OUT_DIR / "filter.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1)
    )
    if failed:
        print("REFUSED, nothing to train on: " + "; ".join(failed), flush=True)
        return 3
    random.Random(4100).shuffle(keep)
    with (store.OUT_DIR / "train-checked.jsonl").open("w", encoding="utf-8") as handle:
        for row in keep:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    store.stamp(store.OUT_DIR / "train-checked.jsonl")
    print(
        f"train-checked: {len(keep)} rows ({len(yes)} 是, {len(no)} 否, {len(kept_lines)} lines, "
        f"{len(kept_tasks)} task instructions) {kept}",
        flush=True,
    )
    return 0
