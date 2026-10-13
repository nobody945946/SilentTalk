from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sherpa_onnx

from silenttalk.copilot.script import to_taiwan_traditional
from silenttalk.copilot.stt_worker import (
    ClosedCallback,
    ErrorCallback,
    OpenSpeaker,
    SpeakerTranscriber,
    TurnCallback,
)

_LOG = logging.getLogger(__name__)

# Streaming Paraformer emits tokens once per ~0.6 s chunk; a shorter zero tail
# never flushes the last chunk and drops the final 1-3 characters.
_TAIL_PADDING_SECONDS = 0.66


@dataclass(slots=True)
class _SpeakerStream(OpenSpeaker):
    stream: object
    started_at: float


class StreamingTranscriber(SpeakerTranscriber[_SpeakerStream]):
    """Discord PCM -> per-speaker streaming Paraformer transcripts."""

    ENGINE = "paraformer"

    def __init__(
        self,
        model_dir: Path,
        on_turn: TurnCallback,
        on_error: ErrorCallback,
        *,
        endpoint_silence_ms: int = 650,
        max_utterance_seconds: float = 25.0,
        on_closed: ClosedCallback | None = None,
    ) -> None:
        super().__init__(
            on_turn,
            on_error,
            endpoint_silence_ms=endpoint_silence_ms,
            on_closed=on_closed,
        )
        self._model_dir = model_dir
        self._max_utterance_seconds = max(5.0, max_utterance_seconds)
        self._recognizer: sherpa_onnx.OnlineRecognizer | None = None

    def _load(self) -> None:
        self._recognizer = self._create_recognizer()

    def _open(self, speaker_name: str, received_at: float) -> _SpeakerStream:
        return _SpeakerStream(
            speaker_name=speaker_name,
            last_packet_at=received_at,
            stream=self._recognizer.create_stream(),
            started_at=received_at,
        )

    def _accept(
        self, speaker_id: int, state: _SpeakerStream, pcm: bytes, received_at: float
    ) -> None:
        recognizer = self._recognizer
        self._accept_pcm(recognizer, state.stream, pcm)
        if recognizer.is_endpoint(state.stream):
            text = str(recognizer.get_result(state.stream))
            recognizer.reset(state.stream)
            state.started_at = received_at
            self._emit(speaker_id, state.speaker_name, text)

    def _flush_at(self, state: _SpeakerStream) -> float:
        # Silence since the last packet, or an utterance running too long.
        return min(
            state.last_packet_at + self._endpoint_seconds,
            state.started_at + self._max_utterance_seconds,
        )

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
            # Open-mic users keep sending packets through background noise, so
            # packet gaps alone never end their turn. These rules count time
            # since the last decoded token (noise does not reset them).
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=0.8,
            rule3_min_utterance_length=20.0,
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

    def _finalize(self, speaker_id: int, state: _SpeakerStream) -> None:
        recognizer = self._recognizer
        tail = np.zeros(int(_TAIL_PADDING_SECONDS * 48000), dtype=np.float32)
        state.stream.accept_waveform(48000, tail)
        state.stream.input_finished()
        while recognizer.is_ready(state.stream):
            recognizer.decode_stream(state.stream)

        self._emit(speaker_id, state.speaker_name, str(recognizer.get_result(state.stream)))

    def _emit(self, speaker_id: int, speaker_name: str, raw_text: str) -> None:
        text = to_taiwan_traditional(" ".join(raw_text.split()))
        if not text:
            return

        _LOG.info(
            "copilot_turn_final speaker_id=%s char_count=%d",
            speaker_id,
            len(text),
        )
        self._on_turn(speaker_id, speaker_name, text)
