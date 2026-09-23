from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from silenttalk.state import AppState
from silenttalk.tts.base import AudioResult, TTSEngine

_LOG = logging.getLogger(__name__)


class JobState(StrEnum):
    QUEUED = "QUEUED"
    SYNTHESIZING = "SYNTHESIZING"
    PLAYING = "PLAYING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class SpeechJob:
    text: str = field(repr=False)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    state: JobState = JobState.QUEUED


class AudioPlayer(Protocol):
    async def play(self, audio: AudioResult) -> None: ...

    async def stop(self) -> None: ...


StatusCallback = Callable[[AppState, str], None]


class SpeechQueue:
    """One synthesis and one playback at a time, with generation-based cancel."""

    def __init__(
        self, tts: TTSEngine, player: AudioPlayer, status: StatusCallback
    ) -> None:
        self._tts = tts
        self._player = player
        self._status = status
        self._queue: asyncio.Queue[SpeechJob] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._current: SpeechJob | None = None
        self._generation = 0
        self._idle = asyncio.Event()
        self._idle.set()

    @property
    def current(self) -> SpeechJob | None:
        return self._current

    def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="speech-queue")

    async def enqueue(self, text: str) -> SpeechJob:
        if self._worker is None or self._worker.done():
            self.start()
        job = SpeechJob(text=text)
        self._idle.clear()
        await self._queue.put(job)
        _LOG.info("job_queued job_id=%s char_count=%d", job.id, len(text))
        return job

    async def cancel_all(self) -> None:
        self._generation += 1
        while True:
            try:
                job = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            job.state = JobState.CANCELLED
            self._queue.task_done()
        if self._current is not None:
            self._current.state = JobState.CANCELLED
        await self._player.stop()
        if self._current is None:
            self._idle.set()
        _LOG.info("queue_cancelled")

    async def wait_idle(self) -> None:
        await self._idle.wait()

    async def shutdown(self) -> None:
        await self.cancel_all()
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None
        await self._tts.shutdown()

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            self._current = job
            generation = self._generation
            audio: AudioResult | None = None
            started = time.perf_counter()
            try:
                job.state = JobState.SYNTHESIZING
                self._status(AppState.SYNTHESIZING, "語音合成中…")
                audio = await self._tts.synthesize(job.text)
                synth_ms = round((time.perf_counter() - started) * 1000)
                if generation != self._generation:
                    job.state = JobState.CANCELLED
                    continue
                job.state = JobState.PLAYING
                self._status(AppState.SPEAKING, "播放中…")
                await self._player.play(audio)
                if generation == self._generation:
                    job.state = JobState.DONE
                    _LOG.info(
                        "job_done job_id=%s char_count=%d backend=edge synthesis_ms=%d",
                        job.id,
                        len(job.text),
                        synth_ms,
                    )
            except asyncio.CancelledError:
                job.state = JobState.CANCELLED
                raise
            except Exception as exc:  # noqa: BLE001 - a failed job must not kill the worker.
                job.state = JobState.FAILED
                _LOG.error(
                    "job_failed job_id=%s error_type=%s", job.id, type(exc).__name__
                )
                self._status(AppState.ERROR, f"播放失敗：{exc}")
            finally:
                if audio is not None:
                    audio.path.unlink(missing_ok=True)
                self._current = None
                self._queue.task_done()
                if self._queue.empty():
                    self._idle.set()
                    if job.state is not JobState.FAILED:
                        self._status(AppState.READY, "就緒")
