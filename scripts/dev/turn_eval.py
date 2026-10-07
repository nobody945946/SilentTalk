"""Character-mode turn-taking eval (handoff/dev-box.md §5.2): speak or stay silent, and what.

Usage (from the repo root; llama-server is found on PATH or in .runtime/tools):
    python scripts/dev/turn_eval.py --stats                  # test-set stats only
    python scripts/dev/turn_eval.py --policy old             # production path at a pinned commit
    python scripts/dev/turn_eval.py --policy new --judge     # character_turn(), then Claude judge
    python scripts/dev/turn_eval.py --judge-only old-gemma-4-E2B-it-qat-UD-Q4_K_XL

Every conversation in scripts/dev/turn_eval_data.jsonl is played line by line
with teacher forcing: the character's scripted lines always enter the history,
whatever the model said. At every other line (a decision point) we record
whether the character spoke, what it said and how long that took, then report:

  recall       share of `speak` lines where it spoke        (target >= 95%)
  false speak  share of `silent` lines where it spoke       (target <= 10%)
  ...per tag and per engagement mode; `either` lines count for neither.

Policies:
  old  CopilotRuntime._handle_turn/_speak as of --old-rev (default: the commit
       before the character-mode rewrite), loaded from git so the baseline
       stays fixed while silenttalk/ changes: _MIN_TRIGGER_CHARS, address_of,
       should_reply with CharacterState, simulated clock (--seconds-per-line),
       ConversationStore.render_for_prompt, LocalReplyModel.character_reply.
  new  LocalReplyModel.character_turn(turns=..., summary="", addressed=...,
       engagement=...) from the working tree. See `new_policy_turn`.

--judge rates every generated reply (blind to the policy) with the claude CLI,
exactly like persona_eval.py: natural / voice / fit 1-5 and breaks_character.
Claude is only an evaluator here (handoff/dev-box.md rule 2). The test set is synthetic;
results go to .runtime/dev/turn_eval/<tag>.json. Nothing but numbers and ids is
printed.

This file is the command line; the parts live beside it: turn_eval_set (the
test set and who plays in it), turn_eval_model (the model under test and its
server), turn_eval_policies (old and new), turn_eval_metrics, turn_eval_judge
(--judge) and turn_eval_blind (--judge-pair, --judge-soul).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import turn_eval_model
import turn_eval_set
from turn_eval_blind import judge_pair, judge_soul
from turn_eval_judge import judge_records
from turn_eval_metrics import compute_metrics, print_metrics
from turn_eval_model import (
    EDGE_AGENT_MODEL_DIR,
    OLD_REV,
    copilot_config,
    ensure_llama_server_on_path,
)
from turn_eval_policies import AGENDAS, STATES, run_new, run_old
from turn_eval_set import DATA_PATH, OUT_DIR, PROJECT_DIR, load_test_set, print_stats

# The policies and judges import the app (silenttalk) when they run.
sys.path.insert(0, str(PROJECT_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--policy", choices=("old", "new"), default="old")
    parser.add_argument("--model", help="gguf in EDGE_AGENT_MODEL_DIR (default: config.toml)")
    parser.add_argument("--lora", help="new policy only: adapter gguf in EDGE_AGENT_MODEL_DIR")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--tag", help="results name (default: <policy>-<model stem>)")
    parser.add_argument("--old-rev", default=OLD_REV,
                        help="git revision for --policy old, or 'worktree'")
    parser.add_argument("--seconds-per-line", type=float, default=4.0)
    parser.add_argument("--only", help="comma-separated conversation ids (smoke runs)")
    parser.add_argument("--stats", action="store_true", help="print test-set stats and exit")
    parser.add_argument("--judge", action="store_true", help="rate replies with the claude CLI")
    parser.add_argument("--judge-only", metavar="TAG", help="judge an existing results file")
    parser.add_argument("--agenda", action="store_true",
                        help="new policy: give the character today's concerns first (make_agenda)")
    parser.add_argument("--memory", choices=("off", "light", "full"),
                        help="new policy: character_memory")
    parser.add_argument("--chain", action="store_true",
                        help="new policy: a persona's chats are consecutive days (memory carries over)")
    parser.add_argument("--later-only", action="store_true",
                        help="--judge-pair: only the 2nd and later chats of each persona")
    parser.add_argument("--lull", action="store_true",
                        help="new policy: after each chat, a quiet spell; record the line it opens with")
    parser.add_argument("--judge-pair", nargs=2, metavar=("TAG_A", "TAG_B"),
                        help="blind A/B of two existing runs, per line and per conversation")
    parser.add_argument("--judge-soul", metavar="TAG",
                        help="can you tell who is talking and what they want? (existing results)")
    parser.add_argument("--judge-model", default="sonnet")
    parser.add_argument("--judge-batch", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--cpu", action="store_true",
                        help="no GPU layers (latencies are then not comparable)")
    parser.add_argument("--lora-uses", help="with --lora: comma-separated parts "
                        "(called,active,line) that use the adapter; default all")
    parser.add_argument("--port", type=int, help="llama-server port (default 18411)")
    parser.add_argument("--persona-file", type=Path,
                        help="one persona row (e.g. .runtime/dev/chardata-ms1/personas.jsonl) "
                        "for every conversation; use with --data scripts/dev/machine_spirit_eval.jsonl")
    args = parser.parse_args()
    turn_eval_model.CPU_ONLY = args.cpu
    turn_eval_model.MEMORY = args.memory
    if args.lora_uses:
        turn_eval_model.LORA_USES = tuple(part.strip() for part in args.lora_uses.split(",") if part.strip())
    if args.port:
        turn_eval_model.EVAL_PORT = args.port

    data_sha256 = hashlib.sha256(args.data.read_bytes()).hexdigest()
    if args.persona_file:
        turn_eval_set.PERSONA_OVERRIDE = json.loads(args.persona_file.read_text(encoding="utf-8").splitlines()[0])
    test_set = load_test_set(args.data)
    turn_eval_set.OWNER_NAME = str(test_set.meta.get("owner", ""))
    if args.only:
        wanted = set(args.only.split(","))
        test_set.conversations = [c for c in test_set.conversations if c.id in wanted]
    if args.stats:
        print_stats(test_set)
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.judge_pair:
        tag_a, tag_b = args.judge_pair
        result = judge_pair(tag_a, tag_b, test_set, args.judge_model, args.seed, args.later_only)
        out = OUT_DIR / f"pair-{tag_a}-vs-{tag_b}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"lines ({result['points']} points, both orders): {tag_a} {result['lines']['a']}"
              f"  {tag_b} {result['lines']['b']}  tie {result['lines']['tie']}")
        print(f"know this person (per conversation): {result['know']}   real person: {result['real']}"
              f"   life moves on: {result['life']}")
        return 0
    if args.judge_soul:
        path = OUT_DIR / f"{args.judge_soul}.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        result["soul"] = judge_soul(result["records"], test_set, args.judge_model, args.seed)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        soul = result["soul"]
        print(f"soul {args.judge_soul}: attribution {soul['attribution']} (chance 0.33), "
              f"know {soul['know']} / 5, {soul['verdicts']} verdicts over {soul['conversations']} conversations")
        return 0
    if args.judge_only:
        path = OUT_DIR / f"{args.judge_only}.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        result["judge"] = judge_records(
            result["records"], test_set, args.judge_model, args.seed, args.judge_batch
        )
        result["judge_model"] = args.judge_model
        path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print_metrics(result["metrics"], result["judge"])
        print(f"saved {path}")
        return 0

    config = copilot_config()
    model_name = args.model or str(config["llm_model"])
    args.model_path = EDGE_AGENT_MODEL_DIR / model_name
    if not args.model_path.is_file():
        raise SystemExit(f"model not found: {args.model_path}")
    ensure_llama_server_on_path()
    tag = args.tag or f"{args.policy}-{Path(model_name).stem}"
    print(f"policy {args.policy}  model {model_name}  conversations "
          f"{len(test_set.conversations)}  port {turn_eval_model.EVAL_PORT}", flush=True)

    git_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_DIR,
                              capture_output=True, text=True).stdout.strip()
    # The new policy runs the working tree; note if it differs from HEAD.
    git_dirty = bool(subprocess.run(["git", "status", "--porcelain", "silenttalk"],
                                    cwd=PROJECT_DIR, capture_output=True, text=True).stdout.strip())
    started = time.time()
    runner = run_old if args.policy == "old" else run_new
    records = asyncio.run(runner(args, test_set))
    metrics = compute_metrics(records)
    result: dict[str, Any] = {
        "tag": tag, "policy": args.policy, "model": model_name,
        "old_rev": args.old_rev if args.policy == "old" else None,
        "git_head": git_head, "silenttalk_dirty": git_dirty,
        "data": str(args.data.relative_to(PROJECT_DIR)) if args.data.is_relative_to(PROJECT_DIR)
        else str(args.data),
        "data_sha256": data_sha256,
        "seconds_per_line": args.seconds_per_line,
        "wall_seconds": round(time.time() - started, 1),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "metrics": metrics, "records": records, "agendas": AGENDAS, "states": STATES,
    }
    path = OUT_DIR / f"{tag}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.judge:
        result["judge"] = judge_records(
            records, test_set, args.judge_model, args.seed, args.judge_batch
        )
        result["judge_model"] = args.judge_model
        path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print_metrics(metrics, result.get("judge"))
    print(f"saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
