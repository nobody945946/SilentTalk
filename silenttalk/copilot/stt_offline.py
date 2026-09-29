"""Discord PCM -> per-speaker Silero VAD segments -> offline SenseVoice.

Drop-in alternative to ``stt.StreamingTranscriber`` (same constructor and
start/stop/push_pcm), selected by ``config.toml`` ``copilot.stt_engine``.
The VAD cuts each speaker's audio into utterances; each finished utterance is
decoded in one pass, so there is no streaming tail to flush and sentence
endings are not dropped.
"""

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

from silenttalk.copilot.script import to_taiwan_traditional

_LOG = logging.getLogger(__name__)

TurnCallback = Callable[[int, str, str], None]
ErrorCallback = Callable[[str], None]

INPUT_RATE = 48000
SAMPLE_RATE = 16000
_DECIMATION = INPUT_RATE // SAMPLE_RATE

# Silero VAD (sherpa-onnx). 0.5 s of silence closes a segment, which also ends
# turns for open-mic speakers whose packets never stop.
_VAD_THRESHOLD = 0.5
_VAD_MIN_SILENCE_SECONDS = 0.5
_VAD_MIN_SPEECH_SECONDS = 0.25
_VAD_MAX_SPEECH_SECONDS = 20.0
_VAD_WINDOW_SIZE = 512
_VAD_BUFFER_SECONDS = 30.0
# Idle speakers hand their VAD back for reuse instead of reloading the model.
_VAD_POOL_SIZE = 8

# "auto" vs forced "zh" measured the same within noise (2026-09-26 sweep over
# 5 perturbed copies of the stt_eval set); "auto" keeps English words usable.
_LANGUAGE = "auto"
# Zeros added before and after each VAD segment before decoding. Silero cuts
# close to the speech edges; 0.25 s of silence lowered the average CER from
# 8.1% to 7.5% in the same sweep (0.1 s did not help).
_SEGMENT_PADDING_SECONDS = 0.25


def _lowpass_taps(
    num_taps: int = 63, cutoff_hz: float = 7000.0, rate: int = INPUT_RATE
) -> np.ndarray:
    """Blackman-windowed sinc low-pass with unity DC gain."""
    n = np.arange(num_taps, dtype=np.float64) - (num_taps - 1) / 2
    fc = cutoff_hz / rate
    taps = np.sinc(2 * fc * n) * np.blackman(num_taps)
    return (taps / taps.sum()).astype(np.float32)


_TAPS = _lowpass_taps()


def pcm_to_mono(pcm: bytes) -> np.ndarray:
    """48 kHz stereo s16le -> mono float32 in [-1, 1). A trailing odd sample is dropped."""
    samples = np.frombuffer(pcm, dtype="<i2")
    usable = len(samples) - (len(samples) % 2)
    if usable <= 0:
        return np.zeros(0, dtype=np.float32)
    stereo = samples[:usable].reshape(-1, 2).astype(np.float32)
    return stereo.mean(axis=1) / 32768.0


class Downsampler:
    """Streaming 48 kHz -> 16 kHz: FIR low-pass below 8 kHz, then keep every 3rd sample.

    Keeps filter history and decimation phase between calls, so feeding 20 ms
    Discord frames one at a time gives the same output as one big array.
    """

    def __init__(self) -> None:
        self._history = np.zeros(len(_TAPS) - 1, dtype=np.float32)
        self._phase = 0

    def process(self, samples: np.ndarray) -> np.ndarray:
        count = len(samples)
        if count == 0:
            return np.zeros(0, dtype=np.float32)
        buffer = np.concatenate((self._history, samples.astype(np.float32)))
        filtered = np.convolve(buffer, _TAPS, mode="valid")  # len == count
        out = filtered[self._phase :: _DECIMATION]
        self._phase = (self._phase - count) % _DECIMATION
        self._history = buffer[-(len(_TAPS) - 1) :]
        return out.astype(np.float32, copy=False)


