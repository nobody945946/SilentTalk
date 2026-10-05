"""Handoff documents stay small enough to rewrite whole instead of patching.

AGENTS.md §3: a work file holds only the current state and next steps; when it
changes it is archived and rewritten, so a size limit keeps old history and
contradicting versions from piling up.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = [(ROOT / "AGENTS.md", 4_000)] + [
    (path, 10_000) for path in sorted((ROOT / "handoff").glob("*.md"))
]


@pytest.mark.parametrize(("path", "limit"), DOCS, ids=lambda value: getattr(value, "name", ""))
def test_handoff_document_stays_within_its_limit(path: Path, limit: int) -> None:
    length = len(path.read_text(encoding="utf-8"))
    assert length <= limit, (
        f"{path.relative_to(ROOT)} has {length} characters (limit {limit}); "
        "archive it and rewrite it with only the current state"
    )


def test_every_work_file_is_registered_in_agents_md() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for path in sorted((ROOT / "handoff").glob("*.md")):
        assert f"handoff/{path.name}" in agents
