from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from silenttalk import agent_lease
from silenttalk.copilot import smoke as copilot_smoke
from silenttalk.copilot.llm import LocalReplyModel
from silenttalk.copilot.reply_transport import InferenceDeferred, ReplyTransport


class FakeEdgeAgent:
    """EdgeAgent's control port as SilentTalk sees it: GET /status/events (the
    status at once, then one each change) and the character's inference path,
    which turns a request away while `busy` and publishes the refusal, as
    EdgeAgent's gateway does."""

    def __init__(self, **status: object) -> None:
        self.status: dict[str, object] = {
            "ready": True,
            "mode": "character",
            "owner_pid": os.getpid(),
            "character_admitted": True,
            "character_refused": 0,
            **status,
        }
        self.busy = False
        self.requests: list[str] = []
        self._changes = threading.Condition()
        self._version = 0
        # Streams end when this changes (drop): their handlers return and the
        # server closes the sockets, as EdgeAgent's exit closes them. A
        # shutdown() alone does not end a client's read on Windows.
        self._generation = 0
        self.streams_served = 0  # streams whose handler is serving
        self._closed = False
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                fake.requests.append("GET " + self.path)
                if self.path != "/status/events":
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                with fake._changes:
                    seen, generation = -1, fake._generation
                    fake.streams_served += 1
                try:
                    while True:
                        with fake._changes:
                            fake._changes.wait_for(
                                lambda last=seen: fake._version != last
                                or fake._closed or fake._generation != generation
                            )
                            if fake._closed or fake._generation != generation:
                                return
                            seen, status = fake._version, dict(fake.status)
                        self.wfile.write(
                            b"event: status\ndata: " + json.dumps(status).encode() + b"\n\n"
                        )
                        self.wfile.flush()
                except OSError:
                    pass

            def do_POST(self) -> None:
                fake.requests.append("POST " + self.path)
                self.rfile.read(int(self.headers["Content-Length"]))
                if fake.busy:
                    fake.publish(
                        character_refused=int(fake.status["character_refused"]) + 1,
                        character_admitted=False,
                    )
                    body, code = b'{"error":{"code":"inference_busy"}}', 423
                else:
                    body = b'{"choices":[{"message":{"content":"\xe5\xa5\xbd"}}]}'
                    code = 200
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def publish(self, **changes: object) -> None:
        with self._changes:
            self.status.update(changes)
            self._version += 1
            self._changes.notify_all()

    def drop(self) -> None:
        """EdgeAgent went away: every open stream ends."""
        with self._changes:
            self._generation += 1
            self._changes.notify_all()

    def close(self) -> None:
        with self._changes:
            self._closed = True
            self._changes.notify_all()
        self.drop()
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def edge_agent(monkeypatch):
    fake = FakeEdgeAgent()
    monkeypatch.setattr(agent_lease, "CONTROL_PORT", fake.port)
    yield fake
    fake.close()


class HeldStream:
    """agent_lease.StatusStream as it reads while the lease is held: the given
    statuses, then nothing until closed."""

    def __init__(self, *statuses: dict[str, object]) -> None:
        self._statuses = statuses or (
            {"ready": True, "mode": "character", "owner_pid": os.getpid(),
             "character_admitted": True},
        )
        self._closed = threading.Event()

    def __call__(self, deadline: float | None = None) -> HeldStream:
        return self

    def __iter__(self):
        yield from self._statuses
        self._closed.wait()

    def close(self) -> None:
        self._closed.set()


def _no_sleep(seconds: float) -> None:
    raise AssertionError("waited on a timer")


def test_silenttalk_sends_character_configuration_through_http_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = SimpleNamespace(
        llm_model="e4b.gguf",
        character_lora="character.gguf",
        llama_port=18088,
        llm_context_size=32768,
    )
    calls: list[tuple[str, dict[str, object], float]] = []
    monkeypatch.setattr(
        agent_lease,
        "load_settings",
        lambda project_dir: SimpleNamespace(copilot=config),
    )
    monkeypatch.setattr(agent_lease, "ensure_service", lambda **kwargs: {})
    monkeypatch.setattr(
        agent_lease,
        "post_json",
        lambda path, payload, timeout: calls.append((path, payload, timeout)) or {},
    )

    agent_lease.acquire_character(tmp_path, 456)

    assert calls == [
        (
            "/character",
            {
                "owner_pid": 456,
                "character": {
                    "model": "e4b.gguf",
                    "lora": "character.gguf",
                    "port": 18088,
                    "context_size": 32768,
                },
            },
            360,
        )
    ]


def test_e4b_command_is_found_before_a_new_terminal_is_opened(tmp_path, monkeypatch):
    command = tmp_path / "Microsoft/WinGet/Links/edge-agent.cmd"
    command.parent.mkdir(parents=True)
    command.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(agent_lease.shutil, "which", lambda name: None)
    if os.name == "nt":
        assert agent_lease._global_agent_command() == str(command)


