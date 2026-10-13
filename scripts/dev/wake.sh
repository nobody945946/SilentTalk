#!/bin/bash
# The dev-box session's wake trigger (handoff/dev-box.md §4 rule 11). The
# owner, 2026-10-09: the session finds problems itself, but it is woken only at
# the nodes that need it; no resident loop, no heartbeat, no fixed-interval
# asking, no log files.
#
# It waits only for what is pending, the way that thing can signal:
# - The queue, while it runs: the kernel wakes the wait when queue.log grows
#   (tail -F uses inotify); a step event, a yield or an error wakes the session.
#   A long step logs only progress lines, so the harness's 2 h limit with fresh
#   lines is a quiet re-arm (ALIVE); an hour without the log growing is a hang (SILENCE).
# - CI: only the pushes recorded with `wake.sh ci`, every 5 minutes until their
#   runs finish; a failure wakes the session, a success is dropped.
# - The laptop: only while a round handed over with `wake.sh handoff` is not
#   reported. GitHub cannot tell this machine when the laptop pushed, so it is
#   asked when the round could be done (its expected length after the laptop's
#   receipt) and when the harness ends the wait (2 h). A report wakes the
#   session; so does a received round still unreported after its expected
#   time (once). No receipt yet means the laptop has not been opened since.
#   The laptop's side is one silent push per round (laptop-received).
# - Nothing pending: it exits at once and the session does not re-arm it.
#
#   wake.sh                        wait (run in the background; re-arm after it exits)
#   wake.sh handoff <hours>        record the laptop round just pushed (the last
#                                  commit that changed handoff/laptop.md)
#   wake.sh ci <owner/repo> <sha>  watch that push's CI runs (the full 40-character sha)
set -u
ST=/home/clawd/SilentTalk
LOG=${WAKE_LOG:-/home/clawd/EdgeAgent/.runtime/fw/queue.log}
DIR=${WAKE_STATE:-$ST/.runtime/wake}
STATE=$DIR/laptop    # pending= hours= report0= received_at= alarmed=
CIWATCH=$DIR/ci      # "owner/repo sha" per line
RE='^== |^relaunch|queue finished|^Traceback|^SystemExit|stopped|OOM|out of memory|judge rejected|"trusted"|containment FAILED|did not become ready|llama-server exited|server exited|saved adapter|saved the epoch|peak GPU|skipped \{|tasks hold in|cards retired|[0-9]+ tasks -> |rows; skipped|rows -> '
LIMIT=${WAKE_LIMIT:-7000}  # the harness ends a background job at 2 h
QUIET=${WAKE_QUIET:-3600}  # a running queue that logs nothing this long is hung
mkdir -p "$DIR"

ref() { git ls-remote https://github.com/nobody945946/SilentTalk "refs/heads/$1" 2>/dev/null | cut -c1-40; }
# A queue relaunched while its old step still runs waits in relaunch.sh for the
# lock; that step keeps writing the log, so it counts as running (2026-10-13:
# the wake exited with NOTHING PENDING through a 7-hour recording).
queue_running() { pgrep -f '^bash \.runtime/fw/(queue|relaunch)\.sh$' >/dev/null; }
set_state() { touch "$STATE"; sed -i "/^$1=/d" "$STATE"; echo "$1=$2" >> "$STATE"; }
load_state() { pending="" hours="" report0="" received_at="" alarmed=""; [ -f "$STATE" ] && . "$STATE"; }
ci_pending() { [ -s "$CIWATCH" ]; }

case "${1:-}" in
  handoff)
    : > "$STATE"
    set_state pending "$(git -C "$ST" log -1 --format=%H origin/copilot-story-mode -- handoff/laptop.md)"
    set_state hours "${2:?expected hours}"
    set_state report0 "$(ref laptop-report)"
    cat "$STATE"; exit 0 ;;
  ci)
    [[ ${3:-} =~ ^[0-9a-f]{40}$ ]] || { echo "the full sha, please" >&2; exit 2; }
    echo "${2:?owner/repo} $3" >> "$CIWATCH"; exit 0 ;;
esac

ci_check() {  # drops finished runs; prints failures
  local repo sha runs keep=""
  while read -r repo sha; do
    [ -z "${sha:-}" ] && continue
    runs=$(gh api "repos/$repo/actions/runs?head_sha=$sha" \
      --jq '.workflow_runs[] | "\(.status) \(.conclusion) \(.id) \(.head_branch)"' 2>/dev/null)
    if [ -z "$runs" ] || echo "$runs" | rg -q '^(queued|in_progress|waiting|pending|requested) '; then
      keep+="$repo $sha"$'\n'
    else
      echo "$runs" | rg -v '^completed (success|skipped) ' | sed "s|^|CI FAILED: $repo ${sha:0:7} |"
    fi
  done < "$CIWATCH"
  printf '%s' "$keep" > "$CIWATCH"
}

