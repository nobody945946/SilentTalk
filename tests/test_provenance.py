"""A training-data file never mixes rows made under two sets of rules."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "dev"))
import character_data  # noqa: E402
import chardata_store  # noqa: E402
import provenance  # noqa: E402


def test_appending_under_other_rules_is_refused(tmp_path: Path) -> None:
    data = tmp_path / "scripts.jsonl"
    provenance.claim(data, "test", "v1")
    data.write_text('{"a": 1}\n', encoding="utf-8")
    provenance.claim(data, "test", "v1")  # same rules: fine
    with pytest.raises(provenance.MixedData):
        provenance.claim(data, "test", "v2")
    unstamped = tmp_path / "refined.jsonl"
    unstamped.write_text('{"a": 1}\n', encoding="utf-8")
    with pytest.raises(provenance.MixedData):
        provenance.claim(unstamped, "test", "v1")


def test_a_set_must_share_one_version(tmp_path: Path) -> None:
    a, b, c = (tmp_path / name for name in ("a.jsonl", "b.jsonl", "c.jsonl"))
    for path in (a, b, c):
        path.write_text("{}\n", encoding="utf-8")
    provenance.stamp(a, "test", "v1")
    provenance.stamp(b, "test", "v2")
    problems = provenance.require_same([a, b, c, tmp_path / "missing.jsonl"], "v1")
    assert problems == ["b.jsonl: rules v2 != v1", "c.jsonl: no version stamp"]


def test_the_pipeline_refuses_a_directory_made_under_other_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chardata_store, "OUT_DIR", tmp_path)
    (tmp_path / "personas.jsonl").write_text("{}\n", encoding="utf-8")
    scripts = tmp_path / "scripts.jsonl"
    chardata_store.append_row(scripts, {"lines": []})
    assert json.loads(provenance.sidecar(scripts).read_text())["version"] == chardata_store.rules_version()
    monkeypatch.setattr(sys, "argv", ["character_data.py", "render"])
    monkeypatch.setattr(character_data, "make_render", lambda args: None)
    assert character_data.main() == 0
    # The persona card changes: everything made before it is stale.
    (tmp_path / "personas.jsonl").write_text('{"changed": true}\n', encoding="utf-8")
    assert character_data.main() == character_data.MIXED_EXIT
