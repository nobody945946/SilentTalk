from silenttalk.config import DiscordConfig
from silenttalk.discord_voice import DiscordVoiceClient


def test_gateway_intents_are_minimal() -> None:
    client = DiscordVoiceClient(DiscordConfig("unused", 123), lambda *_: None)
    assert client.intents.guilds
    assert client.intents.voice_states
    assert not client.intents.message_content
    assert not client.intents.members
