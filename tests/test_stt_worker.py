"""The STT worker sleeps until something happens: a packet, stop(), or the
soonest open speaker's flush deadline. No periodic wakeups."""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from silenttalk.copilot.smoke import TurnCollector, transcribe_pcm
from silenttalk.copilot.stt import StreamingTranscriber, _SpeakerStream
from silenttalk.copilot.stt_worker import OpenSpeaker, SpeakerTranscriber

FRAME = b"\x00\x00" * 1920  # 20 ms of 48 kHz stereo s16le
# Windows fires a timer up to one clock tick (15.6 ms) before its time
# (asyncio's clock resolution, the kernel's timer tick): lower bounds allow it.
TICK = 0.02
# Its monotonic clock steps by that tick too, so the worker can read the very
# time the packet was stamped: then the wait is the whole silence, plus the
# rounding of `stamp + silence - stamp` (0.4000000000000057 on CI).
ROUNDING = 1e-9


class _CountingQueue(queue.Queue):
    """Records the timeout of every get(): each one is a wakeup of the worker."""

    def __init__(self) -> None:
        super().__init__(maxsize=4096)
        self.timeouts: list[float | None] = []
        self.called = threading.Condition()

    def get(self, block: bool = True, timeout: float | None = None):  # type: ignore[override]
        with self.called:
            self.timeouts.append(timeout)
            self.called.notify_all()
        return super().get(block, timeout)

    def wait_gets(self, count: int) -> None:
        with self.called:
            assert self.called.wait_for(lambda: len(self.timeouts) >= count, 2.0)


class _Engine(SpeakerTranscriber[OpenSpeaker]):
    ENGINE = "fake"

    def __init__(self, *, endpoint_silence_ms: int = 400) -> None:
        self.events: list[tuple[str, int, float]] = []
        self.closed = threading.Event()
        self.entered = threading.Event()
        self.gate: threading.Event | None = None

        def on_closed(speaker_id: int) -> None:
            self.events.append(("closed", speaker_id, time.monotonic()))
            self.closed.set()

        super().__init__(
            lambda speaker_id, _name, _text: self.events.append(
                ("turn", speaker_id, time.monotonic())
            ),
            lambda _message: None,
            endpoint_silence_ms=endpoint_silence_ms,
            on_closed=on_closed,
        )
        self.queue = _CountingQueue()
        self._packets = self.queue

    def _load(self) -> None:
        pass

    def _open(self, speaker_name: str, received_at: float) -> OpenSpeaker:
        return OpenSpeaker(speaker_name, received_at)

    def _accept(
        self, speaker_id: int, state: OpenSpeaker, pcm: bytes, received_at: float
    ) -> None:
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(5.0)

    def _flush_at(self, state: OpenSpeaker) -> float:
        return state.last_packet_at + self._endpoint_seconds

    def _finalize(self, speaker_id: int, state: OpenSpeaker) -> None:
        self._on_turn(speaker_id, state.speaker_name, "done")

    def closes(self) -> list[tuple[int, float]]:
        return [(sid, at) for kind, sid, at in self.events if kind == "closed"]


def test_idle_worker_blocks_on_the_queue_and_stop_wakes_it() -> None:
    engine = _Engine()
    engine.start()
    thread = engine._thread
    time.sleep(0.3)  # old loop: six 50 ms wakeups by now
    assert engine.queue.timeouts == [None]

    started = time.monotonic()
    engine.stop()
    assert time.monotonic() - started < 0.5
    assert thread is not None and not thread.is_alive()
    assert engine.queue.timeouts == [None]  # the stop sentinel answered that get


def test_a_speaker_is_flushed_exactly_at_its_silence_deadline() -> None:
    engine = _Engine(endpoint_silence_ms=400)
    engine.start()
    try:
        pushed = time.monotonic()
        engine.push_pcm(7, "Alice", FRAME)
        assert engine.closed.wait(2.0)
        engine.queue.wait_gets(3)
    finally:
        engine.stop()

    [(speaker_id, closed_at)] = engine.closes()
    assert speaker_id == 7
    assert 0.4 - TICK <= closed_at - pushed < 0.4 + 0.3
    # Block for a packet; sleep until the deadline; block again once closed.
    first, until_flush, after = engine.queue.timeouts
    assert first is None and after is None
    assert until_flush is not None and 0.0 < until_flush <= 0.4 + ROUNDING
    assert [kind for kind, _, _ in engine.events] == ["turn", "closed"]


