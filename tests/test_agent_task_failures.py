"""Why an Agent task failed reaches the logs as a code, never as text."""

from __future__ import annotations

import aiohttp

from silenttalk.agent_lease import AgentLeaseError
from silenttalk.agent_tasks import client_failure
from silenttalk.copilot.task_runner import failure_code


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
