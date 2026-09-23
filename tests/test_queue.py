from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from silenttalk.speech_queue import JobState, SpeechQueue
from silenttalk.tts.base import AudioResult


class FakeTTS:
    def __init__(self, directory: Path, delay: float = 0) -> None:
        self.directory = directory
        self.delay = delay
        self.calls: list[str] = []

    async def initialize(self) -> None:
        return None

    async def synthesize(self, text: str) -> AudioResult:
        self.calls.append(text)
        await asyncio.sleep(self.delay)
        path = self.directory / f"audio-{len(self.calls)}.mp3"
        path.write_bytes(b"audio")
        return AudioResult(path, None, None, "mp3")

    async def shutdown(self) -> None:
        return None


class FakePlayer:
    def __init__(self, delay: float = 0) -> None:
        self.delay = delay
        self.played: list[str] = []
        self.stopped = 0

    async def play(self, audio: AudioResult) -> None:
        self.played.append(audio.path.name)
        await asyncio.sleep(self.delay)

    async def stop(self) -> None:
        self.stopped += 1


@pytest.mark.asyncio
async def test_thirty_jobs_are_fifo_and_finish(tmp_path: Path) -> None:
    tts = FakeTTS(tmp_path)
    player = FakePlayer()
    queue = SpeechQueue(tts, player, lambda *_: None)
    jobs = [await queue.enqueue(f"第 {index} 句") for index in range(30)]
    await asyncio.wait_for(queue.wait_idle(), timeout=3)
    assert tts.calls == [f"第 {index} 句" for index in range(30)]
    assert len(player.played) == 30
    assert all(job.state is JobState.DONE for job in jobs)
    assert not list(tmp_path.glob("*.mp3"))
    await queue.shutdown()


@pytest.mark.asyncio
async def test_cancel_discards_current_synthesis_and_pending_jobs(
    tmp_path: Path,
) -> None:
    tts = FakeTTS(tmp_path, delay=0.05)
    player = FakePlayer()
    queue = SpeechQueue(tts, player, lambda *_: None)
    first = await queue.enqueue("第一句")
    second = await queue.enqueue("第二句")
    await asyncio.sleep(0.01)
    await queue.cancel_all()
    await asyncio.wait_for(queue.wait_idle(), timeout=1)
    assert first.state is JobState.CANCELLED
    assert second.state is JobState.CANCELLED
    assert player.played == []
    assert player.stopped == 1
    await queue.shutdown()
