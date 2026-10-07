from __future__ import annotations

import json
import os
import tkinter as tk
from pathlib import Path

import pytest

from silenttalk.config import ConfigError, config_defaults, load_settings
from silenttalk.discord_invite import invite_url
from silenttalk.settings_schema import all_settings
from silenttalk.settings_store import SettingsError, SettingsStore, merge
from silenttalk.settings_ui import SettingsPanel
from silenttalk.ui import SilentTalkUI


@pytest.fixture(scope="module")
def settings_ui():
    """Exercise real panels in one app/Tcl interpreter, as production does."""
    try:
        ui = SilentTalkUI(
            "F8", "F9", lambda _: None, lambda: None, lambda: None,
            config_defaults=config_defaults(Path(".")),
            invite_link=lambda: "",
        )
    except tk.TclError:
        if os.name == "nt":
            raise
        pytest.skip("No graphical display available for Tk")
    try:
        yield ui
    finally:
        ui.close()


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


def test_retired_agent_settings_are_absent_and_old_overrides_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import inspect
    from dataclasses import fields

    from silenttalk.config import CopilotConfig
    from silenttalk.copilot.llm import LocalReplyModel

    retired = {"llm_gpu_layers", "llm_low_vram", "agent_report_public"}
    assert retired.isdisjoint(s.key for s in all_settings())
    assert retired.isdisjoint(f.name for f in fields(CopilotConfig))
    assert retired.isdisjoint(config_defaults(Path("."))["copilot"])
    assert {"gpu_layers", "low_vram"}.isdisjoint(
        inspect.signature(LocalReplyModel).parameters
    )
    project = _project(tmp_path, monkeypatch)
    store = SettingsStore(project / "settings.json")
    store.save({"copilot": dict.fromkeys(retired, "obsolete")})
    before = store.path.read_bytes()
    load_settings(project)
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("tts_only", [True, False])
def test_app_startup_uses_current_model_settings(
    tmp_path, monkeypatch, enabled, tts_only
):
    import sys
    from dataclasses import replace
    from unittest.mock import Mock

    import app

    settings = load_settings(_project(tmp_path, monkeypatch))
    settings = replace(settings, copilot=replace(settings.copilot, enabled=enabled))
    controller = Mock()
    ui_factory = Mock()
    monkeypatch.setattr(
        sys, "argv", ["app.py", "--tts-only" if tts_only else "--character-mode"]
    )
    monkeypatch.setattr(app, "configure_logging", lambda _: None)
    monkeypatch.setattr(app, "load_settings", lambda _: settings)
    monkeypatch.setattr(app, "config_defaults", lambda _: {})
    monkeypatch.setattr(app, "AppController", Mock(return_value=controller))
    monkeypatch.setattr(app, "SilentTalkUI", ui_factory)

    assert app.main() == 0
    arguments = ui_factory.call_args.kwargs
    assert arguments["copilot_info"] == (
        [
            ("回覆模型", settings.copilot.llm_model),
            ("語音辨識", settings.copilot.stt_engine),
        ]
        if enabled and not tts_only
        else []
    )
    assert arguments["start_character_mode"] is (not tts_only)
    assert app.AppController.call_args.args[0].copilot.enabled is (
        enabled and not tts_only
    )
    assert settings.copilot.enabled is enabled
    controller.start.assert_called_once()
    ui_factory.return_value.run.assert_called_once()


def test_persona_editor_preserves_voice_values_and_protects_builtin(
    tmp_path: Path, settings_ui
) -> None:
    from dataclasses import replace

    from silenttalk.persona import MACHINE_SPIRIT, PersonaState, PersonaStore
    from silenttalk.persona_ui import PersonaPanel

    root = settings_ui.root
    store = PersonaStore(tmp_path / "personas.json")
    custom = replace(
        MACHINE_SPIRIT, id="custom", name="Test", voice_pitch=23, voice_speed=7
    )
    store.save(PersonaState([MACHINE_SPIRIT, custom], MACHINE_SPIRIT.id))
    statuses = []
    try:
        panel = PersonaPanel(
            root, store, on_apply=lambda _: None, on_status=statuses.append
        )
        assert panel.fields.collect(panel._current(), panel._name_var.get()).voice_pitch == 22
        assert panel._save(apply=True)
        assert store.load().active_persona().voice_pitch == 22
        before = store.path.read_bytes()
        panel._delete()
        panel._delete()
        assert store.path.read_bytes() == before
        assert panel._state.active == MACHINE_SPIRIT.id
        assert panel._state.find(MACHINE_SPIRIT.id) is not None
        assert any("內建" in message for message in statuses)

        panel._open(custom.id)
        assert panel.fields.collect(panel._current(), panel._name_var.get()).voice_pitch == 23
        assert panel.fields.collect(panel._current(), panel._name_var.get()).voice_speed == 7
        panel.fields.voice._voice_knobs["voice_pitch"].set(24, notify=True)
        assert panel._save(apply=True)
        saved = store.load().find(custom.id)
        assert (saved.voice_pitch, saved.voice_speed) == (24, 7)
        panel._delete()
        panel._delete()
        assert store.load().find(custom.id) is None
    finally:
        panel.destroy()


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


def test_settings_discord_invite_link_displays_and_updates(settings_ui) -> None:
    root = settings_ui.root

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
        panel.destroy()


def test_silenttalk_ui_invite_link_card(settings_ui, monkeypatch) -> None:
    link_state = ""
    ui = settings_ui
    monkeypatch.setattr(ui.invite, "_invite_link_getter", lambda: link_state)
    try:
        ui.settings_panel.show("discord")
        assert ui.invite._invite_card_body is not None
        labels = [
            c for c in ui.invite._invite_card_body.winfo_children() if isinstance(c, tk.Label)
        ]
        assert any("連上 Discord 後才會出現" in c.cget("text") for c in labels)

        url = invite_url(1552128066719981608)
        link_state = url
        ui.settings_panel.show("discord")

        found = False
        for child in ui.invite._invite_card_body.winfo_children():
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
        ui.settings_panel.show("chat")


def test_records_settings_prepare_and_show_status(tmp_path, settings_ui):
    from silenttalk import records
    root = settings_ui.root
    messages = []
    try:
        panel = SettingsPanel(root, None, config_defaults(Path(".")), on_status=messages.append)
        panel.set_value("copilot", "record_folder", str(tmp_path))
        panel.set_value("copilot", "record_transcripts", True)
        panel._refresh_record_status(schedule=False)
        assert panel._record_status.get().startswith("暫停")
        panel._prepare_records()
        assert (tmp_path / records.MARKER).is_file()
        assert panel._record_status.get() == "記錄中"
        (tmp_path / records.MARKER).unlink()
        panel._refresh_record_status(schedule=False)
        assert panel._record_status.get().startswith("暫停")
        panel.set_value("copilot", "record_transcripts", False)
        panel._refresh_record_status(schedule=False)
        assert panel._record_status.get() == "關閉"
        panel.set_value("copilot", "record_folder", str(tmp_path / "missing"))
        panel._prepare_records()
        assert messages[-1].startswith("無法設定紀錄資料夾")
    finally:
        panel.destroy()
