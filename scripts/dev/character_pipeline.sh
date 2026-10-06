#!/bin/bash
# The machine spirit's character data, from the laptop agent's chats to the
# rows that pass the hard check (character_data.py has the steps):
#
#   personas  the built-in card (machine_spirit.py builtin)
#   import    the writer's answers (TASKS: persona and skeletons .json,
#             ANSWERS: its JSONL), checked like external-check, stamped
#   render    the app's own requests as rows
#   student   Gemma 4 E4B answers them (its own server)
#   check     the checker, Gemma 4 31B (another family than the writers),
#             answers every gate question and compares lines blind, both
#             orders
#   filter    the whole set or nothing (character_data.HARD_CHECK)
#
# The rows train together with the Agent's, one adapter for both (the
# product loads one); this script stops at the checked rows.
#
#   CHARDATA=.runtime/dev/chardata-ms8 TASKS=... ANSWERS=... scripts/dev/character_pipeline.sh
#   CHARDATA=... scripts/dev/character_pipeline.sh --status
#
# Every stage is resumable and leaves a marker in $DIR/state/. flock keeps one
# copy running; a dead server is restarted at once and a hung one within
# ~45 s; "not now" (GPU busy) exits 75 and is retried; a stage failing 3
# times in a row is marked .blocked until someone looks at it.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO" || exit 1
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export PYTHONUNBUFFERED=1

