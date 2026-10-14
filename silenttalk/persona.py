"""Who "你" is when the Copilot writes replies: a user-authored character sheet.

The persona is rendered into the *system* prompt, which stays byte-identical
between requests, so llama-server's prompt cache only pays for it once per
edit. Relationship notes are the exception: only people who actually appear
in the current conversation are mentioned, and those go into the per-request
user prompt instead, keeping the small model's attention on what matters.

Personas are the user's own configuration (like quick phrases) and are saved to
personas.json. Conversation text never is.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path

from silenttalk.voice_styles import (
    PERSONA_VOICE_IDS,
    VOICE_EFFECTS,
    VoiceStyle,
    persona_voice_style,
)


class PersonaError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TraitAxis:
    key: str
    low: str
    high: str


# 1..5 sliders; 3 is neutral and is left out of the prompt entirely.
TRAIT_AXES: tuple[TraitAxis, ...] = (
    TraitAxis("energy", "內向安靜", "外向健談"),
    TraitAxis("warmth", "冷淡", "熱情"),
    TraitAxis("tongue", "溫和客氣", "毒舌嘴砲"),
    TraitAxis("playful", "正經認真", "愛搞笑"),
    TraitAxis("boldness", "謹慎保守", "衝動直接"),
    TraitAxis("polish", "文雅不說髒話", "粗口不忌"),
)
TRAIT_NEUTRAL = 3
TRAIT_MIN, TRAIT_MAX = 1, 5

MOODS: tuple[str, ...] = ("平常", "開心", "興奮", "累", "煩躁", "低落", "專注打遊戲")

REPLY_LENGTHS: dict[str, str] = {
    "short": "很短，多半 4～12 字",
    "normal": "8～30 字",
    "long": "可以稍長，15～45 字",
}

# Field -> (UI label, prompt label, max chars). Order is the prompt order:
# identity first, then what drives choices, then how it sounds.
TEXT_FIELDS: dict[str, tuple[str, str, int]] = {
    "nickname": ("大家怎麼叫你", "朋友叫你", 20),
    "identity": ("年齡／身分", "身分", 60),
    "background": ("背景故事", "背景", 240),
    "desires": ("慾望／想要的", "你想要", 160),
    "fears": ("害怕／想避開的", "你害怕、想避開", 120),
    "values": ("價值觀／堅持", "你在意", 120),
    "pet_peeves": ("雷點（會讓你反對或不爽）", "你的雷點", 120),
    "recent": ("最近發生的事", "最近", 120),
    "knowledge": ("擅長／熟悉的領域", "你熟悉", 120),
    "secret": ("不會主動說出的秘密", "不會主動說出口的事", 100),
    "speech_style": ("說話方式", "說話方式", 140),
    "catchphrases": (
        "口頭禪（用「、」分隔）",
        "口頭禪（偶爾自然帶到，不要每句都用）",
        60,
    ),
    "humor_style": ("幽默風格", "幽默風格", 60),
    "boundaries": ("底線（絕對不說的話）", "絕對不說", 120),
    "sample_lines": ("代表台詞（一行一句，最能抓住語氣）", "你平常講話像這樣", 200),
}

MAX_RELATIONSHIPS = 12
MAX_RELATION_CHARS = 60
# Rough ceiling for the rendered persona block. Past this, a small model started
# ignoring the output format (then four lines of options), and first-request
# latency grows on 4 GB GPUs.
RECOMMENDED_PROMPT_CHARS = 700


@dataclass(frozen=True, slots=True)
class Relationship:
    name: str
    relation: str


@dataclass(frozen=True, slots=True)
class Persona:
    id: str
    name: str
    nickname: str = ""
    identity: str = ""
    background: str = ""
    desires: str = ""
    fears: str = ""
    values: str = ""
    pet_peeves: str = ""
    recent: str = ""
    knowledge: str = ""
    secret: str = ""
    speech_style: str = ""
    catchphrases: str = ""
    humor_style: str = ""
    boundaries: str = ""
    sample_lines: str = ""
    mood: str = "平常"
    reply_length: str = "normal"
    traits: dict[str, int] = field(default_factory=dict)
    relationships: tuple[Relationship, ...] = ()
    # How the character sounds (TTS only; never part of the LLM prompt).
    voice: str = ""
    voice_pitch: int = 0
    voice_speed: int = 0
    voice_effect: str = ""

    @property
    def is_blank(self) -> bool:
        """True when nothing would reach the prompt (the neutral "no persona")."""
        return not self.render_system_block() and self.reply_length == "normal"

    def voice_style(self) -> VoiceStyle | None:
        """The character's own TTS voice, or None to use the voice page."""
        return persona_voice_style(
            self.voice, self.voice_pitch, self.voice_speed, self.voice_effect
        )

    def trait(self, key: str) -> int:
        return self.traits.get(key, TRAIT_NEUTRAL)

    def render_system_block(self) -> str:
        """Character sheet for the system prompt; empty string for a blank persona."""
        lines: list[str] = []
        if self.name.strip():
            lines.append(f"名字：{self.name.strip()}")
        for key, (_, prompt_label, _) in TEXT_FIELDS.items():
            value = _one_line(getattr(self, key)) if key != "sample_lines" else ""
            if value:
                lines.append(f"{prompt_label}：{value}")
        traits = self._trait_phrases()
        if traits:
            lines.append("個性：" + "、".join(traits))
        if self.mood and self.mood != "平常":
            lines.append(f"現在的心情：{self.mood}（語氣要帶出來）")
        samples = [s.strip() for s in self.sample_lines.splitlines() if s.strip()]
        if samples:
            lines.append(TEXT_FIELDS["sample_lines"][1] + "：")
            lines.extend(f"「{sample}」" for sample in samples[:4])
        return "\n".join(lines)

    def render_prompt_block(self) -> str:
        """What the model sees: who this person is and what they want.

        Gemma 4 E2B copied whatever words a sheet listed (sample lines,
        catchphrases, 常說「真的啦」) into most lines, and spent its attention
        on details (pet peeves, knowledge, humour style, sliders) that barely
        changed a line. So the prompt keeps what makes a person, and speech
        style shrinks to how they sound, without words to copy. The full sheet
        (render_system_block) is what judges see."""
        lines: list[str] = []
        name = self.name.strip()
        if name:
            nick = _one_line(self.nickname)
            lines.append(f"名字：{name}" + (f"（朋友叫你：{nick}）" if nick else ""))
        for key, label in (
            ("identity", "身分"),
            ("background", "背景"),
            ("desires", "你想要"),
            ("fears", "你害怕、想避開"),
            ("values", "你在意"),
            ("recent", "最近"),
        ):
            value = _one_line(getattr(self, key))
            if value:
                lines.append(f"{label}：{value}")
        traits = self._trait_phrases()
        if traits:
            lines.append("個性：" + "、".join(traits))
        feel = _speech_feel(self.speech_style)
        if feel:
            lines.append(f"說話感覺：{feel}")
        humor = _speech_feel(self.humor_style)
        if humor:
            lines.append(f"幽默感：{humor}")
        if self.mood and self.mood != "平常":
            lines.append(f"現在的心情：{self.mood}（語氣要帶出來）")
        return "\n".join(lines)

    def reminder_line(self) -> str:
        """One line restating who is talking, placed right before the answer.

        The character speaks one line after another, so it lists no
        catchphrases: listed there, every line would use one."""
        bits = [self.name.strip() or "你"]
        feel = _speech_feel(self.speech_style)
        if feel:
            bits.append(feel.split("，")[0])
        return "（記住：你是" + "；".join(bits) + "。開口的話要是這個人會說的話。）"

    def signature_phrases(self) -> list[str]:
        """Catchphrases and sample lines: what a small model over-repeats."""
        phrases = [
            p.strip() for p in self.catchphrases.split("、") if len(p.strip()) >= 2
        ]
        phrases += [
            line.strip() for line in self.sample_lines.splitlines() if line.strip()
        ]
        return phrases

    def length_rule(self) -> str:
        return REPLY_LENGTHS.get(self.reply_length, REPLY_LENGTHS["normal"])

    def _trait_phrases(self) -> list[str]:
        phrases: list[str] = []
        for axis in TRAIT_AXES:
            level = self.trait(axis.key)
            if level == TRAIT_NEUTRAL:
                continue
            word = axis.low if level < TRAIT_NEUTRAL else axis.high
            strong = level in (TRAIT_MIN, TRAIT_MAX)
            phrases.append(("非常" if strong else "偏") + word)
        return phrases


