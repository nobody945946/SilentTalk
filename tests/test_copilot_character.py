from silenttalk.copilot.character import NameMatcher, asks_if_ai, persona_names
from silenttalk.copilot.persona import (
    EXAMPLE_PERSONAS,
    MACHINE_SPIRIT,
    Persona,
    blank_persona,
)


def test_the_machine_spirit_is_called_by_how_its_name_sounds() -> None:
    """A spoken name is the owner's @ (2026-10-05). Speech recognition
    writes whatever sounds alike, simplified characters included."""
    calls = NameMatcher(persona_names(MACHINE_SPIRIT))
    for line in ("機魂今天天氣怎樣", "雞魂你在嗎", "欸基魂", "幾魂", "机魂", "玛基纳在不在",
                 "machina-prime-09a 你好"):
        assert calls(line), line
    for line in ("我跟朋友在聊天", "機會來了", "今天要吃什麼", "馬上就好"):
        assert not calls(line), line


def test_names_come_from_the_name_and_nicknames() -> None:
    carry = EXAMPLE_PERSONAS[0]  # 凱哥, nicknames 凱哥、阿凱
    calls = NameMatcher(persona_names(carry))
    assert calls("阿凱你覺得呢") and calls("欸凱哥 等等衝B") and calls("我剛才跟阿凱講話")
    assert not calls("我們等等衝B")
    # A bot without a name answers to "機器人".
    assert NameMatcher(persona_names(blank_persona()))("欸機器人你會唱歌嗎")
    # One-character names would match everywhere; they are ignored.
    assert persona_names(Persona(id="p", name="我")) == ["機器人"]
    assert not NameMatcher([])("任何一句")


def test_only_questions_aimed_at_the_bot_count_as_asking_if_it_is_an_ai() -> None:
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
