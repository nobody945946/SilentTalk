from __future__ import annotations

import asyncio
import time

import pytest

from silenttalk.config import DiscordConfig
from silenttalk.discord_voice import DiscordVoiceClient


@pytest.mark.asyncio
async def test_close_cancels_voice_monitor_task() -> None:
    client = DiscordVoiceClient(DiscordConfig("unused", 123), lambda *_: None)
    client._voice_monitor_task = asyncio.create_task(asyncio.sleep(60))
    client._voice_reconcile_task = asyncio.create_task(asyncio.sleep(60))
    await client.close()
    assert client._voice_monitor_task is None
    assert client._voice_reconcile_task is None


def test_reconnect_failure_uses_exponential_backoff() -> None:
    config = DiscordConfig(
        "unused",
        123,
        voice_reconnect_cooldown_seconds=2.0,
        voice_reconnect_max_interval_seconds=10.0,
    )
    client = DiscordVoiceClient(config, lambda *_: None)
    client._schedule_voice_reconcile = lambda delay=None: None  # type: ignore[method-assign]

    client._record_reconnect_failure()
    first_deadline = client._next_reconnect_at
    assert 0.0 < first_deadline - time.monotonic() <= 2.0
    assert client._reconnect_delay == 4.0

    client._record_reconnect_failure()
    assert client._reconnect_delay == 8.0

    client._record_reconnect_failure()
    assert client._reconnect_delay == 10.0


@pytest.mark.asyncio
async def test_owner_missing_grace_does_not_disconnect_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DiscordConfig("unused", 123, owner_leave_grace_seconds=8.0)
    client = DiscordVoiceClient(config, lambda *_: None)
    fake_voice = object()
    monkeypatch.setattr(
        type(client),
        "voice_clients",
        property(lambda _: [fake_voice]),
    )
    monkeypatch.setattr(client, "_find_owner_channel", lambda: None)
    follow_calls: list[object] = []

    async def fake_follow(channel: object) -> None:
        follow_calls.append(channel)

    monkeypatch.setattr(client, "_follow", fake_follow)
    monkeypatch.setattr(client, "_schedule_voice_reconcile", lambda delay=None: None)

    await client.sync_owner_voice()

    assert follow_calls == []
    assert client._owner_missing_since is not None
