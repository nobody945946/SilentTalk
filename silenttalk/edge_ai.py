from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


# Hardware-qualified defaults for the RTX 3050 Ti laptop.
GENERAL_CONTEXT_SIZE = 98_304
CONTROL_PORT = 18_087
GENERAL_PORT = 18_089


class EdgeAIError(RuntimeError):
    pass


def build_server_args(
    executable: str,
    model_path: Path,
    *,
    port: int,
    context_size: int,
    threads: int,
    gpu_layers: int,
    low_vram: bool,
    lora_path: Path | None = None,
) -> list[str]:
    """The single owner of llama-server flags for base and character modes."""
    slots = 2 if lora_path is not None else 1
    args = [
        executable,
        "--model",
        str(model_path),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--ctx-size",
        str(context_size * slots),
        "--threads",
        str(threads),
        "--n-gpu-layers",
        str(gpu_layers),
        "--parallel",
        str(slots),
        "--jinja",
    ]
    if lora_path is not None:
        args += ["--lora", str(lora_path)]
    if low_vram:
        args += [
            "--flash-attn",
            "on",
            "--cache-type-k",
            "q8_0",
            "--cache-type-v",
            "q8_0",
        ]
    return args


def service_status(timeout: float = 1.0) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{CONTROL_PORT}/status", timeout=timeout
        ) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    return value if isinstance(value, dict) else None


def control_service_present(timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", CONTROL_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_service(project_dir: Path, timeout: float = 120.0) -> dict[str, object]:
    status = service_status()
    # A model switch used to make /status slow enough that a caller spawned a
    # second manager. A listening control socket always means an existing
    # manager owns the GPU, even while its JSON status is momentarily pending.
    if status is None and not control_service_present():
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "silenttalk.edge_service",
                "--project-dir",
                str(project_dir),
            ],
            cwd=project_dir,
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
        if last is not None and last.get("ready") is True:
            return last
        if last is not None and last.get("error"):
            raise EdgeAIError(str(last["error"]))
        time.sleep(0.25)
    raise EdgeAIError(f"E4B service did not become ready: {last}")


def acquire_character(project_dir: Path, owner_pid: int) -> dict[str, object]:
    ensure_service(project_dir)
    return _post("/character", {"owner_pid": owner_pid}, timeout=120)


def release_character(owner_pid: int) -> dict[str, object]:
    return _post("/base", {"owner_pid": owner_pid}, timeout=120)


def request_base(project_dir: Path) -> dict[str, object]:
    status = ensure_service(project_dir)
    if status.get("mode") == "base":
        return status
    return _post("/base", {}, timeout=120)


def _post(path: str, payload: dict[str, object], *, timeout: float) -> dict[str, object]:
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
        raise EdgeAIError(f"E4B mode switch failed ({exc.code}): {detail}") from exc
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise EdgeAIError(f"E4B service request failed: {exc}") from exc
    if not isinstance(value, dict) or value.get("ready") is not True:
        raise EdgeAIError(f"E4B mode switch did not become ready: {value}")
    return value