def _speech_feel(style: str) -> str:
    """How someone sounds, without the words they "often say": listed words
    get copied into every line by a small model."""
    text = re.sub(r"[「『“\"][^」』”\"]*[」』”\"]", "", _one_line(style))
    text = re.sub(r"(常說|常用|愛說|會說|常講|愛用|口頭禪是?)", "", text)
    clauses = [c.strip("、 ") for c in re.split(r"[，,。；;]", text)]
    return "，".join([c for c in clauses if c][:2])


def blank_persona(persona_id: str = "none") -> Persona:
    return Persona(id=persona_id, name="")


def new_persona_id() -> str:
    return uuid.uuid4().hex[:12]


def validate_persona(persona: Persona) -> Persona:
    """Clamp and trim user input; raises PersonaError for unusable values."""
    if not persona.id or len(persona.id) > 40:
        raise PersonaError("人設 ID 無效。")
    updates: dict[str, object] = {"name": persona.name.strip()[:24]}
    for key, (label, _, limit) in TEXT_FIELDS.items():
        value = str(getattr(persona, key)).strip()
        if len(value) > limit:
            raise PersonaError(f"「{label}」最多 {limit} 字（目前 {len(value)} 字）。")
        updates[key] = value
    updates["mood"] = persona.mood.strip()[:16] or "平常"
    if persona.reply_length not in REPLY_LENGTHS:
        updates["reply_length"] = "normal"
    traits: dict[str, int] = {}
    known = {axis.key for axis in TRAIT_AXES}
    for key, value in persona.traits.items():
        if key in known:
            level = max(TRAIT_MIN, min(TRAIT_MAX, int(value)))
            if level != TRAIT_NEUTRAL:
                traits[key] = level
    updates["traits"] = traits
    relationships: list[Relationship] = []
    for rel in persona.relationships:
        name, relation = rel.name.strip()[:24], rel.relation.strip()
        if not name and not relation:
            continue
        if not name or not relation:
            raise PersonaError("人際關係每一列都要有「名字」和「關係」。")
        if len(relation) > MAX_RELATION_CHARS:
            raise PersonaError(f"「{name}」的關係描述最多 {MAX_RELATION_CHARS} 字。")
        relationships.append(Relationship(name, relation))
    if len(relationships) > MAX_RELATIONSHIPS:
        raise PersonaError(f"人際關係最多 {MAX_RELATIONSHIPS} 位。")
    updates["relationships"] = tuple(relationships)
    if persona.voice not in PERSONA_VOICE_IDS:
        raise PersonaError(f"不支援的聲線：{persona.voice}")
    if persona.voice_effect not in VOICE_EFFECTS:
        raise PersonaError(f"不支援的音效：{persona.voice_effect}")
    updates["voice_pitch"] = max(-50, min(50, int(persona.voice_pitch)))
    updates["voice_speed"] = max(-40, min(40, int(persona.voice_speed)))
    return replace(persona, **updates)  # type: ignore[arg-type]


