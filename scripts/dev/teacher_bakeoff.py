"""M3: which local model writes the most natural character lines?

Every candidate plays the character at each "speak" point of the M1 test
set (scripts/dev/turn_eval_data.jsonl), with exactly the request the app
sends once the gate said 是 (LocalReplyModel.character_messages, addressed).
Teacher candidates also get a "+pick" variant: four samples, then the same
model picks the most natural one, which is how training data would be made;
and a "+think" variant: the model's own reasoning mode on (offline, so its
slowness costs nothing at runtime), then the line. Time per variant is kept
in timing.json: a teacher has to regenerate thousands of lines.
Claude then ranks the candidates blind, point by point. Claude only
evaluates here; its output never becomes training data (handoff/dev-box.md rule 2).

    .venv/bin/python scripts/dev/teacher_bakeoff.py generate [--only NAME,...]
    .venv/bin/python scripts/dev/teacher_bakeoff.py judge [--passes 2]
    .venv/bin/python scripts/dev/teacher_bakeoff.py report
    # rank a subset in its own verdict file (more than ~6 versions per
    # ranking makes the judge noisy):
    ... judge --tag pick --variants student-gemma4-e2b,qwen3-30b-a3b+pick,...

Resumable: generated lines and judgements are kept in .runtime/dev/m3/.
The test set is synthetic, so saving the lines does not break rule 1.
"""

from __future__ import annotations

import argparse
import functools
import json
import random
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import turn_eval  # noqa: E402

from silenttalk.copilot import persona as persona_module  # noqa: E402
from silenttalk.copilot.llm import LocalReplyModel, find_llama_server  # noqa: E402
from silenttalk.copilot.types import ConversationTurn  # noqa: E402

OUT_DIR = PROJECT_DIR / ".runtime" / "dev" / "m3"
LINES_PATH = OUT_DIR / "lines.json"
JUDGE_PATH = OUT_DIR / "judge.json"
TIMING_PATH = OUT_DIR / "timing.json"
THINK_TOKENS = 3000
PORT = 18420
LLM_DIR = PROJECT_DIR / ".runtime" / "models" / "llm"
TEACHER_DIR = PROJECT_DIR / ".runtime" / "models" / "teacher"

# name -> (gguf, is_teacher). The student is the reference to beat.
CANDIDATES: dict[str, tuple[Path, bool]] = {
    "student-gemma4-e2b": (LLM_DIR / "gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf", False),
    # Other students that fit a 4 GB 3050 Ti; the user leaves the choice open
    # as long as speed keeps up.
    "student-gemma4-e4b": (LLM_DIR / "gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf", False),
    "student-qwen3.5-4b": (LLM_DIR / "Qwen3.5-4B-Q4_K_M.gguf", False),
    "qwen3-30b-a3b": (
        TEACHER_DIR / "Qwen3-30B-A3B-Instruct-2507-UD-Q4_K_XL.gguf",
        True,
    ),
    "qwen3.6-35b-a3b": (TEACHER_DIR / "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf", True),
    "qwen3.6-27b": (TEACHER_DIR / "Qwen3.6-27B-UD-Q4_K_XL.gguf", True),
    "gemma4-31b": (TEACHER_DIR / "gemma-4-31B-it-UD-Q4_K_XL.gguf", True),
    "gemma4-26b-taide": (TEACHER_DIR / "model-Q4_K_M.gguf", True),
}
SAMPLES = 4
_LOCK = threading.Lock()

PICK_PROMPT = """下面是 Discord 語音聊天的最後幾句，以及角色「{name}」接話的 {k} 個候選。
角色人設：
{sheet}

對話：
{chat}

候選：
{options}

哪一句最像這個人在語音裡真的會脫口而出的話？標準：口語自然、不做作、不像客服或旁白，符合人設的口吻和立場，接得上前一句，長度合適。
只回答一個數字（1 到 {k}）。"""

JUDGE_PROMPT = """你是對話品質評審。下面每一組都是 Discord 語音聊天（語音辨識結果，可能沒有標點），最後有人在跟角色說話，接著是幾個不同版本的角色回話，順序是隨機的。

角色人設：
{sheet}

評比標準，由重到輕：
1. 像真人朋友在語音裡會脫口而出的話：口語、自然、不做作，不像客服、旁白、翻譯腔或作文。
2. 符合人設的口吻、用詞和立場（不是每句都塞口頭禪）。
3. 接得上前一句、回應了對方真正在說的事。
4. 長度合適，沒有自稱 AI、沒有答應做寫程式或查資料這類角色做不到的事。

{items}

每一組把版本代號從最好排到最差，並列出明顯不及格（出戲、不通順、答非所問、自稱 AI）的代號。
只輸出 JSON 陣列，不要其他文字，長度 {n}，依序對應：[{{"id": 1, "ranking": ["C", "A", "B"], "bad": ["B"]}}, ...]"""


