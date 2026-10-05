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
from silenttalk.copilot.runtime import CopilotRuntime, _Trigger
from silenttalk.copilot.types import VOICE_ROOM, AgentTask
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
        await asyncio.wait_for(client.run("fixture", workspace, event, conversation=42), 10)
        assert events[-1] == ("error", {"message": "fixture failure"})
        assert not state["executed"]
        assert state["requests"][0]["client"] == "discord"
        # A place's tasks share one EdgeAgent session.
        assert state["requests"][0]["session_id"] == "discord-42"
        assert state["requests"][0]["agent"] is True
        assert state["requests"][0]["working_dir"] == str(tmp_path)
        # Unless told otherwise a task is read-only: EdgeAgent refuses changes.
        assert state["requests"][0]["read_only"] is True
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
        return AgentTask("fixture")

    async def notice(**kwargs):
        await pause("ack")
        return "fixture"

    class Tasks:
        async def workspace(self):
            await pause("workspace")
            return str(tmp_path)

        async def run(self, *args, **kwargs):
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
    dispatch = asyncio.create_task(runtime._dispatch_owner(_Trigger("owner", "fixture"), ()))
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
            return AgentTask("fixture")

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

        async def run(self, text, workspace, callback, *, read_only, conversation):
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
    assert not runtime._owner_tasks and runtime._pending[VOICE_ROOM].speaker_id == 2
    runtime._handle_turn(1, "owner", "幫我看一下測試資料夾")
    assert not runtime._owner_tasks and runtime._pending[VOICE_ROOM].speaker_id == 1
    runtime._handle_turn(1, "owner", "幫我看一下測試資料夾", via="text")
    assert len(runtime._owner_tasks) == 1
    assert [turn.speaker_id for turn in runtime._context(VOICE_ROOM).snapshot()] == [2, 1, 1]


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
    assert list(runtime._task_hints) == [("report", expected, VOICE_ROOM)]


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
    assert list(runtime._task_hints) == [("report", "3 個測試通過", VOICE_ROOM)]
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
    assert await runtime._dispatch_owner(_Trigger("owner", "fixture"), ()) is True
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
    assert hint == ("approval", PRIVATE_APPROVAL.format(kind="刪除或清除資料"), VOICE_ROOM)
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
async def test_a_command_approval_comes_with_its_explanation_first():
    dm = _DM()
    client = _discord_client(dm)

    async def decide(call_id, approved):
        return True

    await client.send_approval({"call_id": "c1", "tool": "powershell", "arguments": {"command": "Remove-Item x"},
                                "explain": "影響：會刪除：x" + "。" * 2100}, decide)
    texts = [text for text, _ in dm.sent]
    assert texts[0].startswith("這個指令在做什麼") and "會刪除：x" in texts[0]
    assert all(len(text) <= 2000 for text in texts) and len(texts) == 3
    assert dm.sent[-1][1] is not None and "Remove-Item x" in texts[-1]
    dm.sent[-1][1].stop()


@pytest.mark.asyncio
async def test_a_closed_dm_fails_instead_of_falling_back_to_the_channel():
    client = _discord_client(_DM(fail=True))

    async def decide(call_id, approved):
        return True

    with pytest.raises(discord.Forbidden):
        await client.send_approval({"call_id": "c1", "tool": "write"}, decide)
    assert await client.send_private("結果") is False


class _Thread:
    """A thread the bot opened: newest message first, like Discord's history."""

    def __init__(self, messages, starter=None):
        self.id, self.sent, self._messages, self._starter = 77, [], messages, starter
        self.parent = SimpleNamespace(fetch_message=self._fetch)

    async def send(self, text, **kwargs):
        self.sent.append(text)

    async def _fetch(self, message_id):
        assert message_id == self.id
        if self._starter is None:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "gone")
        return self._starter

    def history(self, limit, before=None):
        async def lines():
            for message in self._messages[:limit]:
                yield message
        return lines()


def _post(author, text, *, bot=False, kind=discord.MessageType.default):
    return SimpleNamespace(clean_content=text, type=kind,
                           author=SimpleNamespace(id=author, display_name=f"u{author}", bot=bot))


def _thread_client(thread):
    client = object.__new__(DiscordVoiceClient)
    client._connection = SimpleNamespace(user=SimpleNamespace(id=99))
    client._is_our_thread = lambda channel: channel is thread

    async def channel(place):
        return thread if place == thread.id else None

    client._channel = channel
    return client