def audio_stats(samples: np.ndarray) -> tuple[float, float]:
    """Level (dBFS, RMS) and median spectral flatness of 16 kHz audio.

    Flatness is the geometric over the arithmetic mean of the power spectrum
    per 32 ms frame, 300-3400 Hz: voice stays well below 0.3, white noise
    is ~0.56 (e.g. frames that were never decrypted). Numbers only, for the
    log.
    """
    if len(samples) == 0:
        return -120.0, 1.0
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    level = 20.0 * float(np.log10(max(rms, 1e-6)))
    frame = 512
    count = len(samples) // frame
    if count == 0:
        return level, 1.0
    frames = samples[: count * frame].reshape(count, frame) * np.hanning(frame)
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2 + 1e-12
    band = power[:, int(300 * frame / SAMPLE_RATE) : int(3400 * frame / SAMPLE_RATE)]
    flatness = np.exp(np.mean(np.log(band), axis=1)) / np.mean(band, axis=1)
    return level, float(np.median(flatness))


def pad_segment(
    samples: np.ndarray, seconds: float = _SEGMENT_PADDING_SECONDS
) -> np.ndarray:
    """Surround a VAD segment with ``seconds`` of silence on both sides."""
    pad = np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)
    return np.concatenate((pad, samples.astype(np.float32, copy=False), pad))


def has_speech_text(text: str) -> bool:
    """False for empty or punctuation-only results (SenseVoice emits "。" on noise)."""
    return any(ch.isalnum() for ch in text)


@dataclass(slots=True)
class _SpeakerState:
    speaker_name: str
    vad: sherpa_onnx.VoiceActivityDetector
    resampler: Downsampler
    last_packet_at: float