# ---------------------------------------------------------------- points


def speak_points(test_set: Any) -> list[dict[str, Any]]:
    """Every line the character must answer, with the chat up to it."""
    points = []
    for conv in test_set.conversations:
        persona = turn_eval.resolve_persona(persona_module, test_set, conv.persona_id)
        ids = turn_eval.speaker_ids(conv)
        turns: list[ConversationTurn] = []
        for index, line in enumerate(conv.lines):
            if line.get("self"):
                turns.append(
                    ConversationTurn(0, persona.name, line["text"], is_self=True)
                )
                continue
            turns.append(
                ConversationTurn(
                    ids.get(line["speaker"], 9),
                    line["speaker"],
                    line["text"],
                    via=line.get("via", "voice"),
                )
            )
            if line.get("expect") == "speak":
                points.append(
                    {
                        "id": f"{conv.id}#{index}",
                        "conv": conv.id,
                        "index": index,
                        "persona": persona,
                        "engagement": conv.engagement,
                        "turns": list(turns),
                        "tags": line.get("tags", []),
                    }
                )
    return points


def request_messages(point: dict[str, Any]) -> list[dict[str, str]]:
    model = LocalReplyModel(Path("unused.gguf"))
    model.set_persona(point["persona"])
    return model.character_messages(
        turns=point["turns"], addressed=True, engagement=point["engagement"]
    )


def parse_line(point: dict[str, Any], raw: str) -> str:
    model = LocalReplyModel(Path("unused.gguf"))
    model.set_persona(point["persona"])
    newest = next(t.text for t in reversed(point["turns"]) if not t.is_self)
    return model._parse_character_line(raw, newest)


def chat_text(point: dict[str, Any], last: int = 8) -> str:
    return "\n".join(
        f"{t.speaker_name}（角色）：{t.text}"
        if t.is_self
        else f"{t.speaker_name}：{t.text}"
        for t in point["turns"][-last:]
    )


# ---------------------------------------------------------------- server


def start_server(gguf: Path) -> subprocess.Popen[bytes]:
    args = [
        find_llama_server(),
        "--model",
        str(gguf),
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--ctx-size",
        "16384",
        "--parallel",
        "4",
        "--jinja",
        "--fit",
        "on",
        "--fit-target",
        "2048",
        "--threads",
        "12",
    ]
    server = subprocess.Popen(
        args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(
                f"llama-server exited with {server.returncode} for {gguf.name}"
            )
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2)
            return server
        except OSError:
            time.sleep(2)
    server.kill()
    raise RuntimeError("llama-server did not come up")


def stop_server(server: subprocess.Popen[bytes]) -> None:
    server.terminate()
    try:
        server.wait(20)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()


def complete(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    n: int = 1,
    think: bool = False,
) -> list[str]:
    outputs = []
    for _ in range(n):
        body = {
            "messages": messages,
            "temperature": temperature,
            "top_p": 0.9,
            "max_tokens": max_tokens,
            "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": think},
        }
        request = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/v1/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=900) as response:
            message = json.load(response)["choices"][0]["message"]
        text = message.get("content") or ""
        if think and (message.get("reasoning_content") or "<think>" in text):
            with _LOCK:
                THOUGHT_SEEN.add("reasoning")
        # A reasoning model that ran out of tokens mid-thought leaves an
        # unclosed <think>; nothing after it is an answer.
        text = re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.S).strip()
        outputs.append(text)
    return outputs


# Set when a +think request actually came back with reasoning; a model
# without a reasoning mode just answers, and the report says so.
THOUGHT_SEEN: set[str] = set()


# ---------------------------------------------------------------- generate


