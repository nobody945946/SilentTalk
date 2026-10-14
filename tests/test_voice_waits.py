"""Waiting for the voice connection and for receive: woken where that state
comes up, never by asking again on a timer."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from discord.ext import voice_recv

from silenttalk.config import DiscordConfig
from silenttalk.discord_voice import DiscordVoiceClient
from silenttalk.smoke import wait_for_owner_voice

# Windows fires a timer up to one clock tick (15.6 ms) before its time
# (asyncio's clock resolution, the kernel's timer tick): lower bounds allow it.
TICK = 0.02


class _Voice:
    def is_connected(self) -> bool:
        return True


def _client(
    monkeypatch: pytest.MonkeyPatch, voices: list[object]
) -> tuple[DiscordVoiceClient, list[int]]:
    """A client whose voice_clients is `voices`; the list counts how often
    a waiter looked at the connection."""
    monkeypatch.setattr(
        DiscordVoiceClient, "voice_clients", property(lambda self: voices)
    )
    client = DiscordVoiceClient(
        DiscordConfig("unused", 123), lambda *_: None, pcm_callback=lambda *_: None
    )
    looks = [0]
    active = client.active_voice

    def counted() -> object:
        looks[0] += 1
        return active()

    monkeypatch.setattr(client, "active_voice", counted)
    return client, looks


@pytest.mark.asyncio
async def test_wait_until_connected_wakes_when_the_connection_comes_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    voices: list[object] = []
    client, looks = _client(monkeypatch, voices)
    loop = asyncio.get_running_loop()

    async def reconcile() -> None:
        await asyncio.sleep(0.3)
        voices.append(_Voice())
        client._mark_voice_healthy()

    task = asyncio.create_task(reconcile())
    started = loop.time()
    try:
        assert await client.wait_until_connected(5.0)
        assert 0.3 - TICK <= loop.time() - started < 1.0
        assert looks == [2]  # before sleeping, and once when woken
    finally:
        await task
        await client.close()


@pytest.mark.asyncio
async def test_wait_until_connected_sleeps_to_its_deadline_without_looking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, looks = _client(monkeypatch, [])
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        assert not await client.wait_until_connected(0.4)
        assert 0.4 - TICK <= loop.time() - started < 1.0
        assert looks == [2]  # before sleeping, and at the deadline
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_a_wake_that_no_longer_holds_is_waited_past(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    voices: list[object] = []
    client, looks = _client(monkeypatch, voices)

    async def flap() -> None:
        await asyncio.sleep(0.05)
        client._voice_ready.set()  # set, but the connection is gone again
        await asyncio.sleep(0.1)
        voices.append(_Voice())
        client._mark_voice_healthy()

    task = asyncio.create_task(flap())
    try:
        assert await client.wait_until_connected(5.0)
        assert looks == [3]
    finally:
        await task
        await client.close()


@pytest.mark.asyncio
async def test_wait_until_voice_ready_raises_at_its_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(monkeypatch, [])

    async def owner_not_in_voice() -> None:
        pass

    monkeypatch.setattr(client, "sync_owner_voice", owner_not_in_voice)
    try:
        with pytest.raises(RuntimeError, match="尚未恢復連線"):
            await client.wait_until_voice_ready(timeout_seconds=0.2)
    finally:
        await client.close()


def _receiver() -> Mock:
    voice = Mock(spec=voice_recv.VoiceRecvClient)
    voice.is_connected.return_value = True
    voice.is_listening.return_value = False
    voice._connection = SimpleNamespace(dave_protocol_version=0)
    voice.channel = SimpleNamespace()
    voice.listen.side_effect = lambda *_a, **_k: setattr(
        voice.is_listening, "return_value", True
    )
    return voice


@pytest.mark.asyncio
async def test_wait_until_receiving_wakes_when_receive_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    voice = _receiver()
    client, looks = _client(monkeypatch, [voice])
    loop = asyncio.get_running_loop()

    async def start_listening() -> None:
        await asyncio.sleep(0.3)
        client._ensure_listening(voice)

    task = asyncio.create_task(start_listening())
    started = loop.time()
    try:
        assert await client.wait_until_receiving(5.0)
        assert 0.3 - TICK <= loop.time() - started < 1.0
        voice.listen.assert_called_once()
        assert looks == [2]
    finally:
        await task
        await client.close()


@pytest.mark.asyncio
async def test_wait_until_receiving_gives_up_at_its_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, looks = _client(monkeypatch, [_receiver()])  # connected, not listening
    try:
        assert not await client.wait_until_receiving(0.3)
        assert looks == [2]
    finally:
        await client.close()


class _SmokeClient:
    def __init__(self, connected: bool) -> None:
        self.connected = connected
        self.timeouts: list[float] = []

    async def wait_until_connected(self, timeout: float) -> bool:
        self.timeouts.append(timeout)
        return self.connected

    def voice_diagnostics(self) -> tuple[int, int, bool]:
        return 2, 5, False


@pytest.mark.asyncio
async def test_voice_smoke_waits_once_for_the_owners_voice() -> None:
    client = _SmokeClient(connected=True)
    await wait_for_owner_voice(client)  # type: ignore[arg-type]
    assert client.timeouts == [20.0]


@pytest.mark.asyncio
async def test_voice_smoke_reports_what_the_bot_sees_at_the_deadline() -> None:
    client = _SmokeClient(connected=False)
    with pytest.raises(RuntimeError) as raised:
        await wait_for_owner_voice(client)  # type: ignore[arg-type]
    assert "可見伺服器=2" in str(raised.value)
    assert "可見語音頻道=5" in str(raised.value)
    assert "Owner 可見=False" in str(raised.value)
