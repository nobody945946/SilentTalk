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
_QUESTION = re.compile(r"(什麼|甚麼|怎麼|為什麼|為何|誰|哪|幾|多少|要不要|是不是|有沒有|對不對|好不好)")
_QUESTION_END = ("？", "?", "嗎", "呢", "吧")
# How people refer to a bot that has no name of its own.
_GENERIC_NAMES = ("機器人", "bot", "ai")


@dataclass(frozen=True, slots=True)
class CharacterPolicy:
    cooldown_seconds: float = 8.0
    # Unprompted, speak only after this many lines from others.
    turn_gap: int = 3
    # Drop a reply when the chat moved on by this many lines while generating.
    stale_turns: int = 2


@dataclass(slots=True)
class CharacterState:
    last_spoke_at: float | None = None
    turns_since_spoke: int = 0

    def heard(self) -> None:
        self.turns_since_spoke += 1

    def spoke(self, now: float) -> None:
        self.last_spoke_at = now
        self.turns_since_spoke = 0


def is_question(text: str) -> bool:
    stripped = text.strip()
    return stripped.endswith(_QUESTION_END) or bool(_QUESTION.search(stripped))


def talks_to_you(text: str) -> bool:
    """Singular "你" (not "你們"): the line is aimed at one listener."""
    return bool(re.search(r"你(?!們)", text))


def is_addressed(text: str, persona: Persona) -> bool:
    folded = text.casefold()
    names = [persona.name, *persona.nickname.split("、")]
    names = [name.strip().casefold() for name in names if len(name.strip()) >= 2]
    if not names:
        names = list(_GENERIC_NAMES)
    return any(name in folded for name in names)


def should_reply(
    policy: CharacterPolicy,
    state: CharacterState,
    text: str,
    *,
    addressed: bool,
    now: float,
) -> bool:
    if addressed:
        return True
    if state.last_spoke_at is not None and now - state.last_spoke_at < policy.cooldown_seconds:
        return False
    return is_question(text) or state.turns_since_spoke >= policy.turn_gap
