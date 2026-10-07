from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from silenttalk.conversation import AGENT_NAME as _AGENT_NAME
from silenttalk.conversation import (
    AGENT_RESULT_CONTEXT_CHARS as _AGENT_RESULT_CONTEXT_CHARS,
)
from silenttalk.conversation import AGENT_SPEAKER_ID as _AGENT_SPEAKER_ID
from silenttalk.conversation import (
    VOICE_ROOM,
    ConversationTurn,
)
from silenttalk.copilot.context import ConversationStore
from silenttalk.copilot.reply_transport import InferenceDeferred

_LOG = logging.getLogger(__name__)


_MAX_THREADS = 16


class ConversationSessions:
    def __init__(self, model, config, owner_id, *, history, self_name, on_evict):
        self._llm = model
        self._owner_user_id, self._thread_history = owner_id, history
        self._self_name, self._on_evict = self_name, on_evict
        self._max_session_turns = config.max_session_turns
        self._compact_keep = config.compact_keep_turns
        self._compact_trigger = self._compact_keep + max(4, config.compact_batch_turns)
        self.enabled = config.compact_context
        self._contexts = {}
        self._resuming = {}
        self._compacting = set()
        self._jobs = set()
        self._loop = None

    def _spawn(self, coroutine, name):
        job = self._loop.create_task(coroutine, name=name)
        self._jobs.add(job)
        job.add_done_callback(self._jobs.discard)

    async def stop(self):
        for job in self._jobs:
            job.cancel()
        await asyncio.gather(*self._jobs, return_exceptions=True)
        self._loop = None

    def receive_text(
        self,
        handle: Callable[[], None],
        place: int,
        message_id: int,
        agent: bool = True,
    ) -> None:
        """A typed line, after its thread's earlier conversation is back: the
        first line of a thread the app has no conversation for (restarted, or
        forgotten past _MAX_THREADS) first reads the thread back."""
        queued = self._resuming.get(place)
        if queued is not None:
            queued.append(handle)
            return
        if (
            not agent
            or place in self._contexts
            or self._thread_history is None
            or self._loop is None
        ):
            handle()
            return
        self._resuming[place] = [handle]
        self._spawn(self._resume_thread(place, message_id), "copilot-thread-history")

    async def _resume_thread(self, place: int, before: int) -> None:
        """The thread's earlier lines become its conversation again, as
        context only: nothing in them is answered, handed to the Agent or
        recorded again, and no approval comes back (approvals are DMs). If
        the thread cannot be read the character is told so, rather than
        acting as if it remembered."""
        assert self._thread_history is not None
        turns: list[ConversationTurn] = []
        try:
            lines = await self._thread_history(place, before, self._max_session_turns)
            for author, name, text, kind in lines:
                if kind == "agent":
                    turns.append(
                        ConversationTurn(
                            _AGENT_SPEAKER_ID,
                            _AGENT_NAME,
                            text[:_AGENT_RESULT_CONTEXT_CHARS],
                            via="text",
                            place=place,
                        )
                    )
                else:
                    turns.append(
                        ConversationTurn(
                            self._owner_user_id if kind == "mine" else author,
                            self._self_name() if kind == "mine" else name,
                            text,
                            is_self=kind == "mine",
                            via="text",
                            place=place,
                        )
                    )
            _LOG.info("thread_history_read lines=%d", len(turns))
        except InferenceDeferred:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - an unreadable thread is said, not guessed
            _LOG.warning("thread_history_failed error_type=%s", type(exc).__name__)
            turns = [
                ConversationTurn(
                    _AGENT_SPEAKER_ID,
                    "系統",
                    "（讀不到這個討論串之前的訊息）",
                    via="text",
                    place=place,
                )
            ]
        store = self.context(place)
        for turn in turns:
            store.append(turn)
        for handle in self._resuming.pop(place, []):
            handle()

    def context(self, place: int) -> ConversationStore:
        """The conversation of one place, made when it first speaks. Only
        _MAX_THREADS threads are kept; the one quiet the longest goes first."""
        store = self._contexts.get(place)
        if store is not None and place != VOICE_ROOM:
            self._contexts[place] = self._contexts.pop(place)  # most recent last
        if store is None:
            store = ConversationStore(max_turns=self._max_session_turns)
            self._contexts[place] = store
            threads = [p for p in self._contexts if p != VOICE_ROOM]
            for old in threads[: max(0, len(threads) - _MAX_THREADS)]:
                del self._contexts[old]
                self._on_evict(old)
        return store

    def all_turns(self) -> list[ConversationTurn]:
        """Every place's recent turns in time order (for the character's life)."""
        return sorted(
            (t for store in self._contexts.values() for t in store.snapshot()),
            key=lambda t: t.created_at,
        )

    def maybe_compact(self, place: int) -> None:
        """Start folding a place's oldest turns into its summary, off the hot path."""
        loop = self._loop
        if place in self._compacting or loop is None or not self.enabled:
            return
        if len(self.context(place).snapshot()) < self._compact_trigger:
            return
        self._compacting.add(place)
        self._spawn(self._compact(place), "copilot-compact")

    async def _compact(self, place: int) -> None:
        context = self.context(place)
        try:
            keep = self._compact_keep
            older = context.pending_compaction(keep)
            if not older:
                return
            transcript = "\n".join(
                f"{'你' if turn.is_self else turn.speaker_name}：{turn.text}"
                for turn in older
            )
            started = time.perf_counter()
            summary = await self._llm.summarize(transcript, context.summary)
            if not summary:
                return
            context.compact(summary, len(older), keep)
            _LOG.info(
                "copilot_context_compacted folded=%d summary_chars=%d ms=%d",
                len(older),
                len(summary),
                round((time.perf_counter() - started) * 1000),
            )
        except InferenceDeferred:
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOG.warning("copilot_compact_failed", exc_info=False)
        finally:
            self._compacting.discard(place)

    def bind(self, loop):
        self._loop = loop

    def configure(self, values, batch_default):
        self._compact_keep = max(
            8, int(values.get("compact_keep_turns", self._compact_keep))
        )
        self._compact_trigger = self._compact_keep + max(
            4, int(values.get("compact_batch_turns", batch_default))
        )
