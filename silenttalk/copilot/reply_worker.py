"""Drain bounded character work only when the model owner permits inference."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from silenttalk.conversation import Trigger
from silenttalk.copilot.character_life import CharacterLife
from silenttalk.copilot.replies import CharacterReplies
from silenttalk.copilot.reply_transport import InferenceDeferred
from silenttalk.copilot.sessions import ConversationSessions
from silenttalk.copilot.task_runner import AgentTaskRunner

_POLL_SECONDS = 1.0
_RETRY_SECONDS = 1.0


async def run_reply_worker(
    wake: asyncio.Event,
    pending: dict[int, Trigger],
    *,
    replies: CharacterReplies,
    tasks: AgentTaskRunner,
    sessions: ConversationSessions,
    life: CharacterLife,
    respond: Callable[[Trigger], Awaitable[None]],
    character_mode: Callable[[], bool],
    agent_enabled: Callable[[], bool],
) -> None:
    while True:
        try:
            await asyncio.wait_for(wake.wait(), timeout=_POLL_SECONDS)
        except TimeoutError:
            try:
                if replies.lull_due():
                    await replies.open_topic()
                elif life.update_due(bool(pending)):
                    await life.update()
            except InferenceDeferred:
                replies.lull_spoken = False
            continue
        wake.clear()
        if tasks.has_hint and character_mode():
            hint = tasks.take_hint()
            try:
                await replies.task_line(*hint)
            except InferenceDeferred:
                tasks.defer_hint(hint)
                await asyncio.sleep(_RETRY_SECONDS)
            wake.set()
            continue
        if tasks.has_waiting and not tasks.busy and character_mode():
            # The Agent is free: the oldest work that waited for it.
            await tasks.start_waiting()
            wake.set()
            continue
        if tasks.has_owner_task and character_mode() and agent_enabled():
            trigger, turns = tasks.take_owner_task()
            try:
                await tasks.dispatch_owner(trigger, turns)
            except InferenceDeferred:
                tasks.defer_owner(trigger, turns)
                await asyncio.sleep(_RETRY_SECONDS)
            wake.set()
            continue
        if not pending:
            continue
        place = next(iter(pending))
        trigger = pending.pop(place)
        sessions.maybe_compact(place)
        if pending:
            wake.set()
        try:
            if character_mode():
                await respond(trigger)
            else:
                await replies.generate(trigger)
        except InferenceDeferred:
            # A newer trigger wins; never accumulate a backlog of old chatter.
            pending.setdefault(place, trigger)
            await asyncio.sleep(_RETRY_SECONDS)
            wake.set()
