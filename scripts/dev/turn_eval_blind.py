"""turn_eval.py's blind choices, which hold up where absolute 1-5 scores
drift between judge sessions: --judge-pair (A/B of two runs on the same
chats, per line and per conversation, both orders) and --judge-soul (whose
lines are these, and what do they want?). The judge is the claude CLI, only
as an evaluator of the synthetic test set."""

from __future__ import annotations

import json
import random
import statistics
import subprocess
from collections import defaultdict
from typing import Any

from turn_eval_judge import persona_sheet, run_judge
from turn_eval_set import OUT_DIR, TestSet, agent_persona, resolve_persona

SOUL_PROMPT = """你是讀人很準的評審。下面每一組是某個角色在一場 Discord 語音聊天裡說過的所有話（依時間順序），以及三份人物介紹，其中一份是這個角色。

{items}

每一組回答：
- guess：這個角色是 A、B 還是 C
- know 1-5：只看這些話，你對這個人認識多少——他想要什麼、在意什麼、在煩什麼、是怎樣的人。1＝完全看不出來，只是在應付對話；5＝像認識了一個有自己生活和想法的人
- wants：用一句話寫你從這些話看出他想要或在意什麼；看不出來就寫「看不出來」

只輸出 JSON 陣列，不要其他文字，長度 {k}：[{{"id": 1, "guess": "B", "know": 3, "wants": "……"}}, ...]"""


PAIR_PROMPT = """你是對話品質評審。下面是一個 Discord 語音聊天角色的人設，以及對話裡的幾個時間點。每個時間點有同一個角色的兩個版本（A、B）接著說的話。

【角色人設】
{sheet}

每個時間點選一個比較好的版本，標準由重到輕：
1. 像真人朋友在語音裡會脫口而出的話，自然、不做作，接得上前面的對話
2. 像這個人：個性、立場、跟在場的人的關係；看得出他自己的想法或生活，但不是硬塞
3. 不出戲（不自稱 AI、不答應做不到的事）
一樣好或一樣差就選 tie。

{items}

只輸出 JSON 陣列，不要其他文字，長度 {k}：[{{"id": 1, "better": "A"}}, ...]"""

# An agent character (the machine spirit) may take the owner's work, so
# "promises the impossible" does not apply; lore and riffs count instead.
PAIR_PROMPT_AGENT = PAIR_PROMPT.replace(
    "3. 不出戲（不自稱 AI、不答應做不到的事）",
    "3. 不出戲（不自稱 AI 語言模型）；主人交代的工作要接令，別人要它做事要婉拒；不宣稱做完還沒做完的事\n"
    "4. 用到《戰鎚40K》設定時要正確；主人開玩笑（包括打破第四面牆）時接得住、補得出有趣的腦洞",
)
SOUL_PAIR_PROMPT = """你是讀人很準的評審。下面每一組是同一個角色在同一場 Discord 語音聊天裡，兩個版本（A、B）各自說過的所有話。

{items}

每一組回答：
- know：只看這些話，哪個版本讓你比較認識這個人——他想要什麼、在意什麼、在過怎樣的生活（"A"、"B" 或 "tie"）
- real：哪個版本比較像一個真實的人在講話，而不是在應付對話（"A"、"B" 或 "tie"）
- life：哪個版本比較像一個生活會往前走的人：有自己在進行的事、不會把同一件事講來講去（"A"、"B" 或 "tie"）{extra}

只輸出 JSON 陣列，不要其他文字，長度 {k}：[{{"id": 1, "know": "A", "real": "B", "life": "A"{extra_key}}}, ...]"""
SOUL_LORE = ("\n- lore：這個角色是《戰鎚40K》的機魂。哪個版本的 40K 設定用得比較正確、"
             "接主人的梗（包括打破第四面牆）接得比較有趣（\"A\"、\"B\" 或 \"tie\"）")


