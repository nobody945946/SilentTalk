#!/bin/bash
# Character-mode LoRA, end to end: teacher data (character_data.py) -> hard
# quality check -> LoRA training on the rows that pass -> GGUF adapter ->
# turn-taking eval, paired against the current best. Every stage is
# resumable and leaves a marker in $DIR/state/, so running this again
# continues where it stopped (network drop, crash, reboot, closed session).
#
#   scripts/dev/character_pipeline.sh            # run / resume (safe to call often)
#   scripts/dev/character_pipeline.sh --status   # show progress
#
# Round 3 (the first round's data stays in .runtime/dev/chardata/):
#   teacher  Qwen3.6-27B, dense: best of the teacher comparison
#            (.runtime/dev/m3/report-pick.json)
#   student  Gemma 4 E4B (QLoRA), which writes its own line for every line
#            row: the teacher's line is kept only if it beats that
#   checker  Gemma 4 31B, another family than the teacher, so it does not
#            share the teacher's blind spots; answers every gate question
#            and compares teacher and student lines blind, both orders
# Teacher and checker are 3-bit quants that fit whole in the ~16 GB the
# shared GPU has free: the first round's 17 GB MoE spilled to the CPU and
# the whole 3090 ran at 20-60 tokens/s. They are served by a CUDA build of
# llama-server (LLAMA_SERVER): the Vulkan build the laptop uses read prompts
# at ~120 tokens/s here.
#
# The filter stage refuses the whole set (stage *filter.blocked) when any
# number in character_data.HARD_CHECK is missed; nothing is trained then.
# Order, so that a set that would be refused costs as little as possible:
#   calibrate  the checker on every gate row of 60 random first-round
#              scripts: how far it agrees with labels made the same way.
#              Whole scripts, in order, so the server reads each chat once
#              (random single rows re-read ~1.4k tokens each: 10 s a row)
#   pilot_*    the whole data path on 30 personas, through the hard check
#   the rest   as many personas as the pilot's yield needs for ~2000 kept
#              lines (at most 300; resumes on top of the pilot), training,
#              eval paired against the current candidates
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

DIR=.runtime/dev/chardata-v3
export CHARDATA_DIR="$REPO/$DIR"
V1=.runtime/dev/chardata
STATE=$DIR/state
LOGS=$DIR/logs
mkdir -p "$STATE" "$LOGS"
LOG=$LOGS/pipeline.log

PER_PERSONA=${PER_PERSONA:-2}
GENERATOR=${GENERATOR:-.runtime/models/teacher/Qwen3.6-27B-UD-IQ3_XXS.gguf}
CHECKER=${CHECKER:-.runtime/models/teacher/gemma-4-31B-it-UD-IQ3_XXS.gguf}
PILOT_PERSONAS=30
HARD_LINES=1500  # character_data.HARD_CHECK["lines_kept"], scaled for the pilot
TEACHER=$GENERATOR  # whichever model the data step needs; one at a time
TEACHER_PORT=18200
STUDENT_HF=${STUDENT_HF:-.runtime/hf/gemma-4-E4B-it-qat}
STUDENT_GGUF=${STUDENT_GGUF:-gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf}
TAG=${TAG:-v3-e4b}
LORA_DIR=.runtime/dev/lora/character-$TAG
LORA_GGUF=.runtime/models/llm/character-$TAG.q8_0.gguf
LLAMA_SRC=.runtime/tools/llama.cpp-b11179
LLAMA_SERVER=${LLAMA_SERVER:-.runtime/tools/llama.cpp-b11179-src/build-cuda/bin/llama-server}
[ -x "$LLAMA_SERVER" ] || LLAMA_SERVER=llama-server
# Parallel requests per server, measured on the shared 3090 (CUDA build):
# the 27B teacher writes 43 tokens/s alone, 112 with 8, 151 with 16 (12
# keeps its cache well inside the free memory). Gemma 4 31B reads prompts
# slower the more sequences it holds (414 tokens/s with 1, 386 with 2, 112
# with 8), so the checker gets 2.
SLOTS=${SLOTS:-12}
CHECKER_SLOTS=${CHECKER_SLOTS:-2}
SERVER_SLOTS=$SLOTS

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

if [ "${1:-}" = "--status" ]; then
    for f in personas scripts refined train student check train-checked; do
        printf '%-14s %s\n' "$f" "$(wc -l 2>/dev/null < "$DIR/$f.jsonl" || echo 0)"
    done
    [ -f "$V1/filter.json" ] && echo "calibrate (first round's gate rows): $(tr -d '\n ' < "$V1/filter.json")"
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
        -ngl 99 --fit off -c $((SERVER_SLOTS * 4096)) --parallel "$SERVER_SLOTS" -fa on \
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

