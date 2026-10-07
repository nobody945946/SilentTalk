from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

from silenttalk.agent_tasks import AgentTaskClient
from silenttalk.config import CopilotConfig
from silenttalk.conversation import (
    VOICE_ROOM,
    AgentTask,
    Attachment,
    ConversationTurn,
    ReplySuggestions,
    ThinkingCallback,
    TurnCallback,
)
from silenttalk.conversation import Trigger as _Trigger
from silenttalk.copilot.character import CharacterPolicy, NameMatcher, persona_names
from silenttalk.copilot.character_life import CharacterLife
from silenttalk.copilot.character_state import STATE_FILE, CharacterStateStore
from silenttalk.copilot.llm import LocalReplyModel
from silenttalk.copilot.replies import CharacterReplies
from silenttalk.copilot.sessions import ConversationSessions
from silenttalk.copilot.stt import StreamingTranscriber
from silenttalk.copilot.stt_offline import OfflineTranscriber
from silenttalk.copilot.task_runner import AgentTaskRunner
from silenttalk.persona import Persona, blank_persona
from silenttalk.records import TranscriptRecorder

_LOG = logging.getLogger(__name__)

SuggestionCallback = Callable[[ReplySuggestions], None]
MessageCallback = Callable[[str], None]
AgendaCallback = Callable[[tuple[str, ...]], None]

# How often the worker looks for a lull while nothing else wakes it.
_LULL_POLL_SECONDS = 1.0
LineCallback = Callable[[str], None]
# A typed answer and the place it goes to (VOICE_ROOM or a thread).
PlaceLineCallback = Callable[[str, int], None]
# The owner's message that handed over work: (channel, message, state), state
# "accepted" while the Agent works, then "done" or "failed".
TaskMarkCallback = Callable[[int, int, str], None]
# An Agent result posted in the thread it came from: (text, thread) -> sent.
ResultCallback = Callable[[str, int], Awaitable[bool]]
# A thread's earlier lines (thread, before message, limit) ->
# [(author ID, name, text, kind)], kind "mine", "agent" or "text"
# (DiscordVoiceClient.thread_history).
HistoryCallback = Callable[[int, int, int], Awaitable[list[tuple[int, str, str, str]]]]
# A file someone posted with the line (or in the message it replies to): its
# name and how to read it. The Discord client chooses which, never the model.

# "嗯", "好", "喔" are context, not something worth four reply options.
_MIN_TRIGGER_CHARS = 2
# one would slow every later reply there).
# whole result is typed into the chat).