laptop_check() {  # notes the receipt; prints a report or a stall
  load_state
  [ -z "$pending" ] && return
  local now received
  now=$(ref laptop-report)
  if [ -n "$now" ] && [ "$now" != "$report0" ]; then
    : > "$STATE"
    echo "LAPTOP REPORT: laptop-report moved ${report0:0:7} -> ${now:0:7}"; return
  fi
  if [ -z "$received_at" ]; then
    received=$(ref laptop-received)
    if [ -n "$received" ] && git -C "$ST" fetch -q origin laptop-received 2>/dev/null \
        && git -C "$ST" merge-base --is-ancestor "$pending" "$received" 2>/dev/null; then
      received_at=$(date +%s); set_state received_at "$received_at"
    fi
  fi
  if [ -n "$received_at" ] && [ -z "$alarmed" ] && [ $(( $(date +%s) - received_at )) -ge $(( hours * 3600 )) ]; then
    set_state alarmed 1
    echo "LAPTOP STALLED: received ${pending:0:7} $(( ($(date +%s) - received_at) / 60 )) min ago, no report (expected ${hours} h)"
  fi
}

next_ask() {  # when GitHub is next worth asking (epoch)
  local at=$deadline now; now=$(date +%s)
  if ci_pending && [ $((now + 300)) -lt "$at" ]; then at=$((now + 300)); fi
  load_state
  if [ -n "$pending" ] && [ -n "$received_at" ] && [ -z "$alarmed" ]; then
    local due=$((received_at + hours * 3600))
    [ "$due" -lt "$at" ] && at=$due
  fi
  [ "$at" -le "$now" ] && at=$((now + 60))
  echo "$at"
}

start=$(date +%s); deadline=$((start + LIMIT))
from=$(($(wc -l < "$LOG") + 1))
load_state
if ! queue_running && ! ci_pending && [ -z "$pending" ]; then
  echo "NOTHING PENDING: not re-armed"; exit 0
fi
found="" mode=asleep lines=0 last=$start
if queue_running; then
  mode=awake
  coproc TAIL { exec tail -n 0 -F "$LOG" 2>/dev/null; }
fi
while [ -z "$found" ]; do
  ask=$(next_ask)
  wait_s=$((ask - $(date +%s))); [ "$wait_s" -lt 1 ] && wait_s=1
  if [ "$mode" = awake ]; then
    # Blocks in the kernel until the log grows, GitHub is due or the log has
    # been quiet for an hour.
    until_s() { local t=$ask; [ $((last + QUIET)) -lt "$t" ] && t=$((last + QUIET)); echo $((t - $(date +%s))); }
    wait_s=$(until_s); [ "$wait_s" -lt 1 ] && wait_s=1
    while IFS= read -r -t "$wait_s" line <&"${TAIL[0]}"; do
      lines=$((lines + 1)) last=$(date +%s)
      [[ $line =~ $RE ]] && { found="$line"; break; }
      wait_s=$(until_s); [ "$wait_s" -lt 1 ] && break
    done
    [ -n "$found" ] && break
    # A progress bar rewrites its line with \r: the log grows, no line ends.
    grown=$(stat -c %Y "$LOG" 2>/dev/null || echo 0); [ "$grown" -gt "$last" ] && last=$grown
  else
    sleep "$wait_s"
  fi
  if [ "$(date +%s)" -ge "$ask" ]; then
    out=$( { ci_pending && ci_check; }; laptop_check )
    [ -n "$out" ] && { found="$out"; break; }
  fi
  if [ "$mode" = awake ] && [ $(( $(date +%s) - last )) -ge "$QUIET" ]; then
    found="SILENCE: the log has not grown for $(( ($(date +%s) - last) / 60 )) min"
  elif [ "$(date +%s)" -ge "$deadline" ]; then
    [ "$mode" = awake ] && found="ALIVE: $lines progress lines, no step event; re-arm" || found="ASLEEP: nothing happened; re-arm"
  fi
done
[ -n "${TAIL_PID:-}" ] && kill "$TAIL_PID" 2>/dev/null
echo "$(date '+%F %T') ($mode)"
echo "$found"
if [ "$mode" = awake ]; then
  tail -n +"$from" "$LOG" | rg "$RE" | head -30 | rg -vxF "$found"
  echo "--- last lines:"; tail -n 3 "$LOG" | cut -c1-200
fi
exit 0
