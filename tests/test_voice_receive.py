from __future__ import annotations

from dataclasses import dataclass

from silenttalk.config import DiscordConfig
from silenttalk.discord_voice import DiscordVoiceClient


@dataclass
class FakeUser:
    id: int
    name: str
    bot: bool = False

    @property
    def display_name(self) -> str:
        return self.name


@dataclass
class FakeVoiceData:
    pcm: bytes


def test_voice_receive_ignores_owner_and_bots_but_keeps_other_people() -> None:
    heard: list[tuple[int, str, bytes]] = []
    client = DiscordVoiceClient(
        DiscordConfig("unused", 123),
        lambda *_: None,
        pcm_callback=lambda user_id, name, pcm: heard.append((user_id, name, pcm)),
    )

    client._on_voice_pcm(FakeUser(123, "Owner"), FakeVoiceData(b"owner"))  # type: ignore[arg-type]
    client._on_voice_pcm(FakeUser(456, "OtherBot", True), FakeVoiceData(b"bot"))  # type: ignore[arg-type]
    client._on_voice_pcm(FakeUser(789, "Alice"), FakeVoiceData(b"human"))  # type: ignore[arg-type]

    assert heard == [(789, "Alice", b"human")]