@pytest.mark.asyncio
async def test_a_result_is_posted_in_the_thread_in_headed_parts():
    thread = _Thread([])
    assert await _thread_client(thread).send_result("結" * 4000, 77) is True
    assert len(thread.sent) == 3 and all(len(text) <= 2000 for text in thread.sent)
    assert [text.split("\n")[0] for text in thread.sent] == [
        "【思考機回報】（1/3）", "【思考機回報】（2/3）", "【思考機回報】（3/3）"]
    assert "".join(text.split("\n", 1)[1] for text in thread.sent) == "結" * 4000


@pytest.mark.asyncio
async def test_a_thread_reads_back_oldest_first_from_the_owners_opening_message():
    thread = _Thread([
        _post(99, "【思考機回報】（2/2）\n第二段"), _post(99, "【思考機回報】（1/2）\n第一段"),
        _post(99, "遵命"), _post(55, "別的 bot", bot=True),
        _post(1, "", kind=discord.MessageType.thread_created), _post(1, "幫我數 tmp 檔"),
    ], starter=_post(1, "@Machina 開工"))
    client = _thread_client(thread)
    assert await client.thread_history(77, 500, 50) == [
        (1, "u1", "@Machina 開工", "text"), (1, "u1", "幫我數 tmp 檔", "text"),
        (99, "u99", "遵命", "mine"), (99, "u99", "第一段", "agent"), (99, "u99", "第二段", "agent")]
    # Read only as far back as asked: the opening message is left out then.
    assert [line[2] for line in await client.thread_history(77, 500, 2)] == ["第一段", "第二段"]
    # The opening message itself has nothing before it.
    assert await client.thread_history(77, 77, 50) == []
    assert await _thread_client(_Thread([])).thread_history(5, 500, 50) == []


def _marked_runtime(tmp_path, *, delivered=True, read_only=True, posted=True, history=None):
    """A character runtime whose Agent lists a folder; records the marks on
    the owner's message, what is typed where, what is spoken and the DMs."""
    seen = SimpleNamespace(marks=[], typed=[], spoken=[], hints=[], private=[], read_only=[],
                           results=[], conversations=[], recorded=[])

    class Model:
        def set_owner(self, user_id, name):
            pass

        async def task_from_owner(self, **kwargs):
            return AgentTask("列出測試資料夾", read_only=read_only)

        def __getattr__(self, name):  # the setters apply_settings calls
            return lambda *args: None

        async def character_turn(self, **kwargs):
            seen.hints.append(kwargs.get("task_hint"))
            return "（角色的話）"

    async def send_private(text):
        seen.private.append(text)
        return delivered

    async def post_result(text, place):
        seen.results.append((text, place))
        return posted

    class Tasks:
        async def workspace(self):
            return str(tmp_path)

        async def run(self, text, workspace, callback, *, read_only, conversation):
            seen.read_only.append(read_only)
            seen.conversations.append(conversation)
            await callback("delta", {"text": "a.txt c.tmp"})
            await callback("done", {})

    runtime = CopilotRuntime(
        tmp_path,
        replace(CopilotConfig(), character_agent=True, compact_context=False,
                character_memory="off", character_lull_seconds=0),
        1,
        lambda value: None,
        lambda value: None,
        on_character_line=seen.spoken.append,
        on_character_text=lambda line, place: seen.typed.append((line, place)),
        on_turn=seen.recorded.append,
        agent_tasks=Tasks(),
        on_agent_private=send_private,
        on_agent_result=post_result,
        on_task_mark=lambda channel, message, state: seen.marks.append((channel, message, state)),
        thread_history=history,
    )
    runtime._llm = Model()
    runtime._character_mode = True
    runtime._loop = asyncio.get_running_loop()
    runtime._wake = asyncio.Event()
    runtime._worker = asyncio.create_task(runtime._suggestion_worker())
    return runtime, seen


async def _until(condition):
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("timed out")


async def _close(runtime):
    runtime._worker.cancel()
    await asyncio.gather(runtime._worker, return_exceptions=True)
    await runtime.stop_agent_task()


