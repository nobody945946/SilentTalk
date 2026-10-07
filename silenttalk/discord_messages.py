from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import discord

from silenttalk.config import DiscordConfig
from silenttalk.conversation import VOICE_ROOM
from silenttalk.state import AppState

_LOG = logging.getLogger(__name__)
import time
from pathlib import Path

from silenttalk.discord_channels import DiscordChannels

READABLE_IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
READABLE_DOCUMENTS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".log",
    ".xml",
    ".yaml",
    ".yml",
    ".ini",
    ".toml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".py",
    ".ps1",
    ".sql",
    ".c",
    ".h",
    ".cpp",
    ".cs",
    ".java",
    ".go",
    ".rs",
    ".pdf",
    ".docx",
}
MAX_ATTACHMENTS = 4
IMAGE_BYTES = 8_000_000
DOCUMENT_BYTES = 2_000_000


class DiscordMessages:
    """Route typed messages through an optional callback, independent of AI."""

    def __init__(
        self,
        client: discord.Client,
        config: DiscordConfig,
        channels: DiscordChannels,
        voice: Callable[[], object],
        status: Callable[[AppState, str], None],
        *,
        callback: Callable[..., None] | None = None,
        threads_open: Callable[[], bool] | None = None,
        names: Callable[[str], bool] | None = None,
    ):
        self._client = client
        self._config = config
        self._channels = channels
        self._voice = voice
        self._status = status
        self.callback = callback if config.text_chat else None
        self._threads_open = threads_open or (lambda: False)
        self.name_matches = names or (lambda _: False)

    def apply_config(self, config: DiscordConfig) -> None:
        self._config = config

    async def receive(self, message: discord.Message) -> None:
        """Typed lines the character takes part in: the chat of the voice
        channel the bot sits in; the owner's @ in a text channel, which opens
        his Agent thread there, and his lines in it (nobody else's: they are
        nobody's work); and in any text channel a line that @s or names the
        character, which is a chat with it right there. Other text-channel
        messages are not read, and nothing typed is written to disk
        (records.py keeps transcripts only on the records drive)."""
        callback = self.callback
        if callback is None:
            return
        if message.author.bot or (
            self._client.user and message.author.id == self._client.user.id
        ):
            return
        content = message.clean_content.strip()
        files = self._attachments(message)
        if not content and not files:
            return  # a sticker, an embed or a file no one can read
        if files:
            names = "、".join(name for name, _ in files)
            content = f"{content}（附件：{names}）" if content else f"（附件：{names}）"
        voice = self._voice()
        channel = message.channel
        agent = False
        if voice is not None and channel.id == voice.channel.id:
            place, addressed = VOICE_ROOM, self._mentions_me(message)
        elif self._channels.is_our_thread(channel) and self._threads_open():
            if message.author.id != self._config.owner_user_id:
                return
            place, addressed, agent = channel.id, True, True
        elif self._opens_thread(message):
            thread = await self._open_thread(message)
            if thread is None:
                return
            place, addressed, agent = thread.id, True, True
        elif (
            isinstance(channel, discord.TextChannel)
            and self._threads_open()
            and (self._mentions_me(message) or self.name_matches(content))
        ):
            place, addressed = channel.id, True
        else:
            return
        name = str(
            getattr(message.author, "display_name", None)
            or getattr(message.author, "name", None)
            or message.author.id
        )
        _LOG.info(
            "text_message_received char_count=%d addressed=%s place=%s",
            len(content),
            addressed,
            "voice" if place == VOICE_ROOM else ("thread" if agent else "channel"),
        )
        callback(
            message.author.id,
            name,
            content,
            addressed,
            place=place,
            channel_id=channel.id,
            message_id=message.id,
            agent=agent,
            attachments=tuple(files),
        )

    @staticmethod
    def _attachments(
        message: discord.Message,
    ) -> list[tuple[str, Callable[[], Awaitable[bytes]]]]:
        """The readable files of this message and of the message it replies
        to (the usual way to point at an image: reply to it and call the
        character): (name, read), read only when work is handed over."""
        replied = getattr(message.reference, "resolved", None)
        found = [*message.attachments, *getattr(replied, "attachments", ())]
        chosen = []
        for item in found:
            suffix = Path(item.filename).suffix.lower()
            limit = (
                IMAGE_BYTES
                if suffix in READABLE_IMAGES
                else DOCUMENT_BYTES
                if suffix in READABLE_DOCUMENTS
                else 0
            )
            if 0 < item.size <= limit:
                chosen.append((item.filename, item.read))
        return chosen[:MAX_ATTACHMENTS]

    def _mentions_me(self, message: discord.Message) -> bool:
        return self._client.user is not None and (
            self._client.user in message.mentions
            or getattr(getattr(message.reference, "resolved", None), "author", None)
            == self._client.user
        )

    def _opens_thread(self, message: discord.Message) -> bool:
        """Only the owner opens an Agent thread, by @ in a text channel. A
        reply to the character is a chat, not an @ (the owner, 2026-10-05),
        though Discord lists the replied-to author among the mentions."""
        return (
            isinstance(message.channel, discord.TextChannel)
            and message.author.id == self._config.owner_user_id
            and self._client.user is not None
            and self._client.user in message.mentions
            and message.reference is None
            and self._threads_open()
        )

    async def _open_thread(self, message: discord.Message) -> discord.Thread | None:
        me = getattr(message.guild, "me", None)
        name = f"{getattr(me, 'display_name', None) or 'Bot'}・{time.strftime('%m/%d %H:%M')}"
        try:
            thread = await message.create_thread(
                name=name[:100], auto_archive_duration=1440
            )
        except discord.HTTPException as exc:
            _LOG.warning("thread_open_failed status=%s", getattr(exc, "status", "?"))
            self._status(
                AppState.ERROR,
                "開不了討論串：請給 Bot 這個頻道的「建立公開討論串」和「在討論串中傳送訊息」權限。",
            )
            return None
        self._channels.remember_thread(thread.id)
        _LOG.info("thread_opened")
        return thread
