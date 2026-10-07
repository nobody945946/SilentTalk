"""Conversation records in the user's selected folder (AGENTS.md rule 1).

The user keeps transcripts so the Agent and the character can grow from them
(「我不希望agent用完就忘」). They are written only:

- under the folder set in settings (copilot.record_folder), and only while that
  folder holds the marker file the setup step wrote (MARKER). Local SSD folders
  are allowed; an unavailable or unprepared folder gets nothing, and nothing
  is kept elsewhere to be written later;
- as text (who, when, typed or spoken, what); never audio.

They are the user's own record, not shared: no announcement in the channel
and no per-person exclusions (the user's decision).

One JSONL file per day under silenttalk/. Nothing here is logged: the log
only says whether recording is on or paused.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from silenttalk.conversation import ConversationTurn

_LOG = logging.getLogger(__name__)
# Written by setup to identify the folder selected for records.
MARKER = ".agent-records"


def validate_record_folder(folder: str) -> Path:
    """Require an existing folder, resolving junctions and symlinks."""
    if not isinstance(folder, str) or not folder.strip():
        raise ValueError("請先選擇紀錄資料夾")
    path = Path(folder).resolve(strict=True)
    if not path.is_dir():
        raise ValueError("紀錄資料夾不存在")
    return path


def prepare_record_folder(folder: str) -> Path:
    """Mark the existing folder selected by the user for records."""
    path = validate_record_folder(folder)
    (path / MARKER).touch(exist_ok=True)
    return path


def recording_status(enabled: bool, folder: str) -> str:
    if not enabled:
        return "關閉"
    try:
        path = validate_record_folder(folder)
        if (path / MARKER).is_file():
            return "記錄中"
    except (OSError, ValueError, RuntimeError):
        pass
    return "暫停：紀錄資料夾無法使用或尚未設定；請確認資料夾與標記檔"


@dataclass
class TranscriptRecorder:
    enabled: bool = False
    folder: str = ""

    def __post_init__(self) -> None:
        self._state = ""

    def configure(self, *, enabled: bool, folder: str) -> None:
        self.enabled, self.folder = enabled, folder

    def ready(self) -> bool:
        """Recording is on and the selected folder is available and prepared."""
        return recording_status(self.enabled, self.folder) == "記錄中"

    def write(self, turn: ConversationTurn, character: str = "") -> bool:
        """Append one line; False when it was not written (off, drive
        absent, or the write failed)."""
        if not self.enabled:
            return False
        if not self.ready():
            self._note("paused")
            return False
        stamp = turn.created_at or time.time()
        day = time.strftime("%Y-%m-%d", time.localtime(stamp))
        record = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stamp)),
            "speaker_id": turn.speaker_id,
            "speaker": character if turn.is_self and character else turn.speaker_name,
            "self": turn.is_self,
            "via": turn.via,
            # 0 = the voice channel, otherwise the Discord thread it was said in
            "place": turn.place,
            "text": turn.text,
        }
        try:
            path = validate_record_folder(self.folder) / "silenttalk" / f"{day}.jsonl"
            path.parent.mkdir(exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except (OSError, ValueError, RuntimeError) as exc:
            self._note(f"failed {type(exc).__name__}")
            return False
        self._note("on")
        return True

    def _note(self, state: str) -> None:
        if state != self._state:
            self._state = state
            _LOG.info("transcript_recording state=%s", state)
