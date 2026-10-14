from __future__ import annotations

import difflib
import re
from collections.abc import Sequence

from silenttalk.conversation import ConversationTurn
from silenttalk.copilot import reply_templates as templates
from silenttalk.copilot.script import to_taiwan_traditional
from silenttalk.persona import Persona


def _strip_thinking(text: str) -> str:
    close = text.lower().rfind(templates._THINK_CLOSE)
    return text[close + len(templates._THINK_CLOSE) :] if close >= 0 else text


def quiet_for(turns: Sequence[ConversationTurn]) -> int:
    """Lines from others since the character last spoke."""
    count = 0
    for turn in reversed(turns):
        if turn.is_self:
            break
        count += 1
    return count


def _signature_used(phrase: str, line: str) -> bool:
    """A catchphrase appears, or a long sample line is echoed in part."""
    phrase, line = _compact(phrase), _compact(line)
    if len(phrase) <= 6:
        return bool(phrase) and phrase in line
    return any(phrase[i : i + 5] in line for i in range(len(phrase) - 4))


def _alike_to(a: str, b: str, ratio: float) -> bool:
    return (
        bool(a)
        and difflib.SequenceMatcher(None, _compact(a), _compact(b)).ratio() >= ratio
    )


def _echoes(reply: str, line: str) -> bool:
    """The reply mostly repeats the line it answers ("有啊我們週末去看電影" ->
    "有啊，週末去看電影"): a small model does this instead of answering."""
    reply, line = _compact(reply), _compact(line)
    if reply == line:
        return True
    return (
        len(reply) >= 4 and difflib.SequenceMatcher(None, reply, line).ratio() >= 0.75
    )


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum()).lower()


def clean_reply(value: str, max_chars: int) -> str:
    value = value.strip().strip("\"'「」『』*")
    # Small Qwen models slip into Simplified now and then (2-9% of lines).
    value = to_taiwan_traditional(" ".join(value.split()))
    if value.startswith("...") or value in {"…", "..."}:
        return ""
    if len(value) > max_chars:
        value = value[:max_chars].rstrip() + "…"
    return value


def parse_character_line(
    raw: str, trigger_text: str, persona: Persona, max_chars: int
) -> str:
    cleaned = raw.strip()
    close_index = cleaned.lower().rfind(templates._THINK_CLOSE)
    if close_index >= 0:
        cleaned = cleaned[close_index + len(templates._THINK_CLOSE) :]
    line = next((part.strip() for part in cleaned.splitlines() if part.strip()), "")
    # Tolerate "SAY|…", "你要說：…" and "<own name>：…" decorations, but
    # never strip other text before a colon ("說真的：…" is speech).
    names = {"你", "我", persona.name.strip()} | {
        nick.strip() for nick in persona.nickname.split("、")
    }
    speaker = "|".join(re.escape(name) for name in names if name)
    line = re.sub(
        rf"^(SAY\s*[|｜:：]|你要說\s*[:：]|({speaker})\s*[:：])", "", line
    ).strip()
    value = clean_reply(line, max_chars)
    if not value or value.upper().startswith("SKIP") or _echoes(value, trigger_text):
        return ""
    return value
