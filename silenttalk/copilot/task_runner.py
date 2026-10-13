from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from collections import deque

from silenttalk.conversation import AGENT_NAME as _AGENT_NAME
from silenttalk.conversation import (
    AGENT_RESULT_CONTEXT_CHARS as _AGENT_RESULT_CONTEXT_CHARS,
)
from silenttalk.conversation import AGENT_SPEAKER_ID as _AGENT_SPEAKER_ID
from silenttalk.conversation import SPOKEN_RESULT_CHARS as _SPOKEN_RESULT_CHARS
from silenttalk.conversation import (
    VOICE_ROOM,
    AgentTask,
    ConversationTurn,
)
from silenttalk.copilot.reply_templates import PRIVATE_REPORTS
from silenttalk.copilot.reply_transport import InferenceDeferred

_LOG = logging.getLogger(__name__)


from silenttalk.conversation import Attachment
from silenttalk.conversation import Trigger as _Trigger

_AGENT_RESULT_MAX_CHARS = 6000
# One Agent does one job at a time; work asked meanwhile waits its turn and
# starts, oldest first, when the running job ends (laptop round 11: a voice
# lookup asked during the owner's work was turned away with "wait until it is
# done" and never ran). A few at most: anyone in a chat may ask.
_MAX_WAITING = 3
_QUEUED = "前一件工作還在做，這件已經排在後面，做完就接著做。"
_QUEUE_FULL = "前面已經排了好幾件工作，這件沒有收下，請等前面的做完再交代。"
_STOPPED = "工作被中斷了，沒有結果。"
# What a chat anyone is in hears of a failed lookup: the reason's code only.
_FAILED = "工作失敗了（{code}）。"


_FAILURE_CODE = re.compile(r"[a-z][a-z0-9_]{0,39}")


def failure_code(value: object) -> str:
    """The reason code if it is one (a short snake_case name), else unknown."""
    return value if isinstance(value, str) and _FAILURE_CODE.fullmatch(value) else "unknown"


