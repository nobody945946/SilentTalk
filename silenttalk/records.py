"""Conversation records on the user's encrypted external drive (AGENTS.md rule 1).

The user keeps transcripts so the Agent and the character can grow from them
(「我不希望agent用完就忘」). They are written only:

- under the folder set in settings (copilot.record_folder), and only while that
  folder holds the marker file the setup step wrote (MARKER): a drive that is
  unplugged or still locked, or any other disk, gets nothing, and nothing is
  kept elsewhere to be written later;
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

from silenttalk.copilot.types import ConversationTurn

_LOG = logging.getLogger(__name__)
# Written by the setup step on the encrypted drive; its presence is the
# signal that this folder is the user's records drive and is unlocked.
MARKER = ".agent-records"


@dataclass
class TranscriptRecorder:
    enabled: bool = False
    folder: str = ""

    def __post_init__(self) -> None:
        self._state = ""

    def configure(self, *, enabled: bool, folder: str) -> None:
        self.enabled, self.folder = enabled, folder

    def ready(self) -> bool:
        """Recording is on and the records drive is there and unlocked."""
        return self.enabled and bool(self.folder) and (Path(self.folder) / MARKER).is_file()

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
            "text": turn.text,
        }
        try:
            path = Path(self.folder) / "silenttalk" / f"{day}.jsonl"
            path.parent.mkdir(exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            self._note(f"failed {type(exc).__name__}")
            return False
        self._note("on")
        return True

    def _note(self, state: str) -> None:
        if state != self._state:
            self._state = state
            _LOG.info("transcript_recording state=%s", state)
