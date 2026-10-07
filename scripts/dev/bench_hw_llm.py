"""bench_hw.py's LLM stage: llama-server started with the app's flags, the
1-token speak-or-not decision in both prompt formats (or the app's LoRA gate
and reply), and generation speed."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import time
import urllib.request
from pathlib import Path

from bench_hw_chat import (
    CHAT,
    RECALL_MARKER,
    SYSTEM,
    TIMED_FROM,
    new_format_requests,
    old_format_requests,
    synthetic_chat,
)
from bench_hw_system import NO_WINDOW, BenchError, gpu_memory_used

EDGE_AGENT_MODEL_DIR = Path(
    os.environ.get("EDGE_AGENT_MODEL_DIR", Path.home() / "EdgeAgent" / "models")
)
PORT = 18399


def find_llama_server(explicit: str | None) -> str:
    if explicit:
        if not Path(explicit).is_file():
            raise BenchError(f"--llama-server 指定的檔案不存在：{explicit}")
        return explicit
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
    if os.name == "nt":
        links = winget / "Links"
        os.environ["PATH"] = f"{links}{os.pathsep}{os.environ.get('PATH', '')}"
    exe = shutil.which("llama-server.exe") or shutil.which("llama-server")
    if exe:
        return exe
    # winget sometimes unpacks a portable package without creating the
    # Links shim; the exe is then only under Packages\ggml.llamacpp_*.
    if os.name == "nt":
        found = sorted((winget / "Packages").glob("ggml.llamacpp*/**/llama-server.exe"))
        if found:
            return str(found[-1])
    raise BenchError(
        "找不到 llama-server。Windows：winget install --id ggml.llamacpp -e，"
        "或用 --llama-server 指定路徑；Linux 開發機先 source .runtime/tools/env.sh"
    )


def bench_llm(
    args: argparse.Namespace, rows: list[tuple[str, str]], gpu_before: int | None
) -> None:
    model = Path(args.model)
    if not model.is_file():
        model = EDGE_AGENT_MODEL_DIR / args.model
    if not model.is_file():
        raise BenchError(f"找不到模型 {model}")
    lora = None
    if args.lora:
        lora = Path(args.lora)
        if not lora.is_file():
            lora = EDGE_AGENT_MODEL_DIR / args.lora
        if not lora.is_file():
            raise BenchError(f"找不到 LoRA {lora}")
    exe = find_llama_server(args.llama_server)
    rows.append(("llama-server", exe))
    listing = subprocess.run(
        [exe, "--list-devices"],
        capture_output=True,
        timeout=30,
        creationflags=NO_WINDOW,
    )
    devices = [
        line.strip()
        for line in (listing.stdout + listing.stderr)
        .decode("utf-8", "replace")
        .splitlines()
        if "MiB" in line and ":" in line
    ]
    rows.append(("llama.cpp 裝置", " | ".join(devices) or "沒有（只能用 CPU）"))

    # Same flags as silenttalk/copilot/llm.py LocalReplyModel.start (low_vram).
    threads = max(2, min(6, (os.cpu_count() or 4) // 2))
    slots = 2 if lora else 1
    rows.append(("每槽 context", f"{args.context_size} tokens × {slots} slots"))
    cmd = [
        exe,
        "--model",
        str(model),
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        # With an adapter the app runs one slot per adapter scale (llm.py
        # _lora_field), each with the full context.
        "--ctx-size",
        str(args.context_size * slots),
        "--threads",
        str(threads),
        "--n-gpu-layers",
        str(args.gpu_layers),
        "--parallel",
        str(slots),
        "--jinja",
        "--flash-attn",
        "on",
        "--cache-type-k",
        "q8_0",
        "--cache-type-v",
        "q8_0",
    ] + (["--lora", str(lora)] if lora else [])
    started = time.perf_counter()
    server = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=NO_WINDOW,
    )
    try:
        wait_healthy(server)
        rows.append(("模型載入", f"{time.perf_counter() - started:.1f} s"))
        gpu_after = gpu_memory_used()
        if gpu_before is not None and gpu_after is not None:
            rows.append(
                (
                    "模型吃掉的 VRAM",
                    f"{gpu_after - gpu_before} MiB（載入前已用 {gpu_before} MiB）",
                )
            )
        post(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": "暖機"},
            ],
            1,
        )

        chat = synthetic_chat(args.history_turns)
        timed_from = max(TIMED_FROM, len(chat) - 8)
        old_requests = old_format_requests(chat, timed_from)
        new_requests = new_format_requests(chat, timed_from)
        if lora is not None:
            # What the app does per line: the gate with the adapter (slot 0),
            # then the reply, with the adapter on the same slot when "line"
            # is one of its uses, else without it (slot 1). Each slot keeps
            # its cache.
            on = {"lora": [{"id": 0, "scale": 1.0}], "id_slot": 0}
            off = {"lora": [{"id": 0, "scale": 0.0}], "id_slot": 1}
            line_on = "line" in args.lora_uses.split(",")
            reply = on if line_on else off
            post(new_requests[0], 1, extra=on)
            post(new_requests[0], 1, extra=off)
            gates, replies = [], []
            for messages in new_requests[1:]:
                gates.append(post(messages, 1, extra=on))
                replies.append(post(messages, 20, extra=reply))
            rows.append(("判斷一句（LoRA，slot 0）", summarize(gates)))
            rows.append(
                (
                    "接著回一句（LoRA，slot 0，最多 20 token）"
                    if line_on
                    else "接著回一句（原模型，slot 1，最多 20 token）",
                    summarize(replies),
                )
            )
            if args.history_turns > len(CHAT):
                recalled = RECALL_MARKER in replies[-1]["text"]
                rows.append(
                    (
                        "長對話回想",
                        ("PASS" if recalled else "FAIL") + f"（{replies[-1]['text']}）",
                    )
                )
            speed = post(new_requests[-1], 32, ignore_eos=True, extra=reply)
            rows.append(
                (
                    "生成速度（LoRA）" if line_on else "生成速度",
                    f"{speed['tps']:.1f} token/s",
                )
            )
            return

        # The first request of each format fills its cache; time the rest,
        # which is what a running chat looks like.
        post(old_requests[0], 1)
        old = [post(m, 1) for m in old_requests[1:]]
        post(new_requests[0], 1)
        new = [post(m, 1) for m in new_requests[1:]]
        rows.append(("判斷一句（舊格式）", summarize(old)))
        rows.append(("判斷一句（新格式）", summarize(new)))

        # Generation speed: force a fixed length so every machine does the same work.
        speed = post(new_requests[-1], 32, ignore_eos=True)
        rows.append(("生成速度", f"{speed['tps']:.1f} token/s"))
        reply = post(new_requests[-1], 60)
        rows.append(
            ("回一句話（新格式）", f"{reply['ms']:.0f} ms（{reply['n']} token）")
        )
    finally:
        server.terminate()
        try:
            server.wait(5)
        except subprocess.TimeoutExpired:
            server.kill()


def wait_healthy(server: subprocess.Popen) -> None:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise BenchError(
                f"llama-server 啟動失敗，exit code={server.returncode}"
                "（常見：port 被占用、VRAM 不足）"
            )
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1)
            return
        except OSError:
            time.sleep(0.5)
    raise BenchError("llama-server 載入逾時")


def post(
    messages: list[dict],
    max_tokens: int,
    *,
    ignore_eos: bool = False,
    extra: dict | None = None,
) -> dict:
    body = {
        **(extra or {}),
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "cache_prompt": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if ignore_eos:
        body["ignore_eos"] = True
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)
    timings = result.get("timings", {})
    return {
        "ms": (time.perf_counter() - started) * 1000,
        "prompt": timings.get("prompt_n", 0),
        "prompt_total": result.get("usage", {}).get("prompt_tokens", 0),
        "n": timings.get("predicted_n", 0),
        "tps": timings.get("predicted_per_second", 0.0),
        "text": str(result.get("choices", [{}])[0].get("message", {}).get("content", "")),
    }


def summarize(results: list[dict]) -> str:
    ms = [r["ms"] for r in results]
    prompt = statistics.median(r["prompt"] for r in results)
    prompt_total = statistics.median(r["prompt_total"] for r in results)
    return (
        f"中位數 {statistics.median(ms):.0f} ms（{min(ms):.0f}–{max(ms):.0f}），"
        f"總 prompt {prompt_total:.0f} token，每次重算 {prompt:.0f} token"
    )
