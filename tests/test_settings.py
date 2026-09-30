from __future__ import annotations

import json
from pathlib import Path

import pytest

from silenttalk.config import ConfigError, config_defaults, load_settings
from silenttalk.settings_schema import all_settings
from silenttalk.settings_store import SettingsError, SettingsStore, merge


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_USER_ID", "123456789")
    (tmp_path / "config.toml").write_text(
        Path("config.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def test_the_page_can_change_settings_without_touching_config_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, monkeypatch)
    before = (project / "config.toml").read_text(encoding="utf-8")
    SettingsStore(project / "settings.json").save(
        {"copilot": {"character_engagement": "active", "compact_context": False}}
    )

    settings = load_settings(project)

    assert settings.copilot.character_engagement == "active"
    assert settings.copilot.compact_context is False
    # Untouched keys keep the file's values, and the file itself is unchanged.
    assert settings.copilot.compact_keep_turns == 96
    assert (project / "config.toml").read_text(encoding="utf-8") == before


def test_a_bad_value_from_the_page_is_rejected_by_the_same_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, monkeypatch)
    SettingsStore(project / "settings.json").save(
        {"copilot": {"character_engagement": "whatever"}}
    )

    with pytest.raises(ConfigError, match="character_engagement"):
        load_settings(project)


def test_every_setting_on_the_page_has_a_default_to_reset_to() -> None:
    defaults = config_defaults(Path("."))

    missing = [
        f"{s.section}.{s.key}" for s in all_settings() if s.key not in defaults[s.section]
    ]

    assert missing == []


def test_choices_offered_are_values_the_config_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, monkeypatch)
    store = SettingsStore(project / "settings.json")

    for setting in all_settings():
        if setting.kind != "choice" or setting.section != "copilot":
            continue
        for value, _label in setting.choices:
            store.save({setting.section: {setting.key: value}})
            load_settings(project)  # must not raise


def test_only_changed_values_are_stored(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")

    store.save({"copilot": {"a": 1}, "tts": {}})

    assert json.loads((tmp_path / "settings.json").read_text()) == {"copilot": {"a": 1}}


def test_unreadable_settings_file_reports_instead_of_crashing(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(SettingsError, match="讀取失敗"):
        SettingsStore(path).load()


def test_merge_keeps_sections_the_user_never_touched() -> None:
    merged = merge({"a": {"x": 1, "y": 2}, "b": {"z": 3}}, {"a": {"y": 9}})

    assert merged == {"a": {"x": 1, "y": 9}, "b": {"z": 3}}
