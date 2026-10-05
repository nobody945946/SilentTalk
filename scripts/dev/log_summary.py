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
    not, so show only which logger it came from without arbitrary message text."""
    text = str(record.get("event", ""))
    name = text.split(" ", 1)[0]
    if EVENT_NAME.fullmatch(name):
        return name
    return str(record.get("logger", "?"))


def generate_summary(records: list[dict], all_sessions: bool = False) -> str:
    if not all_sessions:
        # The last app run or --stt-check run, whichever came last.
        starts = [
            i
            for i, r in enumerate(records)
            if r.get("event", "").startswith(
                ("copilot_runtime_ready", "copilot_stt_check_start")
            )
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
            problems[
                f"{record['level']} {_problem_name(record)}{_exception_type(record)}"
            ] += 1

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
    segments = events.get("copilot_stt_segment", [])
    received = [
        str(r.get("event", ""))
        for r in records
        if str(r.get("event", "")).startswith("voice_receive_stats")
    ]
    checks = events.get("copilot_stt_check", [])
    check_done = events.get("copilot_stt_check_done", [])

    task_decisions = events.get("agent_task_decision", [])
    task_dispatched = [r for r in task_decisions if r.get("dispatched") == "True"]
    task_skipped = [r for r in task_decisions if r.get("dispatched") == "False"]
    task_finished = events.get("agent_task_finished", [])
    lookups = events.get("agent_chat_task_decision", [])
    lookups_yes = [r for r in lookups if r.get("chat_task") == "True"]
    posted = events.get("agent_result_posted", [])
    posted_ok = [r for r in posted if r.get("posted") == "True"]
    history_read = events.get("thread_history_read", [])
    history_failed = events.get("thread_history_failed", [])
    task_dispatch_failed = events.get("agent_task_dispatch_failed", [])

    approvals = events.get("agent_approval_decided", [])
    approved_true = [r for r in approvals if r.get("approved") == "True"]
    approved_false = [r for r in approvals if r.get("approved") == "False"]
    approval_failed = events.get("agent_approval_failed", [])
    approval_timeout = events.get("agent_approval_timeout_failed", [])

    private_results = events.get("agent_result_private", [])
    private_delivered = [r for r in private_results if r.get("delivered") == "True"]
    private_undelivered = [r for r in private_results if r.get("delivered") == "False"]
    private_failed = events.get("agent_private_failed", [])
    private_send_failed = events.get("private_send_failed", [])
    private_all_failures = len(private_failed) + len(private_send_failed)

    threads_opened = events.get("thread_opened", [])
    threads_failed = events.get("thread_open_failed", [])

    tasks_marked = events.get("task_marked", [])
    marks_accepted = [r for r in tasks_marked if r.get("state") == "accepted"]
    marks_done = [r for r in tasks_marked if r.get("state") == "done"]
    marks_failed = [r for r in tasks_marked if r.get("state") == "failed"]
    marks_mark_failed = events.get("task_mark_failed", [])

    def median_of(rows: list[dict[str, str]], key: str, fmt: str) -> str:
        values = []
        for r in rows:
            try:
                values.append(float(r[key]))
            except (KeyError, ValueError):
                pass
        return format(statistics.median(values), fmt) if values else "—"

    def receive_summary() -> str:
        if not received:
            return "—"
        totals = Counter()
        lost = 0.0
        for text in received:
            packets = re.search(r"rtp_packets=(\d+) rtp_loss=([\d.]+)%", text)
            if packets:
                count, loss = int(packets.group(1)), float(packets.group(2)) / 100
                totals["rtp_packets"] += count
                lost += count * loss / max(1e-9, 1 - loss)
            for key in (
                "odd_frames",
                "dropped_no_session",
                "decode_errors",
                "padded",
                "dave_dropped",
                "unknown_ssrc",
                "recoveries",
            ):
                found = re.search(rf"{key}=(\d+)", text)
                totals[key] += int(found.group(1)) if found else 0
        dave = re.search(r"dave=([A-Za-z0-9_.-]+)", received[-1])
        packets = totals["rtp_packets"]
        return (
            f"{len(received)} 次；收到 {packets} 個語音封包、路上遺失 "
            f"{lost / (packets + lost):.1%}"
            if packets
            else f"{len(received)} 次；沒有收到任何語音封包"
        ) + (
            f"；大小不對 {totals['odd_frames']}、沒 DAVE session 丟掉 {totals['dropped_no_session']}"
            f"、解碼錯誤 {totals['decode_errors']}、有 padding {totals['padded']}"
            f"、DAVE 解不開丟掉 {totals['dave_dropped']}、SSRC 未對應丟掉 {totals['unknown_ssrc']}"
            f"、DAVE 復原 {totals['recoveries']}；最後一次 DAVE：{dave.group(1)}"
            if dave
            else ""
        )

    device_str = (
        " ".join(re.findall(r"[A-Za-z0-9_().,:+\-]+", str(devices[-1]["event"]).split(" ", 1)[-1]))
        if devices
        else "—"
    )

    rows = [
        (
            "GPU（llama.cpp 看到的）",
            device_str or "—",
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
        ("收音（每 30 秒記一次）", receive_summary()),
        ("STT 斷出的句子", str(len(events.get("copilot_turn_final", [])))),
        (
            "STT 片段音量／頻譜平坦度（人聲 < 0.3，雜訊約 0.56）",
            (
                f"中位數 {median_of(segments, 'level_dbfs', '.1f')} dBFS／"
                f"{median_of(segments, 'flatness', '.2f')}；像雜訊（> 0.4）"
                f"{sum(float(r.get('flatness', 0)) > 0.4 for r in segments)}/{len(segments)} 段"
            ),
        ),
        (
            "真人辨識測試（--stt-check）",
            (
                f"經過 Discord 平均錯字率 {float(check_done[-1]['cer']):.1%}（{check_done[-1]['sentences']} 句，"
                f"{'PASS' if check_done[-1].get('passed') == '1' else 'FAIL'}）；"
                + (
                    f"本機麥克風直接收 {float(check_done[-1]['local_cer']):.1%}；"
                    if float(check_done[-1].get("local_cer", -1)) >= 0
                    else "本機麥克風沒量；"
                )
                + f"有結果 {sum(int(r.get('heard_chars', 0)) > 0 for r in checks)}/{len(checks)} 句"
            )
            if check_done
            else "沒有跑",
        ),
        (
            "STT 聲音片段長度（SenseVoice）",
            ms(events.get("copilot_stt_segment", []), "audio_ms"),
        ),
        (
            "STT 辨識一段花的時間",
            ms(events.get("copilot_stt_segment", []), "decode_ms"),
        ),
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
        (
            "聊天工作判斷（叫到機魂的句子）",
            f"{len(lookups)}（交給 Agent {len(lookups_yes)}、自己回 {len(lookups) - len(lookups_yes)}）",
        ),
        ("聊天工作判斷延遲", ms(lookups, "latency_ms")),
        (
            "Agent 派工判斷（主人的 Agent 串）",
            f"{len(task_decisions)}（派工 {len(task_dispatched)}、不派工 {len(task_skipped)}"
            + (f"、失敗 {len(task_dispatch_failed)}" if task_dispatch_failed else "")
            + "）",
        ),
        (
            "Agent 派工判斷延遲",
            ms(task_decisions, "latency_ms"),
        ),
        (
            "Agent 任務執行時間",
            ms(task_finished, "elapsed_ms"),
        ),
        (
            "Agent 批准",
            f"{len(approvals)}（准許 {len(approved_true)}、拒絕 {len(approved_false)}"
            + (f"、失敗 {len(approval_failed)}" if approval_failed else "")
            + (f"、逾時 {len(approval_timeout)}" if approval_timeout else "")
            + "）",
        ),
        (
            "Agent 批准往返延遲",
            ms(approvals, "roundtrip_ms"),
        ),
        (
            "結果貼到聊天室或串",
            f"{len(posted)}（貼出 {len(posted_ok)}、貼不上 {len(posted) - len(posted_ok)}）",
        ),
        (
            "討論串讀回",
            f"{len(history_read)}" + (f"（讀不到 {len(history_failed)}）" if history_failed else ""),
        ),
        (
            "Agent 私訊結果",
            f"{len(private_results)}（送達 {len(private_delivered)}、未送達 {len(private_undelivered)}"
            + (f"、失敗 {private_all_failures}" if private_all_failures else "")
            + "）",
        ),
        (
            "討論串建立",
            f"{len(threads_opened)}"
            + (f"（失敗 {len(threads_failed)}）" if threads_failed else ""),
        ),
        (
            "訊息表情標記（⚙️／✅／❌）",
            f"{len(tasks_marked)}（accepted {len(marks_accepted)}、done {len(marks_done)}、failed {len(marks_failed)}"
            + (f"、失敗 {len(marks_mark_failed)}" if marks_mark_failed else "")
            + "）",
        ),
    ]
    out: list[str] = [
        "| 項目 | 數字 |",
        "|---|---|",
    ]
    for name, value in rows:
        out.append(f"| {name} | {value} |")
    out.append("")
    out.append("警告／錯誤（只列事件名稱和次數）：")
    for name, count in problems.most_common() or [("沒有", 0)]:
        out.append(f"- {name}" + (f" × {count}" if count else ""))
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", type=Path, default=PROJECT_DIR / "silenttalk.log")
    parser.add_argument("--all", action="store_true", help="every session in the file")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not args.log.is_file():
        print(f"找不到 {args.log}")
        return 1

    records = []
    for line in args.log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    print(generate_summary(records, all_sessions=args.all))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
