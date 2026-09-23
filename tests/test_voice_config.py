from pathlib import Path

import pytest

from silenttalk.config import load_settings


def test_voice_reconnect_backoff_is_configurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.toml").write_text(
        """
[tts]
engine = "edge"
[discord]
voice_reconnect_interval_seconds = 20.0
voice_reconnect_max_interval_seconds = 90.0
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_USER_ID", "123")
    settings = load_settings(tmp_path)
    assert settings.discord.voice_reconnect_interval_seconds == 20.0
    assert settings.discord.voice_reconnect_max_interval_seconds == 90.0
