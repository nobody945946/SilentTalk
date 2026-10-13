"""Messages between the dev box and the laptop, both ways, with no polling
(the owner, 2026-10-14: 「把輪巡腳本都拆掉，讓你們雙向溝通」).

The mailboxes live on the dev box; the laptop reaches them over its SSH
session (the dev box cannot reach the laptop). A message is a small JSON file
in the receiver's spool, so nothing is lost when nobody is waiting; the wait
blocks in the kernel on a FIFO doorbell and the sender rings it. Metadata
only (repo, branch, commit, handoff path, a short note): never conversation
content, credentials or the owner's files.

  channel.py send <devbox|laptop> <kind> [text]   kind: round, received, report, note
  channel.py wait <devbox|laptop>                 prints each message as one JSON line, then exits

From the laptop: ssh <dev box> python3 /home/clawd/SilentTalk/scripts/dev/channel.py ...
"""

from __future__ import annotations

import errno
import json
import os
import select
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CHANNEL_ROOT", Path(__file__).resolve().parents[2] / ".runtime" / "channel"))
BOXES = ("devbox", "laptop")
KINDS = ("round", "received", "report", "note")
MAX_TEXT = 500


def _box(box: str) -> Path:
    if box not in BOXES:
        raise SystemExit(f"box must be one of {', '.join(BOXES)}")
    path = ROOT / box
    path.mkdir(parents=True, exist_ok=True)
    bell = path / "bell"
    if not bell.exists():
        try:
            os.mkfifo(bell)
        except FileExistsError:
            pass
    return path


def bell(box: str) -> int:
    """The receiver's end of its doorbell, opened read-write so it never
    sees end-of-file: select() wakes only when a sender rings."""
    return os.open(_box(box) / "bell", os.O_RDWR | os.O_NONBLOCK)


def drain(fd: int) -> None:
    try:
        while os.read(fd, 4096):
            pass
    except BlockingIOError:
        pass


def ring(box: str) -> None:
    try:
        fd = os.open(_box(box) / "bell", os.O_WRONLY | os.O_NONBLOCK)
    except OSError as exc:
        if exc.errno == errno.ENXIO:  # nobody waits: the spool keeps the message
            return
        raise
    try:
        os.write(fd, b"!")
    except BlockingIOError:  # the doorbell is already full of rings
        pass
    finally:
        os.close(fd)


def send(to: str, kind: str, text: str = "") -> dict[str, str]:
    if kind not in KINDS:
        raise SystemExit(f"kind must be one of {', '.join(KINDS)}")
    if len(text) > MAX_TEXT:
        raise SystemExit(f"metadata only: at most {MAX_TEXT} characters")
    message = {
        "from": BOXES[1 - BOXES.index(to)] if to in BOXES else "",
        "to": to,
        "kind": kind,
        "text": text,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    spool = _box(to)
    name = f"{time.time_ns()}-{os.getpid()}"
    temporary = spool / f".{name}.tmp"
    temporary.write_text(json.dumps(message, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, spool / f"{name}.json")
    ring(to)
    return message


def take(box: str) -> list[dict[str, str]]:
    """The messages waiting for `box`, oldest first, removed from its spool."""
    messages = []
    for path in sorted(_box(box).glob("*.json")):
        try:
            messages.append(json.loads(path.read_text(encoding="utf-8")))
            path.unlink()
        except FileNotFoundError:  # another waiter took it
            continue
    return messages


def wait(box: str) -> list[dict[str, str]]:
    fd = bell(box)  # opened before looking, so a ring in between is kept
    try:
        while True:
            drain(fd)
            messages = take(box)
            if messages:
                return messages
            select.select([fd], [], [])
    finally:
        os.close(fd)


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "send":
        print(json.dumps(send(argv[1], argv[2], " ".join(argv[3:])), ensure_ascii=False))
        return 0
    if len(argv) == 2 and argv[0] == "wait":
        for message in wait(argv[1]):
            print(json.dumps(message, ensure_ascii=False), flush=True)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
