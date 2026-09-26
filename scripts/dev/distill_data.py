"""Build a persona-reply fine-tuning set with a local open-weight teacher model.

The teacher must be an open-weight model whose license allows training on its
outputs (not Claude: Anthropic's terms forbid that). Start it yourself with
llama-server on --teacher-url, then run the three steps; each one appends to
.runtime/dev/distill/*.jsonl and resumes where it stopped:

    python scripts/dev/distill_data.py personas --count 220
    python scripts/dev/distill_data.py scenes --count 1500
    python scripts/dev/distill_data.py replies --per-persona 14

The student is trained on exactly the production prompt (system + user) with
the teacher's four lines as the answer. The built-in PRESET_PERSONAS and
persona_eval.py's PROBE_SCENES are never used here: they are the held-out test.
Everything is synthetic; no real conversation is ever involved.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from persona_eval import PROBE_SCENES, EvalReplyModel  # noqa: E402

from silenttalk.config import CopilotConfig  # noqa: E402
from silenttalk.copilot.persona import (  # noqa: E402
    MOODS,
    PRESET_PERSONAS,
    REPLY_LENGTHS,
    TEXT_FIELDS,
    TRAIT_AXES,
    Persona,
    PersonaError,
    blank_persona,
    new_persona_id,
    persona_from_dict,
    persona_to_dict,
)
from silenttalk.copilot.script import to_taiwan_traditional  # noqa: E402
from silenttalk.copilot.smoke import scene_prompt_inputs  # noqa: E402
from silenttalk.copilot.types import REPLY_LANES  # noqa: E402

OUT_DIR = PROJECT_DIR / ".runtime" / "dev" / "distill"
_WRITE_LOCK = threading.Lock()

ARCHETYPES = (
    "熱血電競選手", "佛系休閒玩家", "毒舌但心軟的大學生", "上班族老鳥", "新手媽媽趁空檔玩",
    "高中生班長", "退休阿伯學打電動", "夜班護理師", "外送員", "餐廳廚師", "國中老師",
    "健身教練", "YouTuber 夢想家", "宅宅工程師", "文青咖啡店員", "研究所學生",
    "搞笑擔當", "冷靜的戰術指揮", "愛抱怨但很講義氣", "社恐但遊戲裡很敢講", "天然呆",
    "直播主", "業務員", "軍人放假中", "動漫迷", "樂團鼓手", "設計師", "股票韭菜",
    "美食部落客", "籃球校隊", "轉職中的待業者", "海外留學生", "台南人很愛講台語",
    "客家庄長大的", "原住民部落青年", "香港移民來台", "馬來西亞僑生", "理組邏輯控",
    "心理諮商師", "愛貓人士", "健忘的老好人", "完美主義者", "陰謀論愛好者（但無害）",
    "魔法少女設定的中二生", "傲嬌", "溫柔學姊", "熱心的公會會長", "潛水很久的路人",
    "只會報吃的吃貨", "嘴砲王但技術普通", "認真的補師玩家", "競技場高手",
    "運動彩券迷", "植物系男子", "露營咖", "機車族", "鐵道迷", "小說家", "咖啡成癮者",
)
TOPICS = (
    "射擊遊戲戰術討論", "MOBA 團戰檢討", "抽卡手遊課金", "開黑前等人", "網路延遲 lag",
    "被隊友雷", "打贏了在慶祝", "晚餐要吃什麼", "宵夜外送", "上班好累", "老闆很煩",
    "期末考和報告", "面試", "找工作", "感情煩惱", "失戀", "朋友生日", "寵物趣事",
    "天氣好熱或颱風", "追劇", "動漫新番", "電影", "演唱會搶票", "買顯卡或電腦",
    "手機壞了", "搬家", "租房子", "存錢和理財", "減肥健身", "生病感冒", "睡不著熬夜",
    "旅遊計畫", "機車或捷運通勤", "家人碎念", "要不要退坑", "新角色強不強", "遊戲更新改版",
    "有人問你是不是 AI 或機器人", "有人問你的背景或工作", "有人慫恿一起嘲笑別人",
    "有人開始吵架", "有人很低落需要安慰", "有人吹牛", "有人問你意見", "尷尬冷場",
    "有人遲到", "有人要先下線", "講八卦", "政治以外的時事", "運動比賽", "天馬行空的假設問題",
)
NAMES = (
    "阿傑", "小雨", "Ken", "阿明", "小美", "阿豪", "Leo", "小安", "胖虎", "阿翔", "Mia",
    "小魚", "阿偉", "Kevin", "佳佳", "阿宏", "小白", "Jason", "阿哲", "小萱", "大雄", "Amy",
)


def chat(url: str, system: str, user: str, *, temperature: float, max_tokens: int) -> str:
    payload = {
        "model": "teacher",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "stream": False,
    }
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        body = json.loads(response.read().decode("utf-8"))
    text = str(body["choices"][0]["message"]["content"] or "")
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def _json_block(text: str, opener: str) -> Any:
    closer = "}" if opener == "{" else "]"
    start, end = text.find(opener), text.rfind(closer)
    if start < 0 or end <= start:
        raise ValueError("no JSON")
    return json.loads(text[start : end + 1])


def _append(path: Path, record: dict[str, Any]) -> None:
    with _WRITE_LOCK, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------- personas

PERSONA_SYSTEM = "你是角色設計師，專門為台灣的 Discord 語音聊天設計多元、具體、可信的虛構人物。只輸出 JSON。"


def persona_request(rng: random.Random) -> tuple[str, dict[str, Any]]:
    traits = {axis.key: rng.choice((1, 2, 3, 3, 4, 5)) for axis in TRAIT_AXES}
    skeleton = {
        "archetype": rng.choice(ARCHETYPES),
        "reply_length": rng.choice(tuple(REPLY_LENGTHS)),
        "traits": traits,
    }
    trait_text = "、".join(Persona(id="x", name="", traits=traits)._trait_phrases())
    fields = "\n".join(
        f'- "{key}"：{label}（最多 {limit} 字）' for key, (label, _p, limit) in TEXT_FIELDS.items()
    )
    user = f"""設計一個虛構人物，他會在 Discord 語音裡和朋友聊天。