def test_the_soonest_open_speaker_sets_the_wakeup() -> None:
    engine = _Engine(endpoint_silence_ms=400)
    engine.start()
    try:
        first_at = time.monotonic()
        engine.push_pcm(1, "A", FRAME)
        engine.queue.wait_gets(2)
        time.sleep(0.15)
        second_at = time.monotonic()
        engine.push_pcm(2, "B", FRAME)
        engine.queue.wait_gets(5)
        assert engine.closed.wait(2.0)
    finally:
        engine.stop()

    (a, a_at), (b, b_at) = engine.closes()
    assert (a, b) == (1, 2)
    assert 0.4 - TICK <= a_at - first_at < 0.4 + 0.3
    assert 0.4 - TICK <= b_at - second_at < 0.4 + 0.3
    # packet A, packet B, A's deadline, B's deadline, then idle: five gets.
    timeouts = engine.queue.timeouts
    assert len(timeouts) == 5
    assert timeouts[0] is None and timeouts[-1] is None
    assert all(t is not None and 0.0 <= t <= 0.4 + ROUNDING for t in timeouts[1:-1])


def test_stop_ends_the_worker_even_when_the_queue_is_full() -> None:
    engine = _Engine()
    engine.gate = threading.Event()
    engine.start()
    thread = engine._thread
    engine.push_pcm(1, "A", FRAME)
    assert engine.entered.wait(2.0)  # the worker holds the first packet
    for _ in range(4096):
        engine.push_pcm(1, "A", FRAME)
    assert engine.queue.full()

    stopper = threading.Thread(target=engine.stop)
    stopper.start()
    assert engine._stop.wait(2.0)  # and there is no room for the sentinel
    engine.gate.set()
    stopper.join(2.0)
    assert not stopper.is_alive()
    assert thread is not None and not thread.is_alive()
    assert [sid for sid, _ in engine.closes()] == [1]  # flushed on the way out


class _FakeOnlineRecognizer:
    """Never finds an endpoint: only the silence flush ends the turn."""

    def create_stream(self) -> SimpleNamespace:
        stream = SimpleNamespace(samples=0, finished=False)
        stream.accept_waveform = lambda _rate, samples: setattr(
            stream, "samples", stream.samples + len(samples)
        )
        stream.input_finished = lambda: setattr(stream, "finished", True)
        return stream

    def is_ready(self, _stream: SimpleNamespace) -> bool:
        return False

    def is_endpoint(self, _stream: SimpleNamespace) -> bool:
        return False

    def get_result(self, stream: SimpleNamespace) -> str:
        return "这个 boss 血量剩一半了" if stream.finished else ""


def test_streaming_transcriber_flushes_after_endpoint_silence(tmp_path: Path) -> None:
    turns: list[tuple[int, str, str, float]] = []
    closed = threading.Event()
    transcriber = StreamingTranscriber(
        tmp_path,
        lambda sid, name, text: turns.append((sid, name, text, time.monotonic())),
        lambda _message: None,
        endpoint_silence_ms=650,
        on_closed=lambda _sid: closed.set(),
    )
    transcriber._create_recognizer = _FakeOnlineRecognizer  # type: ignore[method-assign]
    transcriber.start()
    try:
        for _ in range(20):
            transcriber.push_pcm(7, "Alice", FRAME)
        last_packet = time.monotonic()
        assert closed.wait(3.0)
    finally:
        transcriber.stop()

    assert [(t[0], t[1], t[2]) for t in turns] == [(7, "Alice", "這個 boss 血量剩一半了")]
    assert turns[0][3] - last_packet >= 0.6 - TICK


def test_streaming_flush_deadline_is_silence_or_utterance_length(tmp_path: Path) -> None:
    transcriber = StreamingTranscriber(
        tmp_path,
        lambda *_: None,
        lambda _message: None,
        endpoint_silence_ms=650,
        max_utterance_seconds=5.0,
    )
    state = _SpeakerStream(
        speaker_name="A", last_packet_at=100.0, stream=None, started_at=96.0
    )
    assert transcriber._flush_at(state) == 100.0 + 0.65
    state.started_at = 95.5
    assert transcriber._flush_at(state) == 95.5 + 5.0


def test_turn_collector_returns_when_the_stream_closes() -> None:
    engine = _Engine(endpoint_silence_ms=400)
    collector = TurnCollector()
    engine._on_turn = collector.on_turn
    engine._on_closed = collector.on_closed
    engine.start()
    try:
        started = time.monotonic()
        heard = transcribe_pcm(engine, collector, FRAME * 10)  # type: ignore[arg-type]
        elapsed = time.monotonic() - started
    finally:
        engine.stop()

    assert heard == "done"
    # The flush itself (0.4 s), not the flush plus a fixed second.
    assert 0.4 - TICK <= elapsed < 0.4 + 0.5


def test_turn_collector_gives_a_never_closing_stream_its_grace() -> None:
    collector = TurnCollector()
    collector.TRAILING_TURN_SECONDS = 0.2
    collector.reset()
    collector.on_turn(0, "local", "前半")
    started = time.monotonic()
    assert collector.wait(5.0) == "前半"
    assert 0.2 - TICK <= time.monotonic() - started < 1.0
