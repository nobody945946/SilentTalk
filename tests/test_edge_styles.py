import pytest

from silenttalk.config import TTSConfig
from silenttalk.speech_settings import combine_edge_rate
from silenttalk.tts.edge import resolve_speech_settings
from silenttalk.voice_styles import voice_style_choices


def test_space_marine_uses_deeper_base_voice_without_extreme_pitch_shift() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    text, voice, rate, pitch, volume, audio_filter = resolve_speech_settings(
        "For the Emperor!",
        config,
        voice_style="space_marine",
    )
    assert text == "For the Emperor!"
    assert voice == "en-US-AndrewNeural"
    assert rate == "-6%"
    assert pitch == "-14Hz"
    assert volume == "+8%"
    assert audio_filter is not None and "bass=" in audio_filter


def test_major_roles_use_distinct_base_voices() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    role_to_expected_voice = {
        "space_marine": "en-US-AndrewNeural",
        "space_marine_commander": "en-US-ChristopherNeural",
        "mechanicus": "en-US-EricNeural",
        "inquisitor": "en-US-RogerNeural",
        "chaos": "en-US-GuyNeural",
        "british_officer": "en-GB-ThomasNeural",
        "battle_sister": "en-US-AriaNeural",
    }
    actual = {
        role: resolve_speech_settings("Test", config, voice_style=role)[1]
        for role in role_to_expected_voice
    }
    assert actual == role_to_expected_voice


def test_mechanicus_is_narrow_band_and_electronic() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    text, voice, _, pitch, _, audio_filter = resolve_speech_settings(
        "For the Omnissiah!",
        config,
        voice_style="mechanicus",
    )
    assert text == "For the Omnissiah!"
    assert voice == "en-US-EricNeural"
    assert pitch == "-6Hz"
    assert audio_filter is not None
    assert "highpass=" in audio_filter
    assert "lowpass=" in audio_filter
    assert "aecho=" in audio_filter


def test_speed_only_legacy_styles_are_hidden_from_dropdown() -> None:
    keys = {key for key, _ in voice_style_choices()}
    assert "slow" not in keys
    assert "fast" not in keys
    assert "deep" not in keys
    assert "cute" not in keys
    assert "space_marine" in keys
    assert "mechanicus" in keys
    assert "narrator" in keys


def test_ui_rate_multiplies_style_rate() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    _, _, rate, _, _, _ = resolve_speech_settings(
        "For the Emperor!",
        config,
        voice_style="space_marine",
        rate_multiplier=0.80,
    )
    assert rate == "-25%"


def test_legacy_style_prefix_still_works() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    text, voice, rate, pitch, _, audio_filter = resolve_speech_settings(
        "/mechanicus For the Omnissiah!",
        config,
    )
    assert text == "For the Omnissiah!"
    assert voice == "en-US-EricNeural"
    assert rate == "-4%"
    assert pitch == "-6Hz"
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
