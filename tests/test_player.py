from __future__ import annotations

from pathlib import Path

import pytest

from silenttalk.config import AudioConfig
from silenttalk.discord_voice import DiscordAudioPlayer
from silenttalk.tts.base import AudioResult


class FakeVoice:
    def __init__(self) -> None:
        self.play_calls = 0
        self.errors: list[Exception | None] = []

    def play(self, source: object, *, after: object) -> None:
        self.play_calls += 1
        after(self.errors.pop(0) if self.errors else None)

    def is_playing(self) -> bool:
        return False


class FakeClient:
    def __init__(self, voice: FakeVoice) -> None:
        self.voice = voice
        self.connect_attempts = 0
        self.disconnect_attempts = 0

    def active_voice(self) -> FakeVoice:
        return self.voice

    async def sync_owner_voice(self) -> None:
        return None

    async def connect(self) -> None:
        self.connect_attempts += 1

    async def disconnect(self) -> None:
        self.disconnect_attempts += 1


@pytest.mark.asyncio
async def test_multiple_messages_reuse_existing_voice_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "silenttalk.discord_voice.discord.FFmpegOpusAudio",
        lambda *args, **kwargs: object(),
    )
    audio_path = tmp_path / "speech.mp3"
    audio_path.write_bytes(b"audio")
    result = AudioResult(audio_path, None, None, "mp3")
    voice = FakeVoice()
    client = FakeClient(voice)
    player = DiscordAudioPlayer(client, AudioConfig())  # type: ignore[arg-type]

    await player.play(result)
    await player.play(result)

    assert voice.play_calls == 2
    assert client.connect_attempts == 0
    assert client.disconnect_attempts == 0


@pytest.mark.asyncio
async def test_ffmpeg_filter_is_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    def fake_source(*args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(
        "silenttalk.discord_voice.discord.FFmpegOpusAudio",
        fake_source,
    )
    audio_path = tmp_path / "speech.mp3"
    audio_path.write_bytes(b"audio")
    voice = FakeVoice()
    player = DiscordAudioPlayer(FakeClient(voice), AudioConfig())  # type: ignore[arg-type]

    await player.play(
        AudioResult(
            audio_path,
            None,
            None,
            "mp3",
            ffmpeg_filter="highpass=f=110,aecho=0.8:0.65:28:0.22",
        )
    )

    assert "-af" in str(calls[0]["options"])
    assert "aecho=" in str(calls[0]["options"])


@pytest.mark.asyncio
async def test_voice_drop_does_not_replay_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "silenttalk.discord_voice.discord.FFmpegOpusAudio",
        lambda *args, **kwargs: object(),
    )
    audio_path = tmp_path / "speech.mp3"
    audio_path.write_bytes(b"audio")
    voice = FakeVoice()
    voice.errors = [RuntimeError("voice transport dropped"), None]
    client = FakeClient(voice)
    player = DiscordAudioPlayer(client, AudioConfig(playback_timeout_seconds=10))

    with pytest.raises(RuntimeError, match="未重播"):
        await player.play(AudioResult(audio_path, None, None, "mp3"))

    assert voice.play_calls == 1
    assert client.connect_attempts == 0
