from __future__ import annotations

import asyncio
import math
import struct
import tempfile
import wave
from pathlib import Path

from silenttalk.config import Settings
from silenttalk.discord_playback import DiscordAudioPlayer, play_smoke_tone
from silenttalk.discord_voice import DiscordVoiceClient
from silenttalk.state import AppState
from silenttalk.tts.edge import EdgeTTSEngine

OWNER_VOICE_TIMEOUT = 20.0


def create_test_tone(path: Path, duration_seconds: float = 1.0) -> None:
    sample_rate = 48_000
    frame_count = int(sample_rate * duration_seconds)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            fade = min(1.0, index / 480, (frame_count - index) / 480)
            sample = int(
                8000 * fade * math.sin(2 * math.pi * 440 * index / sample_rate)
            )
            frames.extend(struct.pack("<h", sample))
        output.writeframes(frames)


async def wait_for_owner_voice(
    client: DiscordVoiceClient, timeout: float = OWNER_VOICE_TIMEOUT
) -> None:
    """Until the client's own reconcile has followed the owner into voice;
    at the deadline, what the bot can see of the owner."""
    if not await client.wait_until_connected(timeout):
        guild_count, voice_count, owner_visible = client.voice_diagnostics()
        raise RuntimeError(
            "Owner voice state 不可見；"
            f"Bot 可見伺服器={guild_count}、可見語音頻道={voice_count}、"
            f"Owner 可見={owner_visible}。"
        )


async def run_voice_smoke(settings: Settings, tts_text: str | None = None) -> None:
    def status(state: AppState, message: str) -> None:
        print(f"{state.value}: {message}")

    client = DiscordVoiceClient(settings.discord, status)
    async with client:
        await client.login(settings.discord.token)
        connect_task = asyncio.create_task(client.connect(reconnect=False))
        try:
            await asyncio.wait_for(client.wait_until_ready(), timeout=30)
            await wait_for_owner_voice(client)
            with tempfile.TemporaryDirectory(prefix="silenttalk-smoke-") as temp_dir:
                if tts_text is None:
                    tone = Path(temp_dir) / "gate1-tone.wav"
                    create_test_tone(tone)
                    await play_smoke_tone(client, settings.audio, tone)
                    print("Gate 1 fixed-audio playback completed.")
                else:
                    engine = EdgeTTSEngine(settings.tts, Path(temp_dir))
                    try:
                        await engine.initialize()
                        audio_result = await engine.synthesize(tts_text)
                        await DiscordAudioPlayer(client, settings.audio).play(
                            audio_result
                        )
                        audio_result.path.unlink(missing_ok=True)
                    finally:
                        await engine.shutdown()
                    print("Gate 2 EdgeTTS-to-Discord playback completed.")
        finally:
            await client.close()
            await asyncio.gather(connect_task, return_exceptions=True)