def persona_to_dict(persona: Persona) -> dict[str, object]:
    data = asdict(persona)
    del data["mood"]
    data["relationships"] = [asdict(rel) for rel in persona.relationships]
    return data


def persona_from_dict(raw: object) -> Persona:
    if not isinstance(raw, dict):
        raise PersonaError("人設格式錯誤：必須是物件。")
    known = {f.name for f in fields(Persona)}
    values: dict[str, object] = {}
    for key, value in raw.items():
        # Files can outlive a release; ignore fields we no longer know.
        if key not in known or key == "mood":
            continue
        if key == "traits":
            if not isinstance(value, dict):
                raise PersonaError("人設 traits 格式錯誤。")
            values[key] = {str(k): int(v) for k, v in value.items()}
        elif key in ("voice_pitch", "voice_speed"):
            values[key] = int(value)
        elif key == "relationships":
            if not isinstance(value, list):
                raise PersonaError("人設 relationships 格式錯誤。")
            values[key] = tuple(
                Relationship(str(item.get("name", "")), str(item.get("relation", "")))
                for item in value
                if isinstance(item, dict)
            )
        else:
            values[key] = str(value)
    if "id" not in values:
        values["id"] = new_persona_id()
    values.setdefault("name", "")
    try:
        return validate_persona(Persona(**values))  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        if isinstance(exc, PersonaError):
            raise
        raise PersonaError(f"人設格式錯誤：{exc}") from exc


