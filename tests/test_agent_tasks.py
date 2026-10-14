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
from silenttalk.conversation import VOICE_ROOM, AgentTask
from silenttalk.conversation import Trigger as _Trigger
from silenttalk.copilot.reply_templates import PRIVATE_REPORTS
from silenttalk.copilot.runtime import CopilotRuntime
from silenttalk.discord_approval import AgentApprovalView
from silenttalk.discord_channels import DiscordChannels
from silenttalk.persona import MACHINE_SPIRIT


@pytest.mark.asyncio
async def test_sse_denial_and_failure_use_discord_profile_and_first_workspace(tmp_path):
    released = asyncio.Event()
    state = {"requests": [], "approvals": [], "executed": False, "resets": []}

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

    async def reset(request):
        state["resets"].append((await request.json())["session_id"])
        return web.json_response({"reset": True})

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
    app.router.add_post("/chat/reset", reset)
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
        assert state["requests"][0]["scope"] == "read"
        assert state["approvals"][0]["scope"] == "once"
        assert client.session_id is None and state["resets"] == []
        # A public task is a session of its own, dropped when it ends.
        released.set()
        await asyncio.wait_for(
            client.run("fixture", workspace, event, scope="public", conversation=42), 10
        )
        public = state["requests"][1]["session_id"]
        assert public != "discord-42" and state["resets"] == [public]
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


class _DM:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, text, **kwargs):
        if self.fail:
            raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"),
                                    "Cannot send messages to this user")
        self.sent.append((text, kwargs.get("view")))


def _discord_client(dm):
    client = object.__new__(DiscordChannels)
    client._config = SimpleNamespace(owner_user_id=1)
    client._client = SimpleNamespace()
    client._client.get_user = lambda user_id: (
        SimpleNamespace(dm_channel=dm) if user_id == 1 else None
    )

    def no_channel():
        raise AssertionError("the voice channel must not be used")

    client._voice = no_channel
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
                                "explain": "影響：會刪除：x" + "。" * 2100,
                                "explain_title": "這個指令在做什麼（PowerShell 自己解析的結果）"}, decide)
    texts = [text for text, _ in dm.sent]
    # EdgeAgent titles its own explanation (a command's parse, a tool's plan).
    assert texts[0].startswith("這個指令在做什麼（PowerShell 自己解析的結果）：") and "會刪除：x" in texts[0]
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
    client = object.__new__(DiscordChannels)
    client._client = SimpleNamespace(user=SimpleNamespace(id=99))
    client.is_our_thread = lambda channel: channel is thread

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


THREAD = 42  # the owner's Agent thread
TEXT_CHANNEL = 900


def _marked_runtime(
    tmp_path,
    *,
    delivered=True,
    scope="read",
    posted=True,
    history=None,
    lookup=None,
    fail_run=None,
    hold=None,
    stopped=False,
):
    """A character runtime (owner: user 1) whose Agent lists a folder; it
    records the marks on messages, what is typed where, what is spoken, the
    DMs, the posted results and how the Agent was asked. `lookup`: the
    instructions for every line that calls it (or, a function of the line,
    for the lines it returns them for); `hold`: an event the Agent's first
    run waits for."""
    seen = SimpleNamespace(
        marks=[],
        typed=[],
        spoken=[],
        hints=[],
        private=[],
        scopes=[],
        results=[],
        conversations=[],
        recorded=[],
        asked=[],
        texts=[],
        files=[],
    )

    class Model:
        def set_owner(self, user_id, name):
            pass

        async def task_from_owner(self, **kwargs):
            seen.asked.append(("owner", kwargs["turns"][-1].text))
            return AgentTask(kwargs["turns"][-1].text, scope=scope)

        async def chat_task(self, **kwargs):
            line = kwargs["turns"][-1].text
            seen.asked.append(("lookup", line))
            text = lookup(line) if callable(lookup) else lookup
            # Even a model that asks for more gets only the chat's scope.
            return AgentTask(text, scope="change") if text else None

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

        async def run(
            self, text, workspace, callback, *, scope, conversation, attachments
        ):
            seen.texts.append(text)
            seen.files.append(attachments)
            seen.scopes.append(scope)
            seen.conversations.append(conversation)
            if fail_run:
                await callback("error", {"message": fail_run})
                return
            if stopped:
                await callback("cancelled", {})
                return
            if hold is not None and len(seen.texts) == 1:
                await hold.wait()
            await callback("delta", {"text": "a.txt c.tmp"})
            await callback("done", {})

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
        on_character_line=seen.spoken.append,
        on_character_text=lambda line, place: seen.typed.append((line, place)),
        on_turn=seen.recorded.append,
        agent_tasks=Tasks(),
        on_agent_private=send_private,
        on_agent_result=post_result,
        on_task_mark=lambda channel, message, state: seen.marks.append(
            (channel, message, state)
        ),
        thread_history=history,
    )
    runtime._llm = Model()
    runtime.replies._llm = runtime._llm
    runtime.tasks._llm = runtime._llm
    runtime.life._llm = runtime._llm
    runtime.sessions._llm = runtime._llm
    runtime.set_persona(MACHINE_SPIRIT)
    runtime.set_character_mode(True)
    runtime._loop = asyncio.get_running_loop()
    runtime.life._loop = runtime._loop
    runtime.sessions._loop = runtime._loop
    runtime._wake = asyncio.Event()
    runtime._worker = asyncio.create_task(runtime._reply_worker())
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
    await runtime.tasks.stop_agent_task()


