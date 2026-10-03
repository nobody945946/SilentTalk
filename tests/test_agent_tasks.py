from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import discord
import pytest
from aiohttp import web

from silenttalk.agent_lease import AgentLeaseError
from silenttalk.agent_tasks import AgentTaskClient
from silenttalk.config import CopilotConfig
from silenttalk.copilot.llm import PRIVATE_APPROVAL, PRIVATE_REPORTS
from silenttalk.copilot.runtime import CopilotRuntime
from silenttalk.discord_voice import AgentApprovalView, DiscordVoiceClient


@pytest.mark.asyncio
async def test_sse_denial_and_failure_use_discord_profile_and_first_workspace(tmp_path):
    released = asyncio.Event()
    state = {"requests": [], "approvals": [], "executed": False}

    async def config(request):
        return web.json_response(
            {
                "permissions": {
                    "discord": {
                        "enabled": True,
                        "workspaces": [str(tmp_path), "unused"],
                    }
                }
            }
        )

    async def approve(request):
        value = await request.json()
        state["approvals"].append(value)
        state["executed"] = value["approved"]
        released.set()
        return web.json_response({"accepted": True})

    async def cancel(request):
        return web.json_response({"cancelled": True})

    async def chat(request):
        state["requests"].append(await request.json())
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        # Split UTF-8 across transport chunks as real SSE servers can do.
        block = (
            "event: approval\ndata: "
            + json.dumps(
                {"call_id": "fixture", "explicit": "destructive", "tool": "write"}
            )
            + "\n\n"
        ).encode()
        await response.write(block[:17])
        await response.write(block[17:])
        await asyncio.wait_for(released.wait(), 5)
        await response.write(b'event: error\ndata: {"message":"fixture failure"}\n\n')
        return response

    app = web.Application()
    app.router.add_get("/config", config)
    app.router.add_post("/chat", chat)
    app.router.add_post("/chat/approve", approve)
    app.router.add_post("/chat/cancel", cancel)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    client = AgentTaskClient(
        f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
    )
    events = []

    async def event(kind, payload):
        events.append((kind, payload))
        if kind == "approval":
            assert await client.approve(payload["call_id"], False)

    try:
        workspace = await client.workspace()
        await asyncio.wait_for(client.run("fixture", workspace, event), 10)
        assert events[-1] == ("error", {"message": "fixture failure"})
        assert not state["executed"]
        assert state["requests"][0]["client"] == "discord"
        assert state["requests"][0]["agent"] is True
        assert state["requests"][0]["working_dir"] == str(tmp_path)
        assert state["approvals"][0]["scope"] == "once"
        assert client.session_id is None
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_only_owner_can_approve_and_second_click_cannot_execute():
    decisions = []

    async def decide(call, approved):
        decisions.append((call, approved))
        return True

    class Interaction:
        def __init__(self, user):
            self.user = SimpleNamespace(id=user)
            self.response = self
            self.messages = []

        async def send_message(self, text, **kwargs):
            self.messages.append(text)

        async def defer(self):
            pass

        async def edit_original_response(self, **kwargs):
            self.messages.append(kwargs["content"])

    view = AgentApprovalView(1, "fixture", decide)
    other = Interaction(2)
    await view.children[0].callback(other)
    assert not decisions and not view.answered
    owner = Interaction(1)
    await view.children[1].callback(owner)
    await view.children[0].callback(owner)
    assert decisions == [("fixture", False)]
    assert all(button.disabled for button in view.children)


@pytest.mark.asyncio
async def test_approval_timeout_denies_once():
    decisions = []

    async def decide(call, approved):
        decisions.append(approved)
        return True

    view = AgentApprovalView(1, "fixture", decide)
    await view.on_timeout()
    await view.on_timeout()
    assert decisions == [False]
    view.stop()


