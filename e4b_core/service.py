from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from e4b_core.chat import NativeChat
from e4b_core.runtime import (
    CONTROL_PORT,
    DEFAULT_MODEL,
    GENERAL_CONTEXT_SIZE,
    GENERAL_PORT,
    build_server_args,
    find_llama_server,
)
from e4b_core.web import NATIVE_CHAT_HTML


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

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _listening_pid(port: int) -> int | None:
    """Return the exact Windows PID listening on a reserved core port."""
    if os.name != "nt":
        return None
    listing = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        check=False,
        timeout=5,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = listing.stdout.decode(errors="replace")
    endpoint = re.compile(rf"^(?:\[.*\]|[^:]+):{port}$")
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 5 and endpoint.match(fields[1]) and fields[-1].isdigit():
            return int(fields[-1])
    return None


def _process_image(pid: int) -> Path | None:
    if os.name != "nt":
        return None
    import ctypes

    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        size = ctypes.c_ulong(32_768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not ctypes.windll.kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return None
        return Path(buffer.value)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _clear_reserved_port(port: int) -> None:
    """Recover only an orphaned llama-server on an E4B-owned model port."""
    pid = _listening_pid(port)
    if pid is None:
        return
    image = _process_image(pid)
    if image is None or image.name.lower() != "llama-server.exe":
        raise RuntimeError(f"reserved E4B port {port} is occupied by PID {pid}")
    import ctypes

    terminate = 0x0001
    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(terminate | synchronize, False, pid)
    if not handle:
        raise RuntimeError(f"cannot recover orphaned llama-server PID {pid}")
    try:
        if not ctypes.windll.kernel32.TerminateProcess(handle, 1):
            raise RuntimeError(f"cannot terminate orphaned llama-server PID {pid}")
        ctypes.windll.kernel32.WaitForSingleObject(handle, 5_000)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    if _listening_pid(port) is not None:
        raise RuntimeError(
            f"orphaned llama-server PID {pid} did not release port {port}"
        )


class E4BCore:
    """Owns the model process; applications can only lease it through HTTP."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.model_dir = (project_dir / ".runtime" / "models" / "llm").resolve()
        self.lock = threading.RLock()
        self.process: subprocess.Popen[bytes] | None = None
        self.mode = "starting"
        self.port = GENERAL_PORT
        self.owner_pid: int | None = None
        self.owner_dead_since: float | None = None
        self.handoff_until = 0.0
        self.error = ""
        self.loading = False
        self.chat = NativeChat(model_port=GENERAL_PORT)

    def status(self) -> dict[str, object]:
        process = self.process
        ready = (
            not self.loading
            and process is not None
            and process.poll() is None
            and _health_ok(self.port)
        )
        return {
            "service": "e4b-core",
            "mode": self.mode,
            "ready": ready,
            "port": self.port,
            "url": f"http://127.0.0.1:{CONTROL_PORT}/",
            "model_url": f"http://127.0.0.1:{self.port}",
            "owner_pid": self.owner_pid,
            "error": self.error,
        }

    def switch(
        self,
        mode: str,
        owner_pid: int | None = None,
        character: dict[str, object] | None = None,
    ) -> dict[str, object]:
        with self.lock:
            if (
                mode == "base"
                and self.mode == "character"
                and self.owner_pid is not None
                and _pid_alive(self.owner_pid)
                and owner_pid != self.owner_pid
            ):
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
                self._start_child(mode, owner_pid, character)
            except Exception as exc:
                self.error = str(exc)
                self.loading = False
                if mode != "base":
                    try:
                        self._start_child("base", None, None)
                    except Exception as base_exc:  # noqa: BLE001 - preserve first failure
                        self.error += f"; base restore failed: {base_exc}"
                raise
            self.loading = False
            return self.status()

    def _start_child(
        self,
        mode: str,
        owner_pid: int | None,
        character: dict[str, object] | None,
    ) -> None:
        if mode == "base":
            model_path = self._model_path(DEFAULT_MODEL)
            lora_path = None
            context_size = GENERAL_CONTEXT_SIZE
            port = GENERAL_PORT
            gpu_layers = 99
            low_vram = True
        elif mode == "character":
            if character is None:
                raise ValueError("character configuration required")
            model_path = self._model_path(self._required_string(character, "model"))
            lora_name = self._required_string(character, "lora")
            lora_path = self._model_path(lora_name) if lora_name else None
            context_size = self._bounded_int(character, "context_size", 1_024, 32_768)
            port = self._bounded_int(character, "port", 1_024, 65_535)
            if port in (CONTROL_PORT, GENERAL_PORT):
                raise ValueError("character port conflicts with E4B core")
            gpu_layers = self._bounded_int(character, "gpu_layers", 0, 999)
            low_vram = character.get("low_vram") is True
        else:
            raise ValueError(f"unknown E4B core mode: {mode}")

        threads = max(2, min(6, (os.cpu_count() or 4) // 2))
        _clear_reserved_port(port)
        args = build_server_args(
            find_llama_server(),
            model_path,
            port=port,
            context_size=context_size,
            threads=threads,
            gpu_layers=gpu_layers,
            low_vram=low_vram,
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
            if _health_ok(port) and (
                os.name != "nt" or _listening_pid(port) == self.process.pid
            ):
                return
            time.sleep(0.25)
        self._stop_child()
        raise TimeoutError(f"llama-server on port {port} did not become ready")

    def _model_path(self, filename: str) -> Path:
        if (
            not filename
            or Path(filename).name != filename
            or not filename.endswith(".gguf")
        ):
            raise ValueError("model must be a .gguf filename")
        path = (self.model_dir / filename).resolve()
        if path.parent != self.model_dir or not path.is_file():
            raise FileNotFoundError(path)
        return path

    @staticmethod
    def _required_string(payload: dict[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str):
            raise TypeError(f"{key} must be a string")
        return value

    @staticmethod
    def _bounded_int(
        payload: dict[str, object], key: str, minimum: int, maximum: int
    ) -> int:
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{key} must be an integer")
        if not minimum <= value <= maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}")
        return value

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
                except (OSError, RuntimeError, ValueError):
                    time.sleep(2)

    def hold_handoff(self, seconds: float = 30.0) -> dict[str, object]:
        with self.lock:
            if self.mode == "character":
                self.handoff_until = time.monotonic() + seconds
            return self.status()

    def stop_service(self) -> dict[str, object]:
        with self.lock:
            if (
                self.mode == "character"
                and self.owner_pid is not None
                and _pid_alive(self.owner_pid)
            ):
                raise PermissionError("SilentTalk still owns character mode")
            self.loading = True
            self._stop_child()
            self.mode = "stopped"
            self.port = GENERAL_PORT
            self.owner_pid = None
            self.owner_dead_since = None
            self.handoff_until = 0.0
            self.loading = False
            return self.status()


class Handler(BaseHTTPRequestHandler):
    core: E4BCore

    def do_GET(self) -> None:
        if self.path == "/status":
            self._json(HTTPStatus.OK, self.core.status())
        elif self.path in ("/", "/index.html"):
            self._html(NATIVE_CHAT_HTML)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            payload = self._payload()
            if self.path == "/chat":
                self._chat(payload)
                return
            if self.path == "/chat/reset":
                session_id = self._session_id(payload)
                self.core.chat.reset(session_id)
                self._json(HTTPStatus.OK, {"reset": True})
                return
            stop_control_server = False
            owner = payload.get("owner_pid")
            owner_pid = (
                owner
                if isinstance(owner, int) and not isinstance(owner, bool)
                else None
            )
            if self.path == "/character":
                if owner_pid is None or not _pid_alive(owner_pid):
                    raise ValueError("live owner_pid required")
                character = payload.get("character")
                if not isinstance(character, dict):
                    raise ValueError("character configuration required")
                result = self.core.switch("character", owner_pid, character)
            elif self.path == "/handoff":
                result = self.core.hold_handoff()
            elif self.path == "/base":
                result = self.core.switch("base", owner_pid)
            elif self.path == "/shutdown":
                result = self.core.stop_service()
                stop_control_server = True
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
        except PermissionError as exc:
            self._json(HTTPStatus.CONFLICT, {"error": str(exc), "ready": False})
            return
        except (TypeError, ValueError, FileNotFoundError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc), "ready": False})
            return
        except Exception as exc:  # noqa: BLE001 - HTTP boundary must return JSON
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": str(exc), "ready": False},
            )
            return
        self._json(HTTPStatus.OK, result)
        if stop_control_server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _chat(self, payload: dict[str, object]) -> None:
        session_id = self._session_id(payload)
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("non-empty text required")
        if len(text) > 250_000:
            raise ValueError("message is too long")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            with self.core.lock:
                status = self.core.status()
                if status["mode"] != "base" or status["ready"] is not True:
                    raise RuntimeError("E4B core is currently leased by SilentTalk")
                for event, data in self.core.chat.stream_reply(
                    session_id, text.strip()
                ):
                    self._event(event, data)
        except Exception as exc:  # noqa: BLE001 - stream errors must reach the browser
            self._event("error", {"message": str(exc)})

    def _event(self, event: str, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        body = f"event: {event}\ndata: {data}\n\n".encode()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def _payload(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("request is too large")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise TypeError("JSON object required")
        return value

    @staticmethod
    def _session_id(payload: dict[str, object]) -> str:
        value = payload.get("session_id")
        if not isinstance(value, str) or not 8 <= len(value) <= 100:
            raise ValueError("valid session_id required")
        return value

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, value: str) -> None:
        body = value.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ExclusiveHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", type=Path, required=True)
    args = parser.parse_args()
    core = E4BCore(args.project_dir.resolve())
    Handler.core = core
    server = ExclusiveHTTPServer(("127.0.0.1", CONTROL_PORT), Handler)
    threading.Thread(target=core.monitor_owner, name="e4b-owner", daemon=True).start()
    threading.Thread(
        target=lambda: core.switch("base"), name="e4b-bootstrap", daemon=True
    ).start()
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        core._stop_child()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
