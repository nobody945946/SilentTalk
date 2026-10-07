from __future__ import annotations

import io
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import discord
import pytest

from silenttalk.opus_source import OpusSource
from silenttalk.tts.base import AudioResult


@pytest.mark.parametrize("code", [0, 3221225477])
def test_encoder_eof_waits_for_the_real_exit_code(code, monkeypatch):
    process = SimpleNamespace(
        stdout=io.BytesIO(),
        wait=Mock(return_value=code),
        poll=Mock(return_value=None),
        kill=Mock(),
    )
    monkeypatch.setattr(
        "silenttalk.opus_source.subprocess.Popen", lambda *a, **k: process
    )
    source = OpusSource(
        AudioResult("synthetic.mp3", None, None, "mp3"), executable="ffmpeg"
    )
    try:
        if code:
            with pytest.raises(discord.FFmpegProcessError, match=str(code)):
                source.read()
        else:
            assert source.read() == b""
        process.wait.assert_called_once_with(timeout=5)
    finally:
        source.cleanup()


def test_encoder_exit_timeout_is_failure_and_cleanup_is_idempotent(monkeypatch):
    process = SimpleNamespace(
        stdout=io.BytesIO(),
        wait=Mock(side_effect=[subprocess.TimeoutExpired("synthetic", 5), 0]),
        poll=Mock(return_value=None),
        kill=Mock(),
    )
    monkeypatch.setattr(
        "silenttalk.opus_source.subprocess.Popen", lambda *a, **k: process
    )
    source = OpusSource(
        AudioResult("synthetic.mp3", None, None, "mp3"), executable="ffmpeg"
    )
    with pytest.raises(discord.FFmpegProcessError, match="EOF"):
        source.read()
    source.cleanup()
    source.cleanup()
    process.kill.assert_called_once()
