from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from silenttalk.copilot import stt_offline
from silenttalk.copilot.stt_offline import (
    Downsampler,
    OfflineTranscriber,
    has_speech_text,
    pad_segment,
    pcm_to_mono,
)

FRAME_BYTES = 3840  # 20 ms of 48 kHz stereo s16le, like Discord


def _tone_pcm(seconds: float, hz: float = 440.0) -> bytes:
    t = np.arange(int(seconds * 48000)) / 48000
    mono = (np.sin(2 * np.pi * hz * t) * 8000).astype("<i2")
    return np.repeat(mono, 2).tobytes()


def test_pcm_to_mono_averages_channels_and_drops_odd_sample() -> None:
    pcm = np.array([1000, 3000, -2000, 0, 7], dtype="<i2").tobytes()
    mono = pcm_to_mono(pcm)
    assert mono.dtype == np.float32
    np.testing.assert_allclose(mono, [2000 / 32768, -1000 / 32768])
    assert len(pcm_to_mono(b"")) == 0


def test_downsampler_is_streaming_consistent() -> None:
    samples = pcm_to_mono(_tone_pcm(0.5))
    whole = Downsampler().process(samples)
    chunked = Downsampler()
    parts = [chunked.process(samples[i : i + 961]) for i in range(0, len(samples), 961)]
    assert len(whole) == len(samples) // 3
    np.testing.assert_allclose(np.concatenate(parts), whole, atol=1e-6)


def test_downsampler_keeps_speech_band_and_removes_aliasing_band() -> None:
    def gain(hz: float) -> float:
        x = pcm_to_mono(_tone_pcm(0.5, hz))
        y = Downsampler().process(x)[200:]
        return float(np.sqrt(np.mean(y**2)) / np.sqrt(np.mean(x**2)))

    assert gain(1000.0) > 0.95
    assert gain(12000.0) < 0.01


def test_pad_segment_and_speech_text_filter() -> None:
    padded = pad_segment(np.ones(10, dtype=np.float32), seconds=0.01)
    assert len(padded) == 160 + 10 + 160
    assert padded[:160].sum() == 0 and padded[-160:].sum() == 0
    assert not has_speech_text("")
    assert not has_speech_text("。？")
    assert has_speech_text("好。")


class _FakeVad:
    """Holds all audio until flush(); mimics a speaker who never pauses long."""

    def __init__(self) -> None:
        self.buffer: list[np.ndarray] = []
        self.segments: list[np.ndarray] = []
        self.flushes = 0

    def accept_waveform(self, samples: np.ndarray) -> None:
        self.buffer.append(np.asarray(samples, dtype=np.float32))

    def flush(self) -> None:
        self.flushes += 1
        if self.buffer:
            self.segments.append(np.concatenate(self.buffer))
            self.buffer.clear()

    def empty(self) -> bool:
        return not self.segments

    @property
    def front(self) -> SimpleNamespace:
        return SimpleNamespace(samples=self.segments[0])

    def pop(self) -> None:
        self.segments.pop(0)

    def reset(self) -> None:
        self.buffer.clear()
        self.segments.clear()


class _FakeRecognizer:
    def __init__(self) -> None:
        self.decoded_lengths: list[int] = []

    def create_stream(self) -> SimpleNamespace:
        stream = SimpleNamespace(samples=None, result=SimpleNamespace(text=""))
        stream.accept_waveform = lambda _rate, samples: setattr(
            stream, "samples", samples
        )
        return stream

    def decode_stream(self, stream: SimpleNamespace) -> None:
        self.decoded_lengths.append(len(stream.samples))
        stream.result.text = "这个 boss 血量剩一半了"


def test_pending_audio_is_flushed_after_endpoint_silence(tmp_path: Path) -> None:
    turns: list[tuple[int, str, str, float]] = []
    got_turn = threading.Event()

    def on_turn(speaker_id: int, name: str, text: str) -> None:
        turns.append((speaker_id, name, text, time.monotonic()))
        got_turn.set()

    transcriber = OfflineTranscriber(
        tmp_path, on_turn, lambda _message: None, endpoint_silence_ms=650
    )
    recognizer = _FakeRecognizer()
    vad = _FakeVad()
    transcriber._create_recognizer = lambda: recognizer  # type: ignore[method-assign]
    transcriber._create_vad_config = lambda: None  # type: ignore[method-assign]
    transcriber._new_vad = lambda: vad  # type: ignore[method-assign]

    transcriber.start()
    try:
        pcm = _tone_pcm(0.4)
        for start in range(0, len(pcm), FRAME_BYTES):
            transcriber.push_pcm(7, "Alice", pcm[start : start + FRAME_BYTES])
        last_packet = time.monotonic()
        assert got_turn.wait(3.0)
    finally:
        transcriber.stop()

    assert vad.flushes == 1
    assert [(t[0], t[1], t[2]) for t in turns] == [
        (7, "Alice", "這個 boss 血量剩一半了")
    ]
    assert turns[0][3] - last_packet >= 0.6
    padding = 2 * int(stt_offline._SEGMENT_PADDING_SECONDS * stt_offline.SAMPLE_RATE)
    assert recognizer.decoded_lengths == [int(0.4 * 16000) + padding]
