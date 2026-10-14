"""The laptop waker (scripts/dev/laptop_waker.py): one Codex run per new
batch of mail, nothing on a timer but a failed connection's wait, and a
network change connects again at once."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

DEV = Path(__file__).resolve().parents[1] / "scripts" / "dev"
linux_only = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="the real mailboxes are Linux-only"
)

FAKE_CODEX = """
import json, os, sys, time
with open(os.environ["FAKE_CODEX_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "at": time.time()}) + "\\n")
raise SystemExit(int(os.environ.get("FAKE_CODEX_EXIT", "0")))
"""


def _load(name: str, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CHANNEL_ROOT", str(tmp_path / "channel"))
    spec = importlib.util.spec_from_file_location(
        f"{name}_under_test", DEV / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def waker_module(tmp_path, monkeypatch):
    return _load("laptop_waker", tmp_path, monkeypatch)


@pytest.fixture
def channel(tmp_path, monkeypatch):
    return _load("channel", tmp_path, monkeypatch)


@pytest.fixture
def codex(tmp_path, monkeypatch):
    script = tmp_path / "fake_codex.py"
    script.write_text(FAKE_CODEX, encoding="utf-8")
    log = tmp_path / "codex.log"
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    runs = lambda: (
        [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        if log.exists()
        else []
    )
    return [sys.executable, str(script)], runs


class FakeNetwork:
    """Waits on the process for real; a wait with no process records its
    timeout and returns at once; `changes` network changes come first."""

    def __init__(self, changes: int = 0) -> None:
        self.changes = changes
        self.backoffs: list[float] = []

    def wait(self, process, timeout):
        if process is None:
            self.backoffs.append(timeout)
            return "timeout"
        if self.changes:
            self.changes -= 1
            return "network"
        process.wait()
        return "exited"

    def close(self) -> None:
        pass


def _rounds(n: int):
    left = iter([True] * n + [False])
    return lambda: next(left)


def _waker(module, codex_command, network, tmp_path, channel_command=None):
    return module.Waker(
        channel_command or [sys.executable, str(DEV / "channel.py")],
        codex_command,
        network,
        delays=(1.0, 4.0),
        running=tmp_path / "laptop-agent.json",
    )


@linux_only
def test_waiting_mail_starts_one_run_with_the_fixed_prompt(
    waker_module, channel, codex, tmp_path
) -> None:
    command, runs = codex
    sent = channel.send("laptop", "round", "abc1234 handoff/laptop.md")
    waker = _waker(waker_module, command, FakeNetwork(), tmp_path)

    waker.serve(_rounds(1))

    [run] = runs()
    assert run["argv"] == [waker_module.PROMPT]  # never a message's text
    assert Path(run["cwd"]) == waker_module.REPO
    assert waker.after == sent["id"]
    assert not (tmp_path / "laptop-agent.json").exists()
    assert channel.pending("laptop")  # the run's agent says done, not the waker


@linux_only
def test_a_failed_run_is_told_and_only_newer_mail_starts_another(
    waker_module, channel, codex, tmp_path, monkeypatch
) -> None:
    command, runs = codex
    monkeypatch.setenv("FAKE_CODEX_EXIT", "3")
    channel.send("laptop", "round", "first")
    waker = _waker(waker_module, command, FakeNetwork(), tmp_path)
    thread = threading.Thread(target=waker.serve, args=(_rounds(2),), daemon=True)
    thread.start()

    [note] = channel.wait("devbox")
    assert note["kind"] == "note" and "exited 3" in note["text"]
    channel.done("devbox", [note["id"]])
    thread.join(0.3)
    assert (
        thread.is_alive() and len(runs()) == 1
    )  # the same mail does not start it again

    newer = channel.send("laptop", "note", "second")
    thread.join(10)
    assert not thread.is_alive()
    assert len(runs()) == 2 and runs()[1]["at"] > float(newer["id"].split("-")[0]) / 1e9


def test_a_failed_connection_waits_longer_each_time_up_to_the_cap(
    waker_module, codex, tmp_path
) -> None:
    command, runs = codex
    network = FakeNetwork()
    broken = [sys.executable, "-c", "raise SystemExit(255)"]
    waker = _waker(waker_module, command, network, tmp_path, channel_command=broken)

    waker.serve(_rounds(5))

    assert network.backoffs == [1.0, 2.0, 4.0, 4.0, 4.0]
    assert runs() == []


@linux_only
def test_a_network_change_connects_again_at_once(
    waker_module, channel, codex, tmp_path
) -> None:
    command, runs = codex
    channel.send("laptop", "round", "abc1234 handoff/laptop.md")
    network = FakeNetwork(changes=1)
    waker = _waker(waker_module, command, network, tmp_path)

    waker.serve(_rounds(2))

    assert network.backoffs == []
    assert len(runs()) == 1


def test_install_writes_a_startup_command_and_uninstall_removes_it(
    waker_module, tmp_path
) -> None:
    startup = tmp_path / "Startup"
    startup.mkdir()
    codex_path = r"C:\Program Files\Codex\codex.exe"
    args = [
        "install",
        "--dev",
        "devbox",
        "--codex",
        codex_path,
        "--codex-arg=--sandbox",
        "--startup-dir",
        str(startup),
    ]

    assert waker_module.main(args) == 0

    target = startup / waker_module.STARTUP_NAME
    text = target.read_bytes().decode("utf-8")
    assert text.startswith('@echo off\r\nstart "" ') and text.endswith("\r\n")
    assert f'"{codex_path}"' in text
    assert " run --dev devbox --codex " in text and "--codex-arg --sandbox" in text

    assert waker_module.main(["uninstall", "--startup-dir", str(startup)]) == 0
    assert not target.exists()


def test_install_refuses_what_cmd_would_read(waker_module, tmp_path) -> None:
    with pytest.raises(SystemExit):
        waker_module.main(
            [
                "install",
                "--dev",
                "dev%PATH%",
                "--codex",
                "codex",
                "--startup-dir",
                str(tmp_path),
            ]
        )


def test_only_one_waker_runs(waker_module, tmp_path) -> None:
    first = waker_module.single_instance(tmp_path / "waker.lock")
    try:
        assert first is not None
        assert waker_module.single_instance(tmp_path / "waker.lock") is None
    finally:
        first.close()
    again = waker_module.single_instance(tmp_path / "waker.lock")
    assert again is not None
    again.close()


@pytest.mark.skipif(os.name != "nt", reason="NotifyAddrChange is Windows")
def test_windows_network_wait_returns_on_process_exit_and_times_out(
    waker_module,
) -> None:
    network = waker_module.NetworkChanges()
    try:
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        assert network.wait(process, 10.0) == "exited"
        process.wait()
        assert network.wait(None, 0.05) in {"timeout", "network"}
    finally:
        network.close()
