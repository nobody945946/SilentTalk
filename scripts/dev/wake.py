"""The dev-box session's wake trigger (handoff/dev-box.md §4 rule 10). The
session finds problems itself but is woken only when something happened;
nothing here asks at a fixed interval (the owner, 2026-10-14).

One wait, on whatever can signal:
- The laptop: its messages (channel.py; it sends over its SSH session) ring
  this box's doorbell, so the kernel wakes the wait. A round handed over with
  `wake.py round` is expected back within its hours; if no report message has
  come by then, that wakes the session once.
- The queue, while it runs: tail -F (inotify) wakes the wait when queue.log
  grows; a step event, a yield or an error wakes the session; an hour without
  the log growing is a hang (SILENCE).
- CI: GitHub cannot reach this box, so a push recorded with `wake.py ci` is
  asked about once, when its runs should be done (the repo's recent run
  times); a run still going is asked again only after half that time. A
  failure wakes the session; a success wakes it only when the push was
  recorded with what waits on it (a handoff held until CI is green).
- The harness ends a background job at 2 h: the wait exits before (ALIVE or
  ASLEEP) and the session re-arms it.

  python3 scripts/dev/wake.py                          wait (background; re-arm after it exits)
  python3 scripts/dev/wake.py ci <owner/repo> <sha> [<what waits>]
                                                       watch that push's CI (the full sha); with
                                                       what waits on it, a success wakes too
  python3 scripts/dev/wake.py round <hours> <text>     tell the laptop a round is pushed (text:
                                                       commit and path) and expect its report
"""

from __future__ import annotations

import json
import os
import re
import selectors
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import channel  # noqa: E402

ST = Path(__file__).resolve().parents[2]
LOG = Path(os.environ.get("WAKE_LOG", "/home/clawd/EdgeAgent/.runtime/fw/queue.log"))
STATE = Path(os.environ.get("WAKE_STATE", ST / ".runtime" / "wake" / "state.json"))
EVENT = re.compile(
    r'^== |^relaunch|queue finished|^Traceback|^SystemExit|stopped|OOM|out of memory|judge rejected|"trusted"'
    r"|containment FAILED|did not become ready|llama-server exited|server exited|saved adapter|saved the epoch"
    r"|peak GPU|skipped \{|tasks hold in|cards retired|[0-9]+ tasks -> |rows; skipped|rows -> "
)
LIMIT = float(os.environ.get("WAKE_LIMIT", 7000))  # the harness ends a background job at 2 h
QUIET = float(os.environ.get("WAKE_QUIET", 3600))  # a running queue that logs nothing this long is hung
CI_DEFAULT = 600.0


def load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"ci": [], "laptop_due": None}


def save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    os.replace(temporary, STATE)
    channel.ring("devbox")  # a waiting wake picks up the new times


def gh(path: str, jq: str) -> list[str]:
    done = subprocess.run(["gh", "api", path, "--jq", jq], capture_output=True, text=True, timeout=60)
    return done.stdout.split("\n") if done.returncode == 0 else []


def ci_expected(repo: str) -> float:
    """How long the repo's recent successful runs took (the longest)."""
    lines = gh(f"repos/{repo}/actions/runs?status=success&per_page=10",
               ".workflow_runs[] | [.run_started_at, .updated_at] | @tsv")
    took = []
    for line in filter(None, lines):
        start, end = line.split("\t")
        took.append(datetime.fromisoformat(end.replace("Z", "+00:00")).timestamp()
                    - datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp())
    return max(took) + 30 if took else CI_DEFAULT


def ci_check(entry: dict) -> tuple[str, float | None]:
    """(failures to report, or "", and the next time to ask, or None when done)."""
    lines = [line for line in gh(f"repos/{entry['repo']}/actions/runs?head_sha={entry['sha']}",
                                 '.workflow_runs[] | "\\(.status) \\(.conclusion) \\(.id) \\(.head_branch)"') if line]
    if not lines or any(line.split()[0] in {"queued", "in_progress", "waiting", "pending", "requested"} for line in lines):
        return "", time.time() + max(60.0, entry["expected"] / 2)
    failed = [line for line in lines if not re.match(r"completed (success|skipped) ", line)]
    if not failed and entry.get("waits"):
        return f"CI GREEN: {entry['repo']} {entry['sha'][:7]}; now: {entry['waits']}", None
    return "\n".join(f"CI FAILED: {entry['repo']} {entry['sha'][:7]} {line}" for line in failed), None


