"""bench_hw.py's speech stages: EdgeTTS time to first audio and to the whole
line (needs internet), and Paraformer STT on that clip, decode speed and
the finalize step after a line ends. The clip only lives in a temporary
file that is deleted right away."""

from __future__ import annotations

import asyncio
import shutil
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

from bench_hw_system import NO_WINDOW, BenchError

PROJECT_DIR = Path(__file__).resolve().parents[2]
TTS_LINE = "欸我的，下波我先進，你們跟緊一點"
TTS_VOICE = "zh-TW-YunJheNeural"


def synth_clip(rows: list[tuple[str, str]]) -> bytes | None:
    """EdgeTTS timing, and the clip doubles as STT input."""
    try:
        import edge_tts
    except ImportError:
        rows.append(("TTS", "沒裝 edge_tts"))
        return None

    async def once() -> tuple[float, float, bytes]:
        started = time.perf_counter()
        first = None
        audio = bytearray()
        async for chunk in edge_tts.Communicate(TTS_LINE, TTS_VOICE).stream():
            if chunk["type"] == "audio":
                if first is None:
                    first = time.perf_counter() - started
                audio.extend(chunk["data"])
        return (
            (first or 0.0) * 1000,
            (time.perf_counter() - started) * 1000,
            bytes(audio),
        )

    runs = []
    for _ in range(3):
        try:
            runs.append(asyncio.run(once()))
        except Exception as exc:  # network errors come in many types
            rows.append(("TTS", f"失敗：{type(exc).__name__}（沒網路就加 --skip-tts）"))
            return None
    first = statistics.median(r[0] for r in runs)
    total = statistics.median(r[1] for r in runs)
    rows.append(("TTS 第一段聲音", f"{first:.0f} ms"))
    rows.append(("TTS 整句合成完", f"{total:.0f} ms（{len(TTS_LINE)} 字）"))
    return runs[-1][2]


def bench_stt(rows: list[tuple[str, str]], mp3: bytes | None) -> None:
    if mp3 is None:
        rows.append(("STT", "跳過（需要 TTS 產生的測試音檔）"))
        return
    try:
        import numpy as np
        import sherpa_onnx
    except ImportError as exc:
        raise BenchError(f"缺套件 {exc.name}") from exc
    model_dir = PROJECT_DIR / ".runtime" / "models" / "asr"
    if not (model_dir / "encoder.int8.onnx").is_file():
        raise BenchError(f"找不到 {model_dir}")
    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not ffmpeg:
        raise BenchError("找不到 ffmpeg")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
        handle.write(mp3)
        clip = Path(handle.name)
    try:
        pcm = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                str(clip),
                "-f",
                "f32le",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-",
            ],
            capture_output=True,
            timeout=30,
            creationflags=NO_WINDOW,
        ).stdout
    finally:
        clip.unlink(missing_ok=True)
    samples = np.frombuffer(pcm, dtype=np.float32)
    seconds = len(samples) / 48000
    # Same recognizer settings as silenttalk/copilot/stt.py.
    recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
        tokens=str(model_dir / "tokens.txt"),
        encoder=str(model_dir / "encoder.int8.onnx"),
        decoder=str(model_dir / "decoder.int8.onnx"),
        num_threads=1,
        sample_rate=16000,
        feature_dim=80,
        enable_endpoint_detection=True,
        rule1_min_trailing_silence=2.4,
        rule2_min_trailing_silence=0.8,
        rule3_min_utterance_length=20.0,
        decoding_method="greedy_search",
        provider="cpu",
    )
    stream = recognizer.create_stream()
    busy = 0.0
    step = 48000 // 50  # 20 ms Discord packets
    for start in range(0, len(samples), step):
        began = time.perf_counter()
        stream.accept_waveform(48000, samples[start : start + step])
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)
        busy += time.perf_counter() - began
    began = time.perf_counter()
    stream.accept_waveform(48000, np.zeros(int(0.66 * 48000), dtype=np.float32))
    stream.input_finished()
    while recognizer.is_ready(stream):
        recognizer.decode_stream(stream)
    finalize = (time.perf_counter() - began) * 1000
    text = recognizer.get_result(stream).strip()
    rows.append(
        (
            "STT 解碼速度",
            f"{busy / seconds:.3f} × 即時（{seconds:.1f} s 音檔，越小越好）",
        )
    )
    rows.append(
        ("STT 句尾收尾", f"{finalize:.0f} ms（另外固定等 0.8 s 靜音才判定講完）")
    )
    rows.append(("STT 聽到", text or "（空白）"))
