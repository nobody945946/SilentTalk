from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from e4b_core import api as core_api
from e4b_core import runtime as core_runtime
from e4b_core import service as core_service
from silenttalk import edge_ai as edge_client
from silenttalk.copilot import llm
from silenttalk.copilot.llm import LocalReplyModel


def _value_after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def test_base_server_is_one_full_speed_96k_slot() -> None:
    args = core_runtime.build_server_args(
        "llama-server",
        Path("e4b.gguf"),
        port=core_runtime.GENERAL_PORT,
        context_size=core_runtime.GENERAL_CONTEXT_SIZE,
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
    args = core_runtime.build_server_args(
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


def test_silenttalk_sends_character_configuration_through_core_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = SimpleNamespace(
        llm_model="e4b.gguf",
        character_lora="character.gguf",
        llama_port=18088,
        llm_context_size=32768,
        llm_gpu_layers=99,
        llm_low_vram=True,
    )
    calls: list[tuple[str, dict[str, object], float]] = []
    monkeypatch.setattr(
        edge_client,
        "load_settings",
        lambda project_dir: SimpleNamespace(copilot=config),
    )
    monkeypatch.setattr(edge_client, "ensure_service", lambda project_dir: {})
    monkeypatch.setattr(
        edge_client,
        "post_json",
        lambda path, payload, timeout: calls.append((path, payload, timeout)) or {},
    )

    edge_client.acquire_character(tmp_path, 456)

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
                    "gpu_layers": 99,
                    "low_vram": True,
                },
            },
            120,
        )
    ]


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
    manager = core_service.E4BCore(tmp_path)
    manager.mode = "character"
    manager.owner_pid = 123
    monkeypatch.setattr(core_service, "_pid_alive", lambda pid: True)

    with pytest.raises(PermissionError):
        manager.switch("base")


def test_new_silenttalk_instance_takes_over_without_reloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Running:
        def poll(self) -> None:
            return None

    manager = core_service.E4BCore(tmp_path)
    manager.mode = "character"
    manager.port = 18088
    manager.owner_pid = 123
    manager.process = Running()  # type: ignore[assignment]
    monkeypatch.setattr(core_service, "_health_ok", lambda port: True)

    status = manager.switch("character", 456)

    assert manager.owner_pid == 456
    assert status["ready"] is True


def test_slow_status_never_spawns_a_second_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    statuses = iter([None, {"mode": "starting", "ready": True}])
    monkeypatch.setattr(core_api, "service_status", lambda timeout=1.0: next(statuses))
    monkeypatch.setattr(core_api, "control_service_present", lambda: True)

    def duplicate(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not spawn a duplicate manager")

    monkeypatch.setattr(core_api.subprocess, "Popen", duplicate)

    assert core_api.ensure_service(tmp_path)["ready"] is True


def test_restart_handoff_temporarily_suspends_crash_restore(tmp_path: Path) -> None:
    manager = core_service.E4BCore(tmp_path)
    manager.mode = "character"

    manager.hold_handoff()

    assert manager.handoff_until > 0


def test_stop_refuses_to_break_a_live_silenttalk_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = core_service.E4BCore(tmp_path)
    manager.mode = "character"
    manager.owner_pid = 123
    monkeypatch.setattr(core_service, "_pid_alive", lambda pid: True)

    with pytest.raises(PermissionError):
        manager.stop_service()


def test_stop_releases_the_base_server(tmp_path: Path) -> None:
    class Running:
        returncode = 0

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    manager = core_service.E4BCore(tmp_path)
    manager.mode = "base"
    manager.process = Running()  # type: ignore[assignment]

    status = manager.stop_service()

    assert manager.process is None
    assert status["mode"] == "stopped"
    assert status["ready"] is False


def test_core_identifies_the_exact_listener_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = SimpleNamespace(
        stdout=(
            b"  TCP    127.0.0.1:18087    0.0.0.0:0    LISTENING    111\r\n"
            b"  TCP    127.0.0.1:18089    0.0.0.0:0    LISTENING    222\r\n"
        )
    )
    monkeypatch.setattr(core_service.subprocess, "run", lambda *args, **kwargs: listing)

    assert core_service._listening_pid(18089) == 222


def test_core_never_kills_a_non_llama_process_on_its_reserved_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(core_service, "_listening_pid", lambda port: 321)
    monkeypatch.setattr(
        core_service, "_process_image", lambda pid: Path("C:/Windows/other.exe")
    )

    with pytest.raises(RuntimeError, match="occupied by PID 321"):
        core_service._clear_reserved_port(18089)