@pytest.mark.skipif(os.name != "nt", reason="Windows independent launcher")
def test_background_client_uses_the_installed_launcher_without_shell_parsing(
    tmp_path, monkeypatch
):
    directory = tmp_path / "中文 & 路徑"
    directory.mkdir()
    launcher = directory / "edge-agent-launch.ps1"
    launcher.write_text("# fixture launcher\n", encoding="ascii")
    monkeypatch.setattr(agent_lease, "_control_service_present", lambda: False)
    monkeypatch.setattr(
        agent_lease, "StatusStream", HeldStream({"ready": True, "mode": "base"})
    )
    monkeypatch.setattr(
        agent_lease, "_global_agent_command", lambda: str(directory / "edge-agent.cmd")
    )
    with patch("subprocess.Popen") as spawn:
        agent_lease.ensure_service()
    argv = spawn.call_args.args[0]
    assert argv[0] == "powershell.exe"
    assert argv[argv.index("-File") + 1] == str(launcher)
    assert argv[-1] == "start"
    assert not spawn.call_args.kwargs["creationflags"] & subprocess.DETACHED_PROCESS
    spawn.return_value.wait.assert_called_once_with()


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell process flags")
def test_background_start_really_executes_the_independent_launcher(
    tmp_path, monkeypatch
):
    marker = tmp_path / "started"
    directory = tmp_path / "原生 & E4B"
    directory.mkdir()
    launcher = directory / "edge-agent-launch.ps1"
    marker_path = str(marker).replace("'", "''")
    launcher.write_text(
        f"[IO.File]::WriteAllText('{marker_path}', '1')\n", encoding="utf-8-sig"
    )

    class Stream(HeldStream):
        def __iter__(self):
            # The launcher has exited before the status is read.
            yield {"ready": marker.exists()}

    monkeypatch.setattr(agent_lease, "StatusStream", Stream())
    monkeypatch.setattr(agent_lease, "_control_service_present", lambda: False)
    monkeypatch.setattr(
        agent_lease, "_global_agent_command", lambda: str(directory / "edge-agent.cmd")
    )
    assert agent_lease.ensure_service(timeout=15)["ready"] is True
    assert marker.read_text() == "1"


def test_copilot_smoke_keeps_only_model_names_for_e4b(tmp_path: Path) -> None:
    config = SimpleNamespace(
        llm_model="e4b.gguf",
        character_lora="character.gguf",
        character_lora_uses=("line",),
        llama_port=18088,
        llm_context_size=32768,
        max_reply_chars=72,
    )

    model = copilot_smoke.build_reply_model(tmp_path, config)

    assert model._managed_service is True
    assert model._project_dir == tmp_path
    assert model._model_path == Path("e4b.gguf")
    assert model._lora_path == Path("character.gguf")
    assert ".runtime" not in str(model._model_path)


@pytest.mark.asyncio
async def test_silenttalk_always_borrows_and_releases_e4b(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        agent_lease,
        "acquire_character",
        lambda project_dir, owner_pid: (
            calls.append(("acquire", owner_pid)) or {"port": 18089}
        ),
    )
    monkeypatch.setattr(
        agent_lease,
        "release_character",
        lambda owner_pid: calls.append(("release", owner_pid)),
    )
    monkeypatch.setattr(agent_lease, "StatusStream", HeldStream())
    model = LocalReplyModel(
        Path("e4b.gguf"),
        lora_path=Path("character.gguf"),
        project_dir=tmp_path,
    )

    await asyncio.wait_for(model.start(), 1)
    assert model.transport.lease.owned is True
    assert model.transport.adapter_loaded is True
    assert model.transport.base_url == "http://127.0.0.1:18089"
    await model.stop()

    assert calls == [("acquire", os.getpid()), ("release", os.getpid())]
    assert model.transport.lease.owned is False


def test_edge_client_starts_global_e4b_and_waits_on_its_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EdgeAgent not running: its launcher starts it and returns once it is
    up; the status then comes from its stream. No timer anywhere."""
    monkeypatch.setattr(agent_lease, "_control_service_present", lambda: False)
    monkeypatch.setattr(
        agent_lease, "_global_agent_command", lambda: "C:/bin/edge-agent.cmd"
    )
    monkeypatch.setattr(
        agent_lease, "StatusStream", HeldStream({"ready": True, "mode": "base"})
    )
    monkeypatch.setattr(agent_lease.time, "sleep", _no_sleep)

    with patch("subprocess.Popen") as spawn:
        result = agent_lease.ensure_service(timeout=1)

    assert result["ready"] is True
    command = spawn.call_args.args[0]
    assert command[-2:] == ["C:/bin/edge-agent.cmd", "start"]
    spawn.return_value.wait.assert_called_once_with()


def test_startup_readiness_comes_from_the_stream_without_asking_again(
    edge_agent: FakeEdgeAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EdgeAgent is up but its model still loading: the wait ends with the
    status that says ready, pushed by EdgeAgent, not by asking again."""
    edge_agent.publish(ready=False, mode="base")
    monkeypatch.setattr(agent_lease.time, "sleep", _no_sleep)
    result: dict[str, object] = {}
    thread = threading.Thread(
        target=lambda: result.update(agent_lease.ensure_service(timeout=5))
    )
    thread.start()
    threading.Event().wait(0.3)
    assert not result
    ready_at = time.monotonic()
    edge_agent.publish(ready=True)
    thread.join(2)
    assert result["ready"] is True
    assert time.monotonic() - ready_at < 0.2
    assert edge_agent.requests == ["GET /status/events"]


