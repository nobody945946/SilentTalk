from silenttalk.tts.edge import resolve_speech_style


def test_style_prefix_changes_only_current_utterance() -> None:
    text, rate, pitch = resolve_speech_style("/deep 這句低沉一點", "+0%", "+0Hz")
    assert text == "這句低沉一點"
    assert rate == "-8%"
    assert pitch == "-35Hz"


def test_unknown_prefix_is_spoken_normally() -> None:
    text, rate, pitch = resolve_speech_style("/hello 世界", "-5%", "+2Hz")
    assert text == "/hello 世界"
    assert rate == "-5%"
    assert pitch == "+2Hz"


def test_bare_style_command_is_not_swallowed() -> None:
    text, rate, pitch = resolve_speech_style("/cute", "+0%", "+0Hz")
    assert text == "/cute"
    assert rate == "+0%"
    assert pitch == "+0Hz"
