"""Why an Agent task failed reaches the logs as a code, never as text, and
a chat as a fixed reason for that code."""

from __future__ import annotations

import aiohttp

from silenttalk.agent_lease import AgentLeaseError
from silenttalk.agent_tasks import client_failure
from silenttalk.copilot.task_runner import FAILURE_REASONS, failure_code, failure_words


def test_client_failures_have_stable_codes() -> None:
    assert client_failure(TimeoutError()) == "read_timeout"
    response = aiohttp.ClientResponseError(request_info=None, history=(), status=423)  # type: ignore[arg-type]
    assert client_failure(response) == "http_423"
    assert client_failure(aiohttp.ClientConnectionError()) == "connection"
    assert client_failure(AgentLeaseError("Agent 連線結束，沒有完成事件。")) == "stream_ended"
    assert client_failure(ValueError("invalid task event")) == "invalid_event"


def test_only_a_code_is_logged_never_a_message() -> None:
    assert failure_code("repeat_limit") == "repeat_limit"
    assert failure_code("請幫我查 C:\\Users\\me 的檔案") == "unknown"
    assert failure_code(None) == "unknown"
    assert failure_code("x" * 60) == "unknown"


def test_a_chat_hears_a_reason_for_every_code_never_the_code() -> None:
    assert failure_words("repeat_limit") == "工作失敗了：思考機把同一個操作重複了好幾次都沒有進展，被停下。"
    assert failure_words("agent_busy") == failure_words("inference_busy")
    for code in FAILURE_REASONS:
        assert code not in failure_words(code)
    # A code this app has no reason for (a newer EdgeAgent's) is unknown.
    assert failure_words("some_new_code") == failure_words("unknown") == "工作失敗了：原因不明。"