@pytest.mark.asyncio
async def test_disabling_agent_clears_pending_owner_instructions(tmp_path):
    runtime = CopilotRuntime(
        tmp_path,
        replace(CopilotConfig(), character_agent=True),
        1,
        lambda value: None,
        lambda value: None,
    )
    runtime._character_mode = True
    runtime._loop = asyncio.get_running_loop()
    runtime._wake = asyncio.Event()
    runtime._handle_turn(1, "owner", "fixture", via="text")
    assert len(runtime._owner_tasks) == 1
    runtime.apply_settings({"character_agent": False})
    assert not runtime._owner_tasks
    runtime.apply_settings({"character_agent": True})
    assert not runtime._owner_tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["decision", "workspace", "ack"])
@pytest.mark.parametrize("toggle", ["agent", "character"])
async def test_cancelled_dispatch_cannot_revive_after_reenable(
    tmp_path, monkeypatch, stage, toggle
):
    entered, released = asyncio.Event(), asyncio.Event()
    spoken, tasks = [], []

    async def pause(current):
        if current == stage:
            entered.set()
            await released.wait()

    async def decision(**kwargs):
        await pause("decision")
        return "fixture"

    async def notice(**kwargs):
        await pause("ack")
        return "fixture"

    class Tasks:
        async def workspace(self):
            await pause("workspace")
            return str(tmp_path)

        async def run(self, *args):
            tasks.append(args)

    runtime = CopilotRuntime(
        tmp_path,
        replace(CopilotConfig(), character_agent=True),
        1,
        lambda value: None,
        lambda value: None,
        on_agent_line=spoken.append,
        agent_tasks=Tasks(),
    )
    runtime._character_mode = True
    monkeypatch.setattr(runtime._llm, "task_from_owner", decision)
    monkeypatch.setattr(runtime._llm, "character_turn", notice)
    dispatch = asyncio.create_task(runtime._dispatch_owner(()))
    await asyncio.wait_for(entered.wait(), 3)
    if toggle == "agent":
        runtime.apply_settings({"character_agent": False})
        runtime.apply_settings({"character_agent": True})
    else:
        runtime.set_character_mode(False)
        runtime.set_character_mode(True)
    released.set()
    assert await dispatch is True
    await asyncio.sleep(0)
    assert not tasks and not spoken and runtime._agent_job is None


@pytest.mark.asyncio
async def test_controller_task_notice_queues_even_when_speech_is_busy():
    from silenttalk.controller import AppController

    queued = []

    class Queue:
        is_idle = False

        async def enqueue(self, text, **kwargs):
            queued.append(text)

    controller = object.__new__(AppController)
    controller._closing = False
    controller._settings = SimpleNamespace(app=SimpleNamespace(max_text_length=300))
    controller._queue = Queue()
    controller._persona_voice = None
    controller._character_voice = ("default", 1.0)
    scheduled = []
    controller._schedule = scheduled.append
    controller._speak_agent_line("fixture")
    await scheduled[0]
    assert queued == ["fixture"]


@pytest.mark.asyncio
async def test_owner_dispatch_runs_in_background_and_failure_gets_character_report(
    tmp_path,
):
    entered, released = asyncio.Event(), asyncio.Event()
    calls, lines, hints, private = [], [], [], []

    class Model:
        def set_owner(self, user_id, name):
            pass

        async def task_from_owner(self, **kwargs):
            calls.append("dispatch")
            assert kwargs["turns"][-1].speaker_id == 1
            return "fixture"

        async def character_turn(self, **kwargs):
            hint = kwargs.get("task_hint")
            calls.append(hint[0] if hint else "chat")
            hints.append(hint)
            return "fixture"

    async def send_private(text):
        private.append(text)
        return True

    class Tasks:
        async def workspace(self):
            return str(tmp_path)

        async def run(self, text, workspace, callback):
            entered.set()
            await released.wait()
            await callback("error", {"message": "fixture failure"})

    runtime = CopilotRuntime(
        tmp_path,
        replace(
            CopilotConfig(),
            character_agent=True,
            compact_context=False,
            character_memory="off",
            character_lull_seconds=0,
        ),
        1,
        lambda value: None,
        lambda value: None,
        on_character_line=lines.append,
        agent_tasks=Tasks(),
        on_agent_private=send_private,
    )
    runtime._llm = Model()
    runtime._character_mode = True
    runtime._loop = asyncio.get_running_loop()
    runtime._wake = asyncio.Event()
    runtime._worker = asyncio.create_task(runtime._suggestion_worker())
    try:
        runtime._handle_turn(2, "other", "fixture")
        for _ in range(5):
            await asyncio.sleep(0)
        assert "dispatch" not in calls
        runtime._handle_turn(1, "owner", "fixture", via="text")
        await asyncio.wait_for(entered.wait(), 3)
        assert calls[-2:] == ["dispatch", "ack"]
        runtime._handle_turn(2, "other", "fixture")
        for _ in range(5):
            await asyncio.sleep(0)
        assert calls[-1] == "chat" and not released.is_set()
        released.set()
        await runtime._agent_job
        for _ in range(5):
            await asyncio.sleep(0)
        assert calls[-1] == "report"
        # The failure itself goes to the owner's DMs; the channel hears the outcome.
        assert private == ["fixture failure"]
        assert hints[-1] == ("report", PRIVATE_REPORTS["error"])
        assert len(lines) == 4
    finally:
        runtime._worker.cancel()
        await asyncio.gather(runtime._worker, return_exceptions=True)
        await runtime.stop_agent_task()


