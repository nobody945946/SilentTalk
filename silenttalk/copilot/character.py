"""Character-mode settings, and how a line calls the character.

Whether a line is for the character is decided by its name, not guessed by
the model (the owner, 2026-10-05: a spoken name is "using your mouth to @ the
bot"; every line needs it, so a chat with friends is never taken as talking
to it). NameMatcher finds the names by sound: speech recognition writes
雞魂 or 基魂 for 機魂. `asks_if_ai` backs the opt-in "admit" policy.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from silenttalk.persona import Persona

# When the character opens its mouth at all.
#   called  - only when a line calls it: its name (by sound, in voice and
#             text) or an @mention or reply in text. Every line needs it.
#   active  - also joins in on its own when the model finds the moment.
# Asked "are you an AI?", the character either stays in the fiction or steps
# out of it. In a private channel among friends this is a storytelling
# choice, like an NPC never admitting it is scripted.


@dataclass(frozen=True, slots=True)
class CharacterPolicy:
    mode: str = "called"
    # Drop a reply when the chat moved on by this many lines while generating.
    stale_turns: int = 2


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


_HOMOPHONES = Path(__file__).with_name("data") / "homophones.txt"
_HAN = re.compile(r"[\u3400-\u9fff]")


# How people call a bot that has no name of its own.
_GENERIC_NAMES = ("機器人",)


def persona_names(persona: Persona) -> list[str]:
    """What this character answers to: its name and nicknames. One-character
    names are skipped: they would match inside half the words in the language."""
    names = [persona.name, *persona.nickname.split("、")]
    names = [name.strip() for name in names if len(name.strip()) >= 2]
    return names or list(_GENERIC_NAMES)


# Speech recognition closes a segment at half a second of silence, so "機魂，
# (pause) 幫我查明天天氣" arrives as two lines and only the first has the name
# (laptop round 11: voice lookups that named it never reached the Agent). A
# spoken line that is nothing but the call ("機魂", "機魂在嗎": at most this
# many other letters) passes it on to the same speaker's next spoken line
# (runtime.py, _CALL_CARRY_SECONDS).
BARE_CALL_CHARS = 2


class NameMatcher:
    """Whether a line calls the character: a Latin name as written (any
    case), a Chinese one by sound, so any characters read the same way
    (tones ignored) count. Built once per persona from the few lines of the
    homophone table its names need."""

    def __init__(self, names: Iterable[str]) -> None:
        names = [name for name in names if name]
        wanted = {ch for name in names for ch in name if _HAN.match(ch)}
        sounds: dict[str, set[str]] = {ch: set() for ch in wanted}
        rows: dict[str, str] = {}
        if wanted:
            for line in _HOMOPHONES.read_text(encoding="utf-8").splitlines():
                if line.startswith("#"):
                    continue
                syllable, chars = line.split("\t", 1)
                rows[syllable] = chars
                for ch in wanted.intersection(chars):
                    sounds[ch].add(syllable)
        alike = {ch: "".join(sorted({c for s in sounds[ch] for c in rows[s]} | {ch}))
                 for ch in wanted}
        parts = [
            "".join(f"[{re.escape(alike[ch])}]" if ch in alike else re.escape(ch) for ch in name)
            for name in names
        ]
        self._pattern = re.compile("|".join(parts), re.IGNORECASE) if parts else None

    def __call__(self, text: str) -> bool:
        return self._pattern is not None and self._pattern.search(text) is not None

    def rest(self, text: str) -> str:
        """The line without its calls (what was said besides the name)."""
        return self._pattern.sub("", text) if self._pattern is not None else text

    def bare(self, text: str) -> bool:
        """A call and next to nothing else ("機魂", "機魂在嗎"): what the
        caller wants comes in their next line (BARE_CALL_CHARS)."""
        return self(text) and sum(ch.isalnum() for ch in self.rest(text)) <= BARE_CALL_CHARS
