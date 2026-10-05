from silenttalk.copilot.character import (
    CharacterPolicy,
    CharacterState,
    is_addressed,
    is_question,
    should_reply,
)
from silenttalk.copilot.persona import EXAMPLE_PERSONAS, Persona, blank_persona

CALLED = CharacterPolicy(mode="called", follow_up_seconds=20.0)
ACTIVE = CharacterPolicy(mode="active", cooldown_seconds=8.0, turn_gap=3)


def test_questions_without_punctuation_are_detected() -> None:
    assert is_question("你今天要不要一起打")
    assert is_question("晚餐吃什麼")
    assert is_question("真的假的？")
    assert not is_question("我先下線了")


def test_being_called_is_told_apart_from_being_talked_about() -> None:
    from silenttalk.copilot.character import address_of

    carry = EXAMPLE_PERSONAS[0]  # 凱哥, nicknames 凱哥、阿凱

    # Unmistakable: the name opens the line, or Discord says so.
    assert address_of("凱哥你覺得呢", carry).called
    assert address_of("欸 凱哥等等衝B", carry).called
    assert address_of("任何一句", carry, mention=True).called

    # The name turned up, but this is about him, not to him. The model gets
    # the line and can answer SKIP instead of barging in.
    about_him = address_of("我剛才跟阿凱講話好像在做任務對話", carry)
    assert about_him.mentioned and not about_him.called
    assert address_of("等一下叫凱哥來", carry).mentioned

    # Not his business at all: no model call.
    assert not address_of("我們衝B啦", carry).worth_reading


def test_calling_the_character_by_name_or_nickname() -> None:
    carry = EXAMPLE_PERSONAS[0]  # 凱哥, nicknames 凱哥、阿凱

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


def test_only_questions_aimed_at_the_bot_count_as_asking_if_it_is_an_ai() -> None:
    from silenttalk.copilot.character import asks_if_ai

    # Asked of the bot: it has to own up.
    assert asks_if_ai("欸你是AI吧")
    assert asks_if_ai("你是真人嗎")
    assert asks_if_ai("欸你是不是 AI 啊？聲音好平")
    assert asks_if_ai("不是啦我剛剛覺得你反應太快像機器人")

    # Someone talking about a bot, not to one. Nudging the character to
    # confess here would break the act for no reason.
    assert not asks_if_ai("剛剛打野打太快了像機器人")
    assert not asks_if_ai("我乾脆寫個老闆指令機器人來自動回應他")
    assert not asks_if_ai("這個bot好笑")
    # Not about AI at all.
    assert not asks_if_ai("我在aim練槍") and not asks_if_ai("robot玩具")


def test_questions_are_spotted_without_punctuation() -> None:
    # Speech recognition gives no "？", and the particle can sit mid-sentence.
    assert is_question("欸你們有吃宵夜嗎我剛點了雞排飯外送到家")
    assert is_question("晚餐吃什麼")
    assert not is_question("我先下線了")
