"""How fast is character mode on *this* machine? One command, about 2 minutes.

    .venv\\Scripts\\python.exe scripts\\dev\\bench_hw.py        (Windows)
    .venv/bin/python scripts/dev/bench_hw.py                  (Linux)

Measures each stage between "someone stopped talking" and "the bot starts
speaking", with the same llama-server flags the app uses:

  - LLM: deciding whether to speak (1 token), old prompt format vs the
    append-only chat format, and reply generation speed
  - STT: Paraformer decode speed and the finalize step after a line ends
  - TTS: EdgeTTS time to first audio and to the whole line (needs internet)

Self-contained on purpose: neither it nor its bench_hw_* modules import
silenttalk, so it runs on an older install as long as .venv, llama-server
and the models are there. All
text is a fixed synthetic chat; nothing is written to disk except a
temporary TTS clip that is deleted right away.

Paste the table it prints at the end back to whoever asked for it.
"""

from __future__ import annotations

import argparse
import sys

from bench_hw_chat import CHAT
from bench_hw_llm import bench_llm
from bench_hw_speech import bench_stt, synth_clip
from bench_hw_system import BenchError, gpu_memory_used, print_system


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--model",
        default="gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf",
        help="file name in EDGE_AGENT_MODEL_DIR or a path",
    )
    parser.add_argument("--gpu-layers", type=int, default=99, help="0 = CPU only")
    parser.add_argument(
        "--context-size",
        type=int,
        default=32768,
        help="context tokens per llama-server slot (default: 32768)",
    )
    parser.add_argument(
        "--history-turns",
        type=int,
        default=len(CHAT),
        help="synthetic chat turns sent before the timed tail (default: 16)",
    )
    parser.add_argument(
        "--lora",
        help="adapter (file in EDGE_AGENT_MODEL_DIR or a path): time the app's LoRA gate + reply",
    )
    parser.add_argument(
        "--lora-uses",
        default="called",
        help='with --lora: as copilot.character_lora_uses; "line" in it times the reply with the adapter too',
    )
    parser.add_argument("--skip-tts", action="store_true", help="no internet")
    parser.add_argument("--llama-server", help="path to llama-server(.exe)")
    args = parser.parse_args()
    if args.context_size < 1024:
        parser.error("--context-size must be at least 1024")
    if args.history_turns < 10:
        parser.error("--history-turns must be at least 10")
    # Redirected output on a zh-TW Windows is cp950, which has no Simplified
    # characters; the STT line would crash the whole report.
    sys.stdout.reconfigure(errors="replace")

    rows: list[tuple[str, str]] = []
    print_system(rows)
    gpu_before = gpu_memory_used()
    try:
        bench_llm(args, rows, gpu_before)
    except BenchError as exc:
        rows.append(("LLM", f"失敗：{exc}"))
    try:
        bench_stt(rows, None if args.skip_tts else synth_clip(rows))
    except BenchError as exc:
        rows.append(("STT", f"失敗：{exc}"))

    print("\n==== 貼這張表回來 ====")
    for name, value in rows:
        print(f"{name}：{value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
