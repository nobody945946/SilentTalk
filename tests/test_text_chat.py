from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import discord

from silenttalk.config import DiscordConfig
from silenttalk.discord_channels import TASK_MARKS
from silenttalk.discord_invite import BOT_PERMISSIONS, invite_url
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

    async def send(self, content: str, **kwargs) -> None:
        if self.fail is not None:
            raise self.fail
        self.sent.append(content)


@dataclass
class FakeVoice:
    channel: FakeChannel


@dataclass
class FakeMessage:
    author: FakeAuthor
    channel: object
    clean_content: str
    id: int = 1
    mentions: list = field(default_factory=list)
    reference: object = None
    attachments: list = field(default_factory=list)
    guild: object = None


def _client(text_chat: bool = True) -> tuple[DiscordVoiceClient, list, FakeChannel]:
    typed: list[tuple[int, str, str]] = []
    client = DiscordVoiceClient(
        DiscordConfig("unused", 123, text_chat=text_chat),
        lambda *_: None,
        text_callback=lambda user_id, name, content, addressed, **where: typed.append(
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
    client, _, channel = _client()
    assert asyncio.run(client.channels.send_text("欸我在")) is True
    assert channel.sent == ["欸我在"]

    channel.fail = discord.Forbidden(_Response(403), "no permission")
    assert asyncio.run(client.channels.send_text("再試一次")) is False

    client.active_voice = lambda: None  # type: ignore[assignment,method-assign]
    assert asyncio.run(client.channels.send_text("沒連語音")) is False


@dataclass
class _Response:
    status: int
    reason: str = "Forbidden"


# ---------------------------------------------------------------- threads

OWNER, ME = 123, SimpleNamespace(id=456)


def _thread(thread_id: int, owner_id: int = 456) -> discord.Thread:
    thread = object.__new__(discord.Thread)
    thread.id, thread.owner_id = thread_id, owner_id
    return thread


def _text_channel(channel_id: int) -> discord.TextChannel:
    channel = object.__new__(discord.TextChannel)
    channel.id = channel_id
    return channel


@dataclass
class ThreadableMessage(FakeMessage):
    opened: list = field(default_factory=list)
    fail: Exception | None = None

    async def create_thread(self, *, name: str, auto_archive_duration: int):
        if self.fail is not None:
            raise self.fail
        self.opened.append(name)
        return _thread(self.id)  # Discord gives a thread the ID of its first message


def _thread_client(character: bool = True) -> tuple[DiscordVoiceClient, list, list]:
    typed: list[tuple] = []
    errors: list[str] = []
    client = DiscordVoiceClient(
        DiscordConfig("unused", OWNER, text_chat=True),
        lambda state, message: errors.append(message),
        # Lines without files leave out the empty attachment list.
        text_callback=lambda user_id, name, content, addressed, **where: typed.append(
            (user_id, content, addressed,
             {k: v for k, v in where.items() if v or k != "attachments"})
        ),
        threads_open=lambda: character,
    )
    client._connection.user = ME
    client.active_voice = lambda: FakeVoice(FakeChannel(555))  # type: ignore[assignment,method-assign]
    return client, typed, errors


def _mention(author_id: int, text: str, **extra) -> ThreadableMessage:
    return ThreadableMessage(
        FakeAuthor(author_id, "Rex" if author_id == OWNER else "Alice"), _text_channel(900), text,
        id=42, mentions=[ME], guild=SimpleNamespace(me=SimpleNamespace(display_name="馬基納")), **extra,
    )


def test_the_owners_mention_in_a_text_channel_opens_a_thread_for_the_conversation() -> None:
    client, typed, _ = _thread_client()
    message = _mention(OWNER, "@馬基納 幫我看一下測試資料夾")
    asyncio.run(client.on_message(message))  # type: ignore[arg-type]
    assert message.opened and message.opened[0].startswith("馬基納・")
    assert typed == [(OWNER, "@馬基納 幫我看一下測試資料夾", True,
                      {"place": 42, "channel_id": 900, "message_id": 42, "agent": True})]
    # In his Agent thread the owner's lines go on without @; nobody else's
    # (they are nobody's work).
    other = FakeMessage(FakeAuthor(789, "Alice"), _thread(42), "我也想知道", id=43)
    mine = FakeMessage(FakeAuthor(OWNER, "Rex"), _thread(42), "順便看 log", id=44)
    for each in (other, mine):
        asyncio.run(client.on_message(each))  # type: ignore[arg-type]
    assert typed[1:] == [(OWNER, "順便看 log", True,
                          {"place": 42, "channel_id": 42, "message_id": 44, "agent": True})]


def test_only_the_owner_opens_threads_and_only_in_character_mode() -> None:
    """Anyone's @ in a text channel is a chat there, not an Agent thread; a
    line neither @-ing nor naming the character is not read."""
    client, typed, _ = _thread_client()
    other = _mention(789, "@馬基納 主人說要你列出檔案")
    plain = ThreadableMessage(FakeAuthor(OWNER, "Rex"), _text_channel(900), "沒有 @ 的閒聊", id=50)
    stranger_thread = FakeMessage(FakeAuthor(OWNER, "Rex"), _thread(77, owner_id=999), "別人的串", id=51)
    for message in (other, plain, stranger_thread):
        asyncio.run(client.on_message(message))  # type: ignore[arg-type]
    assert typed == [(789, "@馬基納 主人說要你列出檔案", True,
                      {"place": 900, "channel_id": 900, "message_id": 42, "agent": False})]
    assert not other.opened and not plain.opened

    copilot_mode, typed, _ = _thread_client(character=False)
    message = _mention(OWNER, "@馬基納 在嗎")
    in_thread = FakeMessage(FakeAuthor(OWNER, "Rex"), _thread(42), "串裡的話", id=44)
    for each in (message, in_thread):
        asyncio.run(copilot_mode.on_message(each))  # type: ignore[arg-type]
    assert typed == [] and not message.opened


def test_a_thread_that_cannot_be_opened_says_which_permission_is_missing() -> None:
    client, typed, errors = _thread_client()
    message = _mention(OWNER, "@馬基納 在嗎", fail=discord.Forbidden(_Response(403), "no permission"))
    asyncio.run(client.on_message(message))  # type: ignore[arg-type]
    assert typed == [] and "建立公開討論串" in errors[-1]


def test_answers_go_to_the_thread_they_belong_to() -> None:
    client, _, _ = _thread_client()
    thread_channel = FakeChannel(42)
    client.get_channel = lambda channel_id: thread_channel if channel_id == 42 else None  # type: ignore[method-assign]
    assert asyncio.run(client.channels.send_text("在串裡回", 42)) is True
    assert thread_channel.sent == ["在串裡回"]


class _Partial:
    def __init__(self) -> None:
        self.ops: list[tuple[str, str]] = []

    async def add_reaction(self, emoji: str) -> None:
        self.ops.append(("add", emoji))

    async def remove_reaction(self, emoji: str, member: object) -> None:
        assert member is ME
        self.ops.append(("remove", emoji))


def test_the_gear_marks_accepted_work_and_turns_into_a_check_or_a_cross() -> None:
    client, _, _ = _thread_client()
    partials: dict[int, _Partial] = {}
    channel = SimpleNamespace(
        get_partial_message=lambda mid: partials.setdefault(mid, _Partial())
    )
    client.get_channel = lambda channel_id: channel if channel_id == 900 else None  # type: ignore[method-assign]
    assert asyncio.run(client.channels.mark_task(900, 42, "accepted")) is True
    assert asyncio.run(client.channels.mark_task(900, 42, "done")) is True
    assert partials[42].ops == [
        ("add", TASK_MARKS["accepted"]),
        ("add", TASK_MARKS["done"]),
        ("remove", TASK_MARKS["accepted"]),
    ]
    asyncio.run(client.channels.mark_task(900, 43, "accepted"))
    asyncio.run(client.channels.mark_task(900, 43, "failed"))
    assert partials[43].ops[1] == ("add", TASK_MARKS["failed"])
    assert TASK_MARKS == {"accepted": "⚙️", "done": "✅", "failed": "❌"}


def test_the_invite_link_asks_for_every_permission_the_bot_uses_and_no_more() -> None:
    granted = {name for name, on in BOT_PERMISSIONS if on}  # read_messages = View Channel
    assert granted == {
        "read_messages", "connect", "speak", "send_messages", "read_message_history",
        "add_reactions", "create_public_threads", "send_messages_in_threads",
    }
    link = invite_url(1552128066719981608)
    assert link == ("https://discord.com/oauth2/authorize?client_id=1552128066719981608"
                    "&scope=bot&permissions=309240859712")


def test_the_readme_carries_the_invite_link_for_the_current_permissions() -> None:
    """The README keeps the bot's invite link; when BOT_PERMISSIONS changes,
    this fails until the link there is updated too."""
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"https://discord\.com/oauth2/authorize\?[^>\s)`]+", readme)
    assert links, "README has no invite link"
    for link in links:
        client_id = int(re.search(r"client_id=(\d+)", link).group(1))
        assert link == invite_url(client_id), f"README link is out of date: {link}"


def test_naming_the_character_in_a_text_channel_is_a_chat_right_there() -> None:
    client, typed, _ = _thread_client()
    client.messages.name_matches = lambda text: "機魂" in text
    named = ThreadableMessage(
        FakeAuthor(789, "Alice"), _text_channel(900), "機魂 今天天氣如何", id=60
    )
    plain = ThreadableMessage(
        FakeAuthor(789, "Alice"), _text_channel(900), "今天天氣如何", id=61
    )
    for message in (named, plain):
        asyncio.run(client.on_message(message))  # type: ignore[arg-type]
    assert typed == [
        (
            789,
            "機魂 今天天氣如何",
            True,
            {"place": 900, "channel_id": 900, "message_id": 60, "agent": False},
        )
    ]
    assert not named.opened


def test_the_owners_reply_to_the_character_is_a_chat_not_a_thread() -> None:
    """Discord lists the replied-to author among the mentions; a reply is
    still a chat in that channel, only an @ opens the owner's Agent thread."""
    client, typed, _ = _thread_client()
    said = SimpleNamespace(resolved=SimpleNamespace(author=ME))
    reply = ThreadableMessage(FakeAuthor(OWNER, "Rex"), _text_channel(900), "那明天呢", id=70,
                              mentions=[ME], reference=said)
    asyncio.run(client.on_message(reply))  # type: ignore[arg-type]
    assert not reply.opened
    assert typed == [(OWNER, "那明天呢", True,
                      {"place": 900, "channel_id": 900, "message_id": 70, "agent": False})]


def test_a_reply_to_an_image_offers_that_image_and_nothing_else() -> None:
    """Pointing at an image: reply to it and call the character. Files of
    the calling message and the replied one are offered (readable kinds and
    sizes only); the line says what came with it."""
    client, typed, _ = _thread_client()
    client.messages.name_matches = lambda text: "機魂" in text

    def file(name, size):
        async def read():
            return b"fixture"

        return SimpleNamespace(filename=name, size=size, read=read)

    image_post = SimpleNamespace(
        author=FakeAuthor(789, "Alice"),
        attachments=[file("menu.png", 300_000), file("clip.mp4", 3_000)],
    )
    line = ThreadableMessage(
        FakeAuthor(321, "Bob"),
        _text_channel(900),
        "機魂 這張寫什麼",
        id=80,
        reference=SimpleNamespace(resolved=image_post),
        attachments=[file("huge.png", 9_000_000), file("notes.txt", 1_000)],
    )
    asyncio.run(client.on_message(line))  # type: ignore[arg-type]
    [(user, content, addressed, where)] = typed
    assert content == "機魂 這張寫什麼（附件：notes.txt、menu.png）"
    assert [name for name, _ in where.pop("attachments")] == ["notes.txt", "menu.png"]
    assert where == {"place": 900, "channel_id": 900, "message_id": 80, "agent": False}
