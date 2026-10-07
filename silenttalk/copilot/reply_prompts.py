from __future__ import annotations

import collections
from collections.abc import Sequence
from datetime import datetime

from silenttalk import ai_options as options
from silenttalk.conversation import ConversationTurn
from silenttalk.copilot import reply_templates as templates
from silenttalk.copilot.character import asks_if_ai
from silenttalk.copilot.character_state import (
    CharacterState,
    Concern,
)
from silenttalk.copilot.reply_parsing import _signature_used
from silenttalk.persona import Persona, blank_persona


class ReplyPrompts:
    def __init__(
        self,
        *,
        can_type: bool,
        ai_honesty: str,
        agent_dispatch: bool,
        owner_id: int | None,
        owner_name: str,
        max_reply_chars: int,
        memory: str,
    ):
        self.persona = blank_persona()
        self.life = CharacterState()
        self.recent_lines: collections.deque[str] = collections.deque(maxlen=4)
        self.can_type, self.ai_honesty = can_type, ai_honesty
        self.agent_dispatch = agent_dispatch
        self.owner_id, self.owner_name = owner_id, owner_name
        self.max_reply_chars = max(24, max_reply_chars)
        self.memory = memory if memory in options.MEMORY_LEVELS else "off"

    def option_messages(
        self, *, turns: Sequence[ConversationTurn], summary: str = ""
    ) -> list[dict[str, str]]:
        """The character chat (character mode's format, "你" as the assistant)
        with the options request on the end. Only that tail changes between
        rounds, so llama-server prefills just the new lines."""
        messages = self.character_messages(
            turns=turns, summary=summary, engagement="options", gate=True
        )
        ask = templates._OPTIONS_ASK
        if self.memory != "off":
            ask = f"（現在是{_now_words()}）\n" + ask
        if not self.persona.is_blank:
            ask = (
                self.persona.reminder_line("說出口的話要是", list_catchphrases=False)
                + "\n"
                + ask
            )
        if messages[-1]["role"] == "user":
            messages[-1] = {
                "role": "user",
                "content": messages[-1]["content"] + "\n\n" + ask,
            }
        else:
            messages.append({"role": "user", "content": ask})
        return messages

    def owner_messages(
        self,
        *,
        turns: Sequence[ConversationTurn],
        engagement: str = "called",
    ) -> list[dict[str, str]] | None:
        """The chat the Agent's work is read from: the character's system
        prompt (same cached prefix) and the owner's own recent typed lines,
        matched by Discord user ID, never by name. None unless the newest line
        is one of them. Other people's lines, the owner's spoken lines, the
        character's lines (which answer the others) and the summary (which
        folds them in) are left out."""
        if self.owner_id is None:
            return None
        own = [
            t
            for t in turns
            if t.speaker_id == self.owner_id and not t.is_self and t.via == "text"
        ]
        if not turns or not own or own[-1] is not turns[-1]:
            return None
        lines = [
            f"{t.speaker_name}：{t.text}" for t in own[-templates._TASK_OWNER_LINES :]
        ]
        return [
            {
                "role": "system",
                "content": self._build_turn_system_prompt(self.persona, engagement),
            },
            {
                "role": "user",
                "content": "\n".join([templates._OWNER_LINES_HEAD, *lines]),
            },
        ]

    def task_scope_messages(
        self, *, turns: Sequence[ConversationTurn], engagement: str = "called"
    ) -> list[dict[str, str]] | None:
        """The change-or-read question on the owner's newest typed line."""
        if not turns:
            return None
        return self._owner_question(
            turns,
            engagement,
            templates._TASK_SCOPE_QUESTION.format(
                line=" ".join(turns[-1].text.split())
            ),
        )

    def _owner_question(
        self, turns: Sequence[ConversationTurn], engagement: str, question: str
    ) -> list[dict[str, str]] | None:
        """The owner's lines (owner_messages) with one question on the end;
        every task question shares this cached prefix."""
        base = self.owner_messages(turns=turns, engagement=engagement)
        if base is None:
            return None
        return base[:-1] + [
            {"role": "user", "content": base[-1]["content"] + "\n\n" + question}
        ]

    def gate_messages(
        self,
        *,
        turns: Sequence[ConversationTurn],
        summary: str = "",
        engagement: str = "called",
        question: str = "called",
    ) -> list[dict[str, str]] | None:
        """The 是/否 request asked before writing a line: the cached chat with
        a gate question on the end ("called": is this line for you; "active":
        would joining in now be natural). None when the character spoke last."""
        base = self.character_messages(
            turns=turns, summary=summary, engagement=engagement, gate=True
        )
        if base[-1]["role"] != "user":
            return None
        return base[:-1] + [
            {
                "role": "user",
                "content": base[-1]["content"]
                + "\n\n"
                + templates._GATE_QUESTION[question],
            }
        ]

    def character_messages(
        self,
        *,
        turns: Sequence[ConversationTurn],
        summary: str = "",
        addressed: bool = False,
        engagement: str = "called",
        gate: bool = False,
        joining: bool = False,
        lull: bool = False,
        task_hint: tuple[str, str] | None = None,
    ) -> list[dict[str, str]]:
        """The chat as messages. Everything but the tail of the last message
        is byte-identical to the previous request's, for the prompt cache.
        `gate` leaves out the per-request hints (the gate adds its question)."""
        persona = self.persona
        messages = [
            {
                "role": "system",
                "content": self._build_turn_system_prompt(persona, engagement),
            }
        ]
        if summary:
            messages.append(
                {"role": "user", "content": f"（這場對話稍早的重點：{summary}）"}
            )
        for turn in _stable_window(turns):
            if turn.is_self:
                if messages[-1]["role"] == "system":
                    # Chat templates want a user turn first.
                    messages.append({"role": "user", "content": "（對話開始）"})
                if messages[-1]["role"] == "assistant":
                    messages[-1]["content"] += "\n" + turn.text
                else:
                    messages.append({"role": "assistant", "content": turn.text})
                continue
            line = f"{turn.speaker_name}：{turn.text}"
            if self.agent_dispatch and turn.via == "text":
                # Only typed orders reach the Agent, so the character has to
                # see which lines were typed (a spoken order gets "type it").
                line = f"{turn.speaker_name}（打字）：{turn.text}"
            if messages[-1]["role"] == "user":
                messages[-1]["content"] += "\n" + line
            else:
                messages.append({"role": "user", "content": line})
        if lull and messages[-1]["role"] != "user":
            # The character spoke last; the lull itself is the new "message".
            messages.append({"role": "user", "content": "（安靜）"})
        if task_hint is not None and messages[-1]["role"] != "user":
            # The Agent's news arrives after the character's own line.
            messages.append({"role": "user", "content": "（思考機有消息）"})
        if messages[-1]["role"] != "user" or gate:
            return messages
        # Per-request hints ride on the end of the newest message only; the
        # next request drops them again, which costs a few tokens of prefill.
        hints = []
        if task_hint is not None:
            kind, detail = task_hint
            hints.append(templates.TASK_HINTS[kind].format(detail=detail))
        elif lull:
            hints.append(templates._LULL_HINT)
        elif addressed:
            hints.append("（最後這句是在叫你，要回應）")
        elif joining:
            # "active" mode chiming in: nobody called it, so it must not
            # answer as if someone had.
            hints.append("（沒有人叫你，你決定自然地插一句話）")
        # It knows what time it is ("都半夜了還不睡"): with memory on only;
        # on Gemma 4 E2B the clock was part of a variant that lost.
        if self.memory != "off":
            hints.append(f"（現在是{_now_words()}）")
        if not persona.is_blank:
            hints.append(persona.reminder_line("開口的話要是", list_catchphrases=False))
        used = [
            phrase
            for phrase in persona.signature_phrases()
            if any(_signature_used(phrase, line) for line in self.recent_lines)
        ]
        if used:
            hints.append(
                "（你最近已經說過"
                + "、".join(f"「{p}」" for p in used[:3])
                + "，這句換個說法，不要再用）"
            )
        if self.ai_honesty == "admit":
            recent = [turn.text for turn in turns if not turn.is_self][-4:]
            if asks_if_ai("\n".join(recent)):
                hints.append(
                    "（有人在問你是不是 AI 或真人：要老實承認你是 AI 扮演的角色，用你的口吻說）"
                )
        if hints:
            messages[-1] = {
                "role": "user",
                "content": messages[-1]["content"] + "\n\n" + "\n".join(hints),
            }
        return messages

    def _build_turn_system_prompt(self, persona: Persona, engagement: str) -> str:
        sheet = persona.render_prompt_block()
        # All of them, not just who is talking right now: the list is part of
        # the persona, so it stays in the cached prompt. This is what makes a
        # character treat the owner as its husband, kid or brother.
        relations = [
            f"- {rel.name}：{rel.relation}"
            for rel in persona.relationships
            if rel.name and rel.relation
        ]
        if relations:
            sheet += (
                "\n你和這些人的關係（他們說話時，對話裡會出現這個名字）：\n"
                + "\n".join(relations)
                # M1 family chats: a wife answered "老婆你選哪臺車啊" as if
                # she were the husband, and missed lines that opened with 老婆.
                + "\n他們用關係叫你（例如「老婆」「媽」「阿嬤」「哥」）就是在叫你；"
                "你跟他們說話要符合這個關係，不要搞混誰是誰。"
            )
        name = persona.name.strip()
        return templates._TURN_SYSTEM.format(
            who=f"「{name}」" if name else "一個友善、好聊的朋友",
            engagement=templates._ENGAGEMENT_RULES.get(
                engagement, templates._ENGAGEMENT_RULES["called"]
            ),
            ai_rule={
                "admit": templates._AI_ADMIT,
                "machine": templates._AI_MACHINE,
            }.get(self.ai_honesty, templates._AI_IN_CHARACTER),
            abilities=templates._CAN_DISPATCH.format(
                owner=f"「{self.owner_name}」" if self.owner_name else "",
            )
            if self.agent_dispatch
            else (templates._CAN_TYPE if self.can_type else templates._VOICE_ONLY),
            length=persona.length_rule(),
            max_chars=self.max_reply_chars,
            sheet=f"\n【你的人設】口吻、用詞、句長、立場都照這裡：\n{sheet}\n{self._state_block()}"
            if sheet
            else "",
        )

    def _state_block(self) -> str:
        if self.memory == "off":
            items = self.agenda
            if not items:
                return ""
            return (
                templates._AGENDA_HEADER
                + "\n"
                + "\n".join(f"- {item}" for item in items)
                + "\n"
            )
        block = self.life.prompt_block(full=self.memory == "full")
        return f"\n【你自己的生活】\n{block}\n" if block else ""

    @property
    def state(self) -> CharacterState:
        return self.life

    @property
    def agenda(self) -> tuple[str, ...]:
        """What is on its mind right now (the active concerns)."""
        return tuple(concern.text for concern in self.life.active_concerns())

    def set_state(self, state: CharacterState) -> None:
        """Takes effect on the next request (the system prompt cache refills once)."""
        self.life = state

    def set_agenda(self, items: Sequence[str]) -> None:
        """Concerns only, nothing else about its life (tests and evals)."""
        self.life = CharacterState(concerns=tuple(Concern(item) for item in items))


def _stable_window(turns: Sequence[ConversationTurn]) -> Sequence[ConversationTurn]:
    """The newest turns, trimmed a batch at a time so the start stays put."""
    excess = len(turns) - templates._TURN_WINDOW
    if excess <= 0:
        return turns
    start = -(-excess // templates._TURN_DROP_BATCH) * templates._TURN_DROP_BATCH
    return turns[start:]


def _now_words(now: datetime | None = None) -> str:
    """ "星期五晚上 11:40": the local time the way people say it."""
    now = now or datetime.now()
    hour = now.hour
    part = (
        "半夜"
        if hour < 5
        else "清晨"
        if hour < 8
        else "早上"
        if hour < 11
        else "中午"
        if hour < 13
        else "下午"
        if hour < 18
        else "晚上"
    )
    return f"星期{templates._WEEKDAYS[now.weekday()]}{part} {now:%H:%M}"
