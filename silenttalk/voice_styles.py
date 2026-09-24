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


VOICE_STYLES: dict[str, VoiceStyle] = {
    "default": VoiceStyle("default", "一般", None, "+0%", "+0Hz", "+0%"),
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
        "機械神甫｜低沉電子",
        "en-GB-RyanNeural",
        "-16%",
        "-35Hz",
        "+6%",
        "highpass=f=110,lowpass=f=3000,aecho=0.8:0.65:28:0.22",
    ),
    "chaplain": VoiceStyle(
        "chaplain",
        "牧師｜威嚴低吼",
        "en-GB-RyanNeural",
        "-20%",
        "-50Hz",
        "+12%",
        "bass=g=12:f=95,acompressor=threshold=-20dB:ratio=5:attack=5:release=100",
    ),
    "chaos": VoiceStyle(
        "chaos",
        "混沌｜深沉回響",
        "en-US-ChristopherNeural",
        "-17%",
        "-55Hz",
        "+10%",
        "bass=g=9:f=90,aecho=0.8:0.6:55:0.18",
    ),
    "ork": VoiceStyle(
        "ork",
        "獸人｜粗暴咆哮",
        "en-GB-RyanNeural",
        "+8%",
        "-28Hz",
        "+18%",
        "bass=g=8:f=120,acompressor=threshold=-16dB:ratio=5:attack=3:release=70",
    ),
    "slow": VoiceStyle("slow", "慢速", None, "-25%", "-5Hz", "+0%"),
    "fast": VoiceStyle("fast", "快速", None, "+30%", "+0Hz", "+0%"),
    "deep": VoiceStyle("deep", "低沉", None, "-8%", "-35Hz", "+0%"),
    "cute": VoiceStyle("cute", "高音", None, "+12%", "+35Hz", "+0%"),
}


def voice_style_choices() -> list[tuple[str, str]]:
    return [(style.key, style.label) for style in VOICE_STYLES.values()]


def voice_style_label(key: str) -> str:
    style = VOICE_STYLES.get(key)
    return style.label if style else key


def apply_style_directive(text: str, style_key: str) -> str:
    if style_key == "default":
        return text
    if style_key not in VOICE_STYLES:
        raise ValueError(f"未知聲線：{style_key}")
    return f"/{style_key} {text}"
