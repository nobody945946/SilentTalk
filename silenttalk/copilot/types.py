from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    speaker_id: int
    speaker_name: str
    text: str
    is_self: bool = False
    created_at: float = 0.0
    # "voice" (spoken, via STT) or "text" (typed in the channel's chat).
    via: str = "voice"
    # Where it was said: VOICE_ROOM (the voice channel, spoken or in its chat)
    # or the ID of a Discord thread the bot opened. Each place is its own
    # conversation; a line is only answered, and only remembered, where it was said.
    place: int = 0

    @classmethod
    def now(
        cls,
        speaker_id: int,
        speaker_name: str,
        text: str,
        *,
        is_self: bool = False,
        via: str = "voice",
        place: int = 0,
    ) -> "ConversationTurn":
        return cls(
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            text=text,
            is_self=is_self,
            via=via,
            place=place,
            created_at=time(),
        )


# The voice channel the bot sits in (its voice and its built-in chat).
VOICE_ROOM = 0


@dataclass(frozen=True, slots=True)
class AgentTask:
    """Work for the Agent and how far it may reach (EdgeAgent's task scope):
    "read" (the owner's work that only reads this computer), "change" (the
    owner's work that changes things, each change approved in his DMs) or
    "public" (a lookup anyone may ask for: the web alone)."""

    text: str
    scope: str = "read"


@dataclass(frozen=True, slots=True)
class ReplyLane:
    """One fixed reply direction: LLM output tag, story-mode key, UI label."""

    code: str
    key: str
    label: str
    field: str


# The four option slots, in the order they fill and are shown. They are
# alternatives the character might say, not fixed intents (see
# LocalReplyModel.suggest), so they have no label. Codes and fields are
# identifiers from the first design (agree / ask / disagree / joke); the
# codes still pick each slot's colour.
REPLY_LANES: tuple[ReplyLane, ...] = (
    ReplyLane("AGREE", "w", "", "agree"),
    ReplyLane("ASK", "a", "", "ask"),
    ReplyLane("DISAGREE", "d", "", "disagree"),
    ReplyLane("HUMOR", "s", "", "humor"),
)


@dataclass(frozen=True, slots=True)
class ReplySuggestions:
    trigger_speaker: str
    trigger_text: str
    agree: str = ""
    disagree: str = ""
    humor: str = ""
    ask: str = ""
    error: str = ""
    # True while the model is still writing; the remaining lanes will follow.
    partial: bool = False

    def text_for(self, lane: ReplyLane) -> str:
        return str(getattr(self, lane.field))

    def items(self) -> tuple[tuple[ReplyLane, str], ...]:
        return tuple((lane, self.text_for(lane)) for lane in REPLY_LANES)

    def has_any(self) -> bool:
        return any(text for _, text in self.items())
