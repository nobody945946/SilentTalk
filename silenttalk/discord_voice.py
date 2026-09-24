from __future__ import annotations

import asyncio
import logging
import time
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
        self._voice_reconcile_task: asyncio.Task[None] | None = None
        self._owner_missing_since: float | None = None
        self._next_reconnect_at = 0.0
        self._reconnect_delay = config.voice_reconnect_cooldown_seconds

    async def on_ready(self) -> None:
        _LOG.info(
            "discord_ready bot_user_id=%s", self.user.id if self.user else "unknown"
        )
        if self._voice_monitor_task is None or self._voice_monitor_task.done():
            self._voice_monitor_task = asyncio.create_task(
                self._voice_monitor(), name="voice-self-heal"
            )
        self._schedule_voice_reconcile(delay=0.0)

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
        # Discord can emit a leave then a join while changing channels or while
        # the gateway/voice transport is recovering. Collapse that burst into
        # one reconciliation against the final cached state.
        self._schedule_voice_reconcile()

    def _schedule_voice_reconcile(self, delay: float | None = None) -> None:
        if self.is_closed():
            return
        current = asyncio.current_task()
        if (
            self._voice_reconcile_task is not None
            and self._voice_reconcile_task is not current
        ):
            self._voice_reconcile_task.cancel()
        settle = (
            self._config.voice_state_settle_seconds if delay is None else max(0.0, delay)
        )
        self._voice_reconcile_task = asyncio.create_task(
            self._delayed_reconcile(settle), name="voice-reconcile"
        )

    async def _delayed_reconcile(self, delay: float) -> None:
        try:
            if delay:
                await asyncio.sleep(delay)
            await self.sync_owner_voice()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a later event/watchdog will retry.
            _LOG.warning("voice_reconcile_failed error_type=%s", type(exc).__name__)

    async def _voice_monitor(self) -> None:
        while not self.is_closed():
            try:
                await asyncio.sleep(self._config.voice_reconnect_interval_seconds)
                await self.sync_owner_voice()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - monitor must survive transient faults.
                _LOG.warning("voice_self_heal_failed error_type=%s", type(exc).__name__)

    async def close(self) -> None:
        tasks = [self._voice_monitor_task, self._voice_reconcile_task]
        for task in tasks:
            if task is not None:
                task.cancel()
        await asyncio.gather(*(task for task in tasks if task is not None), return_exceptions=True)
        self._voice_monitor_task = None
        self._voice_reconcile_task = None
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
        channel = self._find_owner_channel()
        now = time.monotonic()

        if channel is None:
            if self._owner_missing_since is None:
                self._owner_missing_since = now
            elapsed = now - self._owner_missing_since
            grace = self._config.owner_leave_grace_seconds
            if self.voice_clients and elapsed < grace:
                remaining = grace - elapsed
                _LOG.info("owner_voice_missing_grace remaining_seconds=%.2f", remaining)
                self._schedule_voice_reconcile(delay=remaining)
                return
        else:
            self._owner_missing_since = None

        await self._follow(channel)

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

            if target_voice is not None and target_voice.channel.id == channel.id:
                self._mark_voice_healthy()
                self._status(AppState.VOICE_CONNECTED, f"已連線：{channel.name}")
                return

            if target_voice is not None:
                await target_voice.move_to(channel)
                self._mark_voice_healthy()
                self._status(AppState.VOICE_CONNECTED, f"已連線：{channel.name}")
                return

            now = time.monotonic()
            if now < self._next_reconnect_at:
                wait_seconds = max(0.0, self._next_reconnect_at - now)
                _LOG.info("voice_reconnect_cooldown remaining_seconds=%.2f", wait_seconds)
                self._schedule_voice_reconcile(delay=wait_seconds)
                return

            # Only clean stale/other-guild clients when we are actually about to
            # make a new connection. This avoids disconnect/reconnect churn during
            # transient cache inconsistencies.
            for voice in voices:
                await self._close_voice(voice)

            try:
                await channel.connect(timeout=20.0, reconnect=True)
            except Exception:
                self._record_reconnect_failure()
                raise

            self._mark_voice_healthy()
            self._status(AppState.VOICE_CONNECTED, f"已連線：{channel.name}")

    def _mark_voice_healthy(self) -> None:
        self._reconnect_delay = self._config.voice_reconnect_cooldown_seconds
        self._next_reconnect_at = 0.0

    def _record_reconnect_failure(self) -> None:
        now = time.monotonic()
        self._next_reconnect_at = now + self._reconnect_delay
        _LOG.warning(
            "voice_reconnect_backoff delay_seconds=%.2f", self._reconnect_delay
        )
        self._reconnect_delay = min(
            self._reconnect_delay * 2,
            self._config.voice_reconnect_max_interval_seconds,
        )
        self._schedule_voice_reconcile(
            delay=max(0.0, self._next_reconnect_at - time.monotonic())
        )

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
        # This is a no-op while healthy. During a reconnect cooldown it deliberately
        # does not hammer Discord; the sentence fails instead of causing join spam.
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
            raise RuntimeError("Discord Voice 正在恢復連線，請稍後再送一次。")
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

        options = "-vn"
        if audio.ffmpeg_filter:
            options += f' -af "{audio.ffmpeg_filter}"'
        source = discord.FFmpegOpusAudio(
            str(audio.path), executable=self._audio.ffmpeg_path, options=options
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
