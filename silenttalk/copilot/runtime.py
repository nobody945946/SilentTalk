from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from silenttalk.config import CopilotConfig
from silenttalk.copilot.character import (
    CharacterPolicy,
    CharacterState,
    is_addressed,
    should_reply,
)
from silenttalk.copilot.context import ConversationStore
from silenttalk.copilot.llm import LocalReplyModel
from silenttalk.copilot.persona import Persona, blank_persona
from silenttalk.copilot.stt import StreamingTranscriber
from silenttalk.copilot.stt_offline import OfflineTranscriber
from silenttalk.copilot.types import ConversationTurn, ReplySuggestions

_LOG = logging.getLogger(__name__)

SuggestionCallback = Callable[[ReplySuggestions], None]
MessageCallback = Callable[[str], None]
TurnCallback = Callable[[ConversationTurn], None]
ThinkingCallback = Callable[[str, str], None]
LineCallback = Callable[[str], None]

# "嗯", "好", "喔" are context, not something worth four reply options.
_MIN_TRIGGER_CHARS = 2


@dataclass(frozen=True, slots=True)
class _Trigger:
    speaker_name: str
    text: str
    # Position in the conversation, to notice when the chat moved on.
    seq: int = 0
    addressed: bool = False


class CopilotRuntime:
    """Owns local STT, conversation context, and local reply generation."""

    def __init__(
        self,
        project_dir: Path,
        config: CopilotConfig,
        owner_user_id: int,
        on_suggestions: SuggestionCallback,
        on_error: MessageCallback,
        *,
        on_turn: TurnCallback | None = None,
        on_thinking: ThinkingCallback | None = None,
        on_character_line: LineCallback | None = None,
    ) -> None:
        self._config = config
        self._owner_user_id = owner_user_id
        self._on_suggestions = on_suggestions
        self._on_error = on_error
        self._on_turn = on_turn
        self._on_thinking = on_thinking
        self._on_character_line = on_character_line
        self._persona = blank_persona()
        self._character_mode = False
        self._character_policy = CharacterPolicy(
            cooldown_seconds=config.character_cooldown_seconds,
            turn_gap=config.character_turn_gap,
        )
        self._character_state = CharacterState()
        self._turn_seq = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: _Trigger | None = None
        self._latest_trigger: _Trigger | None = None
        self._wake: asyncio.Event | None = None
        self._worker: asyncio.Task[None] | None = None

        runtime_dir = project_dir / ".runtime"
        if config.stt_engine == "sensevoice":
            transcriber, asr_dir = OfflineTranscriber, runtime_dir / "models" / "sensevoice"
        else:
            transcriber, asr_dir = StreamingTranscriber, runtime_dir / "models" / "asr"
        llm_model = runtime_dir / "models" / "llm" / config.llm_model

        self._context = ConversationStore(
            recent_turns=config.recent_turns,
            max_turns=config.max_session_turns,
            char_budget=config.context_char_budget,
            older_self_turns=4,
        )
        self._llm = LocalReplyModel(
            llm_model,
            port=config.llama_port,
            context_size=config.llm_context_size,
            max_reply_chars=config.max_reply_chars,
            gpu_layers=config.llm_gpu_layers,
            low_vram=config.llm_low_vram,
        )
        self._stt = transcriber(
            asr_dir,
            on_turn=self._on_transcribed_turn,
            on_error=on_error,
            endpoint_silence_ms=config.endpoint_silence_ms,
        )

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        await asyncio.to_thread(self._stt.start)
        await self._llm.start()
        self._worker = asyncio.create_task(
            self._suggestion_worker(), name="copilot-suggestion-worker"
        )
        _LOG.info("copilot_runtime_ready")

    async def stop(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        await asyncio.to_thread(self._stt.stop)
        await self._llm.stop()
        self._loop = None

    def accept_pcm(self, speaker_id: int, speaker_name: str, pcm: bytes) -> None:
        self._stt.push_pcm(speaker_id, speaker_name, pcm)

    def record_self(self, text: str) -> None:
        """Something the bot actually said aloud (after playback finished)."""
        name = "你"
        if self._character_mode and self._persona.name.strip():
            name = self._persona.name.strip()
        turn = ConversationTurn.now(self._owner_user_id, name, text, is_self=True)
        self._context.append(turn)
        self._emit_turn(turn)
        self._character_state.spoke(time.monotonic())

    def set_persona(self, persona: Persona) -> None:
        """Must run on the runtime loop; applies from the next generation on."""
        self._persona = persona
        self._llm.set_persona(persona)
        _LOG.info("copilot_persona_set blank=%s", persona.is_blank)

    def set_character_mode(self, enabled: bool) -> None:
        """Copilot (you pick, the bot says it) vs. character (the bot is the
        persona and joins in by itself). Must run on the runtime loop."""
        if enabled == self._character_mode:
            return
        self._character_mode = enabled
        self._pending = None
        self._character_state = CharacterState(turns_since_spoke=0)
        _LOG.info("copilot_character_mode enabled=%s", enabled)

    def regenerate(self) -> bool:
        """Ask again for the newest line. Must run on the runtime loop."""
        if self._latest_trigger is None or self._wake is None:
            return False
        self._pending = self._latest_trigger
        self._wake.set()
        return True

    def _on_transcribed_turn(
        self,
        speaker_id: int,
        speaker_name: str,
        text: str,
    ) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._handle_turn, speaker_id, speaker_name, text)

    def _handle_turn(
        self,
        speaker_id: int,
        speaker_name: str,
        text: str,
    ) -> None:
        # In copilot mode the bot speaks *for* the owner, so the owner's own mic
        # is not conversation; in character mode the owner is one more friend.
        if speaker_id == self._owner_user_id and not self._character_mode:
            return

        turn = ConversationTurn.now(speaker_id, speaker_name, text)
        self._context.append(turn)
        self._emit_turn(turn)
        self._turn_seq += 1
        if self._character_mode:
            self._character_state.heard()
        if len(_compact(text)) < _MIN_TRIGGER_CHARS or self._wake is None:
            return

        trigger = _Trigger(speaker_name, text, self._turn_seq)
        if self._character_mode:
            addressed = is_addressed(text, self._persona)
            if not should_reply(
                self._character_policy,
                self._character_state,
                text,
                addressed=addressed,
                now=time.monotonic(),
            ):
                return
            trigger = _Trigger(speaker_name, text, self._turn_seq, addressed)

        # Latest wins: while a generation is running, newer lines replace the
        # queued trigger instead of stacking requests on a small GPU.
        self._latest_trigger = trigger
        self._pending = trigger
        self._wake.set()

    async def _suggestion_worker(self) -> None:
        assert self._wake is not None
        while True:
            await self._wake.wait()
            self._wake.clear()
            trigger, self._pending = self._pending, None
            if trigger is None:
                continue
            if self._character_mode:
                await self._speak(trigger)
            else:
                await self._generate(trigger)

    async def _speak(self, trigger: _Trigger) -> None:
        started = time.perf_counter()
        try:
            line = await self._llm.character_reply(
                context=self._context.render_for_prompt(),
                trigger_speaker=trigger.speaker_name,
                trigger_text=trigger.text,
                addressed=trigger.addressed,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOG.warning("copilot_character_failed error_type=%s", type(exc).__name__)
            self._on_error(f"角色回話產生失敗：{exc}")
            return
        moved_on = self._turn_seq - trigger.seq
        _LOG.info(
            "copilot_character_line latency_ms=%d spoke=%s addressed=%s moved_on=%d",
            round((time.perf_counter() - started) * 1000),
            bool(line),
            trigger.addressed,
            moved_on,
        )
        if not line or not self._character_mode:
            return
        if moved_on >= self._character_policy.stale_turns and not trigger.addressed:
            return  # the chat moved on; a late reply would sound off
        if self._on_character_line is not None:
            self._on_character_line(line)

    async def _generate(self, trigger: _Trigger) -> None:
        if self._on_thinking is not None:
            self._on_thinking(trigger.speaker_name, trigger.text)
        context = self._context.render_for_prompt()
        started = time.perf_counter()
        try:
            suggestions = await self._llm.suggest(
                context=context,
                trigger_speaker=trigger.speaker_name,
                trigger_text=trigger.text,
                on_partial=self._on_suggestions,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOG.warning(
                "copilot_suggestion_failed error_type=%s",
                type(exc).__name__,
            )
            self._on_error(f"Copilot 建議產生失敗：{exc}")
            suggestions = ReplySuggestions(
                trigger_speaker=trigger.speaker_name,
                trigger_text=trigger.text,
                error=str(exc),
            )
        _LOG.info(
            "copilot_suggestion_ready latency_ms=%d lanes=%d failed=%s",
            round((time.perf_counter() - started) * 1000),
            sum(bool(text) for _, text in suggestions.items()),
            bool(suggestions.error),
        )
        self._on_suggestions(suggestions)

    def _emit_turn(self, turn: ConversationTurn) -> None:
        if self._on_turn is None:
            return
        try:
            self._on_turn(turn)
        except Exception:
            _LOG.exception("copilot_turn_callback_failed")


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())
