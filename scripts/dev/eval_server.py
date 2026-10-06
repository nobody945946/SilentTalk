"""The model server the character evals ask: EdgeAgent's own server
arguments (the product's), on the dev box's CUDA build, optionally with the
adapter the product would load."""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path.home() / "EdgeAgent"))

from edge_agent.runtime import build_server_args  # noqa: E402

SERVER = PROJECT_DIR / ".runtime/tools/llama.cpp-b11193-src/build-cuda/bin/llama-server"
MODEL = PROJECT_DIR / ".runtime/models/llm/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"


def serve(model: Path, port: int, lora: Path | None = None) -> subprocess.Popen:
    args = build_server_args(str(SERVER), model, port=port, context_size=8192, threads=8,
                             gpu_layers=99, low_vram=True, lora_path=lora, slots=1)
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(600):
        if process.poll() is not None:
            raise SystemExit("llama-server exited while loading")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2):
                return process
        except OSError:
            time.sleep(1)
    process.terminate()
    raise SystemExit("llama-server did not become ready")
