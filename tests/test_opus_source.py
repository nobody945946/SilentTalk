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


def test_machine_spirit_effect_encodes_real_stream_without_native_crash():
    import shutil
    from pathlib import Path

    from silenttalk.tts.stream import AudioStream
    from silenttalk.voice_styles import VOICE_EFFECTS

    root = Path(__file__).resolve().parents[1]
    shipped = next((root / ".runtime/ffmpeg").glob("*/bin/ffmpeg.exe"), None)
    executable = str(shipped) if shipped is not None else shutil.which("ffmpeg")
    if not executable:
        pytest.skip("requires the deployed FFmpeg or system FFmpeg")
    # Synthetic tone stays in RAM: exercise the exact effect and encoder,
    # independently of Microsoft's network and anyone's Discord conversation.
    tone = subprocess.run(
        [executable, "-nostdin", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:a", "libmp3lame", "-f", "mp3", "-loglevel", "error", "pipe:1"],
        capture_output=True, check=True, timeout=20,
    ).stdout
    stream = AudioStream()
    stream.feed(tone)
    stream.finish()
    source = OpusSource(
        AudioResult(None, None, None, "mp3", ffmpeg_filter=VOICE_EFFECTS["machine_spirit"][1], stream=stream),
        executable=executable,
    )
    try:
        packets = list(iter(source.read, b""))
        assert len([p for p in packets if not p.startswith((b"OpusHead", b"OpusTags"))]) >= 20
        assert source._process.returncode == 0
    finally:
        source.cleanup()
