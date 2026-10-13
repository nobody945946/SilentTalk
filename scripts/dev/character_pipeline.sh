#!/bin/bash
# The machine spirit's character data, from the teacher's chats to the rows
# that pass the hard check (character_data.py has the steps):
#
#   personas  the built-in card (machine_spirit.py builtin)
#   write     the dev box's teacher, Qwen3.8-27B (WRITER), writes the chats
#             (character_data.py write; WRITE_ARGS are passed on)
#   render    the app's own requests as rows
#   student   Gemma 4 E4B answers them
#   check     the checker, Gemma 4 31B (another family than the teacher),
#             answers every gate question and compares lines blind, both
#             orders
#   filter    the whole set or nothing (chardata_filter.HARD_CHECK);
#             LINES_BY_RULES=1: lines need only the app's rules (no ranking)
#
# The rows train together with the Agent's, one adapter for both (the
# product loads one); this script stops at the checked rows.
#
#   CHARDATA=.runtime/dev/chardata-ms10 scripts/dev/character_pipeline.sh
#   CHARDATA=... scripts/dev/character_pipeline.sh --status
#
# write, student and check each start their own llama-server, a child of
# this script on port 18200, its output in $LOGS/<stage>-server.log. The
# server is ready when it says it is listening there (serve_wait.py: the log
# and the server's exit, whichever comes first, no asking at an interval);
# the step then runs, and whichever of the two ends first wakes the script.
# The server is stopped when its step ends.
#
# Nothing here waits for the GPU, retries or restarts a server: every problem
# stops the run for the live session to look at, and a rerun resumes at the
# stage that stopped (each finished stage leaves a marker in $DIR/state/;
# flock keeps one copy running). Exit status:
#   0  done (or already done)
#   1  a stage failed, its server exited or did not come up, or another copy
#      holds the lock (see $LOGS/pipeline.log, <stage>.log, <stage>-server.log)
#   2  a stage is blocked, $STATE/<stage>.blocked: its data was made under
#      other rules (a step's exit 4: start a new data directory) or the hard
#      check refused the set (filter's exit 3); a rerun does not unblock it
#   3  the GPU lacks the room for the stage's model (free, needed and the
#      processes holding it are logged)
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO" || exit 1
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export PYTHONUNBUFFERED=1

DIR=${CHARDATA:?set CHARDATA to the data folder of this round}
export CHARDATA_DIR="$REPO/$DIR"
STATE=$DIR/state
LOGS=$DIR/logs
mkdir -p "$STATE" "$LOGS"
LOG=$LOGS/pipeline.log

PY=.venv/bin/python
WRITER=${WRITER:-.runtime/models/teacher/Qwen3.8-27B-UD-IQ3_XXS.gguf}  # EdgeAgent's teacher-38-iq3
CHECKER=${CHECKER:-.runtime/models/teacher/gemma-4-31B-it-UD-IQ3_XXS.gguf}
STUDENT_GGUF=${STUDENT_GGUF:-gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf}
E4B_MODELS=${E4B_MODELS:-.runtime/models/llm}  # the student, where the bench reads it too
LLAMA_SERVER=${LLAMA_SERVER:-.runtime/tools/llama.cpp-b11179-src/build-cuda/bin/llama-server}
NVIDIA_SMI=${NVIDIA_SMI:-nvidia-smi}
PORT=18200
LOAD_SECONDS=900  # the one deadline, for a load that hangs; an exit is noticed at once
# Parallel requests per server on the shared 3090: Gemma 4 31B reads prompts
# slower the more sequences it holds (414 tokens/s with 1, 112 with 8), so the
# checker gets 2; the student 8 slots of 8192 (a machine-spirit chat fits);
# the writer 4 of 16384.
WRITER_SLOTS=${WRITER_SLOTS:-4}
WRITER_CTX=${WRITER_CTX:-16384}
CHECKER_SLOTS=${CHECKER_SLOTS:-2}
SLOTS=${SLOTS:-8}
SLOT_CTX=${SLOT_CTX:-8192}

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

if [ "${1:-}" = "--status" ]; then
    for f in scripts train student check train-checked; do
        printf '%-14s %s\n' "$f" "$(wc -l 2>/dev/null < "$DIR/$f.jsonl" || echo 0)"
    done
    [ -f "$DIR/filter.json" ] && echo "filter: $(tr -d '\n ' < "$DIR/filter.json")"
    echo "done:    $(cd "$STATE" && ls | grep -v '\.' | tr '\n' ' ')"
    blocked=$(cd "$STATE" && ls -- *.blocked 2>/dev/null | tr '\n' ' ')
    [ -n "$blocked" ] && echo "BLOCKED: $blocked (see $LOGS/<stage>.log)"
    tail -5 "$LOG" 2>/dev/null
    exit 0
fi

[ -e "$STATE/done" ] && exit 0
exec 9> "$STATE/.lock"
if ! flock -n 9; then
    echo "another copy is working on $DIR" >&2
    exit 1
fi

# This script's children, stopped with it: the stage's server, the wait for
# it to listen and the step that uses it.
SERVER="" WAITER="" DATA_JOB="" STAGE=""
cleanup() {
    [ -n "$SERVER$WAITER$DATA_JOB" ] || return 0
    # shellcheck disable=SC2086  # the empty ones drop out
    kill $WAITER $DATA_JOB $SERVER 2>/dev/null
    # shellcheck disable=SC2086
    wait $WAITER $DATA_JOB $SERVER 2>/dev/null
}
trap 'cleanup; exit 143' TERM INT HUP
trap cleanup EXIT