class OfflineTranscriber:
    """Discord PCM -> per-speaker Silero VAD -> offline SenseVoice transcripts.

    ``model_dir`` holds SenseVoice ``model.int8.onnx`` + ``tokens.txt``; the VAD
    model is read from ``vad_dir`` (default: ``model_dir.parent / "vad"``).
    """

    def __init__(
        self,
        model_dir: Path,
        on_turn: TurnCallback,
        on_error: ErrorCallback,
        *,
        endpoint_silence_ms: int = 650,
        max_utterance_seconds: float = 25.0,
        vad_dir: Path | None = None,
    ) -> None:
        self._model_dir = model_dir
        self._vad_dir = vad_dir if vad_dir is not None else model_dir.parent / "vad"
        self._on_turn = on_turn
        self._on_error = on_error
        self._endpoint_seconds = max(0.35, endpoint_silence_ms / 1000.0)
        self._max_speech_seconds = max(
            5.0, min(_VAD_MAX_SPEECH_SECONDS, max_utterance_seconds)
        )
        self._packets: queue.Queue[tuple[int, str, bytes, float] | None] = queue.Queue(
            maxsize=4096
        )
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._startup_error: Exception | None = None
        self._vad_config: sherpa_onnx.VadModelConfig | None = None
        self._vad_pool: list[sherpa_onnx.VoiceActivityDetector] = []

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
            self._vad_config = self._create_vad_config()
            self._vad_pool = [self._new_vad()]
        except Exception as exc:
            self._startup_error = exc
            self._ready.set()
            return

        speakers: dict[int, _SpeakerState] = {}
        self._ready.set()
        _LOG.info("copilot_stt_ready engine=sensevoice")

        try:
            while not self._stop.is_set():
                try:
                    item = self._packets.get(timeout=0.05)
                except queue.Empty:
                    item = None

                if item is not None:
                    speaker_id, speaker_name, pcm, received_at = item
                    state = speakers.get(speaker_id)
                    if state is None:
                        state = _SpeakerState(
                            speaker_name=speaker_name,
                            vad=self._take_vad(),
                            resampler=Downsampler(),
                            last_packet_at=received_at,
                        )
                        speakers[speaker_id] = state
                    else:
                        state.speaker_name = speaker_name
                        state.last_packet_at = received_at

                    samples = state.resampler.process(pcm_to_mono(pcm))
                    if len(samples):
                        state.vad.accept_waveform(samples)
                    self._drain(recognizer, speaker_id, state)

                now = time.monotonic()
                due = [
                    speaker_id
                    for speaker_id, state in speakers.items()
                    if now - state.last_packet_at >= self._endpoint_seconds
                ]
                for speaker_id in due:
                    self._finalize(recognizer, speaker_id, speakers.pop(speaker_id))
        except Exception as exc:
            _LOG.exception("copilot_stt_worker_failed")
            self._on_error(f"Copilot STT 發生錯誤：{type(exc).__name__}")
        finally:
            for speaker_id, state in list(speakers.items()):
                try:
                    self._finalize(recognizer, speaker_id, state)
                except Exception:
                    _LOG.debug("copilot_stt_final_flush_failed", exc_info=True)

    def _create_recognizer(self) -> sherpa_onnx.OfflineRecognizer:
        model = self._model_dir / "model.int8.onnx"
        tokens = self._model_dir / "tokens.txt"
        vad = self._vad_dir / "silero_vad.onnx"
        missing = [path for path in (model, tokens, vad) if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                "缺少 STT 模型：" + ", ".join(path.name for path in missing)
            )

        return sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model),
            tokens=str(tokens),
            num_threads=1,
            sample_rate=SAMPLE_RATE,
            language=_LANGUAGE,
            use_itn=True,
            provider="cpu",
        )

    def _create_vad_config(self) -> sherpa_onnx.VadModelConfig:
        config = sherpa_onnx.VadModelConfig()
        config.sample_rate = SAMPLE_RATE
        config.num_threads = 1
        config.provider = "cpu"
        config.silero_vad.model = str(self._vad_dir / "silero_vad.onnx")
        config.silero_vad.threshold = _VAD_THRESHOLD
        config.silero_vad.min_silence_duration = _VAD_MIN_SILENCE_SECONDS
        config.silero_vad.min_speech_duration = _VAD_MIN_SPEECH_SECONDS
        config.silero_vad.max_speech_duration = self._max_speech_seconds
        config.silero_vad.window_size = _VAD_WINDOW_SIZE
        return config

    def _new_vad(self) -> sherpa_onnx.VoiceActivityDetector:
        return sherpa_onnx.VoiceActivityDetector(
            self._vad_config, buffer_size_in_seconds=_VAD_BUFFER_SECONDS
        )

    def _take_vad(self) -> sherpa_onnx.VoiceActivityDetector:
        return self._vad_pool.pop() if self._vad_pool else self._new_vad()

    def _finalize(
        self,
        recognizer: sherpa_onnx.OfflineRecognizer,
        speaker_id: int,
        state: _SpeakerState,
    ) -> None:
        state.vad.flush()
        self._drain(recognizer, speaker_id, state)
        state.vad.reset()
        if len(self._vad_pool) < _VAD_POOL_SIZE:
            self._vad_pool.append(state.vad)

    def _drain(
        self,
        recognizer: sherpa_onnx.OfflineRecognizer,
        speaker_id: int,
        state: _SpeakerState,
    ) -> None:
        while not state.vad.empty():
            samples = np.asarray(state.vad.front.samples, dtype=np.float32)
            state.vad.pop()
            started = time.perf_counter()
            stream = recognizer.create_stream()
            stream.accept_waveform(SAMPLE_RATE, pad_segment(samples))
            recognizer.decode_stream(stream)
            # INFO, content-free: how a speaker's audio was cut up tells a
            # VAD that splits sentences from a recogniser that mishears.
            level, flatness = audio_stats(samples)
            _LOG.info(
                "copilot_stt_segment speaker_id=%s audio_ms=%d decode_ms=%d "
                "level_dbfs=%.1f flatness=%.2f",
                speaker_id,
                len(samples) * 1000 // SAMPLE_RATE,
                int((time.perf_counter() - started) * 1000),
                level,
                flatness,
            )
            if not self._emit(speaker_id, state.speaker_name, stream.result.text):
                # The VAD heard speech but nothing came out: the "said it a
                # bit fast or unclear and it failed" case. Length only.
                _LOG.info(
                    "copilot_stt_empty speaker_id=%s audio_ms=%d",
                    speaker_id,
                    len(samples) * 1000 // SAMPLE_RATE,
                )

    def _emit(self, speaker_id: int, speaker_name: str, raw_text: str) -> bool:
        text = to_taiwan_traditional(" ".join(raw_text.split()))
        if not has_speech_text(text):
            return False

        _LOG.info(
            "copilot_turn_final speaker_id=%s char_count=%d",
            speaker_id,
            len(text),
        )
        self._on_turn(speaker_id, speaker_name, text)
        return True
