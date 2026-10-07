"""The reply model under test (turn_eval.py): the copilot code at a pinned
revision or the working tree, built with the app's [copilot] settings, and
the llama-server EdgeAgent would lease it from, played on the dev box."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
import tomllib
import types
import urllib.request
from pathlib import Path
from typing import Any

import turn_eval_set
from turn_eval_set import PROJECT_DIR, agent_persona

EDGE_AGENT_MODEL_DIR = Path(
    os.environ.get("EDGE_AGENT_MODEL_DIR", Path.home() / "EdgeAgent" / "models")
)
EDGE_AGENT_ROOT = Path(os.environ.get("EDGE_AGENT_ROOT", Path.home() / "EdgeAgent"))
EVAL_SERVER = PROJECT_DIR / ".runtime/tools/llama.cpp-b11193-src/build-cuda/bin/llama-server"
# Last commit with the old character path (keyword gate + character_reply),
# before llm.py / runtime.py / character.py / context.py were rewritten.
OLD_REV = "5924fd083cea63c4e15fd48421eddd7b51ac1169"

# Production defaults for [copilot] (CopilotConfig at OLD_REV); config.toml wins.
COPILOT_DEFAULTS: dict[str, Any] = {
    "llm_context_size": 4096,
    "recent_turns": 16,
    "max_session_turns": 100,
    "context_char_budget": 2400,
    "max_reply_chars": 72,
    "llm_model": "gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf",
    "compact_context": True,
    "compact_keep_turns": 20,
    "compact_batch_turns": 12,
    "character_ai_honesty": "in_character",
    "character_follow_up_seconds": 20.0,
    "character_cooldown_seconds": 8.0,
    "character_turn_gap": 3,
}

# Set by turn_eval.py (and options_eval.py) from their flags; read through
# this module (turn_eval_model.MEMORY), so the value set is the one read.
EVAL_PORT = 18411
# --cpu: no GPU layers, for when a training run holds the GPU.
# Decisions and lines compare fine; latencies do not.
CPU_ONLY = False
# --memory: character_memory for the new policy.
MEMORY: str | None = None
# --lora-uses: which requests the adapter is applied to.
LORA_USES: tuple[str, ...] | None = None


def load_old_modules(rev: str) -> types.SimpleNamespace:
    """The copilot modules as of `rev`, imported under a private package name so
    the working tree (being rewritten) cannot change the baseline. "worktree"
    imports silenttalk.copilot as it is on disk instead."""
    if rev == "worktree":
        from silenttalk.copilot import character, context, llm, persona
        from silenttalk.copilot import types as ctypes
        return types.SimpleNamespace(
            character=character, context=context, llm=llm, persona=persona, types=ctypes
        )
    package = "_turn_eval_old"
    if package in sys.modules:
        mod = sys.modules[package]
        return types.SimpleNamespace(**{n: getattr(mod, n) for n in
                                        ("character", "context", "llm", "persona", "types")})
    root = types.ModuleType(package)
    root.__path__ = []  # type: ignore[attr-defined]
    sys.modules[package] = root
    names = ("types", "script", "persona", "character", "context", "llm")
    for name in names:
        source = subprocess.run(
            ["git", "show", f"{rev}:silenttalk/copilot/{name}.py"],
            cwd=PROJECT_DIR, capture_output=True, text=True, check=True,
        ).stdout
        for other in names:
            source = source.replace(f"silenttalk.copilot.{other}", f"{package}.{other}")
        spec = importlib.util.spec_from_loader(f"{package}.{name}", loader=None)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        module.__file__ = f"<{rev[:10]}:silenttalk/copilot/{name}.py>"
        sys.modules[f"{package}.{name}"] = module
        exec(compile(source, module.__file__, "exec"), module.__dict__)  # noqa: S102
        setattr(root, name, module)
    return types.SimpleNamespace(**{n: getattr(root, n) for n in
                                    ("character", "context", "llm", "persona", "types")})


def copilot_config() -> dict[str, Any]:
    values = dict(COPILOT_DEFAULTS)
    config_path = PROJECT_DIR / "config.toml"
    if config_path.exists():
        with config_path.open("rb") as handle:
            values.update(tomllib.load(handle).get("copilot", {}))
    return values


def ensure_llama_server_on_path() -> None:
    if shutil.which("llama-server"):
        return
    tools = sorted((PROJECT_DIR / ".runtime" / "tools").glob("llama-b*"))
    if tools:
        os.environ["PATH"] = f"{tools[-1]}{os.pathsep}{os.environ.get('PATH', '')}"
        os.environ["LD_LIBRARY_PATH"] = f"{tools[-1]}{os.pathsep}{os.environ.get('LD_LIBRARY_PATH', '')}"


def make_model(
    llm_module: Any, model_path: Path, config: dict[str, Any], lora: Path | None = None
) -> Any:
    extra: dict[str, Any] = {"lora_path": lora} if lora is not None else {}
    if lora is not None and LORA_USES is not None:
        extra["lora_uses"] = LORA_USES
    if MEMORY is not None:
        extra["memory"] = MEMORY
    honesty = str(config["character_ai_honesty"])
    if agent_persona():
        extra |= {"agent_dispatch": True, "owner_name": turn_eval_set.OWNER_NAME}
        honesty = "machine"
    return llm_module.LocalReplyModel(
        model_path,
        **extra,
        port=EVAL_PORT,
        context_size=int(config["llm_context_size"]),
        max_reply_chars=int(config["max_reply_chars"]),
        ai_honesty=honesty,
        # CPU-only prefill of a fresh persona prompt can pass the app's 15 s.
        request_timeout_seconds=180.0 if CPU_ONLY else 15.0,
    )


class LeaseStandIn:
    """Plays EdgeAgent's part on the dev box: SilentTalk leases its model from
    EdgeAgent, which does not run here. Starts llama-server with EdgeAgent's
    own character-lease arguments (runtime.build_server_args: two slots with
    an adapter) and points the product's lease calls at it."""

    def __init__(
        self,
        llm_module: Any,
        model_path: Path,
        lora: Path | None,
        config: dict[str, Any],
    ) -> None:
        sys.path.insert(0, str(EDGE_AGENT_ROOT))
        from edge_agent.runtime import build_server_args

        args = build_server_args(
            str(EVAL_SERVER),
            model_path,
            port=EVAL_PORT,
            context_size=int(config["llm_context_size"]),
            threads=8,
            gpu_layers=0 if CPU_ONLY else 99,
            low_vram=True,
            lora_paths=[lora] if lora is not None else (),
            slots=2 if lora is not None else 1,
        )
        self.process = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for _ in range(600):
            if self.process.poll() is not None:
                raise SystemExit("eval llama-server exited while loading")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{EVAL_PORT}/health", timeout=2
                ):
                    break
            except OSError:
                time.sleep(1)
        # Older baselines owned the lease calls in llm; current clients use
        # the independent HTTP lease owner. The fixture replaces that owner.
        transport_class = getattr(llm_module, "ReplyTransport", None)
        lease_class = (sys.modules[transport_class.__module__].CharacterLease if transport_class
                       else getattr(llm_module, "CharacterLease", None))
        lease_module = (
            sys.modules[lease_class.__module__] if lease_class else llm_module
        )
        lease_module.acquire_character = lambda *_args, **_kw: {"port": EVAL_PORT}
        lease_module.release_character = lambda *_args, **_kw: None
        if lease_class:
            lease_module.service_status = lambda: {
                "ready": self.process.poll() is None,
                "mode": "character",
                "owner_pid": os.getpid(),
            }

    def close(self) -> None:
        self.process.terminate()
        self.process.wait(timeout=60)
