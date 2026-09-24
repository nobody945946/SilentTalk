from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from silenttalk.config import CopilotConfig
from silenttalk.copilot.context import ConversationStore
from silenttalk.copilot.llm import LocalReplyModel
from silenttalk.copilot.stt import StreamingTranscriber
from silenttalk.copilot.types import ReplySuggestions

_LOG = logging.getLogger(__name__)

SuggestionCallback = Callable[[ReplySuggestions], None]
MessageCallback = Callable[[str], None]


class CopilotRuntime:
    """Owns local STT, conversation context, and local reply generation."""

    def __init__(
        self,
        project_dir: Path,
        config: CopilotConfig,
        owner_user_id: int,
        on_suggestions: SuggestionCallback,
        on_error: MessageCallback,
    ) -> None:
        self._config = config
        self._owner_user_id = owner_user_id
        self._on_suggestions = on_suggestions
        self._on_error = on_error
        self._loop: asyncio.AbstractEventLoop | None = None
        self._generation = 0

        runtime_dir = project_dir / ".runtime"
        asr_dir = runtime_dir / "models" / "asr"
        llm_model = runtime_dir / "models" / "llm" / "Qwen3-0.6B-Q4_K_M.gguf"

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
        )
        self._stt = StreamingTranscriber(
            asr_dir,
            on_turn=self._on_transcribed_turn,
            on_error=on_error,
            endpoint_silence_ms=config.endpoint_silence_ms,
        )

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        await asyncio.to_thread(self._stt.start)
        await self._llm.start()
        _LOG.info("copilot_runtime_ready")

    async def stop(self) -> None:
        await asyncio.to_thread(self._stt.stop)
        await self._llm.stop()
        self._loop = None

    def accept_pcm(self, speaker_id: int, speaker_name: str, pcm: bytes) -> None:
        self._stt.push_pcm(speaker_id, speaker_name, pcm)

    def record_self(self, text: str) -> None:
        self._context.append_self(self._owner_user_id, text)

    def _on_transcribed_turn(
        self,
        speaker_id: int,
        speaker_name: str,
        text: str,
    ) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(
                self._handle_turn(speaker_id, speaker_name, text),
                name="copilot-reply-suggestions",
            )
        )

    async def _handle_turn(
        self,
        speaker_id: int,
        speaker_name: str,
        text: str,
    ) -> None:
        if speaker_id == self._owner_user_id:
            return

        self._context.append_external(speaker_id, speaker_name, text)
        self._generation += 1
        generation = self._generation
        context = self._context.render_for_prompt()

        try:
            suggestions = await self._llm.suggest(
                context=context,
                trigger_speaker=speaker_name,
                trigger_text=text,
            )
        except Exception as exc:
            _LOG.warning(
                "copilot_suggestion_failed error_type=%s",
                type(exc).__name__,
            )
            self._on_error(f"Copilot 建議產生失敗：{exc}")
            return

        if generation != self._generation:
            return
        self._on_suggestions(suggestions)
