from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import discord
from discord.ext import voice_recv

from silenttalk import voice_recv_patch
from silenttalk.config import DiscordConfig
from silenttalk.discord_channels import DiscordChannels
from silenttalk.discord_invite import invite_url
from silenttalk.discord_messages import DiscordMessages
from silenttalk.state import AppState
from silenttalk.voice_stats import ReceiveStats, dave_receive_ready

_LOG = logging.getLogger(__name__)
voice_recv_patch.apply()
# 20 ms of 48 kHz stereo s16le: every decoded Discord voice frame.
StatusCallback = Callable[[AppState, str], None]
PCMCallback = Callable[[int, str, bytes], None]
# (author id, display name, content, addressed) of a typed line, with
# keywords place (VOICE_ROOM, a text channel or a thread), channel_id,
# message_id and agent (the place is the owner's Agent thread).
# `addressed` is Discord's own signal: an @mention of the bot or a reply to
# one of its messages - exact, unlike matching the name as a substring.
TextCallback = Callable[..., None]
# Discord's own limit; a character's line is far shorter, but a paste is not.
# Everything the bot does in a server, asked for in its invite link so a
# server admin grants it in one click: join and speak in voice, read and type
# in the voice channel's chat, open threads and talk in them, mark the owner's
# orders. The Message Content Intent is not a server permission: the bot's
# owner turns it on in the Developer Portal.


