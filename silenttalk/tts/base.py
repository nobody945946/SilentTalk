from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from silenttalk.tts.stream import AudioStream
from silenttalk.voice_styles import VoiceStyle


@dataclass(frozen=True, slots=True)
class AudioResult:
    """Synthesized audio: a temporary file at `path`, or, when `stream` is
    set, bytes still arriving (then `path` is None)."""

    path: Path | None
    sample_rate: int | None
    channel_count: int | None
    sample_format: str
    duration_seconds: float | None = None
    ffmpeg_filter: str | None = None
    stream: AudioStream | None = None

    def discard(self) -> None:
        """Release the audio after playback, cancel or failure."""
        if self.stream is not None:
            self.stream.close()
        if self.path is not None:
            self.path.unlink(missing_ok=True)


class TTSEngine(Protocol):
    async def initialize(self) -> None: ...

    async def synthesize(
        self,
        text: str,
        voice_style: str | VoiceStyle = "default",
        rate_multiplier: float = 1.0,
    ) -> AudioResult: ...

    async def shutdown(self) -> None: ...