online() { curl -s -m 10 -o /dev/null https://api.anthropic.com; }
need_vram() {
    local free; free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${free:-0}" -ge "$1" ] || { echo "only ${free} MiB free, need $1"; return 75; }
}
train() { need_vram 12500 || return 75; .runtime/train-venv/bin/python scripts/dev/train_lora.py "$@"; }
eval_run() { .venv/bin/python scripts/dev/turn_eval.py --policy new --model "$STUDENT_GGUF" "$@"; }
# Paired, both orders, against every current candidate that has results.
eval_pair() {
    online || return 75
    local base
    for base in now-e4b now-e4b-gate; do
        [ -f ".runtime/dev/turn_eval/$base.json" ] || continue
        .venv/bin/python scripts/dev/turn_eval.py --judge-pair "$base" "$TAG" || return 1
    done
}
generator() { TEACHER=$GENERATOR SERVER_SLOTS=$SLOTS; data "$@"; }
checker() { TEACHER=$CHECKER SERVER_SLOTS=$CHECKER_SLOTS; data "$@"; }
student() {
    TEACHER=.runtime/models/llm/$STUDENT_GGUF SERVER_SLOTS=$SLOTS
    data student --student-url "http://127.0.0.1:$TEACHER_PORT"
}
# The checker against the first round's gate labels. Informational: its
# number decides whether the first round's gate adapter may ship, and shows
# early whether the checker and the labels can meet HARD_CHECK at all.
calibrate() {
    python3 - "$V1" <<'PY'
import json, random, sys
rows = [json.loads(line) for line in open(f"{sys.argv[1]}/train-gate-compact.jsonl")]
pick = set(random.Random(7).sample(sorted({r["script"] for r in rows}), 60))
with open(f"{sys.argv[1]}/gate-sample.jsonl", "w") as out:
    for row in rows:
        if row["script"] in pick:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
PY
    CHARDATA_DIR="$REPO/$V1" checker check --rows gate-sample.jsonl || return
    CHARDATA_DIR="$REPO/$V1" .venv/bin/python scripts/dev/character_data.py filter \
        --rows gate-sample.jsonl --min-lines 0
    local rc=$?
    [ "$rc" -eq 0 ] || [ "$rc" -eq 3 ]
}
personas() { head -n "$1" "$V1/personas.jsonl" > "$DIR/personas.jsonl"; }
# Personas for ~2000 kept lines at the pilot's yield.
full_count() {
    python3 - "$DIR/filter.json" "$PILOT_PERSONAS" <<'PY'
import json, math, sys
kept = json.load(open(sys.argv[1]))["lines_kept"]
pilot = int(sys.argv[2])
print(max(pilot, min(300, math.ceil(2000 * pilot / max(kept, 1)))))
PY
}
render() { .venv/bin/python scripts/dev/character_data.py render; }
filter() { .venv/bin/python scripts/dev/character_data.py filter "$@"; }

stage calibrate calibrate
# Exit 3 from a filter = refused by HARD_CHECK: marked blocked at once.
stage pilot_personas personas "$PILOT_PERSONAS"
stage pilot_scripts generator scripts --per-persona "$PER_PERSONA"
stage pilot_refine generator refine
stage pilot_render render
stage pilot_student student
stage pilot_check checker check
stage pilot_filter filter --min-lines $((HARD_LINES * PILOT_PERSONAS / 300))
stage personas personas "$(full_count)"
stage scripts generator scripts --per-persona "$PER_PERSONA"
stage refine generator refine
stage render render
stage student student
stage check checker check
teacher_down
stage filter filter

# CPU preflight (offline): the loss must cover exactly the answer tokens.
stage train_check env CUDA_VISIBLE_DEVICES= .runtime/train-venv/bin/python \
    scripts/dev/train_lora.py --base "$STUDENT_HF" --out "$LORA_DIR.check" \
    --data "$DIR/train-checked.jsonl" --max-length 3072 --check
# One epoch: rows carry the whole chat (~1.5k tokens) at ~1.3 s each.
stage train train --base "$STUDENT_HF" --out "$LORA_DIR" --data "$DIR/train-checked.jsonl" \
    --batch 1 --grad-accum 16 --max-length 3072 --4bit --epochs 1
stage convert env PYTHONPATH="$LLAMA_SRC/gguf-py" .runtime/train-venv/bin/python \
    "$LLAMA_SRC/convert_lora_to_gguf.py" --base "$STUDENT_HF" --outtype q8_0 \
    --outfile "$LORA_GGUF" "$LORA_DIR"
# Generate first (offline, saved), then judge: no network only delays judging.
stage eval eval_run --lora "$(basename "$LORA_GGUF")" --lora-uses called,active,line \
    --agenda --lull --tag "$TAG"
stage eval_pair eval_pair

touch "$STATE/done"
log "pipeline finished; see .runtime/dev/turn_eval/pair-*-vs-$TAG.json"