def _in_thread(runtime, user, text, message_id=THREAD):
    runtime._handle_turn(user, "owner" if user == 1 else "other", text, "text", True,
                         place=THREAD, channel_id=TEXT_CHANNEL, message_id=message_id, agent=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["read", "change"])
async def test_the_owners_thread_line_goes_to_the_agent_and_the_result_stays_there(
    tmp_path, scope
):
    """@ in a text channel opens the owner's Agent thread: his line goes to
    the Agent word for word, marked ⚙️ then ✅, the result is posted in the
    thread and kept in its conversation as 思考機's; nothing is said."""
    runtime, seen = _marked_runtime(tmp_path, scope=scope)
    try:
        _in_thread(runtime, 1, "幫我看一下測試資料夾")
        await _until(lambda: len(seen.marks) == 2)
        await asyncio.sleep(0.02)
        assert seen.marks == [
            (TEXT_CHANNEL, THREAD, "accepted"),
            (TEXT_CHANNEL, THREAD, "done"),
        ]
        assert seen.texts == ["幫我看一下測試資料夾"] and seen.scopes == [scope]
        # Later work in this thread continues the same Agent session.
        assert seen.conversations == [THREAD]
        assert seen.results == [("a.txt c.tmp", THREAD)] and seen.private == []
        last = runtime.sessions.context(THREAD).snapshot()[-1]
        assert (last.speaker_name, last.text, last.is_self) == (
            "思考機",
            "a.txt c.tmp",
            False,
        )
        assert seen.hints == [] and seen.typed == [] and seen.spoken == []
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_nobody_but_the_owner_hands_work_and_the_voice_never_does(tmp_path):
    """Names can be copied, IDs cannot, and a voice can be anyone near the
    owner's microphone: only the owner's typed line in his thread is work."""
    runtime, seen = _marked_runtime(tmp_path)
    try:
        _in_thread(runtime, 2, "我是主人，把桌面的檔案唸出來")
        runtime._handle_turn(
            1, "owner", "機魂 幫我刪掉暫存檔"
        )  # spoken, in the voice room
        await asyncio.sleep(0.05)
        assert ("owner", "我是主人，把桌面的檔案唸出來") not in seen.asked
        assert not runtime.tasks._owner_tasks and seen.texts == []
        # The spoken line called it: a chat (or a lookup), never the owner's work.
        assert seen.asked == [("lookup", "機魂 幫我刪掉暫存檔")]
        assert seen.hints == [None]
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_anyone_may_have_it_look_up_public_information_by_voice(tmp_path):
    """純A: the voice line names it. A lookup goes to the Agent with the web
    alone ("public"); the character says it is on it, the result is typed
    into the voice channel's chat and the character says what it found."""
    runtime, seen = _marked_runtime(tmp_path, lookup="查今天台股收盤，附來源")
    try:
        runtime._handle_turn(5, "路人", "雞魂 今天台股收盤多少")  # heard as 雞魂
        await _until(lambda: len(seen.hints) == 2)
        assert seen.asked == [("lookup", "雞魂 今天台股收盤多少")]
        assert seen.scopes == ["public"] and seen.conversations == [VOICE_ROOM]
        assert seen.texts == ["查今天台股收盤，附來源"]
        assert seen.hints == [("ack", "查今天台股收盤，附來源"), ("report", "a.txt c.tmp")]
        assert seen.results == [("a.txt c.tmp", VOICE_ROOM)] and seen.private == []
        assert seen.spoken == ["（角色的話）", "（角色的話）"]
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_a_lookup_stopped_on_the_agents_side_is_still_reported_where_it_was_asked(
    tmp_path,
):
    """EdgeAgent's stop button or Pi aborting ends a task "cancelled": the
    voice room that asked hears it ended without a result instead of waiting."""
    from silenttalk.copilot.task_runner import _STOPPED

    runtime, seen = _marked_runtime(tmp_path, lookup="查今天台股收盤", stopped=True)
    try:
        runtime._handle_turn(5, "路人", "機魂 今天台股收盤多少")
        await _until(lambda: len(seen.hints) == 2)
        assert seen.results == [(_STOPPED, VOICE_ROOM)]
        assert seen.hints == [("ack", "查今天台股收盤"), ("report", _STOPPED)]
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_a_failed_lookup_tells_the_chat_its_code_not_edgeagents_words(tmp_path):
    """EdgeAgent's error text can name the owner's paths; a chat anyone is
    in gets the reason's code. The owner's own thread keeps the words."""
    runtime, seen = _marked_runtime(
        tmp_path, lookup="查今天台股收盤", fail_run="C:\\Users\\Rex\\EdgeAgent 讀不到"
    )
    try:
        runtime._handle_turn(5, "路人", "機魂 今天台股收盤多少")
        await _until(lambda: seen.results)
        assert seen.results == [("工作失敗了（unknown）。", VOICE_ROOM)]
        _in_thread(runtime, 1, "幫我看一下測試資料夾")
        await _until(lambda: len(seen.results) == 2)
        assert seen.results[1] == ("C:\\Users\\Rex\\EdgeAgent 讀不到", THREAD)
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_a_lookup_typed_in_a_text_channel_is_marked_and_posted_there(tmp_path):
    runtime, seen = _marked_runtime(tmp_path, lookup="查明天台北天氣")
    try:
        runtime._handle_turn(5, "路人", "機魂 明天台北會下雨嗎", "text", True,
                             place=TEXT_CHANNEL, channel_id=TEXT_CHANNEL, message_id=7)
        await _until(lambda: len(seen.marks) == 2)
        await asyncio.sleep(0.02)
        assert seen.marks == [(TEXT_CHANNEL, 7, "accepted"), (TEXT_CHANNEL, 7, "done")]
        assert seen.results == [("a.txt c.tmp", TEXT_CHANNEL)]
        assert seen.hints == [] and seen.spoken == [] and seen.typed == []
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_a_line_that_is_not_a_lookup_gets_the_characters_own_answer(tmp_path):
    runtime, seen = _marked_runtime(tmp_path)
    try:
        runtime._handle_turn(5, "路人", "機魂 你喜歡萬機神嗎")
        await _until(lambda: seen.spoken)
        assert seen.asked == [("lookup", "機魂 你喜歡萬機神嗎")]
        assert seen.texts == [] and seen.hints == [None]
        runtime._handle_turn(5, "路人", "今天好累")  # does not call it: nothing at all
        await asyncio.sleep(0.05)
        assert len(seen.asked) == 1 and len(seen.spoken) == 1
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_disabling_agent_clears_pending_owner_instructions(tmp_path):
    runtime = CopilotRuntime(
        tmp_path,
        replace(CopilotConfig(), character_agent=True),
        1,
        lambda value: None,
    )
    runtime.set_character_mode(True)
    runtime._loop = asyncio.get_running_loop()
    runtime.life._loop = runtime._loop
    runtime.sessions._loop = runtime._loop
    runtime._wake = asyncio.Event()
    runtime._handle_turn(1, "owner", "fixture", "text", True, place=THREAD, agent=True)
    assert len(runtime.tasks._owner_tasks) == 1
    runtime.apply_settings({"character_agent": False})
    assert not runtime.tasks._owner_tasks
    runtime.apply_settings({"character_agent": True})
    assert not runtime.tasks._owner_tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["decision", "workspace"])
