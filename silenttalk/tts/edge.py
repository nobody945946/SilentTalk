from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

import edge_tts

from silenttalk.config import TTSConfig
from silenttalk.speech_settings import combine_edge_rate, validate_rate_multiplier
from silenttalk.tts.base import AudioResult
from silenttalk.voice_styles import VOICE_STYLES

_LOG = logging.getLogger(__name__)


def _consume_legacy_style_prefix(text: str, voice_style: str) -> tuple[str, str]:
    """Keep old /deep, /space_marine, etc. inputs working without using them internally."""
    stripped = text.lstrip()
    prefix, separator, remainder = stripped.partition(" ")
    if not prefix.startswith("/") or not separator or not remainder.strip():
        return text, voice_style

    key = prefix[1:].lower()
    if key not in VOICE_STYLES:
        return text, voice_style
    return remainder.strip(), key


def resolve_speech_settings(
    text: str,
    config: TTSConfig,
    voice_style: str = "default",
    rate_multiplier: float = 1.0,
) -> tuple[str, str, str, str, str, str | None]:
    """Resolve text + structured style + UI speed into EdgeTTS/FFmpeg settings."""
    validate_rate_multiplier(rate_multiplier)
    spoken_text, style_key = _consume_legacy_style_prefix(text, voice_style)
    style = VOICE_STYLES.get(style_key)
    if style is None:
        raise ValueError(f"未知聲線：{style_key}")

    if style.key == "default":
        voice = config.voice
        base_rate = config.rate
        pitch = config.pitch
        volume = config.volume
    else:
        voice = style.voice or config.voice
        base_rate = style.rate
        pitch = style.pitch
        volume = style.volume

    rate = combine_edge_rate(base_rate, rate_multiplier)
    return spoken_text, voice, rate, pitch, volume, style.ffmpeg_filter


class EdgeTTSEngine:
    def __init__(self, config: TTSConfig, temp_dir: Path) -> None:
        self._config = config
        self._temp_dir = temp_dir
        self._voice = config.voice

    @property
    def voice(self) -> str:
        return self._voice

    async def initialize(self) -> None:
        if self._voice:
            return
        voices = await asyncio.wait_for(
            edge_tts.list_voices(), timeout=self._config.timeout_seconds
        )
        candidates = [v for v in voices if str(v.get("Locale", "")).lower() == "zh-tw"]
        if not candidates:
            raise RuntimeError("EdgeTTS 沒有回傳 zh-TW voice。")
        female = next(
            (v for v in candidates if v.get("Gender") == "Female"), candidates[0]
        )
        self._voice = str(female["ShortName"])
        _LOG.info("edge_tts_voice_selected voice=%s", self._voice)

    async def synthesize(
        self,
        text: str,
        voice_style: str = "default",
        rate_multiplier: float = 1.0,
    ) -> AudioResult:
        if not self._voice:
            await self.initialize()

        effective_config = TTSConfig(
            engine=self._config.engine,
            voice=self._voice,
            rate=self._config.rate,
            pitch=self._config.pitch,
            volume=self._config.volume,
            timeout_seconds=self._config.timeout_seconds,
        )
        spoken_text, voice, rate, pitch, volume, audio_filter = resolve_speech_settings(
            text,
            effective_config,
            voice_style=voice_style,
            rate_multiplier=rate_multiplier,
        )

        fd, raw_path = tempfile.mkstemp(
            prefix="silenttalk-", suffix=".mp3", dir=self._temp_dir
        )
        import os

        os.close(fd)
        path = Path(raw_path)
        try:
            communicate = edge_tts.Communicate(
                spoken_text,
                voice,
                rate=rate,
                volume=volume,
                pitch=pitch,
            )
            await asyncio.wait_for(
                communicate.save(str(path)), timeout=self._config.timeout_seconds
            )
            if path.stat().st_size == 0:
                raise RuntimeError("EdgeTTS 產生空白音訊。")
            return AudioResult(
                path, None, None, "mp3", ffmpeg_filter=audio_filter
            )
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    async def shutdown(self) -> None:
        return None
