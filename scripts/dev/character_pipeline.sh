#!/bin/bash
# Character-mode LoRA, end to end: teacher data (character_data.py) -> LoRA
# training -> GGUF adapter -> M1 turn-taking eval. Every stage is resumable
# and leaves a marker in .runtime/dev/chardata/state/, so running this again
# continues where it stopped (network drop, crash, reboot, closed session).
#
#   scripts/dev/character_pipeline.sh            # run / resume (safe to call often)
#   scripts/dev/character_pipeline.sh --status   # show progress
#
# Same unattended rules as the first pipeline (archived with its data in
# archive/distill-v1): flock keeps one copy running, a dead teacher is
# restarted at once and a hung one within ~45 s, "not now" (no network, GPU
# busy) exits 75 and is retried, a stage failing 3 times in a row is marked
# .blocked until someone looks at it.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO" || exit 1
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
# Nothing up to the judge needs the internet.
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export PYTHONUNBUFFERED=1

DIR=.runtime/dev/chardata
STATE=$DIR/state
LOGS=$DIR/logs
mkdir -p "$STATE" "$LOGS"
LOG=$LOGS/pipeline.log

PERSONAS=${PERSONAS:-300}
PER_PERSONA=${PER_PERSONA:-2}
TEACHER=${TEACHER:-.runtime/models/teacher/Qwen3-30B-A3B-Instruct-2507-UD-Q4_K_XL.gguf}
TEACHER_PORT=18200
STUDENT_HF=${STUDENT_HF:-.runtime/hf/gemma-4-E2B-it-qat}
STUDENT_GGUF=${STUDENT_GGUF:-gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf}
LORA_DIR=.runtime/dev/lora/character-e2b
LORA_GGUF=.runtime/models/llm/character-e2b-lora.gguf
LLAMA_SRC=.runtime/tools/llama.cpp-b11179
# With part of the experts on the CPU (the GPU is shared), more parallel
# slots batch more tokens per pass over those weights.
SLOTS=${SLOTS:-8}

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

if [ "${1:-}" = "--status" ]; then
    for f in personas scripts refined train; do
        printf '%-9s %s\n' "$f" "$(wc -l < "$DIR/$f.jsonl" 2>/dev/null || echo 0)"
    done
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
    if [ -n "$pid" ]; then
        for _ in $(seq 150); do
            health && return 0
            kill -0 "$pid" 2>/dev/null || break
            sleep 2
        done
        kill -9 "$pid" 2>/dev/null
        sleep 2
    fi
    log "starting teacher $(basename "$TEACHER")"
    # --fit sizes the offload to the VRAM the shared GPU has free.
    nohup llama-server -m "$TEACHER" --host 127.0.0.1 --port "$TEACHER_PORT" \
        --fit on --fit-target 2048 -c $((SLOTS * 4096)) --parallel "$SLOTS" -fa on \
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
    [ -n "$pid" ] && kill "$pid" && log "teacher stopped" && sleep 5
    return 0
}

# A data step under teacher supervision (see the first pipeline for why the
# watcher and the health checks look the way they do).
data() {
    teacher_up || return 1
    .venv/bin/python scripts/dev/character_data.py "$@" \
        --teacher-url "http://127.0.0.1:$TEACHER_PORT" --workers "$SLOTS" &
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

online() { curl -s -m 10 -o /dev/null https://api.anthropic.com; }
need_vram() {
    local free; free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${free:-0}" -ge "$1" ] || { echo "only ${free} MiB free, need $1"; return 75; }
}
train() { need_vram 12500 || return 75; .runtime/train-venv/bin/python scripts/dev/train_lora.py "$@"; }
eval_run() { .venv/bin/python scripts/dev/turn_eval.py --policy new --model "$STUDENT_GGUF" "$@"; }
eval_judge() { online || return 75; .venv/bin/python scripts/dev/turn_eval.py "$@"; }

stage personas data personas --count "$PERSONAS"
stage scripts data scripts --per-persona "$PER_PERSONA"
stage refine data refine
teacher_down
stage render .venv/bin/python scripts/dev/character_data.py render

# CPU preflight (offline): the loss must cover exactly the answer tokens.
stage train_check env CUDA_VISIBLE_DEVICES= .runtime/train-venv/bin/python \
    scripts/dev/train_lora.py --base "$STUDENT_HF" --out "$LORA_DIR.check" \
    --data "$DIR/train.jsonl" --max-length 3072 --check
stage train train --base "$STUDENT_HF" --out "$LORA_DIR" --data "$DIR/train.jsonl" \
    --batch 1 --grad-accum 16 --max-length 3072
stage convert env PYTHONPATH="$LLAMA_SRC/gguf-py" .runtime/train-venv/bin/python \
    "$LLAMA_SRC/convert_lora_to_gguf.py" --base "$STUDENT_HF" --outtype f16 \
    --outfile "$LORA_GGUF" "$LORA_DIR"
# Generate first (offline, saved), then judge: no network only delays judging.
stage eval eval_run --lora "$(basename "$LORA_GGUF")" --tag new-lora-e2b
stage eval_judge eval_judge --judge-only new-lora-e2b

touch "$STATE/done"
log "pipeline finished; compare .runtime/dev/turn_eval/new-lora-e2b.json with new-gemma-4-E2B-it-qat-UD-Q4_K_XL.json"
