"""Numbers from silenttalk.log for a real Discord test, as a Markdown table.

    .venv\\Scripts\\python.exe scripts\\dev\\log_summary.py            (Windows)
    .venv/bin/python scripts/dev/log_summary.py [--log PATH] [--all]

Only counts, timings and event names are printed, never message text, so
the output can be pasted or committed as it is. By default it covers the
last app session (from the last copilot_runtime_ready on).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
FIELD = re.compile(r"(\w+)=(\S+)")
EVENT_NAME = re.compile(r"[a-z][a-z0-9_]*")


def _exception_type(record: dict) -> str:
    """The exception class of a traceback ("aiohttp.ClientConnectorError"),
    never its message: that is what tells a network drop from a bad token."""
    trace = str(record.get("exception") or "").strip().splitlines()
    if not trace:
        return ""
    name = trace[-1].split(":", 1)[0].strip()
    return f"（{name}）" if re.fullmatch(r"[\w.]+", name) else ""


def _problem_name(record: dict) -> str:
    """Our own events start with a snake_case name. A library's message does
    not ("1 packets were lost being flushed in decoder-5"), so show which
    logger it came from and its first words with numbers masked."""
    text = str(record.get("event", ""))
    name = text.split(" ", 1)[0]
    if EVENT_NAME.fullmatch(name):
        return name
    shape = re.sub(r"\d+", "N", " ".join(text.split()[:7]))[:60]
    return f"{record.get('logger', '?')}：{shape}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", type=Path, default=PROJECT_DIR / "silenttalk.log")
    parser.add_argument("--all", action="store_true", help="every session in the file")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if not args.log.is_file():
        print(f"找不到 {args.log}")
        return 1

    records = []
    for line in args.log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not args.all:
        starts = [
            i
            for i, r in enumerate(records)
            if r.get("event", "").startswith("copilot_runtime_ready")
        ]
        if starts:
            records = records[max(0, starts[-1] - 50) :]

    events: dict[str, list[dict[str, str]]] = {}
    problems: Counter[str] = Counter()
    for record in records:
        text = str(record.get("event", ""))
        name = text.split(" ", 1)[0]
        events.setdefault(name, []).append(dict(FIELD.findall(text)))
        if record.get("level") in ("WARNING", "ERROR", "CRITICAL"):
            problems[f"{record['level']} {_problem_name(record)}{_exception_type(record)}"] += 1

    def ms(rows: list[dict[str, str]], key: str) -> str:
        values = [
            int(r[key])
            for r in rows
            if r.get(key, "").lstrip("-").isdigit() and int(r[key]) >= 0
        ]
        if not values:
            return "—"
        values.sort()
        p90 = values[min(len(values) - 1, int(len(values) * 0.9))]
        return f"中位數 {statistics.median(values):.0f} ms、p90 {p90} ms（n={len(values)}）"

    lines = events.get("copilot_character_line", [])
    spoke = [r for r in lines if r.get("spoke") == "True"]
    quiet = [r for r in lines if r.get("spoke") == "False"]
    jobs = events.get("job_done", [])
    streamed = [r for r in jobs if r.get("streamed") == "True"]
    devices = [
        r for r in records if str(r.get("event", "")).startswith("copilot_llm_devices")
    ]
    receive = events.get("voice_receive_started", [])

    rows = [
        (
            "GPU（llama.cpp 看到的）",
            str(devices[-1]["event"]).split(" ", 1)[-1] if devices else "—",
        ),
        (
            "連上 Discord（ready／resumed）",
            (
                f"{len(events.get('discord_ready', []))}"
                f"／{len(events.get('discord_gateway_resumed', []))}"
            ),
        ),
        (
            "語音接收",
            f"dave_version={receive[-1].get('dave_version')}"
            if receive
            else "沒有啟動",
        ),
        ("STT 斷出的句子", str(len(events.get("copilot_turn_final", [])))),
        (
            "STT 聽到聲音但沒辨識出字（SenseVoice）",
            f"{len(events.get('copilot_stt_empty', []))}"
            + (
                f"（{ms(events.get('copilot_stt_empty', []), 'audio_ms')}）"
                if events.get("copilot_stt_empty")
                else ""
            ),
        ),
        ("打字訊息", str(len(events.get("text_message_received", [])))),
        ("角色判斷次數", f"{len(lines)}（開口 {len(spoke)}、沒開口 {len(quiet)}）"),
        ("聽到 → 角色的話備好（開口時）", ms(spoke, "since_heard_ms")),
        ("聽到 → 決定不開口", ms(quiet, "since_heard_ms")),
        ("模型本身（開口時）", ms(spoke, "latency_ms")),
        (
            "因為還在說話而丟掉的句子",
            str(len(events.get("character_line_dropped", []))),
        ),
        ("說出口的句子", f"{len(jobs)}（串流 {len(streamed)}）"),
        ("TTS 到第一段聲音（串流）", ms(streamed, "synthesis_ms")),
    ]
    print("| 項目 | 數字 |")
    print("|---|---|")
    for name, value in rows:
        print(f"| {name} | {value} |")
    print()
    print("警告／錯誤（只列事件名稱和次數）：")
    for name, count in problems.most_common() or [("沒有", 0)]:
        print(f"- {name}" + (f" × {count}" if count else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
