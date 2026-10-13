"""The model server the character evals ask: EdgeAgent's own server
arguments (the product's), on the dev box's CUDA build, optionally with the
adapter the product would load. Ready when it says it is listening
(serve_wait.py)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path.home() / "EdgeAgent"))

from edge_agent.runtime import build_server_args  # noqa: E402
from serve_wait import start  # noqa: E402  (scripts/dev)

SERVER = PROJECT_DIR / ".runtime/tools/llama.cpp-b11193-src/build-cuda/bin/llama-server"
MODEL = PROJECT_DIR / ".runtime/models/llm/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"


def serve(model: Path, port: int, lora: Path | None = None) -> subprocess.Popen:
    args = build_server_args(str(SERVER), model, port=port, context_size=8192, threads=8,
                             gpu_layers=99, low_vram=True, lora_paths=[lora] if lora else (), slots=1)
    return start(args, timeout=600)
