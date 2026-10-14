"""The character data directory (character_data.py): where each step's files
are, how rows are appended, read and keyed, and the rules version every file
is stamped with (provenance.py)."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

import provenance  # scripts/dev

from silenttalk.conversation import (
    AGENT_NAME,
    AGENT_RESULT_CONTEXT_CHARS,
    AGENT_SPEAKER_ID,
    SPOKEN_RESULT_CHARS,
)
from silenttalk.copilot.character import BARE_CALL_CHARS
from silenttalk.copilot.task_runner import _FAILED, _MAX_WAITING, _QUEUED, _STOPPED
from silenttalk.persona import Persona, persona_from_dict

PROJECT_DIR = Path(__file__).resolve().parents[2]
DEV_DIR = Path(__file__).resolve().parent
# CHARDATA_DIR keeps each round's data apart (v1 stays in chardata/).
OUT_DIR = (
    Path(os.environ["CHARDATA_DIR"])
    if os.environ.get("CHARDATA_DIR")
    else PROJECT_DIR / ".runtime" / "dev" / "chardata"
)
_WRITE_LOCK = threading.Lock()

# What decides these files' content (provenance.py): the app's prompts, these
# rules and checks, the persona cards. A data directory holds one version.
RULE_FILES = (
    PROJECT_DIR / "silenttalk" / "copilot" / "llm.py",
    PROJECT_DIR / "silenttalk" / "persona.py",
    PROJECT_DIR / "silenttalk" / "ai_options.py",
    PROJECT_DIR / "silenttalk" / "copilot" / "reply_templates.py",
    PROJECT_DIR / "silenttalk" / "copilot" / "reply_prompts.py",
    PROJECT_DIR / "silenttalk" / "copilot" / "reply_parsing.py",
    PROJECT_DIR / "silenttalk" / "copilot" / "character_generation.py",
    # The generator itself: its command line and every module of its steps
    # (a module added later counts without being listed).
    DEV_DIR / "character_data.py",
    *sorted(DEV_DIR.glob("chardata_*.py")),
)
DATA_FILES = (
    "scripts.jsonl", "refined.jsonl", "train.jsonl", "student.jsonl", "check.jsonl",
    "train-checked.jsonl",
)
PRODUCER = "character_data"
_CLAIMED: set[Path] = set()
# What personas.jsonl stores beside the persona itself.
_EXTRA_KEYS = ("role", "owner_relation", "archetype", "stt_variants")


def rules_version() -> str:
    files = provenance.fingerprint([*RULE_FILES, OUT_DIR / "personas.jsonl"])
    # How the app puts the Agent's result into a chat, what it says of work
    # that waits or fails and what counts as a bare call shape an agent
    # character's rows too: those values, not their whole files, which change
    # for many other reasons and would stop a run for nothing.
    agent = repr((AGENT_NAME, AGENT_SPEAKER_ID, AGENT_RESULT_CONTEXT_CHARS, SPOKEN_RESULT_CHARS,
                  _QUEUED, _FAILED, _STOPPED, _MAX_WAITING, BARE_CALL_CHARS))
    return hashlib.sha256((files + agent).encode()).hexdigest()[:16]


def stamp(path: Path) -> None:
    """A file written whole, under the current rules."""
    provenance.stamp(path, PRODUCER, rules_version())


def append_row(path: Path, record: dict[str, Any]) -> None:
    with _WRITE_LOCK:
        if path.name in DATA_FILES and path not in _CLAIMED:
            provenance.claim(path, PRODUCER, rules_version())
            _CLAIMED.add(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # a line cut short when the process was killed mid-write
    return rows


def row_key(row: dict[str, Any]) -> str:
    return f"{row['script']}:{row['index']}:{row['kind']}"


def persona_of(raw: dict[str, Any]) -> Persona:
    """The persona of a personas.jsonl row, without what is stored beside it."""
    return persona_from_dict({k: v for k, v in raw.items() if k not in _EXTRA_KEYS})