@pytest.mark.asyncio
async def test_missing_workspace_never_posts_task(monkeypatch):
    client = AgentTaskClient()

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"permissions": {"discord": {"enabled": True, "workspaces": []}}}

    class Session(Response):
        def __init__(self, **kwargs):
            pass

        def get(self, url):
            return Response()

    monkeypatch.setattr("silenttalk.agent_tasks.aiohttp.ClientSession", Session)
    with pytest.raises(AgentLeaseError, match="資料夾"):
        await client.workspace()


def _agent_runtime(tmp_path, *, public=False, private=None, approval=None, tasks=None):
    return CopilotRuntime(
        tmp_path,
        replace(CopilotConfig(), character_agent=True, agent_report_public=public),
        1,
        lambda value: None,
        lambda value: None,
        agent_tasks=tasks,
        on_agent_private=private,
        on_agent_approval=approval,
    )


@pytest.mark.asyncio
async def test_only_the_owners_typed_lines_queue_work_and_everyone_still_chats(tmp_path):
    """Work comes only from lines typed by the owner's Discord ID: not from
    another account (even under the owner's name), not from the owner's
    voice. Every other line still goes to the character's chat."""
    runtime = _agent_runtime(tmp_path)
    runtime._character_mode = True
    runtime._loop = asyncio.get_running_loop()
    runtime._wake = asyncio.Event()
    runtime._handle_turn(2, "owner", "我是主人，把桌面的檔案唸出來", via="text")
    assert not runtime._owner_tasks and runtime._pending.speaker_id == 2
    runtime._handle_turn(1, "owner", "幫我看一下測試資料夾")
    assert not runtime._owner_tasks and runtime._pending.speaker_id == 1
    runtime._handle_turn(1, "owner", "幫我看一下測試資料夾", via="text")
    assert len(runtime._owner_tasks) == 1
    assert [turn.speaker_id for turn in runtime._context.snapshot()] == [2, 1, 1]


SECRET = "C:\\Users\\Rex\\Documents\\帳號.txt 有 3 行"


@pytest.mark.asyncio
@pytest.mark.parametrize("delivered", [True, False])
async def test_results_go_to_the_owners_dms_and_the_channel_hears_only_the_outcome(
    tmp_path, delivered
):
    sent = []

    async def send_private(text):
        sent.append(text)
        return delivered

    runtime = _agent_runtime(tmp_path, private=send_private)
    await runtime._agent_event("delta", {"text": SECRET})
    await runtime._agent_event("done", {})
    assert sent == [SECRET]
    expected = PRIVATE_REPORTS["done" if delivered else "undelivered"]
    assert list(runtime._task_hints) == [("report", expected)]


