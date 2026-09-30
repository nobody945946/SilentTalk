from __future__ import annotations

from pathlib import Path

from e4b_core.api import ensure_service, post_json
from e4b_core.runtime import E4BCoreError
from silenttalk.config import load_settings

# SilentTalk is an E4B Core API client. It never owns or launches llama-server.
EdgeAIError = E4BCoreError


def acquire_character(project_dir: Path, owner_pid: int) -> dict[str, object]:
    settings = load_settings(project_dir).copilot
    ensure_service(project_dir)
    return post_json(
        "/character",
        {
            "owner_pid": owner_pid,
            "character": {
                "model": settings.llm_model,
                "lora": settings.character_lora,
                "port": settings.llama_port,
                "context_size": settings.llm_context_size,
                "gpu_layers": settings.llm_gpu_layers,
                "low_vram": settings.llm_low_vram,
            },
        },
        timeout=120,
    )


def release_character(owner_pid: int) -> dict[str, object]:
    return post_json("/base", {"owner_pid": owner_pid}, timeout=120)


def hold_restart_handoff() -> dict[str, object]:
    return post_json("/handoff", {}, timeout=5)
