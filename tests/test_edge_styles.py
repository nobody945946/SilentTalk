from silenttalk.config import TTSConfig
from silenttalk.tts.edge import resolve_speech_style, resolve_speech_volume


def test_space_marine_style_selects_english_low_voice() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    text, voice, rate, pitch, audio_filter = resolve_speech_style(
        "/space_marine For the Emperor!", config
    )
    assert text == "For the Emperor!"
    assert voice == "en-US-ChristopherNeural"
    assert rate == "-12%"
    assert pitch == "-45Hz"
    assert audio_filter is not None and "bass=" in audio_filter


def test_mechanicus_style_has_electronic_post_process() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural")
    text, voice, _, pitch, audio_filter = resolve_speech_style(
        "/mechanicus For the Omnissiah!", config
    )
    assert text == "For the Omnissiah!"
    assert voice == "en-GB-RyanNeural"
    assert pitch == "-35Hz"
    assert audio_filter is not None and "aecho=" in audio_filter
    assert resolve_speech_volume("/mechanicus For the Omnissiah!", config) == "+6%"


def test_unknown_prefix_is_spoken_normally() -> None:
    config = TTSConfig(voice="zh-TW-YunJheNeural", rate="-5%", pitch="+2Hz")
    text, voice, rate, pitch, audio_filter = resolve_speech_style("/hello 世界", config)
    assert text == "/hello 世界"
    assert voice == "zh-TW-YunJheNeural"
    assert rate == "-5%"
    assert pitch == "+2Hz"
    assert audio_filter is None