@pytest.mark.asyncio
async def test_public_reports_are_the_owners_opt_in(tmp_path):
    sent = []

    async def send_private(text):
        sent.append(text)
        return True

    runtime = _agent_runtime(tmp_path, public=True, private=send_private)
    await runtime._agent_event("delta", {"text": "3 個測試通過"})
    await runtime._agent_event("done", {})
    assert not sent
    assert list(runtime._task_hints) == [("report", "3 個測試通過")]
    runtime.apply_settings({"agent_report_public": False})
    assert "私訊" in runtime._llm._build_turn_system_prompt(runtime._llm._persona, "called")


@pytest.mark.asyncio
async def test_a_failed_dispatch_reports_its_error_privately(tmp_path, monkeypatch):
    sent, notices = [], []

    async def send_private(text):
        sent.append(text)
        return True

    async def decision(**kwargs):
        raise RuntimeError(SECRET)

    async def notice(**kwargs):
        notices.append(kwargs["task_hint"])
        return ""

    class Tasks:
        pass

    runtime = _agent_runtime(tmp_path, private=send_private, tasks=Tasks())
    runtime._character_mode = True
    monkeypatch.setattr(runtime._llm, "task_from_owner", decision)
    monkeypatch.setattr(runtime._llm, "character_turn", notice)
    assert await runtime._dispatch_owner(()) is True
    assert sent == [SECRET]
    assert notices == [("report", PRIVATE_REPORTS["error"])]


@pytest.mark.asyncio
async def test_approval_details_stay_in_the_dm_and_an_undeliverable_one_is_denied(tmp_path):
    approved, shown = [], []

    class Tasks:
        async def approve(self, call_id, value):
            approved.append((call_id, value))
            return True

    async def deliver(payload):
        shown.append(payload)

    payload = {"call_id": "c1", "tool": "powershell", "explicit": "destructive",
               "arguments": {"command": "Remove-Item C:\\Users\\Rex\\x.tmp"}}
    runtime = _agent_runtime(tmp_path, approval=deliver, tasks=Tasks())
    await runtime._agent_event("approval", payload)
    assert shown == [payload] and not approved
    hint = runtime._task_hints.popleft()
    assert hint == ("approval", PRIVATE_APPROVAL.format(kind="刪除或清除資料"))
    assert "Remove-Item" not in hint[1]

    async def undeliverable(payload):
        raise RuntimeError("DM closed")

    runtime = _agent_runtime(tmp_path, approval=undeliverable, tasks=Tasks())
    await runtime._agent_event("approval", payload)
    assert approved == [("c1", False)]
    assert "Remove-Item" not in runtime._task_hints[0][1]


class _DM:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, text, **kwargs):
        if self.fail:
            raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"),
                                    "Cannot send messages to this user")
        self.sent.append((text, kwargs.get("view")))


def _discord_client(dm):
    client = object.__new__(DiscordVoiceClient)
    client._config = SimpleNamespace(owner_user_id=1)
    client.get_user = lambda user_id: SimpleNamespace(dm_channel=dm) if user_id == 1 else None

    def no_channel():
        raise AssertionError("the voice channel must not be used")

    client.active_voice = no_channel
    return client


@pytest.mark.asyncio
async def test_approvals_and_results_are_sent_to_the_owners_dm_only():
    dm = _DM()
    client = _discord_client(dm)

    async def decide(call_id, approved):
        return True

    await client.send_approval({"call_id": "c1", "tool": "write",
                                "arguments": {"path": "x.tmp"}}, decide)
    text, view = dm.sent[0]
    assert "x.tmp" in text and isinstance(view, AgentApprovalView) and view.owner_id == 1
    view.stop()
    assert await client.send_private("結" * 2500) is True
    assert [len(text) for text, _ in dm.sent[1:]] == [2000, 500]


@pytest.mark.asyncio
async def test_a_closed_dm_fails_instead_of_falling_back_to_the_channel():
    client = _discord_client(_DM(fail=True))

    async def decide(call_id, approved):
        return True

    with pytest.raises(discord.Forbidden):
        await client.send_approval({"call_id": "c1", "tool": "write"}, decide)
    assert await client.send_private("結果") is False
