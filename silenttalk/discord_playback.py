from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Protocol

import discord

from silenttalk.config import AudioConfig
from silenttalk.opus_source import OpusSource
from silenttalk.tts.base import AudioResult

_LOG = logging.getLogger(__name__)


class VoiceTransport(Protocol):
    def active_voice(self) -> discord.VoiceClient | None: ...
    async def wait_until_voice_ready(
        self, timeout_seconds: float | None = None
    ) -> None: ...
    async def recover_voice_transport(self, reason: str) -> bool: ...


class DiscordAudioPlayer:
    def __init__(self, client: VoiceTransport, audio: AudioConfig) -> None:
        self._client = client
        self._audio = audio

    async def play(self, audio: AudioResult) -> None:
        await self._client.wait_until_voice_ready()
        try:
            await self._play_once(audio)
        except asyncio.CancelledError:
            raise
        except discord.FFmpegProcessError:
            # Encoding failed locally; reconnecting a healthy Discord voice
            # session cannot repair FFmpeg and interrupts the next sentence.
            raise
        except Exception as exc:
            _LOG.warning(
                "voice_playback_failed_recovering error_type=%s",
                type(exc).__name__,
            )
            await self.stop()
            recovered = await self._client.recover_voice_transport(
                reason=type(exc).__name__
            )
            if recovered:
                raise RuntimeError(
                    "Discord Voice 播放中斷；連線已自動恢復。該句未重播，以避免回音。"
                ) from exc
            raise RuntimeError(
                "Discord Voice 播放中斷；正在背景恢復連線。該句未重播，以避免回音。"
            ) from exc

    async def _play_once(self, audio: AudioResult) -> None:
        voice = self._client.active_voice()
        if voice is None:
            raise RuntimeError("Discord Voice 尚未建立可用連線。")

        loop = asyncio.get_running_loop()
        finished: asyncio.Future[None] = loop.create_future()

        def after(error: Exception | None) -> None:
            def complete() -> None:
                if finished.done():
                    return
                if error:
                    finished.set_exception(error)
                else:
                    finished.set_result(None)

            loop.call_soon_threadsafe(complete)

        source = OpusSource(audio, executable=self._audio.ffmpeg_path)
        try:
            voice.play(source, after=after)
            await asyncio.wait_for(
                finished, timeout=self._audio.playback_timeout_seconds
            )
        finally:
            source.cleanup()

    async def stop(self) -> None:
        voice = self._client.active_voice()
        if voice is not None and voice.is_playing():
            stop_playing = getattr(voice, "stop_playing", None)
            if callable(stop_playing):
                stop_playing()
            else:
                voice.stop()


async def play_smoke_tone(
    client: VoiceTransport,
    audio: AudioConfig,
    path: Path,
) -> None:
    await client.wait_until_voice_ready()
    await DiscordAudioPlayer(client, audio).play(
        AudioResult(path, None, None, path.suffix.lstrip("."))
    )
