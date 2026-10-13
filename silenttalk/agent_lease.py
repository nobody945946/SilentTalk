from __future__ import annotations

import asyncio
import http.client
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
from collections.abc import Callable, Iterator
from pathlib import Path

from silenttalk.config import load_settings

# SilentTalk is an EdgeAgent API client. It never owns or launches llama-server.
CONTROL_PORT = 18_087
_LOG = logging.getLogger(__name__)
# The first wait after a failed attempt to take the lease; it doubles to 30 s.
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


def _launch_service() -> None:
    """Start EdgeAgent with its own launcher (`edge-agent start`) and wait for
    the launcher to exit: it returns once the service answers and its model
    has loaded or failed to (the status says which), within its own
    deadline."""
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
    ).wait()


def ensure_service(
    timeout: float = 360.0, *, require_ready: bool = True
) -> dict[str, object]:
    """EdgeAgent's status once its control service answers (started first if
    it is not running), and with `require_ready` once its model is ready.
    Waits on the launcher and on EdgeAgent's status stream: nothing asks on a
    timer."""
    if not _control_service_present():
        _launch_service()
    stream = StatusStream(time.monotonic() + timeout)
    last: dict[str, object] | None = None
    try:
        for last in stream:
            if not require_ready or last.get("ready") is True:
                return last
            if last.get("error"):
                raise AgentLeaseError(str(last["error"]))
    finally:
        stream.close()
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