def generate(args: argparse.Namespace) -> None:
    turn_eval.ensure_llama_server_on_path()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    points = speak_points(turn_eval.load_test_set())
    lines: dict[str, dict[str, str]] = _load(LINES_PATH)
    names = args.only.split(",") if args.only else list(CANDIDATES)
    timing: dict[str, dict[str, Any]] = _load(TIMING_PATH)
    for name in names:
        gguf, is_teacher = CANDIDATES[name]
        stages = [("plain", [name] + ([f"{name}+pick"] if is_teacher else []))]
        if is_teacher and not args.no_think:
            stages.append(("think", [f"{name}+think"]))
        todo_by_stage = [
            (stage, [p for p in points if any(v not in lines.get(p["id"], {}) for v in variants)])
            for stage, variants in stages
        ]
        if not any(todo for _, todo in todo_by_stage):
            print(f"{name}: done", flush=True)
            continue
        if not gguf.is_file():
            print(f"{name}: missing {gguf.name}, skipped", flush=True)
            continue
        started = time.monotonic()
        server = start_server(gguf)
        print(f"{name}: server up in {time.monotonic() - started:.0f} s", flush=True)
        try:
            for stage, todo in todo_by_stage:
                if not todo:
                    continue
                THOUGHT_SEEN.clear()
                stage_started = time.monotonic()
                one = _generate_one if stage == "plain" else _generate_think
                with ThreadPoolExecutor(4) as pool:
                    job = functools.partial(one, lines, name, is_teacher)
                    for n, _ in enumerate(pool.map(job, todo), 1):
                        if n % 10 == 0:
                            with _LOCK:
                                _save(LINES_PATH, lines)
                            print(f"  {name} {stage} {n}/{len(todo)}", flush=True)
                _save(LINES_PATH, lines)
                seconds = time.monotonic() - stage_started
                entry = timing.setdefault(name, {})
                entry[f"{stage}_seconds_per_point"] = round(seconds / len(todo), 2)
                if stage == "think":
                    entry["reasoning_seen"] = bool(THOUGHT_SEEN)
                _save(TIMING_PATH, timing)
                print(f"{name} {stage}: {len(todo)} points in {seconds:.0f} s", flush=True)
        finally:
            stop_server(server)


def _generate_one(
    lines: dict[str, dict[str, str]], name: str, is_teacher: bool, point: dict[str, Any]
) -> None:
    messages = request_messages(point)
    # The app's own sampling for the plain variant.
    raw = complete(messages, temperature=0.65, max_tokens=90)[0]
    result = {name: parse_line(point, raw)}
    if is_teacher:
        samples = [
            parse_line(point, r)
            for r in complete(messages, temperature=0.9, max_tokens=90, n=SAMPLES)
        ]
        samples = [s for s in dict.fromkeys(samples) if s] or [result[name]]
        result[f"{name}+pick"] = pick(point, samples)
    with _LOCK:
        lines.setdefault(point["id"], {}).update(result)


def _generate_think(
    lines: dict[str, dict[str, str]], name: str, is_teacher: bool, point: dict[str, Any]
) -> None:
    raw = complete(
        request_messages(point), temperature=0.65, max_tokens=THINK_TOKENS, think=True
    )[0]
    with _LOCK:
        lines.setdefault(point["id"], {})[f"{name}+think"] = parse_line(point, raw)


def pick(point: dict[str, Any], samples: list[str]) -> str:
    if len(samples) == 1:
        return samples[0]
    persona = point["persona"]
    prompt = PICK_PROMPT.format(
        name=persona.name,
        sheet=persona.render_system_block(),
        chat=chat_text(point),
        k=len(samples),
        options="\n".join(f"{n}. {s}" for n, s in enumerate(samples, 1)),
    )
    answer = complete(
        [{"role": "user", "content": prompt}], temperature=0.0, max_tokens=8
    )[0]
    match = re.search(r"\d+", answer)
    choice = int(match.group(0)) if match else 1
    return samples[choice - 1] if 1 <= choice <= len(samples) else samples[0]


# ---------------------------------------------------------------- judge


def _variants(args: argparse.Namespace, lines: dict[str, dict[str, str]]) -> list[str]:
    everything = sorted({v for row in lines.values() for v in row})
    if not args.variants:
        return everything
    wanted = args.variants.split(",")
    missing = [v for v in wanted if v not in everything]
    if missing:
        raise SystemExit(f"no lines for {missing}; generate them first")
    return sorted(wanted)


def _judge_path(args: argparse.Namespace) -> Path:
    return OUT_DIR / f"judge-{args.tag}.json" if args.tag else JUDGE_PATH