DIR=${CHARDATA:?set CHARDATA to the round's data folder}
export CHARDATA_DIR="$REPO/$DIR"
STATE=$DIR/state
LOGS=$DIR/logs
mkdir -p "$STATE" "$LOGS"
LOG=$LOGS/pipeline.log

CHECKER=${CHECKER:-.runtime/models/teacher/gemma-4-31B-it-UD-IQ3_XXS.gguf}
STUDENT_GGUF=${STUDENT_GGUF:-gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf}
E4B_MODELS=${E4B_MODELS:-.runtime/models/llm}  # the student, where the bench reads it too
TEACHER=$CHECKER  # the model the current stage's server runs; one at a time
TEACHER_PORT=18200
LLAMA_SERVER=${LLAMA_SERVER:-.runtime/tools/llama.cpp-b11179-src/build-cuda/bin/llama-server}
[ -x "$LLAMA_SERVER" ] || LLAMA_SERVER=llama-server
# Parallel requests per server on the shared 3090: Gemma 4 31B reads prompts
# slower the more sequences it holds (414 tokens/s with 1, 112 with 8), so the
# checker gets 2; the student 8 slots of 8192 (a machine-spirit chat fits).
CHECKER_SLOTS=${CHECKER_SLOTS:-2}
SLOTS=${SLOTS:-8}
SLOT_CTX=${SLOT_CTX:-8192}
SERVER_SLOTS=$SLOTS

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

if [ "${1:-}" = "--status" ]; then
    for f in scripts train student check train-checked; do
        printf '%-14s %s\n' "$f" "$(wc -l 2>/dev/null < "$DIR/$f.jsonl" || echo 0)"
    done
    [ -f "$DIR/filter.json" ] && echo "filter: $(tr -d '\n ' < "$DIR/filter.json")"
    echo "done:    $(cd "$STATE" && ls | grep -v '\.' | tr '\n' ' ')"
    blocked=$(cd "$STATE" && ls *.blocked 2>/dev/null | tr '\n' ' ')
    [ -n "$blocked" ] && echo "BLOCKED: $blocked (see $LOGS/<stage>.log)"
    tail -5 "$LOG" 2>/dev/null
    exit 0
fi

[ -e "$STATE/done" ] && exit 0
exec 9> "$STATE/.lock"
flock -n 9 || exit 0
DATA_JOB="" WATCHER="" TIMER=""
cleanup() { kill $WATCHER $TIMER $DATA_JOB 2>/dev/null; }
trap 'cleanup; exit 143' TERM INT HUP
trap cleanup EXIT

# shellcheck disable=SC1091
source .runtime/tools/env.sh


teacher_pid() {
    local pid
    for pid in $(pgrep -x llama-server); do
        if tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q -- "--port $TEACHER_PORT "; then
            echo "$pid"
            return
        fi
    done
}

health() { curl -sf -m 5 "http://127.0.0.1:$TEACHER_PORT/health" > /dev/null; }

teacher_up() {
    local pid; pid=$(teacher_pid)
    if [ -n "$pid" ] && ! tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q -- "$(basename "$TEACHER")"; then
        log "switching model to $(basename "$TEACHER")"
        teacher_down
        pid=""
    fi
    if [ -n "$pid" ]; then
        for _ in $(seq 150); do
            health && return 0
            kill -0 "$pid" 2>/dev/null || break
            sleep 2
        done
        kill -9 "$pid" 2>/dev/null
        sleep 2
    fi
    # The whole model on the GPU or not at all: with --fit it once started
    # while the previous model was still freeing its memory, left layers on
    # the CPU and wrote at a fifth of the speed. Wait for the room instead.
    local need=$(( $(stat -c %s "$TEACHER") / 1048576 + 3500 ))
    for _ in $(seq 60); do [ "$(free_mib)" -ge "$need" ] && break; sleep 30; done
    if [ "$(free_mib)" -lt "$need" ]; then
        log "only $(free_mib) MiB free, $(basename "$TEACHER") needs $need"
        return 75
    fi
    log "starting $(basename "$TEACHER") ($(free_mib) MiB free)"
    nohup "$LLAMA_SERVER" -m "$TEACHER" --host 127.0.0.1 --port "$TEACHER_PORT" \
        -ngl 99 --fit off -c $((SERVER_SLOTS * SLOT_CTX)) --parallel "$SERVER_SLOTS" -fa on \
        --cache-type-k q8_0 --cache-type-v q8_0 --jinja -t 12 \
        > "$LOGS/teacher.log" 2>&1 9>&- &
    for _ in $(seq 300); do
        health && return 0
        sleep 2
    done
    log "teacher did not come up"
    return 1
}

teacher_restart() {
    local pid; pid=$(teacher_pid)
    if [ -n "$pid" ]; then
        kill -9 "$pid" 2>/dev/null
        for _ in $(seq 50); do [ -z "$(teacher_pid)" ] && break; sleep 0.2; done
    fi
    teacher_up
}

teacher_down() {
    local pid; pid=$(teacher_pid)
    [ -n "$pid" ] || return 0
    kill "$pid"
    for _ in $(seq 120); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    log "teacher stopped"
}
free_mib() { nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1; }

# A data step under teacher supervision (see the first pipeline for why the
# watcher and the health checks look the way they do).
data() {
    teacher_up || return $?
    .venv/bin/python scripts/dev/character_data.py "$@" \
        --teacher-url "http://127.0.0.1:$TEACHER_PORT" --workers "$SERVER_SLOTS" &
    DATA_JOB=$!
    local job=$DATA_JOB misses=0 tp finished status
    while true; do
        tp=$(teacher_pid)
        if [ -z "$tp" ]; then
            log "teacher gone; restarting"
            teacher_restart || { kill "$job"; wait "$job"; DATA_JOB=""; return 1; }
            continue
        fi
        tail --pid="$tp" -f /dev/null 9>&- & WATCHER=$!
        sleep 10 9>&- & TIMER=$!
        wait -n -p finished "$job" "$WATCHER" "$TIMER"
        status=$?
        kill "$WATCHER" "$TIMER" 2>/dev/null
        wait "$WATCHER" "$TIMER" 2>/dev/null
        if [ "$finished" = "$job" ]; then
            DATA_JOB=""
            return "$status"
        fi
        if ! kill -0 "$tp" 2>/dev/null; then
            log "teacher exited; restarting"
            teacher_restart || { kill "$job"; wait "$job"; DATA_JOB=""; return 1; }
            misses=0
        elif health; then
            misses=0
        else
            misses=$((misses + 1))
            log "teacher health check failed ($misses/3)"
            if [ "$misses" -ge 3 ]; then
                log "teacher hung; restarting"
                teacher_restart || { kill "$job"; wait "$job"; DATA_JOB=""; return 1; }
                misses=0
            fi
        fi
    done
}

MAX_FAILS=3
stage() {
    local name=$1; shift
    [ -e "$STATE/$name" ] && return 0
    [ -e "$STATE/$name.blocked" ] && exit 0
    log "stage $name: start"
    "$@" >> "$LOGS/$name.log" 2>&1
    local rc=$?
    if [ "$rc" -eq 0 ]; then
        touch "$STATE/$name"
        rm -f "$STATE/$name.fails"
        log "stage $name: done"
        return 0
    fi
    if [ "$rc" -eq 75 ]; then
        log "stage $name: waiting (not possible right now), will retry"
        exit 0
    fi
    if [ "$rc" -eq 4 ]; then
        touch "$STATE/$name.blocked"
        log "stage $name: BLOCKED, the data here was made under other rules (scripts/dev/provenance.py); start a new data directory"
        exit 0
    fi
    if [ "$rc" -eq 3 ] && [[ $name == *filter ]]; then
        touch "$STATE/$name.blocked"
        log "stage $name: REFUSED by the quality check, nothing will be trained; see $DIR/filter.json"
        exit 0
    fi
    local fails=$(( $(cat "$STATE/$name.fails" 2>/dev/null || echo 0) + 1 ))
    echo "$fails" > "$STATE/$name.fails"
    if [ "$fails" -ge "$MAX_FAILS" ]; then
        touch "$STATE/$name.blocked"
        log "stage $name: BLOCKED after $fails failures in a row (exit $rc); see $LOGS/$name.log"
    else
        log "stage $name: FAILED (exit $rc, $fails/$MAX_FAILS), will resume on the next run"
    fi
    exit 1
}

checker() { TEACHER=$CHECKER SERVER_SLOTS=$CHECKER_SLOTS; data "$@"; }
student() {
    TEACHER=$E4B_MODELS/$STUDENT_GGUF SERVER_SLOTS=$SLOTS
    data student --student-url "http://127.0.0.1:$TEACHER_PORT"
}
step() { .venv/bin/python scripts/dev/character_data.py "$@"; }

stage personas .venv/bin/python scripts/dev/machine_spirit.py builtin --chardata "$DIR"
stage import step external-import --tasks "${TASKS:?set TASKS}" --file "${ANSWERS:?set ANSWERS}"
stage render step render
stage student student
stage check checker check
teacher_down
stage filter step filter
touch "$STATE/done"
log "character rows ready: $DIR/train-checked.jsonl"
