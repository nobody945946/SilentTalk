from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import discord

from silenttalk.config import DiscordConfig
from silenttalk.conversation import VOICE_ROOM

_LOG = logging.getLogger(__name__)
import json

from silenttalk.discord_approval import AgentApprovalView

MAX_TEXT_CHARS = 2000
# On the owner's message that handed over work (the user chose the gear).
TASK_MARKS = {"accepted": "\u2699\ufe0f", "done": "\u2705", "failed": "\u274c"}
# Heads every message of an Agent result posted in a thread, so reading the
# thread back tells the Agent's work apart from what the character said.
AGENT_RESULT_HEAD = "【思考機回報】"
# A thread's earlier lines, oldest first: (author ID, display name, text,
# kind) with kind "mine" (the character), "agent" (a posted result) or "text".
HistoryLine = tuple[int, str, str, str]


class DiscordChannels:
    """Channel delivery and thread history; no model or voice lifecycle."""

    def __init__(
        self, client: discord.Client, config: DiscordConfig, voice: Callable[[], object]
    ):
        self._client = client
        self._config = config
        self._voice = voice
        self._threads: set[int] = set()

    def apply_config(self, config: DiscordConfig) -> None:
        self._config = config

    def remember_thread(self, thread_id: int) -> None:
        self._threads.add(thread_id)

    def is_our_thread(self, channel: object) -> bool:
        return isinstance(channel, discord.Thread) and (
            channel.id in self._threads
            or (
                self._client.user is not None
                and channel.owner_id == self._client.user.id
            )
        )

    async def _channel(self, place: int) -> discord.abc.Messageable | None:
        if place == VOICE_ROOM:
            channel = getattr(self._voice(), "channel", None)
            return channel if hasattr(channel, "send") else None
        try:
            return self._client.get_channel(place) or await self._client.fetch_channel(
                place
            )
        except discord.HTTPException:
            return None

    async def send_text(self, text: str, place: int = VOICE_ROOM) -> bool:
        """Say something in the voice channel's text chat or in a thread the
        bot opened. False if it could not be sent (not connected, missing
        permission, Discord error)."""
        channel = await self._channel(place)
        if channel is None:
            _LOG.info("text_send_skipped reason=no_channel")
            return False
        try:
            await channel.send(
                text[:MAX_TEXT_CHARS], allowed_mentions=discord.AllowedMentions.none()
            )
        except discord.Forbidden:
            _LOG.warning("text_send_failed reason=forbidden")
            return False
        except discord.HTTPException as exc:
            _LOG.warning("text_send_failed status=%s", getattr(exc, "status", "?"))
            return False
        return True

    async def send_result(self, text: str, place: int) -> bool:
        """The Agent's result in the thread the work came from, so the thread
        keeps it: split at Discord's limit, each part headed. False if a part
        could not be sent."""
        channel = await self._channel(place)
        if channel is None:
            return False
        size = MAX_TEXT_CHARS - len(AGENT_RESULT_HEAD) - 12
        parts = [
            text[start : start + size] for start in range(0, max(len(text), 1), size)
        ]
        try:
            for index, part in enumerate(parts, 1):
                count = f"（{index}/{len(parts)}）" if len(parts) > 1 else ""
                await channel.send(
                    f"{AGENT_RESULT_HEAD}{count}\n{part}",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except discord.HTTPException as exc:
            _LOG.warning("result_send_failed status=%s", getattr(exc, "status", "?"))
            return False
        return True

    async def thread_history(
        self, place: int, before: int, limit: int
    ) -> list[HistoryLine]:
        """The lines of a thread this bot opened, before message `before`
        (newest `limit`, oldest first, starting with the owner's message that
        opened it once the thread is read to its start). Picks a conversation
        back up after the app forgot it; read into RAM only."""
        if before == place:
            # The thread's opening message itself: nothing came before it.
            return []
        channel = await self._channel(place)
        if not self.is_our_thread(channel):
            return []
        found: list[discord.Message] = []
        async for message in channel.history(
            limit=limit, before=discord.Object(before) if before else None
        ):
            found.append(message)
        if len(found) < limit:
            try:
                # A thread opened from a message has that message's ID.
                found.append(await channel.parent.fetch_message(channel.id))
            except (discord.HTTPException, AttributeError):
                pass
        lines: list[HistoryLine] = []
        for message in reversed(found):
            content = message.clean_content.strip()
            if not content or message.type not in (
                discord.MessageType.default,
                discord.MessageType.reply,
            ):
                continue
            name = str(
                getattr(message.author, "display_name", None) or message.author.id
            )
            if (
                self._client.user is not None
                and message.author.id == self._client.user.id
            ):
                if content.startswith(AGENT_RESULT_HEAD):
                    body = content.split("\n", 1)[1] if "\n" in content else ""
                    lines.append((message.author.id, name, body.strip(), "agent"))
                else:
                    lines.append((message.author.id, name, content, "mine"))
            elif not message.author.bot:
                lines.append((message.author.id, name, content, "text"))
        return lines

    async def mark_task(self, channel_id: int, message_id: int, state: str) -> bool:
        """⚙️ on the owner's message while the Agent works on it, then ✅ or ❌."""
        mark = TASK_MARKS[state]
        try:
            channel = self._client.get_channel(
                channel_id
            ) or await self._client.fetch_channel(channel_id)
            message = channel.get_partial_message(message_id)
            await message.add_reaction(mark)
            if state != "accepted" and self._client.user is not None:
                try:
                    await message.remove_reaction(
                        TASK_MARKS["accepted"], self._client.user
                    )
                except discord.NotFound:
                    pass
        except (discord.HTTPException, AttributeError) as exc:
            _LOG.warning(
                "task_mark_failed state=%s error_type=%s", state, type(exc).__name__
            )
            return False
        _LOG.info("task_marked state=%s", state)
        return True

    async def _owner_dm(self) -> discord.abc.Messageable:
        """The owner's DMs, the only place the Agent's details are sent.
        Fails (discord.Forbidden) when the owner does not accept DMs from
        server members; then nothing is sent anywhere else instead."""
        owner_id = self._config.owner_user_id
        user = self._client.get_user(owner_id) or await self._client.fetch_user(
            owner_id
        )
        return user.dm_channel or await user.create_dm()

    async def send_private(self, text: str) -> bool:
        """Send the owner a DM (split at Discord's limit). False if it could
        not be delivered."""
        try:
            dm = await self._owner_dm()
            for start in range(0, max(len(text), 1), MAX_TEXT_CHARS):
                await dm.send(
                    text[start : start + MAX_TEXT_CHARS],
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except discord.HTTPException as exc:
            _LOG.warning("private_send_failed status=%s", getattr(exc, "status", "?"))
            return False
        return True

    async def send_approval(
        self, payload: dict[str, object], decide: Callable[[str, bool], Awaitable[bool]]
    ) -> None:
        """The approval buttons and the exact operation, in the owner's DMs
        only. Raises when the DM cannot be sent; the caller then denies it."""
        reason = {
            "protected": "碰到受保護檔案",
            "destructive": "刪除或清除資料",
            # EdgeAgent: a URL nobody gave it; it could carry data out.
            "new_url": "開啟一個不是你給的網址",
        }.get(str(payload.get("explicit", "")), "需要主人批准")
        if payload.get("after_web"):
            reason += "；讀過網頁之後的操作"
        details = json.dumps(payload.get("arguments", {}), ensure_ascii=False)[:1500]
        # EdgeAgent's own reading of the operation (PowerShell's parser for a
        # command, a ready-made tool's own plan), titled by EdgeAgent: sent
        # first, in as many messages as it takes.
        explain = str(payload.get("explain") or payload.get("explain_error") or "")
        title = str(
            payload.get("explain_title")
            or "這個操作在做什麼（EdgeAgent 自己算出的，不是模型猜的）"
        )
        view = AgentApprovalView(
            self._config.owner_user_id, str(payload["call_id"]), decide
        )
        try:
            dm = await self._owner_dm()
            if explain:
                text = f"{title}：\n{explain}"
                for start in range(0, len(text), MAX_TEXT_CHARS):
                    await dm.send(
                        text[start : start + MAX_TEXT_CHARS],
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            await dm.send(
                f"{reason} · {payload.get('tool', '')}\n{details}\n僅准許一次。",
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception:
            view.stop()
            raise
