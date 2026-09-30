from __future__ import annotations

import os
from pathlib import Path

import pytest

from silenttalk import edge_ai, edge_service
from silenttalk.copilot import llm
from silenttalk.copilot.llm import LocalReplyModel


def _value_after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def test_base_server_is_one_full_speed_96k_slot() -> None:
    args = edge_ai.build_server_args(
        "llama-server",
        Path("e4b.gguf"),
        port=edge_ai.GENERAL_PORT,
        context_size=edge_ai.GENERAL_CONTEXT_SIZE,
        threads=4,
        gpu_layers=99,
        low_vram=True,
    )

    assert _value_after(args, "--port") == "18089"
    assert _value_after(args, "--ctx-size") == "98304"
    assert _value_after(args, "--parallel") == "1"
    assert "--lora" not in args
    assert _value_after(args, "--cache-type-k") == "q8_0"
    assert _value_after(args, "--cache-type-v") == "q8_0"


def test_character_server_gets_two_32k_slots_and_the_lora() -> None:
    args = edge_ai.build_server_args(
        "llama-server",
        Path("e4b.gguf"),
        port=18088,
        context_size=32_768,
        threads=4,
        gpu_layers=99,
        low_vram=True,
        lora_path=Path("character.gguf"),
    )

    assert _value_after(args, "--ctx-size") == "65536"
    assert _value_after(args, "--parallel") == "2"
    assert _value_after(args, "--lora") == "character.gguf"


@pytest.mark.asyncio
async def test_silenttalk_borrows_and_releases_the_independent_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_path = tmp_path / "e4b.gguf"
    lora_path = tmp_path / "character.gguf"
    model_path.write_bytes(b"model")
    lora_path.write_bytes(b"lora")
    calls: list[tuple[str, int]] = []

    monkeypatch.setattr(
        llm,
        "acquire_character",
        lambda project_dir, owner_pid: calls.append(("acquire", owner_pid)),
    )
    monkeypatch.setattr(
        llm,
        "release_character",
        lambda owner_pid: calls.append(("release", owner_pid)),
    )
    model = LocalReplyModel(
        model_path,
        lora_path=lora_path,
        project_dir=tmp_path,
        managed_service=True,
    )

    await model.start()
    assert model._lora_loaded is True
    await model.stop()

    assert calls == [("acquire", os.getpid()), ("release", os.getpid())]
    assert model._lora_loaded is False


def test_general_entry_cannot_steal_a_live_silenttalk_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = edge_service.EdgeAIManager(tmp_path)
    manager.mode = "character"
    manager.owner_pid = 123
    monkeypatch.setattr(edge_service, "_pid_alive", lambda pid: True)

    with pytest.raises(PermissionError):
        manager.switch("base")


def test_new_silenttalk_instance_takes_over_without_reloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Running:
        def poll(self) -> None:
            return None

    manager = edge_service.EdgeAIManager(tmp_path)
    manager.mode = "character"
    manager.port = 18088
    manager.owner_pid = 123
    manager.process = Running()  # type: ignore[assignment]
    monkeypatch.setattr(edge_service, "_health_ok", lambda port: True)

    status = manager.switch("character", 456)

    assert manager.owner_pid == 456
    assert status["ready"] is True


def test_slow_status_never_spawns_a_second_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    statuses = iter([None, {"mode": "starting", "ready": True}])
    monkeypatch.setattr(edge_ai, "service_status", lambda timeout=1.0: next(statuses))
    monkeypatch.setattr(edge_ai, "control_service_present", lambda: True)

    def duplicate(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not spawn a duplicate manager")

    monkeypatch.setattr(edge_ai.subprocess, "Popen", duplicate)

    assert edge_ai.ensure_service(tmp_path)["ready"] is True


def test_restart_handoff_temporarily_suspends_crash_restore(tmp_path: Path) -> None:
    manager = edge_service.EdgeAIManager(tmp_path)
    manager.mode = "character"

    manager.hold_handoff()

    assert manager.handoff_until > 0