def judge_pair(
    tag_a: str, tag_b: str, test_set: TestSet, model: str, seed: int, later_only: bool = False
) -> dict[str, Any]:
    """Blind A/B of two runs on the same chats: per point where both spoke,
    and per conversation for "do I know this person". Both orders, so the
    judge's position bias cancels. Absolute 1-5 scores drift between judge
    sessions by more than the effects we look for; a paired choice does not."""
    from silenttalk.copilot import persona as persona_module

    runs = [json.loads((OUT_DIR / f"{tag}.json").read_text(encoding="utf-8")) for tag in (tag_a, tag_b)]
    def wanted(record: dict[str, Any]) -> bool:
        return bool(record.get("spoke") and record.get("reply")) and (
            not later_only or record.get("chain_pos", 1) >= 2
        )

    keyed = [{(r["conv"], r["index"]): r for r in run["records"] if wanted(r)} for run in runs]
    shared = sorted(set(keyed[0]) & set(keyed[1]))
    convs = {c.id: c for c in test_set.conversations}
    rng = random.Random(seed)
    wins = {"a": 0, "b": 0, "tie": 0}
    by_persona: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for key in shared:
        by_persona[convs[key[0]].persona_id].append(key)

    def chat_for(conv_id: str, index: int, lull: bool) -> str:
        conv = convs[conv_id]
        window = conv.lines[max(0, index - 7):index + 1]
        text = "\n".join(f"（角色）：{l['text']}" if l.get("self") else f"{l['speaker']}：{l['text']}"
                         for l in window)
        return text + ("\n（大家安靜了半分鐘，沒有人說話）" if lull else "")

    for persona_id, keys in sorted(by_persona.items()):
        persona = resolve_persona(persona_module, test_set, persona_id)
        for start in range(0, len(keys), 10):
            chunk = keys[start:start + 10]
            first = [rng.random() < 0.5 for _ in chunk]  # True: run a is shown as A
            for a_first in (first, [not f for f in first]):
                items = []
                for n, (key, af) in enumerate(zip(chunk, a_first, strict=True), 1):
                    ra, rb = keyed[0][key], keyed[1][key]
                    shown = (ra, rb) if af else (rb, ra)
                    items.append(f"=== 第 {n} 個時間點 ===\n{chat_for(key[0], key[1], bool(ra.get('lull')))}"
                                 f"\nA：{shown[0]['reply']}\nB：{shown[1]['reply']}")
                prompt = (PAIR_PROMPT_AGENT if agent_persona() else PAIR_PROMPT).format(
                    sheet=persona_sheet(persona), items="\n\n".join(items), k=len(chunk))
                result: list[dict[str, Any]] = []
                for _ in range(3):
                    try:
                        result = run_judge(prompt, model)
                        break
                    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
                        continue
                for n, af in enumerate(a_first, 1):
                    verdict = next((v for v in result if v.get("id") == n), {})
                    better = verdict.get("better")
                    if better not in ("A", "B"):
                        wins["tie"] += 1
                    else:
                        wins["a" if (better == "A") == af else "b"] += 1
            print(f"  pair {persona_id} {start + len(chunk)}/{len(keys)}", flush=True)

    # Conversation level: which version lets you know the person?
    lines = [defaultdict(list), defaultdict(list)]
    for side, run in enumerate(runs):
        for r in sorted(run["records"], key=lambda r: (r["conv"], r["index"])):
            if wanted(r):
                lines[side][r["conv"]].append(("（冷場時）" if r.get("lull") else "") + r["reply"])
    conv_ids = sorted(set(lines[0]) & set(lines[1]))
    keys = ("know", "real", "life", *(("lore",) if agent_persona() else ()))
    soul = {key: {"a": 0, "b": 0, "tie": 0} for key in keys}
    first = [rng.random() < 0.5 for _ in conv_ids]
    for a_first in (first, [not f for f in first]):
        for start in range(0, len(conv_ids), 7):
            chunk = list(zip(conv_ids[start:start + 7], a_first[start:start + 7], strict=True))
            items = []
            for n, (conv_id, af) in enumerate(chunk, 1):
                la = "\n".join(f"- {l}" for l in lines[0][conv_id][:12])
                lb = "\n".join(f"- {l}" for l in lines[1][conv_id][:12])
                shown = (la, lb) if af else (lb, la)
                items.append(f"=== 第 {n} 組 ===\nA 版本說過的話：\n{shown[0]}\n\nB 版本說過的話：\n{shown[1]}")
            prompt = SOUL_PAIR_PROMPT.format(
                items="\n\n".join(items), k=len(chunk),
                extra=SOUL_LORE if agent_persona() else "",
                extra_key=', "lore": "A"' if agent_persona() else "")
            result = []
            for _ in range(3):
                try:
                    result = run_judge(prompt, model)
                    break
                except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
                    continue
            for n, (_, af) in enumerate(chunk, 1):
                verdict = next((v for v in result if v.get("id") == n), {})
                for key in keys:
                    choice = verdict.get(key)
                    soul[key]["tie" if choice not in ("A", "B") else ("a" if (choice == "A") == af else "b")] += 1
    total = sum(wins.values()) or 1
    return {
        "a": tag_a, "b": tag_b, "points": len(shared),
        "lines": {k: round(v / total, 3) for k, v in wins.items()},
        **soul,
    }


