from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from silenttalk.config import load_settings
from silenttalk.copilot.llm import find_llama_server
from silenttalk.edge_ai import (
    CONTROL_PORT,
    GENERAL_CONTEXT_SIZE,
    GENERAL_PORT,
    build_server_args,
)


def _health_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=1
        ) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        query = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(query, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class EdgeAIManager:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.lock = threading.RLock()
        self.process: subprocess.Popen[bytes] | None = None
        self.mode = "starting"
        self.port = GENERAL_PORT
        self.owner_pid: int | None = None
        self.owner_dead_since: float | None = None
        self.handoff_until = 0.0
        self.error = ""
        self.loading = False

    def status(self) -> dict[str, object]:
        # Never wait behind a 10-second model load. The control plane must stay
        # observable during transitions or another caller may mistake it for a
        # missing service and try to start a duplicate.
        loading = self.loading
        process = self.process
        mode = self.mode
        port = self.port
        owner_pid = self.owner_pid
        error = self.error
        ready = (
            not loading
            and process is not None
            and process.poll() is None
            and _health_ok(port)
        )
        return {
            "mode": mode,
            "ready": ready,
            "port": port,
            "url": f"http://127.0.0.1:{port}",
            "owner_pid": owner_pid,
            "error": error,
        }

    def switch(self, mode: str, owner_pid: int | None = None) -> dict[str, object]:
        with self.lock:
            if mode == "base" and self.mode == "character":
                if self.owner_pid is not None and _pid_alive(self.owner_pid):
                    if owner_pid != self.owner_pid:
                        raise PermissionError("SilentTalk still owns character mode")
            if (
                mode == self.mode
                and self.process is not None
                and self.process.poll() is None
                and _health_ok(self.port)
            ):
                if mode == "character" and owner_pid is not None:
                    self.owner_pid = owner_pid
                    self.owner_dead_since = None
                    self.handoff_until = 0.0
                return self.status()

            self.loading = True
            self.error = ""
            self._stop_child()
            try:
                self._start_child(mode, owner_pid)
            except Exception as exc:
                self.error = str(exc)
                self.loading = False
                if mode != "base":
                    try:
                        self._start_child("base", None)
                    except Exception as base_exc:
                        self.error += f"; base restore failed: {base_exc}"
                raise
            self.loading = False
            return self.status()

    def _start_child(self, mode: str, owner_pid: int | None) -> None:
        settings = load_settings(self.project_dir)
        config = settings.copilot
        model_path = (
            self.project_dir / ".runtime" / "models" / "llm" / config.llm_model
        )
        if not model_path.is_file():
            raise FileNotFoundError(model_path)
        lora_path: Path | None = None
        context_size = GENERAL_CONTEXT_SIZE
        port = GENERAL_PORT
        if mode == "character":
            port = config.llama_port
            context_size = config.llm_context_size
            candidate = (
                self.project_dir
                / ".runtime"
                / "models"
                / "llm"
                / config.character_lora
            )
            if config.character_lora and candidate.is_file():
                lora_path = candidate
        threads = max(2, min(6, (os.cpu_count() or 4) // 2))
        args = build_server_args(
            find_llama_server(),
            model_path,
            port=port,
            context_size=context_size,
            threads=threads,
            gpu_layers=config.llm_gpu_layers,
            low_vram=config.llm_low_vram,
            lora_path=lora_path,
        )
        self.process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.mode = mode
        self.port = port
        self.owner_pid = owner_pid if mode == "character" else None
        self.owner_dead_since = None
        if mode == "character":
            self.handoff_until = 0.0
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                code = self.process.returncode
                self.process = None
                raise RuntimeError(f"llama-server exited with {code}")
            if _health_ok(port):
                return
            time.sleep(0.25)
        self._stop_child()
        raise TimeoutError(f"llama-server on port {port} did not become ready")

    def _stop_child(self) -> None:
        process = self.process
        self.process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def monitor_owner(self) -> None:
        while True:
            time.sleep(1)
            with self.lock:
                dead = (
                    self.mode == "character"
                    and self.owner_pid is not None
                    and not _pid_alive(self.owner_pid)
                )
                if dead and self.owner_dead_since is None:
                    self.owner_dead_since = time.monotonic()
                elif not dead:
                    self.owner_dead_since = None
                stale = (
                    dead
                    and self.owner_dead_since is not None
                    and time.monotonic() - self.owner_dead_since >= 3
                    and time.monotonic() >= self.handoff_until
                )
                owner_pid = self.owner_pid
            if stale:
                try:
                    self.switch("base", owner_pid)
                except Exception:
                    time.sleep(2)

    def hold_handoff(self, seconds: float = 30.0) -> dict[str, object]:
        with self.lock:
            if self.mode == "character":
                self.handoff_until = time.monotonic() + seconds
            return self.status()


class Handler(BaseHTTPRequestHandler):
    manager: EdgeAIManager

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/status":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._json(HTTPStatus.OK, self.manager.status())

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            owner = payload.get("owner_pid")
            owner_pid = owner if isinstance(owner, int) else None
            if self.path == "/character":
                if owner_pid is None or not _pid_alive(owner_pid):
                    raise ValueError("live owner_pid required")
                result = self.manager.switch("character", owner_pid)
            elif self.path == "/handoff":
                result = self.manager.hold_handoff()
            elif self.path == "/base":
                result = self.manager.switch("base", owner_pid)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
        except PermissionError as exc:
            self._json(HTTPStatus.CONFLICT, {"error": str(exc), "ready": False})
            return
        except Exception as exc:
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": str(exc), "ready": False},
            )
            return
        self._json(HTTPStatus.OK, result)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ExclusiveHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self) -> None:
        # SO_EXCLUSIVEADDRUSE is the Windows single-instance gate. Without it,
        # two Python servers can both LISTEN on one localhost port.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", type=Path, required=True)
    args = parser.parse_args()
    manager = EdgeAIManager(args.project_dir.resolve())
    Handler.manager = manager
    server = ExclusiveHTTPServer(("127.0.0.1", CONTROL_PORT), Handler)
    threading.Thread(target=manager.monitor_owner, name="edge-ai-owner", daemon=True).start()
    threading.Thread(
        target=lambda: manager.switch("base"),
        name="edge-ai-bootstrap",
        daemon=True,
    ).start()
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        manager._stop_child()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
