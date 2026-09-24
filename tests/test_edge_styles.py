import pytest

from silenttalk.config import TTSConfig
from silenttalk.speech_settings import combine_edge_rate
from silenttalk.tts.edge import resolve_speech_settings


def test_space_marine_style_selects_english_low_voice() -> None:
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
    assert audio_filter is not None and "bass=" in audio_filter


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
        "/mechanicus For the Omnissiah!",
        config,
    )
    assert text == "For the Omnissiah!"
    assert voice == "en-GB-RyanNeural"
    assert rate == "-16%"
    assert pitch == "-35Hz"
    assert audio_filter is not None and "aecho=" in audio_filter


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
