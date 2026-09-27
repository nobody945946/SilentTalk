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

    @classmethod
    def now(
        cls,
        speaker_id: int,
        speaker_name: str,
        text: str,
        *,
        is_self: bool = False,
        via: str = "voice",
    ) -> "ConversationTurn":
        return cls(
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            text=text,
            is_self=is_self,
            via=via,
            created_at=time(),
        )


@dataclass(frozen=True, slots=True)
class ReplyLane:
    """One fixed reply direction: LLM output tag, story-mode key, UI label."""

    code: str
    key: str
    label: str
    field: str


# Order is the order shown in lists and asked of the LLM. The label is also
# the tag the LLM writes each line under. Codes and fields are identifiers
# from the first design (agree / ask / disagree / joke); what each lane asks
# for now is _LANE_ASKS in llm.py: say what you think, ask, take a stand, joke.
REPLY_LANES: tuple[ReplyLane, ...] = (
    ReplyLane("AGREE", "w", "接話", "agree"),
    ReplyLane("ASK", "a", "追問", "ask"),
    ReplyLane("DISAGREE", "d", "表態", "disagree"),
    ReplyLane("HUMOR", "s", "玩笑", "humor"),
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
    # The character's own view of the moment, written before the lanes.
    thought: str = ""

    def text_for(self, lane: ReplyLane) -> str:
        return str(getattr(self, lane.field))

    def items(self) -> tuple[tuple[ReplyLane, str], ...]:
        return tuple((lane, self.text_for(lane)) for lane in REPLY_LANES)

    def has_any(self) -> bool:
        return any(text for _, text in self.items())