@pytest.mark.asyncio
async def test_work_from_a_thread_is_marked_on_the_message_instead_of_announced(tmp_path):
    runtime, seen = _marked_runtime(tmp_path)
    try:
        runtime._handle_turn(1, "owner", "幫我看一下測試資料夾", "text", True,
                             place=42, channel_id=900, message_id=42)
        await _until(lambda: len(seen.marks) == 2)
        await asyncio.sleep(0.02)
        assert seen.marks == [(900, 42, "accepted"), (900, 42, "done")]
        # The result stays in the thread (the owner's memory of the work) and
        # in the thread's conversation, said by the Agent, not the character.
        assert seen.results == [("a.txt c.tmp", 42)] and seen.private == []
        last = runtime._context(42).snapshot()[-1]
        assert (last.speaker_name, last.text, last.is_self) == ("思考機", "a.txt c.tmp", False)
        # Later work typed in this thread continues the same Agent session.
        assert seen.conversations == [42]
        # No 「接令」 or 「完成了」 lines: the gear, the check and the result say it.
        assert seen.hints == [] and seen.typed == [] and seen.spoken == []
    finally:
        await _close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("read_only", [True, False])
async def test_the_tasks_scope_reaches_edgeagent(tmp_path, read_only):
    """Work the owner asked only to read goes to EdgeAgent read-only; work
    that asks for changes goes with the owner's usual permissions."""
    runtime, seen = _marked_runtime(tmp_path, read_only=read_only)
    try:
        runtime._handle_turn(1, "owner", "幫我看一下測試資料夾", "text", True,
                             place=42, channel_id=900, message_id=42)
        await _until(lambda: len(seen.marks) == 2)
        assert seen.read_only == [read_only]
    finally:
        await _close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("delivered", [True, False])
async def test_a_result_the_thread_cannot_take_goes_to_the_dm(tmp_path, delivered):
    runtime, seen = _marked_runtime(tmp_path, posted=False, delivered=delivered)
    try:
        runtime._handle_turn(1, "owner", "幫我看一下測試資料夾", "text", True,
                             place=42, channel_id=900, message_id=42)
        await _until(lambda: seen.marks[-1:] == [(900, 42, "done")])
        await asyncio.sleep(0.02)
        assert seen.results == [("a.txt c.tmp", 42)] and seen.private == ["a.txt c.tmp"]
        if delivered:
            assert seen.hints == [] and seen.typed == []
        else:
            assert seen.hints == [("report", PRIVATE_REPORTS["undelivered"])]
            assert seen.typed == [("（角色的話）", 42)] and seen.spoken == []
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_a_forgotten_thread_is_read_back_before_its_new_line(tmp_path):
    """After a restart (or once more threads pushed it out) a thread's next
    line first brings its earlier lines back, as context only: nothing old is
    answered, handed to the Agent or recorded again."""
    asked = []
    release = asyncio.Event()

    async def history(place, before, limit):
        asked.append((place, before))
        await release.wait()
        return [(1, "owner", "幫我數 tmp 檔", "text"), (99, "Machina", "遵命", "mine"),
                (99, "Machina", "a.tmp b.tmp", "agent"), (5, "阿傑", "我也想看", "text")]

    runtime, seen = _marked_runtime(tmp_path, history=history)
    try:
        runtime.accept_text(5, "阿傑", "那剛剛那兩個是什麼", True, place=77, channel_id=900, message_id=80)
        runtime.accept_text(5, "阿傑", "快說", True, place=77, channel_id=900, message_id=81)
        await _until(lambda: asked)
        release.set()
        await _until(lambda: len(runtime._context(77).snapshot()) == 6)
        turns = runtime._context(77).snapshot()
        assert [t.text for t in turns] == ["幫我數 tmp 檔", "遵命", "a.tmp b.tmp", "我也想看",
                                           "那剛剛那兩個是什麼", "快說"]
        assert turns[1].is_self and turns[2].speaker_name == "思考機" and not turns[2].is_self
        assert turns[0].speaker_id == 1 and turns[0].via == "text"
        assert asked == [(77, 80)]
        assert [t.text for t in seen.recorded] == ["那剛剛那兩個是什麼", "快說"]
        assert not runtime._owner_tasks and seen.conversations == []
        runtime.accept_text(5, "阿傑", "還在嗎", True, place=77, channel_id=900, message_id=82)
        await _until(lambda: len(runtime._context(77).snapshot()) == 7)
        assert len(asked) == 1  # read once
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_an_unreadable_thread_is_not_pretended_to_be_remembered(tmp_path):
    asked = []

    async def history(place, before, limit):
        asked.append(place)
        raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "no history")

    runtime, seen = _marked_runtime(tmp_path, history=history)
    try:
        runtime.accept_text(5, "阿傑", "剛剛說到哪", True, place=77, channel_id=900, message_id=80)
        await _until(lambda: asked and not runtime._resuming)
        note, line = runtime._context(77).snapshot()
        assert note.text == "（讀不到這個討論串之前的訊息）" and line.text == "剛剛說到哪"
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_work_typed_in_the_voice_room_is_marked_and_still_announced(tmp_path):
    runtime, seen = _marked_runtime(tmp_path)
    try:
        runtime._handle_turn(1, "owner", "幫我看一下測試資料夾", "text", True,
                             channel_id=555, message_id=7)
        await _until(lambda: len(seen.spoken) == 2)
        assert seen.marks == [(555, 7, "accepted"), (555, 7, "done")]
        assert seen.hints == [("ack", "列出測試資料夾"), ("report", PRIVATE_REPORTS["done"])]
        assert seen.typed == [] and seen.results == [] and seen.private == ["a.txt c.tmp"]
        assert seen.conversations == [VOICE_ROOM]
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_a_busy_agent_says_so_in_the_thread_and_a_stopped_job_gets_a_cross(tmp_path):
    from silenttalk.copilot.runtime import _BUSY

    runtime, seen = _marked_runtime(tmp_path)
    running = asyncio.get_running_loop().create_future()
    runtime._agent_job = running
    runtime._agent_origin = _Trigger("owner", "上一件", speaker_id=1, place=42, channel_id=900, message_id=41)
    try:
        later = _Trigger("owner", "再一件", speaker_id=1, place=42, channel_id=900, message_id=43)
        assert await runtime._dispatch_owner(later, ()) is True
        assert seen.hints == [("report", _BUSY)] and seen.typed == [("（角色的話）", 42)]
        assert not any(message == 43 for _, message, _ in seen.marks)
        runtime.apply_settings({"character_agent": False})  # the owner turns the Agent off
        assert seen.marks == [(900, 41, "failed")]
    finally:
        running.cancel()
        await _close(runtime)


