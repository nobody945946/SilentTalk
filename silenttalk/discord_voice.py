from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

import discord

from silenttalk.config import AudioConfig, DiscordConfig
from silenttalk.state import AppState
from silenttalk.tts.base import AudioResult

_LOG = logging.getLogger(__name__)
StatusCallback = Callable[[AppState, str], None]


class DiscordVoiceClient(discord.Client):
    def __init__(self, config: DiscordConfig, status: StatusCallback) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.voice_states = True
        super().__init__(intents=intents)
        self._config = config
        self._status = status
        self._voice_lock = asyncio.Lock()
        self._voice_monitor_task: asyncio.Task[None] | None = None

    async def on_ready(self) -> None:
        _LOG.info(
            "discord_ready bot_user_id=%s", self.user.id if self.user else "unknown"
        )
        if self._voice_monitor_task is None or self._voice_monitor_task.done():
            self._voice_monitor_task = asyncio.create_task(
                self._voice_monitor(), name="voice-self-heal"
            )
        try:
            await self.sync_owner_voice()
        except Exception as exc:  # noqa: BLE001 - monitor will retry after gateway ready.
            _LOG.warning("initial_voice_sync_failed error_type=%s", type(exc).__name__)

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        is_owner = member.id == self._config.owner_user_id
        is_bot = self.user is not None and member.id == self.user.id
        if before.channel == after.channel or not (is_owner or is_bot):
            return
        # Cross-guild switches arrive as separate leave/join events. Give the cache a
        # brief moment to settle, then route from the owner's global end state.
        await asyncio.sleep(0.25)
        await self.sync_owner_voice()

    async def _voice_monitor(self) -> None:
        delay = self._config.voice_reconnect_interval_seconds
        while not self.is_closed():
            try:
                await asyncio.sleep(delay)
                channel = self._find_owner_channel()
                voices = list(self.voice_clients)
                healthy = next(
                    (voice for voice in voices if voice.is_connected()), None
                )
                stale = any(not voice.is_connected() for voice in voices)
                needs_sync = channel is None and bool(voices)
                if channel is not None:
                    needs_sync = (
                        healthy is None
                        or stale
                        or healthy.guild.id != channel.guild.id
                        or healthy.channel.id != channel.id
                    )
                if needs_sync:
                    await self.sync_owner_voice()
                delay = self._config.voice_reconnect_interval_seconds
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - monitor must survive transient faults.
                _LOG.warning("voice_self_heal_failed error_type=%s", type(exc).__name__)
                delay = min(
                    delay * 2, self._config.voice_reconnect_max_interval_seconds
                )

    async def close(self) -> None:
        if self._voice_monitor_task is not None:
            self._voice_monitor_task.cancel()
            await asyncio.gather(self._voice_monitor_task, return_exceptions=True)
            self._voice_monitor_task = None
        await super().close()

    def _find_owner_channel(self) -> discord.abc.Connectable | None:
        for guild in self.guilds:
            for channel in guild.voice_channels:
                if self._config.owner_user_id in channel.voice_states:
                    return channel
        return None

    def voice_diagnostics(self) -> tuple[int, int, bool]:
        """Return non-sensitive counts for diagnosing owner visibility."""
        channels = [
            channel for guild in self.guilds for channel in guild.voice_channels
        ]
        owner_visible = any(
            self._config.owner_user_id in channel.voice_states for channel in channels
        )
        return len(self.guilds), len(channels), owner_visible

    async def sync_owner_voice(self) -> None:
        await self._follow(self._find_owner_channel())

    async def _follow(self, channel: discord.abc.Connectable | None) -> None:
        async with self._voice_lock:
            voices = list(self.voice_clients)
            if channel is None:
                if self._config.disconnect_when_owner_leaves:
                    for voice in voices:
                        await self._close_voice(voice)
                self._status(AppState.OWNER_NOT_IN_VOICE, "請先加入 Discord 語音頻道")
                return

            target_guild_id = channel.guild.id
            target_voice = next(
                (
                    voice
                    for voice in voices
                    if voice.guild.id == target_guild_id and voice.is_connected()
                ),
                None,
            )

            # A transport drop can leave a dead VoiceClient in discord.py's
            # cache. Clean every stale/other-guild client before connect(), or
            # Discord rejects the new connection as already connected.
            for voice in voices:
                if voice is not target_voice:
                    await self._close_voice(voice)

            if target_voice is None:
                await channel.connect(timeout=20.0, reconnect=True)
            elif target_voice.channel.id != channel.id:
                await target_voice.move_to(channel)
            self._status(AppState.VOICE_CONNECTED, f"已連線：{channel.name}")

    @staticmethod
    async def _close_voice(voice: discord.VoiceClient) -> None:
        try:
            await voice.disconnect(force=True)
        except Exception:  # noqa: BLE001 - stale cleanup must not block reconnect.
            voice.cleanup()

    def active_voice(self) -> discord.VoiceClient | None:
        return next((vc for vc in self.voice_clients if vc.is_connected()), None)


class DiscordAudioPlayer:
    def __init__(self, client: DiscordVoiceClient, audio: AudioConfig) -> None:
        self._client = client
        self._audio = audio

    async def play(self, audio: AudioResult) -> None:
        # This is a no-op while healthy; it reconnects only before a new sentence
        # when the previous voice transport has actually disappeared.
        await self._client.sync_owner_voice()
        try:
            await self._play_once(audio)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Discord does not expose an exact audio frame offset. Replaying a
            # sentence after it started would create an audible echo.
            _LOG.warning(
                "voice_playback_failed_no_replay error_type=%s", type(exc).__name__
            )
            await self.stop()
            raise RuntimeError(
                "Discord Voice 播放中斷；未重播該句，以避免回音。"
            ) from exc

    async def _play_once(self, audio: AudioResult) -> None:
        voice = self._client.active_voice()
        if voice is None:
            raise RuntimeError("Owner 尚未加入語音頻道。")
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

        source = discord.FFmpegOpusAudio(
            str(audio.path), executable=self._audio.ffmpeg_path, options="-vn"
        )
        voice.play(source, after=after)
        await asyncio.wait_for(finished, timeout=self._audio.playback_timeout_seconds)

    async def stop(self) -> None:
        voice = self._client.active_voice()
        if voice is not None and voice.is_playing():
            voice.stop()


async def play_smoke_tone(
    client: DiscordVoiceClient, audio: AudioConfig, path: Path
) -> None:
    """Gate 1 runner: play a caller-provided fixed audio file in the owner's VC."""
    await client.sync_owner_voice()
    await DiscordAudioPlayer(client, audio).play(
        AudioResult(path, None, None, path.suffix.lstrip("."))
    )
