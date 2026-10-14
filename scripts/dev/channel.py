"""Messages between the dev box and the laptop, both ways, with no polling
(the owner, 2026-10-14: 「把輪巡腳本都拆掉，讓你們雙向溝通」).

The mailboxes live on the dev box; the laptop reaches them over SSH (the dev
box cannot reach the laptop). A message is a small JSON file in the
receiver's spool, so nothing is lost when nobody is waiting; a wait blocks in
the kernel (inotify on the spool) until a message lands. A message stays
until its receiver says it is `done`: a waiter whose SSH connection died (a
laptop that slept) still wakes and prints into the dead connection, and the
message must not go with it. Metadata only (repo, branch, commit, handoff
path, a short note): never conversation content, credentials or the owner's
files.

  channel.py send <devbox|laptop> <kind> [text]   kind: round, received, report, note
  channel.py wait <devbox|laptop> [--after <id>]  prints the waiting messages, one JSON line each
                                                  with its id, once one is newer than <id>
                                                  (any, without --after); then exits
  channel.py done <devbox|laptop> <id>...         removes messages that were acted on

From the laptop: ssh <dev box> python3 /home/clawd/SilentTalk/scripts/dev/channel.py ...
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import select
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CHANNEL_ROOT", Path(__file__).resolve().parents[2] / ".runtime" / "channel"))
BOXES = ("devbox", "laptop")
KINDS = ("round", "received", "report", "note")
MAX_TEXT = 500
ID = re.compile(r"[0-9]{1,20}-[0-9]{1,10}")
IN_MOVED_TO = 0x80


def _box(box: str) -> Path:
    if box not in BOXES:
        raise SystemExit(f"box must be one of {', '.join(BOXES)}")
    path = ROOT / box
    path.mkdir(parents=True, exist_ok=True)
    return path


def _order(message_id: str) -> tuple[int, int]:
    nanoseconds, pid = message_id.split("-")
    return int(nanoseconds), int(pid)


def watch(directory: Path) -> int:
    """A descriptor that turns readable when a file is renamed into
    `directory` (messages and wake.py's state land by os.replace). inotify
    wakes every waiter and is consumed by none, so a waiter on a dead
    connection cannot take another's wakeup."""
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "inotify_init1")
    if libc.inotify_add_watch(fd, os.fsencode(directory), IN_MOVED_TO) < 0:
        error = ctypes.get_errno()
        os.close(fd)
        raise OSError(error, f"inotify_add_watch {directory}")
    return fd


def bell(box: str) -> int:
    """Readable when a message lands in `box` (see watch)."""
    return watch(_box(box))


def drain(fd: int) -> None:
    try:
        while os.read(fd, 4096):
            pass
    except BlockingIOError:
        pass


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
    os.replace(temporary, spool / f"{name}.json")  # the rename wakes the waits
    return {"id": name, **message}


def pending(box: str) -> list[dict[str, str]]:
    """The messages waiting for `box`, oldest first, each with its id; they
    stay until done()."""
    messages = []
    for path in sorted(_box(box).glob("*.json"), key=lambda path: _order(path.stem)):
        if not ID.fullmatch(path.stem):
            continue
        try:
            messages.append({"id": path.stem, **json.loads(path.read_text(encoding="utf-8"))})
        except FileNotFoundError:  # done() meanwhile
            continue
    return messages


def done(box: str, ids: list[str]) -> int:
    """Remove the messages with these ids (a receiver acted on them); how many were there."""
    spool, removed = _box(box), 0
    for message_id in ids:
        if not ID.fullmatch(message_id):
            raise SystemExit(f"not a message id: {message_id[:40]!r}")
        try:
            (spool / f"{message_id}.json").unlink()
            removed += 1
        except FileNotFoundError:  # done before
            pass
    return removed


def wait(box: str, after: str | None = None) -> list[dict[str, str]]:
    """The waiting messages once one is newer than `after` (any, with no
    `after`): one that came while nobody waited returns at once."""
    if after is not None and not ID.fullmatch(after):
        raise SystemExit(f"not a message id: {after[:40]!r}")
    fd = bell(box)  # watched before looking, so a message in between wakes it
    try:
        while True:
            drain(fd)
            messages = pending(box)
            if any(after is None or _order(message["id"]) > _order(after) for message in messages):
                return messages
            select.select([fd], [], [])
    finally:
        os.close(fd)


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "send":
        print(json.dumps(send(argv[1], argv[2], " ".join(argv[3:])), ensure_ascii=False))
        return 0
    if argv[:1] == ["wait"] and (len(argv) == 2 or (len(argv) == 4 and argv[2] == "--after")):
        for message in wait(argv[1], argv[3] if len(argv) == 4 else None):
            print(json.dumps(message, ensure_ascii=False), flush=True)
        return 0
    if len(argv) >= 3 and argv[0] == "done":
        print(done(argv[1], argv[2:]))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
