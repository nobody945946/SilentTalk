#!/bin/bash
# Persona-LoRA distillation pipeline: teacher data -> LoRA training -> GGUF
# adapter -> persona_eval. Every stage is resumable and leaves a marker in
# .runtime/dev/distill/state/, so running this again continues where it
# stopped (network drop, crash, reboot, closed session).
#
#   scripts/dev/distill_pipeline.sh            # run / resume (safe to call often)
#   scripts/dev/distill_pipeline.sh --status   # show progress
#
# Unattended: a cron watchdog calls it every 5 minutes; flock keeps a single
# copy running and a finished pipeline exits immediately:
#   */5 * * * * /home/clawd/SilentTalk/scripts/dev/distill_pipeline.sh >/dev/null 2>&1
# Remove that crontab line once .runtime/dev/distill/state/done exists.
#
# Needs (Linux dev box): .runtime/tools/env.sh (llama-server b11179 on PATH),
# the teacher GGUF, .runtime/train-venv, .runtime/hf/gemma-4-E2B-it-qat and
# the `claude` CLI for the judge. Superseded by character_pipeline.sh.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO" || exit 1
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
# Everything up to the judge is local; never let a library phone home, so the
# pipeline keeps going without internet. Only the judge stages need network
# and simply retry (cron) until it is back.
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
# Stage logs are redirected to files; without this, a stage's stdout (training
# loss, per-stage progress) sits in Python's buffer for hours.
export PYTHONUNBUFFERED=1

DIR=.runtime/dev/distill
STATE=$DIR/state
LOGS=$DIR/logs
mkdir -p "$STATE" "$LOGS"
LOG=$LOGS/pipeline.log

PERSONAS=220
SCENES=800
PER_PERSONA=14
TEACHER=.runtime/models/teacher/Qwen3-30B-A3B-Instruct-2507-UD-Q4_K_XL.gguf
TEACHER_PORT=18200
STUDENT_HF=.runtime/hf/gemma-4-E2B-it-qat
STUDENT_GGUF=gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf
LORA_DIR=.runtime/dev/lora/gemma4-e2b
LORA_GGUF=.runtime/dev/lora/gemma4-e2b-persona-lora.gguf
LLAMA_SRC=.runtime/tools/llama.cpp-b11179

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

if [ "${1:-}" = "--status" ]; then
    for f in personas scenes replies; do
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
flock -n 9 || exit 0          # another copy is already running
# The lock is inherited on purpose by the stage commands (a data/train job
# that outlives a killed pipeline keeps a second copy from writing the same
# files) and deliberately closed (9>&-) for the teacher and helper processes.
# On a normal stop, take our helpers and the running job down with us; the
# teacher stays up for the next run.
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
        # Already running, maybe still loading (~20 s): don't replace it early.
        for _ in $(seq 150); do
            health && return 0
            kill -0 "$pid" 2>/dev/null || break
            sleep 2
        done
        kill -9 "$pid" 2>/dev/null
        sleep 2
    fi
    log "starting teacher"
    nohup llama-server -m "$TEACHER" --host 127.0.0.1 --port "$TEACHER_PORT" \
        -ngl 99 --n-cpu-moe 18 -c 16384 --parallel 4 -fa on \
        --cache-type-k q8_0 --cache-type-v q8_0 --jinja -t 12 \
        > "$LOGS/teacher.log" 2>&1 9>&- &   # 9>&-: the teacher must not hold our lock
    for _ in $(seq 150); do
        health && return 0
        sleep 2
    done
    log "teacher did not come up"
    return 1
}

# Only called for a dead or hung teacher: it holds no state worth a graceful
# shutdown, and a hung process would ignore TERM anyway, so KILL at once.
teacher_restart() {
    local pid; pid=$(teacher_pid)
    if [ -n "$pid" ]; then
        kill -9 "$pid" 2>/dev/null
        # teacher_pid ignores a zombie (empty cmdline); `kill -0` would not.
        for _ in $(seq 50); do [ -z "$(teacher_pid)" ] && break; sleep 0.2; done
    fi
    teacher_up
}

teacher_down() {
    local pid; pid=$(teacher_pid)
    [ -n "$pid" ] && kill "$pid" && log "teacher stopped" && sleep 5
    return 0
}