class DiscordVoiceClient(discord.Client):
    def __init__(
        self,
        config: DiscordConfig,
        status: StatusCallback,
        pcm_callback: PCMCallback | None = None,
        text_callback: TextCallback | None = None,
        threads_open: Callable[[], bool] | None = None,
        names: Callable[[str], bool] | None = None,
    ) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.voice_states = True
        if config.text_chat:
            # Message Content is privileged: without it in the Developer
            # Portal the gateway refuses the connection, so this is opt-in.
            intents.guild_messages = True
            intents.message_content = True
        super().__init__(intents=intents)
        self._config = config
        self._status = status
        self._pcm_callback = pcm_callback
        self._text_callback = text_callback
        # Whether text channels and threads are conversations now (the
        # character is on): the owner's @ in a text channel opens his Agent
        # thread, and a line that calls the character there is a chat.
        self._threads_open = threads_open or (lambda: True)
        # Whether a typed line calls the character by name (the runtime's
        # NameMatcher); a text-channel line is passed on only then.
        self._names = names or (lambda text: False)
        # The threads opened this session.
        # This bot's invite link, known once it has logged in.
        self.invite_link = ""
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._voice_lock = asyncio.Lock()
        self._voice_monitor_task: asyncio.Task[None] | None = None
        self._voice_reconcile_task: asyncio.Task[None] | None = None
        self._voice_reconcile_deadline: float | None = None
        self._voice_reconcile_wake = asyncio.Event()
        self._voice_closing = False
        self._owner_missing_since: float | None = None
        self._next_reconnect_at = 0.0
        self._reconnect_delay = config.voice_reconnect_cooldown_seconds
        self._voice_ready = asyncio.Event()
        self._listen_retries = 0
        self._receive = ReceiveStats(time.monotonic())
        self.channels = DiscordChannels(self, config, lambda: self.active_voice())
        self.messages = DiscordMessages(
            self,
            config,
            self.channels,
            lambda: self.active_voice(),
            status,
            callback=text_callback,
            threads_open=threads_open,
            names=names,
        )

    def set_pcm_callback(self, callback: PCMCallback | None) -> None:
        self._pcm_callback = callback
        if callback is not None and self._event_loop is not None:
            self._event_loop.call_soon_threadsafe(self._schedule_voice_reconcile, 0.0)

    def apply_config(self, config: DiscordConfig) -> None:
        """Live settings. Intents and the token are startup-only, so only the
        behaviour flags and timings are taken from here."""
        self._config = config
        self.channels.apply_config(config)
        self.messages.apply_config(config)

    def set_text_callback(self, callback: TextCallback | None) -> None:
        self.messages.callback = callback

    async def on_message(self, message: discord.Message) -> None:
        await self.messages.receive(message)

    async def on_ready(self) -> None:
        self._event_loop = asyncio.get_running_loop()
        _LOG.info(
            "discord_ready bot_user_id=%s", self.user.id if self.user else "unknown"
        )
        application_id = self.application_id or (self.user.id if self.user else None)
        if application_id:
            self.invite_link = invite_url(application_id)
        if self._voice_monitor_task is None or self._voice_monitor_task.done():
            self._voice_monitor_task = asyncio.create_task(
                self._voice_monitor(), name="voice-self-heal"
            )
        self._schedule_voice_reconcile(delay=0.0)

    async def on_resumed(self) -> None:
        _LOG.info("discord_gateway_resumed")
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
        self._schedule_voice_reconcile()

    def _schedule_voice_reconcile(self, delay: float | None = None) -> None:
        if self.is_closed() or self._voice_closing:
            return
        settle = (
            self._config.voice_state_settle_seconds
            if delay is None
            else max(0.0, delay)
        )
        self._voice_reconcile_deadline = time.monotonic() + settle
        self._voice_reconcile_wake.set()
        if self._voice_reconcile_task is None or self._voice_reconcile_task.done():
            self._voice_reconcile_task = asyncio.create_task(
                self._reconcile_voice(), name="voice-reconcile"
            )

    async def _reconcile_voice(self) -> None:
        # Coalesce state events while settling, then finish the active
        # handshake. Events produced by that handshake queue another check;
        # they must not cancel the operation that produced them.
        while not self._voice_closing:
            deadline = self._voice_reconcile_deadline
            if deadline is None:
                return
            self._voice_reconcile_wake.clear()
            delay = deadline - time.monotonic()
            if delay > 0:
                try:
                    await asyncio.wait_for(self._voice_reconcile_wake.wait(), delay)
                except TimeoutError:
                    pass
                else:
                    continue
            self._voice_reconcile_deadline = None
            try:
                await self.sync_owner_voice()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOG.warning("voice_reconcile_failed error_type=%s", type(exc).__name__)

    async def _voice_monitor(self) -> None:
        while not self.is_closed():
            try:
                await asyncio.sleep(self._config.voice_reconnect_interval_seconds)
                await self.sync_owner_voice()
                self._log_receive_stats()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOG.warning("voice_self_heal_failed error_type=%s", type(exc).__name__)

    async def close(self) -> None:
        self._voice_closing = True
        self._voice_reconcile_deadline = None
        self._voice_ready.clear()
        self._event_loop = None
        tasks = [self._voice_monitor_task, self._voice_reconcile_task]
        for task in tasks:
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in tasks if task is not None),
            return_exceptions=True,
        )
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
                self._voice_ready.clear()
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
                self._ensure_listening(target_voice)
                self._mark_voice_healthy()
                self._status(AppState.VOICE_CONNECTED, f"已連線：{channel.name}")
                return

            if target_voice is not None:
                self._voice_ready.clear()
                try:
                    await target_voice.move_to(channel)
                except Exception:
                    _LOG.warning("voice_move_failed_reconnect")
                    await self._connect_fresh_locked(channel, voices)
                else:
                    self._ensure_listening(target_voice)
                    self._mark_voice_healthy()
                self._status(AppState.VOICE_CONNECTED, f"已連線：{channel.name}")
                return

            now = time.monotonic()
            if now < self._next_reconnect_at:
                self._voice_ready.clear()
                wait_seconds = max(0.0, self._next_reconnect_at - now)
                _LOG.info(
                    "voice_reconnect_cooldown remaining_seconds=%.2f",
                    wait_seconds,
                )
                self._schedule_voice_reconcile(delay=wait_seconds)
                return

            await self._connect_fresh_locked(channel, voices)
            self._status(AppState.VOICE_CONNECTED, f"已連線：{channel.name}")

    async def _connect_fresh_locked(
        self,
        channel: discord.abc.Connectable,
        voices: list[discord.VoiceClient] | None = None,
    ) -> None:
        self._voice_ready.clear()
        for voice in voices if voices is not None else list(self.voice_clients):
            await self._close_voice(voice)

        try:
            # Transport capabilities do not depend on AI readiness. Attaching
            # a recovered receiver must never require replacing this connection.
            # reconnect=False: this client is the one owner of reconnecting
            # (reconcile with its back-off). The SDK's own loop would wake
            # after its back-off, leave the channel and connect again, knocking
            # out the connection made meanwhile (laptop audit 2026-10-07: 573
            # forced disconnects in 3 hours, one every ~20 s). The SDK still
            # resumes on 4015 and follows a channel move by itself.
            new_voice = await channel.connect(
                timeout=20.0,
                reconnect=False,
                cls=voice_recv.VoiceRecvClient,
            )
        except Exception:
            self._record_reconnect_failure()
            raise

        self._listen_retries = 0
        self._ensure_listening(new_voice)
        self._mark_voice_healthy()

    async def wait_until_voice_ready(
        self, timeout_seconds: float | None = None
    ) -> None:
        if self.active_voice() is not None:
            return

        self._voice_ready.clear()
        await self.sync_owner_voice()
        if self.active_voice() is not None:
            return

        timeout = (
            self._config.voice_ready_timeout_seconds
            if timeout_seconds is None
            else max(0.1, timeout_seconds)
        )
        try:
            await asyncio.wait_for(self._voice_ready.wait(), timeout=timeout)
        except TimeoutError as exc:
            raise RuntimeError("Discord Voice 尚未恢復連線，請稍後再試。") from exc

        if self.active_voice() is None:
            self._voice_ready.clear()
            raise RuntimeError("Discord Voice 尚未恢復連線，請稍後再試。")

    async def recover_voice_transport(self, reason: str) -> bool:
        channel = self._find_owner_channel()
        if channel is None:
            self._voice_ready.clear()
            self._schedule_voice_reconcile()
            return False

        async with self._voice_lock:
            self._voice_ready.clear()
            voices = list(self.voice_clients)
            _LOG.warning(
                "voice_transport_recovery reason=%s stale_clients=%d",
                reason,
                len(voices),
            )

            now = time.monotonic()
            if now < self._next_reconnect_at:
                wait_seconds = max(0.0, self._next_reconnect_at - now)
                self._schedule_voice_reconcile(delay=wait_seconds)
                return False

            try:
                await self._connect_fresh_locked(channel, voices)
            except Exception as exc:
                _LOG.warning(
                    "voice_transport_recovery_failed error_type=%s",
                    type(exc).__name__,
                )
                return False

            self._status(AppState.VOICE_CONNECTED, f"已恢復：{channel.name}")
            return True

    def _ensure_listening(self, voice: discord.VoiceClient | None) -> None:
        if self._pcm_callback is None or voice is None:
            return
        if not isinstance(voice, voice_recv.VoiceRecvClient):
            _LOG.warning("voice_receive_unavailable wrong_voice_client=true")
            return
        if voice.is_listening():
            return
        connection = getattr(voice, "_connection", None)
        dave_version = int(getattr(connection, "dave_protocol_version", 0) or 0)
        if isinstance(voice.channel, discord.StageChannel):
            _LOG.warning("voice_receive_skipped reason=stage_channel")
            return
        if dave_version and getattr(connection, "dave_session", None) is None:
            # With DAVE on, frames can only be decrypted once discord.py has
            # the session; connect() can return just before it exists.
            self._listen_retries += 1
            _LOG.warning(
                "voice_receive_waiting reason=no_dave_session attempt=%d",
                self._listen_retries,
            )
            if self._listen_retries <= 10:
                self._schedule_voice_reconcile(delay=1.0)
            return
        self._listen_retries = 0
        voice.listen(
            voice_recv.BasicSink(
                lambda user, data: self._on_voice_pcm(user, data, voice)
            ),
            after=self._on_listen_stopped,
        )
        _LOG.info("voice_receive_started dave_version=%d", dave_version)

    def _on_voice_pcm(
        self,
        user: discord.Member | discord.User | None,
        data: voice_recv.VoiceData,
        voice: discord.VoiceClient | None = None,
    ) -> None:
        callback = self._pcm_callback
        if callback is None or user is None or not data.pcm:
            return
        if self.user is not None and user.id == self.user.id:
            return
        if bool(getattr(user, "bot", False)):
            return
        # DAVE on but no session yet: nothing decrypted these frames and they
        # decode to noise, which STT would turn into invented words.
        ready = voice is None or dave_receive_ready(voice)
        if ready:
            self._receive.frame(user.id, len(data.pcm))
        else:
            self._receive.dropped += 1
            return

        name = str(
            getattr(user, "display_name", None)
            or getattr(user, "name", None)
            or user.id
        )
        callback(user.id, name, data.pcm)

    def _log_receive_stats(self) -> None:
        """Every 30 s while listening, even when no frame gets through (all
        of them failing to decrypt is exactly the case to see)."""
        now = time.monotonic()
        if now - self._receive.started < ReceiveStats.PERIOD:
            return
        voice = self.active_voice()
        stats, self._receive = self._receive, ReceiveStats(now)
        if voice is None or not getattr(voice, "is_listening", lambda: False)():
            return
        members = getattr(voice.channel, "members", [])
        stats.log(voice, now, [m.id for m in members if not getattr(m, "bot", False)])

    def _on_listen_stopped(self, error: Exception | None) -> None:
        if error is None or self.is_closed():
            return
        _LOG.warning(
            "voice_receive_stopped error_type=%s",
            type(error).__name__,
        )
        loop = self._event_loop
        if loop is None or loop.is_closed():
            return

        def recover() -> None:
            asyncio.create_task(
                self.recover_voice_transport("voice_receive"),
                name="voice-receive-recovery",
            )

        loop.call_soon_threadsafe(recover)

    def _mark_voice_healthy(self) -> None:
        self._reconnect_delay = self._config.voice_reconnect_cooldown_seconds
        self._next_reconnect_at = 0.0
        self._voice_ready.set()

    def _record_reconnect_failure(self) -> None:
        self._voice_ready.clear()
        now = time.monotonic()
        self._next_reconnect_at = now + self._reconnect_delay
        _LOG.warning(
            "voice_reconnect_backoff delay_seconds=%.2f",
            self._reconnect_delay,
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
        """Retire a voice client for good. Its SDK tasks (the websocket poller
        and a pending connect) are cancelled before it disconnects:
        disconnect() alone leaves them running, and a poller sleeping in its
        back-off would later leave the channel and reconnect over the
        replacement. discord.py 2.7.1 (pinned) keeps them on the connection
        state; tests/test_voice_lifecycle.py runs the real one."""
        connection = getattr(voice, "_connection", None)
        for name in ("_runner", "_connector"):
            task = getattr(connection, name, None)
            if isinstance(task, asyncio.Task) and task is not asyncio.current_task():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                setattr(connection, name, None)
        try:
            await voice.disconnect(force=True)
        except Exception:
            voice.cleanup()

    def active_voice(self) -> discord.VoiceClient | None:
        return next(
            (vc for vc in self.voice_clients if vc.is_connected()),
            None,
        )
