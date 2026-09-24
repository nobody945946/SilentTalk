from __future__ import annotations

import asyncio
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import edge_tts

from silenttalk.config import TTSConfig
from silenttalk.tts.base import AudioResult

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SpeechStyle:
    rate: str
    pitch: str


_STYLE_PRESETS: dict[str, SpeechStyle] = {
    "/slow": SpeechStyle("-25%", "-5Hz"),
    "/fast": SpeechStyle("+30%", "+0Hz"),
    "/deep": SpeechStyle("-8%", "-35Hz"),
    "/cute": SpeechStyle("+12%", "+35Hz"),
}


def resolve_speech_style(
    text: str, default_rate: str, default_pitch: str
) -> tuple[str, str, str]:
    """Return (spoken_text, rate, pitch) for an optional one-shot style prefix."""
    stripped = text.lstrip()
    prefix, separator, remainder = stripped.partition(" ")
    style = _STYLE_PRESETS.get(prefix.lower())
    if style is None or not separator or not remainder.strip():
        return text, default_rate, default_pitch
    return remainder.strip(), style.rate, style.pitch


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
        spoken_text, rate, pitch = resolve_speech_style(
            text, self._config.rate, self._config.pitch
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
                self._voice,
                rate=rate,
                volume=self._config.volume,
                pitch=pitch,
            )
            await asyncio.wait_for(
                communicate.save(str(path)), timeout=self._config.timeout_seconds
            )
            if path.stat().st_size == 0:
                raise RuntimeError("EdgeTTS 產生空白音訊。")
            return AudioResult(path, None, None, "mp3")
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    async def shutdown(self) -> None:
        return None
