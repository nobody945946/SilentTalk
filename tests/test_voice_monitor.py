from __future__ import annotations

import pytest

from silenttalk.config import DiscordConfig
from silenttalk.discord_voice import DiscordVoiceClient


@pytest.mark.asyncio
async def test_close_cancels_voice_monitor_task() -> None:
    client = DiscordVoiceClient(DiscordConfig("unused", 123), lambda *_: None)
    client._voice_monitor_task = __import__("asyncio").create_task(
        __import__("asyncio").sleep(60)
    )
    await client.close()
    assert client._voice_monitor_task is None
