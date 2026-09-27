from silenttalk.copilot.character import (
    CharacterPolicy,
    CharacterState,
    is_addressed,
    is_question,
    should_reply,
)
from silenttalk.copilot.persona import PRESET_PERSONAS, Persona, blank_persona

CALLED = CharacterPolicy(mode="called", follow_up_seconds=20.0)
ACTIVE = CharacterPolicy(mode="active", cooldown_seconds=8.0, turn_gap=3)


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

    assert should_reply(CALLED, state, "凱哥你說呢", addressed=True, now=101.0)
    assert should_reply(ACTIVE, state, "凱哥你說呢", addressed=True, now=101.0)


def test_active_mode_waits_for_cooldown_and_a_reason() -> None:
    state = CharacterState()
    state.spoke(now=100.0)
    state.heard()

    # Inside the cooldown: quiet even for a question.
    assert not should_reply(ACTIVE, state, "晚餐吃什麼", addressed=False, now=104.0)
    # After it: a question is a reason, a plain statement is not (yet).
    assert should_reply(ACTIVE, state, "晚餐吃什麼", addressed=False, now=110.0)
    assert not should_reply(ACTIVE, state, "我吃飽了", addressed=False, now=110.0)
    state.heard()
    state.heard()
    assert should_reply(ACTIVE, state, "我吃飽了", addressed=False, now=110.0)


def test_called_mode_answers_one_follow_up_then_waits_to_be_named_again() -> None:
    state = CharacterState()

    # Nothing before it spoke: a stray question is not for it.
    assert not should_reply(CALLED, state, "晚餐吃什麼", addressed=False, now=100.0)

    state.spoke(now=100.0)
    # Right after answering, the next line continues the exchange...
    assert should_reply(CALLED, state, "那你呢", addressed=False, now=105.0)
    state.follow_ups += 1
    # ...but it does not then ride along with the whole conversation.
    assert not should_reply(CALLED, state, "我也是", addressed=False, now=107.0)
    # Being named works at any time.
    assert should_reply(CALLED, state, "凱哥你覺得呢", addressed=True, now=107.0)

    state.spoke(now=200.0)
    # Long after it spoke, an unaddressed line is not for it.
    assert not should_reply(CALLED, state, "所以呢", addressed=False, now=230.0)


def test_ai_questions_are_spotted_next_to_chinese_text() -> None:
    from silenttalk.copilot.character import asks_if_ai

    assert asks_if_ai("欸你是AI吧") and asks_if_ai("你是真人嗎") and asks_if_ai("這個bot好笑")
    assert not asks_if_ai("我在aim練槍") and not asks_if_ai("robot玩具")
