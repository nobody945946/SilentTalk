from __future__ import annotations

from pathlib import Path

from scripts.dev.log_summary import generate_summary


def test_log_summary_parses_agent_events_and_never_leaks_dialogue(tmp_path: Path) -> None:
    secrets = [
        "機密對話一號：今天吃什麼",
        "機密對話二號：密碼是 123456",
        "不要在日誌輸出我的訊息",
        "這是指令原文不可外流",
        "這是任務結果機密內容",
        "使用者說了機密真心話",
    ]

    records = [
        {"event": "copilot_runtime_ready"},
        {
            "event": "agent_task_decision latency_ms=120 dispatched=True",
            "instruction": secrets[3],
            "text": secrets[0],
        },
        {
            "event": "agent_task_decision latency_ms=250 dispatched=False",
            "text": secrets[1],
        },
        {
            "level": "WARNING",
            "event": "agent_task_dispatch_failed error_type=RuntimeError",
            "message": secrets[2],
        },
        {
            "event": "agent_task_finished elapsed_ms=3400",
            "result": secrets[4],
        },
        {
            "event": "agent_task_checks unverified=2 source_problems=1 converted=3",
        },
        {
            "event": "agent_approval_decided approved=True roundtrip_ms=1500",
        },
        {
            "event": "agent_approval_decided approved=False roundtrip_ms=800",
        },
        {
            "level": "WARNING",
            "event": "agent_approval_failed error_type=PermissionError",
        },
        {
            "level": "WARNING",
            "event": "agent_approval_timeout_failed error_type=TimeoutError",
        },
        {
            "event": "agent_result_private kind=done delivered=True",
            "result": secrets[4],
        },
        {
            "event": "agent_result_private kind=error delivered=False",
        },
        {
            "level": "WARNING",
            "event": "agent_private_failed error_type=HTTPException",
        },
        {
            "level": "WARNING",
            "event": "private_send_failed status=403",
        },
        {
            "event": "thread_opened",
        },
        {"event": "agent_chat_task_decision latency_ms=90 chat_task=True", "text": secrets[0]},
        {"event": "agent_chat_task_decision latency_ms=50 chat_task=False"},
        {"event": "agent_result_posted kind=done posted=True place=voice", "result": secrets[4]},
        {"event": "agent_result_posted kind=done posted=False place=text"},
        {"event": "thread_history_read lines=12"},
        {"level": "WARNING", "event": "thread_history_failed error_type=Forbidden"},
        {
            "level": "WARNING",
            "event": "thread_open_failed status=500",
        },
        {
            "event": "task_marked state=accepted",
        },
        {
            "event": "task_marked state=done",
        },
        {
            "event": "task_marked state=failed",
        },
        {
            "level": "WARNING",
            "event": "task_mark_failed state=accepted error_type=Forbidden",
        },
        {
            "level": "WARNING",
            "logger": "discord.gateway",
            "event": f"non_standard_warning_event with text {secrets[5]}",
        },
    ]

    summary = generate_summary(records, all_sessions=True)

    assert "| Agent 派工判斷（主人的 Agent 串） | 2（派工 1、不派工 1、失敗 1） |" in summary
    assert "| 聊天工作判斷（叫到機魂的句子） | 2（交給 Agent 1、自己回 1） |" in summary
    assert "| 結果貼到聊天室或串 | 2（貼出 1、貼不上 1） |" in summary
    assert "| 討論串讀回 | 1（讀不到 1） |" in summary
    assert "中位數 185 ms" in summary
    assert "| Agent 任務執行時間 | 中位數 3400 ms、p90 3400 ms（n=1） |" in summary
    assert "| Agent 主機核對（完成的工作） | 1（改了程式沒通過檢查 1、來源對不上的數字 1、簡轉繁觸發 3） |" in summary
    assert "| Agent 批准 | 2（准許 1、拒絕 1、失敗 1、逾時 1） |" in summary
    assert "中位數 1150 ms" in summary
    assert "| Agent 私訊結果 | 2（送達 1、未送達 1、失敗 2） |" in summary
    assert "| 討論串建立 | 1（失敗 1） |" in summary
    assert "| 訊息表情標記（⚙️／✅／❌） | 3（accepted 1、done 1、failed 1、失敗 1） |" in summary

    # Privacy guarantee: no dialogue text or arbitrary string payload from log may appear in the summary
    for secret in secrets:
        assert secret not in summary
