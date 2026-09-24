from pathlib import Path

import pytest

from silenttalk.config import ConfigError, load_settings


def _write_config(
    directory: Path,
    engine: str = "edge",
) -> None:
    (directory / "config.toml").write_text(
        f"""
[app]
max_text_length = 50
[tts]
engine = "{engine}"
[discord]
[audio]
ffmpeg_path = "missing-ffmpeg-for-test"
""",
        encoding="utf-8",
    )


def test_loads_env_and_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(tmp_path)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_USER_ID", "123456789")
    settings = load_settings(tmp_path)
    assert settings.discord.owner_user_id == 123456789
    assert settings.app.max_text_length == 50
    assert settings.tts.engine == "edge"
    assert settings.copilot.enabled is True
    assert settings.copilot.endpoint_silence_ms == 650
    assert settings.copilot.llm_context_size == 2048
    assert settings.validate_runtime() == ["找不到 FFmpeg：missing-ffmpeg-for-test"]


def test_loads_credentials_from_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path)
    (tmp_path / ".env").write_text(
        "DISCORD_BOT_TOKEN=file-token\nOWNER_USER_ID=987654321\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("OWNER_USER_ID", raising=False)

    settings = load_settings(tmp_path)

    assert settings.discord.token == "file-token"
    assert settings.discord.owner_user_id == 987654321


def test_rejects_missing_owner_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.delenv("OWNER_USER_ID", raising=False)
    with pytest.raises(ConfigError, match="OWNER_USER_ID"):
        load_settings(tmp_path)


def test_rejects_missing_bot_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setenv("OWNER_USER_ID", "123")
    with pytest.raises(ConfigError, match="DISCORD_BOT_TOKEN"):
        load_settings(tmp_path)


def test_rejects_missing_config(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="唯一設定檔"):
        load_settings(tmp_path)


def test_rejects_unimplemented_tts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path, "cosyvoice")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_USER_ID", "123")
    with pytest.raises(ConfigError, match="只支援"):
        load_settings(tmp_path)


def test_rejects_duplicate_hotkeys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.toml").write_text(
        '[app]\nspeak_hotkey = "F8"\nstop_hotkey = "F8"\n'
        '[tts]\nengine = "edge"\n'
        '[discord]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_USER_ID", "123")
    with pytest.raises(ConfigError, match="不可相同"):
        load_settings(tmp_path)
