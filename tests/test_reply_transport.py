import io
import urllib.error
from pathlib import Path

import pytest

from silenttalk.copilot.reply_transport import (
    InferenceDeferred,
    LocalLLMError,
    ReplyTransport,
)


def test_a_busy_owner_defers_the_request(monkeypatch):
    transport = ReplyTransport(Path("unused"), 18087, True, 15)
    captured = []

    def busy(request, timeout):
        captured.append(request)
        raise urllib.error.HTTPError(request.full_url, 423, "busy", {},
                                     io.BytesIO(b'{"error":{"code":"inference_busy"}}'))

    monkeypatch.setattr("urllib.request.urlopen", busy)
    transport.lease.statuses_seen = 7
    with pytest.raises(InferenceDeferred) as deferred:
        transport.request_messages([])
    assert captured[0].get_header("X-character-owner") == str(transport._owner_pid)
    # Its turn counts only EdgeAgent's statuses after the request was sent.
    assert deferred.value.seen == 7


@pytest.mark.parametrize("body", [b'[]', b'bad json', b'{"error":"unrelated"}'])
def test_a_different_locked_response_remains_a_service_error(body):
    error = urllib.error.HTTPError("fixture", 423, "fixture", {}, io.BytesIO(body))
    with pytest.raises(LocalLLMError):
        ReplyTransport._http_error(error)


def test_adapters_share_one_slot_while_the_owner_controls_scales():
    transport = ReplyTransport(Path("unused"), 18087, True, 15)
    transport.adapter_loaded = True
    assert [transport.lora_field(role)["id_slot"] for role in (True, False)] == [0, 0]
