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

    # Role-oriented presets. The base voice does most of the character work;
    # DSP is intentionally moderate so speech stays intelligible.
    "space_marine": VoiceStyle(
        "space_marine",
        "星際戰士｜重甲老兵",
        "en-US-AndrewNeural",
        "-6%",
        "-14Hz",
        "+8%",
        "bass=g=6:f=110,acompressor=threshold=-20dB:ratio=3:attack=5:release=90",
    ),
    "space_marine_commander": VoiceStyle(
        "space_marine_commander",
        "星際戰士｜指揮官",
        "en-US-ChristopherNeural",
        "-4%",
        "-8Hz",
        "+8%",
        "bass=g=4:f=120,acompressor=threshold=-18dB:ratio=3:attack=5:release=80",
    ),
    "chaplain": VoiceStyle(
        "chaplain",
        "帝國牧師｜權威宣告",
        "en-US-ChristopherNeural",
        "-8%",
        "-16Hz",
        "+10%",
        "bass=g=7:f=100,aecho=0.8:0.55:34:0.10,acompressor=threshold=-19dB:ratio=4:attack=5:release=95",
    ),
    "mechanicus": VoiceStyle(
        "mechanicus",
        "機械神甫｜冷靜電子",
        "en-US-EricNeural",
        "-4%",
        "-6Hz",
        "+4%",
        "highpass=f=180,lowpass=f=2700,aecho=0.8:0.60:22:0.16,acompressor=threshold=-21dB:ratio=3:attack=4:release=70",
    ),
    "servitor": VoiceStyle(
        "servitor",
        "機械侍從｜窄頻機械",
        "en-US-EricNeural",
        "-10%",
        "-10Hz",
        "+2%",
        "highpass=f=260,lowpass=f=2100,aecho=0.8:0.48:16:0.10,acompressor=threshold=-22dB:ratio=4:attack=3:release=60",
    ),
    "inquisitor": VoiceStyle(
        "inquisitor",
        "審判官｜正式冷峻",
        "en-US-RogerNeural",
        "-3%",
        "-6Hz",
        "+6%",
        "acompressor=threshold=-20dB:ratio=3:attack=5:release=85",
    ),
    "vox_officer": VoiceStyle(
        "vox_officer",
        "Vox 通訊｜軍用無線電",
        "en-US-ChristopherNeural",
        "+0%",
        "+0Hz",
        "+6%",
        "highpass=f=300,lowpass=f=3000,acompressor=threshold=-18dB:ratio=5:attack=4:release=65",
    ),
    "chaos": VoiceStyle(
        "chaos",
        "混沌冠軍｜狂熱低吼",
        "en-US-GuyNeural",
        "-5%",
        "-18Hz",
        "+10%",
        "bass=g=8:f=95,aecho=0.8:0.55:48:0.14,acompressor=threshold=-18dB:ratio=4:attack=4:release=85",
    ),
    "ork": VoiceStyle(
        "ork",
        "獸人｜粗暴咆哮",
        "en-US-GuyNeural",
        "+4%",
        "-12Hz",
        "+14%",
        "bass=g=9:f=115,acompressor=threshold=-16dB:ratio=5:attack=3:release=65",
    ),
    "narrator": VoiceStyle(
        "narrator",
        "敘事者｜深沉男聲",
        "en-US-AndrewNeural",
        "-5%",
        "-8Hz",
        "+2%",
        None,
    ),
    "tactician": VoiceStyle(
        "tactician",
        "戰術官｜冷靜男聲",
        "en-US-EricNeural",
        "+0%",
        "+0Hz",
        "+0%",
        None,
    ),
    "british_officer": VoiceStyle(
        "british_officer",
        "英倫軍官｜沉著男聲",
        "en-GB-ThomasNeural",
        "-2%",
        "-4Hz",
        "+2%",
        None,
    ),
    "battle_sister": VoiceStyle(
        "battle_sister",
        "戰地女聲｜清晰果決",
        "en-US-AriaNeural",
        "+0%",
        "-2Hz",
        "+2%",
        "acompressor=threshold=-21dB:ratio=2.5:attack=5:release=80",
    ),

    # Legacy text-prefix modifiers. They remain valid for old saved phrases /
    # manual commands but are deliberately hidden from the voice dropdown now
    # that speech rate has its own UI control.
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
