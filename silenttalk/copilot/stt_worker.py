"""The worker both STT engines share: Discord PCM packets in, one thread,
per-speaker streams closed at their flush deadline.

The thread sleeps in the packet queue until the next thing happens: a
packet, the stop sentinel, or the soonest open speaker's flush deadline
(their silence, or an engine's length limit). With nobody open it waits for
the next packet with no timeout; nothing wakes it to look again.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

_LOG = logging.getLogger(__name__)

TurnCallback = Callable[[int, str, str], None]
ErrorCallback = Callable[[str], None]
# A speaker's stream was closed (their flush, or stop()) after its last turn.
ClosedCallback = Callable[[int], None]

Packet = tuple[int, str, bytes, float]


@dataclass(slots=True)
class OpenSpeaker:
    """A speaker whose stream is open; engines add their decoder state."""

    speaker_name: str
    last_packet_at: float


SpeakerT = TypeVar("SpeakerT", bound=OpenSpeaker)


class SpeakerTranscriber(Generic[SpeakerT]):
    """Owns the packet queue, the worker thread and when each speaker's
    stream is closed. An engine loads its models (`_load`), opens a speaker
    (`_open`), feeds a packet (`_accept`, emitting turns its endpointing
    finds), says when an open speaker is due (`_flush_at`) and closes one
    (`_finalize`, emitting what is left)."""

    ENGINE = ""

    def __init__(
        self,
        on_turn: TurnCallback,
        on_error: ErrorCallback,
        *,
        endpoint_silence_ms: int = 650,
        on_closed: ClosedCallback | None = None,
    ) -> None:
        self._on_turn = on_turn
        self._on_error = on_error
        self._on_closed = on_closed
        self._endpoint_seconds = max(0.35, endpoint_silence_ms / 1000.0)
        # None is the stop sentinel.
        self._packets: queue.Queue[Packet | None] = queue.Queue(maxsize=4096)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._startup_error: Exception | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._ready.clear()
        self._startup_error = None
        self._thread = threading.Thread(
            target=self._run,
            name="copilot-stt",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=30):
            raise RuntimeError("Copilot STT 載入逾時。")
        if self._startup_error is not None:
            raise RuntimeError(f"Copilot STT 載入失敗：{self._startup_error}")

    def stop(self) -> None:
        self._stop.set()
        try:
            self._packets.put_nowait(None)
        except queue.Full:
            # The worker is not blocked on an empty queue: it sees _stop
            # before it could take the last packet.
            pass
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None

    def push_pcm(self, speaker_id: int, speaker_name: str, pcm: bytes) -> None:
        if not pcm or self._stop.is_set():
            return
        item = (speaker_id, speaker_name, bytes(pcm), time.monotonic())
        try:
            self._packets.put_nowait(item)
        except queue.Full:
            _LOG.warning("copilot_stt_packet_dropped queue_full=true")

    def _run(self) -> None:
        try:
            self._load()
        except Exception as exc:  # noqa: BLE001 - start() reports any load failure
            self._startup_error = exc
            self._ready.set()
            return

        speakers: dict[int, SpeakerT] = {}
        self._ready.set()
        _LOG.info("copilot_stt_ready engine=%s", self.ENGINE)

        try:
            while not self._stop.is_set():
                item = self._next_packet(speakers)
                if item is not None:
                    speaker_id, speaker_name, pcm, received_at = item
                    state = speakers.get(speaker_id)
                    if state is None:
                        state = self._open(speaker_name, received_at)
                        speakers[speaker_id] = state
                    else:
                        state.speaker_name = speaker_name
                        state.last_packet_at = received_at
                    self._accept(speaker_id, state, pcm, received_at)

                now = time.monotonic()
                due = [
                    speaker_id
                    for speaker_id, state in speakers.items()
                    if self._flush_at(state) <= now
                ]
                for speaker_id in due:
                    self._close(speaker_id, speakers.pop(speaker_id))
        except Exception as exc:  # noqa: BLE001 - reported to the UI, then flushed
            _LOG.exception("copilot_stt_worker_failed")
            self._on_error(f"Copilot STT 發生錯誤：{type(exc).__name__}")
        finally:
            for speaker_id, state in list(speakers.items()):
                try:
                    self._close(speaker_id, state)
                except Exception:  # noqa: BLE001 - best effort on the way out
                    _LOG.debug("copilot_stt_final_flush_failed", exc_info=True)

    def _next_packet(self, speakers: dict[int, SpeakerT]) -> Packet | None:
        """The next packet, or None for the stop sentinel and once the
        soonest open speaker's flush deadline has come."""
        flush_at = min(
            (self._flush_at(state) for state in speakers.values()), default=None
        )
        timeout = None if flush_at is None else max(0.0, flush_at - time.monotonic())
        try:
            return self._packets.get(timeout=timeout)
        except queue.Empty:
            return None

    def _close(self, speaker_id: int, state: SpeakerT) -> None:
        self._finalize(speaker_id, state)
        if self._on_closed is not None:
            self._on_closed(speaker_id)

    # ---- engine ------------------------------------------------------------

    def _load(self) -> None:
        raise NotImplementedError

    def _open(self, speaker_name: str, received_at: float) -> SpeakerT:
        raise NotImplementedError

    def _accept(
        self, speaker_id: int, state: SpeakerT, pcm: bytes, received_at: float
    ) -> None:
        raise NotImplementedError

    def _flush_at(self, state: SpeakerT) -> float:
        """Monotonic time at which this open speaker's stream is closed."""
        raise NotImplementedError

    def _finalize(self, speaker_id: int, state: SpeakerT) -> None:
        raise NotImplementedError
