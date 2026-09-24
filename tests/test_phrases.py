import json
from pathlib import Path

import pytest

from silenttalk.phrases import (
    DEFAULT_QUICK_PHRASES,
    QuickPhrase,
    QuickPhraseError,
    QuickPhraseStore,
)


def test_missing_file_loads_default_warhammer_pack(tmp_path: Path) -> None:
    store = QuickPhraseStore(tmp_path / "quick_phrases.json")
    assert store.load() == list(DEFAULT_QUICK_PHRASES)
    assert len(store.load()) == 6
    assert store.load()[0] == QuickPhrase("For the Emperor!", "space_marine")
    assert store.load()[2] == QuickPhrase("For the Omnissiah!", "mechanicus")


def test_add_update_delete_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "quick_phrases.json"
    path.write_text("[]", encoding="utf-8")
    store = QuickPhraseStore(path)

    assert store.add("等一下，我馬上回來。", "deep") == [
        QuickPhrase("等一下，我馬上回來。", "deep")
    ]
    assert store.add("左邊有人。")[-1] == QuickPhrase("左邊有人。", "default")
    assert store.update(1, "右邊有人。", "fast")[-1] == QuickPhrase(
        "右邊有人。", "fast"
    )
    assert store.delete(0) == [QuickPhrase("右邊有人。", "fast")]

    reloaded = QuickPhraseStore(path)
    assert reloaded.load() == [QuickPhrase("右邊有人。", "fast")]


def test_old_string_array_is_backward_compatible(tmp_path: Path) -> None:
    path = tmp_path / "quick_phrases.json"
    path.write_text(json.dumps(["收到。", "等等。"], ensure_ascii=False), encoding="utf-8")
    store = QuickPhraseStore(path)
    assert store.load() == [
        QuickPhrase("收到。", "default"),
        QuickPhrase("等等。", "default"),
    ]


def test_rejects_blank_duplicate_and_unknown_style(tmp_path: Path) -> None:
    path = tmp_path / "quick_phrases.json"
    path.write_text("[]", encoding="utf-8")
    store = QuickPhraseStore(path)
    store.add("收到。")

    with pytest.raises(QuickPhraseError, match="不可為空白"):
        store.add("   ")

    with pytest.raises(QuickPhraseError, match="已存在"):
        store.add("收到。", "deep")

    with pytest.raises(QuickPhraseError, match="未知"):
        store.add("測試。", "missing-style")


def test_enforces_max_phrase_count(tmp_path: Path) -> None:
    path = tmp_path / "quick_phrases.json"
    path.write_text("[]", encoding="utf-8")
    store = QuickPhraseStore(path, max_phrases=2)
    store.add("一")
    store.add("二")

    with pytest.raises(QuickPhraseError, match="最多 2 句"):
        store.add("三")