class AgentTaskRunner:
    def __init__(
        self,
        client,
        model,
        *,
        on_approval,
        on_private,
        on_result,
        on_mark,
        context,
        emit_turn,
        task_line,
        wake,
    ):
        self._agent_tasks, self._llm = client, model
        self._on_agent_approval, self._on_agent_private = on_approval, on_private
        self._on_agent_result, self._on_task_mark = on_result, on_mark
        self._context, self._emit_turn, self._task_line = context, emit_turn, task_line
        self._wake = wake
        self.enabled = False
        self.engagement = "called"
        self._agent_job = None
        self._agent_origin = None
        self._agent_scope = "read"
        self._task_hints = deque()
        self._owner_tasks = deque()
        self._waiting = deque()
        self._task_result = ""
        self.epoch = 0

    def invalidate(self) -> None:
        self.epoch += 1
        self._task_hints.clear()
        self._owner_tasks.clear()
        self._waiting.clear()
        self._task_result = ""
        if self._agent_job is not None:
            self._agent_job.cancel()
        origin, self._agent_origin = self._agent_origin, None
        if origin is not None:
            self._mark(origin, "failed")

    async def stop_agent_task(self) -> None:
        self.invalidate()
        job, self._agent_job = self._agent_job, None
        if job is not None:
            await asyncio.gather(job, return_exceptions=True)

    def _mark(self, origin: _Trigger, state: str) -> None:
        """The owner's message that handed over the work: accepted, done or failed."""
        if self._on_task_mark is not None and origin.message_id:
            self._on_task_mark(origin.channel_id, origin.message_id, state)

    async def dispatch_owner(
        self, trigger: _Trigger, turns: tuple[ConversationTurn, ...]
    ) -> None:
        """A line the owner typed in his Agent thread: the Agent's work, word
        for word, read-only unless it asks for changes."""
        epoch = self.epoch
        started = time.monotonic()
        try:
            task = await self._llm.task_from_owner(
                turns=turns,
                engagement=self.engagement,
            )
        except InferenceDeferred:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - task failures must reach the owner
            _LOG.warning("agent_task_dispatch_failed error_type=%s", type(exc).__name__)
            self._mark(trigger, "failed")
            await self._deliver_owner_result("error", str(exc), trigger.place)
            return
        _LOG.info(
            "agent_task_decision latency_ms=%d dispatched=%s scope=%s",
            round((time.monotonic() - started) * 1000),
            task is not None,
            task.scope if task is not None else "-",
        )
        if task is not None:
            await self.dispatch(trigger, task, epoch)

    async def dispatch(self, trigger: _Trigger, task: AgentTask, epoch: int) -> None:
        """Hand one task to the Agent: the owner's work in his thread, or a
        lookup asked in a chat. While another runs it waits its turn (the
        place it came from hears so). `epoch`: when it was asked; a task the
        owner stopped meanwhile (Agent or character turned off and on) never
        starts."""
        if epoch != self.epoch or not self.enabled:
            return
        if self.busy or self._waiting:
            full = len(self._waiting) >= _MAX_WAITING
            if not full:
                self._waiting.append((trigger, task, epoch))
            # Said by the worker like any news of the Agent's, so a model
            # that has to wait cannot ask the line again and queue it twice.
            self._task_hints.append(
                ("report", _QUEUE_FULL if full else _QUEUED, trigger.place)
            )
            self._wake()
            return
        await self._start(trigger, task, epoch, ack=True)

    async def start_waiting(self) -> None:
        """The oldest task that waited for the Agent; it already heard that it
        would wait, so nothing is said when it starts."""
        trigger, task, epoch = self._waiting.popleft()
        await self._start(trigger, task, epoch, ack=False)

    async def _start(
        self, trigger: _Trigger, task: AgentTask, epoch: int, *, ack: bool
    ) -> None:
        assert self._agent_tasks is not None
        try:
            if epoch != self.epoch or not self.enabled:
                return
            workspace = await self._agent_tasks.workspace()
            if epoch != self.epoch or not self.enabled:
                return
            self._agent_origin, self._agent_scope = trigger, task.scope
            self._mark(trigger, "accepted")
            if ack and trigger.place == VOICE_ROOM:
                await self._task_line("ack", task.text, VOICE_ROOM)
            if epoch != self.epoch or not self.enabled:
                return
            self._task_result = ""
            self._agent_job = asyncio.create_task(
                self._run_agent_task(
                    task, workspace, epoch, trigger.place, trigger.attachments
                ),
                name="discord-agent-task",
            )
            # The next waiting task starts once this one has fully ended.
            self._agent_job.add_done_callback(lambda _job: self._wake())
        except InferenceDeferred:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - task failures must reach the character
            _LOG.warning("agent_task_dispatch_failed error_type=%s", type(exc).__name__)
            if epoch == self.epoch:
                if self._agent_origin is trigger:
                    self._agent_origin = None
                self._mark(trigger, "failed")
                await self._finish("error", str(exc), trigger, task.scope)

    async def _run_agent_task(
        self,
        task: AgentTask,
        workspace: str,
        epoch: int,
        place: int,
        attachments: tuple[Attachment, ...] = (),
    ) -> None:
        assert self._agent_tasks is not None
        started = time.monotonic()

        async def on_event(kind: str, payload: dict[str, object]) -> None:
            if epoch == self.epoch:
                await self._agent_event(kind, payload)

        # The files posted with the line, read into RAM only now that they
        # are needed; one that cannot be read is left out (the Agent says
        # what it did not get).
        files = []
        for name, read in attachments:
            try:
                files.append(
                    {"name": name, "data": base64.b64encode(await read()).decode()}
                )
            except Exception as exc:  # noqa: BLE001 - a lost attachment is not a lost task
                _LOG.warning(
                    "agent_attachment_failed error_type=%s", type(exc).__name__
                )
        try:
            await self._agent_tasks.run(
                task.text,
                workspace,
                on_event,
                scope=task.scope,
                conversation=place,
                attachments=files,
            )
        finally:
            _LOG.info(
                "agent_task_finished elapsed_ms=%d",
                round((time.monotonic() - started) * 1000),
            )

    async def _agent_event(self, kind: str, payload: dict[str, object]) -> None:
        place = (
            self._agent_origin.place if self._agent_origin is not None else VOICE_ROOM
        )
        if kind == "delta":
            self._task_result = (self._task_result + str(payload.get("text", "")))[
                -_AGENT_RESULT_MAX_CHARS:
            ]
            return
        if kind == "approval":
            # Only the owner's work asks (a lookup never does): the buttons
            # and the exact operation go to his DMs, the thread hears nothing.
            assert self._agent_tasks is not None
            if self._on_agent_approval is None:
                await self._agent_tasks.approve(str(payload["call_id"]), False)
                return
            try:
                await self._on_agent_approval(payload)
            except Exception as exc:  # noqa: BLE001 - failed approval delivery must deny the operation
                await self._agent_tasks.approve(str(payload["call_id"]), False)
                self._task_hints.append(
                    ("report", PRIVATE_REPORTS["approval_undelivered"], place)
                )
                _LOG.warning("agent_approval_failed error_type=%s", type(exc).__name__)
        elif kind in {"done", "error", "cancelled"}:
            # Why a task failed, as a code only (never the message, which can
            # quote the request): EdgeAgent's or the client's (agent_tasks.py).
            _LOG.info(
                "agent_task_ended kind=%s reason=%s",
                kind,
                failure_code(payload.get("reason")) if kind == "error" else "-",
            )
            if kind == "done":
                # EdgeAgent's own checks on the answer, as counts only: code
                # changed with no passing check, cited numbers its sources do
                # not back, and how often Simplified text had to be converted.
                _LOG.info(
                    "agent_task_checks unverified=%d source_problems=%d converted=%d",
                    len(payload.get("unverified") or []),
                    len(payload.get("source_problems") or []),
                    int(payload.get("converted") or 0),
                )
            if kind == "done":
                result = self._task_result or "工作完成。"
            elif kind == "error" and self._agent_scope == "public":
                # EdgeAgent's own words can name this computer's paths; a
                # chat anyone is in gets the reason's code only.
                result = _FAILED.format(code=failure_code(payload.get("reason")))
            elif kind == "error":
                result = str(payload.get("message") or "工作失敗了。")
            else:
                # Stopped on EdgeAgent's side (its stop button, Pi aborting):
                # whoever asked still hears it ended, or they wait forever.
                result = _STOPPED
            self._task_result = ""
            origin, self._agent_origin = self._agent_origin, None
            if origin is not None:
                self._mark(origin, "done" if kind == "done" else "failed")
                await self._finish(kind, result, origin, self._agent_scope)
        self._wake()

    async def _finish(
        self, kind: str, result: str, origin: _Trigger, scope: str
    ) -> None:
        """Deliver a finished task's result where it was asked for."""
        epoch = self.epoch
        if scope == "public":
            # A lookup: the result (public by nature) is typed into the chat
            # it was asked in, and in the voice room the character also says
            # what it found.
            await self._post_result(kind, result, origin.place)
            if origin.place == VOICE_ROOM and epoch == self.epoch:
                self._task_hints.append(
                    ("report", result[:_SPOKEN_RESULT_CHARS], VOICE_ROOM)
                )
            return
        detail = await self._deliver_owner_result(kind, result, origin.place)
        if detail and epoch == self.epoch:
            self._task_hints.append(("report", detail, origin.place))

    async def _post_result(self, kind: str, result: str, place: int) -> bool:
        """Type a result into a place and keep it in that conversation (as
        said by 思考機, so reading the place back tells it apart)."""
        posted = False
        if self._on_agent_result is not None:
            try:
                posted = await self._on_agent_result(result, place)
            except Exception as exc:  # noqa: BLE001 - reported to the caller
                _LOG.warning(
                    "agent_result_post_failed error_type=%s", type(exc).__name__
                )
        _LOG.info(
            "agent_result_posted kind=%s posted=%s place=%s",
            kind,
            posted,
            "voice" if place == VOICE_ROOM else "text",
        )
        if posted:
            turn = ConversationTurn.now(
                _AGENT_SPEAKER_ID,
                _AGENT_NAME,
                result[:_AGENT_RESULT_CONTEXT_CHARS],
                via="text",
                place=place,
            )
            self._context(place).append(turn)
            self._emit_turn(turn)
        return posted

    async def _deliver_owner_result(self, kind: str, result: str, place: int) -> str:
        """The owner's work: the result goes into his thread (his DMs if the
        thread cannot take it). Returns what the thread must hear, or ""."""
        if await self._post_result(kind, result, place):
            return ""
        delivered = False
        if self._on_agent_private is not None:
            try:
                delivered = await self._on_agent_private(result)
            except Exception as exc:  # noqa: BLE001 - an undelivered result is reported as such
                _LOG.warning("agent_private_failed error_type=%s", type(exc).__name__)
        _LOG.info("agent_result_private kind=%s delivered=%s", kind, delivered)
        return "" if delivered else PRIVATE_REPORTS["undelivered"]

    @property
    def available(self):
        return self._agent_tasks is not None

    @property
    def busy(self):
        return self._agent_job is not None and not self._agent_job.done()

    @property
    def has_waiting(self):
        return bool(self._waiting)

    @property
    def has_hint(self):
        return bool(self._task_hints)

    def take_hint(self):
        return self._task_hints.popleft()

    @property
    def has_owner_task(self):
        return bool(self._owner_tasks)

    def take_owner_task(self):
        return self._owner_tasks.popleft()

    def queue_owner(self, trigger, turns):
        self._owner_tasks.append((trigger, turns))

    def defer_hint(self, hint):
        self._task_hints.appendleft(hint)

    def defer_owner(self, trigger, turns):
        self._owner_tasks.appendleft((trigger, turns))
