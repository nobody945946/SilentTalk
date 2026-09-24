from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AudioResult:
    path: Path
    sample_rate: int | None
    channel_count: int | None
    sample_format: str
    duration_seconds: float | None = None
    ffmpeg_filter: str | None = None


class TTSEngine(Protocol):
    async def initialize(self) -> None: ...

    async def synthesize(self, text: str) -> AudioResult: ...

    async def shutdown(self) -> None: ...
