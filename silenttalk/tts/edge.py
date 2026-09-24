from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

import edge_tts

from silenttalk.config import TTSConfig
from silenttalk.tts.base import AudioResult
from silenttalk.voice_styles import VOICE_STYLES, VoiceStyle

_LOG = logging.getLogger(__name__)


def resolve_speech_style(
    text: str, config: TTSConfig
) -> tuple[str, str, str, str, str | None]:
    """Resolve optional /style prefix into text, voice, rate, pitch and filter."""
    stripped = text.lstrip()
    prefix, separator, remainder = stripped.partition(" ")
    key = prefix[1:].lower() if prefix.startswith("/") else ""
    style = VOICE_STYLES.get(key)
    if style is None or not separator or not remainder.strip():
        return text, config.voice, config.rate, config.pitch, None
    voice = style.voice or config.voice
    volume = style.volume if style.key != "default" else config.volume
    return remainder.strip(), voice, style.rate, style.pitch, style.ffmpeg_filter


def resolve_speech_volume(text: str, config: TTSConfig) -> str:
    stripped = text.lstrip()
    prefix, separator, remainder = stripped.partition(" ")
    key = prefix[1:].lower() if prefix.startswith("/") else ""
    style = VOICE_STYLES.get(key)
    if style is None or not separator or not remainder.strip():
        return config.volume
    return style.volume


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

    async def synthesize(self, text: str) -> AudioResult:
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
        spoken_text, voice, rate, pitch, audio_filter = resolve_speech_style(
            text, effective_config
        )
        volume = resolve_speech_volume(text, effective_config)
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
