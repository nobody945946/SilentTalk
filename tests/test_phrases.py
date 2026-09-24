from pathlib import Path

import pytest

from silenttalk.phrases import QuickPhraseError, QuickPhraseStore


def test_missing_file_loads_as_empty(tmp_path: Path) -> None:
    store = QuickPhraseStore(tmp_path / "quick_phrases.json")
    assert store.load() == []


def test_add_update_delete_round_trip(tmp_path: Path) -> None:
    store = QuickPhraseStore(tmp_path / "quick_phrases.json")

    assert store.add("等一下，我馬上回來。") == ["等一下，我馬上回來。"]
    assert store.add("左邊有人。") == ["等一下，我馬上回來。", "左邊有人。"]
    assert store.update(1, "右邊有人。") == ["等一下，我馬上回來。", "右邊有人。"]
    assert store.delete(0) == ["右邊有人。"]

    reloaded = QuickPhraseStore(tmp_path / "quick_phrases.json")
    assert reloaded.load() == ["右邊有人。"]


def test_rejects_blank_and_duplicate_phrases(tmp_path: Path) -> None:
    store = QuickPhraseStore(tmp_path / "quick_phrases.json")
    store.add("收到。")

    with pytest.raises(QuickPhraseError, match="不可為空白"):
        store.add("   ")

    with pytest.raises(QuickPhraseError, match="已存在"):
        store.add("收到。")


def test_rejects_invalid_json_shape(tmp_path: Path) -> None:
    path = tmp_path / "quick_phrases.json"
    path.write_text('{"phrase": "收到。"}', encoding="utf-8")
    store = QuickPhraseStore(path)

    with pytest.raises(QuickPhraseError, match="字串陣列"):
        store.load()


def test_enforces_max_phrase_count(tmp_path: Path) -> None:
    store = QuickPhraseStore(tmp_path / "quick_phrases.json", max_phrases=2)
    store.add("一")
    store.add("二")

    with pytest.raises(QuickPhraseError, match="最多 2 句"):
        store.add("三")
