from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from silenttalk.config import DiscordConfig
from silenttalk.discord_voice import DiscordVoiceClient


@dataclass
class FakeAuthor:
    id: int
    display_name: str
    bot: bool = False


@dataclass
class FakeChannel:
    id: int
    sent: list[str] = field(default_factory=list)
    fail: Exception | None = None

    async def send(self, content: str) -> None:
        if self.fail is not None:
            raise self.fail
        self.sent.append(content)


@dataclass
class FakeVoice:
    channel: FakeChannel


@dataclass
class FakeMessage:
    author: FakeAuthor
    channel: FakeChannel
    clean_content: str


def _client(text_chat: bool = True) -> tuple[DiscordVoiceClient, list, FakeChannel]:
    typed: list[tuple[int, str, str]] = []
    client = DiscordVoiceClient(
        DiscordConfig("unused", 123, text_chat=text_chat),
        lambda *_: None,
        text_callback=lambda user_id, name, content, addressed: typed.append(
            (user_id, name, content, addressed)
        ),
    )
    channel = FakeChannel(555)
    client.active_voice = lambda: FakeVoice(channel)  # type: ignore[assignment,method-assign]
    return client, typed, channel


def test_only_the_voice_channels_own_chat_is_read() -> None:
    client, typed, channel = _client()
    other = FakeChannel(999)
    alice, bot = FakeAuthor(789, "Alice"), FakeAuthor(456, "OtherBot", bot=True)

    for message in (
        FakeMessage(alice, other, "另一個頻道的訊息"),
        FakeMessage(bot, channel, "機器人自己講話"),
        FakeMessage(alice, channel, "   "),  # sticker / attachment only
        FakeMessage(alice, channel, "  凱哥晚餐吃什麼  "),
    ):
        asyncio.run(client.on_message(message))  # type: ignore[arg-type]

    assert typed == [(789, "Alice", "凱哥晚餐吃什麼", False)]


def test_text_is_not_read_without_the_callback() -> None:
    client, typed, channel = _client()
    client.set_text_callback(None)

    asyncio.run(client.on_message(FakeMessage(FakeAuthor(789, "Alice"), channel, "有人嗎")))  # type: ignore[arg-type]

    assert typed == []


def test_message_content_intent_is_only_requested_when_text_chat_is_on() -> None:
    on, _, _ = _client(text_chat=True)
    off, _, _ = _client(text_chat=False)

    assert on.intents.message_content and on.intents.guild_messages
    assert not off.intents.message_content and not off.intents.guild_messages


def test_sending_reports_failure_instead_of_raising() -> None:
    import discord

    client, _, channel = _client()
    assert asyncio.run(client.send_text("欸我在")) is True
    assert channel.sent == ["欸我在"]

    channel.fail = discord.Forbidden(_Response(403), "no permission")
    assert asyncio.run(client.send_text("再試一次")) is False

    client.active_voice = lambda: None  # type: ignore[assignment,method-assign]
    assert asyncio.run(client.send_text("沒連語音")) is False


@dataclass
class _Response:
    status: int
    reason: str = "Forbidden"
