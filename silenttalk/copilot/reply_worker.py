"""Drain bounded character work only when the model owner permits inference."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from silenttalk.conversation import Trigger
from silenttalk.copilot.character_life import CharacterLife
from silenttalk.copilot.replies import CharacterReplies
from silenttalk.copilot.reply_transport import InferenceDeferred
from silenttalk.copilot.sessions import ConversationSessions
from silenttalk.copilot.task_runner import AgentTaskRunner


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
    turn: Callable[[InferenceDeferred], Awaitable[None]],
) -> None:
    """`turn`: until the model owner would take a request it deferred. Its
    status stream says when (LocalReplyModel.turn); nothing is sent again
    before that. Work that comes in meanwhile waits where it is kept: a
    newer line replaces its place's in `pending` (latest wins)."""
    while True:
        # Asleep until something happens (a line, a result, a setting: they
        # set `wake`) or until the next thing falls due: no asking every
        # second (owner, 2026-10-14: 「輪巡都拆掉」).
        due = [at for at in (replies.lull_at(), life.update_at(bool(pending))) if at is not None]
        try:
            await asyncio.wait_for(
                wake.wait(), timeout=max(0.0, min(due) - time.monotonic()) if due else None
            )
        except TimeoutError:
            try:
                if replies.lull_due():
                    await replies.open_topic()
                elif life.update_due(bool(pending)):
                    await life.update()
            except InferenceDeferred as deferred:
                await turn(deferred)  # it stays due
            continue
        wake.clear()
        if tasks.has_hint and character_mode():
            hint = tasks.take_hint()
            try:
                await replies.task_line(*hint)
            except InferenceDeferred as deferred:
                tasks.defer_hint(hint)
                await turn(deferred)
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
            except InferenceDeferred as deferred:
                tasks.defer_owner(trigger, turns)
                await turn(deferred)
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
        except InferenceDeferred as deferred:
            # A newer trigger wins; never accumulate a backlog of old chatter.
            pending.setdefault(place, trigger)
            await turn(deferred)
            wake.set()
