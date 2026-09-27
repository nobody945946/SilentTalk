from silenttalk.config import TTSConfig
from silenttalk.tts.edge import resolve_speech_settings
from silenttalk.voice_styles import VOICE_EFFECTS, persona_voice_style


def test_persona_voice_overrides_the_app_voice_and_keeps_the_ui_speed() -> None:
    style = persona_voice_style("zh-TW-HsiaoChenNeural", -15, -10, "echo")
    text, voice, rate, pitch, _volume, audio_filter = resolve_speech_settings(
        "你好", TTSConfig(voice="zh-TW-YunJheNeural"), voice_style=style, rate_multiplier=1.2
    )

    assert (text, voice, pitch) == ("你好", "zh-TW-HsiaoChenNeural", "-15Hz")
    assert rate != "-10%"  # the voice page's speed is applied on top
    assert audio_filter == VOICE_EFFECTS["echo"][1]


def test_pitch_only_persona_keeps_the_app_voice() -> None:
    style = persona_voice_style("", 15, 0, "")
    _text, voice, _rate, pitch, _volume, _filter = resolve_speech_settings(
        "你好", TTSConfig(voice="zh-TW-YunJheNeural"), voice_style=style
    )

    assert (voice, pitch) == ("zh-TW-YunJheNeural", "+15Hz")


def test_every_effect_restores_loudness_and_limits_peaks() -> None:
    for key, (_label, chain) in VOICE_EFFECTS.items():
        if key:
            assert chain is not None and chain.endswith("alimiter=limit=0.95")
