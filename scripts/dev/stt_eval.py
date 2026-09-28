"""STT accuracy score: 16 Taiwanese chat lines through the real transcriber.

Usage (from the repo root, models already in .runtime/models/asr):
    python scripts/dev/stt_eval.py            # uses cached audio if present
    python scripts/dev/stt_eval.py --refresh  # re-synthesize with EdgeTTS (network)
    python scripts/dev/stt_eval.py --engine sensevoice  # Silero VAD + SenseVoice
                                                         # (.runtime/models/sensevoice + vad)

    python scripts/dev/stt_eval.py --stress [--engine E] [--vad-threshold 0.35]
        # the same lines spoken faster, quieter, muffled and run together:
        # the laptop test (2026-09-28) found recognition fails on slightly
        # fast or unclear speech. Prints CER and misses per condition.

Baseline 2026-09-25, streaming Paraformer + 0.66 s tail: average CER ~8-9%.
Known model misses (not bugs): boss→包, lag→了鉤, 打野→達也, 補師→不是, 明天見→明天.
Any change to silenttalk/copilot/stt.py must keep the average at or below baseline.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

from silenttalk.config import STT_ENGINES, CopilotConfig, TTSConfig
from silenttalk.copilot.smoke import (
    build_transcriber,
    char_error_rate,
    synthesize_discord_pcm,
    transcribe_pcm,
)
from silenttalk.tts.edge import EdgeTTSEngine

CACHE_DIR = PROJECT_DIR / ".runtime" / "dev" / "stt_samples"
FEMALE, MALE = "zh-TW-HsiaoChenNeural", "zh-TW-YunJheNeural"
# (id, voice, reference, add 20 dB white noise)
SAMPLES = (
    ("u01", FEMALE, "左邊有人，快點過來幫我", False),
    ("u02", MALE, "這個boss血量剩一半了，大家開大", False),
    ("u03", FEMALE, "你今天晚上要不要一起打rank", True),
    ("u04", MALE, "我這邊好lag喔，網路一直斷線", False),
    ("u05", FEMALE, "等一下我去倒個水馬上回來", False),
    ("u06", MALE, "補師先不要衝，站在後面就好", False),
    ("u07", FEMALE, "剛剛那波團戰真的打得很好", True),
    ("u08", MALE, "你們有人看過昨天的直播嗎", False),
    ("u09", FEMALE, "我沒有子彈了，誰可以丟給我", False),
    ("u10", MALE, "中路那個打野一直來抓我", True),
    ("u11", FEMALE, "這把輸了沒關係，下一把再來", False),
    ("u12", MALE, "晚餐要吃什麼，要不要叫外送", False),
    ("u13", FEMALE, "小心後面，有人在繞我們", False),
    ("u14", MALE, "我先下線了，明天見", True),
    ("u15", FEMALE, "這個技能冷卻時間太長了吧", False),
    ("u16", MALE, "誰有空幫我解一下這個任務", False),
)


def add_noise(pcm: bytes, snr_db: float = 20.0) -> bytes:
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    signal_rms = float(np.sqrt(np.mean(samples**2))) or 1.0
    noise = np.random.default_rng(0).standard_normal(samples.shape).astype(np.float32)
    mixed = samples + noise * signal_rms / (10 ** (snr_db / 20))
    return np.clip(mixed, -32768, 32767).astype("<i2").tobytes()


def scale(pcm: bytes, db: float) -> bytes:
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) * (10 ** (db / 20))
    return np.clip(samples, -32768, 32767).astype("<i2").tobytes()


def lowpass(pcm: bytes, cutoff_hz: float, rate: int = 48000) -> bytes:
    """Muffle: drop everything above `cutoff_hz` (FFT, per stereo channel)."""
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32).reshape(-1, 2)
    spectrum = np.fft.rfft(samples, axis=0)
    spectrum[np.fft.rfftfreq(len(samples), 1 / rate) > cutoff_hz] = 0
    out = np.fft.irfft(spectrum, n=len(samples), axis=0)
    return np.clip(out, -32768, 32767).astype("<i2").reshape(-1).tobytes()


# Stress conditions: (name, speaking-rate folder, transform). "runon" joins
# two lines with no pause, the way a fast talker runs sentences together.
STRESS = (
    ("normal", "+0%", lambda pcm: pcm),
    ("fast +35%", "+35%", lambda pcm: pcm),
    ("fast +60%", "+60%", lambda pcm: pcm),
    ("quiet -18 dB", "+0%", lambda pcm: scale(pcm, -18)),
    ("muffled", "+0%", lambda pcm: add_noise(scale(lowpass(pcm, 2200), -10), 15)),
    ("fast+muffled", "+35%", lambda pcm: add_noise(scale(lowpass(pcm, 2200), -10), 15)),
)


async def ensure_samples(refresh: bool, ffmpeg: str, rate: str = "+0%") -> None:
    """Cached per speaking rate; "+0%" keeps the original cache folder."""
    folder = CACHE_DIR if rate == "+0%" else CACHE_DIR / f"rate{rate}"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stt-eval-") as temp:
        engines: dict[str, EdgeTTSEngine] = {}
        try:
            for sample_id, voice, text, noisy in SAMPLES:
                target = folder / f"{sample_id}.pcm"
                if target.is_file() and not refresh:
                    continue
                if voice not in engines:
                    engines[voice] = EdgeTTSEngine(TTSConfig(voice=voice, rate=rate), Path(temp))
                    await engines[voice].initialize()
                pcm = await synthesize_discord_pcm(engines[voice], text, ffmpeg)
                target.write_bytes(add_noise(pcm) if noisy else pcm)
                print(f"synthesized {sample_id}")
        finally:
            for engine in engines.values():
                await engine.shutdown()


def sample_pcm(sample_id: str, rate: str) -> bytes:
    folder = CACHE_DIR if rate == "+0%" else CACHE_DIR / f"rate{rate}"
    return (folder / f"{sample_id}.pcm").read_bytes()


def stress(args: argparse.Namespace) -> int:
    for rate in sorted({rate for _, rate, _ in STRESS}):
        asyncio.run(ensure_samples(args.refresh, args.ffmpeg, rate))
    transcriber, collector = build_transcriber(
        PROJECT_DIR, CopilotConfig(stt_engine=args.engine)
    )
    transcriber.start()
    rows = []
    try:
        for name, rate, transform in STRESS:
            rates, misses = [], 0
            for sample_id, _voice, reference, _noisy in SAMPLES:
                heard = transcribe_pcm(transcriber, collector, transform(sample_pcm(sample_id, rate)))
                misses += not heard
                rates.append(char_error_rate(reference, heard))
            rows.append((name, sum(rates) / len(rates), misses))
        # Two lines back to back, no pause between them.
        rates, misses = [], 0
        for first, second in zip(SAMPLES[::2], SAMPLES[1::2], strict=True):
            pcm = sample_pcm(first[0], "+35%") + sample_pcm(second[0], "+35%")
            heard = transcribe_pcm(transcriber, collector, pcm)
            misses += not heard
            rates.append(char_error_rate(first[2] + second[2], heard))
        rows.append(("run-on +35%", sum(rates) / len(rates), misses))
    finally:
        transcriber.stop()
    label = args.engine + (f" vad={args.vad_threshold}" if args.vad_threshold else "")
    print(f"\n| {label} | CER | 沒辨識到 |\n|---|---|---|")
    for name, cer, missed in rows:
        print(f"| {name} | {cer:.1%} | {missed} |")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="re-synthesize audio")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    parser.add_argument("--engine", choices=STT_ENGINES, default="paraformer")
    parser.add_argument("--stress", action="store_true", help="faster, quieter, muffled speech")
    parser.add_argument("--vad-threshold", type=float, help="sensevoice: Silero VAD threshold")
    args = parser.parse_args()
    if args.vad_threshold:
        from silenttalk.copilot import stt_offline

        stt_offline._VAD_THRESHOLD = args.vad_threshold
    if args.stress:
        return stress(args)

    asyncio.run(ensure_samples(args.refresh, args.ffmpeg))
    transcriber, collector = build_transcriber(
        PROJECT_DIR, CopilotConfig(stt_engine=args.engine)
    )
    transcriber.start()
    rates: list[float] = []
    try:
        for sample_id, _voice, reference, noisy in SAMPLES:
            pcm = (CACHE_DIR / f"{sample_id}.pcm").read_bytes()
            heard = transcribe_pcm(transcriber, collector, pcm)
            rate = char_error_rate(reference, heard)
            rates.append(rate)
            flag = "noisy" if noisy else "     "
            print(f"{sample_id} {flag} {rate:5.0%}  {reference}｜{heard or '（沒有）'}")
    finally:
        transcriber.stop()
    print(
        f"\nAVERAGE CER {sum(rates) / len(rates):.1%}  engine={args.engine}"
        "  (baseline: paraformer ~8%, sensevoice target <= 6.5%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