def queue_running() -> bool:
    # A queue relaunched while its old step still runs waits in relaunch.sh
    # for the lock; that step keeps writing the log, so it counts as running.
    return subprocess.run(["pgrep", "-f", r"^bash \.runtime/fw/(queue|relaunch)\.sh$"],
                          capture_output=True).returncode == 0


def wait() -> int:
    start = time.time()
    deadline = start + LIMIT
    selector = selectors.DefaultSelector()
    inbox = channel.bell("devbox")
    selector.register(inbox, selectors.EVENT_READ, "inbox")
    tail = None
    if queue_running():
        tail = subprocess.Popen(["tail", "-n", "0", "-F", str(LOG)], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        os.set_blocking(tail.stdout.fileno(), False)
        selector.register(tail.stdout, selectors.EVENT_READ, "log")
    found, events, buffer, lines, last = "", [], b"", 0, start
    try:
        while not found:
            state = load()
            timers = [deadline] + [entry["due"] for entry in state["ci"]]
            if state.get("laptop_due"):
                timers.append(state["laptop_due"])
            if tail is not None:
                timers.append(last + QUIET)
            for key, _ in selector.select(max(0.0, min(timers) - time.time())):
                if key.data == "inbox":
                    channel.drain(inbox)
                    messages = channel.take("devbox")
                    if messages:
                        if any(message["kind"] == "report" for message in messages):
                            state = load()
                            state["laptop_due"] = None
                            STATE.parent.mkdir(parents=True, exist_ok=True)
                            STATE.write_text(json.dumps(state), encoding="utf-8")
                        found = "\n".join("LAPTOP: " + json.dumps(m, ensure_ascii=False) for m in messages)
                else:
                    chunk = os.read(tail.stdout.fileno(), 65536)
                    buffer += chunk
                    *complete, buffer = buffer.split(b"\n")
                    for raw in complete:
                        line = raw.decode("utf-8", "replace")
                        lines, last = lines + 1, time.time()
                        if EVENT.search(line):
                            events.append(line)
                            found = found or line
            if found:
                break
            now = time.time()
            state, reports = load(), []
            for entry in list(state["ci"]):
                if entry["due"] <= now:
                    report, again = ci_check(entry)
                    state["ci"].remove(entry)
                    if again is not None:
                        state["ci"].append({**entry, "due": again})
                    if report:
                        reports.append(report)
            if state.get("laptop_due") and state["laptop_due"] <= now:
                reports.append(f"LAPTOP OVERDUE: no report for the round sent {state.get('laptop_round', '')}")
                state["laptop_due"] = None
            if state != load():
                STATE.write_text(json.dumps(state), encoding="utf-8")
            if reports:
                found = "\n".join(reports)
            elif tail is not None and max(last, LOG.stat().st_mtime) + QUIET <= now:
                found = f"SILENCE: the log has not grown for {round((now - last) / 60)} min"
            elif tail is not None and LOG.stat().st_mtime > last:
                last = LOG.stat().st_mtime  # a progress bar rewrites its line with \r
            elif now >= deadline:
                found = (f"ALIVE: {lines} progress lines, no step event; re-arm" if tail is not None
                         else "ASLEEP: nothing happened; re-arm")
    finally:
        if tail is not None:
            tail.kill()
        os.close(inbox)
    print(f"{time.strftime('%F %T')} ({'awake' if tail is not None else 'asleep'})")
    print(found)
    for line in events[:30]:
        if line != found:
            print(line)
    if tail is not None:
        print("--- last lines:")
        print("\n".join(LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-3:])[:600])
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "ci":
        if not re.fullmatch(r"[0-9a-f]{40}", argv[2]):
            raise SystemExit("the full sha, please")
        expected = ci_expected(argv[1])
        state = load()
        state["ci"].append({"repo": argv[1], "sha": argv[2], "expected": expected, "due": time.time() + expected,
                            "waits": " ".join(argv[3:])})
        save(state)
        print(f"CI of {argv[1]} {argv[2][:7]} asked about in {round(expected / 60)} min")
        return 0
    if len(argv) >= 3 and argv[0] == "round":
        hours, text = float(argv[1]), " ".join(argv[2:])
        message = channel.send("laptop", "round", text)
        state = load()
        state["laptop_due"], state["laptop_round"] = time.time() + hours * 3600, text
        save(state)
        print(json.dumps(message, ensure_ascii=False))
        return 0
    if not argv:
        return wait()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
