from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path

from silenttalk.agent_tasks import AgentTaskClient
from silenttalk.config import CopilotConfig
from silenttalk.copilot.character import CharacterPolicy
from silenttalk.copilot.character_state import STATE_FILE, CharacterStateStore
from silenttalk.copilot.context import ConversationStore
from silenttalk.copilot.llm import (
    APPROVAL_KINDS,
    PRIVATE_APPROVAL,
    PRIVATE_REPORTS,
    LocalReplyModel,
)
from silenttalk.copilot.persona import Persona, blank_persona
from silenttalk.copilot.stt import StreamingTranscriber
from silenttalk.copilot.stt_offline import OfflineTranscriber
from silenttalk.copilot.types import VOICE_ROOM, ConversationTurn, ReplySuggestions
from silenttalk.records import TranscriptRecorder

_LOG = logging.getLogger(__name__)

SuggestionCallback = Callable[[ReplySuggestions], None]
MessageCallback = Callable[[str], None]
TurnCallback = Callable[[ConversationTurn], None]
ThinkingCallback = Callable[[str, str], None]
AgendaCallback = Callable[[tuple[str, ...]], None]

# How often the worker looks for a lull while nothing else wakes it.
_LULL_POLL_SECONDS = 1.0
# Updating the character's life costs a 3050 Ti a few seconds of generation,
# so it never runs mid-chat: "light" waits for this long a silence (after any
# lull topic), "full" also runs every _FULL_UPDATE_LINES lines while idle.
_QUIET_UPDATE_SECONDS = 90.0
_FULL_UPDATE_LINES = 16
# Too little chat since the last update to be worth one.
_MIN_UPDATE_LINES = 4
LineCallback = Callable[[str], None]
# A typed answer and the place it goes to (VOICE_ROOM or a thread).
PlaceLineCallback = Callable[[str, int], None]
# The owner's message that handed over work: (channel, message, state), state
# "accepted" while the Agent works, then "done" or "failed".
TaskMarkCallback = Callable[[int, int, str], None]

# "嗯", "好", "喔" are context, not something worth four reply options.
_MIN_TRIGGER_CHARS = 2
# Threads kept in memory; the one quiet the longest is forgotten first.
_MAX_THREADS = 16
_BUSY = "目前工作仍在進行，請等完成後再交代下一件。"
# What a thread hears about a job besides the marks on the owner's message.
_THREAD_NOTICES = frozenset(
    {_BUSY, PRIVATE_REPORTS["undelivered"], PRIVATE_REPORTS["approval_undelivered"]}
)


@dataclass(frozen=True, slots=True)
class _Trigger:
    speaker_name: str
    text: str
    # Position in the conversation, to notice when the chat moved on.
    seq: int = 0
    # Discord's own signal: an @mention of the bot or a reply to it.
    addressed: bool = False
    via: str = "voice"
    # time.monotonic() when the line came in, to log how long an answer took
    # including any wait behind the previous generation.
    heard_at: float = 0.0
    speaker_id: int = 0
    # Where it was said (VOICE_ROOM or a thread) and the Discord message it
    # came in, which gets the task marks when it hands over work.
    place: int = VOICE_ROOM
    channel_id: int = 0
    message_id: int = 0