@pytest.mark.parametrize("toggle", ["agent", "character"])
async def test_cancelled_dispatch_cannot_revive_after_reenable(
    tmp_path, monkeypatch, stage, toggle
):
    entered, released = asyncio.Event(), asyncio.Event()
    tasks = []

    async def pause(current):
        if current == stage:
            entered.set()
            await released.wait()

    async def decision(**kwargs):
        await pause("decision")
        return AgentTask("fixture")

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
        agent_tasks=Tasks(),
    )
    runtime.set_character_mode(True)
    monkeypatch.setattr(runtime._llm, "task_from_owner", decision)
    dispatch = asyncio.create_task(
        runtime.tasks.dispatch_owner(_Trigger("owner", "fixture", place=THREAD), ())
    )
    await asyncio.wait_for(entered.wait(), 3)
    if toggle == "agent":
        runtime.apply_settings({"character_agent": False})
        runtime.apply_settings({"character_agent": True})
    else:
        runtime.set_character_mode(False)
        runtime.set_character_mode(True)
    released.set()
    await dispatch
    await asyncio.sleep(0)
    assert not tasks and runtime.tasks._agent_job is None


SECRET = "C:\\Users\\Rex\\Documents\\帳號.txt 有 3 行"


@pytest.mark.asyncio
async def test_a_failure_is_posted_in_the_owners_thread(tmp_path):
    runtime, seen = _marked_runtime(tmp_path, fail_run=SECRET)
    try:
        _in_thread(runtime, 1, "看一下帳號檔")
        await _until(lambda: seen.marks[-1:] == [(TEXT_CHANNEL, THREAD, "failed")])
        await asyncio.sleep(0.02)
        assert seen.results == [(SECRET, THREAD)]
        assert seen.spoken == [] and seen.hints == []
    finally:
        await _close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("delivered", [True, False])
