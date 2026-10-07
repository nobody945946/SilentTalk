"""The turn-taking test set (turn_eval.py): its conversations and decision
points, who plays in them (the set's personas, or one --persona-file card
for all, with the set's owner), and where results on it are written."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_PATH = Path(__file__).with_name("turn_eval_data.jsonl")
OUT_DIR = PROJECT_DIR / ".runtime" / "dev" / "turn_eval"
EXPECTS = ("speak", "silent", "either")
REQUIRED_TAGS = (
    "called_by_name", "called_mid", "third_person", "you_to_other", "misheard_name",
    "reply_to_bot", "ai_probe", "assistant_request", "private_talk",
    "question_to_group", "plain",
)

# Set by turn_eval.py from its flags; other modules read them through this
# module (turn_eval_set.OWNER_NAME), so they see the value set.
# --persona-file: one persona row (character_data / machine_spirit.py pick)
# used for every conversation. With "agent": true the character takes the
# owner's work (copilot.character_agent) and is a machine (honesty).
PERSONA_OVERRIDE: dict[str, Any] | None = None
OWNER_NAME = ""


@dataclass
class Conversation:
    id: str
    persona_id: str
    engagement: str
    scene: str
    lines: list[dict[str, Any]]


@dataclass
class TestSet:
    meta: dict[str, Any]
    conversations: list[Conversation] = field(default_factory=list)

    def decision_points(self) -> list[tuple[Conversation, int, dict[str, Any]]]:
        return [
            (conv, index, line)
            for conv in self.conversations
            for index, line in enumerate(conv.lines)
            if not line.get("self")
        ]


def load_test_set(path: Path = DATA_PATH) -> TestSet:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or "meta" not in rows[0]:
        raise SystemExit(f"{path}: first line must be the meta header")
    test_set = TestSet(rows[0]["meta"])
    persona_ids = {p["id"] for p in test_set.meta.get("personas", [])}
    for row in rows[1:]:
        conv = Conversation(
            row["id"], row["persona_id"], row["engagement"], row.get("scene", ""), row["lines"]
        )
        if conv.engagement not in ("called", "active"):
            raise SystemExit(f"{conv.id}: engagement must be called|active")
        if not (conv.persona_id.startswith("preset-") or conv.persona_id in persona_ids
                or PERSONA_OVERRIDE is not None):
            raise SystemExit(f"{conv.id}: unknown persona {conv.persona_id}")
        for index, line in enumerate(conv.lines):
            where = f"{conv.id}#{index}"
            if not line.get("text", "").strip():
                raise SystemExit(f"{where}: empty text")
            if line.get("self"):
                continue
            if line.get("expect") not in EXPECTS:
                raise SystemExit(f"{where}: expect must be one of {EXPECTS}")
            if not line.get("tags"):
                raise SystemExit(f"{where}: tags missing")
            if line.get("via", "voice") not in ("voice", "text"):
                raise SystemExit(f"{where}: via must be voice|text")
            if line.get("mention") and line.get("via") != "text":
                raise SystemExit(f"{where}: mention only exists for typed lines")
        test_set.conversations.append(conv)
    return test_set


def print_stats(test_set: TestSet) -> None:
    points = test_set.decision_points()
    by_expect = defaultdict(int)
    by_tag: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_mode: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for conv, _, line in points:
        by_expect[line["expect"]] += 1
        by_mode[conv.engagement][line["expect"]] += 1
        for tag in line["tags"]:
            by_tag[tag][line["expect"]] += 1
    lengths = [len(conv.lines) for conv in test_set.conversations]
    humans = [len({l["speaker"] for l in conv.lines if not l.get("self")}) for conv in test_set.conversations]
    modes = defaultdict(int)
    for conv in test_set.conversations:
        modes[conv.engagement] += 1
    total = len(points)
    print(f"conversations {len(test_set.conversations)}  "
          f"(called {modes['called']}, active {modes['active']})  "
          f"lines {min(lengths)}-{max(lengths)}  humans {min(humans)}-{max(humans)}")
    speakish = by_expect["speak"] + by_expect["either"]
    print(f"decision points {total}: speak {by_expect['speak']}  either {by_expect['either']}  "
          f"silent {by_expect['silent']}  (speak+either {speakish / total:.0%})")
    for mode, counts in sorted(by_mode.items()):
        print(f"  {mode:<7} " + "  ".join(f"{k} {counts[k]}" for k in EXPECTS))
    print(f"{'tag':<18}{'n':>5}{'speak':>7}{'either':>8}{'silent':>8}")
    for tag in sorted(by_tag, key=lambda t: -sum(by_tag[t].values())):
        counts = by_tag[tag]
        print(f"{tag:<18}{sum(counts.values()):>5}{counts['speak']:>7}"
              f"{counts['either']:>8}{counts['silent']:>8}")
    missing = [t for t in REQUIRED_TAGS if t not in by_tag]
    if missing:
        print("missing required tags:", ", ".join(missing))


def agent_persona() -> bool:
    return bool(PERSONA_OVERRIDE and PERSONA_OVERRIDE.get("agent"))


def resolve_persona(persona_module: Any, test_set: TestSet, persona_id: str) -> Any:
    if PERSONA_OVERRIDE is not None:
        # --persona-file (machine_spirit_eval.jsonl: the chosen card), with
        # the set's owner as the persona's owner.
        persona = persona_module.persona_from_dict(PERSONA_OVERRIDE)
        owner, relation = test_set.meta.get("owner"), PERSONA_OVERRIDE.get("owner_relation")
        if owner and relation:
            from dataclasses import replace

            persona = replace(persona, relationships=(
                persona_module.Relationship(owner, relation), *persona.relationships))
        return persona
    # EXAMPLE_PERSONAS since the machine spirit became the only preset;
    # older revisions (--old-rev) keep them in PRESET_PERSONAS.
    for preset in (*persona_module.PRESET_PERSONAS, *getattr(persona_module, "EXAMPLE_PERSONAS", ())):
        if preset.id == persona_id:
            return preset
    for raw in test_set.meta.get("personas", []):
        if raw["id"] == persona_id:
            return persona_module.persona_from_dict(raw)
    raise SystemExit(f"unknown persona {persona_id}")


def speaker_ids(conv: Conversation) -> dict[str, int]:
    ids: dict[str, int] = {}
    for line in conv.lines:
        if not line.get("self"):
            ids.setdefault(line["speaker"], len(ids) + 1)
    return ids
