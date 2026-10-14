"""Conversation data shared by the UI, transport, records, and optional AI.

This module has no dependency on a model, speech recognizer, or Discord.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
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
    "public" (work anyone in a chat may ask for: that chat's posts and the
    public web in, one message out)."""

    text: str
    scope: str = "read"


TurnCallback = Callable[[ConversationTurn], None]


Attachment = tuple[str, Callable[[], Awaitable[bytes]]]


@dataclass(frozen=True, slots=True)
class Trigger:
    speaker_name: str
    text: str
    # Position in the conversation, to notice when the chat moved on.
    seq: int = 0
    # Discord's own signal: an @mention of the bot or a reply to it.
    addressed: bool = False
    via: str = "voice"
    # time.monotonic() when the line came in, to log how long an answer took
    # including any wait behind the previous generation.
    heard_at: float = 0.0
    speaker_id: int = 0
    # Where it was said (VOICE_ROOM or a thread) and the Discord message it
    # came in, which gets the task marks when it hands over work.
    place: int = VOICE_ROOM
    channel_id: int = 0
    message_id: int = 0
    # Files posted with the line, read only if the line hands work over.
    attachments: tuple[Attachment, ...] = ()


AGENT_NAME = "思考機"
AGENT_SPEAKER_ID = 0
AGENT_RESULT_CONTEXT_CHARS = 800
SPOKEN_RESULT_CHARS = 600
