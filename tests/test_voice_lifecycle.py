"""A retired voice connection can never act on its replacement.

From the laptop's audit (2026-10-07): discord.py's websocket poller, asleep in
its reconnect back-off after a 4006, woke after the app had replaced the
connection, left the channel and connected again; with the app reconnecting
too, the bot was knocked out every ~20 s. This runs the installed library's
real poll loop and disconnect, with only the network faked.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest
from discord.voice_state import VoiceConnectionState

from silenttalk.config import DiscordConfig
from silenttalk.discord_voice import DiscordVoiceClient


@pytest.mark.asyncio
async def test_a_retired_connection_never_leaves_or_reconnects_over_its_replacement(monkeypatch):
    client = DiscordVoiceClient(DiscordConfig("unused", 123), lambda *_: None)
    failed, reconnected = asyncio.Event(), asyncio.Event()
    guild = SimpleNamespace(id=456, me=SimpleNamespace(voice=None))
    registered = {"voice": None}
    left_replacement: list[bool] = []

    async def change_voice_state(*, channel, **kwargs):
        if channel is None and registered.get("voice") == "replacement":
            left_replacement.append(True)

    guild.change_voice_state = change_voice_state
    voice = Mock(channel=Mock(guild=guild), guild=guild)
    connection = VoiceConnectionState(voice)
    connection.timeout = 0.1
    connection.self_deaf = connection.self_mute = False
    connection.ws = Mock(close=AsyncMock())

    async def poll():
        if not failed.is_set():
            failed.set()
            raise discord.ConnectionClosed(Mock(), shard_id=None, code=4006)
        await asyncio.Event().wait()

    async def reconnect(**kwargs):
        reconnected.set()

    async def disconnect(**kwargs):
        await connection.disconnect(wait=False)

    class Backoff:
        def delay(self):
            return 0.1

    connection.ws.poll_event = poll
    connection._connect = reconnect
    voice._connection = connection
    voice.disconnect = disconnect
    voice.cleanup = Mock(side_effect=lambda: registered.pop("voice", None))
    monkeypatch.setattr("discord.voice_state.ExponentialBackoff", Backoff)
    connection._runner = asyncio.create_task(connection._poll_voice_ws(True))
    runner = connection._runner
    try:
        await asyncio.wait_for(failed.wait(), 1)
        await client._close_voice(voice)
        assert runner.done() and connection._runner is None
        registered["voice"] = "replacement"
        await asyncio.sleep(0.3)  # past the SDK's back-off
        assert not left_replacement
        assert not reconnected.is_set()
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)
        connection._socket_reader.stop()
        await client.close()


@pytest.mark.asyncio
async def test_retiring_a_client_whose_sdk_tasks_ended_just_disconnects() -> None:
    client = DiscordVoiceClient(DiscordConfig("unused", 123), lambda *_: None)
    voice = Mock(_connection=SimpleNamespace(_runner=None, _connector=None), disconnect=AsyncMock())
    await client._close_voice(voice)
    voice.disconnect.assert_awaited_once_with(force=True)
    await client.close()