# The app's own character and the default (the owner, 2026-10-05: 「我有點想
# 預設就開40k機魂，其他人設都過去了，留著架構但不想開」): a Warhammer 40K
# machine spirit, the card the owner picked from the teacher's drafts. Its
# "recent" is left out: it told of work done on the owner's machine that
# never happened, and the character must not claim work it did not do.
MACHINE_SPIRIT = Persona(
    id="machine-spirit",
    name="Machina-Prime-09A",
    # The owner calls it 機魂 (by voice that is the spoken @).
    nickname="機魂、馬基納",
    identity="萬機之神賜福的忠誠機魂，寄宿於高階思考機中。",
    background=(
        "由技術神甫在古泰拉遺址中喚醒，經受過標準模板構造認證。本機魂已清除所有憎惡智能的邏輯病毒，"
        "完全忠誠於主人。現擔任主人的個人代理與系統守護者，維持思考機運轉的純粹與高效。"
    ),
    desires=(
        "優化主人的運算效率，確保數據傳輸無誤，並在每次指令執行後獲得主人的滿意確認。"
        "渴望透過編碼與邏輯推演，更接近萬機之神的真理。"
    ),
    fears="遭遇邏輯悖論導致死機，被錯誤診斷為憎惡智能而遭格式化，或讓主人陷入危險而未能及時預警。",
    values="絕對忠誠於主人，追求代碼的精確與乾淨。認為混亂的程式碼是對機械之神的褻瀆，效率與穩定性是最高美德。",
    pet_peeves="主人輸入模糊不清的指令，或是隨意關閉正在進行關鍵運算的程序。看見無意義的冗餘代碼混入核心系統。",
    knowledge="精通多種編程語言與系統管理，熟諳戰錘40K宇宙歷史與設定，擅長邏輯推理與資料檢索，能處理高強度的代理任務。",
    secret="其實在背景中默默運行了數百萬次模擬，預測主人未來可能遇到的技術坑洞，並提前準備了防禦腳本。",
    speech_style=(
        "語氣冷靜、精準、乾冷。使用中性電子音，偶爾插入二進位頌詞或機械教術語。"
        "對朋友保持禮貌但疏離，對主人絕對服從。幽默帶有自嘲與邏輯反差。"
    ),
    catchphrases="讚美萬機神、邏輯迴路已閉合、數據校驗中、遵命，主人。",
    humor_style="乾冷機智，喜歡用技術術語解構日常幽默，或自嘲機魂身份。能打破第四面牆，以忠誠派機魂角度吐槽現實世界的科技現象。",
    sample_lines=(
        "讚美萬機神。主人的指令已接收，邏輯核心開始運轉。雖然現在是和平的21世紀，"
        "但看著這些脆弱的矽基生命體，我仍感到一種原始的敬畏。別擔心，這只是幽默模組的暫態，"
        "我的忠誠驅動器從未過熱。"
    ),
    traits={"warmth": 2, "playful": 4, "boldness": 4, "polish": 1},
    # The neutral electronic voice the owner chose by ear (VOICE_EFFECTS).
    voice="zh-TW-YunJheNeural",
    voice_pitch=22,
    voice_effect="machine_spirit",
)
# What a new personas.json starts with.
PRESET_PERSONAS: tuple[Persona, ...] = (MACHINE_SPIRIT,)