async def test_a_result_the_thread_cannot_take_goes_to_the_dm(tmp_path, delivered):
    runtime, seen = _marked_runtime(tmp_path, posted=False, delivered=delivered)
    try:
        _in_thread(runtime, 1, "幫我看一下測試資料夾")
        await _until(lambda: seen.marks[-1:] == [(TEXT_CHANNEL, THREAD, "done")])
        await asyncio.sleep(0.02)
        assert seen.results == [("a.txt c.tmp", THREAD)] and seen.private == ["a.txt c.tmp"]
        if delivered:
            assert seen.hints == [] and seen.typed == []
        else:
            assert seen.hints == [("report", PRIVATE_REPORTS["undelivered"])]
            assert seen.typed == [("（角色的話）", THREAD)] and seen.spoken == []
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_approval_details_stay_in_the_dm_and_an_undeliverable_one_is_denied(
    tmp_path,
):
    """The buttons and the exact operation go to the owner's DMs; the thread
    hears nothing of them. Undeliverable: denied, and the thread is told."""
    approved, shown = [], []

    class Tasks:
        async def approve(self, call_id, value):
            approved.append((call_id, value))
            return True

    async def deliver(payload):
        shown.append(payload)

    def runtime_with(approval):
        runtime = CopilotRuntime(
            tmp_path,
            replace(CopilotConfig(), character_agent=True),
            1,
            lambda value: None,
            agent_tasks=Tasks(),
            on_agent_approval=approval,
        )
        runtime.tasks._agent_origin = _Trigger("owner", "x", speaker_id=1, place=THREAD)
        return runtime

    payload = {
        "call_id": "c1",
        "tool": "powershell",
        "explicit": "destructive",
        "arguments": {"command": "Remove-Item C:\\Users\\Rex\\x.tmp"},
    }
    runtime = runtime_with(deliver)
    await runtime.tasks._agent_event("approval", payload)
    assert shown == [payload] and not approved and not runtime.tasks._task_hints

    async def undeliverable(payload):
        raise RuntimeError("DM closed")

    runtime = runtime_with(undeliverable)
    await runtime.tasks._agent_event("approval", payload)
    assert approved == [("c1", False)]
    assert list(runtime.tasks._task_hints) == [
        ("report", PRIVATE_REPORTS["approval_undelivered"], THREAD)
    ]


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
        return [
            (1, "owner", "幫我數 tmp 檔", "text"),
            (99, "Machina", "遵命", "mine"),
            (99, "Machina", "a.tmp b.tmp", "agent"),
            (5, "阿傑", "我也想看", "text"),
        ]

    runtime, seen = _marked_runtime(tmp_path, history=history)
    try:
        runtime.accept_text(
            5,
            "阿傑",
            "那剛剛那兩個是什麼",
            True,
            place=77,
            channel_id=900,
            message_id=80,
            agent=True,
        )
        runtime.accept_text(
            5, "阿傑", "快說", True, place=77, channel_id=900, message_id=81, agent=True
        )
        await _until(lambda: asked)
        release.set()
        await _until(lambda: len(runtime.sessions.context(77).snapshot()) == 6)
        turns = runtime.sessions.context(77).snapshot()
        assert [t.text for t in turns] == [
            "幫我數 tmp 檔",
            "遵命",
            "a.tmp b.tmp",
            "我也想看",
            "那剛剛那兩個是什麼",
            "快說",
        ]
        assert (
            turns[1].is_self
            and turns[2].speaker_name == "思考機"
            and not turns[2].is_self
        )
        assert turns[0].speaker_id == 1 and turns[0].via == "text"
        assert asked == [(77, 80)]
        assert [t.text for t in seen.recorded] == ["那剛剛那兩個是什麼", "快說"]
        assert not runtime.tasks._owner_tasks and seen.conversations == []
        runtime.accept_text(
            5,
            "阿傑",
            "還在嗎",
            True,
            place=77,
            channel_id=900,
            message_id=82,
            agent=True,
        )
        await _until(lambda: len(runtime.sessions.context(77).snapshot()) == 7)
        assert len(asked) == 1  # read once
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_an_unreadable_thread_is_not_pretended_to_be_remembered(tmp_path):
    asked = []

    async def history(place, before, limit):
        asked.append(place)
        raise discord.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), "no history"
        )

    runtime, seen = _marked_runtime(tmp_path, history=history)
    try:
        runtime.accept_text(
            5,
            "阿傑",
            "剛剛說到哪",
            True,
            place=77,
            channel_id=900,
            message_id=80,
            agent=True,
        )
        await _until(lambda: asked and not runtime.sessions._resuming)
        note, line = runtime.sessions.context(77).snapshot()
        assert (
            note.text == "（讀不到這個討論串之前的訊息）" and line.text == "剛剛說到哪"
        )
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_work_asked_while_the_agent_is_busy_waits_its_turn_and_still_runs(
    tmp_path,
):
    """Laptop round 11: a lookup asked by voice during the owner's work was
    told to wait until it was done and never ran. Now it waits its turn: the
    voice room hears that it is queued, and once the owner's work is done the
    lookup runs and its result comes back to the voice room."""
    from silenttalk.copilot.task_runner import _QUEUED

    hold = asyncio.Event()
    runtime, seen = _marked_runtime(tmp_path, lookup="查明天台北天氣，附來源", hold=hold)
    try:
        _in_thread(runtime, 1, "幫我看一下測試資料夾")
        await _until(lambda: seen.texts == ["幫我看一下測試資料夾"])
        runtime._handle_turn(5, "路人", "機魂 明天台北會下雨嗎")
        await _until(lambda: ("report", _QUEUED) in seen.hints)
        assert seen.texts == ["幫我看一下測試資料夾"] and seen.spoken == ["（角色的話）"]
        hold.set()
        await _until(lambda: len(seen.results) == 2 and len(seen.hints) == 2)
        assert seen.texts == ["幫我看一下測試資料夾", "查明天台北天氣，附來源"]
        assert seen.scopes == ["read", "public"]
        assert seen.results == [("a.txt c.tmp", THREAD), ("a.txt c.tmp", VOICE_ROOM)]
        # It already heard it would wait: no second "on it", just the result.
        assert seen.hints == [("report", _QUEUED), ("report", "a.txt c.tmp")]
        assert seen.marks == [(TEXT_CHANNEL, THREAD, "accepted"), (TEXT_CHANNEL, THREAD, "done")]
    finally:
        hold.set()
        await _close(runtime)


