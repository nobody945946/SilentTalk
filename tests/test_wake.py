"""The dev box's wake trigger (scripts/dev/wake.py): a round handed to the
laptop is expected back within its hours, counted again from its receipt."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="the wake trigger runs on the Linux dev box",
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dev" / "wake.py"


@pytest.fixture
def wake(tmp_path, monkeypatch):
    monkeypatch.setenv("CHANNEL_ROOT", str(tmp_path / "channel"))
    monkeypatch.setenv("WAKE_STATE", str(tmp_path / "wake" / "state.json"))
    monkeypatch.delitem(sys.modules, "channel", raising=False)  # its spool is read at import
    spec = importlib.util.spec_from_file_location("wake_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("channel", None)


def test_a_receipt_starts_the_rounds_hours_again_and_a_report_ends_them(wake) -> None:
    assert wake.main(["round", "2", "abc1234 handoff/laptop.md"]) == 0
    state = wake.load()
    state["laptop_due"] = None  # the laptop was off: the round went overdue once
    wake.save(state)

    wake.channel.send("devbox", "received", "round 16 abc1234")
    wake.read_inbox()
    due = wake.load()["laptop_due"]
    assert due is not None and abs(due - (time.time() + 2 * 3600)) < 60

    wake.channel.send("devbox", "report", "laptop-report def5678 round 16 done")
    wake.read_inbox()
    assert wake.load()["laptop_due"] is None
    # A receipt after the report (a waker run's) opens nothing.
    wake.channel.done("devbox", [message["id"] for message in wake.channel.pending("devbox")])
    wake.channel.send("devbox", "received", "waker run ok")
    wake.read_inbox()
    assert wake.load()["laptop_due"] is None
