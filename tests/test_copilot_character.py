from silenttalk.copilot.character import (
    CharacterPolicy,
    CharacterState,
    is_addressed,
    is_question,
    should_reply,
)
from silenttalk.copilot.persona import PRESET_PERSONAS, Persona, blank_persona

POLICY = CharacterPolicy(cooldown_seconds=8.0, turn_gap=3)


def test_questions_without_punctuation_are_detected() -> None:
    assert is_question("你今天要不要一起打")
    assert is_question("晚餐吃什麼")
    assert is_question("真的假的？")
    assert not is_question("我先下線了")


def test_calling_the_character_by_name_or_nickname() -> None:
    carry = PRESET_PERSONAS[0]  # 凱哥, nicknames 凱哥、阿凱

    assert is_addressed("阿凱你覺得呢", carry)
    assert is_addressed("欸凱哥 等等衝B", carry)
    assert not is_addressed("我們等等衝B", carry)
    # A bot without a name answers to "機器人" / "bot".
    assert is_addressed("欸機器人你會唱歌嗎", blank_persona())
    # One-character names would match everywhere; they are ignored.
    assert not is_addressed("我覺得可以", Persona(id="p", name="我"))


def test_addressed_lines_are_always_answered_even_right_after_speaking() -> None:
    state = CharacterState()
    state.spoke(now=100.0)

    assert should_reply(POLICY, state, "凱哥你說呢", addressed=True, now=101.0)


def test_unprompted_replies_wait_for_cooldown_and_a_reason() -> None:
    state = CharacterState()
    state.spoke(now=100.0)
    state.heard()

    # Inside the cooldown: quiet even for a question.
    assert not should_reply(POLICY, state, "晚餐吃什麼", addressed=False, now=104.0)
    # After it: a question is a reason, a plain statement is not (yet).
    assert should_reply(POLICY, state, "晚餐吃什麼", addressed=False, now=110.0)
    assert not should_reply(POLICY, state, "我吃飽了", addressed=False, now=110.0)
    state.heard()
    state.heard()
    assert should_reply(POLICY, state, "我吃飽了", addressed=False, now=110.0)
