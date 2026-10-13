"""Wait for a llama-server to say it is listening; never ask it at an interval.

Once the model is loaded, llama-server prints

    0.02.486.788 I srv  llama_server: model loaded
    0.02.486.790 I srv  llama_server: listening on http://127.0.0.1:18189

(older builds: "main: server is listening on http://..."). That line is the
readiness; the server's output ending first means it exited while loading,
and its last lines say why. Nothing here asks /health (the owner, 2026-10-14:
nothing asks at a fixed interval); the one deadline is for a load that hangs.

- start(): the Python tools (eval_server.py and the evals that start their
  own server). The server is a child with its output on a pipe; a thread
  reads it line by line (blocking reads), writes each line to the log if one
  is given, and keeps reading after the server is ready, so the pipe never
  fills.
- The command line, for character_pipeline.sh, whose servers are children of
  the script writing straight to their log: follows the log from where this
  start began (tail -F, inotify) and the server's exit (a pidfd), whichever
  comes first. Linux only.

    serve_wait.py LOG PID [--from BYTES] [--timeout SECONDS]

  exit 0: listening; 1: the server exited first (its last lines printed);
  2: not listening by the deadline (the caller stops the server).
"""

from __future__ import annotations

import argparse
import os
import select
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import IO

LISTENING = b"listening on http://"
LAST_LINES = 20


class NotListening(SystemExit):
    """The server exited while loading, or was not listening by the deadline
    (then it was stopped). A SystemExit: a tool that does not catch it stops
    with the reason."""

    def __init__(self, message: str, exited: bool) -> None:
        super().__init__(message)
        self.exited = exited


class _Output:
    """A llama-server's output, read line by line as it is written."""

    def __init__(self) -> None:
        self.settled = threading.Event()  # listening, exited, or the output ended
        self.listening = False
        self.exited = False
        self.last: deque[bytes] = deque(maxlen=LAST_LINES)

    def follow(self, stream: IO[bytes], log: Path | None = None) -> None:
        sink = log.open("ab") if log is not None else None
        try:
            for line in iter(stream.readline, b""):
                if sink is not None:
                    sink.write(line)
                    sink.flush()
                self.last.append(line)
                if not self.listening and LISTENING in line:
                    self.listening = True
                    self.settled.set()
        finally:
            if sink is not None:
                sink.close()
            self.settled.set()

    def watch_exit(self, pid: int) -> None:
        """A pidfd turns readable when the process ends."""
        try:
            fd = os.pidfd_open(pid)
        except ProcessLookupError:
            pass  # already gone
        else:
            select.select([fd], [], [])
            os.close(fd)
        self.exited = True
        self.settled.set()

    def last_lines(self) -> str:
        return b"".join(self.last).decode("utf-8", "replace").rstrip()


def start(args: list[str], *, log: Path | None = None, timeout: float = 900) -> subprocess.Popen:
    """Start llama-server and return it once it is listening; its output keeps
    going to `log` (appended), or only through memory. Raises NotListening."""
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    output = _Output()
    reader = threading.Thread(target=output.follow, args=(process.stdout, log), daemon=True)
    reader.start()
    output.settled.wait(timeout)
    if output.listening:
        return process
    exited = output.settled.is_set()  # the output ended: the server is going
    process.terminate()
    try:
        process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    reader.join()
    why = (f"exited ({process.returncode}) before it was listening" if exited
           else f"did not become ready in {timeout:.0f} s (stopped it)")
    raise NotListening(f"llama-server {why}; its last lines:\n{output.last_lines()}", exited)


def follow_log(log: Path, pid: int, offset: int, timeout: float) -> int:
    """For a server another process started, writing to `log` itself."""
    output = _Output()
    tail = subprocess.Popen(["tail", "-F", "-c", f"+{offset + 1}", str(log)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    threading.Thread(target=output.follow, args=(tail.stdout,), daemon=True).start()
    threading.Thread(target=output.watch_exit, args=(pid,), daemon=True).start()
    output.settled.wait(timeout)
    ended = tail.poll()
    tail.terminate()
    tail.wait()
    if output.listening:
        print(f"llama-server {pid} is listening", flush=True)
        return 0
    if output.exited:
        # From the file itself: the follower may not have caught up yet.
        with log.open("rb") as handle:
            handle.seek(offset)
            lines = handle.read().decode("utf-8", "replace").rstrip().splitlines()
        print(f"llama-server {pid} exited before it was listening; the last lines of {log}:",
              *lines[-LAST_LINES:], sep="\n", flush=True)
        return 1
    if ended is not None:
        print(f"could not follow {log} (tail exited {ended})", flush=True)
        return 1
    print(f"llama-server {pid} did not become ready in {timeout:.0f} s", flush=True)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", type=Path, help="the server's log (the server writes it)")
    parser.add_argument("pid", type=int, help="the server's process")
    parser.add_argument("--from", dest="offset", type=int, default=0,
                        help="where this start's output begins in the log (bytes)")
    parser.add_argument("--timeout", type=float, default=900, help="seconds a model may take to load")
    args = parser.parse_args(argv)
    return follow_log(args.log, args.pid, args.offset, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
