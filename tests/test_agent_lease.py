from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from silenttalk import agent_lease
from silenttalk.copilot import smoke as copilot_smoke
from silenttalk.copilot.llm import LocalReplyModel


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
    statuses = iter([None, {"ready": True, "mode": "base"}])
    monkeypatch.setattr(agent_lease, "service_status", lambda: next(statuses))
    monkeypatch.setattr(agent_lease, "_control_service_present", lambda: False)
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
    monkeypatch.setattr(
        agent_lease,
        "service_status",
        lambda: {"ready": True} if marker.exists() else None,
    )
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
        character_lora_uses=("options",),
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
    model = LocalReplyModel(
        Path("e4b.gguf"),
        lora_path=Path("character.gguf"),
        project_dir=tmp_path,
    )

    await model.start()
    assert model.transport.lease.owned is True
    assert model.transport.adapter_loaded is True
    assert model.transport.base_url == "http://127.0.0.1:18089"
    await model.stop()

    assert calls == [("acquire", os.getpid()), ("release", os.getpid())]
    assert model.transport.lease.owned is False


def test_edge_client_starts_global_e4b_without_importing_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = iter([None, {"ready": True, "mode": "base"}])
    monkeypatch.setattr(agent_lease, "service_status", lambda: next(statuses))
    monkeypatch.setattr(agent_lease, "_control_service_present", lambda: False)
    monkeypatch.setattr(
        agent_lease, "_global_agent_command", lambda: "C:/bin/edge-agent.cmd"
    )
    monkeypatch.setattr(agent_lease.time, "sleep", lambda seconds: None)

    with patch("subprocess.Popen") as spawn:
        result = agent_lease.ensure_service(timeout=1)

    assert result["ready"] is True
    command = spawn.call_args.args[0]
    assert command[-2:] == ["C:/bin/edge-agent.cmd", "start"]


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


def test_character_acquisition_does_not_require_a_healthy_previous_model(monkeypatch):
    monkeypatch.setattr(
        agent_lease, "service_status", lambda: {"ready": False, "error": "model crash"}
    )
    assert agent_lease.ensure_service(require_ready=False)["ready"] is False


@pytest.mark.asyncio
async def test_lease_retries_initial_failure_and_recovers_a_lost_service(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(agent_lease, "_LEASE_CHECK_SECONDS", 0.01)
    monkeypatch.setattr(agent_lease, "_LEASE_RETRY_SECONDS", 0.01)
    acquired = []
    connected = []
    released = []
    status = {"ready": True, "mode": "character", "owner_pid": 123}

    def acquire(project_dir, owner_pid):
        acquired.append(owner_pid)
        if len(acquired) == 1:
            raise agent_lease.AgentLeaseError("synthetic unavailable service")
        status["ready"] = True
        return {"port": 18089 + len(acquired) - 2}

    monkeypatch.setattr(agent_lease, "acquire_character", acquire)
    monkeypatch.setattr(agent_lease, "service_status", lambda: dict(status))
    monkeypatch.setattr(agent_lease, "release_character", released.append)
    lease = agent_lease.CharacterLease(tmp_path, 123, connected.append)
    try:
        await asyncio.wait_for(lease.start(), timeout=1)
        assert acquired == [123, 123]
        assert connected == [{"port": 18089}]
        status["ready"] = False
        async with asyncio.timeout(1):
            while len(connected) < 2:
                await asyncio.sleep(0.01)
        assert connected[-1] == {"port": 18090}
        assert not released
    finally:
        await lease.stop()
    assert released == [123]


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
