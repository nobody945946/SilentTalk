from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from silenttalk.config import load_settings

# SilentTalk is an EdgeAgent API client. It never owns or launches llama-server.
CONTROL_PORT = 18_087
_LOG = logging.getLogger(__name__)
_LEASE_CHECK_SECONDS = 5.0
_LEASE_RETRY_SECONDS = 5.0


class AgentLeaseError(RuntimeError):
    """Raised when the EdgeAgent service cannot satisfy a request."""


def service_status(timeout: float = 1.0) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{CONTROL_PORT}/status", timeout=timeout
        ) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    return value if isinstance(value, dict) else None


def _control_service_present(timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", CONTROL_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def _global_agent_command() -> str:
    command = shutil.which("edge-agent.cmd") or shutil.which("edge-agent")
    if command is None and os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        candidate = (
            Path(local) / "Microsoft/WinGet/Links/edge-agent.cmd" if local else None
        )
        if candidate is not None and candidate.is_file():
            command = str(candidate)
    if command is None:
        raise AgentLeaseError(
            "找不到獨立 EdgeAgent；請執行啟動 SilentTalk.cmd，自動完成首次部署。"
        )
    return command


def ensure_service(
    timeout: float = 360.0, *, require_ready: bool = True
) -> dict[str, object]:
    status = service_status()
    if status is None and not _control_service_present():
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        command = _global_agent_command()
        if os.name == "nt":
            launcher = Path(command).with_name("edge-agent-launch.ps1")
            if launcher.is_file():
                argv = [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(launcher),
                    "start",
                ]
            else:
                argv = [
                    os.environ.get("COMSPEC", "cmd.exe"),
                    "/d",
                    "/c",
                    "call",
                    command,
                    "start",
                ]
        else:
            argv = [command, "start"]
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )

    deadline = time.monotonic() + timeout
    last: dict[str, object] | None = None
    while time.monotonic() < deadline:
        last = service_status()
        if last is not None and (not require_ready or last.get("ready") is True):
            return last
        if last is not None and last.get("error"):
            raise AgentLeaseError(str(last["error"]))
        time.sleep(0.25)
    raise AgentLeaseError(f"EdgeAgent did not become ready: {last}")


def post_json(
    path: str,
    payload: dict[str, object],
    *,
    timeout: float,
    require_ready: bool = True,
) -> dict[str, object]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{CONTROL_PORT}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AgentLeaseError(f"EdgeAgent request failed ({exc.code}): {detail}") from exc
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise AgentLeaseError(f"EdgeAgent request failed: {exc}") from exc
    if not isinstance(value, dict) or (
        require_ready and value.get("ready") is not True
    ):
        raise AgentLeaseError(f"EdgeAgent request did not become ready: {value}")
    return value


def acquire_character(project_dir: Path, owner_pid: int) -> dict[str, object]:
    settings = load_settings(project_dir).copilot
    # A lease asks the service owner to load the requested model. Requiring
    # its previous model to be healthy first would prevent crash recovery.
    ensure_service(require_ready=False)
    return post_json(
        "/character",
        {
            "owner_pid": owner_pid,
            "character": {
                "model": settings.llm_model,
                "lora": settings.character_lora,
                "port": settings.llama_port,
                # Requested prompt limit while borrowing idle inference;
                # no permanent KV reservation or model ownership.
                "context_size": settings.llm_context_size,
            },
        },
        timeout=360,
    )


def release_character(owner_pid: int) -> dict[str, object]:
    return post_json("/base", {"owner_pid": owner_pid}, timeout=360)


def hold_restart_handoff() -> dict[str, object]:
    return post_json("/handoff", {}, timeout=5)


class CharacterLease:
    """Maintain an HTTP lease without owning the model or the speech gateway."""

    def __init__(
        self,
        project_dir: Path,
        owner_pid: int,
        on_connected: Callable[[dict[str, object]], None],
    ) -> None:
        self._project_dir = project_dir
        self._owner_pid = owner_pid
        self._on_connected = on_connected
        self._ready = asyncio.Event()
        self._closed = threading.Event()
        self._task: asyncio.Task[None] | None = None
        self.owned = False

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._closed = threading.Event()
            self._task = asyncio.create_task(self._maintain(), name="character-lease")
        await self._ready.wait()

    def _acquire(self, closed: threading.Event) -> dict[str, object]:
        lease = acquire_character(self._project_dir, self._owner_pid)
        # Cancelling an asyncio waiter cannot stop its HTTP thread. A response
        # arriving after shutdown must return that lease instead of orphaning it.
        if closed.is_set():
            release_character(self._owner_pid)
            raise AgentLeaseError("Character lease closed")
        return lease

    async def _maintain(self) -> None:
        delay = _LEASE_RETRY_SECONDS
        while not self._closed.is_set():
            try:
                if not self._ready.is_set():
                    lease = await asyncio.to_thread(self._acquire, self._closed)
                    self.owned = True
                    self._on_connected(lease)
                    self._ready.set()
                    delay = _LEASE_RETRY_SECONDS
                    _LOG.info("character_lease_connected")
                await asyncio.sleep(_LEASE_CHECK_SECONDS)
                status = await asyncio.to_thread(service_status)
                if (
                    status is None
                    or status.get("ready") is not True
                    or status.get("mode") != "character"
                    or status.get("owner_pid") != self._owner_pid
                ):
                    self._ready.clear()
                    _LOG.warning("character_lease_disconnected")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._ready.clear()
                _LOG.warning(
                    "character_lease_retry error_type=%s delay_seconds=%.1f",
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(30.0, delay * 2)

    async def stop(self) -> None:
        self._closed.set()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._ready.clear()
        if self.owned:
            try:
                await asyncio.to_thread(release_character, self._owner_pid)
            except AgentLeaseError:
                _LOG.warning("agent_lease_return_failed")
            finally:
                self.owned = False
