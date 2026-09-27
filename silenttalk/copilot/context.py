from __future__ import annotations

import threading

from silenttalk.copilot.types import ConversationTurn


class ConversationStore:
    """Small prompt window backed by a larger in-memory session history."""

    def __init__(
        self,
        *,
        recent_turns: int = 12,
        max_turns: int = 80,
        char_budget: int = 2200,
        older_self_turns: int = 4,
        summary_chars: int = 320,
    ) -> None:
        self._recent_turns = max(4, recent_turns)
        self._max_turns = max(self._recent_turns, max_turns)
        self._char_budget = max(600, char_budget)
        self._older_self_turns = max(0, older_self_turns)
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

    def compact(self, summary: str, folded: int) -> None:
        """Replace the `folded` oldest turns with `summary`.

        Called after the summary was generated; turns that arrived meanwhile
        are untouched, so nothing recent is lost.
        """
        summary = " ".join(summary.split())[: self._summary_chars]
        with self._lock:
            folded = min(folded, max(0, len(self._turns) - self._recent_turns))
            if folded <= 0:
                return
            del self._turns[:folded]
            self._summary = summary

    def render_for_prompt(self) -> str:
        with self._lock:
            turns = list(self._turns)

        if not turns:
            return "(目前沒有先前對話)"

        recent = turns[-self._recent_turns :]
        older = turns[: -self._recent_turns]
        older_self = [turn for turn in older if turn.is_self]
        older_self = older_self[-self._older_self_turns :]

        prefix: list[str] = []
        if self._summary:
            prefix.append(f"這場對話稍早的重點：{self._summary}")
            prefix.append("")
        if older_self:
            prefix.append("較早你自己說過：")
            for turn in older_self:
                prefix.append(f"- 你：{self._trim(turn.text, 140)}")
            prefix.append("")

        recent_lines = ["最近對話："]
        for turn in recent:
            speaker = "你" if turn.is_self else turn.speaker_name
            recent_lines.append(f"{speaker}：{self._trim(turn.text, 220)}")

        lines = prefix + recent_lines
        while sum(len(line) + 1 for line in lines) > self._char_budget:
            if len(recent_lines) > 5:
                recent_lines.pop(1)
            elif len(prefix) > 2:
                # Drop an older "you said" line; the summary line stays.
                prefix.pop(-2 if self._summary else 1)
            else:
                break
            lines = prefix + recent_lines

        return "\n".join(lines).strip()

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: max(1, limit - 1)].rstrip() + "…"