def _approval_kind(payload: dict[str, object]) -> str:
    """The kind of step an approval is for, in words the channel may hear."""
    explicit = str(payload.get("explicit", ""))
    if explicit in APPROVAL_KINDS:
        return APPROVAL_KINDS[explicit]
    tool = str(payload.get("tool", ""))
    category = {"edit": "edit", "write": "edit", "powershell": "shell", "bash": "shell",
                "web_search": "web", "web_fetch": "web"}.get(tool, "shell")
    return APPROVAL_KINDS[category]


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
        on_task_mark: TaskMarkCallback | None = None,
    ) -> None:
        self._config = config
        self._owner_user_id = owner_user_id
        self._on_suggestions = on_suggestions
        self._on_error = on_error
        self._on_turn = on_turn
        # Transcripts on the user's encrypted records drive (records.py).
        self._recorder = TranscriptRecorder(
            enabled=config.record_transcripts, folder=config.record_folder,
        )
        self._on_thinking = on_thinking
        self._on_character_line = on_character_line
        self._on_character_text = on_character_text
        self._on_agenda = on_agenda
        self._agent_tasks = agent_tasks
        self._on_agent_approval = on_agent_approval
        self._on_agent_line = on_agent_line or on_character_line
        # The owner's DMs: the Agent's results and errors go here, never to
        # the channel unless copilot.agent_report_public. False = not sent.
        self._on_agent_private = on_agent_private
        self._on_task_mark = on_task_mark
        self._agent_job: asyncio.Task[None] | None = None
        # The owner's line that started the running job: where to tell about
        # it and which message to mark.
        self._agent_origin: _Trigger | None = None
        # (kind, detail, place): what the character is told to say about the job.
        self._task_hints: deque[tuple[str, str, int]] = deque()
        self._owner_tasks: deque[tuple[_Trigger, tuple[ConversationTurn, ...]]] = deque()
        self._task_result = ""
        self._agent_epoch = 0
        self._agenda_task: asyncio.Task[None] | None = None
        self._memory = config.character_memory
        self._states = CharacterStateStore(project_dir / STATE_FILE)
        self._lines_since_update = 0
        # Lulls: when anyone last spoke in the voice room, and whether the
        # character already opened a topic in this quiet spell (only someone
        # else talking starts a new one, so it never talks to an empty room
        # twice). Threads have no lulls.
        self._last_heard_at = 0.0
        # When anyone last said anything anywhere (life updates wait for quiet).
        self._last_activity_at = 0.0
        self._lull_spoken = True
        self._persona = blank_persona()
        self._character_mode = False
        self._character_policy = CharacterPolicy(mode=config.character_engagement)
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
            transcriber, asr_dir = OfflineTranscriber, runtime_dir / "models" / "sensevoice"
        else:
            transcriber, asr_dir = StreamingTranscriber, runtime_dir / "models" / "asr"
        llm_model = Path(config.llm_model)

        # One conversation per place: the voice room and each thread.
        self._max_session_turns = config.max_session_turns
        self._contexts: dict[int, ConversationStore] = {}
        # Keep this many turns verbatim; older ones are folded into a summary
        # so a long session never gets truncated mid-thought.
        self._compact_keep = config.compact_keep_turns
        self._compact_trigger = self._compact_keep + max(4, config.compact_batch_turns)
        self._compacting: set[int] = set()
        self._llm = LocalReplyModel(
            llm_model,
            port=config.llama_port,
            context_size=config.llm_context_size,
            max_reply_chars=config.max_reply_chars,
            gpu_layers=config.llm_gpu_layers,
            low_vram=config.llm_low_vram,
            can_type=can_type,
            ai_honesty=config.character_ai_honesty,
            lora_path=(
                Path(config.character_lora) if config.character_lora else None
            ),
            lora_uses=config.character_lora_uses,
            memory=config.character_memory,
            project_dir=project_dir,
            agent_dispatch=config.character_agent,
            owner_id=owner_user_id,
            report_public=config.agent_report_public,
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
        await self.stop_agent_task()
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        # The chat is over: let its life move on once more before closing.
        if self._memory != "off" and self._lines_since_update >= _MIN_UPDATE_LINES:
            try:
                await asyncio.wait_for(self._update_life(), timeout=30)
            except (TimeoutError, asyncio.CancelledError):
                _LOG.warning("copilot_state_update_skipped reason=timeout")
        self._save_life()
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
        self, speaker_id: int, speaker_name: str, text: str, addressed: bool = False,
        *, place: int = VOICE_ROOM, channel_id: int = 0, message_id: int = 0,
    ) -> None:
        """A line someone typed; safe from any thread. `addressed`: Discord
        says it @mentioned the bot or replied to it. `place`: VOICE_ROOM (the
        voice channel's chat) or the thread it was typed in; `channel_id` and
        `message_id` name the Discord message."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(
            lambda: self._handle_turn(
                speaker_id, speaker_name, text, "text", addressed,
                place=place, channel_id=channel_id, message_id=message_id,
            )
        )

    def record_self(self, text: str, place: int = VOICE_ROOM, *, via: str = "voice") -> None:
        """Something the bot actually said aloud or typed (`via`), in that
        place (after playback finished or the message was sent)."""
        name = "你"
        if self._character_mode and self._persona.name.strip():
            name = self._persona.name.strip()
        turn = ConversationTurn.now(
            self._owner_user_id, name, text, is_self=True, via=via, place=place
        )
        self._context(place).append(turn)
        self._emit_turn(turn)
        if place == VOICE_ROOM:
            # The silence counts from the last thing anyone said, the bot included.
            self._last_heard_at = time.monotonic()
        self._last_activity_at = time.monotonic()
        self._lines_since_update += 1

    @property
    def character_mode(self) -> bool:
        return self._character_mode

    def _context(self, place: int) -> ConversationStore:
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
                self._pending.pop(old, None)
                self._turn_seq.pop(old, None)
        return store

    def _all_turns(self) -> list[ConversationTurn]:
        """Every place's recent turns in time order (for the character's life)."""
        return sorted(
            (t for store in self._contexts.values() for t in store.snapshot()),
            key=lambda t: t.created_at,
        )

    def set_persona(self, persona: Persona) -> None:
        """Must run on the runtime loop; applies from the next generation on."""
        changed = persona.id != self._persona.id
        if changed:
            self._save_life()  # the previous character's, before it is swapped out
        self._persona = persona
        self._llm.set_persona(persona)
        _LOG.info("copilot_persona_set blank=%s", persona.is_blank)
        if changed and self._memory != "off" and not persona.is_blank:
            self._llm.set_state(self._states.load(persona.id))
            self._lines_since_update = 0
        if changed or not self._llm.agenda:
            self._start_agenda(reroll=False)

    def refresh_agenda(self) -> None:
        """換一批: new concerns in place of the ones it has not brought up yet.
        Must run on the runtime loop."""
        self._start_agenda(reroll=True)

    def clear_life(self) -> None:
        """Forget what the character carried between sessions (persona page).
        Must run on the runtime loop."""
        if not self._persona.is_blank:
            self._states.clear(self._persona.id)
        self._llm.set_state(type(self._llm.state)())
        self._start_agenda(reroll=False)

    def _start_agenda(self, *, reroll: bool) -> None:
        if self._loop is None or self._persona.is_blank:
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
            tuple(c.text + marks.get(c.status, "") for c in self._llm.state.active_concerns())
        )

    def _save_life(self) -> None:
        if self._memory == "off" or self._persona.is_blank or self._llm.state.is_empty:
            return
        try:
            self._states.save(self._persona.id, self._llm.state)
        except OSError as exc:
            _LOG.warning("copilot_state_save_failed error_type=%s", type(exc).__name__)

    def _update_due(self) -> bool:
        if self._memory == "off" or self._persona.is_blank or self._pending:
            return False
        if self._memory == "full" and self._lines_since_update >= _FULL_UPDATE_LINES:
            return True
        quiet = time.monotonic() - self._last_activity_at
        return self._lines_since_update >= _MIN_UPDATE_LINES and quiet >= _QUIET_UPDATE_SECONDS

    async def _update_life(self) -> None:
        """How the chat moved its life on: concerns shared, progressing, done
        or dropped, new ones, recent and mood (views and feelings in "full").
        Counts only in the log; the state itself is the user's file."""
        started = time.perf_counter()
        self._lines_since_update = 0
        try:
            state = await self._llm.update_state(self._all_turns())
            if len(state.active_concerns()) < 2:
                state = await self._llm.fill_concerns(state)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOG.warning("copilot_state_update_failed error_type=%s", type(exc).__name__)
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

    def apply_settings(self, copilot: dict[str, object]) -> None:
        """Live settings from the settings page. Must run on the runtime loop.

        Only what does not need a reload: engagement, compaction and reply
        length. Model, port and STT engine are startup-only."""
        self._config = replace(
            self._config,
            character_lull_seconds=float(
                copilot.get("character_lull_seconds", self._config.character_lull_seconds)
            ),
            character_agent=bool(copilot.get("character_agent", self._config.character_agent)),
            agent_report_public=bool(
                copilot.get("agent_report_public", self._config.agent_report_public)
            ),
            record_transcripts=bool(
                copilot.get("record_transcripts", self._config.record_transcripts)
            ),
            record_folder=str(copilot.get("record_folder", self._config.record_folder)).strip(),
        )
        self._recorder.configure(
            enabled=self._config.record_transcripts, folder=self._config.record_folder,
        )
        self._llm.set_agent_dispatch(self._config.character_agent)
        self._llm.set_report_public(self._config.agent_report_public)
        if not self._config.character_agent:
            self._invalidate_agent_task()
        policy = self._character_policy
        self._character_policy = CharacterPolicy(
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
        self._compact_keep = max(
            8, int(copilot.get("compact_keep_turns", self._compact_keep))
        )
        self._compact_trigger = self._compact_keep + max(
            4, int(copilot.get("compact_batch_turns", self._config.compact_batch_turns))
        )
        self._llm.set_max_reply_chars(self._config.max_reply_chars)
        self._llm.set_ai_honesty(
            str(copilot.get("character_ai_honesty", self._config.character_ai_honesty))
        )
        _LOG.info(
            "copilot_settings_applied engagement=%s compact=%s",
            self._character_policy.mode,
            self._config.compact_context,
        )

    def set_character_mode(self, enabled: bool) -> None:
        """Copilot (you pick, the bot says it) vs. character (the bot is the
        persona and joins in by itself). Must run on the runtime loop."""
        if enabled == self._character_mode:
            return
        self._character_mode = enabled
        if not enabled:
            self._invalidate_agent_task()
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
    ) -> None:
        # In copilot mode the bot speaks *for* the owner, so the owner's own mic
        # is not conversation; in character mode the owner is one more friend.
        if speaker_id == self._owner_user_id and not self._character_mode:
            return

        if speaker_id == self._owner_user_id:
            # Whose work the character may take (copilot.character_agent).
            self._llm.set_owner(speaker_id, speaker_name)
        turn = ConversationTurn.now(speaker_id, speaker_name, text, via=via, place=place)
        self._context(place).append(turn)
        self._emit_turn(turn)
        seq = self._turn_seq[place] = self._turn_seq.get(place, 0) + 1
        self._last_activity_at = time.monotonic()
        if place == VOICE_ROOM:
            self._last_heard_at = self._last_activity_at
            self._lull_spoken = False
        self._lines_since_update += 1
        if self._wake is not None and not self._pending:
            # Nothing waiting to generate: a good moment to compact.
            self._maybe_compact(place)
        if len(_compact(text)) < _MIN_TRIGGER_CHARS or self._wake is None:
            return

        # In character mode every line goes to the model, which reads the
        # whole chat and decides whether it is being talked to (SKIP if not).
        # Keyword rules could not tell "阿凱你在嗎" from "我剛才跟阿凱講話".
        trigger = _Trigger(
            speaker_name, text, seq, mentioned, via, time.monotonic(), speaker_id,
            place, channel_id, message_id,
        )

        # Latest wins: while a generation is running, a newer line of the same
        # place replaces its queued trigger instead of stacking requests on a
        # small GPU; places are answered in the order they spoke.
        self._latest_trigger = trigger
        if (
            self._character_mode
            and self._config.character_agent
            and speaker_id == self._owner_user_id
            and via == "text"
        ):
            # The only way into the Agent: a line typed by the configured
            # owner's Discord user ID (names can be copied, IDs cannot; a
            # voice can come from anyone near the owner's microphone).
            self._owner_tasks.append((trigger, tuple(self._context(place).snapshot())))
            self._wake.set()
            return
        self._pending[place] = trigger
        self._wake.set()

    def _maybe_compact(self, place: int) -> None:
        """Start folding a place's oldest turns into its summary, off the hot path."""
        loop = self._loop
        if place in self._compacting or loop is None or not self._config.compact_context:
            return
        if len(self._context(place).snapshot()) < self._compact_trigger:
            return
        self._compacting.add(place)
        loop.create_task(self._compact(place), name="copilot-compact")

    async def _compact(self, place: int) -> None:
        context = self._context(place)
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
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOG.warning("copilot_compact_failed", exc_info=False)
        finally:
            self._compacting.discard(place)

    async def _suggestion_worker(self) -> None:
        assert self._wake is not None
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=_LULL_POLL_SECONDS)
            except TimeoutError:
                if self._lull_due():
                    await self._open_topic()
                elif self._update_due():
                    await self._update_life()
                continue
            self._wake.clear()
            if self._task_hints and self._character_mode:
                kind, detail, place = self._task_hints.popleft()
                await self._task_line(kind, detail, place)
                self._wake.set()
                continue
            if self._owner_tasks and self._character_mode and self._config.character_agent:
                owner_trigger, turns = self._owner_tasks.popleft()
                if not await self._dispatch_owner(owner_trigger, turns):
                    await self._speak(owner_trigger)
                self._wake.set()
                continue
            if not self._pending:
                continue
            place = next(iter(self._pending))
            trigger = self._pending.pop(place)
            self._maybe_compact(place)
            if self._pending:
                self._wake.set()  # another place is waiting
            if self._character_mode:
                await self._speak(trigger)
            else:
                await self._generate(trigger)

    def _invalidate_agent_task(self) -> None:
        self._agent_epoch += 1
        self._task_hints.clear()
        self._owner_tasks.clear()
        self._task_result = ""
        if self._agent_job is not None:
            self._agent_job.cancel()
        origin, self._agent_origin = self._agent_origin, None
        if origin is not None:
            self._mark(origin, "failed")

    async def stop_agent_task(self) -> None:
        self._invalidate_agent_task()
        job, self._agent_job = self._agent_job, None
        if job is not None:
            await asyncio.gather(job, return_exceptions=True)

    def _mark(self, origin: _Trigger, state: str) -> None:
        """The owner's message that handed over the work: accepted, done or failed."""
        if self._on_task_mark is not None and origin.message_id:
            self._on_task_mark(origin.channel_id, origin.message_id, state)

    def _says(self, place: int, detail: str) -> bool:
        """Whether the character reports on the job in this place. In the
        voice room it acknowledges, asks for approvals and reports. In a
        thread the marks on the owner's message already say accepted and
        done, so it only types what the marks cannot: a DM that could not be
        delivered, or the result itself when the owner made results public
        (being busy is always said)."""
        return (
            place == VOICE_ROOM
            or self._config.agent_report_public
            or detail in _THREAD_NOTICES
        )

    async def _dispatch_owner(
        self, trigger: _Trigger, turns: tuple[ConversationTurn, ...]
    ) -> bool:
        if self._agent_tasks is None:
            return False
        epoch = self._agent_epoch
        started = time.monotonic()
        try:
            instruction = await self._llm.task_from_owner(
                turns=turns, engagement=self._character_policy.mode,
            )
            _LOG.info("agent_task_decision latency_ms=%d dispatched=%s",
                      round((time.monotonic() - started) * 1000), bool(instruction))
            if epoch != self._agent_epoch:
                return True
            if not instruction or not self._character_mode or not self._config.character_agent:
                return False
            if self._agent_job is not None and not self._agent_job.done():
                await self._task_line("report", _BUSY, trigger.place)
                return True
            workspace = await self._agent_tasks.workspace()
            if epoch != self._agent_epoch:
                return True
            self._agent_origin = trigger
            self._mark(trigger, "accepted")
            if trigger.place == VOICE_ROOM:
                await self._task_line("ack", instruction, VOICE_ROOM)
            if epoch != self._agent_epoch or not self._character_mode or not self._config.character_agent:
                return True
            self._task_result = ""
            self._agent_job = asyncio.create_task(
                self._run_agent_task(instruction, workspace, epoch), name="discord-agent-task",
            )
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - task failures must reach the character
            _LOG.warning("agent_task_dispatch_failed error_type=%s", type(exc).__name__)
            if epoch == self._agent_epoch:
                if self._agent_origin is trigger:
                    self._agent_origin = None
                self._mark(trigger, "failed")
                detail = await self._report_detail("error", str(exc))
                if self._says(trigger.place, detail):
                    await self._task_line("report", detail, trigger.place)
            return True

    async def _run_agent_task(self, instruction: str, workspace: str, epoch: int) -> None:
        assert self._agent_tasks is not None
        started = time.monotonic()
        async def on_event(kind: str, payload: dict[str, object]) -> None:
            if epoch == self._agent_epoch:
                await self._agent_event(kind, payload)
        try:
            await self._agent_tasks.run(instruction, workspace, on_event)
        finally:
            _LOG.info("agent_task_finished elapsed_ms=%d", round((time.monotonic() - started) * 1000))

    async def _agent_event(self, kind: str, payload: dict[str, object]) -> None:
        epoch = self._agent_epoch
        place = self._agent_origin.place if self._agent_origin is not None else VOICE_ROOM
        if kind == "delta":
            self._task_result = (self._task_result + str(payload.get("text", "")))[-2400:]
            return
        if kind == "approval":
            assert self._agent_tasks is not None
            if self._on_agent_approval is None:
                await self._agent_tasks.approve(str(payload["call_id"]), False)
                return
            try:
                await self._on_agent_approval(payload)
            except Exception as exc:  # noqa: BLE001 - failed approval delivery must deny the operation
                await self._agent_tasks.approve(str(payload["call_id"]), False)
                self._task_hints.append(("report", PRIVATE_REPORTS["approval_undelivered"], place))
                _LOG.warning("agent_approval_failed error_type=%s", type(exc).__name__)
            else:
                if epoch != self._agent_epoch:
                    return
                # The tool's arguments (paths, commands) went to the owner's
                # DMs with the buttons; the channel only hears what kind of step.
                if place == VOICE_ROOM:
                    detail = PRIVATE_APPROVAL.format(kind=_approval_kind(payload))
                    self._task_hints.append(("approval", detail, place))
        elif kind in {"done", "error", "cancelled"}:
            result = self._task_result if kind == "done" else str(payload.get("message", "工作已取消。"))
            self._task_result = ""
            detail = await self._report_detail(kind, result or "工作完成。")
            if epoch != self._agent_epoch:
                return
            origin, self._agent_origin = self._agent_origin, None
            if origin is not None:
                self._mark(origin, "done" if kind == "done" else "failed")
            if self._says(place, detail):
                self._task_hints.append(("report", detail, place))
        if self._wake is not None:
            self._wake.set()

    async def _report_detail(self, kind: str, result: str) -> str:
        """What the character is told of a finished task: the result itself
        with copilot.agent_report_public, otherwise only the outcome, after
        the result has gone to the owner's DMs."""
        if self._config.agent_report_public:
            return result
        if kind == "cancelled":
            return PRIVATE_REPORTS["cancelled"]
        delivered = False
        if self._on_agent_private is not None:
            try:
                delivered = await self._on_agent_private(result)
            except Exception as exc:  # noqa: BLE001 - an undelivered result is reported as such
                _LOG.warning("agent_private_failed error_type=%s", type(exc).__name__)
        _LOG.info("agent_result_private kind=%s delivered=%s", kind, delivered)
        return PRIVATE_REPORTS[kind if delivered else "undelivered"]

    async def _task_line(self, kind: str, detail: str, place: int = VOICE_ROOM) -> None:
        """The character's own words about the job, in the place the work
        came from: spoken in the voice room, typed in a thread."""
        if not self._character_mode or not self._config.character_agent:
            return
        epoch = self._agent_epoch
        started = time.monotonic()
        context = self._context(place)
        try:
            line = await self._llm.character_turn(
                turns=context.snapshot(), summary=context.summary,
                engagement=self._character_policy.mode, task_hint=(kind, detail),
            )
            if line and epoch == self._agent_epoch and self._character_mode and self._config.character_agent:
                if place == VOICE_ROOM:
                    if self._on_agent_line is not None:
                        self._on_agent_line(line)
                elif self._on_character_text is not None:
                    self._on_character_text(line, place)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - preserve the worker when notice generation fails
            _LOG.warning("agent_character_report_failed error_type=%s", type(exc).__name__)
            self._on_error("角色的工作回報暫時無法產生。")
        _LOG.info("agent_character_notice kind=%s latency_ms=%d", kind,
                  round((time.monotonic() - started) * 1000))

    def _lull_due(self) -> bool:
        seconds = self._config.character_lull_seconds
        return (
            self._character_mode
            and seconds > 0
            and not self._lull_spoken
            and not self._pending
            and time.monotonic() - self._last_heard_at >= seconds
        )

    async def _open_topic(self) -> None:
        """Nobody has said anything for a while: the character brings up
        something on its mind, or asks after someone."""
        self._lull_spoken = True
        heard_at = self._last_heard_at
        started = time.perf_counter()
        room = self._context(VOICE_ROOM)
        try:
            line = await self._llm.character_turn(
                turns=room.snapshot(),
                summary=room.summary,
                engagement=self._character_policy.mode,
                lull=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOG.warning("copilot_lull_failed error_type=%s", type(exc).__name__)
            return
        _LOG.info(
            "copilot_character_lull latency_ms=%d spoke=%s",
            round((time.perf_counter() - started) * 1000),
            bool(line),
        )
        # Someone spoke while it was thinking: the lull is over.
        if not line or not self._character_mode or self._last_heard_at != heard_at:
            return
        if self._on_character_line is not None:
            self._on_character_line(line)

    async def _speak(self, trigger: _Trigger) -> None:
        started = time.perf_counter()
        context = self._context(trigger.place)
        try:
            line = await self._llm.character_turn(
                turns=context.snapshot(),
                summary=context.summary,
                addressed=trigger.addressed,
                engagement=self._character_policy.mode,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOG.warning("copilot_character_failed error_type=%s", type(exc).__name__)
            self._on_error(f"角色回話產生失敗：{exc}")
            return
        moved_on = self._turn_seq.get(trigger.place, 0) - trigger.seq
        _LOG.info(
            "copilot_character_line latency_ms=%d since_heard_ms=%d spoke=%s"
            " addressed=%s moved_on=%d",
            round((time.perf_counter() - started) * 1000),
            round((time.monotonic() - trigger.heard_at) * 1000) if trigger.heard_at else -1,
            bool(line),
            trigger.addressed,
            moved_on,
        )
        if not line or not self._character_mode:
            return
        if moved_on >= self._character_policy.stale_turns and not trigger.addressed:
            return  # the chat moved on; a late reply would sound off
        # Answer where and how the line came in: a thread gets typed into
        # that thread; in the voice room typed gets typed and spoken gets
        # spoken, falling back to speaking if text is unavailable.
        if trigger.place != VOICE_ROOM:
            if self._on_character_text is not None:
                self._on_character_text(line, trigger.place)
        elif trigger.via == "text" and self._on_character_text is not None:
            self._on_character_text(line, VOICE_ROOM)
        elif self._on_character_line is not None:
            self._on_character_line(line)

    async def _generate(self, trigger: _Trigger) -> None:
        if self._on_thinking is not None:
            self._on_thinking(trigger.speaker_name, trigger.text)
        started = time.perf_counter()
        context = self._context(trigger.place)
        try:
            suggestions = await self._llm.suggest(
                turns=context.snapshot(),
                summary=context.summary,
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
        self._recorder.write(turn, self._persona.name.strip() if self._character_mode else "")
        if self._on_turn is None:
            return
        try:
            self._on_turn(turn)
        except Exception:
            _LOG.exception("copilot_turn_callback_failed")


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())
