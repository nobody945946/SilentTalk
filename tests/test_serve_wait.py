"""scripts/dev/serve_wait.py: a llama-server is ready when it says it is
listening, and one that exits while loading is reported at once, with its
last lines. A fake server stands in (no model, no GPU)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "dev"))

import serve_wait  # noqa: E402

FAKE = """
import sys, time
mode = sys.argv[1]
say = lambda line: print(line, file=sys.stderr, flush=True)
say("0.00.000.355 I srv  llama_server: initializing ...")
say("0.00.055.014 I srv    load_model: loading model 'fake.gguf'")
if mode == "dies":
    say("0.00.100.000 E srv    load_model: failed to load model 'fake.gguf'")
    sys.exit(3)
if mode == "hangs":
    time.sleep(600)
time.sleep(0.2)
say("0.02.486.788 I srv  llama_server: model loaded")
say("0.02.486.790 I srv  llama_server: listening on http://127.0.0.1:18189")
if mode == "chatty":
    for task in range(20000):  # far more than a pipe holds
        print(f"0.03.000.000 I slot print_timing: id  1 | task {task} | total time = 1.0 ms")
    sys.exit(0)
time.sleep(600)
"""


@pytest.fixture
def fake(tmp_path: Path) -> Path:
    path = tmp_path / "fake_server.py"
    path.write_text(FAKE, encoding="utf-8")
    return path


def _stop(process: subprocess.Popen) -> None:
    process.terminate()
    process.wait(timeout=30)


def test_start_returns_once_the_server_says_it_is_listening(fake, tmp_path):
    log = tmp_path / "server.log"
    process = serve_wait.start([sys.executable, str(fake), "listens"], log=log, timeout=60)
    try:
        assert process.poll() is None
        assert "llama_server: listening on http://127.0.0.1:18189" in log.read_text(encoding="utf-8")
    finally:
        _stop(process)


def test_the_output_after_ready_keeps_being_read(fake):
    process = serve_wait.start([sys.executable, str(fake), "chatty"], timeout=60)
    # Undrained, the fake would block on a full pipe and never exit.
    assert process.wait(timeout=60) == 0


def test_a_server_that_exits_while_loading_is_reported_at_once_with_its_last_lines(fake):
    started = time.monotonic()
    with pytest.raises(serve_wait.NotListening) as failed:
        serve_wait.start([sys.executable, str(fake), "dies"], timeout=300)
    assert time.monotonic() - started < 60
    assert failed.value.exited
    assert "exited (3) before it was listening" in str(failed.value)
    assert "failed to load model 'fake.gguf'" in str(failed.value)


def test_a_server_not_listening_by_the_deadline_is_stopped(fake):
    with pytest.raises(serve_wait.NotListening) as failed:
        serve_wait.start([sys.executable, str(fake), "hangs"], timeout=1)
    assert not failed.value.exited
    assert "did not become ready in 1 s (stopped it)" in str(failed.value)
    assert "loading model 'fake.gguf'" in str(failed.value)


# character_pipeline.sh's servers write their own log; the wait follows it
# (tail -F) and the server's exit (a pidfd).
linux = pytest.mark.skipif(sys.platform != "linux", reason="the pipeline's wait is Linux only")


def _server_into(log: Path, fake: Path, mode: str) -> subprocess.Popen:
    with log.open("ab") as handle:
        return subprocess.Popen([sys.executable, str(fake), mode], stdout=handle,
                                stderr=subprocess.STDOUT)


@linux
def test_the_pipeline_wait_reads_only_this_start_of_the_log(fake, tmp_path):
    log = tmp_path / "write-server.log"
    log.write_text("0.02.486.790 I srv  llama_server: listening on http://127.0.0.1:18200\n"
                   "0.09.000.000 I srv  llama_server: cleaning up before exit...\n", encoding="utf-8")
    offset = log.stat().st_size
    process = _server_into(log, fake, "hangs")
    try:
        assert serve_wait.main([str(log), str(process.pid), "--from", str(offset), "--timeout", "1"]) == 2
    finally:
        _stop(process)
    offset = log.stat().st_size
    process = _server_into(log, fake, "listens")
    try:
        assert serve_wait.main([str(log), str(process.pid), "--from", str(offset), "--timeout", "60"]) == 0
    finally:
        _stop(process)


@linux
def test_the_pipeline_wait_reports_a_server_exit_at_once(fake, tmp_path, capsys):
    log = tmp_path / "student-server.log"
    process = _server_into(log, fake, "dies")
    started = time.monotonic()
    try:
        assert serve_wait.main([str(log), str(process.pid), "--timeout", "300"]) == 1
    finally:
        process.wait(timeout=30)
    assert time.monotonic() - started < 60
    out = capsys.readouterr().out
    assert f"llama-server {process.pid} exited before it was listening" in out
    assert "failed to load model 'fake.gguf'" in out
