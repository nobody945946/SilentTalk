from __future__ import annotations

import threading

from silenttalk.copilot.types import ConversationTurn


class ConversationStore:
    """Small prompt window backed by a larger in-memory session history."""

    def __init__(
        self,
        *,
        max_turns: int = 240,
        summary_chars: int = 640,
    ) -> None:
        self._max_turns = max(1, max_turns)
        self._summary_chars = max(0, summary_chars)
        self._turns: list[ConversationTurn] = []
        # What the older, already dropped part of the chat was about. Keeps a
        # long session coherent without growing the prompt.
        self._summary = ""
        self._lock = threading.RLock()

    def append(self, turn: ConversationTurn) -> None:
        text = " ".join(turn.text.split()).strip()
        if not text:
            return
        normalized = ConversationTurn(
            speaker_id=turn.speaker_id,
            speaker_name=turn.speaker_name.strip() or "Unknown",
            text=text,
            is_self=turn.is_self,
            created_at=turn.created_at,
            via=turn.via,
        )
        with self._lock:
            self._turns.append(normalized)
            if len(self._turns) > self._max_turns:
                del self._turns[: len(self._turns) - self._max_turns]

    def append_external(self, speaker_id: int, speaker_name: str, text: str) -> None:
        self.append(ConversationTurn.now(speaker_id, speaker_name, text))

    def append_self(self, speaker_id: int, text: str) -> None:
        self.append(
            ConversationTurn.now(
                speaker_id,
                "你",
                text,
                is_self=True,
            )
        )

    def snapshot(self) -> list[ConversationTurn]:
        with self._lock:
            return list(self._turns)

    @property
    def summary(self) -> str:
        with self._lock:
            return self._summary

    def pending_compaction(self, keep: int) -> list[ConversationTurn]:
        """Turns old enough to fold into the summary, oldest first, or []."""
        with self._lock:
            older = self._turns[: max(0, len(self._turns) - keep)]
        return older

    def compact(self, summary: str, folded: int, keep: int) -> None:
        """Replace the `folded` oldest turns with `summary`.

        Called after the summary was generated; turns that arrived meanwhile
        are untouched, so nothing recent is lost.
        """
        summary = " ".join(summary.split())[: self._summary_chars]
        with self._lock:
            folded = min(folded, max(0, len(self._turns) - max(0, keep)))
            if folded <= 0:
                return
            del self._turns[:folded]
            self._summary = summary
