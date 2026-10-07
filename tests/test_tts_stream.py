from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from silenttalk.config import AudioConfig, TTSConfig
from silenttalk.discord_playback import DiscordAudioPlayer
from silenttalk.speech_queue import JobState, SpeechQueue
from silenttalk.tts import edge
from silenttalk.tts.base import AudioResult
from silenttalk.tts.stream import AudioStream


def _chunks(*parts: bytes, gate: asyncio.Event | None = None, error: bool = False):
    async def produce():
        for n, part in enumerate(parts):
            if n == 1 and gate is not None:
                await gate.wait()
            yield part
        if error:
            raise OSError("connection reset")

    return produce


async def _read_all(stream: AudioStream) -> bytes:
    return await asyncio.to_thread(lambda: b"".join(iter(lambda: stream.read(3), b"")))


@pytest.mark.asyncio
async def test_start_returns_on_the_first_chunk_and_the_rest_keeps_coming() -> None:
    gate = asyncio.Event()
    stream = AudioStream()
    await stream.start(_chunks(b"abc", b"defg", gate=gate), first_chunk_timeout=10)

    assert stream.read(10) == b"abc"  # available before the rest was produced
    gate.set()
    assert await _read_all(stream) == b"defg"


@pytest.mark.asyncio
async def test_error_before_any_audio_fails_the_start() -> None:
    stream = AudioStream()
    with pytest.raises(OSError):
        await stream.start(_chunks(error=True), first_chunk_timeout=10)
    assert stream.read() == b""


@pytest.mark.asyncio
async def test_no_audio_at_all_fails_the_start() -> None:
    with pytest.raises(RuntimeError, match="空白"):
        await AudioStream().start(_chunks(), first_chunk_timeout=10)


@pytest.mark.asyncio
async def test_error_mid_stream_ends_the_audio_and_is_kept() -> None:
    stream = AudioStream()
    await stream.start(_chunks(b"abc", b"def", error=True), first_chunk_timeout=10)

    assert await _read_all(stream) == b"abcdef"
    assert isinstance(stream.error, OSError)


@pytest.mark.asyncio
async def test_close_releases_a_blocked_reader_and_stops_the_producer() -> None:
    gate = asyncio.Event()  # never set: the producer hangs after one chunk
    stream = AudioStream()
    await stream.start(_chunks(b"a", b"b", gate=gate), first_chunk_timeout=10)
    assert stream.read() == b"a"

    reader = threading.Thread(target=stream.read)
    reader.start()
    stream.close()
    await asyncio.to_thread(reader.join, 10)
    await asyncio.sleep(0)

    assert not reader.is_alive()
    assert stream._task is not None and stream._task.cancelled()


@pytest.mark.asyncio
async def test_slow_first_chunk_times_out() -> None:
    async def never():
        await asyncio.Event().wait()
        yield b""

    with pytest.raises(TimeoutError):
        await AudioStream().start(never, first_chunk_timeout=0.01)


class _FakeCommunicate:
    created: list[dict] = []

    def __init__(self, text, voice, **kwargs) -> None:
        _FakeCommunicate.created.append({"text": text, "voice": voice, **kwargs})

    async def stream(self):
        yield {"type": "WordBoundary"}
        yield {"type": "audio", "data": b"mp3-1"}
        yield {"type": "audio", "data": b"mp3-2"}


@pytest.mark.asyncio
async def test_edge_engine_streams_without_writing_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(edge.edge_tts, "Communicate", _FakeCommunicate)
    engine = edge.EdgeTTSEngine(TTSConfig(voice="zh-TW-HsiaoChenNeural"), tmp_path)

    audio = await engine.stream("穩啦")

    assert audio.path is None and audio.stream is not None
    assert await _read_all(audio.stream) == b"mp3-1mp3-2"
    assert list(tmp_path.iterdir()) == []
    assert _FakeCommunicate.created[-1]["connector"] is not None


class _StreamingTTS:
    def __init__(self) -> None:
        self.streams: list[AudioStream] = []

    async def synthesize(self, *args, **kwargs):  # pragma: no cover - must not be used
        raise AssertionError("the queue should stream when it can")

    async def stream(self, text, voice_style="default", rate_multiplier=1.0):
        stream = AudioStream()
        await stream.start(_chunks(b"x"), first_chunk_timeout=10)
        self.streams.append(stream)
        return AudioResult(None, None, None, "mp3", stream=stream)

    async def shutdown(self) -> None:
        return None


class _Player:
    def __init__(self) -> None:
        self.played: list[AudioResult] = []

    async def play(self, audio: AudioResult) -> None:
        self.played.append(audio)

    async def stop(self) -> None:
        return None


@pytest.mark.asyncio
async def test_queue_prefers_streaming_and_releases_the_stream() -> None:
    tts, player, done = _StreamingTTS(), _Player(), []
    queue = SpeechQueue(tts, player, lambda *_: None, on_done=done.append)  # type: ignore[arg-type]

    await queue.enqueue("穩啦")
    await asyncio.wait_for(queue.wait_idle(), 10)

    assert [job.state for job in done] == [JobState.DONE]
    assert player.played[0].stream is tts.streams[0]
    assert tts.streams[0].read() == b"x" and tts.streams[0].read() == b""
    await queue.shutdown()


@pytest.mark.asyncio
async def test_player_pipes_a_stream_into_ffmpeg_as_mp3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(
        "silenttalk.discord_playback.OpusSource",
        lambda *args, **kwargs: calls.append((args, kwargs)) or type("Source", (), {"cleanup": lambda self: None})(),
    )

    class Voice:
        def play(self, source, *, after) -> None:
            after(None)

        def is_playing(self) -> bool:
            return False

    class Client:
        def active_voice(self):
            return Voice()

        async def wait_until_voice_ready(self) -> None:
            return None

    stream = AudioStream()
    audio = AudioResult(
        None, None, None, "mp3", ffmpeg_filter="aecho=0.8:0.65:28:0.22", stream=stream
    )
    await DiscordAudioPlayer(Client(), AudioConfig()).play(audio)  # type: ignore[arg-type]

    args, kwargs = calls[0]
    assert args == (audio,)
    assert args[0].stream is stream
    assert "aecho=" in args[0].ffmpeg_filter
    assert kwargs["executable"] == AudioConfig().ffmpeg_path
