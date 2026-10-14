from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Sequence
from pathlib import Path

from silenttalk.conversation import AgentTask, ConversationTurn
from silenttalk.copilot import character_generation
from silenttalk.copilot import reply_templates as templates
from silenttalk.copilot.character_state import (
    CharacterState,
)
from silenttalk.copilot.reply_parsing import (
    _alike_to,
    _strip_thinking,
    parse_character_line,
    quiet_for,
)
from silenttalk.copilot.reply_prompts import ReplyPrompts
from silenttalk.copilot.reply_transport import InferenceDeferred, ReplyTransport
from silenttalk.copilot.script import to_taiwan_traditional
from silenttalk.persona import Persona

_LOG = logging.getLogger(__name__)


class LocalReplyModel:
    """Leased inference client for local character replies."""

    def __init__(
        self,
        model_path: Path,
        *,
        port: int = 18088,
        context_size: int = 2048,
        max_reply_chars: int = 72,
        request_timeout_seconds: float = 15.0,
        can_type: bool = False,
        ai_honesty: str = "in_character",
        lora_path: Path | None = None,
        lora_uses: Iterable[str] = ("called", "active", "line"),
        memory: str = "off",
        project_dir: Path | None = None,
        agent_dispatch: bool = False,
        owner_id: int | None = None,
        owner_name: str = "",
    ) -> None:
        self._model_path = model_path
        self._lora_path = lora_path
        # Which requests the adapter is applied to (LORA_PARTS): it can help
        # one part and hurt another, so each is switched on only where the
        # eval says it wins.
        self._lora_uses = frozenset(lora_uses)
        # Set once the adapter is on llama-server's command line.
        self._port = port
        # The owner's Discord user ID: the only speaker whose lines can
        # become the Agent's work. Unset, nothing can.
        self._project_dir = project_dir or Path.cwd()
        # Kept as a readable invariant for callers/tests: there is no unmanaged
        # fallback anymore. SilentTalk always leases the independent EdgeAgent.
        self._managed_service = True
        self.transport = ReplyTransport(
            self._project_dir, port, lora_path is not None, request_timeout_seconds
        )
        self.prompts = ReplyPrompts(
            can_type=can_type,
            ai_honesty=ai_honesty,
            agent_dispatch=agent_dispatch,
            owner_id=owner_id,
            owner_name=owner_name,
            max_reply_chars=max_reply_chars,
            memory=memory,
        )
        # Its own life (CharacterState), part of the system prompt.
        # What the character said lately, to stop it repeating its catchphrases.

    def set_ai_honesty(self, mode: str) -> None:
        self.prompts.ai_honesty = mode

    def set_owner(self, user_id: int, name: str) -> None:
        """The owner (Discord user ID, display name): whose lines can become
        the Agent's work, and whose name the character knows them by."""
        self.prompts.owner_id = user_id
        self.prompts.owner_name = name.strip()

    def set_max_reply_chars(self, value: int) -> None:
        self.prompts.max_reply_chars = max(24, value)

    def set_persona(self, persona: Persona) -> None:
        """Takes effect on the next request; the system prompt cache refills once."""
        if persona.id != self.prompts.persona.id:
            self.prompts.recent_lines.clear()
            self.prompts.life = CharacterState()
        self.prompts.persona = persona

    async def start(self) -> None:
        await self.transport.start()

    async def stop(self) -> None:
        await self.transport.stop()

    async def turn(self, deferred: InferenceDeferred) -> None:
        """Until EdgeAgent would take the request it deferred."""
        await self.transport.turn(deferred)

    @property
    def state(self) -> CharacterState:
        return self.prompts.state

    @property
    def agenda(self) -> tuple[str, ...]:
        return self.prompts.agenda

    def set_state(self, state: CharacterState) -> None:
        self.prompts.set_state(state)

    def set_agenda(self, items: Sequence[str]) -> None:
        self.prompts.set_agenda(items)

    async def fill_concerns(self, state: CharacterState) -> CharacterState:
        return await character_generation.fill_concerns(
            self.prompts, self.transport, state
        )

    async def update_state(self, turns: Sequence[ConversationTurn]) -> CharacterState:
        return await character_generation.update_state(
            self.prompts, self.transport, turns
        )

    async def summarize(self, transcript: str, previous: str = "") -> str:
        return await character_generation.summarize(
            self.transport, transcript, previous
        )

    def owner_messages(
        self, *, turns: Sequence[ConversationTurn], engagement: str = "called"
    ) -> list[dict[str, str]] | None:
        return self.prompts.owner_messages(turns=turns, engagement=engagement)

    def task_scope_messages(
        self, *, turns: Sequence[ConversationTurn], engagement: str = "called"
    ) -> list[dict[str, str]] | None:
        return self.prompts.task_scope_messages(turns=turns, engagement=engagement)

    def gate_messages(
        self,
        *,
        turns: Sequence[ConversationTurn],
        summary: str = "",
        engagement: str = "called",
        question: str = "called",
    ) -> list[dict[str, str]] | None:
        return self.prompts.gate_messages(
            turns=turns, summary=summary, engagement=engagement, question=question
        )

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
        return self.prompts.character_messages(
            turns=turns,
            summary=summary,
            addressed=addressed,
            engagement=engagement,
            gate=gate,
            joining=joining,
            lull=lull,
            task_hint=task_hint,
        )

    async def character_turn(
        self,
        *,
        turns: Sequence[ConversationTurn],
        summary: str = "",
        addressed: bool = False,
        engagement: str = "called",
        lull: bool = False,
        task_hint: tuple[str, str] | None = None,
    ) -> str:
        """What the character says after the newest line, or "" to stay quiet.

        `turns` is the whole chat so far, the character's own lines marked
        `is_self`; `addressed` is Discord's own @mention or reply signal.
        `lull`: the channel has gone quiet; open a topic, no gate.
        `task_hint`: (kind, detail) from TASK_HINTS while the Agent works on
        the owner's task; the character always speaks, no gate."""
        if task_hint is not None:
            messages = self.prompts.character_messages(
                turns=turns, summary=summary, engagement=engagement, task_hint=task_hint
            )
            raw = await asyncio.to_thread(
                self.transport.request_messages,
                messages,
                90,
                "line" in self._lora_uses,
            )
            line = parse_character_line(
                raw, "", self.prompts.persona, self.prompts.max_reply_chars
            )
            if line:
                self.prompts.recent_lines.append(line)
            return line
        if lull:
            messages = self.prompts.character_messages(
                turns=turns, summary=summary, engagement=engagement, lull=True
            )
            line = ""
            # Read out word for word, a concern sounds like a note, not like
            # talking (a check on 21 lulls: 2 near-copies).
            for temperature in (0.65, 1.0):
                raw = await asyncio.to_thread(
                    self.transport.request_messages,
                    messages,
                    90,
                    "line" in self._lora_uses,
                    temperature,
                )
                line = parse_character_line(
                    raw, "", self.prompts.persona, self.prompts.max_reply_chars
                )
                if not any(_alike_to(line, item, 0.8) for item in self.agenda):
                    break
            if line:
                self.prompts.recent_lines.append(line)
            return line
        joining = False
        if not addressed:
            # "called": a line is for the character only when it names it
            # (the app checks the name; the model does not guess).
            if engagement != "active" or (turns and turns[-1].is_self):
                return ""
            addressed = await self._gate(turns, summary, engagement, "called")
            if not addressed and engagement == "active":
                joining = quiet_for(
                    turns
                ) >= templates._JOIN_AFTER_QUIET_LINES and await self._gate(
                    turns, summary, engagement, "active"
                )
            if not addressed and not joining:
                return ""
        messages = self.prompts.character_messages(
            turns=turns,
            summary=summary,
            addressed=addressed,
            joining=joining,
            engagement=engagement,
        )
        if messages[-1]["role"] != "user":
            return ""
        raw = await asyncio.to_thread(
            self.transport.request_messages,
            messages,
            90,
            "line" in self._lora_uses,
        )
        newest = next((turn.text for turn in reversed(turns) if not turn.is_self), "")
        line = parse_character_line(
            raw, newest, self.prompts.persona, self.prompts.max_reply_chars
        )
        if line:
            self.prompts.recent_lines.append(line)
        return line

    def set_agent_dispatch(self, enabled: bool) -> None:
        self.prompts.agent_dispatch = enabled

    async def task_from_owner(
        self,
        *,
        turns: Sequence[ConversationTurn],
        engagement: str = "called",
    ) -> AgentTask | None:
        """The owner's newest typed line in his Agent thread, word for word,
        and whether it may change anything ("change") or only read ("read").
        None unless the newest line is the owner's (owner_messages)."""
        if not self.prompts.agent_dispatch:
            return None
        scope = self.prompts.task_scope_messages(turns=turns, engagement=engagement)
        if scope is None:
            return None
        changes = (
            await asyncio.to_thread(
                self.transport.request_gate, scope, "scope" in self._lora_uses
            )
            == "是"
        )
        return AgentTask(turns[-1].text, scope="change" if changes else "read")

    async def chat_task(
        self,
        *,
        turns: Sequence[ConversationTurn],
        summary: str = "",
        engagement: str = "called",
    ) -> AgentTask | None:
        """For a line that called the character in a chat: work for the Agent
        that stays within this chat ("public" scope), or None when it is
        something to answer in person. Anyone may ask."""
        if not self.prompts.agent_dispatch:
            return None
        gate = self.prompts.gate_messages(
            turns=turns, summary=summary, engagement=engagement, question="chat_task"
        )
        if gate is None:
            return None
        use_lora = "task" in self._lora_uses
        if await asyncio.to_thread(self.transport.request_gate, gate, use_lora) != "是":
            return None
        ask = gate[:-1] + [
            {
                "role": "user",
                "content": gate[-1]["content"].removesuffix(
                    templates._GATE_QUESTION["chat_task"]
                )
                + templates._CHAT_TASK_ASK,
            }
        ]
        raw = await asyncio.to_thread(
            self.transport.request_messages, ask, 250, use_lora, 0.3
        )
        text = to_taiwan_traditional(_strip_thinking(raw).strip())[
            : templates._CHAT_TASK_MAX_CHARS
        ]
        return AgentTask(text, scope="public") if text else None

    async def _gate(
        self,
        turns: Sequence[ConversationTurn],
        summary: str,
        engagement: str,
        question: str,
    ) -> bool:
        gate = self.prompts.gate_messages(
            turns=turns, summary=summary, engagement=engagement, question=question
        )
        if gate is None:
            return False
        use_lora = question in self._lora_uses
        return (
            await asyncio.to_thread(self.transport.request_gate, gate, use_lora) == "是"
        )

    async def make_agenda(self) -> tuple[str, ...]:
        """Top up what is on its mind to a few concerns; returns them all."""
        self.prompts.life = await self.fill_concerns(self.prompts.life)
        return self.agenda
