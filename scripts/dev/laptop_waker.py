"""The laptop's side of the channel while no agent is open: wait for the dev
box's messages and start one Codex run for each new batch (the owner,
2026-10-14: 「裝事件喚醒器」). Nothing wakes a Codex turn that has ended, so
without this a round waits in the spool until the owner opens Codex.

Nothing asks on a timer. It blocks on what the kernel signals: the SSH
command that waits on the dev box's spool (it exits when mail comes, or when
the connection dies) and, on Windows, a change of the IPv4 addresses (a
laptop that wakes from sleep or changes networks has a dead SSH connection
that nothing reports; the change makes it connect again at once). Only a
failed connection waits before trying again, a minute at first, doubling to
half an hour, and a network change cuts that wait short.

The Codex run gets a fixed prompt, never a message's text: the round is the
work file on GitHub, which the agent reads and acknowledges itself
(channel.py wait, received, done). While it runs, .runtime/laptop-agent.json
names its PID, so an agent the owner opens by hand sees one is at work. A run
that exits with an error is told to the dev box; its messages stay for the
next run or the owner, and only a newer message starts another run.

  laptop_waker.py run --dev <ssh target> --codex <codex executable> [--codex-arg <arg>]...
  laptop_waker.py install --dev ... --codex ... [--codex-arg ...] [--startup-dir <dir>]
      (a .cmd in the Windows Startup folder that starts `run` with pythonw at logon)
  laptop_waker.py uninstall [--startup-dir <dir>]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHANNEL = "/home/clawd/SilentTalk/scripts/dev/channel.py"
PROMPT = (
    "開工。這一輪是筆電的喚醒器在沒人的時候叫起來的：照 AGENTS.md 和 handoff/laptop.md 做；"
    "需要使用者在場的步驟記成待真人，不要等他。"
)
FIRST_DELAY, LAST_DELAY = 60.0, 1800.0
RUNNING = REPO / ".runtime" / "laptop-agent.json"
LOCK = REPO / ".runtime" / "laptop-waker.lock"
STARTUP_NAME = "SilentTalk laptop waker.cmd"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class NetworkChanges:
    """Windows: an event set when the IPv4 address table changes
    (NotifyAddrChange, overlapped), waited on together with a process."""

    INFINITE = 0xFFFFFFFF
    WAIT_TIMEOUT = 0x102
    ERROR_IO_PENDING = 997
    SYNCHRONIZE = 0x00100000

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class Overlapped(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_void_p),
                ("InternalHigh", ctypes.c_void_p),
                ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE),
            ]

        self._ctypes = ctypes
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel.CreateEventW.restype = wintypes.HANDLE
        self._kernel.OpenProcess.restype = wintypes.HANDLE
        self._kernel.WaitForMultipleObjects.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self._kernel.WaitForMultipleObjects.restype = wintypes.DWORD
        self._iphlp = ctypes.WinDLL("iphlpapi", use_last_error=True)
        self._handle_type = wintypes.HANDLE
        self._event = self._kernel.CreateEventW(None, True, False, None)
        if not self._event:
            raise ctypes.WinError(ctypes.get_last_error())
        self._overlapped = Overlapped()
        self._overlapped.hEvent = self._event
        self._arm()

    def _arm(self) -> None:
        self._kernel.ResetEvent(self._handle_type(self._event))
        handle = self._handle_type()  # not closed: NotifyAddrChange owns it
        code = self._iphlp.NotifyAddrChange(
            self._ctypes.byref(handle), self._ctypes.byref(self._overlapped)
        )
        if code != self.ERROR_IO_PENDING:
            raise OSError(code, "NotifyAddrChange")

    def wait(self, process: subprocess.Popen | None, timeout: float | None) -> str:
        """ "exited" (the process), "network" (re-armed) or "timeout"."""
        handles = [self._event]
        if process is not None:
            opened = self._kernel.OpenProcess(self.SYNCHRONIZE, False, process.pid)
            if not opened:
                raise self._ctypes.WinError(self._ctypes.get_last_error())
            handles.insert(0, opened)
        array = (self._handle_type * len(handles))(*handles)
        milliseconds = self.INFINITE if timeout is None else int(timeout * 1000)
        try:
            code = self._kernel.WaitForMultipleObjects(
                len(handles), array, False, milliseconds
            )
        finally:
            if process is not None:
                self._kernel.CloseHandle(self._handle_type(handles[0]))
        if code == self.WAIT_TIMEOUT:
            return "timeout"
        if code >= len(handles):
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        if handles[code] == self._event:
            self._arm()
            return "network"
        return "exited"

    def close(self) -> None:
        self._iphlp.CancelIPChangeNotify(self._ctypes.byref(self._overlapped))
        self._kernel.CloseHandle(self._handle_type(self._event))


class NoNetworkChanges:
    """Elsewhere (Linux, the tests): only the process and the timeout."""

    def wait(self, process: subprocess.Popen | None, timeout: float | None) -> str:
        if process is None:
            time.sleep(timeout or 0.0)
            return "timeout"
        try:
            process.wait(timeout)
        except subprocess.TimeoutExpired:
            return "timeout"
        return "exited"

    def close(self) -> None:
        pass


def _order(message_id: str) -> tuple[int, int]:
    nanoseconds, pid = message_id.split("-")
    return int(nanoseconds), int(pid)


class Waker:
    def __init__(
        self,
        channel: list[str],
        codex: list[str],
        network: NetworkChanges | NoNetworkChanges,
        *,
        delays: tuple[float, float] = (FIRST_DELAY, LAST_DELAY),
        running: Path = RUNNING,
    ) -> None:
        self.channel = channel  # the command that runs channel.py on the dev box
        self.codex = codex  # the command that starts one run, before its prompt
        self.network = network
        self.delays = delays
        self.running = running
        self.after: str | None = None  # the newest message a run was started for

    def mail(self) -> tuple[str, list[dict[str, str]]]:
        """("mail", the waiting messages) once one is newer than the last
        run's; ("network", []) when a network change cut the wait;
        ("failed", []) when the connection or the dev box failed."""
        command = [*self.channel, "wait", "laptop"]
        if self.after is not None:
            command += ["--after", self.after]
        waiter = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
        output: list[bytes] = []
        reader = threading.Thread(
            target=lambda: output.append(waiter.stdout.read()), daemon=True
        )
        reader.start()
        if self.network.wait(waiter, None) == "network":
            waiter.kill()  # its connection may be dead; connect again
            waiter.wait()
            reader.join()
            return "network", []
        waiter.wait()
        reader.join()
        if waiter.returncode != 0:
            return "failed", []
        messages = []
        for line in b"".join(output).decode("utf-8", "replace").splitlines():
            try:
                message = json.loads(line)
                _order(message["id"])
            except (ValueError, KeyError, TypeError, AttributeError):
                return "failed", []
            messages.append(message)
        newest = max((message["id"] for message in messages), key=_order, default=None)
        if newest is None or (
            self.after is not None and _order(newest) <= _order(self.after)
        ):
            return (
                "failed",
                [],
            )  # wait --after returns only with a newer one: something is off
        self.after = newest
        return "mail", messages

    def start_run(self) -> int:
        process = subprocess.Popen(
            [newest(self.codex[0]), *self.codex[1:], PROMPT],
            cwd=REPO,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
        self.running.parent.mkdir(parents=True, exist_ok=True)
        self.running.write_text(
            json.dumps(
                {
                    "pid": process.pid,
                    "since": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "after": self.after,
                }
            ),
            encoding="utf-8",
        )
        try:
            return process.wait()
        finally:
            self.running.unlink(missing_ok=True)

    def note(self, text: str) -> None:
        subprocess.run(
            [*self.channel, "send", "devbox", "note", text],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
            timeout=120,
            check=False,
        )

    def serve(self, rounds: Callable[[], bool] = lambda: True) -> None:
        """Wait, run, repeat while `rounds()` says so (the tests stop it)."""
        delay = self.delays[0]
        while rounds():
            outcome, messages = self.mail()
            if outcome == "network":
                delay = self.delays[0]
                continue
            if outcome == "failed":
                if self.network.wait(None, delay) == "network":
                    delay = self.delays[0]
                else:
                    delay = min(delay * 2, self.delays[1])
                continue
            delay = self.delays[0]
            code = self.start_run()
            if code != 0:
                left = len(messages)
                self.note(
                    f"laptop waker: the Codex run for {self.after} exited {code}; {left} message(s) were waiting"
                )


def newest(executable: str) -> str:
    """The executable itself, or with a wildcard the newest file it matches."""
    if not glob.has_magic(executable):
        return executable
    matches = glob.glob(executable)
    if not matches:
        raise FileNotFoundError(f"nothing matches {executable}")
    return max(matches, key=os.path.getmtime)


def single_instance(path: Path = LOCK):
    """An open, locked file while this is the only waker; None if another runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")  # noqa: SIM115 - held open: the lock lives as long as the waker
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def startup_dir(given: str | None) -> Path:
    if given:
        return Path(given)
    if os.name != "nt":
        raise SystemExit("--startup-dir is needed outside Windows")
    return (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def startup_line(dev: str, codex: str, codex_args: list[str]) -> str:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = str(pythonw if pythonw.is_file() else Path(sys.executable))
    argv = [
        interpreter,
        str(Path(__file__).resolve()),
        "run",
        "--dev",
        dev,
        "--codex",
        codex,
    ]
    for arg in codex_args:
        argv += ["--codex-arg", arg]
    if any(ch in arg for arg in argv for ch in '%"^&|<>\r\n'):
        raise SystemExit(
            'an argument holds a character cmd would read: % " ^ & | < > or a line break'
        )
    return '@echo off\r\nstart "" ' + subprocess.list2cmdline(argv) + "\r\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="laptop_waker.py", description=__doc__.split("\n\n")[0]
    )
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("run", "install"):
        action = sub.add_parser(name)
        action.add_argument("--dev", required=True, help="the dev box as ssh names it")
        action.add_argument(
            "--codex",
            required=True,
            help="the codex executable; with * the newest match at each run (the VS Code extension's folder changes with its version)",
        )
        action.add_argument(
            "--codex-arg", action="append", default=[], help="an option for codex exec"
        )
        if name == "install":
            action.add_argument("--startup-dir")
    remove = sub.add_parser("uninstall")
    remove.add_argument("--startup-dir")
    args = parser.parse_args(argv)

    if args.action == "install":
        target = startup_dir(args.startup_dir) / STARTUP_NAME
        target.write_text(
            startup_line(args.dev, args.codex, args.codex_arg),
            encoding="utf-8",
            newline="",
        )
        print(target)
        return 0
    if args.action == "uninstall":
        target = startup_dir(args.startup_dir) / STARTUP_NAME
        target.unlink(missing_ok=True)
        print(target)
        return 0

    lock = single_instance()
    if lock is None:
        return 0  # one waker already waits
    network = NetworkChanges() if os.name == "nt" else NoNetworkChanges()
    channel = ["ssh", "-o", "BatchMode=yes", args.dev, "python3", CHANNEL]
    waker = Waker(channel, [args.codex, "exec", *args.codex_arg], network)
    try:
        waker.serve()
    except (
        Exception
    ) as exc:  # no console under pythonw: tell the dev box why it stopped
        waker.note(f"laptop waker stopped: {type(exc).__name__}: {exc}"[:200])
        raise
    finally:
        network.close()
        lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