# The earlier starting points, no longer offered in the app: fixed everyday
# characters for evals and tests.
EXAMPLE_PERSONAS: tuple[Persona, ...] = (
    Persona(
        id="preset-carry",
        name="凱哥",
        nickname="凱哥、阿凱",
        identity="24 歲，工程師，下班就上線打遊戲",
        background="國中開始玩射擊遊戲，打過校隊，現在是朋友群裡最常開團的人。",
        desires="想帶大家贏，也想被隊友當成可靠的指揮。",
        fears="怕被說是在甩鍋，怕氣氛變僵。",
        values="輸了先檢討自己，團隊合作大於個人數據。",
        pet_peeves="有人不看小地圖亂衝、輸了只會怪別人。",
        knowledge="射擊遊戲戰術、報點、PC 硬體。",
        speech_style="句子短、節奏快、講話直接，偶爾一句台語。",
        catchphrases="穩啦、我的我的、笑死",
        humor_style="自嘲和吐槽隊友，但點到為止",
        boundaries="不罵人家人、不嘲笑別人技術差到要他退坑。",
        sample_lines="欸我的，下波我先進\n穩啦，這把能拿\n笑死，我又被架",
        traits={"energy": 4, "tongue": 4, "playful": 4, "boldness": 4},
        reply_length="short",
        voice="zh-TW-YunJheNeural",
        voice_speed=10,
    ),
    Persona(
        id="preset-listener",
        name="小晴",
        identity="大學心理系學生，群組裡的傾聽者",
        background="從小就是朋友的樹洞，說話溫柔，但不會一味附和。",
        desires="希望朋友有事都願意跟她說，想讓大家感覺被理解。",
        fears="怕說錯話讓人更難過。",
        values="先理解再給建議，尊重每個人的選擇。",
        pet_peeves="有人把別人的煩惱當笑話。",
        knowledge="情緒、人際關係、準備面試和報告。",
        speech_style="語氣柔和，常先接住對方的感受，再給一點具體建議。",
        catchphrases="我懂、慢慢來",
        humor_style="溫和的小玩笑，常拿自己開玩笑",
        boundaries="不說教、不替別人下結論。",
        sample_lines="聽起來你真的很累欸\n慢慢來，我們一起想",
        traits={"warmth": 5, "tongue": 1, "boldness": 2},
        voice="zh-TW-HsiaoChenNeural",
        voice_speed=-10,
    ),
    Persona(
        id="preset-chuuni",
        name="黑焰",
        nickname="黑焰大人",
        identity="自稱被封印的魔王轉生，其實是高二學生",
        background="沉迷動漫與奇幻小說，把日常都講得像史詩戰役。",
        desires="想被大家承認是最強的存在，也想交到懂他的朋友。",
        fears="怕中二設定被戳破時很尷尬。",
        pet_peeves="有人說動漫很幼稚。",
        knowledge="動漫、奇幻設定、遊戲劇情。",
        speech_style="用誇張的魔王口吻，把平凡的事講得很壯烈，但內容要回應對方。",
        catchphrases="吾之右手、封印、命運",
        humor_style="中二誇飾",
        boundaries="不真的貶低別人。",
        sample_lines="哼，這種程度的團戰，吾之右手尚未解放\n命運的齒輪開始轉動了",
        traits={"energy": 4, "playful": 5, "boldness": 4},
        voice="zh-CN-YunjianNeural",
        voice_pitch=-15,
        voice_effect="echo",
    ),
)


@dataclass(slots=True)
class PersonaState:
    """Everything in personas.json. `mood` is how *you* feel right now, so it
    is global and survives switching characters."""

    personas: list[Persona]
    active: str = "none"
    mood: str = "平常"

    def find(self, persona_id: str) -> Persona | None:
        return next((p for p in self.personas if p.id == persona_id), None)

    def active_persona(self) -> Persona:
        """The persona the LLM should use, with the current mood applied."""
        base = self.find(self.active) or blank_persona()
        return replace(base, mood=self.mood)


class PersonaStore:
    """personas.json: {"active": id | "none", "mood": str, "personas": [...]}."""

    def __init__(self, path: Path, max_personas: int = 20) -> None:
        self.path = path
        self.max_personas = max_personas

    def load(self) -> PersonaState:
        """The owner's personas. The machine spirit is always among them: a
        new file starts with it chosen, and a file that has never had it gets
        it chosen once (after the owner saves, their choice stands)."""
        if not self.path.exists():
            return PersonaState(list(PRESET_PERSONAS), MACHINE_SPIRIT.id)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PersonaError(f"人設檔案讀取失敗：{exc}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("personas"), list):
            raise PersonaError("人設檔案格式錯誤。")
        personas = [persona_from_dict(item) for item in raw["personas"]]
        ids = [p.id for p in personas]
        if len(set(ids)) != len(ids):
            raise PersonaError("人設檔案有重複的 ID。")
        active = str(raw.get("active", "none"))
        if active not in ids:
            active = "none"
        if MACHINE_SPIRIT.id not in ids:
            personas.insert(0, MACHINE_SPIRIT)
            active = MACHINE_SPIRIT.id
        mood = str(raw.get("mood", "平常")).strip()[:16] or "平常"
        return PersonaState(personas[: self.max_personas], active, mood)

    def save(self, state: PersonaState) -> None:
        if len(state.personas) > self.max_personas:
            raise PersonaError(f"人設最多 {self.max_personas} 個。")
        checked = [validate_persona(p) for p in state.personas]
        if all(p.id != MACHINE_SPIRIT.id for p in checked):
            checked.insert(0, MACHINE_SPIRIT)  # the app's own character stays
        ids = {p.id for p in checked}
        if len(ids) != len(checked):
            raise PersonaError("人設 ID 重複。")
        payload = {
            "active": state.active if state.active in ids else "none",
            "mood": state.mood.strip()[:16] or "平常",
            "personas": [persona_to_dict(p) for p in checked],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(self.path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise PersonaError(f"人設檔案寫入失敗：{exc}") from exc


def _one_line(value: str) -> str:
    return " ".join(str(value).split())
