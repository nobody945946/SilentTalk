import pytest

from silenttalk.config import TTSConfig
from silenttalk.speech_settings import combine_edge_rate
from silenttalk.tts.edge import resolve_speech_settings
from silenttalk.voice_styles import voice_style_choices


def test_space_marine_preserves_user_approved_v1_preset() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    text, voice, rate, pitch, volume, audio_filter = resolve_speech_settings(
        "For the Emperor!",
        config,
        voice_style="space_marine",
    )
    assert text == "For the Emperor!"
    assert voice == "en-US-ChristopherNeural"
    assert rate == "-12%"
    assert pitch == "-45Hz"
    assert volume == "+12%"
    assert audio_filter == (
        "bass=g=10:f=100,"
        "acompressor=threshold=-18dB:ratio=4:attack=5:release=80"
    )


def test_mechanicus_keeps_approved_voice_with_thicker_electronic_body() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    text, voice, rate, pitch, volume, audio_filter = resolve_speech_settings(
        "For the Omnissiah!",
        config,
        voice_style="mechanicus",
    )
    assert text == "For the Omnissiah!"
    assert voice == "en-US-EricNeural"
    assert rate == "-4%"
    assert pitch == "-6Hz"
    assert volume == "+4%"
    assert audio_filter is not None
    assert "bass=g=7:f=120" in audio_filter
    assert "highpass=f=95" in audio_filter
    assert "lowpass=f=3000" in audio_filter
    assert "aecho=0.8:0.68:24:0.22" in audio_filter


def test_battle_sister_is_stern_mature_female_preset() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    text, voice, rate, pitch, volume, audio_filter = resolve_speech_settings(
        "Faith is my shield!",
        config,
        voice_style="battle_sister",
    )
    assert text == "Faith is my shield!"
    assert voice == "en-GB-SoniaNeural"
    assert rate == "-4%"
    assert pitch == "-8Hz"
    assert volume == "+6%"
    assert audio_filter is not None
    assert "bass=g=3:f=150" in audio_filter
    assert "acompressor=" in audio_filter


def test_dropdown_contains_only_current_voice_presets() -> None:
    keys = [key for key, _ in voice_style_choices()]
    assert keys == ["default", "space_marine", "mechanicus", "battle_sister"]


def test_ui_rate_multiplies_style_rate() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    _, _, rate, _, _, _ = resolve_speech_settings(
        "For the Emperor!",
        config,
        voice_style="space_marine",
        rate_multiplier=0.80,
    )
    assert rate == "-30%"


def test_legacy_style_prefix_still_works() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    text, voice, rate, pitch, _, audio_filter = resolve_speech_settings(
        "/deep Testing",
        config,
    )
    assert text == "Testing"
    assert voice == "zh-TW-YunJheNeural"
    assert rate == "-8%"
    assert pitch == "-35Hz"
    assert audio_filter is None


def test_unknown_prefix_is_spoken_normally() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural", rate="-5%", pitch="+2Hz")
    text, voice, rate, pitch, _, audio_filter = resolve_speech_settings(
        "/hello 世界",
        config,
    )
    assert text == "/hello 世界"
    assert voice == "zh-TW-YunJheNeural"
    assert rate == "-5%"
    assert pitch == "+2Hz"
    assert audio_filter is None


def test_rate_combination_and_bounds() -> None:
    assert combine_edge_rate("+0%", 0.80) == "-20%"
    assert combine_edge_rate("-20%", 1.25) == "+0%"
    with pytest.raises(ValueError, match="語速倍率"):
        combine_edge_rate("+0%", 0.50)


def test_synthesis_goes_to_the_address_microsoft_answers() -> None:
    import edge_tts

    from silenttalk.tts import edge

    assert edge_tts.communicate.WSS_URL == edge.SYNTHESIS_URL
    # When edge-tts ships the new address itself, drop SYNTHESIS_URL.
    assert "msedgeservices" not in edge_tts.constants.WSS_URL


@pytest.mark.asyncio
async def test_a_busy_handshake_is_asked_once_more(monkeypatch) -> None:
    import aiohttp

    from silenttalk.tts import edge

    calls = []

    class Busy:
        async def stream(self):
            calls.append("busy")
            raise aiohttp.WSServerHandshakeError(None, (), status=429)
            yield  # an async generator

    class Speaks:
        async def stream(self):
            calls.append("ok")
            yield {"type": "audio", "data": b"mp3"}

    monkeypatch.setattr(edge, "_BUSY_RETRY_SECONDS", 0)
    makers = iter([Busy, Speaks])
    assert [d async for d in edge._audio(lambda: next(makers)())] == [b"mp3"]
    assert calls == ["busy", "ok"]
    makers = iter([Busy, Busy])
    with pytest.raises(aiohttp.WSServerHandshakeError):
        [d async for d in edge._audio(lambda: next(makers)())]
