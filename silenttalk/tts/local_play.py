"""Play a synthesized line on this PC's speakers: persona voice preview.

Never goes to Discord, so trying voices does not disturb the channel.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from silenttalk.tts.base import AudioResult

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def render_wav(audio: AudioResult, ffmpeg: str) -> bytes:
    """The audio as WAV with the same FFmpeg effect chain Discord playback uses."""
    command = [ffmpeg, "-v", "error", "-y", "-i", str(audio.path)]
    if audio.ffmpeg_filter:
        command += ["-af", audio.ffmpeg_filter]
    command += ["-ac", "2", "-ar", "48000", "-f", "wav", "-"]
    result = subprocess.run(
        command, capture_output=True, timeout=30, creationflags=_NO_WINDOW
    )
    if result.returncode != 0 or not result.stdout:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-200:]
        raise RuntimeError(f"試聽轉檔失敗：{detail or result.returncode}")
    return result.stdout


def play_wav(wav: bytes) -> None:
    """Blocking; run it off the UI thread."""
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(wav, winsound.SND_MEMORY)
        return
    for player in (["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-"], ["aplay", "-q", "-"]):
        if shutil.which(player[0]):
            subprocess.run(player, input=wav, check=True, timeout=60)
            return
    raise RuntimeError("找不到可以播放聲音的程式（Windows 內建支援）。")