# Run a data step under teacher supervision. The teacher is restarted
#   - the moment its process exits: `tail --pid` wakes on the exit itself,
#     no polling of the model;
#   - when it is alive but hung: /health (~3 ms, answers even with every slot
#     busy) times out on 3 checks in a row, 10 s apart (~45 s to detect).
# The data client meanwhile retries every 3 s and resumes as soon as it is back.
data() {
    teacher_up || return 1
    .venv/bin/python scripts/dev/distill_data.py "$@" --workers 4 &
    DATA_JOB=$!
    local job=$DATA_JOB misses=0 tp finished status
    while true; do
        tp=$(teacher_pid)
        if [ -z "$tp" ]; then
            log "teacher gone; restarting"
            teacher_restart || { kill "$job"; wait "$job"; DATA_JOB=""; return 1; }
            continue
        fi
        # Helpers must not inherit the lock (fd 9): `tail` lives until the
        # teacher dies and would otherwise lock out every later run.
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

# stage NAME COMMAND...: skip if marked done, else run and mark on success.
#   exit 0   done -> marker, fail counter cleared
#   exit 75  "not now" (no network, GPU busy): stop quietly, cron retries;
#            this is not a failure
#   other    failure; the 3rd in a row marks the stage .blocked and the
#            pipeline stops retrying it (a deterministic error would only
#            waste the GPU every 5 minutes) until someone looks at it:
#            read $LOGS/<stage>.log, fix, then rm $STATE/<stage>.blocked
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
        log "stage $name: waiting (not possible right now), cron will retry"
        exit 0
    fi
    local fails=$(( $(cat "$STATE/$name.fails" 2>/dev/null || echo 0) + 1 ))
    echo "$fails" > "$STATE/$name.fails"
    if [ "$fails" -ge "$MAX_FAILS" ]; then
        touch "$STATE/$name.blocked"
        log "stage $name: BLOCKED after $fails failures in a row (exit $rc); needs a look, see $LOGS/$name.log"
    else
        log "stage $name: FAILED (exit $rc, $fails/$MAX_FAILS), will resume on the next run"
    fi
    exit 1
}

# Gates: return 75 ("not now") instead of failing.
online() { curl -s -m 10 -o /dev/null https://api.anthropic.com; }
judge() { online || return 75; .venv/bin/python scripts/dev/persona_eval.py "$@"; }
# Gemma 4 E2B LoRA needs ~12 GB (9.5 GB weights minus 0.9 GB unused towers,
# plus logits for a 262k vocab). The GPU is shared with other services.
need_vram() {
    local free; free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${free:-0}" -ge "$1" ] || { echo "only ${free} MiB free, need $1"; return 75; }
}
train() { need_vram 12500 || return 75; .runtime/train-venv/bin/python scripts/dev/train_lora.py "$@"; }

stage personas data personas --count "$PERSONAS"
stage scenes data scenes --count "$SCENES"
stage replies data replies --per-persona "$PER_PERSONA"
teacher_down

# ~10 GB of bf16 weights; batch 1 keeps the 262k-vocab logits within a
# 3090 that other services already share.
# Cheap CPU preflight (~15 s, offline): the loss must cover exactly the answer.
# A wrong mask would not crash training, it would silently learn nothing.
stage train_check env CUDA_VISIBLE_DEVICES= .runtime/train-venv/bin/python \
    scripts/dev/train_lora.py --base "$STUDENT_HF" --out "$LORA_DIR.check" --check
stage train train \
    --base "$STUDENT_HF" --out "$LORA_DIR" --batch 1 --grad-accum 16
stage convert env PYTHONPATH="$LLAMA_SRC/gguf-py" .runtime/train-venv/bin/python \
    "$LLAMA_SRC/convert_lora_to_gguf.py" --base "$STUDENT_HF" --outtype f16 \
    --outfile "$LORA_GGUF" "$LORA_DIR"
# Generate offline first (saved), then judge: a failed judge (no network)
# only retries the judging, never the generation.
EVAL=.runtime/dev/persona_eval
stage eval_gen .venv/bin/python scripts/dev/persona_eval.py --model "$STUDENT_GGUF" \
    --server-args="--lora $REPO/$LORA_GGUF" --runs 2 --judge none --tag gemma4-E2B_lora_r2
stage eval_character_gen .venv/bin/python scripts/dev/persona_eval.py --model "$STUDENT_GGUF" \
    --server-args="--lora $REPO/$LORA_GGUF" --runs 2 --mode character --judge none \
    --tag gemma4-E2B_lora_character
stage eval_judge judge --rejudge "$EVAL/gemma4-E2B_lora_r2.json"
stage eval_character_judge judge \
    --rejudge "$EVAL/gemma4-E2B_lora_character.json"

touch "$STATE/done"
log "pipeline finished; compare .runtime/dev/persona_eval/gemma4-E2B_lora_{r2,character}.json with gemma4-E2B_{prod_r2,character_norepeat}.json"
