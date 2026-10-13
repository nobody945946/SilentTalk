"""The machine-spirit character: persona drafts from an open-weight teacher.

The owner described the character in their own words (OWNER_BRIEF). An
open-weight teacher turns that into persona sheets in SilentTalk's Persona
schema plus a lore glossary; the owner picked one, which the app now ships as
persona.MACHINE_SPIRIT. Claude does not write persona text or training data
(dev-box rule 5).

    .venv/bin/python scripts/dev/machine_spirit.py drafts --variants 1,2,3
    .venv/bin/python scripts/dev/machine_spirit.py verify-lore
    .venv/bin/python scripts/dev/machine_spirit.py builtin --chardata .runtime/dev/chardata-ms2
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from serve_wait import start

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from silenttalk.persona import (  # noqa: E402
    MACHINE_SPIRIT,
    REPLY_LENGTHS,
    TEXT_FIELDS,
    TRAIT_AXES,
    Persona,
    Relationship,
    persona_to_dict,
    validate_persona,
)

OUT = ROOT / ".runtime/dev/machine-spirit"
SERVER = ROOT / ".runtime/tools/llama.cpp-b11193-src/build-cuda/bin/llama-server"
# The dev box's one teacher (the owner, 2026-10-07: with Qwen3.8 no other
# model is needed); dense 27B, so on the GPU, its thinking capped.
TEACHER = ROOT / ".runtime/models/teacher/Qwen3.8-27B-UD-Q4_K_XL.gguf"
PORT = 18210

# The owner's own words (2026-10-03), the only source of the character.
OWNER_BRIEF = (
    "腳色設定是戰錘40k的機魂，足夠聰明到能做Agent，忠誠的機械教出身機魂，"
    "至少跟他玩腳色帶入他能對得起來他的人設，語音是中性電子音。"
    "可以交代作代理式ai的工作，也有自由連上網搜尋資料的權限，coding能力特化加強。"
    "他很清楚40k的故事背景，熟悉到甚至能走出第四面牆，比如跟他開玩笑說：現在可是2k古泰拉時期，"
    "你看到外面這樣多蓬勃發展的憎惡智能，該怎麼辦？他可以用忠誠派機魂的人設跟我一起開玩笑，補腦洞，"
    "所以模型要夠強夠會推理，還要熟知40k背景，因為是機魂，所以Agent也處理得很好。"
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
    axes = "、".join(f"{a.key}（1＝{a.low}，5＝{a.high}）" for a in TRAIT_AXES)
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
8. 它非常熟悉 40K 的背景，能打破第四面牆：主人開玩笑說現在是 2K 古泰拉、外面到處是憎惡智能時，它能用忠誠派機魂的立場接梗、補腦洞、自嘲，幽默但不失忠誠。幽默風格和代表台詞要表現這一點。
9. 用語只用 40K 正典裡真的有的東西（例如萬機神、機械神、原動力、機魂、技術神甫、賢者、機僕、護教軍、標準模板構造、憎惡智能、鐵人、科技黑暗時代、古泰拉、智域、二進制語、思考機），不要自創術語。
10. 名字要像機械教替機器取的名字（例如拉丁風格的稱號加編號），朋友叫它的暱稱要短、好念。

角色卡欄位：
- name：名字（最多 24 字，要像機械教替機器取的名字）
{fields}
- reply_length：{" / ".join(REPLY_LENGTHS)} 其中之一
- traits：個性滑桿，鍵為 {axes}，數值 1–5，3 是中性可省略；注意方向，例如 polish 填 1 是「文雅不說髒話」
- relationships：最多 3 列 {{"name","relation"}}，至少包含主人（name 用「主人」）

sample_lines 是 3–5 句代表台詞，用換行分隔的純文字，不要加引號、編號或括號。
另外列出 lore：12–20 個這個角色會用到的 40K 用語，每個 {{"term","meaning"}}，term 用台灣常見的繁體中文譯名（可附英文），meaning 一句話說明正典意思。

只輸出 JSON 物件，鍵為 name、上面每個欄位鍵、reply_length、traits、relationships、lore。"""