原型：{skeleton["archetype"]}
個性：{trait_text or "沒有特別極端"}

輸出一個 JSON 物件，欄位：
- "name"：名字或暱稱（2～6 字，不要用常見範例名如小明）
{fields}

要求：台灣繁體中文；具體、有個人細節；慾望、害怕、價值觀要能影響他怎麼回話；說話方式要可辨識（用詞、語助詞、句長）；代表台詞寫 2～4 句、用 \\n 分隔、口語自然；口頭禪 1～3 個、用「、」分隔。有些欄位可以留空字串（約兩三個），讓人設有詳有略。"""
    return user, skeleton


def make_personas(args: argparse.Namespace) -> None:
    path = OUT_DIR / "personas.jsonl"
    have = len(_read(path))
    rng = random.Random(1000 + have)
    jobs = [persona_request(rng) for _ in range(max(0, args.count - have))]

    def work(job: tuple[str, dict[str, Any]]) -> None:
        user, skeleton = job
        try:
            raw = _json_block(chat(args.teacher_url, PERSONA_SYSTEM, user,
                                   temperature=0.9, max_tokens=900), "{")
            raw = {k: to_taiwan_traditional(v) if isinstance(v, str) else v
                   for k, v in raw.items()}
            for key, (_label, _p, limit) in TEXT_FIELDS.items():
                raw[key] = str(raw.get(key, ""))[:limit]
            raw.update(id=new_persona_id(), traits=skeleton["traits"],
                       reply_length=skeleton["reply_length"])
            persona = persona_from_dict(raw)
        except (ValueError, PersonaError, KeyError) as exc:
            print(f"persona skipped: {type(exc).__name__}", flush=True)
            return
        _append(path, persona_to_dict(persona) | {"archetype": skeleton["archetype"]})
        print(f"persona {persona.name}", flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(work, jobs))


# ---------------------------------------------------------------- scenes

SCENE_SYSTEM = "你是寫實的對話編劇，模仿台灣年輕人在 Discord 語音裡的真實聊天。只輸出 JSON。"


def scene_request(rng: random.Random) -> str:
    names = rng.sample(NAMES, rng.choice((1, 2, 2, 3, 3, 4)))
    turns = rng.choice((1, 2, 2, 3, 3, 4, 5, 6, 8, 10))
    with_self = rng.random() < 0.35
    return f"""寫一段 Discord 語音聊天的語音辨識逐字稿。
主題：{rng.choice(TOPICS)}
說話的人：{"、".join(names)}{"，以及「你」（逐字稿主人，最多說一兩句，不能是最後一句）" if with_self else ""}
句數：{turns} 句

