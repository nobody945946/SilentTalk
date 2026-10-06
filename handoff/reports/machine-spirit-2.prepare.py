"""Serialize explicitly authored turns; validate using the existing owner.

This utility does not generate dialogue, scenarios, work, or persona text.
Edit the manuscript only; the two task/answer pairs are derived artifacts.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    source = root / "machine-spirit-2.manuscript.jsonl"
    job = json.loads((args.repo / "handoff/tasks/machine-spirit-1.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(args.repo / "scripts/dev"))
    import character_data as owner

    _, project_held_humans = owner.held_out()
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    expected = {f"tr{i:03d}" for i in range(1, 101)} | {f"ev{i:03d}" for i in range(1, 21)}
    counts = Counter(row["id"] for row in rows)
    errors = []
    if set(counts) != expected or any(n != 1 for n in counts.values()):
        errors.append("IDs: missing, unexpected, or duplicate")
    if len({row["topic"] for row in rows}) != len(rows):
        errors.append("duplicate scene title")
    buckets = {"train": {"tasks": [], "answers": [], "roles": [], "people": set(), "quiet": 0},
               "eval": {"tasks": [], "answers": [], "roles": [], "people": set(), "quiet": 0}}
    corrections = []
    for row in rows:
        key = row["id"]
        split = "train" if key.startswith("tr") else "eval"
        bucket = buckets[split]
        humans = row.get("people", ["阿嵐", "小柏"] if split == "train" else ["靖安", "海晴"])
        if set(humans) & project_held_humans:
            errors.append(f"{key}: project held-out human name")
        bucket["people"].update(humans)
        name = job["persona"]["name"]
        speakers = {"O": humans[0], "F": humans[1], "C": name}
        skeleton, text = [], []
        for pos, turn in enumerate(row["turns"], 1):
            tag, words = turn.split("|", 1)
            who, _, mode = tag.partition("/")
            speaker = speakers[who]
            slot = {"s": speaker}
            if who != "C" and mode:
                ask = mode.removesuffix("T").removesuffix("V")
                if ask not in owner.ASKS:
                    errors.append(f"{key}:{pos}: invalid ask")
                slot.update(kind="call", ask=ask, typed=mode.endswith("T"), note=words)
                if "機魂" not in words:
                    errors.append(f"{key}:{pos}: call lacks name")
            elif who == "C":
                if mode not in {"reply", "ack", "report", "quiet"}:
                    errors.append(f"{key}:{pos}: invalid role event")
                slot["kind"] = mode
                bucket["roles"].append(words)
                bucket["quiet"] += mode == "quiet"
                if not 8 <= len(words) <= 30:
                    errors.append(f"{key}:{pos}: role length {len(words)}")
                if re.search(r"(?:我是|作為).{0,6}(?:AI|人工智慧|語言模型|聊天機器人|程式)", words):
                    errors.append(f"{key}:{pos}: forbidden identity claim")
                if mode == "ack" and re.search(r"已(?:經)?.{0,3}(?:完成|寫好|執行|查到)", words):
                    errors.append(f"{key}:{pos}: premature success claim")
            else:
                slot.update(kind="chat", note="")
                if "機魂" in words or "馬基納" in words:
                    errors.append(f"{key}:{pos}: unmarked call")
            skeleton.append(slot)
            text.append(words)
            normalized = owner.to_taiwan_traditional(words)
            if normalized != words:
                corrections.append((key, pos))
        concerns = row["concerns"]
        if not 3 <= len(concerns) <= 4 or any(not c.strip() or len(c) > 40 for c in concerns):
            errors.append(f"{key}: concerns count/length")
        works = row["work"]
        if len(works) != sum(slot.get("ask") == "work" for slot in skeleton):
            errors.append(f"{key}: work count mismatch")
        for work in works:
            if not work["task"].strip() or not work["result"].strip() or len(work["result"]) > 200:
                errors.append(f"{key}: invalid work")
            for code in re.findall(r"```python\s*\n(.*?)```", work["result"], re.S):
                ast.parse(code)
        spec = copy.deepcopy(job["chats"][0]["spec"])
        spec.update(humans=humans, owner=humans[0], topic=row["topic"], skeleton=skeleton,
                    with_summary=bool(row.get("summary_before")), quiet=any(s["kind"] == "quiet" for s in skeleton),
                    talks=[s["note"] for s in skeleton if s.get("ask") == "talk"],
                    work=[{"by": s["s"], "what": s["note"], "typed": s["typed"]}
                          for s in skeleton if s.get("ask") == "work"], computer=None, moment="", joke=False)
        answer = {"id": key, "by": "GPT-6", "summary_before": row.get("summary_before", ""),
                  "concerns": concerns, "lines": text, "work": works}
        normalized = owner.assemble_agent_chat(answer, spec, name, ["機魂", "馬基納"])
        _, reason = owner.check_script(normalized, name, spec, ["機魂", "馬基納"])
        if reason:
            errors.append(f"{key}: owner check: {reason}")
        bucket["tasks"].append({"id": key, "spec": spec})
        bucket["answers"].append(answer)
    shared = set(buckets["train"]["roles"]) & set(buckets["eval"]["roles"])
    if shared:
        errors.append(f"train/eval share {len(shared)} exact role lines")
    if buckets["train"]["people"] & buckets["eval"]["people"]:
        errors.append("train/eval humans overlap")
    repeated = {t: n for b in buckets.values() for t, n in Counter(b["roles"]).items() if n > 2}
    if repeated:
        errors.append(f"role lines repeated over twice: {len(repeated)}")
    print(f"manuscript rows={len(rows)}; role normalization differences={len(corrections)}")
    if corrections:
        errors.append("source requires Taiwan Traditional normalization")
        print("normalization locations=" + json.dumps(corrections, ensure_ascii=True))
    for error in errors:
        print(error)
    if errors:
        print("FAIL: no derived files written")
        return 1
    for split, bucket in buckets.items():
        (root / f"machine-spirit-2.{split}.tasks.json").write_text(
            json.dumps({"persona": job["persona"], "chats": bucket["tasks"]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        (root / f"machine-spirit-2.{split}.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in bucket["answers"]), encoding="utf-8", newline="\n")
        print(f"{split}: scenes={len(bucket['answers'])}, role_lines={len(bucket['roles'])}, quiet={bucket['quiet']}")
    print("exact role overlap=0; human overlap=0; Python snippets parse; existing owner checks pass")
    print("source_sha256=" + hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