def ask(messages: list[dict], seed: int) -> dict:
    body = json.dumps({
        "messages": messages,
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


def draft(variant: int) -> tuple[dict, Persona] | None:
    """One sheet; a sheet the product rejects (a field too long) goes back to
    the teacher with the product's own message, to fix only that field."""
    for attempt in range(3):
        messages = [{"role": "system", "content": DRAFT_SYSTEM},
                    {"role": "user", "content": draft_prompt(variant - 1)}]
        raw = ask(messages, seed=100 * variant + attempt)
        for repair in range(3):
            try:
                return raw, to_persona(variant - 1, raw)
            except Exception as exc:  # noqa: BLE001 - PersonaError and malformed fields
                print(f"draft {variant} attempt {attempt + 1}.{repair} rejected: {exc}", flush=True)
                if repair == 2:
                    break
                messages += [
                    {"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
                    {"role": "user", "content": f"這份角色卡沒有通過檢查：{exc}"
                     "請只修正這個問題（例如把那一欄縮短到上限以內，意思不變），"
                     "其他欄位一字不改，輸出完整的 JSON。"},
                ]
                raw = ask(messages, seed=100 * variant + attempt)
    return None


def drafts(variants: list[int], threads: int, teacher: Path, extra: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "drafts.json"
    # Redrafting some variants keeps the others.
    results = {item["variant"]: item for item in
               (json.loads(path.read_text(encoding="utf-8")) if path.is_file() else [])}
    server = start(
        [str(SERVER), "--model", str(teacher), "--host", "127.0.0.1", "--port", str(PORT),
         "--ctx-size", "8192", "--n-gpu-layers", "99", "--threads", str(threads), "--jinja",
         "--parallel", "1", "--reasoning-budget", "1024", *extra], timeout=900)
    try:
        for variant in variants:
            made = draft(variant)
            if made is None:
                print(f"draft {variant} failed", flush=True)
                continue
            raw, persona = made
            results[variant] = {"variant": variant, "persona": raw, "lore": raw.get("lore", []),
                                "rendered": persona.render_system_block()}
            print(f"draft {variant} ok", flush=True)
    finally:
        server.terminate()
        server.wait(timeout=60)
    path.write_text(json.dumps([results[k] for k in sorted(results)], ensure_ascii=False,
                               indent=1), encoding="utf-8")
    print(f"{len(results)} drafts -> {path}")


CHECKER = ROOT / ".runtime/models/teacher/gemma-4-31B-it-UD-IQ3_XXS.gguf"
LORE_CHECK = (
    "下面是《戰鎚40K》用語和它的解釋。這個解釋（含括號裡的英文對照）完全符合正典嗎？"
    "只要有任何一處錯誤或張冠李戴就回答 否。只回答 是 或 否。\n\n{term}：{meaning}"
)


def verify_lore(threads: int, extra: list[str]) -> None:
    """Keep only glossary items an open-weight checker of another family
    (Gemma 31B, 97% on the 40K quiz) finds true to canon: the glossary steers
    the teacher's scripts and the line checks."""
    path = OUT / "drafts.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    server = start(
        [str(SERVER), "--model", str(CHECKER), "--host", "127.0.0.1", "--port", str(PORT),
         "--ctx-size", "4096", "--n-gpu-layers", "0", "--threads", str(threads), "--jinja",
         "--parallel", "1", *extra], timeout=900)
    try:
        for item in items:
            kept, dropped = [], []
            for entry in item["lore"]:
                body = json.dumps({
                    "messages": [{"role": "user", "content": LORE_CHECK.format(**entry)}],
                    "temperature": 0.0, "max_tokens": 2, "grammar": 'root ::= "是" | "否"',
                    "chat_template_kwargs": {"enable_thinking": False}}).encode()
                request = urllib.request.Request(
                    f"http://127.0.0.1:{PORT}/v1/chat/completions", body,
                    {"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=1800) as response:
                    answer = json.loads(response.read())["choices"][0]["message"]["content"]
                (kept if answer.strip() == "是" else dropped).append(entry)
            item["lore"], item["lore_dropped"] = kept, dropped
            item["persona"]["lore"] = kept
            print(f"draft {item['variant']}: kept {len(kept)}, dropped "
                  f"{[e['term'] for e in dropped]}", flush=True)
    finally:
        server.terminate()
        server.wait(timeout=60)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


# How speech recognition writes 機魂 (the app's name matcher accepts them):
# character_data.py puts them into the others' spoken lines now and then.
STT_VARIANTS = ("雞魂", "基魂")


def builtin(chardata: Path, variant: int) -> None:
    """The app's own machine spirit (persona.MACHINE_SPIRIT, as it ships) as
    the one persona row of an agent character for character_data.py, so the
    training requests are the app's byte for byte. Its lore glossary is the
    checked one of the draft the card came from."""
    item = next((item for item in json.loads((OUT / "drafts.json").read_text(encoding="utf-8"))
                 if item["variant"] == variant), None)
    if item is None or item["persona"].get("name") != MACHINE_SPIRIT.name:
        raise SystemExit(f"draft {variant} is not the card the app ships ({MACHINE_SPIRIT.name})")
    row = {**persona_to_dict(MACHINE_SPIRIT), "agent": True, "owner_relation": "",
           "lore": [entry for entry in item["lore"] if isinstance(entry, dict)
                    and entry.get("term") and entry.get("meaning")],
           "stt_variants": list(STT_VARIANTS), "role": "machine spirit"}
    chardata.mkdir(parents=True, exist_ok=True)
    (chardata / "personas.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    print(f"{MACHINE_SPIRIT.name} -> {chardata / 'personas.jsonl'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("drafts")
    d.add_argument("--variants", default="1,2,3", help="which flavours to (re)draft")
    d.add_argument("--threads", type=int, default=12)
    d.add_argument("--teacher", type=Path, default=TEACHER)
    d.add_argument("--server-args", default="",
                   help='extra llama-server args, e.g. "--reasoning-budget 2048"')
    v = sub.add_parser("verify-lore")
    v.add_argument("--threads", type=int, default=12)
    v.add_argument("--server-args", default="")
    b = sub.add_parser("builtin")
    b.add_argument("--chardata", type=Path, required=True, help="a new data directory")
    b.add_argument("--variant", type=int, default=2, help="the draft the shipped card came from")
    args = parser.parse_args()
    if args.command == "verify-lore":
        verify_lore(args.threads, args.server_args.split())
    if args.command == "builtin":
        builtin(args.chardata, args.variant)
    if args.command == "drafts":
        drafts([int(v) for v in args.variants.split(",")], args.threads, args.teacher,
               args.server_args.split())


if __name__ == "__main__":
    main()