stop_server() {
    [ -n "$SERVER" ] || return 0
    kill "$SERVER" 2>/dev/null
    wait "$SERVER"
    SERVER=""
}

# serve MODEL SLOTS SLOT_CTX: the stage's llama-server, listening on $PORT.
serve() {
    local model=$1 slots=$2 ctx=$3 log=$LOGS/$STAGE-server.log
    if [ ! -x "$LLAMA_SERVER" ] || [ ! -f "$model" ]; then
        log "stage $STAGE: no llama-server at $LLAMA_SERVER or no model at $model"
        return 1
    fi
    # The whole model on the GPU or not at all (--fit off): with --fit it once
    # started while the previous model was still freeing its memory, left
    # layers on the CPU and wrote at a fifth of the speed. The GPU is shared:
    # the room is checked once, and too little stops the run (exit 3) for the
    # session to decide when to start again.
    local need free
    need=$(( $(stat -c %s "$model") / 1048576 + 3500 ))
    free=$("$NVIDIA_SMI" --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    case $free in
        ''|*[!0-9]*) log "stage $STAGE: nvidia-smi gave no free memory ('$free')"; return 1 ;;
    esac
    if [ "$free" -lt "$need" ]; then
        log "stage $STAGE: only $free MiB free on the GPU, $(basename "$model") needs $need; the GPU holds:"
        "$NVIDIA_SMI" --query-compute-apps=pid,used_memory,process_name --format=csv,noheader | tee -a "$LOG"
        exit 3
    fi
    local from
    from=$(stat -c %s "$log" 2>/dev/null || echo 0)
    log "stage $STAGE: starting $(basename "$model"), $slots slots of $ctx ($free MiB free)"
    "$LLAMA_SERVER" -m "$model" --host 127.0.0.1 --port "$PORT" -ngl 99 --fit off \
        -c $((slots * ctx)) --parallel "$slots" -fa on --cache-type-k q8_0 --cache-type-v q8_0 \
        --jinja -t 12 >> "$log" 2>&1 9>&- &
    SERVER=$!
    # In the background so that a TERM to this script is handled at once.
    "$PY" scripts/dev/serve_wait.py "$log" "$SERVER" --from "$from" --timeout "$LOAD_SECONDS" 9>&- &
    WAITER=$!
    wait "$WAITER"
    local rc=$?
    WAITER=""
    if [ "$rc" -ne 0 ]; then
        log "stage $STAGE: llama-server did not come up (see $LOGS/$STAGE.log and $log)"
        stop_server
        return 1
    fi
}

# served MODEL SLOTS SLOT_CTX STEP [ARGS...]: a character_data.py step
# against its own server.
served() {
    local model=$1 slots=$2 ctx=$3 step=$4
    shift 4
    serve "$model" "$slots" "$ctx" || return 1
    "$PY" scripts/dev/character_data.py "$step" --teacher-url "http://127.0.0.1:$PORT" \
        --workers "$slots" "$@" 9>&- &
    DATA_JOB=$!
    # Whichever ends first; bash wakes on the child's exit.
    local finished rc
    wait -n -p finished "$DATA_JOB" "$SERVER"
    rc=$?
    if [ "$finished" = "$SERVER" ]; then
        SERVER=""
        log "stage $STAGE: server exited (exit $rc) while the step ran (see $LOGS/$STAGE-server.log)"
        kill "$DATA_JOB" 2>/dev/null
        wait "$DATA_JOB"
        DATA_JOB=""
        return 1
    fi
    DATA_JOB=""
    stop_server
    return "$rc"
}

step() { "$PY" scripts/dev/character_data.py "$@"; }

# stage NAME COMMAND...: once per data directory; its output in $LOGS/NAME.log.
stage() {
    local name=$1
    shift
    [ -e "$STATE/$name" ] && return 0
    if [ -e "$STATE/$name.blocked" ]; then
        log "stage $name: BLOCKED (see $LOGS/$name.log); $STATE/$name.blocked stays until someone decides"
        exit 2
    fi
    STAGE=$name
    log "stage $name: start"
    "$@" >> "$LOGS/$name.log" 2>&1
    local rc=$?
    if [ "$rc" -eq 0 ]; then
        touch "$STATE/$name"
        log "stage $name: done"
        return 0
    fi
    if [ "$rc" -eq 4 ]; then
        touch "$STATE/$name.blocked"
        log "stage $name: BLOCKED, the data here was made under other rules (scripts/dev/provenance.py); start a new data directory"
        exit 2
    fi
    if [ "$rc" -eq 3 ] && [[ $name == *filter ]]; then
        touch "$STATE/$name.blocked"
        log "stage $name: REFUSED by the quality check, nothing will be trained; see $DIR/filter.json"
        exit 2
    fi
    log "stage $name: FAILED (exit $rc); see $LOGS/$name.log"
    exit 1
}

stage personas "$PY" scripts/dev/machine_spirit.py builtin --chardata "$DIR"
# shellcheck disable=SC2086  # WRITE_ARGS: more arguments for the step, split on purpose
stage write served "$WRITER" "$WRITER_SLOTS" "$WRITER_CTX" write ${WRITE_ARGS:-}
stage render step render
stage student served "$E4B_MODELS/$STUDENT_GGUF" "$SLOTS" "$SLOT_CTX" student \
    --student-url "http://127.0.0.1:$PORT"
stage check served "$CHECKER" "$CHECKER_SLOTS" "$SLOT_CTX" check ${LINES_BY_RULES:+--lines-by-rules}
stage filter step filter ${LINES_BY_RULES:+--lines-by-rules}
touch "$STATE/done"
log "character rows ready: $DIR/train-checked.jsonl"
