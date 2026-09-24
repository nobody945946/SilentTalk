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
    ) -> None:
        self._recent_turns = max(4, recent_turns)
        self._max_turns = max(self._recent_turns, max_turns)
        self._char_budget = max(600, char_budget)
        self._older_self_turns = max(0, older_self_turns)
        self._turns: list[ConversationTurn] = []
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
                prefix.pop(1)
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