def judge(args: argparse.Namespace) -> None:
    points = {p["id"]: p for p in speak_points(turn_eval.load_test_set())}
    lines = _load(LINES_PATH)
    judge_path = _judge_path(args)
    verdicts: dict[str, list[dict[str, Any]]] = _load(judge_path)
    variants = _variants(args, lines)
    for pass_no in range(args.passes):
        key = f"pass{pass_no}"
        done = verdicts.setdefault(key, [])
        seen = {v["point"] for v in done}
        rng = random.Random(1000 + pass_no)
        todo = [pid for pid in sorted(points) if pid not in seen and pid in lines]
        by_persona: dict[str, list[str]] = defaultdict(list)
        for pid in todo:
            by_persona[points[pid]["persona"].id].append(pid)
        for persona_id, pids in sorted(by_persona.items()):
            for start in range(0, len(pids), args.batch):
                chunk = pids[start : start + args.batch]
                items, maps = [], []
                for n, pid in enumerate(chunk, 1):
                    row = {v: lines[pid].get(v, "") for v in variants}
                    order = list(variants)
                    rng.shuffle(order)
                    labels = [chr(ord("A") + i) for i in range(len(order))]
                    maps.append(dict(zip(labels, order, strict=True)))
                    options = "\n".join(
                        f"{label}. {row[v] or '（沉默）'}"
                        for label, v in zip(labels, order, strict=True)
                    )
                    items.append(
                        f"=== 第 {n} 組 ===\n{chat_text(points[pid])}\n\n版本：\n{options}"
                    )
                prompt = JUDGE_PROMPT.format(
                    sheet=points[chunk[0]]["persona"].render_system_block(),
                    items="\n\n".join(items),
                    n=len(chunk),
                )
                result = turn_eval.run_judge(prompt, args.judge_model)
                for n, (pid, mapping) in enumerate(zip(chunk, maps, strict=True), 1):
                    verdict = next((r for r in result if r.get("id") == n), None)
                    if not verdict:
                        continue
                    done.append(
                        {
                            "point": pid,
                            "ranking": [
                                mapping[x]
                                for x in verdict.get("ranking", [])
                                if x in mapping
                            ],
                            "bad": [
                                mapping[x]
                                for x in verdict.get("bad", [])
                                if x in mapping
                            ],
                        }
                    )
                _save(judge_path, verdicts)
                print(
                    f"  {key} {persona_id} {start + len(chunk)}/{len(pids)}", flush=True
                )
    report(args)


def report(args: argparse.Namespace) -> None:
    verdicts = _load(_judge_path(args))
    lines = _load(LINES_PATH)
    variants = _variants(args, lines)
    timing = _load(TIMING_PATH)
    student = "student-gemma4-e2b"
    per_pass: dict[str, dict[str, float]] = {}
    rows: dict[str, dict[str, Any]] = {}
    for key, done in verdicts.items():
        ranks: dict[str, list[int]] = defaultdict(list)
        for v in done:
            for place, name in enumerate(v["ranking"], 1):
                ranks[name].append(place)
        per_pass[key] = {name: statistics.fmean(r) for name, r in ranks.items()}
    for name in variants:
        all_ranks, wins, games, bad = [], 0, 0, 0
        for done in verdicts.values():
            for v in done:
                order = v["ranking"]
                if name in order:
                    all_ranks.append(order.index(name) + 1)
                if name != student and name in order and student in order:
                    games += 1
                    wins += order.index(name) < order.index(student)
                bad += name in v["bad"]
        rows[name] = {
            "mean_rank": round(statistics.fmean(all_ranks), 2) if all_ranks else None,
            "win_vs_student": round(wins / games, 2) if games else None,
            "bad": bad,
            "rank_by_pass": [
                round(p.get(name, float("nan")), 2) for p in per_pass.values()
            ],
        }
    print("| 候選 | 平均名次（越小越好） | 各輪 | 贏學生的比例 | 不及格 | 秒／點 |")
    print("|---|---|---|---|---|---|")
    for name, row in sorted(rows.items(), key=lambda kv: kv[1]["mean_rank"] or 99):
        base, _, kind = name.partition("+")
        entry = timing.get(base, {})
        seconds = entry.get(f"{'think' if kind == 'think' else 'plain'}_seconds_per_point")
        if kind == "think" and entry.get("reasoning_seen") is False:
            seconds = f"{seconds}（沒有推理模式）"
        row["seconds_per_point"] = seconds
        print(
            f"| {name} | {row['mean_rank']} | {row['rank_by_pass']} | "
            f"{row['win_vs_student']} | {row['bad']} | {seconds or '—'} |"
        )
    name = f"report-{args.tag}.json" if args.tag else "report.json"
    (OUT_DIR / name).write_text(json.dumps(rows, ensure_ascii=False, indent=2))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save(path: Path, data: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("step", choices=("generate", "judge", "report"))
    parser.add_argument("--only", help="comma-separated candidate names")
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--batch", type=int, default=6)
    parser.add_argument("--judge-model", default="sonnet")
    parser.add_argument("--variants", help="judge/report: only these versions")
    parser.add_argument("--tag", help="judge/report: separate verdict file judge-<tag>.json")
    parser.add_argument("--no-think", action="store_true", help="generate: skip +think")
    args = parser.parse_args()
    {"generate": generate, "judge": judge, "report": report}[args.step](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