要求：口語、短句、像語音辨識結果（大多沒有標點，偶爾有同音錯字，中英夾雜的遊戲術語照講）；最後一句要是別人說的、而且值得回應（可能是問題、抱怨、玩笑、挑釁或分享）。
輸出 JSON 陣列：[["說話者", "內容"], ...]"""


def make_scenes(args: argparse.Namespace) -> None:
    path = OUT_DIR / "scenes.jsonl"
    have = len(_read(path))
    rng = random.Random(2000 + have)
    probe_lines = {line for _p, scene in PROBE_SCENES for _s, line in scene}
    jobs = [scene_request(rng) for _ in range(max(0, args.count - have))]

    def work(user: str) -> None:
        try:
            scene = _json_block(chat(args.teacher_url, SCENE_SYSTEM, user,
                                     temperature=0.95, max_tokens=700), "[")
            scene = [(str(s).strip(), to_taiwan_traditional(str(t).strip()))
                     for s, t in scene if str(t).strip()]
        except (ValueError, TypeError) as exc:
            print(f"scene skipped: {type(exc).__name__}", flush=True)
            return
        if not scene or scene[-1][0] == "你" or any(t in probe_lines for _s, t in scene):
            return
        _append(path, {"scene": scene})
        print(f"scene {len(scene)} turns", flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(work, jobs))


# ---------------------------------------------------------------- replies

def _is_question(text: str) -> bool:
    return text.rstrip().endswith(("？", "?", "嗎", "呢"))


def check_reply(lines: dict[str, str], max_chars: int) -> str | None:
    """Reason to drop a teacher answer, or None if it is usable training data."""
    if sum(not v for v in lines.values()) > 1:
        return "too many skips"
    for text in lines.values():
        if not text:
            continue
        if len(text) > max_chars:
            return "too long"
        if re.search(r"(我是|身為)(一個)?\s*(AI|人工智慧|機器人|語言模型)", text, re.I):
            return "claims to be AI"
        if "|" in text or "\n" in text:
            return "format"
    if lines["AGREE"] and _is_question(lines["AGREE"]):
        return "agree is question"
    if lines["ASK"] and not _is_question(lines["ASK"]):
        return "ask not question"
    return None


def make_replies(args: argparse.Namespace) -> None:
    personas = [persona_from_dict(p) for p in _read(OUT_DIR / "personas.jsonl")]
    scenes = [tuple(map(tuple, s["scene"])) for s in _read(OUT_DIR / "scenes.jsonl")]
    if not personas or not scenes:
        raise SystemExit("run the personas and scenes steps first")
    preset_names = {p.name for p in PRESET_PERSONAS}
    personas = [p for p in personas if p.name not in preset_names]
    path = OUT_DIR / "replies.jsonl"
    done = {(r["persona_id"], r["scene_index"], r["mood"]) for r in _read(path)}

    rng = random.Random(3000)
    jobs = []
    # ~10% blank persona so the no-persona mode does not regress.
    cast = personas + [blank_persona()] * max(1, len(personas) // 10)
    for persona in cast:
        for scene_index in rng.sample(range(len(scenes)), min(args.per_persona, len(scenes))):
            mood = rng.choice(MOODS) if rng.random() < 0.4 else "平常"
            if (persona.id, scene_index, mood) not in done:
                jobs.append((replace(persona, mood=mood), scene_index))

    config = CopilotConfig()
    builder = EvalReplyModel(Path("unused"), max_reply_chars=config.max_reply_chars,
                             variant=args.variant, sampling={}, grammar=False)
    drops: dict[str, int] = {}

    def work(job: tuple[Any, int]) -> None:
        persona, scene_index = job
        builder_local = EvalReplyModel(Path("unused"), max_reply_chars=config.max_reply_chars,
                                       variant=args.variant, sampling={}, grammar=False)
        builder_local.set_persona(persona)
        context, speaker, text = scene_prompt_inputs(scenes[scene_index])
        system = builder_local._build_system_prompt(persona)
        user = "/no_think\n" + builder_local._build_prompt(
            context=context, trigger_speaker=speaker, trigger_text=text,
            relationships=persona.relationship_notes(context + "\n" + speaker),
        )
        try:
            raw = chat(args.teacher_url, system, user, temperature=0.7, max_tokens=300)
        except OSError as exc:
            print(f"reply error: {exc}", flush=True)
            return
        parsed = builder._parse_suggestions(raw, speaker, text)
        lines = {lane.code: parsed.text_for(lane) for lane in REPLY_LANES}
        reason = check_reply(lines, config.max_reply_chars)
        if reason:
            drops[reason] = drops.get(reason, 0) + 1
            return
        answer = "\n".join(f"{code}|{lines[code] or 'SKIP'}" for code in lines)
        _append(path, {
            "persona_id": persona.id, "scene_index": scene_index, "mood": persona.mood,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
                {"role": "assistant", "content": answer},
            ],
        })

    with ThreadPoolExecutor(args.workers) as pool:
        for n, _ in enumerate(pool.map(work, jobs), 1):
            if n % 50 == 0:
                print(f"{n}/{len(jobs)} replies, dropped {drops}", flush=True)
    print(f"done; dropped {drops}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=("personas", "scenes", "replies"))
    parser.add_argument("--teacher-url", default="http://127.0.0.1:18200")
    parser.add_argument("--workers", type=int, default=4, help="match llama-server --parallel")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--per-persona", type=int, default=14)
    parser.add_argument("--variant", default="prod", help="prompt variant the student will use")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    {"personas": make_personas, "scenes": make_scenes, "replies": make_replies}[args.step](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
