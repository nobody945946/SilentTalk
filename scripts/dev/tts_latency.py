"""Time from "text ready" to the first Opus packet Discord would send.

Runs the app's own EdgeTTS engine and Discord playback code (real EdgeTTS,
real FFmpeg) against a fake voice client that pulls packets like discord.py
does, for the file path (synthesize, then play) and the streaming path.

    .venv/bin/python scripts/dev/tts_latency.py [--runs 5]

Needs network (EdgeTTS) and ffmpeg. Nothing is written to disk except the
file path's own temporary MP3, which it deletes as usual.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

from silenttalk.config import AudioConfig, TTSConfig  # noqa: E402
from silenttalk.copilot.persona import PRESET_PERSONAS  # noqa: E402
from silenttalk.discord_voice import DiscordAudioPlayer  # noqa: E402
from silenttalk.tts.edge import EdgeTTSEngine  # noqa: E402

LINES = (
    "穩啦",
    "欸我的，下波我先進，你們跟緊一點",
    "哼，這種程度的團戰，吾之右手尚未解放，等我集滿能量再一口氣收掉他們",
)
# Opus frames from discord.py's FFmpeg source are 20 ms each.
FRAME_SECONDS = 0.02


class FakeVoice:
    """Pulls packets from the source on a thread, as discord.py's player does."""

    def __init__(self) -> None:
        self.first_packet_at: float | None = None
        self.packets = 0
        self._playing = False

    def play(self, source, *, after) -> None:
        self._playing = True

        def run() -> None:
            error = None
            try:
                while True:
                    packet = source.read()
                    if not packet:
                        break
                    if self.first_packet_at is None:
                        self.first_packet_at = time.perf_counter()
                    self.packets += 1
            except Exception as exc:  # report like discord.py would
                error = exc
            finally:
                source.cleanup()
                self._playing = False
                after(error)

        threading.Thread(target=run, daemon=True).start()

    def is_playing(self) -> bool:
        return self._playing

    def stop(self) -> None:
        self._playing = False


class FakeClient:
    def __init__(self, voice: FakeVoice) -> None:
        self._voice = voice

    async def wait_until_voice_ready(self) -> None:
        return None

    def active_voice(self) -> FakeVoice:
        return self._voice


async def one(
    engine: EdgeTTSEngine, text: str, style, streamed: bool
) -> tuple[float, float]:
    voice = FakeVoice()
    player = DiscordAudioPlayer(FakeClient(voice), AudioConfig())  # type: ignore[arg-type]
    started = time.perf_counter()
    synthesize = engine.stream if streamed else engine.synthesize
    audio = await synthesize(text, voice_style=style)
    try:
        await player.play(audio)
    finally:
        audio.discard()
    assert voice.first_packet_at is not None, "no audio came out"
    return (voice.first_packet_at - started) * 1000, voice.packets * FRAME_SECONDS


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        engine = EdgeTTSEngine(TTSConfig(voice="zh-TW-HsiaoChenNeural"), Path(temp))
        styles = {
            "預設聲音": "default",
            "黑焰（echo 音效）": PRESET_PERSONAS[2].voice_style(),
        }
        print(
            "| 句子 | 聲音 | 檔案：第一個封包 | 串流：第一個封包 | 音訊長度 檔案／串流 |"
        )
        print("|---|---|---|---|---|")
        for text in LINES:
            for label, style in styles.items():
                result = {}
                for streamed in (False, True):
                    runs = [
                        await one(engine, text, style, streamed)
                        for _ in range(args.runs)
                    ]
                    result[streamed] = (
                        statistics.median(r[0] for r in runs),
                        statistics.median(r[1] for r in runs),
                    )
                print(
                    f"| {len(text)} 字 | {label} | {result[False][0]:.0f} ms | "
                    f"{result[True][0]:.0f} ms | {result[False][1]:.2f} s／{result[True][1]:.2f} s |"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
