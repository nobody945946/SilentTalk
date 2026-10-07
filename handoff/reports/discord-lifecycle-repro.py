import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest
from discord.voice_state import VoiceConnectionState

from silenttalk.config import DiscordConfig
from silenttalk.discord_voice import DiscordVoiceClient
from silenttalk.discord_messages import DiscordMessages


@pytest.mark.asyncio
async def test_retired_real_discord_runner_can_disconnect_replacement(monkeypatch):
    """Exercise the installed library poll loop and the app retirement owner."""
    client = DiscordVoiceClient(DiscordConfig('unused', 123), lambda *_: None)
    entered, reconnected = asyncio.Event(), asyncio.Event()
    guild = SimpleNamespace(id=456, me=SimpleNamespace(voice=None))
    channel = Mock(guild=guild)
    replacements_disconnected = []
    registered = {'voice': None}

    async def change_voice_state(*, channel, **kwargs):
        if channel is None and registered.get('voice') == 'replacement':
            replacements_disconnected.append(True)

    guild.change_voice_state = change_voice_state
    voice = Mock(channel=channel, guild=guild)
    connection = VoiceConnectionState(voice)
    connection.timeout = 0.1
    connection.self_deaf = False
    connection.self_mute = False
    connection.ws = Mock(close=AsyncMock())
    async def poll():
        if not entered.is_set():
            entered.set()
            raise discord.ConnectionClosed(Mock(), shard_id=None, code=4006)
        await asyncio.Event().wait()

    connection.ws.poll_event = poll
    voice._connection = connection
    async def disconnect(**kwargs):
        await connection.disconnect(wait=False)

    voice.disconnect = disconnect
    voice.cleanup = Mock(side_effect=lambda: registered.pop('voice', None))

    class Backoff:
        def delay(self):
            return 0.1

    async def reconnect(**kwargs):
        reconnected.set()

    monkeypatch.setattr('discord.voice_state.ExponentialBackoff', Backoff)
    connection._connect = reconnect
    connection._runner = asyncio.create_task(connection._poll_voice_ws(True))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await client._close_voice(voice)
        runner_alive = not connection._runner.done()
        registered['voice'] = 'replacement'
        await asyncio.wait_for(reconnected.wait(), 1)
        assert runner_alive, 'Retiring the voice unexpectedly joined its poll task'
        assert replacements_disconnected == [True]
    finally:
        connection._runner.cancel()
        await asyncio.gather(connection._runner, return_exceptions=True)
        connection._socket_reader.stop()
        await client.close()


def test_owner_at_text_channel_always_opens_agent_thread():
    bot = SimpleNamespace(id=1)
    client = SimpleNamespace(user=bot)
    messages = DiscordMessages(client, DiscordConfig('unused', 123), Mock(), lambda: None, lambda *_: None, threads_open=lambda: True)
    message = SimpleNamespace(channel=Mock(spec=discord.TextChannel), author=SimpleNamespace(id=123), mentions=[bot], reference=None)
    assert messages._opens_thread(message)