class CopilotRuntime:
    """Owns local STT/context and leases reply generation from EdgeAgent."""

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
        on_character_text: PlaceLineCallback | None = None,
        on_agenda: AgendaCallback | None = None,
        can_type: bool = False,
        agent_tasks: AgentTaskClient | None = None,
        on_agent_approval: Callable[[dict[str, object]], Awaitable[None]] | None = None,
        on_agent_line: LineCallback | None = None,
        on_agent_private: Callable[[str], Awaitable[bool]] | None = None,
        on_agent_result: ResultCallback | None = None,
        on_task_mark: TaskMarkCallback | None = None,
        thread_history: HistoryCallback | None = None,
    ) -> None:
        self._config = config
        self._owner_user_id = owner_user_id
        self._on_turn = on_turn
        # Transcripts in the user's selected records folder (records.py).
        self._recorder = TranscriptRecorder(
            enabled=config.record_transcripts,
            folder=config.record_folder,
        )
        # The owner's DMs: every approval, and a result his thread could not
        # take; never the channel. False = not sent.
        # A result is posted where the work was asked for: the owner's thread
        # keeps it (reading the thread back restores it), a lookup's goes to
        # the chat it was asked in.
        # Reads a thread back when the app has no conversation for it.
        # Threads being read back: the lines that came in meanwhile, in order.
        # The line that started the running job: where to tell about it and
        # which message to mark; and the job's scope ("public" for a lookup).
        # (kind, detail, place): what the character is told to say about the job.
        # Lulls: when anyone last spoke in the voice room, and whether the
        # character already opened a topic in this quiet spell (only someone
        # else talking starts a new one, so it never talks to an empty room
        # twice). Threads have no lulls.
        # Whether a line calls the character (its names, by sound).
        self._names = NameMatcher(persona_names(blank_persona()))
        self._character_mode = False
        # Lines heard per place, to notice when a conversation moved on.
        self._turn_seq: dict[int, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        # The newest unanswered line of each place, oldest place first.
        self._pending: dict[int, _Trigger] = {}
        self._latest_trigger: _Trigger | None = None
        self._wake: asyncio.Event | None = None
        self._worker: asyncio.Task[None] | None = None

        runtime_dir = project_dir / ".runtime"
        if config.stt_engine == "sensevoice":
            transcriber, asr_dir = (
                OfflineTranscriber,
                runtime_dir / "models" / "sensevoice",
            )
        else:
            transcriber, asr_dir = StreamingTranscriber, runtime_dir / "models" / "asr"
        llm_model = Path(config.llm_model)

        # One conversation per place: the voice room and each thread.
        # Keep this many turns verbatim; older ones are folded into a summary
        # so a long session never gets truncated mid-thought.
        self._llm = LocalReplyModel(
            llm_model,
            port=config.llama_port,
            context_size=config.llm_context_size,
            max_reply_chars=config.max_reply_chars,
            can_type=can_type,
            ai_honesty=config.character_ai_honesty,
            lora_path=(Path(config.character_lora) if config.character_lora else None),
            lora_uses=config.character_lora_uses,
            memory=config.character_memory,
            project_dir=project_dir,
            agent_dispatch=config.character_agent,
            owner_id=owner_user_id,
        )
        self.sessions = ConversationSessions(
            self._llm,
            config,
            owner_user_id,
            history=thread_history,
            self_name=self._self_name,
            on_evict=self._evict_pending,
        )
        self.life = CharacterLife(
            self._llm,
            CharacterStateStore(project_dir / STATE_FILE),
            config.character_memory,
            all_turns=self.sessions.all_turns,
            on_agenda=on_agenda,
        )
        self.replies = CharacterReplies(
            self._llm,
            config,
            context=self.sessions.context,
            sequence=lambda place: self._turn_seq.get(place, 0),
            pending=lambda: bool(self._pending),
            epoch=lambda: self.tasks.epoch,
            on_error=on_error,
            on_line=on_character_line,
            on_text=on_character_text,
            on_agent_line=on_agent_line or on_character_line,
            on_suggestions=on_suggestions,
            on_thinking=on_thinking,
        )
        self.tasks = AgentTaskRunner(
            agent_tasks,
            self._llm,
            on_approval=on_agent_approval,
            on_private=on_agent_private,
            on_result=on_agent_result,
            on_mark=on_task_mark,
            context=self.sessions.context,
            emit_turn=self._emit_turn,
            task_line=self.replies.task_line,
            wake=self._wake_worker,
        )
        self.tasks.engagement = self.replies.policy.mode
        self._stt = transcriber(
            asr_dir,
            on_turn=self._on_transcribed_turn,
            on_error=on_error,
            endpoint_silence_ms=config.endpoint_silence_ms,
        )

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.sessions.bind(self._loop)
        self.life.bind(self._loop)
        self._wake = asyncio.Event()
        await asyncio.to_thread(self._stt.start)
        await self._llm.start()
        self._worker = asyncio.create_task(
            self._suggestion_worker(), name="copilot-suggestion-worker"
        )
        _LOG.info("copilot_runtime_ready")

    async def stop(self) -> None:
        await self.tasks.stop_agent_task()
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        await self.life.stop(final_update=True)
        await self.sessions.stop()
        await asyncio.to_thread(self._stt.stop)
        await self._llm.stop()
        self._loop = None

    def accept_pcm(self, speaker_id: int, speaker_name: str, pcm: bytes) -> None:
        # Options speak for the owner, so their mic is not input there. In
        # character mode the owner is another participant the character hears.
        if speaker_id == self._owner_user_id and not self._character_mode:
            return
        self._stt.push_pcm(speaker_id, speaker_name, pcm)

    def accept_text(
        self,
        speaker_id: int,
        speaker_name: str,
        text: str,
        addressed: bool = False,
        *,
        place: int = VOICE_ROOM,
        channel_id: int = 0,
        message_id: int = 0,
        agent: bool = False,
        attachments: tuple[Attachment, ...] = (),
    ) -> None:
        """A line someone typed; safe from any thread. `addressed`: Discord
        says it @mentioned the bot or replied to it. `place`: VOICE_ROOM (the
        voice channel's chat), a text channel, or the thread it was typed in;
        `agent`: that thread is the owner's Agent thread. `channel_id` and
        `message_id` name the Discord message."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(
            self.sessions.receive_text,
            lambda: self._handle_turn(
                speaker_id,
                speaker_name,
                text,
                "text",
                addressed,
                place=place,
                channel_id=channel_id,
                message_id=message_id,
                agent=agent,
                attachments=attachments,
            ),
            place,
            message_id,
            agent,
        )

    def accepts_name(self, text: str) -> bool:
        """Whether a typed line calls the character by name; safe from any
        thread (the Discord client asks before passing on a text-channel line)."""
        return self._character_mode and self._names(text)

    def record_self(
        self, text: str, place: int = VOICE_ROOM, *, via: str = "voice"
    ) -> None:
        """Something the bot actually said aloud or typed (`via`), in that
        place (after playback finished or the message was sent)."""
        turn = ConversationTurn.now(
            self._owner_user_id,
            self._self_name(),
            text,
            is_self=True,
            via=via,
            place=place,
        )
        self.sessions.context(place).append(turn)
        self._emit_turn(turn)
        if place == VOICE_ROOM:
            # The silence counts from the last thing anyone said, the bot included.
            self.replies.last_heard_at = time.monotonic()
        self.life.note_turn()

    def _self_name(self) -> str:
        if self._character_mode and self.life.persona.name.strip():
            return self.life.persona.name.strip()
        return "你"

    @property
    def character_mode(self) -> bool:
        return self._character_mode

    def apply_settings(self, copilot: dict[str, object]) -> None:
        """Live settings from the settings page. Must run on the runtime loop.

        Only what does not need a reload: engagement, compaction and reply
        length. Model, port and STT engine are startup-only."""
        self._config = replace(
            self._config,
            character_lull_seconds=float(
                copilot.get(
                    "character_lull_seconds", self._config.character_lull_seconds
                )
            ),
            character_agent=bool(
                copilot.get("character_agent", self._config.character_agent)
            ),
            record_transcripts=bool(
                copilot.get("record_transcripts", self._config.record_transcripts)
            ),
            record_folder=str(
                copilot.get("record_folder", self._config.record_folder)
            ).strip(),
        )
        self._recorder.configure(
            enabled=self._config.record_transcripts,
            folder=self._config.record_folder,
        )
        self._llm.set_agent_dispatch(self._config.character_agent)
        self.tasks.enabled = self._character_mode and self._config.character_agent
        if not self._config.character_agent:
            self.tasks.invalidate()
        policy = self.replies.policy
        self.replies.policy = CharacterPolicy(
            mode=str(copilot.get("character_engagement", policy.mode)),
            stale_turns=policy.stale_turns,
        )
        self._config = replace(
            self._config,
            compact_context=bool(
                copilot.get("compact_context", self._config.compact_context)
            ),
            max_reply_chars=int(
                copilot.get("max_reply_chars", self._config.max_reply_chars)
            ),
            character_ai_honesty=str(
                copilot.get("character_ai_honesty", self._config.character_ai_honesty)
            ),
        )
        self.sessions.configure(copilot, self._config.compact_batch_turns)
        self.tasks.engagement = self.replies.policy.mode
        self.replies.configure(self._config)
        self.sessions.enabled = self._config.compact_context
        self._llm.set_max_reply_chars(self._config.max_reply_chars)
        self._llm.set_ai_honesty(
            str(copilot.get("character_ai_honesty", self._config.character_ai_honesty))
        )
        _LOG.info(
            "copilot_settings_applied engagement=%s compact=%s",
            self.replies.policy.mode,
            self._config.compact_context,
        )

    def set_character_mode(self, enabled: bool) -> None:
        """Copilot (you pick, the bot says it) vs. character (the bot is the
        persona and joins in by itself). Must run on the runtime loop."""
        if enabled == self._character_mode:
            return
        self._character_mode = enabled
        self.replies.enabled = enabled
        self.tasks.enabled = enabled and self._config.character_agent
        if not enabled:
            self.tasks.invalidate()
        self._pending.clear()
        _LOG.info("copilot_character_mode enabled=%s", enabled)

    def regenerate(self) -> bool:
        """Ask again for the newest line. Must run on the runtime loop."""
        if self._latest_trigger is None or self._wake is None:
            return False
        self._pending[self._latest_trigger.place] = self._latest_trigger
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
        via: str = "voice",
        mentioned: bool = False,
        *,
        place: int = VOICE_ROOM,
        channel_id: int = 0,
        message_id: int = 0,
        agent: bool = False,
        attachments: tuple[Attachment, ...] = (),
    ) -> None:
        # In copilot mode the bot speaks *for* the owner, so the owner's own mic
        # is not conversation; in character mode the owner is one more friend.
        if speaker_id == self._owner_user_id and not self._character_mode:
            return

        if speaker_id == self._owner_user_id:
            # Whose work the character may take (copilot.character_agent).
            self._llm.set_owner(speaker_id, speaker_name)
        turn = ConversationTurn.now(
            speaker_id, speaker_name, text, via=via, place=place
        )
        self.sessions.context(place).append(turn)
        self._emit_turn(turn)
        seq = self._turn_seq[place] = self._turn_seq.get(place, 0) + 1
        activity = self.life.note_turn()
        if place == VOICE_ROOM:
            self.replies.last_heard_at = activity
            self.replies.lull_spoken = False
        if self._wake is not None and not self._pending:
            # Nothing waiting to generate: a good moment to compact.
            self.sessions.maybe_compact(place)
        if len(_compact(text)) < _MIN_TRIGGER_CHARS or self._wake is None:
            return

        # A line calls the character by its name (by sound: speech
        # recognition writes 雞魂 for 機魂) or by Discord's @mention or reply:
        # the app decides, not the model.
        addressed = mentioned or (self._character_mode and self._names(text))
        trigger = _Trigger(
            speaker_name,
            text,
            seq,
            addressed,
            via,
            time.monotonic(),
            speaker_id,
            place,
            channel_id,
            message_id,
            tuple(attachments),
        )
        self._latest_trigger = trigger
        if agent:
            # The owner's Agent thread: his typed lines are the Agent's work
            # (names can be copied, IDs cannot; a voice can come from anyone
            # near his microphone). Nobody else's line is anybody's work.
            if (
                self._character_mode
                and self._config.character_agent
                and speaker_id == self._owner_user_id
                and via == "text"
            ):
                self.tasks.queue_owner(
                    trigger, tuple(self.sessions.context(place).snapshot())
                )
                self._wake.set()
            return
        if (
            self._character_mode
            and self.replies.policy.mode != "active"
            and not addressed
        ):
            return  # every line must call it (the owner chose this: 純A)
        # Latest wins: while a generation is running, a newer line of the same
        # place replaces its queued trigger instead of stacking requests on a
        # small GPU; places are answered in the order they spoke.
        self._pending[place] = trigger
        self._wake.set()

    async def _suggestion_worker(self) -> None:
        assert self._wake is not None
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=_LULL_POLL_SECONDS)
            except TimeoutError:
                if self.replies.lull_due():
                    await self.replies.open_topic()
                elif self.life.update_due(bool(self._pending)):
                    await self.life.update()
                continue
            self._wake.clear()
            if self.tasks.has_hint and self._character_mode:
                kind, detail, place = self.tasks.take_hint()
                await self.replies.task_line(kind, detail, place)
                self._wake.set()
                continue
            if (
                self.tasks.has_owner_task
                and self._character_mode
                and self._config.character_agent
            ):
                owner_trigger, turns = self.tasks.take_owner_task()
                await self.tasks.dispatch_owner(owner_trigger, turns)
                self._wake.set()
                continue
            if not self._pending:
                continue
            place = next(iter(self._pending))
            trigger = self._pending.pop(place)
            self.sessions.maybe_compact(place)
            if self._pending:
                self._wake.set()  # another place is waiting
            if self._character_mode:
                await self._respond(trigger)
            else:
                await self.replies.generate(trigger)

    async def _respond(self, trigger: _Trigger) -> None:
        """A line in a chat (the voice room or a text channel) that called the
        character: work that stays within this chat goes to the Agent (anyone
        may ask), anything else gets the character's answer."""
        if trigger.addressed and self._config.character_agent and self.tasks.available:
            epoch = self.tasks.epoch
            context = self.sessions.context(trigger.place)
            started = time.monotonic()
            try:
                task = await self._llm.chat_task(
                    turns=context.snapshot(),
                    summary=context.summary,
                    engagement=self.replies.policy.mode,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the character still answers
                _LOG.warning(
                    "agent_chat_task_decision_failed error_type=%s", type(exc).__name__
                )
                task = None
            _LOG.info(
                "agent_chat_task_decision latency_ms=%d chat_task=%s",
                round((time.monotonic() - started) * 1000),
                task is not None,
            )
            if task is not None:
                # Whatever the model wrote, work asked in a chat reaches only
                # what is in that chat and the web (EdgeAgent's "public").
                await self.tasks.dispatch(
                    trigger, AgentTask(task.text, scope="public"), epoch
                )
                return
        await self.replies.speak(trigger)

    def _emit_turn(self, turn: ConversationTurn) -> None:
        self._recorder.write(
            turn, self.life.persona.name.strip() if self._character_mode else ""
        )
        if self._on_turn is None:
            return
        try:
            self._on_turn(turn)
        except Exception:
            _LOG.exception("copilot_turn_callback_failed")

    def _wake_worker(self) -> None:
        if self._wake is not None:
            self._wake.set()

    def _evict_pending(self, place: int) -> None:
        self._pending.pop(place, None)
        self._turn_seq.pop(place, None)

    def set_persona(self, persona: Persona) -> None:
        self.life.set_persona(persona)
        self._names = NameMatcher(persona_names(persona))

    def refresh_agenda(self) -> None:
        self.life.refresh_agenda()

    def clear_life(self) -> None:
        self.life.clear_life()

    async def stop_agent_task(self) -> None:
        await self.tasks.stop_agent_task()


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())
