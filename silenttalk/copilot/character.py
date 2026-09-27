"""When the bot, playing its persona on its own, should speak up.

Character mode has no human approving each line, so the rules err on the side
of staying quiet: always answer when someone calls the character by name,
otherwise only join in after a cooldown, and then only for a question or once
the others have talked for a while. The model can still decline with SKIP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from silenttalk.copilot.persona import Persona

# Question words that mark a line as a question even without "？" (speech
# recognition output rarely has punctuation).
# Speech recognition rarely produces "？", so a question is spotted by its
# words. "嗎/呢" are question particles and can sit mid-sentence
# ("你們有吃宵夜嗎我剛點了外送").
_QUESTION = re.compile(
    r"(什麼|甚麼|怎麼|為什麼|為何|誰|哪|幾|多少|要不要|是不是|有沒有|對不對|好不好|嗎|呢)"
)
_QUESTION_END = ("？", "?", "嗎", "呢", "吧")
# How people refer to a bot that has no name of its own.
_GENERIC_NAMES = ("機器人", "bot", "ai")


# When the character opens its mouth at all.
#   called  - only when spoken to: @mention or a reply in text, its name in
#             voice, plus a short follow-up window so a back-and-forth does
#             not need the name every time. Predictable in a busy channel.
#   active  - also joins in on its own: after a cooldown, on a question or
#             once the others have talked for a while.
# Asked "are you an AI?", the character either stays in the fiction or steps
# out of it. In a private channel among friends this is a storytelling
# choice, like an NPC never admitting it is scripted.
AI_HONESTY_MODES: tuple[tuple[str, str], ...] = (
    ("in_character", "照角色演（不承認）"),
    ("admit", "承認自己是 AI"),
)

ENGAGEMENT_MODES: tuple[tuple[str, str], ...] = (
    ("called", "被叫到才回"),
    ("active", "會主動加入"),
)


@dataclass(frozen=True, slots=True)
class CharacterPolicy:
    mode: str = "called"
    # "called": a line this soon after the character spoke continues the
    # exchange, so the next answer needs no name. 0 disables it.
    follow_up_seconds: float = 20.0
    # "active" only: stay quiet this long after speaking, then join in on a
    # question or after this many lines from others.
    cooldown_seconds: float = 8.0
    turn_gap: int = 3
    # Drop a reply when the chat moved on by this many lines while generating.
    stale_turns: int = 2


@dataclass(slots=True)
class CharacterState:
    last_spoke_at: float | None = None
    turns_since_spoke: int = 0
    # Follow-ups answered since the character last spoke; one keeps an
    # exchange going without letting the bot ride along with the whole chat.
    follow_ups: int = 0

    def heard(self) -> None:
        self.turns_since_spoke += 1

    def spoke(self, now: float) -> None:
        self.last_spoke_at = now
        self.turns_since_spoke = 0
        self.follow_ups = 0


def is_question(text: str) -> bool:
    stripped = text.strip()
    return stripped.endswith(_QUESTION_END) or bool(_QUESTION.search(stripped))


# ASCII-only word edges: \b treats CJK as word characters, so "是AI吧" has none.
# ASCII-only word edges: \b treats CJK as word characters, so "是AI吧" has none.
_AI_WORD = re.compile(
    r"((?<![a-z])(ai|bot)(?![a-z])|ａｉ|人工智慧|機器人|真人)", re.IGNORECASE
)
# "you are (not) a ...": the claim has to be about the listener, which is what
# separates "你是不是 AI" from "剛剛打野打太快了像機器人".
_ABOUT_YOU = re.compile(r"你(?!們)\s*[^，。！？\s]{0,6}?(是|像|不是|該不會|會不會)")


def asks_if_ai(text: str) -> bool:
    """Someone is probing this bot about whether it is an AI or a real person.

    Used either way round: to tell the character to own up, or to tell it to
    stay in character - which is why a false match costs so little now.

    Both halves are required: the AI word, and the line being about "you".
    Mentioning a bot or an AI while talking about something else (a laggy
    teammate, a Slack bot someone is building) is not a question for us.
    """
    if not _AI_WORD.search(text):
        return False
    return bool(_ABOUT_YOU.search(text)) or bool(
        re.search(r"你(?!們)[^，。！？]{0,8}(嗎|吧|\?|？)", text)
    )


def talks_to_you(text: str) -> bool:
    """Singular "你" (not "你們"): the line is aimed at one listener."""
    return bool(re.search(r"你(?!們)", text))


@dataclass(frozen=True, slots=True)
class Address:
    """How sure we are that a line is aimed at the character.

    `called` is unmistakable - an @mention, a reply to it, or its name
    opening the line ("凱哥你覺得呢"). `mentioned` only says the name turned
    up somewhere, which is as likely to be *about* it as *to* it ("我剛才跟
    阿凱講話"). Those go to the model, which sees the whole line and can
    answer SKIP; names come up in 0.03% of lines, so that costs nothing.
    """

    called: bool = False
    mentioned: bool = False

    @property
    def worth_reading(self) -> bool:
        return self.called or self.mentioned


# Openers people put before a name when calling someone.
_VOCATIVE_LEAD = "欸喂齁唉诶@ 　,，.。!！?？~～"


def persona_names(persona: Persona) -> list[str]:
    """What this character answers to. One-character names are skipped: they
    would match inside half the words in the language."""
    names = [persona.name, *persona.nickname.split("、")]
    names = [name.strip() for name in names if len(name.strip()) >= 2]
    return names or list(_GENERIC_NAMES)


def address_of(text: str, persona: Persona, *, mention: bool = False) -> Address:
    """Read who a line is aimed at. `mention` is Discord's own signal."""
    if mention:
        return Address(called=True, mentioned=True)
    folded = text.casefold()
    for name in persona_names(persona):
        index = folded.find(name.casefold())
        if index < 0:
            continue
        # At the start, or after nothing but an opener ("欸 凱哥…").
        opening = not text[:index].strip(_VOCATIVE_LEAD)
        return Address(called=opening, mentioned=True)
    return Address()


def is_addressed(text: str, persona: Persona) -> bool:
    """Kept for callers that only need a yes/no (eval, data generation)."""
    return address_of(text, persona).worth_reading


MAX_FOLLOW_UPS = 1


def should_reply(
    policy: CharacterPolicy,
    state: CharacterState,
    text: str,
    *,
    addressed: bool,
    now: float,
) -> bool:
    """Whether this line is for the character. `addressed` means it was named:
    an @mention or a reply to it in text, its name or nickname in voice."""
    if addressed:
        return True
    since_spoke = None if state.last_spoke_at is None else now - state.last_spoke_at
    if policy.mode == "called":
        return (
            since_spoke is not None
            and since_spoke < policy.follow_up_seconds
            and state.follow_ups < MAX_FOLLOW_UPS
        )
    if since_spoke is not None and since_spoke < policy.cooldown_seconds:
        return False
    return is_question(text) or state.turns_since_spoke >= policy.turn_gap