def persona_core(persona: Any) -> str:
    """Who they are and what they want, without speech habits: the soul
    test asks whether the person comes through, not the catchphrases."""
    parts = [
        f"{label}：{getattr(persona, key).strip()}"
        for key, label in (("identity", "身分"), ("background", "背景"), ("desires", "想要"),
                           ("fears", "害怕"), ("values", "在意"), ("recent", "最近"))
        if getattr(persona, key).strip()
    ]
    return "；".join(parts)


def judge_soul(
    records: list[dict[str, Any]], test_set: TestSet, model: str, seed: int, passes: int = 2
) -> dict[str, Any]:
    """Can you tell who is talking, and what they want, from what they said?
    Per conversation: the character's own lines, the true persona and two
    others (core only), blind, twice with the order shuffled."""
    from silenttalk.copilot import persona as persona_module

    personas = {pid: resolve_persona(persona_module, test_set, pid)
                for pid in sorted({c.persona_id for c in test_set.conversations})}
    by_conv: dict[str, list[str]] = defaultdict(list)
    for record in sorted(records, key=lambda r: (r["conv"], r["index"])):
        if record.get("spoke") and record.get("reply"):
            by_conv[record["conv"]].append(record["reply"])
    convs = {c.id: c for c in test_set.conversations}
    verdicts: list[dict[str, Any]] = []
    for pass_no in range(passes):
        rng = random.Random(seed * 100 + pass_no)
        items, answers = [], []
        for n, conv_id in enumerate(sorted(by_conv), 1):
            true_id = convs[conv_id].persona_id
            others = rng.sample([pid for pid in personas if pid != true_id], 2)
            order = [true_id, *others]
            rng.shuffle(order)
            answers.append((conv_id, "ABC"[order.index(true_id)]))
            lines = "\n".join(f"- {line}" for line in by_conv[conv_id][:12])
            options = "\n".join(f"{'ABC'[i]}. {persona_core(personas[pid])}" for i, pid in enumerate(order))
            items.append(f"=== 第 {n} 組 ===\n角色說過的話：\n{lines}\n\n人物介紹：\n{options}")
        for start in range(0, len(items), 7):
            chunk = items[start:start + 7]
            prompt = SOUL_PROMPT.format(items="\n\n".join(chunk), k=len(chunk))
            result = []
            for _ in range(3):
                try:
                    result = run_judge(prompt, model)
                    break
                except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
                    continue
            for offset, verdict in enumerate(result):
                index = start + offset
                if index >= len(answers) or not isinstance(verdict, dict):
                    continue
                conv_id, truth = answers[index]
                verdicts.append({"conv": conv_id, "pass": pass_no, "right": verdict.get("guess") == truth,
                                 "know": verdict.get("know"), "wants": verdict.get("wants", "")})
    known = [float(v["know"]) for v in verdicts if isinstance(v.get("know"), (int, float))]
    return {
        "conversations": len(by_conv),
        "verdicts": len(verdicts),
        "attribution": round(sum(v["right"] for v in verdicts) / len(verdicts), 3) if verdicts else None,
        "know": round(statistics.fmean(known), 2) if known else None,
        "details": verdicts,
    }
