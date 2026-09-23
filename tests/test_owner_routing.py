from __future__ import annotations

from dataclasses import dataclass

import pytest

from silenttalk.config import DiscordConfig
from silenttalk.discord_voice import DiscordVoiceClient


@dataclass
class FakeGuild:
    id: int


class FakeChannel:
    def __init__(self, channel_id: int, guild: FakeGuild, name: str) -> None:
        self.id = channel_id
        self.guild = guild
        self.name = name
        self.connect_calls = 0

    async def connect(self, **kwargs: object) -> None:
        self.connect_calls += 1


class FakeVoice:
    def __init__(self, channel: FakeChannel) -> None:
        self.channel = channel
        self.guild = channel.guild
        self.connected = True
        self.disconnect_calls = 0
        self.moves: list[FakeChannel] = []

    def is_connected(self) -> bool:
        return self.connected

    async def disconnect(self, *, force: bool) -> None:
        self.disconnect_calls += 1
        self.connected = False

    async def move_to(self, channel: FakeChannel) -> None:
        self.moves.append(channel)
        self.channel = channel

    def cleanup(self) -> None:
        self.connected = False


def _client(
    monkeypatch: pytest.MonkeyPatch, voices: list[FakeVoice]
) -> DiscordVoiceClient:
    monkeypatch.setattr(
        DiscordVoiceClient, "voice_clients", property(lambda self: voices)
    )
    return DiscordVoiceClient(DiscordConfig("unused", 123), lambda *_: None)


@pytest.mark.asyncio
async def test_same_server_move_reuses_voice_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = FakeGuild(1)
    first = FakeChannel(10, guild, "A")
    second = FakeChannel(11, guild, "B")
    voice = FakeVoice(first)
    client = _client(monkeypatch, [voice])

    await client._follow(second)

    assert voice.moves == [second]
    assert voice.disconnect_calls == 0
    assert second.connect_calls == 0


@pytest.mark.asyncio
async def test_cross_server_switch_disconnects_then_connects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_channel = FakeChannel(10, FakeGuild(1), "Old")
    new_channel = FakeChannel(20, FakeGuild(2), "New")
    old_voice = FakeVoice(old_channel)
    client = _client(monkeypatch, [old_voice])

    await client._follow(new_channel)

    assert old_voice.disconnect_calls == 1
    assert old_voice.moves == []
    assert new_channel.connect_calls == 1


@pytest.mark.asyncio
async def test_owner_leaving_disconnects_all_stale_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    voices = [
        FakeVoice(FakeChannel(10, FakeGuild(1), "A")),
        FakeVoice(FakeChannel(20, FakeGuild(2), "B")),
    ]
    client = _client(monkeypatch, voices)

    await client._follow(None)

    assert [voice.disconnect_calls for voice in voices] == [1, 1]


@pytest.mark.asyncio
async def test_stale_voice_client_is_cleaned_before_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_channel = FakeChannel(10, FakeGuild(1), "Stale")
    target_channel = FakeChannel(20, FakeGuild(1), "Target")
    stale_voice = FakeVoice(stale_channel)
    stale_voice.connected = False
    client = _client(monkeypatch, [stale_voice])

    await client._follow(target_channel)

    assert stale_voice.disconnect_calls == 1
    assert target_channel.connect_calls == 1