class StatusStream:
    """EdgeAgent's status as it changes (GET /status/events, server-sent
    events): the current status at once, then one each time anything in it
    changes, whether the inference gateway would take a character request
    now among it. No heartbeat: on localhost a peer that dies closes the
    socket, which ends the stream. Reading blocks; close() from another
    thread ends it (the socket is shut down)."""

    def __init__(self, deadline: float | None = None) -> None:
        # time.monotonic() by which the next status must have come, or None.
        self._deadline = deadline
        self._lock = threading.Lock()
        self._socket: socket.socket | None = None
        self._closed = False

    def _timeout(self) -> float | None:
        if self._deadline is None:
            return None
        left = self._deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("no status from EdgeAgent in time")
        return left

    def __iter__(self) -> Iterator[dict[str, object]]:
        connection = http.client.HTTPConnection(
            "127.0.0.1", CONTROL_PORT, timeout=self._timeout()
        )
        try:
            connection.connect()
            with self._lock:
                if self._closed:
                    return
                # The socket itself: http.client drops the connection's
                # reference once a response owns it.
                sock = self._socket = connection.sock
            connection.request(
                "GET", "/status/events", headers={"Accept": "text/event-stream"}
            )
            response = connection.getresponse()
            if response.status != 200:
                raise AgentLeaseError(
                    f"EdgeAgent status stream failed (HTTP {response.status})"
                )
            while True:
                sock.settimeout(self._timeout())
                raw = response.readline()
                if not raw:
                    return  # EdgeAgent closed it: stopped or restarted
                line = raw.decode("utf-8").strip()
                if line.startswith("data:"):
                    status = json.loads(line[5:])
                    if isinstance(status, dict):
                        yield status
        except (OSError, http.client.HTTPException, ValueError) as exc:
            if not self._closed:
                raise AgentLeaseError(f"EdgeAgent status stream failed: {exc}") from exc
        finally:
            connection.close()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            sock = self._socket
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class CharacterLease:
    """The character's lease on EdgeAgent's model, without owning the model
    or the speech gateway. EdgeAgent owns that state: its status stream says
    whether the lease is still this process's and whether its gateway would
    take a character request now. This follows the stream (no timer) and
    takes the lease again when it is gone."""

    def __init__(
        self,
        project_dir: Path,
        owner_pid: int,
        on_connected: Callable[[dict[str, object]], None],
    ) -> None:
        self._project_dir = project_dir
        self._owner_pid = owner_pid
        self._on_connected = on_connected
        # Set while EdgeAgent's status shows the lease as this process's.
        self._held = asyncio.Event()
        # EdgeAgent's newest status while the lease is held, else None.
        self._status: dict[str, object] | None = None
        # Statuses received so far. A request notes it when it is sent
        # (InferenceDeferred.seen): its turn comes only with a later status.
        self.statuses_seen = 0
        self._news = asyncio.Condition()
        self._closed = threading.Event()
        self._stream: StatusStream | None = None
        self._task: asyncio.Task[None] | None = None
        self.owned = False

    async def start(self) -> None:
        """Until the lease is held."""
        if self._task is None or self._task.done():
            self._closed = threading.Event()
            self._task = asyncio.create_task(self._maintain(), name="character-lease")
        await self._held.wait()

    async def turn(self, seen: int) -> None:
        """Until EdgeAgent would take a character request again, after it
        turned one away (`seen`: statuses_seen when that request was sent).
        EdgeAgent sends a status after every refusal; the turn comes with a
        status after the request that shows the lease held, the model ready
        and the character admitted."""

        def admitted() -> bool:
            status = self._status
            return (
                self.statuses_seen > seen
                and status is not None
                and status.get("ready") is True
                and status.get("character_admitted") is True
            )

        async with self._news:
            await self._news.wait_for(admitted)

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
                lease = await asyncio.to_thread(self._acquire, self._closed)
                self.owned = True
                self._on_connected(lease)
                await self._follow()
                # Held, then gone (EdgeAgent restarted, or its mode or owner
                # changed): take it again at once.
                delay = _LEASE_RETRY_SECONDS
                _LOG.warning("character_lease_disconnected")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOG.warning(
                    "character_lease_retry error_type=%s delay_seconds=%.1f",
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(30.0, delay * 2)

    async def _follow(self) -> None:
        """EdgeAgent's status as it changes, until the lease is gone: a
        status names another mode or owner, or the stream ends. A lease that
        no status showed was never kept: an error."""
        loop = asyncio.get_running_loop()
        news: asyncio.Queue[dict[str, object] | AgentLeaseError | None] = (
            asyncio.Queue()
        )
        stream = self._stream = StatusStream()
        if self._closed.is_set():
            stream.close()

        def deliver(item: dict[str, object] | AgentLeaseError | None) -> None:
            try:
                loop.call_soon_threadsafe(news.put_nowait, item)
            except RuntimeError:
                pass  # the loop is closed: nobody waits for it

        def read() -> None:
            try:
                for status in stream:
                    deliver(status)
                deliver(None)
            except AgentLeaseError as exc:
                deliver(exc)

        # A daemon thread blocked on the stream never holds up the app's
        # exit; closing the stream ends it.
        threading.Thread(target=read, name="edge-agent-status", daemon=True).start()
        held = False
        try:
            while (status := await news.get()) is not None:
                if isinstance(status, AgentLeaseError):
                    raise status
                if (
                    status.get("mode") != "character"
                    or status.get("owner_pid") != self._owner_pid
                ):
                    if held:
                        return
                    raise AgentLeaseError("EdgeAgent did not keep the character lease")
                if not held:
                    held = True
                    self._held.set()
                    _LOG.info("character_lease_connected")
                async with self._news:
                    self._status = status
                    self.statuses_seen += 1
                    self._news.notify_all()
            if not held:
                raise AgentLeaseError("EdgeAgent closed its status stream")
        finally:
            stream.close()
            self._stream = None
            self._status = None
            self._held.clear()

    async def stop(self) -> None:
        self._closed.set()
        stream = self._stream
        if stream is not None:
            stream.close()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._held.clear()
        if self.owned:
            try:
                await asyncio.to_thread(release_character, self._owner_pid)
            except AgentLeaseError:
                _LOG.warning("agent_lease_return_failed")
            finally:
                self.owned = False
