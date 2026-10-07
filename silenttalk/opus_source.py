"""Own the encoder process independently of Discord connection recovery."""

from __future__ import annotations

import subprocess
import threading

import discord
from discord.oggparse import OggError, OggStream

from silenttalk.tts.base import AudioResult

STREAM_INPUT_OPTIONS = "-f mp3 -probesize 32 -analyzeduration 0 -fflags nobuffer"


class OpusSource(discord.AudioSource):
    def __init__(self, audio: AudioResult, *, executable: str):
        self._input = audio.stream
        self._closed = threading.Event()
        self._input_failed = False
        args = [executable, "-nostdin"]
        if self._input is not None:
            args += STREAM_INPUT_OPTIONS.split()
        args += ["-i", "pipe:0" if self._input is not None else str(audio.path)]
        args += [
            "-vn",
            "-map_metadata",
            "-1",
            "-f",
            "opus",
            "-c:a",
            "libopus",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-b:a",
            "128k",
            "-loglevel",
            "warning",
            "-fec",
            "true",
            "-packet_loss",
            "15",
            "-blocksize",
            "8192",
        ]
        if audio.ffmpeg_filter:
            args += ["-af", audio.ffmpeg_filter]
        args += ["pipe:1"]
        self._process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if self._input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._packets = OggStream(self._process.stdout).iter_packets()
        self._feeder = None
        if self._input is not None:
            self._feeder = threading.Thread(
                target=self._feed, name="opus-input", daemon=True
            )
            self._feeder.start()

    def _feed(self) -> None:
        try:
            while not self._closed.is_set():
                chunk = self._input.read(8192)
                if not chunk:
                    self._input_failed = self._input.error is not None
                    break
                self._process.stdin.write(chunk)
                self._process.stdin.flush()
        except Exception:
            self._input_failed = not self._closed.is_set()
        finally:
            try:
                self._process.stdin.close()
            except (OSError, ValueError):
                self._input_failed = not self._closed.is_set()

    def read(self) -> bytes:
        if self._closed.is_set():
            return b""
        try:
            packet = next(self._packets, b"")
        except (OggError, OSError, ValueError) as exc:
            if self._closed.is_set():
                return b""
            raise discord.FFmpegProcessError(
                "Encoder produced invalid Opus data"
            ) from exc
        if packet or self._closed.is_set():
            return packet
        # Pipe EOF can precede the process exit notification on Windows.
        # Wait for the final code rather than treating poll(None) as success.
        try:
            code = self._process.wait(timeout=5)
        except subprocess.TimeoutExpired as exc:
            raise discord.FFmpegProcessError(
                "Encoder did not finish after EOF"
            ) from exc
        if code != 0 or self._input_failed:
            raise discord.FFmpegProcessError(
                f"Encoder failed: exit={code}, input_failed={self._input_failed}"
            )
        return b""

    def is_opus(self) -> bool:
        return True

    def cleanup(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        if self._input is not None:
            self._input.close()
        if self._process.poll() is None:
            self._process.kill()
        self._process.wait(timeout=5)
        if self._process.stdout is not None:
            self._process.stdout.close()
