"""The dev box's mailboxes (scripts/dev/channel.py): a message stays until its
receiver says done, and every waiter wakes on it."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="the mailboxes live on the Linux dev box",
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dev" / "channel.py"


@pytest.fixture
def channel(tmp_path, monkeypatch):
    monkeypatch.setenv("CHANNEL_ROOT", str(tmp_path))
    spec = importlib.util.spec_from_file_location("channel_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _waiting(channel, box, after=None):
    result: list = []
    thread = threading.Thread(
        target=lambda: result.append(channel.wait(box, after)), daemon=True
    )
    thread.start()
    return thread, result


def test_a_message_stays_until_its_receiver_says_done(channel) -> None:
    sent = channel.send("laptop", "round", "abc1234 handoff/laptop.md")

    assert [m["id"] for m in channel.wait("laptop")] == [sent["id"]]
    # A waiter whose connection died has printed it into nothing: still there.
    assert [m["text"] for m in channel.pending("laptop")] == [
        "abc1234 handoff/laptop.md"
    ]

    assert channel.done("laptop", [sent["id"]]) == 1
    assert channel.pending("laptop") == []
    assert channel.done("laptop", [sent["id"]]) == 0


def test_every_waiter_wakes_on_one_message(channel) -> None:
    waiters = [_waiting(channel, "laptop") for _ in range(2)]
    sent = channel.send("laptop", "note", "hello")
    for thread, result in waiters:
        thread.join(5)
        assert not thread.is_alive()
        assert [m["id"] for m in result[0]] == [sent["id"]]


def test_a_wait_after_an_id_returns_only_when_a_newer_one_lands(channel) -> None:
    old = channel.send("laptop", "round", "old")
    thread, result = _waiting(channel, "laptop", old["id"])
    thread.join(0.3)
    assert thread.is_alive()  # only the old one is there

    new = channel.send("laptop", "note", "new")
    thread.join(5)
    assert not thread.is_alive()
    assert [m["id"] for m in result[0]] == [old["id"], new["id"]]


def test_done_takes_only_message_ids(channel) -> None:
    channel.send("laptop", "note", "x")
    for bad in ("../devbox/x", "1-2.json", "abc"):
        with pytest.raises(SystemExit):
            channel.done("laptop", [bad])
    assert len(channel.pending("laptop")) == 1


def test_the_command_line_waits_and_marks_done(tmp_path) -> None:
    env = {"CHANNEL_ROOT": str(tmp_path), "PATH": "/usr/bin:/bin"}

    def run(*args):
        done = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout

    sent = json.loads(run("send", "devbox", "report", "laptop-report 1234567"))
    printed = [json.loads(line) for line in run("wait", "devbox").splitlines()]
    assert [m["id"] for m in printed] == [sent["id"]]
    assert run("done", "devbox", sent["id"]).strip() == "1"
    later = json.loads(run("send", "devbox", "note", "later"))
    printed = [
        json.loads(line)
        for line in run("wait", "devbox", "--after", sent["id"]).splitlines()
    ]
    assert [m["id"] for m in printed] == [later["id"]]


@pytest.mark.parametrize(
    ("command", "words"),
    [
        (
            "python3 /home/clawd/SilentTalk/scripts/dev/channel.py wait laptop",
            ["wait", "laptop"],
        ),
        (
            "channel.py wait laptop --after 1791976126190482451-808389",
            ["wait", "laptop", "--after", "1791976126190482451-808389"],
        ),
        ("python3 channel.py done laptop 1-2 3-4", ["done", "laptop", "1-2", "3-4"]),
        (
            "python3 channel.py send devbox report laptop-report 1234567",
            ["send", "devbox", "report", "laptop-report", "1234567"],
        ),
    ],
)
def test_the_channel_key_runs_the_laptops_channel_commands(
    channel, command, words
) -> None:
    assert channel.gate(command) == words


@pytest.mark.parametrize(
    "command",
    [
        "",
        "bash",
        "cat ~/.ssh/authorized_keys",
        "python3 channel.py wait devbox",
        "python3 channel.py send laptop round x",
        "python3 channel.py send devbox shell x",
        "python3 channel.py done laptop ../devbox/x",
        "python3 channel.py done devbox 1-2",
        "python3 channel.py wait laptop; rm -rf ~",
        "python3 channel.py wait laptop --after $(id)",
        "python3 channel.py send devbox note it's",
        "python3 other.py wait laptop",
    ],
)
def test_the_channel_key_runs_nothing_else(channel, command) -> None:
    with pytest.raises(SystemExit):
        channel.gate(command)


def test_the_gate_runs_the_command_ssh_was_given(tmp_path) -> None:
    env = {"CHANNEL_ROOT": str(tmp_path), "PATH": "/usr/bin:/bin"}
    sent = subprocess.run(
        [sys.executable, str(SCRIPT), "gate"],
        capture_output=True,
        text=True,
        env={
            **env,
            "SSH_ORIGINAL_COMMAND": f"python3 {SCRIPT} send devbox note hello there",
        },
        timeout=10,
        check=False,
    )
    assert sent.returncode == 0, sent.stderr
    assert json.loads(sent.stdout)["text"] == "hello there"
    refused = subprocess.run(
        [sys.executable, str(SCRIPT), "gate"],
        capture_output=True,
        text=True,
        env={**env, "SSH_ORIGINAL_COMMAND": "id"},
        timeout=10,
        check=False,
    )
    assert refused.returncode != 0 and refused.stdout == ""
