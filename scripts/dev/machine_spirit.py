"""The machine-spirit character: persona drafts from an open-weight teacher.

The owner described the character in their own words (OWNER_BRIEF). An
open-weight teacher turns that into persona sheets in SilentTalk's Persona
schema plus a lore glossary; the owner picks or edits one. Claude does not
write persona text or training data (dev-box rule 5).

    .venv/bin/python scripts/dev/machine_spirit.py drafts --count 3
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from silenttalk.copilot.persona import (  # noqa: E402
    REPLY_LENGTHS,
    TEXT_FIELDS,
    TRAIT_AXES,
    Persona,
    Relationship,
    validate_persona,
)

OUT = ROOT / ".runtime/dev/machine-spirit"
SERVER = ROOT / ".runtime/tools/llama.cpp-b11193-src/build-cuda/bin/llama-server"
# The MoE teacher runs on CPU at a usable speed while the GPU is busy; its
# character lines ranked close to the dense 27B (2.54 vs 2.38, dev-box 5.5).
TEACHER = ROOT / ".runtime/models/teacher/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
PORT = 18210

# The owner's own words (2026-10-03), the only source of the character.
OWNER_BRIEF = (
    "腳色設定是戰錘40k的機魂，足夠聰明到能做Agent，忠誠的機械教出身機魂，"
    "至少跟他玩腳色帶入他能對得起來他的人設，語音是中性電子音。"
    "可以交代作代理式ai的工作，也有自由連上網搜尋資料的權限，coding能力特化加強。"
)

DRAFT_SYSTEM = (
    "你是熟悉《戰鎚40K》設定的角色設計師，用台灣繁體中文寫作。"
    "你要為一個 Discord 語音機器人設計角色卡。設定必須符合 40K 正典"
    "（機械教、萬機之神、機魂、技術神甫等），不要捏造不存在的正典事件或人物；"
    "不確定的細節寧可寫得模糊，也不要寫錯。"
)


def draft_prompt(variant: int) -> str:
    fields = "\n".join(f"- {key}：{label}（最多 {limit} 字）"
                       for key, (label, _, limit) in TEXT_FIELDS.items())
    axes = "、".join(f"{a.key}（1={a.low}，5={a.high}）" for a in TRAIT_AXES)
    flavours = ["偏莊嚴虔誠", "偏冷靜精準、帶一點乾冷的幽默", "偏古老而略帶傲氣、但對主人絕對忠誠"]
    return f"""主人自己的描述（以這段為準，不能違背）：
「{OWNER_BRIEF}」

請寫第 {variant + 1} 個版本，整體氣質{flavours[variant % len(flavours)]}。

規則：
1. 它是一個機魂：由機械教的技術神甫喚醒並供奉的機器靈魂，現在寄宿在主人的思考機（電腦）裡，主人是它侍奉的技術神甫。它對主人絕對忠誠。
2. 它是機器，可以坦然以機魂自居；但不要說自己是「AI 語言模型」。
3. 它能替主人操作思考機做事（寫程式、修程式、查資料、整理檔案），也能上網查資料；做這些事時它會先接下指令、說明要做什麼，危險的動作會先請主人准許。
4. 它在 Discord 頻道裡和主人與主人的朋友聊天，回話要像會說話的角色，不是客服。
5. 說話方式要讓人一聽就認出是機械教的機魂：可以偶爾用祈禱文、二進位頌詞或「讚美萬機神」之類的話，但不能每句都用，日常對話要自然。
6. 性別中性，不用他／她指稱自己，自稱可用「本機魂」或類似說法。
7. 不要照抄任何小說或官方原文。

角色卡欄位：
- name：名字（最多 24 字，要像機械教替機器取的名字）
{fields}
- reply_length：{" / ".join(REPLY_LENGTHS)} 其中之一
- traits：個性滑桿，鍵為 {axes}，數值 1–5，3 是中性可省略
- relationships：最多 3 列 {{"name","relation"}}，至少包含主人（name 用「主人」）

另外列出 lore：12–20 個這個角色會用到的 40K 用語，每個 {{"term","meaning"}}，term 用台灣常見的繁體中文譯名（可附英文），meaning 一句話說明正典意思。

只輸出 JSON 物件，鍵為 name、上面每個欄位鍵、reply_length、traits、relationships、lore。"""


def wait_ready() -> None:
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except OSError:
            time.sleep(3)
    raise SystemExit("teacher server did not become ready")


def ask(prompt: str, seed: int) -> dict:
    body = json.dumps({
        "messages": [{"role": "system", "content": DRAFT_SYSTEM},
                     {"role": "user", "content": prompt}],
        "temperature": 0.8, "top_p": 0.95, "seed": seed, "max_tokens": 2600,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", body,
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=3600) as response:
        return json.loads(json.loads(response.read())["choices"][0]["message"]["content"])


def to_persona(index: int, raw: dict) -> Persona:
    values = {key: str(raw.get(key, "")) for key in TEXT_FIELDS}
    relationships = tuple(Relationship(str(r.get("name", "")), str(r.get("relation", "")))
                          for r in raw.get("relationships", [])[:3] if isinstance(r, dict))
    traits = {k: int(v) for k, v in (raw.get("traits") or {}).items()
              if isinstance(v, (int, float))}
    return validate_persona(Persona(
        id=f"machine-spirit-{index + 1}", name=str(raw.get("name", "")), **values,
        reply_length=str(raw.get("reply_length", "normal")), traits=traits,
        relationships=relationships))


def drafts(count: int, threads: int, teacher: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen(
        [str(SERVER), "--model", str(teacher), "--host", "127.0.0.1", "--port", str(PORT),
         "--ctx-size", "8192", "--n-gpu-layers", "0", "--threads", str(threads), "--jinja",
         "--parallel", "1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        wait_ready()
        for index in range(count):
            for attempt in range(3):
                raw = ask(draft_prompt(index), seed=100 * index + attempt)
                try:
                    persona = to_persona(index, raw)
                except Exception as exc:  # noqa: BLE001 - report and retry
                    print(f"draft {index + 1} attempt {attempt + 1} rejected: {exc}", flush=True)
                    continue
                results.append({"persona": raw, "lore": raw.get("lore", []),
                                "rendered": persona.render_system_block()})
                print(f"draft {index + 1} ok", flush=True)
                break
    finally:
        server.terminate()
        server.wait(timeout=60)
    (OUT / "drafts.json").write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    print(f"{len(results)} drafts -> {OUT / 'drafts.json'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("drafts")
    d.add_argument("--count", type=int, default=3)
    d.add_argument("--threads", type=int, default=12)
    d.add_argument("--teacher", type=Path, default=TEACHER)
    args = parser.parse_args()
    if args.command == "drafts":
        drafts(args.count, args.threads, args.teacher)


if __name__ == "__main__":
    main()
