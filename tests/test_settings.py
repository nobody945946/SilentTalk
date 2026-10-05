from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path

import pytest

from silenttalk.config import ConfigError, config_defaults, load_settings
from silenttalk.discord_voice import invite_url
from silenttalk.settings_schema import all_settings
from silenttalk.settings_store import SettingsError, SettingsStore, merge
from silenttalk.settings_ui import SettingsPanel
from silenttalk.ui import SilentTalkUI


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


def test_settings_discord_invite_link_displays_and_updates() -> None:
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("No graphical display available for Tk")

    try:
        link_state = ""

        def get_link() -> str:
            return link_state

        defaults = config_defaults(Path("."))
        panel = SettingsPanel(root, None, defaults, on_status=lambda _: None)

        card_body: tk.Frame | None = None

        def build_discord_invite(parent: tk.Frame) -> None:
            nonlocal card_body
            from silenttalk.widgets import card
            box = card(parent)
            box.outer.pack(fill="x")
            card_body = tk.Frame(box)
            card_body.pack(fill="x")
            refresh_discord_invite()

        def refresh_discord_invite() -> None:
            if card_body is None:
                return
            for child in card_body.winfo_children():
                child.destroy()
            link = get_link()
            if link:
                entry = tk.Entry(card_body)
                entry.insert(0, link)
                entry.pack(side="left")
            else:
                tk.Label(card_body, text="連上 Discord 後才會出現邀請連結").pack(anchor="w")

        panel.add_custom_group("discord", build_discord_invite, on_show=refresh_discord_invite)

        # 1. Before login: empty link shows hint
        panel.show("discord")
        labels = [c for c in card_body.winfo_children() if isinstance(c, tk.Label)]
        assert any("連上 Discord 後才會出現" in c.cget("text") for c in labels)

        # 2. After login: returns invite_url and updates on show
        expected_url = invite_url(1552128066719981608)
        link_state = expected_url
        panel.show("discord")

        entries = [c for c in card_body.winfo_children() if isinstance(c, tk.Entry)]
        assert len(entries) == 1
        assert entries[0].get() == expected_url
    finally:
        root.destroy()


def test_silenttalk_ui_invite_link_card() -> None:
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
    except tk.TclError:
        pytest.skip("No graphical display available for Tk")

    link_state = ""
    try:
        ui = SilentTalkUI(
            "F8", "F9", lambda _: None, lambda: None, lambda: None,
            config_defaults=config_defaults(Path(".")),
            invite_link=lambda: link_state,
        )
    except tk.TclError:
        pytest.skip("No graphical display available for Tk")
    try:
        ui.settings_panel.show("discord")
        assert ui._invite_card_body is not None
        labels = [c for c in ui._invite_card_body.winfo_children() if isinstance(c, tk.Label)]
        assert any("連上 Discord 後才會出現" in c.cget("text") for c in labels)

        url = invite_url(1552128066719981608)
        link_state = url
        ui.settings_panel.show("discord")

        found = False
        for child in ui._invite_card_body.winfo_children():
            for sub in child.winfo_children():
                if isinstance(sub, tk.Entry):
                    assert sub.get() == url
                    found = True
                elif isinstance(sub, tk.Frame):
                    for sub2 in sub.winfo_children():
                        if isinstance(sub2, tk.Entry):
                            assert sub2.get() == url
                            found = True
        assert found, "Entry with invite link not found"
    finally:
        ui.close()