def test_character_acquisition_does_not_require_a_healthy_previous_model(monkeypatch):
    monkeypatch.setattr(agent_lease, "_control_service_present", lambda: True)
    monkeypatch.setattr(
        agent_lease, "StatusStream", HeldStream({"ready": False, "error": "model crash"})
    )
    assert agent_lease.ensure_service(require_ready=False)["ready"] is False
    with pytest.raises(agent_lease.AgentLeaseError, match="model crash"):
        agent_lease.ensure_service()


def test_the_status_stream_sends_each_change_and_closing_ends_a_read(
    edge_agent: FakeEdgeAgent,
) -> None:
    stream = agent_lease.StatusStream()
    statuses = iter(stream)
    assert next(statuses)["mode"] == "character"
    changed_at = time.monotonic()
    edge_agent.publish(mode="base")
    assert next(statuses)["mode"] == "base"
    assert time.monotonic() - changed_at < 0.2
    # A read blocked with nothing to come ends when another thread closes it.
    ended = threading.Event()

    def read_on() -> None:
        for _ in statuses:
            pass
        ended.set()

    threading.Thread(target=read_on, daemon=True).start()
    time.sleep(0.2)
    assert not ended.is_set()
    stream.close()
    assert ended.wait(1)


@pytest.mark.asyncio
async def test_the_lease_is_taken_again_when_edgeagent_says_it_is_gone(
    edge_agent: FakeEdgeAgent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquired: list[int] = []
    connected: list[dict[str, object]] = []
    released: list[int] = []

    def acquire(project_dir, owner_pid):
        acquired.append(owner_pid)
        if len(acquired) == 1:
            raise agent_lease.AgentLeaseError("synthetic unavailable service")
        edge_agent.publish(mode="character", owner_pid=owner_pid)
        return {"port": 18089 + len(acquired) - 2}

    monkeypatch.setattr(agent_lease, "_LEASE_RETRY_SECONDS", 0.01)
    monkeypatch.setattr(agent_lease, "acquire_character", acquire)
    monkeypatch.setattr(agent_lease, "release_character", released.append)
    lease = agent_lease.CharacterLease(tmp_path, os.getpid(), connected.append)
    try:
        await asyncio.wait_for(lease.start(), timeout=1)
        assert len(acquired) == 2 and connected == [{"port": 18089}]
        # Idle: nothing is asked again.
        await asyncio.sleep(0.5)
        assert edge_agent.requests == ["GET /status/events"]
        # EdgeAgent's mode changed: the lease is gone, taken again at once.
        lost_at = time.monotonic()
        edge_agent.publish(mode="base", owner_pid=None)
        async with asyncio.timeout(1):
            while len(connected) < 2:
                await asyncio.sleep(0.01)
        assert time.monotonic() - lost_at < 0.3
        assert connected[-1] == {"port": 18090}
        # EdgeAgent went away (its streams ended): taken again too. The new
        # stream must be served first, or it would outlive the drop (a test
        # race only: a real EdgeAgent's exit closes every socket).
        async with asyncio.timeout(1):
            while edge_agent.streams_served < 2:
                await asyncio.sleep(0.01)
        edge_agent.drop()
        async with asyncio.timeout(1):
            while len(connected) < 3:
                await asyncio.sleep(0.01)
        assert not released
    finally:
        await lease.stop()
    assert released == [os.getpid()]


@pytest.mark.asyncio
async def test_a_model_reload_is_not_a_lost_lease(
    edge_agent: FakeEdgeAgent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EdgeAgent reloading the model after a crash keeps the lease (its mode
    and owner stay): nothing is taken again, the character waits."""
    acquired: list[int] = []
    monkeypatch.setattr(
        agent_lease, "acquire_character", lambda *_: acquired.append(1) or {}
    )
    monkeypatch.setattr(agent_lease, "release_character", lambda *_: None)
    lease = agent_lease.CharacterLease(tmp_path, os.getpid(), lambda _: None)
    try:
        await asyncio.wait_for(lease.start(), timeout=1)
        edge_agent.publish(ready=False, character_admitted=False)
        await asyncio.sleep(0.2)
        edge_agent.publish(ready=True, character_admitted=True)
        await asyncio.sleep(0.2)
        assert acquired == [1]
    finally:
        await lease.stop()


@pytest.mark.asyncio
async def test_a_deferred_request_goes_as_soon_as_edgeagent_admits_it(
    edge_agent: FakeEdgeAgent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EdgeAgent turned the character away: its turn comes with the status
    after that refusal that admits it again, right away, never sooner (the
    status from before the request said admitted too)."""
    monkeypatch.setattr(
        agent_lease, "acquire_character", lambda *_: {"port": edge_agent.port}
    )
    monkeypatch.setattr(agent_lease, "release_character", lambda *_: None)
    transport = ReplyTransport(tmp_path, edge_agent.port, False, 15)
    await asyncio.wait_for(transport.start(), timeout=1)
    try:
        edge_agent.busy = True
        with pytest.raises(InferenceDeferred) as deferred:
            await asyncio.to_thread(transport.request_messages, [])
        waiting = asyncio.create_task(transport.turn(deferred.value))
        await asyncio.sleep(0.3)
        assert not waiting.done()
        edge_agent.busy = False
        freed = time.monotonic()
        edge_agent.publish(character_admitted=True)
        await asyncio.wait_for(waiting, 1)
        assert time.monotonic() - freed < 0.1
        assert await asyncio.to_thread(transport.request_messages, []) == "好"
        posts = [r for r in edge_agent.requests if r.startswith("POST")]
        assert len(posts) == 2
    finally:
        await transport.stop()


@pytest.mark.asyncio
async def test_a_turn_waits_while_the_lease_is_gone(
    edge_agent: FakeEdgeAgent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deferred request waits through a lost lease; the lease taken again
    with the character admitted is its turn."""
    taken = threading.Event()
    taken.set()

    def acquire(*_):
        assert taken.wait(5)
        edge_agent.publish(mode="character", owner_pid=os.getpid())
        return {}

    monkeypatch.setattr(agent_lease, "acquire_character", acquire)
    monkeypatch.setattr(agent_lease, "release_character", lambda *_: None)
    lease = agent_lease.CharacterLease(tmp_path, os.getpid(), lambda _: None)
    try:
        await asyncio.wait_for(lease.start(), timeout=1)
        waiting = asyncio.create_task(lease.turn(lease.statuses_seen))
        taken.clear()
        edge_agent.publish(mode="base", owner_pid=None)
        await asyncio.sleep(0.3)
        assert not waiting.done()
        taken.set()
        await asyncio.wait_for(waiting, 1)
    finally:
        taken.set()
        await lease.stop()


def test_post_json_uses_only_the_loopback_control_api() -> None:
    class Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return Response(b'{"ready":true,"mode":"character"}')

    with patch("urllib.request.urlopen", fake_urlopen):
        result = agent_lease.post_json("/character", {"owner_pid": 7}, timeout=1)

    assert captured == {
        "url": "http://127.0.0.1:18087/character",
        "payload": {"owner_pid": 7},
    }
    assert result["mode"] == "character"


def test_silenttalk_source_has_no_edge_agent_import_or_local_server_builder() -> None:
    source_root = Path(__file__).resolve().parents[1] / "silenttalk"
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in source_root.rglob("*.py")
    )

    assert "from edge_agent" not in sources
    assert "import edge_agent" not in sources
    assert "build_server_args" not in sources


@pytest.mark.asyncio
async def test_stopping_an_unavailable_lease_cancels_retries(tmp_path, monkeypatch):
    attempts = []

    def fail(*args):
        attempts.append(1)
        raise agent_lease.AgentLeaseError("synthetic unavailable service")

    monkeypatch.setattr(agent_lease, "acquire_character", fail)
    lease = agent_lease.CharacterLease(tmp_path, 123, lambda _: None)
    waiting = asyncio.create_task(lease.start())
    async with asyncio.timeout(1):
        while not attempts:
            await asyncio.sleep(0.01)
    await lease.stop()
    waiting.cancel()
    await asyncio.gather(waiting, return_exceptions=True)
    assert lease._task is None
    assert not lease.owned
    assert attempts == [1]


def test_a_late_http_response_returns_the_closed_lease(tmp_path, monkeypatch):
    returned = []
    lease = agent_lease.CharacterLease(tmp_path, 123, lambda _: None)
    monkeypatch.setattr(agent_lease, "acquire_character", lambda *_: {"port": 18089})
    monkeypatch.setattr(agent_lease, "release_character", returned.append)
    lease._closed.set()
    with pytest.raises(agent_lease.AgentLeaseError, match="closed"):
        lease._acquire(lease._closed)
    assert returned == [123]