@pytest.mark.asyncio
async def test_the_controller_types_into_the_right_place_and_marks_the_message():
    from silenttalk.controller import AppController

    calls = []

    class Discord:
        async def send_text(self, text, place):
            calls.append(("send", text, place))
            return True

        async def mark_task(self, channel_id, message_id, state):
            calls.append(("mark", channel_id, message_id, state))

    class Copilot:
        def record_self(self, text, place, *, via):
            calls.append(("self", text, place, via))

    controller = object.__new__(AppController)
    controller._closing = False
    controller._settings = SimpleNamespace(app=SimpleNamespace(max_text_length=300))
    controller._discord, controller._copilot = Discord(), Copilot()
    scheduled = []
    controller._schedule = scheduled.append
    controller._type_as_character("在串裡回你", 42)
    controller._mark_task(900, 42, "done")
    for job in scheduled:
        await job
    assert calls == [("send", "在串裡回你", 42), ("self", "在串裡回你", 42, "text"),
                     ("mark", 900, 42, "done")]


@pytest.mark.asyncio
async def test_public_reports_do_not_add_a_line_to_a_thread_that_has_the_result(tmp_path):
    marks, shown, posted = [], [], []

    async def post(text, place):
        posted.append((text, place))
        return True

    async def deliver(payload):
        shown.append(payload)

    class Tasks:
        async def approve(self, call_id, value):
            raise AssertionError("a delivered approval waits for the owner")

    runtime = _agent_runtime(tmp_path, public=True, approval=deliver, tasks=Tasks())
    runtime._on_agent_result = post
    runtime._on_task_mark = lambda channel, message, state: marks.append(state)
    runtime._agent_origin = _Trigger("owner", "x", speaker_id=1, place=42, channel_id=900, message_id=42)
    await runtime._agent_event("approval", {"call_id": "c1", "tool": "write"})
    await runtime._agent_event("delta", {"text": "3 個測試通過"})
    await runtime._agent_event("done", {})
    assert len(shown) == 1 and marks == ["done"]
    assert posted == [("3 個測試通過", 42)] and list(runtime._task_hints) == []
