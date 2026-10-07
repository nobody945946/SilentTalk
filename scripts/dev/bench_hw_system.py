"""The machine bench_hw.py runs on (OS, CPU, GPU through nvidia-smi), and
BenchError, how a stage says it cannot be measured here."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class BenchError(RuntimeError):
    pass


def print_system(rows: list[tuple[str, str]]) -> None:
    rows.append(("OS", f"{platform.system()} {platform.release()}"))
    rows.append(
        ("CPU", f"{platform.processor() or platform.machine()} x{os.cpu_count()}")
    )
    smi = nvidia_smi("name,memory.total,memory.used,power.limit,clocks.max.sm")
    rows.append(("GPU (nvidia-smi)", smi or "沒有 nvidia-smi"))


def nvidia_smi(fields: str) -> str:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return ""
    try:
        out = subprocess.run(
            [exe, f"--query-gpu={fields}", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""


def gpu_memory_used() -> int | None:
    value = nvidia_smi("memory.used").split(" ")[0]
    return int(value) if value.isdigit() else None
