import json
from pathlib import Path

import pytest

from silenttalk.copilot.llm import LocalReplyModel
from silenttalk.copilot.persona import (
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
    assert "人設" not in model._build_system_prompt(blank)


def test_persona_sheet_reaches_the_system_prompt() -> None:
    persona = Persona(
        id="p1",
        name="凱哥",
        desires="想帶大家贏",
        catchphrases="穩啦、笑死",
        traits={"tongue": 5, "energy": 2, "warmth": 3},
        mood="累",
    )
    system = LocalReplyModel(Path("unused.gguf"))._build_system_prompt(persona)

    assert "名字：凱哥" in system
    assert "你想要：想帶大家贏" in system
    assert "穩啦、笑死" in system
    assert "非常毒舌嘴砲" in system
    assert "偏內向安靜" in system
    # Neutral sliders stay out of the prompt.
    assert "冷淡" not in system and "熱情" not in system
    assert "現在的心情：累" in system


def test_system_prompt_is_stable_so_the_kv_cache_is_reused() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    persona = PRESET_PERSONAS[0]

    assert model._build_system_prompt(persona) == model._build_system_prompt(persona)


def test_only_people_in_the_conversation_get_relationship_notes() -> None:
    persona = Persona(
        id="p1",
        name="我",
        relationships=(
            Relationship("阿傑", "國中同學，互嗆但感情好"),
            Relationship("小雨", "暗戀對象"),
        ),
    )
    notes = persona.relationship_notes("最近對話：\n阿傑：衝B啦")
    prompt = LocalReplyModel(Path("unused.gguf"))._build_prompt(
        context="阿傑：衝B啦",
        trigger_speaker="阿傑",
        trigger_text="衝B啦",
        relationships=notes,
    )

    assert notes == ["阿傑：國中同學，互嗆但感情好"]
    assert "小雨" not in prompt
    assert "- 阿傑：國中同學" in prompt


def test_reply_length_preference_changes_the_length_rule() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    short = Persona(id="p", name="", reply_length="short")

    assert "4～12 字" in model._build_system_prompt(short)
    assert "8～30 字" in model._build_system_prompt(blank_persona())


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
    for preset in PRESET_PERSONAS:
        assert persona_from_dict(persona_to_dict(preset)) == validate_persona(preset)


def test_unknown_fields_from_newer_files_are_ignored() -> None:
    persona = persona_from_dict({"id": "p", "name": "x", "future_field": 1})

    assert persona.name == "x"


def test_store_starts_with_presets_and_no_active_persona(tmp_path: Path) -> None:
    state = PersonaStore(tmp_path / "personas.json").load()

    assert [p.id for p in state.personas] == [p.id for p in PRESET_PERSONAS]
    assert state.active == "none"
    assert state.active_persona().is_blank


def test_store_round_trip_active_selection_and_mood(tmp_path: Path) -> None:
    path = tmp_path / "personas.json"
    store = PersonaStore(path)
    store.save(PersonaState(list(PRESET_PERSONAS), PRESET_PERSONAS[1].id, "累"))

    state = store.load()
    assert state.active == PRESET_PERSONAS[1].id
    assert state.mood == "累"
    active = state.active_persona()
    assert active.name == PRESET_PERSONAS[1].name
    assert "現在的心情：累" in active.render_system_block()
    assert json.loads(path.read_text(encoding="utf-8"))["active"] == state.active


def test_mood_applies_even_without_a_persona(tmp_path: Path) -> None:
    state = PersonaState(list(PRESET_PERSONAS), "none", "煩躁")

    assert state.active_persona().render_system_block() == "現在的心情：煩躁（語氣要帶出來）"


def test_store_forgets_an_active_id_that_no_longer_exists(tmp_path: Path) -> None:
    path = tmp_path / "personas.json"
    path.write_text(
        json.dumps({"active": "gone", "personas": [{"id": "a", "name": "A"}]}),
        encoding="utf-8",
    )

    state = PersonaStore(path).load()
    assert state.active == "none"
    assert state.active_persona().is_blank


def test_persona_reminder_sits_right_before_the_answer() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    kwargs = {"context": "阿傑：衝B啦", "trigger_speaker": "阿傑", "trigger_text": "衝B啦"}

    assert "記住" not in model._build_prompt(**kwargs)
    model.set_persona(PRESET_PERSONAS[0])
    prompt = model._build_prompt(**kwargs)

    assert prompt.endswith("（記住：你是凱哥；句子短、節奏快；口頭禪偶爾用：穩啦、我的我的、笑死。四句都要是這個人會說的話。）\n輸出四行：")
    assert "【你的人設】" in model._build_system_prompt(PRESET_PERSONAS[0])
