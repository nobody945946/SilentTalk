from __future__ import annotations

import asyncio
import logging
import time

from silenttalk.conversation import VOICE_ROOM
from silenttalk.conversation import Trigger as _Trigger
from silenttalk.copilot.character import CharacterPolicy
from silenttalk.copilot.reply_transport import InferenceDeferred

_LOG = logging.getLogger(__name__)


# How often the worker looks for a lull while nothing else wakes it.
# so it never runs mid-chat: "light" waits for this long a silence (after any


class CharacterReplies:
    def __init__(
        self,
        model,
        config,
        *,
        context,
        sequence,
        pending,
        epoch,
        on_error,
        on_line,
        on_text,
        on_agent_line,
    ):
        self._llm, self._config = model, config
        self._context, self._sequence, self._pending = context, sequence, pending
        self._epoch = epoch
        self._on_error, self._on_character_line, self._on_character_text = (
            on_error,
            on_line,
            on_text,
        )
        self._on_agent_line = on_agent_line
        self.enabled = False
        self.policy = CharacterPolicy(mode=config.character_engagement)
        self.last_heard_at = 0.0
        self.lull_spoken = True

    async def task_line(self, kind: str, detail: str, place: int = VOICE_ROOM) -> None:
        """The character's own words about the job, in the place the work
        came from: spoken in the voice room, typed in a thread."""
        if not self.enabled or not self._config.character_agent:
            return
        epoch = self._epoch()
        started = time.monotonic()
        context = self._context(place)
        try:
            line = await self._llm.character_turn(
                turns=context.snapshot(),
                summary=context.summary,
                engagement=self.policy.mode,
                task_hint=(kind, detail),
            )
            if (
                line
                and epoch == self._epoch()
                and self.enabled
                and self._config.character_agent
            ):
                if place == VOICE_ROOM:
                    if self._on_agent_line is not None:
                        self._on_agent_line(line)
                elif self._on_character_text is not None:
                    self._on_character_text(line, place)
        except InferenceDeferred:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - preserve the worker when notice generation fails
            _LOG.warning(
                "agent_character_report_failed error_type=%s", type(exc).__name__
            )
            self._on_error("角色的工作回報暫時無法產生。")
        _LOG.info(
            "agent_character_notice kind=%s latency_ms=%d",
            kind,
            round((time.monotonic() - started) * 1000),
        )

    async def speak(self, trigger: _Trigger) -> None:
        started = time.perf_counter()
        context = self._context(trigger.place)
        try:
            line = await self._llm.character_turn(
                turns=context.snapshot(),
                summary=context.summary,
                addressed=trigger.addressed,
                engagement=self.policy.mode,
            )
        except InferenceDeferred:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOG.warning("copilot_character_failed error_type=%s", type(exc).__name__)
            self._on_error(f"角色回話產生失敗：{exc}")
            return
        moved_on = self._sequence(trigger.place) - trigger.seq
        _LOG.info(
            "copilot_character_line latency_ms=%d since_heard_ms=%d spoke=%s"
            " addressed=%s moved_on=%d",
            round((time.perf_counter() - started) * 1000),
            round((time.monotonic() - trigger.heard_at) * 1000)
            if trigger.heard_at
            else -1,
            bool(line),
            trigger.addressed,
            moved_on,
        )
        if not line or not self.enabled:
            return
        if moved_on >= self.policy.stale_turns and not trigger.addressed:
            return  # the chat moved on; a late reply would sound off
        # Answer where and how the line came in: a thread gets typed into
        # that thread; in the voice room typed gets typed and spoken gets
        # spoken, falling back to speaking if text is unavailable.
        if trigger.place != VOICE_ROOM:
            if self._on_character_text is not None:
                self._on_character_text(line, trigger.place)
        elif trigger.via == "text" and self._on_character_text is not None:
            self._on_character_text(line, VOICE_ROOM)
        elif self._on_character_line is not None:
            self._on_character_line(line)

    async def open_topic(self) -> None:
        """Nobody has said anything for a while: the character brings up
        something on its mind, or asks after someone."""
        self.lull_spoken = True
        heard_at = self.last_heard_at
        started = time.perf_counter()
        room = self._context(VOICE_ROOM)
        try:
            line = await self._llm.character_turn(
                turns=room.snapshot(),
                summary=room.summary,
                engagement=self.policy.mode,
                lull=True,
            )
        except InferenceDeferred:
            self.lull_spoken = False  # not said: the lull is still due
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOG.warning("copilot_lull_failed error_type=%s", type(exc).__name__)
            return
        _LOG.info(
            "copilot_character_lull latency_ms=%d spoke=%s",
            round((time.perf_counter() - started) * 1000),
            bool(line),
        )
        # Someone spoke while it was thinking: the lull is over.
        if not line or not self.enabled or self.last_heard_at != heard_at:
            return
        if self._on_character_line is not None:
            self._on_character_line(line)

    def lull_at(self) -> float | None:
        """When the room will have been quiet long enough to open a topic
        (time.monotonic), or None when no lull is coming."""
        seconds = self._config.character_lull_seconds
        if not self.enabled or seconds <= 0 or self.lull_spoken or self._pending():
            return None
        return self.last_heard_at + seconds

    def lull_due(self) -> bool:
        at = self.lull_at()
        return at is not None and time.monotonic() >= at

    def configure(self, config):
        self._config = config
