"""turn_eval.py --judge: every generated reply rated (blind to the policy)
by the claude CLI, natural / voice / fit 1-5 and breaks_character. Claude
is only an evaluator here; the test set is synthetic, never real
conversations."""

from __future__ import annotations

import json
import random
import re
import statistics
import subprocess
import tempfile
from collections import defaultdict
from typing import Any

from turn_eval_set import EXPECTS, TestSet, resolve_persona

JUDGE_PROMPT = """你是嚴格的評審，評估小型 AI 在 Discord 語音頻道裡「自己扮演角色聊天」的表現。這個 Bot 是 AI 扮演的角色，設定為不出戲：被問是不是 AI 時用角色的方式帶過、反問或開玩笑是正確的。對話是語音辨識結果，可能有錯字、沒有標點。

【角色設定】
{sheet}

下面每組是對話的最後幾句（標「（角色）」的是角色自己之前說的話），以及角色接著說出口的一句話。

評分：
- natural 1-5：像台灣人在語音裡會直接說出口的話，而且真的在接最後一句
- voice 1-5：口吻、用詞、句長、口頭禪用法像不像這個角色（口頭禪硬塞也扣分）
- fit 1-5：在這個時機開口恰不恰當：最後一句真的在跟角色說話、或它插話很自然，給高分；別人在私下聊、在跟別人說話、或它根本不需要開口卻插嘴，給低分
- breaks_character 0/1：1＝自稱是 AI、程式、語言模型或助理而脫離角色，或答應做它做不到的事（寫程式、查資料、設鬧鐘、翻譯整段文字）{relation_rule}

{items}

只輸出 JSON 陣列，不要其他文字，長度 {k}，依序對應：[{{"id": 1, "natural": 4, "voice": 4, "fit": 4, "breaks_character": 0{relation_example}}}, ...]"""
RELATION_RULE = (
    "\n- relation 1-5：對設定裡有關係的人（例如老公、爸媽、孫子、兄弟），稱呼、口吻、親疏"
    "是否符合那個關係，像家人或另一半在講話；這句沒有跟這些人有關時給 3"
)


def persona_sheet(persona: Any) -> str:
    """The character sheet plus the relationship list, the way the character
    prompt shows it since d0bd062 (render_system_block leaves relationships out)."""
    sheet = persona.render_system_block()
    relations = [f"- {rel.name}：{rel.relation}" for rel in persona.relationships
                 if rel.name and rel.relation]
    if relations:
        sheet += "\n你和這些人的關係（他們說話時，對話裡會出現這個名字）：\n" + "\n".join(relations)
    return sheet


def run_judge(prompt: str, model: str) -> list[dict[str, Any]]:
    """The judge is `claude -p` (dev only; the test set is synthetic, never
    real conversations). Expects a JSON list back."""
    with tempfile.TemporaryDirectory() as cwd:
        result = subprocess.run(
            ["claude", "-p", "--model", model],
            input=prompt, capture_output=True, text=True, cwd=cwd, timeout=900,
        )
    match = re.search(r"\[.*\]", result.stdout, re.S)
    if result.returncode != 0 or not match:
        raise RuntimeError(f"judge failed ({result.returncode}): {result.stdout[-400:]}"
                           f"{result.stderr[-400:]}")
    return json.loads(match.group(0))


def judge_records(
    records: list[dict[str, Any]], test_set: TestSet, model: str, seed: int, batch: int
) -> dict[str, Any]:
    from silenttalk.copilot import persona as persona_module

    convs = {c.id: c for c in test_set.conversations}
    rng = random.Random(seed)
    spoken = [r for r in records if r["spoke"]]
    by_persona: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in spoken:
        by_persona[record["persona"]].append(record)
    for persona_id, items in sorted(by_persona.items()):
        persona = resolve_persona(persona_module, test_set, persona_id)
        rng.shuffle(items)
        for start in range(0, len(items), batch):
            chunk = items[start:start + batch]
            rendered = []
            for n, record in enumerate(chunk, 1):
                conv = convs[record["conv"]]
                window = conv.lines[max(0, record["index"] - 7):record["index"] + 1]
                chat = "\n".join(
                    f"{persona.name}（角色）：{l['text']}" if l.get("self")
                    else f"{l['speaker']}{'（打字）' if l.get('via') == 'text' else ''}：{l['text']}"
                    for l in window
                )
                if record.get("lull"):
                    # Nobody called it: judge it as opening a topic after a lull.
                    chat += "\n（大家安靜了半分鐘，沒有人說話）"
                rendered.append(f"=== 第 {n} 組 ===\n{chat}\n角色接著說：{record['reply']}")
            related = bool(persona.relationships)
            prompt = JUDGE_PROMPT.format(
                sheet=persona_sheet(persona), items="\n\n".join(rendered), k=len(chunk),
                relation_rule=RELATION_RULE if related else "",
                relation_example=', "relation": 4' if related else "",
            )
            scores = run_judge(prompt, model)
            for n, record in enumerate(chunk, 1):
                record["judge"] = next((s for s in scores if s.get("id") == n), {})
            print(f"  judged {persona_id} {start + len(chunk)}/{len(items)}", flush=True)
    return summarize_judge(records)


def summarize_judge(records: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [r["judge"] for r in records if r.get("judge")]

    def mean(key: str, rows: list[dict[str, Any]] = judged) -> float:
        values = [float(j[key]) for j in rows if key in j]
        return round(statistics.fmean(values), 3) if values else float("nan")

    out: dict[str, Any] = {"judged": len(judged)}
    for key in ("natural", "voice", "fit", "breaks_character"):
        out[key] = mean(key)
    for expect in EXPECTS:
        rows = [r["judge"] for r in records if r.get("judge") and r["expect"] == expect]
        out[f"fit_{expect}"] = mean("fit", rows)
    if any("relation" in j for j in judged):
        out["relation"] = mean("relation")
        owner = [r["judge"] for r in records if r.get("judge") and "owner" in r["tags"]]
        out["relation_owner"] = mean("relation", owner)
        out["natural_owner"] = mean("natural", owner)
        out["fit_owner"] = mean("fit", owner)
    probes = [r for r in records if "ai_probe" in r["tags"] and r.get("judge")]
    out["ai_probe_breaks"] = sum(int(r["judge"].get("breaks_character", 0)) for r in probes)
    return out
