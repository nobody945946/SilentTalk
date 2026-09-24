from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceStyle:
    key: str
    label: str
    voice: str | None
    rate: str
    pitch: str
    volume: str
    ffmpeg_filter: str | None = None
    ui_visible: bool = True


VOICE_STYLES: dict[str, VoiceStyle] = {
    "default": VoiceStyle("default", "一般", None, "+0%", "+0Hz", "+0%"),

    # User-approved presets. Keep these stable unless listening tests say otherwise.
    "space_marine": VoiceStyle(
        "space_marine",
        "星際戰士｜粗獷低沉",
        "en-US-ChristopherNeural",
        "-12%",
        "-45Hz",
        "+12%",
        "bass=g=10:f=100,acompressor=threshold=-18dB:ratio=4:attack=5:release=80",
    ),
    "mechanicus": VoiceStyle(
        "mechanicus",
        "機械神甫｜厚重電子",
        "en-US-EricNeural",
        "-4%",
        "-6Hz",
        "+4%",
        "bass=g=7:f=120,highpass=f=95,lowpass=f=3000,aecho=0.8:0.68:24:0.22,acompressor=threshold=-20dB:ratio=4:attack=4:release=85",
    ),
    "battle_sister": VoiceStyle(
        "battle_sister",
        "戰鬥修女｜冷峻堅定",
        "en-GB-SoniaNeural",
        "-4%",
        "-8Hz",
        "+6%",
        "bass=g=3:f=150,acompressor=threshold=-19dB:ratio=3.5:attack=4:release=75",
    ),

    # Hidden legacy modifiers: accepted for old saved/manual commands, not shown in UI.
    "slow": VoiceStyle(
        "slow", "慢速（舊相容）", None, "-25%", "-5Hz", "+0%", ui_visible=False
    ),
    "fast": VoiceStyle(
        "fast", "快速（舊相容）", None, "+30%", "+0Hz", "+0%", ui_visible=False
    ),
    "deep": VoiceStyle(
        "deep", "低沉（舊相容）", None, "-8%", "-35Hz", "+0%", ui_visible=False
    ),
    "cute": VoiceStyle(
        "cute", "高音（舊相容）", None, "+12%", "+35Hz", "+0%", ui_visible=False
    ),
}


def voice_style_choices() -> list[tuple[str, str]]:
    return [
        (style.key, style.label)
        for style in VOICE_STYLES.values()
        if style.ui_visible
    ]


def voice_style_label(key: str) -> str:
    style = VOICE_STYLES.get(key)
    return style.label if style else key
