from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace

from silenttalk.persona import Persona, blank_persona

_LOG = logging.getLogger(__name__)


_QUIET_UPDATE_SECONDS = 90.0
_FULL_UPDATE_LINES = 16
_MIN_UPDATE_LINES = 4


class CharacterLife:
    def __init__(self, model, store, memory, *, all_turns, on_agenda):
        self._llm, self._states, self.memory = model, store, memory
        self._all_turns, self._on_agenda = all_turns, on_agenda
        self.persona = blank_persona()
        self.lines_since_update = 0
        self.last_activity_at = 0.0
        self._agenda_task = None
        self._loop = None

    def set_persona(self, persona: Persona) -> None:
        """Must run on the runtime loop; applies from the next generation on."""
        changed = persona.id != self.persona.id
        if changed:
            self._save_life()  # the previous character's, before it is swapped out
        self.persona = persona
        self._llm.set_persona(persona)
        _LOG.info("copilot_persona_set blank=%s", persona.is_blank)
        if changed and self.memory != "off" and not persona.is_blank:
            self._llm.set_state(self._states.load(persona.id))
            self.lines_since_update = 0
        if changed or not self._llm.agenda:
            self._start_agenda(reroll=False)

    def refresh_agenda(self) -> None:
        """換一批: new concerns in place of the ones it has not brought up yet.
        Must run on the runtime loop."""
        self._start_agenda(reroll=True)

    def clear_life(self) -> None:
        """Forget what the character carried between sessions (persona page).
        Must run on the runtime loop."""
        if not self.persona.is_blank:
            self._states.clear(self.persona.id)
        self._llm.set_state(type(self._llm.state)())
        self._start_agenda(reroll=False)

    def _start_agenda(self, *, reroll: bool) -> None:
        if self._loop is None or self.persona.is_blank:
            return
        if self._agenda_task is not None:
            self._agenda_task.cancel()
        self._agenda_task = self._loop.create_task(
            self._make_agenda(reroll), name="copilot-agenda"
        )

    async def _make_agenda(self, reroll: bool) -> None:
        started = time.perf_counter()
        state = self._llm.state
        if reroll:
            state = replace(
                state, concerns=tuple(c for c in state.concerns if c.status != "open")
            )
        try:
            state = await self._llm.fill_concerns(state)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOG.warning("copilot_agenda_failed error_type=%s", type(exc).__name__)
            return
        self._llm.set_state(state)
        self._save_life()
        _LOG.info(
            "copilot_agenda_ready items=%d ms=%d",
            len(state.active_concerns()),
            round((time.perf_counter() - started) * 1000),
        )
        self._show_life()

    def _show_life(self) -> None:
        if self._on_agenda is None:
            return
        marks = {"told": "（說過了）", "progress": "（有進展）"}
        self._on_agenda(
            tuple(
                c.text + marks.get(c.status, "")
                for c in self._llm.state.active_concerns()
            )
        )

    def _save_life(self) -> None:
        if self.memory == "off" or self.persona.is_blank or self._llm.state.is_empty:
            return
        try:
            self._states.save(self.persona.id, self._llm.state)
        except OSError as exc:
            _LOG.warning("copilot_state_save_failed error_type=%s", type(exc).__name__)

    def update_due(self, pending: bool) -> bool:
        if self.memory == "off" or self.persona.is_blank or pending:
            return False
        if self.memory == "full" and self.lines_since_update >= _FULL_UPDATE_LINES:
            return True
        quiet = time.monotonic() - self.last_activity_at
        return (
            self.lines_since_update >= _MIN_UPDATE_LINES
            and quiet >= _QUIET_UPDATE_SECONDS
        )

    async def update(self) -> None:
        """How the chat moved its life on: concerns shared, progressing, done
        or dropped, new ones, recent and mood (views and feelings in "full").
        Counts only in the log; the state itself is the user's file."""
        started = time.perf_counter()
        self.lines_since_update = 0
        try:
            state = await self._llm.update_state(self._all_turns())
            if len(state.active_concerns()) < 2:
                state = await self._llm.fill_concerns(state)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOG.warning(
                "copilot_state_update_failed error_type=%s", type(exc).__name__
            )
            return
        self._llm.set_state(state)
        self._save_life()
        _LOG.info(
            "copilot_state_updated active=%d finished=%d ms=%d",
            len(state.active_concerns()),
            len(state.finished_concerns()),
            round((time.perf_counter() - started) * 1000),
        )
        self._show_life()

    async def stop(self, *, final_update=False):
        if (
            final_update
            and self.memory != "off"
            and self.lines_since_update >= _MIN_UPDATE_LINES
        ):
            try:
                await asyncio.wait_for(self.update(), timeout=30)
            except (TimeoutError, asyncio.CancelledError):
                _LOG.warning("copilot_state_update_skipped reason=timeout")
        if self._agenda_task is not None:
            self._agenda_task.cancel()
            await asyncio.gather(self._agenda_task, return_exceptions=True)
        self._save_life()
        self._loop = None

    def bind(self, loop):
        self._loop = loop

    def note_turn(self):
        self.last_activity_at = time.monotonic()
        self.lines_since_update += 1
        return self.last_activity_at
