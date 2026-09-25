from pathlib import Path

import pytest

from silenttalk.preferences import PreferenceError, PreferenceStore, UserPreferences


def test_preferences_default_to_normal_speed(tmp_path: Path) -> None:
    store = PreferenceStore(tmp_path / "ui_preferences.json")
    assert store.load() == UserPreferences(speech_rate_multiplier=1.0)


def test_preferences_round_trip_speed(tmp_path: Path) -> None:
    store = PreferenceStore(tmp_path / "ui_preferences.json")
    store.save(UserPreferences(speech_rate_multiplier=0.80))
    assert store.load() == UserPreferences(speech_rate_multiplier=0.80)


def test_preferences_reject_out_of_range_speed(tmp_path: Path) -> None:
    store = PreferenceStore(tmp_path / "ui_preferences.json")
    with pytest.raises(PreferenceError, match="語速倍率"):
        store.save(UserPreferences(speech_rate_multiplier=0.50))


def test_preferences_round_trip_story_mode(tmp_path: Path) -> None:
    store = PreferenceStore(tmp_path / "ui_preferences.json")
    store.save(UserPreferences(speech_rate_multiplier=1.2, ui_mode="story"))
    assert store.load() == UserPreferences(speech_rate_multiplier=1.2, ui_mode="story")


def test_preferences_ignore_unknown_saved_mode(tmp_path: Path) -> None:
    path = tmp_path / "ui_preferences.json"
    path.write_text('{"speech_rate_multiplier": 1.0, "ui_mode": "nope"}', "utf-8")
    assert PreferenceStore(path).load().ui_mode == "manual"
