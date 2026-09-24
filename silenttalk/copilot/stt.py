from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sherpa_onnx

_LOG = logging.getLogger(__name__)

TurnCallback = Callable[[int, str, str], None]
ErrorCallback = Callable[[str], None]


@dataclass(slots=True)
class _SpeakerStream:
    speaker_name: str
    stream: object
    started_at: float
    last_packet_at: float


class StreamingTranscriber:
    """Discord PCM -> per-speaker streaming Paraformer transcripts."""

    def __init__(
        self,
        model_dir: Path,
        on_turn: TurnCallback,
        on_error: ErrorCallback,
        *,
        endpoint_silence_ms: int = 650,
        max_utterance_seconds: float = 25.0,
    ) -> None:
        self._model_dir = model_dir
        self._on_turn = on_turn
        self._on_error = on_error
        self._endpoint_seconds = max(0.35, endpoint_silence_ms / 1000.0)
        self._max_utterance_seconds = max(5.0, max_utterance_seconds)
        self._packets: queue.Queue[tuple[int, str, bytes, float] | None] = (
            queue.Queue(maxsize=4096)
        )
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
            recognizer = self._create_recognizer()
        except Exception as exc:
            self._startup_error = exc
            self._ready.set()
            return

        streams: dict[int, _SpeakerStream] = {}
        self._ready.set()
        _LOG.info("copilot_stt_ready")

        try:
            while not self._stop.is_set():
                try:
                    item = self._packets.get(timeout=0.05)
                except queue.Empty:
                    item = None

                if item is not None:
                    speaker_id, speaker_name, pcm, received_at = item
                    state = streams.get(speaker_id)
                    if state is None:
                        state = _SpeakerStream(
                            speaker_name=speaker_name,
                            stream=recognizer.create_stream(),
                            started_at=received_at,
                            last_packet_at=received_at,
                        )
                        streams[speaker_id] = state
                    else:
                        state.speaker_name = speaker_name
                        state.last_packet_at = received_at

                    self._accept_pcm(recognizer, state.stream, pcm)

                now = time.monotonic()
                due = [
                    speaker_id
                    for speaker_id, state in streams.items()
                    if (
                        now - state.last_packet_at >= self._endpoint_seconds
                        or now - state.started_at >= self._max_utterance_seconds
                    )
                ]
                for speaker_id in due:
                    state = streams.pop(speaker_id)
                    self._finalize(recognizer, speaker_id, state)
        except Exception as exc:
            _LOG.exception("copilot_stt_worker_failed")
            self._on_error(f"Copilot STT 發生錯誤：{type(exc).__name__}")
        finally:
            for speaker_id, state in list(streams.items()):
                try:
                    self._finalize(recognizer, speaker_id, state)
                except Exception:
                    _LOG.debug("copilot_stt_final_flush_failed", exc_info=True)

    def _create_recognizer(self) -> sherpa_onnx.OnlineRecognizer:
        encoder = self._model_dir / "encoder.int8.onnx"
        decoder = self._model_dir / "decoder.int8.onnx"
        tokens = self._model_dir / "tokens.txt"
        missing = [path for path in (encoder, decoder, tokens) if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                "缺少 STT 模型：" + ", ".join(path.name for path in missing)
            )

        return sherpa_onnx.OnlineRecognizer.from_paraformer(
            tokens=str(tokens),
            encoder=str(encoder),
            decoder=str(decoder),
            num_threads=1,
            sample_rate=16000,
            feature_dim=80,
            enable_endpoint_detection=False,
            decoding_method="greedy_search",
            provider="cpu",
        )

    @staticmethod
    def _accept_pcm(
        recognizer: sherpa_onnx.OnlineRecognizer,
        stream: object,
        pcm: bytes,
    ) -> None:
        samples = np.frombuffer(pcm, dtype="<i2")
        usable = len(samples) - (len(samples) % 2)
        if usable <= 0:
            return
        stereo = samples[:usable].reshape(-1, 2).astype(np.float32)
        mono = stereo.mean(axis=1) / 32768.0
        stream.accept_waveform(48000, mono)
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)

    def _finalize(
        self,
        recognizer: sherpa_onnx.OnlineRecognizer,
        speaker_id: int,
        state: _SpeakerStream,
    ) -> None:
        tail = np.zeros(int(0.20 * 48000), dtype=np.float32)
        state.stream.accept_waveform(48000, tail)
        state.stream.input_finished()
        while recognizer.is_ready(state.stream):
            recognizer.decode_stream(state.stream)

        text = str(recognizer.get_result(state.stream)).strip()
        text = " ".join(text.split())
        if not text:
            return

        _LOG.info(
            "copilot_turn_final speaker_id=%s char_count=%d",
            speaker_id,
            len(text),
        )
        self._on_turn(speaker_id, state.speaker_name, text)
