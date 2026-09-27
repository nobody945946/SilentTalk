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


# Chinese EdgeTTS voices a persona can speak with (verified against
# edge_tts.list_voices() on 2026-09-27). "" = follow the voice page.
PERSONA_VOICES: tuple[tuple[str, str], ...] = (
    ("", "跟隨預設聲音"),
    ("zh-TW-HsiaoChenNeural", "台灣｜女聲・溫和"),
    ("zh-TW-HsiaoYuNeural", "台灣｜女聲・年輕"),
    ("zh-TW-YunJheNeural", "台灣｜男聲"),
    ("zh-CN-XiaoxiaoNeural", "大陸｜女聲・溫暖"),
    ("zh-CN-XiaoyiNeural", "大陸｜女聲・活潑"),
    ("zh-CN-YunxiNeural", "大陸｜男聲・陽光"),
    ("zh-CN-YunjianNeural", "大陸｜男聲・熱血"),
    ("zh-CN-YunxiaNeural", "大陸｜少年・可愛"),
    ("zh-CN-YunyangNeural", "大陸｜男聲・沉穩"),
    ("zh-CN-liaoning-XiaobeiNeural", "東北腔｜女聲・幽默"),
    ("zh-CN-shaanxi-XiaoniNeural", "陝西腔｜女聲・明亮"),
    ("zh-HK-HiuGaaiNeural", "粵語｜女聲"),
    ("zh-HK-WanLungNeural", "粵語｜男聲"),
)
PERSONA_VOICE_IDS = frozenset(voice for voice, _ in PERSONA_VOICES)

# Post-processing on top of the voice (FFmpeg -af), reusing the kind of chains
# the listening-tested presets above use. Each chain ends with make-up gain
# measured to bring it back to the dry voice's loudness (-27 dBFS RMS on
# zh-TW-YunJheNeural; the effects cost 2-7 dB) and a limiter against clipping,
# so a character with an effect is not quieter than everyone else.
_LEVEL = ",volume={gain}dB,alimiter=limit=0.95"
VOICE_EFFECTS: dict[str, tuple[str, str | None]] = {
    "": ("無", None),
    "deep": (
        "厚重低沉",
        "bass=g=8:f=110,acompressor=threshold=-18dB:ratio=3:attack=5:release=80"
        + _LEVEL.format(gain=2),
    ),
    "echo": ("空間回音", "aecho=0.8:0.6:60:0.22" + _LEVEL.format(gain=6)),
    "radio": (
        "無線電",
        "highpass=f=300,lowpass=f=3400,acompressor=threshold=-20dB:ratio=4:attack=4:release=60"
        + _LEVEL.format(gain=6.5),
    ),
    "robot": (
        "機械電子",
        str(VOICE_STYLES["mechanicus"].ffmpeg_filter) + _LEVEL.format(gain=6.5),
    ),
}
PITCH_STEPS: tuple[tuple[int, str], ...] = (
    (-30, "很低"), (-15, "低"), (0, "一般"), (15, "高"), (30, "很高")
)
SPEED_STEPS: tuple[tuple[int, str], ...] = (
    (-20, "很慢"), (-10, "慢"), (0, "一般"), (10, "快"), (20, "很快")
)


def persona_voice_style(
    voice: str, pitch_hz: int, speed_percent: int, effect: str
) -> VoiceStyle | None:
    """A persona's own voice, or None to use the voice page's choice."""
    if not voice and not pitch_hz and not speed_percent and not effect:
        return None
    return VoiceStyle(
        "persona",
        "人設聲音",
        voice or None,
        f"{speed_percent:+d}%",
        f"{pitch_hz:+d}Hz",
        "+0%",
        VOICE_EFFECTS.get(effect, VOICE_EFFECTS[""])[1],
        ui_visible=False,
    )