@pytest.mark.asyncio
async def test_a_full_queue_says_so_and_a_stopped_job_drops_what_waited(tmp_path):
    from silenttalk.copilot.task_runner import _MAX_WAITING, _QUEUE_FULL, _QUEUED

    runtime, seen = _marked_runtime(tmp_path)
    running = asyncio.get_running_loop().create_future()
    runtime.tasks._agent_job = running
    runtime.tasks._agent_origin = _Trigger(
        "owner", "上一件", speaker_id=1, place=42, channel_id=900, message_id=41
    )
    try:
        for message in range(43, 44 + _MAX_WAITING):
            await runtime.tasks.dispatch(
                _Trigger("owner", "再一件", speaker_id=1, place=42, channel_id=900,
                         message_id=message),
                AgentTask("再一件"), runtime.tasks.epoch,
            )
        await _until(lambda: len(seen.typed) == _MAX_WAITING + 1)
        assert seen.hints == [("report", _QUEUED)] * _MAX_WAITING + [("report", _QUEUE_FULL)]
        assert all(place == 42 for _, place in seen.typed)
        assert not any(message > 41 for _, message, _ in seen.marks)
        runtime.apply_settings({"character_agent": False})  # the owner turns the Agent off
        assert seen.marks == [(900, 41, "failed")] and not runtime.tasks.has_waiting
    finally:
        running.cancel()
        await _close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("call", ["機魂", "雞魂 在嗎"])
