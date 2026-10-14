import json
from pathlib import Path

import pytest

from silenttalk.copilot.llm import LocalReplyModel
from silenttalk.persona import (
    EXAMPLE_PERSONAS,
    MACHINE_SPIRIT,
    PRESET_PERSONAS,
    Persona,
    PersonaError,
    PersonaState,
    PersonaStore,
    Relationship,
    blank_persona,
    persona_from_dict,
    persona_to_dict,
    validate_persona,
)


def test_blank_persona_adds_nothing_to_the_prompt() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    blank = blank_persona()

    assert blank.is_blank
    assert blank.render_system_block() == ""
    assert "【你的人設】" not in model.prompts._build_turn_system_prompt(
        blank, "called"
    )


def test_the_prompt_gets_who_the_person_is_not_words_to_copy() -> None:
    persona = Persona(
        id="p1",
        name="凱哥",
        desires="想帶大家贏",
        recent="昨天排位連輸五場",
        speech_style="句子短、節奏快，常用「欸」「好啦」，偶爾一句台語。",
        catchphrases="穩啦、笑死",
        sample_lines="欸我的，下波我先進",
        pet_peeves="有人亂衝",
        traits={"tongue": 5, "energy": 2, "warmth": 3},
        mood="累",
    )
    system = LocalReplyModel(Path("unused.gguf")).prompts._build_turn_system_prompt(
        persona, "called"
    )

    assert "名字：凱哥" in system
    assert "你想要：想帶大家贏" in system
    assert "最近：昨天排位連輸五場" in system
    assert "說話感覺：句子短、節奏快，偶爾一句台語" in system
    assert "現在的心情：累" in system
    # Words a small model would copy into every line stay out, and so do
    # details that barely changed a line (pet peeves, knowledge).
    for copied in ("好啦", "穩啦", "欸我的", "有人亂衝"):
        assert copied not in system
    # Personality stays: it shapes how they talk without words to copy.
    assert "個性：偏內向安靜、非常毒舌嘴砲" in system
    # Judges still see the whole sheet.
    assert "穩啦、笑死" in persona.render_system_block()


def test_system_prompt_is_stable_so_the_kv_cache_is_reused() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    persona = PRESET_PERSONAS[0]

    assert model.prompts._build_turn_system_prompt(
        persona, "called"
    ) == model.prompts._build_turn_system_prompt(persona, "called")


def test_reply_length_preference_changes_the_length_rule() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    short = Persona(id="p", name="", reply_length="short")

    assert "4～12 字" in model.prompts._build_turn_system_prompt(short, "called")
    assert "8～30 字" in model.prompts._build_turn_system_prompt(
        blank_persona(), "called"
    )


def test_validation_rejects_overlong_fields_and_half_relationships() -> None:
    with pytest.raises(PersonaError, match="背景故事"):
        validate_persona(Persona(id="p", name="x", background="很" * 300))
    with pytest.raises(PersonaError, match="名字"):
        validate_persona(
            Persona(id="p", name="x", relationships=(Relationship("", "朋友"),))
        )


def test_validation_clamps_traits_and_drops_neutral_ones() -> None:
    persona = validate_persona(
        Persona(id="p", name="x", traits={"tongue": 9, "energy": 3, "bogus": 1})
    )

    assert persona.traits == {"tongue": 5}


def test_round_trip_through_dict_keeps_everything() -> None:
    for preset in (*PRESET_PERSONAS, *EXAMPLE_PERSONAS):
        assert persona_from_dict(persona_to_dict(preset)) == validate_persona(preset)


def test_unknown_fields_from_newer_files_are_ignored() -> None:
    persona = persona_from_dict({"id": "p", "name": "x", "future_field": 1})

    assert persona.name == "x"


def test_a_new_store_starts_as_the_machine_spirit(tmp_path: Path) -> None:
    state = PersonaStore(tmp_path / "personas.json").load()

    assert [p.id for p in state.personas] == [MACHINE_SPIRIT.id]
    assert state.active == MACHINE_SPIRIT.id
    assert state.active_persona().nickname == "機魂、馬基納"
    style = state.active_persona().voice_style()
    assert style is not None and style.voice == "zh-TW-YunJheNeural" and style.pitch == "+22Hz"


def test_a_file_that_never_had_the_machine_spirit_gets_it_chosen_once(tmp_path: Path) -> None:
    """The owner's earlier characters stay; the machine spirit joins and is
    chosen. Once the owner saves, their choice stands, and the app's own
    character is never dropped from the file."""
    path = tmp_path / "personas.json"
    old = EXAMPLE_PERSONAS[1]
    path.write_text(json.dumps({"active": old.id, "personas": [persona_to_dict(old)]}),
                    encoding="utf-8")
    store = PersonaStore(path)
    state = store.load()
    assert [p.id for p in state.personas] == [MACHINE_SPIRIT.id, old.id]
    assert state.active == MACHINE_SPIRIT.id
    store.save(PersonaState([old], old.id))
    state = store.load()
    assert state.active == old.id
    assert [p.id for p in state.personas] == [MACHINE_SPIRIT.id, old.id]


def test_store_round_trip_active_selection_and_mood(tmp_path: Path) -> None:
    path = tmp_path / "personas.json"
    store = PersonaStore(path)
    store.save(PersonaState(list(EXAMPLE_PERSONAS), EXAMPLE_PERSONAS[1].id, "累"))

    state = store.load()
    assert state.active == EXAMPLE_PERSONAS[1].id
    assert state.mood == "累"
    active = state.active_persona()
    assert active.name == EXAMPLE_PERSONAS[1].name
    assert "現在的心情：累" in active.render_system_block()
    assert json.loads(path.read_text(encoding="utf-8"))["active"] == state.active


def test_mood_applies_even_without_a_persona(tmp_path: Path) -> None:
    state = PersonaState(list(EXAMPLE_PERSONAS), "none", "煩躁")

    assert state.active_persona().render_system_block() == "現在的心情：煩躁（語氣要帶出來）"


def test_store_forgets_an_active_id_that_no_longer_exists(tmp_path: Path) -> None:
    path = tmp_path / "personas.json"
    path.write_text(
        json.dumps({"active": "gone", "personas": [persona_to_dict(MACHINE_SPIRIT),
                                                    {"id": "a", "name": "A"}]}),
        encoding="utf-8",
    )

    state = PersonaStore(path).load()
    assert state.active == "none"
    assert state.active_persona().is_blank


def test_persona_voice_is_tts_only_and_validated() -> None:
    from silenttalk.persona import persona_from_dict, persona_to_dict

    chuuni = EXAMPLE_PERSONAS[2]
    style = chuuni.voice_style()

    assert style is not None and style.voice == "zh-CN-YunjianNeural"
    assert style.pitch == "-15Hz" and style.ffmpeg_filter
    assert "Yunjian" not in LocalReplyModel(
        Path("unused.gguf")
    ).prompts._build_turn_system_prompt(chuuni, "called")
    assert persona_from_dict(persona_to_dict(chuuni)).voice_style() == style
    # No voice settings: the voice page decides.
    assert Persona(id="p", name="x").voice_style() is None
    with pytest.raises(PersonaError, match="聲線"):
        validate_persona(Persona(id="p", name="x", voice="en-US-Unknown"))
    loud = validate_persona(
        Persona(id="p", name="x", voice_pitch=999, voice_speed=-999)
    )
    assert (loud.voice_pitch, loud.voice_speed) == (50, -40)
