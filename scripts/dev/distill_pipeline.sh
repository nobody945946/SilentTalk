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
# the `claude` CLI for the judge. See HANDOFF.md section 3.6.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO" || exit 1
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

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
    ls "$STATE"
    tail -5 "$LOG" 2>/dev/null
    exit 0
fi

[ -e "$STATE/done" ] && exit 0
exec 9> "$STATE/.lock"
flock -n 9 || exit 0          # another copy is already running

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

teacher_up() {
    if curl -sf "http://127.0.0.1:$TEACHER_PORT/health" > /dev/null; then return 0; fi
    local old; old=$(teacher_pid)
    [ -n "$old" ] && kill "$old" && sleep 3
    log "starting teacher"
    nohup llama-server -m "$TEACHER" --host 127.0.0.1 --port "$TEACHER_PORT" \
        -ngl 99 --n-cpu-moe 18 -c 16384 --parallel 4 -fa on \
        --cache-type-k q8_0 --cache-type-v q8_0 --jinja -t 12 \
        > "$LOGS/teacher.log" 2>&1 9>&- &   # 9>&-: the teacher must not hold our lock
    for _ in $(seq 150); do
        curl -sf "http://127.0.0.1:$TEACHER_PORT/health" > /dev/null && return 0
        sleep 2
    done
    log "teacher did not come up"
    return 1
}

teacher_down() {
    local pid; pid=$(teacher_pid)
    [ -n "$pid" ] && kill "$pid" && log "teacher stopped" && sleep 5
    return 0
}

# stage NAME COMMAND...: skip if marked done, else run and mark on success.
stage() {
    local name=$1; shift
    [ -e "$STATE/$name" ] && return 0
    log "stage $name: start"
    "$@" >> "$LOGS/$name.log" 2>&1
    local rc=$?
    if [ "$rc" -eq 0 ]; then
        touch "$STATE/$name"
        log "stage $name: done"
        return 0
    fi
    log "stage $name: FAILED (exit $rc), will resume on the next run"
    exit 1
}

data() {
    teacher_up || return 1
    .venv/bin/python scripts/dev/distill_data.py "$@" --workers 4
}

stage personas data personas --count "$PERSONAS"
stage scenes data scenes --count "$SCENES"
stage replies data replies --per-persona "$PER_PERSONA"
teacher_down

# ~10 GB of bf16 weights; batch 1 keeps the 262k-vocab logits within a
# 3090 that other services already share.
stage train .runtime/train-venv/bin/python scripts/dev/train_lora.py \
    --base "$STUDENT_HF" --out "$LORA_DIR" --batch 1 --grad-accum 16
stage convert env PYTHONPATH="$LLAMA_SRC/gguf-py" .runtime/train-venv/bin/python \
    "$LLAMA_SRC/convert_lora_to_gguf.py" --base "$STUDENT_HF" --outtype f16 \
    --outfile "$LORA_GGUF" "$LORA_DIR"
stage eval .venv/bin/python scripts/dev/persona_eval.py --model "$STUDENT_GGUF" \
    --server-args="--lora $REPO/$LORA_GGUF" --runs 2 --tag gemma4-E2B_lora_r2
stage eval_character .venv/bin/python scripts/dev/persona_eval.py --model "$STUDENT_GGUF" \
    --server-args="--lora $REPO/$LORA_GGUF" --runs 2 --mode character \
    --tag gemma4-E2B_lora_character

touch "$STATE/done"
log "pipeline finished; compare .runtime/dev/persona_eval/gemma4-E2B_lora_{r2,character}.json with gemma4-E2B_{prod_r2,character_norepeat}.json"