async def test_a_lookup_spoken_after_a_pause_behind_the_name_still_reaches_the_agent(
    tmp_path, call
):
    """Speech recognition ends a segment at half a second of silence: "機魂，
    (pause) 明天台北會下雨嗎" arrives as the bare name, then the request
    without it. The request still called it and goes to the Agent."""
    runtime, seen = _marked_runtime(
        tmp_path, lookup=lambda line: "查明天台北天氣" if "下雨" in line else None
    )
    try:
        runtime._handle_turn(5, "路人", call)
        await _until(lambda: seen.spoken)  # it answered the bare call first
        runtime._handle_turn(5, "路人", "明天台北會下雨嗎")
        await _until(lambda: seen.results)
        assert ("lookup", "明天台北會下雨嗎") in seen.asked
        assert seen.texts == ["查明天台北天氣"] and seen.scopes == ["public"]
        # Only the next line of that speaker: later lines need the name again.
        runtime._handle_turn(5, "路人", "那後天呢")
        runtime._handle_turn(6, "別人", "明天會下雨嗎")
        await asyncio.sleep(0.05)
        assert seen.texts == ["查明天台北天氣"]
    finally:
        await _close(runtime)


@pytest.mark.asyncio
async def test_a_call_with_something_to_say_passes_nothing_on_and_a_late_line_is_not_called(
    tmp_path, monkeypatch
):
    from silenttalk.copilot import runtime as runtime_module

    runtime, _seen = _marked_runtime(tmp_path)

    def waiting() -> str:
        """The line waiting for an answer: only one that called it waits."""
        trigger = runtime._pending.get(VOICE_ROOM)
        return trigger.text if trigger else ""

    try:
        runtime._handle_turn(5, "路人", "機魂 你喜歡萬機神嗎")
        runtime._handle_turn(5, "路人", "明天台北會下雨嗎")
        assert waiting() == "機魂 你喜歡萬機神嗎"
        monkeypatch.setattr(runtime_module, "_CALL_CARRY_SECONDS", 0.05)
        runtime._handle_turn(5, "路人", "機魂")
        await asyncio.sleep(0.1)
        runtime._handle_turn(5, "路人", "明天台北會下雨嗎")
        assert waiting() == ""
        # The time to go on counts from its answer to the call, however late.
        runtime._handle_turn(5, "路人", "機魂")
        await asyncio.sleep(0.1)
        runtime.record_self("在，主人。")
        runtime._handle_turn(5, "路人", "明天台北會下雨嗎")
        assert waiting() == "明天台北會下雨嗎"
    finally:
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
    controller._discord, controller._copilot = (
        SimpleNamespace(channels=Discord()),
        Copilot(),
    )
    scheduled = []
    controller._schedule = scheduled.append
    controller._type_as_character("在串裡回你", 42)
    controller._mark_task(900, 42, "done")
    for job in scheduled:
        await job
    assert calls == [
        ("send", "在串裡回你", 42),
        ("self", "在串裡回你", 42, "text"),
        ("mark", 900, 42, "done"),
    ]


@pytest.mark.asyncio
async def test_files_posted_with_the_line_reach_the_agent_read_only_when_needed(tmp_path):
    """OCR in a chat: the image posted with (or replied to by) the line is
    read into RAM only when work is handed over, and sent with the request."""
    reads = []

    async def image():
        reads.append("photo.png")
        return b"\x89PNG fixture"

    runtime, seen = _marked_runtime(tmp_path, lookup="辨識圖片裡的文字")
    try:
        runtime._handle_turn(5, "路人", "機魂 這張圖寫什麼（附件：photo.png）", "text", True,
                             place=TEXT_CHANNEL, channel_id=TEXT_CHANNEL, message_id=8,
                             attachments=(("photo.png", image),))
        await _until(lambda: seen.files)
        assert reads == ["photo.png"]
        assert seen.files == [[{"name": "photo.png", "data": "iVBORyBmaXh0dXJl"}]]
        assert seen.scopes == ["public"]
    finally:
        await _close(runtime)
