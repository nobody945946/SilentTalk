from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import tomllib
from dotenv import load_dotenv


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AppConfig:
    speak_hotkey: str = "F8"
    stop_hotkey: str = "F9"
    max_text_length: int = 300


@dataclass(frozen=True, slots=True)
class TTSConfig:
    engine: str = "edge"
    voice: str = ""
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"
    timeout_seconds: float = 20.0


@dataclass(frozen=True, slots=True)
class DiscordConfig:
    token: str
    owner_user_id: int
    disconnect_when_owner_leaves: bool = True
    voice_reconnect_interval_seconds: float = 20.0
    voice_reconnect_max_interval_seconds: float = 60.0
    voice_state_settle_seconds: float = 1.5
    owner_leave_grace_seconds: float = 8.0
    voice_reconnect_cooldown_seconds: float = 2.0
    voice_ready_timeout_seconds: float = 12.0


@dataclass(frozen=True, slots=True)
class AudioConfig:
    ffmpeg_path: str = "ffmpeg"
    playback_timeout_seconds: float = 90.0


@dataclass(frozen=True, slots=True)
class Settings:
    app: AppConfig
    tts: TTSConfig
    discord: DiscordConfig
    audio: AudioConfig

    def validate_runtime(self) -> list[str]:
        issues: list[str] = []
        ffmpeg = self.audio.ffmpeg_path
        if not Path(ffmpeg).is_file() and shutil.which(ffmpeg) is None:
            issues.append(f"找不到 FFmpeg：{ffmpeg}")
        return issues


def _section(data: dict, name: str) -> dict:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"config.toml 的 [{name}] 必須是 table。")
    return value


def load_settings(project_dir: Path) -> Settings:
    load_dotenv(project_dir / ".env")
    config_path = project_dir / "config.toml"
    if not config_path.exists():
        raise ConfigError(f"找不到唯一設定檔：{config_path}")
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    owner_raw = os.getenv("OWNER_USER_ID", "").strip()
    if not token:
        raise ConfigError(".env 缺少 DISCORD_BOT_TOKEN。")
    if not owner_raw.isdecimal() or int(owner_raw) <= 0:
        raise ConfigError(".env 的 OWNER_USER_ID 必須是正整數 Discord User ID。")

    app = _section(raw, "app")
    tts = _section(raw, "tts")
    discord = _section(raw, "discord")
    audio = _section(raw, "audio")
    engine = str(tts.get("engine", "edge")).lower()
    if engine != "edge":
        raise ConfigError('MVP 目前只支援 tts.engine = "edge"。')

    app_config = AppConfig(
        speak_hotkey=str(app.get("speak_hotkey", "F8")).upper(),
        stop_hotkey=str(app.get("stop_hotkey", "F9")).upper(),
        max_text_length=int(app.get("max_text_length", 300)),
    )
    if app_config.speak_hotkey == app_config.stop_hotkey:
        raise ConfigError("speak_hotkey 與 stop_hotkey 不可相同。")
    if app_config.max_text_length <= 0:
        raise ConfigError("max_text_length 必須大於 0。")

    reconnect_interval = max(
        5.0, float(discord.get("voice_reconnect_interval_seconds", 20.0))
    )
    reconnect_max = max(
        reconnect_interval,
        float(discord.get("voice_reconnect_max_interval_seconds", 60.0)),
    )

    return Settings(
        app=app_config,
        tts=TTSConfig(
            engine=engine,
            voice=str(tts.get("voice", "")),
            rate=str(tts.get("rate", "+0%")),
            pitch=str(tts.get("pitch", "+0Hz")),
            volume=str(tts.get("volume", "+0%")),
            timeout_seconds=max(1.0, float(tts.get("timeout_seconds", 20.0))),
        ),
        discord=DiscordConfig(
            token=token,
            owner_user_id=int(owner_raw),
            disconnect_when_owner_leaves=bool(
                discord.get("disconnect_when_owner_leaves", True)
            ),
            voice_reconnect_interval_seconds=reconnect_interval,
            voice_reconnect_max_interval_seconds=reconnect_max,
            voice_state_settle_seconds=max(
                0.25, float(discord.get("voice_state_settle_seconds", 1.5))
            ),
            owner_leave_grace_seconds=max(
                0.0, float(discord.get("owner_leave_grace_seconds", 8.0))
            ),
            voice_reconnect_cooldown_seconds=max(
                0.5, float(discord.get("voice_reconnect_cooldown_seconds", 2.0))
            ),
            voice_ready_timeout_seconds=max(
                1.0, float(discord.get("voice_ready_timeout_seconds", 12.0))
            ),
        ),
        audio=AudioConfig(
            ffmpeg_path=str(audio.get("ffmpeg_path", "ffmpeg")),
            playback_timeout_seconds=max(
                10.0, float(audio.get("playback_timeout_seconds", 90.0))
            ),
        ),
    )
