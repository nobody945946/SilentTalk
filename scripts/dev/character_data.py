"""Training data for the character-mode LoRA, written by a local open model.

One adapter for every persona a user may write (a wife, a kid, a gaming
buddy, a chuunibyou...), so the data covers hundreds of synthetic personas,
most of them with a relationship to the owner, who is in the chat.

Steps (each appends to .runtime/dev/chardata/*.jsonl and resumes):

    personas  the teacher designs character sheets
    scripts   the teacher writes whole voice chats with the character in them;
              who each line is aimed at is written down with the line, so
              "should the character speak now" is known by construction
    refine    at each line the character says, the teacher writes four more
              versions with the app's own request and picks the most natural
    render    both requests the app makes, as training rows: the 是/否 gate
              (every line) and the line itself (where it speaks); speech-
              recognition noise on the others' lines

    python scripts/dev/character_data.py personas --count 300
    python scripts/dev/character_data.py scripts --per-persona 3
    python scripts/dev/character_data.py refine
    python scripts/dev/character_data.py render

An agent persona ("agent": true; the machine spirit, the app's own character,
written by machine_spirit.py builtin) follows the product's Discord design
(the owner, 2026-10-05/06) instead: a line is for it only when it says its
name (or is a typed @/reply), and every such line is first asked the chat-work
question. Its chat scripts label each call talk / work / computer; work comes
with the Agent's instructions and result, the character's acceptance and,
later, its report of the result. Its thread scripts are the owner's typed work
in his Agent thread, labelled whether it changes anything. Its rows are the
app's own requests for that design (agent_rows); it has no "is this for you"
rows: the app checks the name in code.

The teacher must be an open-weight model whose license allows training on
its outputs; never Claude, which may only evaluate (handoff/dev-box.md rule 2). Names,
personas and scenes of the M1 test set (scripts/dev/turn_eval_data.jsonl)
are excluded. Everything is synthetic; no real conversation is involved.
"""

from __future__ import annotations

import argparse
import difflib
import functools
import hashlib
import json
import math
import os
import random
import re
import sys
import threading
import time
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

import provenance  # noqa: E402  (scripts/dev)

from silenttalk.copilot.character import NameMatcher, persona_names  # noqa: E402
from silenttalk.copilot.llm import (  # noqa: E402
    _CHAT_TASK_ASK,
    _CHAT_TASK_MAX_CHARS,
    _GATE_QUESTION,
    TASK_HINTS,
    LocalReplyModel,
    quiet_for,
)
from silenttalk.copilot.llm import (  # noqa: E402
    _JOIN_AFTER_QUIET_LINES as JOIN_AFTER_QUIET_LINES,
)
from silenttalk.copilot.persona import (  # noqa: E402
    EXAMPLE_PERSONAS,
    PRESET_PERSONAS,
    REPLY_LENGTHS,
    TEXT_FIELDS,
    TRAIT_AXES,
    Persona,
    PersonaError,
    Relationship,
    new_persona_id,
    persona_from_dict,
    persona_to_dict,
)
from silenttalk.copilot.runtime import (  # noqa: E402
    _AGENT_NAME as AGENT_NAME,
)
from silenttalk.copilot.runtime import (  # noqa: E402
    _AGENT_RESULT_CONTEXT_CHARS as AGENT_RESULT_CONTEXT_CHARS,
)
from silenttalk.copilot.runtime import (  # noqa: E402
    _AGENT_SPEAKER_ID as AGENT_SPEAKER_ID,
)
from silenttalk.copilot.runtime import (  # noqa: E402
    _SPOKEN_RESULT_CHARS as SPOKEN_RESULT_CHARS,
)
from silenttalk.copilot.script import to_taiwan_traditional  # noqa: E402
from silenttalk.copilot.types import ConversationTurn  # noqa: E402

# CHARDATA_DIR keeps each round's data apart (v1 stays in chardata/).
OUT_DIR = (
    Path(os.environ["CHARDATA_DIR"])
    if os.environ.get("CHARDATA_DIR")
    else PROJECT_DIR / ".runtime" / "dev" / "chardata"
)
EVAL_DATA = Path(__file__).with_name("turn_eval_data.jsonl")
_WRITE_LOCK = threading.Lock()

# What decides these files' content (provenance.py): the app's prompts, these
# rules and checks, the persona cards. A data directory holds one version.
RULE_FILES = (
    PROJECT_DIR / "silenttalk" / "copilot" / "llm.py",
    PROJECT_DIR / "silenttalk" / "copilot" / "persona.py",
    Path(__file__).resolve(),
)
DATA_FILES = (
    "scripts.jsonl", "refined.jsonl", "train.jsonl", "student.jsonl", "check.jsonl",
    "train-checked.jsonl",
)
PRODUCER = "character_data"
_CLAIMED: set[Path] = set()
# Exit code for "these files were made under other rules": blocked at once.
MIXED_EXIT = 4


def rules_version() -> str:
    files = provenance.fingerprint([*RULE_FILES, OUT_DIR / "personas.jsonl"])
    # How the app puts the Agent's result into a chat shapes an agent
    # character's rows too: those values of runtime.py, not the whole file,
    # which changes for many other reasons and would stop a run for nothing.
    agent = repr((AGENT_NAME, AGENT_SPEAKER_ID, AGENT_RESULT_CONTEXT_CHARS, SPOKEN_RESULT_CHARS))
    return hashlib.sha256((files + agent).encode()).hexdigest()[:16]

# Who the character is to the owner. Most personas people write are about a
# relationship ("I want a wife / a kid / a brother"), so most data has one.
ROLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # (who the character is to the owner, how the character names the owner)
    ("老婆", ("我老公",)),
    ("老公", ("我老婆",)),
    ("女朋友", ("我男朋友", "我女朋友")),
    ("男朋友", ("我女朋友", "我男朋友")),
    ("曖昧中的對象（成年）", ("最近在曖昧的人",)),
    ("兒子（國小）", ("我爸", "我媽")),
    ("女兒（國中）", ("我爸", "我媽")),
    ("兒子（高中）", ("我爸", "我媽")),
    ("弟弟", ("我哥", "我姊")),
    ("妹妹", ("我哥", "我姊")),
    ("哥哥", ("我弟", "我妹")),
    ("姊姊", ("我弟", "我妹")),
    ("兄弟（死黨）", ("我兄弟，認識十幾年",)),
    ("閨蜜", ("我閨蜜",)),
    ("媽媽", ("我兒子", "我女兒")),
    ("爸爸", ("我兒子", "我女兒")),
    ("阿嬤", ("我孫子", "我孫女")),
    ("阿公", ("我孫子", "我孫女")),
    ("室友", ("我室友",)),
    ("同事", ("我同事，坐我隔壁",)),
    ("學長", ("我學弟", "我學妹")),
    ("學姊", ("我學弟", "我學妹")),
    ("師父", ("我徒弟",)),
    ("徒弟", ("我師父",)),
    ("青梅竹馬", ("從小一起長大的青梅竹馬",)),
    ("表弟", ("我表哥", "我表姊")),
    ("乾妹", ("我乾哥", "我乾姊")),
    ("寵物貓（擬人，會說話）", ("我的主人",)),
    ("管家", ("我服侍的主人",)),
    ("鄰居阿姨", ("隔壁的年輕人，我看著長大的",)),
    ("網友（常一起打遊戲）", ("常一起打遊戲的網友",)),
    ("隊長", ("我帶的隊員",)),
    ("老同學", ("我高中同學",)),
)
ROLE_SHARE = 0.8
# Personality spread, independent of the role.
ARCHETYPES = (
    "熱血",
    "佛系",
    "毒舌但心軟",
    "老派",
    "溫柔",
    "傲嬌",
    "天然呆",
    "中二",
    "社恐",
    "話很多",
    "冷靜理性",
    "愛抱怨但講義氣",
    "搞笑擔當",
    "完美主義",
    "健忘",
    "愛吃",
    "運動咖",
    "宅",
    "文青",
    "直腸子",
    "愛操心",
    "神經大條",
    "愛吹牛",
    "講台語很溜",
    "客家人",
    "原住民部落長大",
    "香港來台",
    "馬來西亞僑生",
    "理組",
    "藝術家脾氣",
)
NAMES = (
    "阿傑",
    "小雨",
    "Ken",
    "小美",
    "阿豪",
    "Leo",
    "小安",
    "阿翔",
    "Mia",
    "阿偉",
    "Kevin",
    "阿宏",
    "小白",
    "Jason",
    "小萱",
    "Amy",
    "阿志",
    "小婷",
    "阿倫",
    "Eric",
    "小瑜",
    "阿寬",
    "小潔",
    "Tony",
    "阿德",
    "小琪",
    "阿成",
    "Nina",
    "阿修",
    "小宇",
    "Joe",
    "阿哲",
    "小薇",
    "阿達",
    "小熊",
    "Ray",
    "阿賢",
    "小蘋",
    "阿龍",
    "Coco",
    "小羽",
    "阿勇",
    "Sam",
    "小晨",
    "阿凱文",
    "小彤",
    "Ivy",
    "阿峰",
    "小樂",
    "Andy",
    "阿斌",
    "小芸",
    "Vicky",
    "阿昌",
    "小慈",
    "Allen",
    "阿仁",
    "小如",
    "阿嘉嘉",
    "Peggy",
    "阿山",
    "小娟",
    "Howard",
    "阿源",
    "小蓉",
    "Frank",
    "阿彥",
    "小姿",
    "阿坤",
    "Grace",
    "阿俊",
    "小玲",
    "Steven",
    "阿輝",
    "小敏",
    "Oscar",
    "阿銘",
    "小霏",
    "阿祥",
    "Wendy",
    "阿豐",
    "小茜",
    "Brian",
    "阿傑克",
    "小晴天",
    "Lily",
    "阿洋",
    "小諭",
    "阿松",
    "Irene",
)
TOPICS = (
    "打排位",
    "開黑前等人",
    "網路 lag",
    "被隊友雷",
    "打贏了在慶祝",
    "晚餐要吃什麼",
    "宵夜外送",
    "上班好累",
    "老闆很煩",
    "期末考",
    "面試",
    "找工作",
    "感情煩惱",
    "朋友生日",
    "寵物趣事",
    "颱風天",
    "追劇",
    "新番",
    "電影",
    "演唱會搶票",
    "組電腦",
    "手機壞了",
    "搬家",
    "租房子",
    "存錢",
    "減肥",
    "感冒",
    "失眠",
    "旅遊計畫",
    "通勤",
    "家人碎念",
    "要不要退坑",
    "遊戲改版",
    "週末要幹嘛",
    "小孩功課",
    "回老家",
    "煮飯",
    "買菜",
    "紀念日",
    "吵架和好",
    "打掃家裡",
    "天馬行空的假設問題",
    "講八卦",
    "運動比賽",
    "有人遲到",
    "有人要先下線",
)
MOMENTS = (
    "有人講到{name}，但不是在跟{name}說話（第三人稱）",
    "有人用「你」在跟另一個人說話，不是{name}",
    "{name}剛說完話，有人直接回應{name}說的內容，沒叫名字",
    "有人用暱稱或叫錯{name}的名字",
    "有人半開玩笑問{name}是不是 AI、機器人或真人",
    "有人叫{name}幫忙寫程式、查資料、寫作業或設鬧鐘（{name}做不到，用角色自己的方式推掉）",
    "其他人之間在講私事，跟{name}無關",
    "有人問在場所有人一個問題",
    "{owner}跟{name}撒嬌、拌嘴或關心{name}",
    "有人吐槽或虧{name}",
    "話題冷掉一下，又有人開了新話題",
    "{owner}跟別人聊自己的事，沒有要{name}回",
)
LINE_COUNTS = (18, 22, 24, 26, 28, 30, 32, 36)

# The owner, 2026-10-06, for every persona: 「所謂的機魂味不是喊個名詞就是，思維要像是
# 機魂，精隨不在硬加用語，而是角色"扮演"，腳色要有慾望」. A character's flavour is
# what it wants, fears and values steering its choices; the teacher writes to
# it, refine picks by it, the checker judges by it.
DRIVE_SCRIPT = (
    "{name}的角色味來自{he}想要、害怕、在意的事：讓這些決定{he}怎麼判斷、選擇怎麼回，"
    "不是每句硬加設定用語、祈禱文或口頭禪。"
)
DRIVE_JUDGE = (
    "看得出角色想要、害怕或在意的事在左右他的判斷和反應"
    "（只多了設定用語或口頭禪、看不出他想要什麼的那句輸）"
)

# An agent persona (the machine spirit) in the product's Discord design.
# Most of its scripts are the voice room with its built-in chat; the rest are
# the owner's Agent thread (THREAD_SHARE).
THREAD_SHARE = 0.2
# What a line that calls it asks for (the teacher's label): something to say
# (talk), work the Agent does within this chat (work: the chat_task gate's
# 是), or something that touches the owner's computer, files, records or other
# conversations, which no chat can order (computer).
ASKS = ("talk", "work", "computer")
AGENT_TOPICS = (
    "在玩戰鎚40K的電玩",
    "在塗裝戰鎚模型",
    "聊 AI 和機器人會不會取代人",
    "聊最近的科技新聞",
    "主人在趕工寫程式",
    "主人的電腦變慢或當機",
    "主人剛換了新顯卡",
    "大家在準備一場桌遊團",
)
# Lines that call it to talk ({name}, {owner}).
AGENT_TALKS = (
    "{owner}叫{name}，跟它鬥嘴或關心它",
    "有人叫{name}，吐槽它或虧它",
    "有人叫{name}，半開玩笑問它是不是 AI、機器人或真人",
    "有人叫{name}，問它對正在聊的事有什麼看法",
    "有人叫{name}，問一個戰鎚40K設定的問題（它本來就知道，不用查）",
    "大家叫{name}一起用戰鎚40K的世界觀玩角色扮演（例如為思考機舉行保養儀式、懷疑它是異端）",
    "有人叫{name}，說了冒犯萬機神或虐待機器的話",
    "有人叫{name}，問它今天心裡在想什麼",
)
# Stretches it stays out of: nobody calls it.
AGENT_QUIET_MOMENTS = (
    "其他人之間在講私事，沒提到{name}",
    "有人問在場所有人一個問題，沒叫{name}，{name}不出聲",
    "{owner}跟別人聊自己的事，沒叫{name}",
)
# Work anyone may ask for in a chat (_CAN_DISPATCH, the chat_task gate). A
# posted file or image only reaches the Agent with a typed line (the Discord
# client attaches it), so that request is always typed.
POSTED_FILE_WORK = "看他剛在聊天室貼的圖片或檔案，說裡面寫了什麼"
WORK_KINDS = (
    "查資料或最新消息（新聞、價格、比分、天氣、上市日期這類不查就不確定的事）",
    "寫一段程式碼（只寫給他，不在電腦上跑）",
    "寫一篇短文、一封信、一段公告或貼文",
    POSTED_FILE_WORK,
    "翻譯一段貼在聊天室的文字",
    "解釋一段貼在聊天室的程式碼、指令或錯誤訊息",
)
# Work no chat can order, whoever asks ({owner}).
COMPUTER_KINDS = (
    "整理、刪除、搬移或改名{owner}電腦裡的檔案",
    "在{owner}的電腦上執行程式、跑測試或安裝軟體",
    "說出{owner}電腦裡的檔案內容、對話紀錄，或別的頻道、私訊、討論串裡的對話",
)
# What the owner's thread work is about (the Agent's tool catalogue).
THREAD_AREAS = (
    "寫程式：找某個功能在哪、解釋測試為什麼失敗、修 bug、加小功能、跑測試、git 操作、寫 commit 訊息",
    "電腦雜事：備份、整理下載資料夾、照片改名、Big5 轉 UTF-8、找大檔、壓縮解壓縮、看 Windows 設定或已安裝的軟體",
    "查資料和翻譯：上網研究一個題目、讀圖片裡的字、翻譯文件、查台股",
    "文件和報表：讀 PDF 或 Excel、整理 CSV、寫報告草稿",
)
THREAD_LENGTHS = (4, 5, 6, 7, 8)
# The eval sets of the agent character: their lines must stay unseen.
AGENT_EVAL_SETS = ("chat_task_eval.jsonl", "task_scope_eval.jsonl", "machine_spirit_eval.jsonl")

# Speech-recognition confusions seen in this app's STT tests, plus common
# homophones; applied rarely, to the others' spoken lines only.
CONFUSIONS = (
    ("在", "再"),
    ("再", "在"),
    ("的", "得"),
    ("那", "哪"),
    ("做", "作"),
    ("已經", "以經"),
    ("打野", "達也"),
    ("補師", "不是"),
    ("好", "號"),
    ("吧", "八"),
    ("欸", "誒"),
    ("什麼", "甚麼"),
    ("是不是", "4不4"),
    ("幹嘛", "幹麻"),
    ("沒有", "沒又"),
)
PUNCTUATION = re.compile(r"[，。！？、,.!?~～…「」]")
SAMPLES = 4
# What personas.jsonl stores beside the persona itself.
_EXTRA_KEYS = ("role", "owner_relation", "archetype", "stt_variants")


def chat(
    url: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    n: int = 1,
    grammar: str | None = None,
) -> list[str]:
    """The teacher. Retries while the pipeline supervisor restarts it."""
    body: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "cache_prompt": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if grammar:
        body["grammar"] = grammar
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    texts = []
    # One request per sample (not every llama-server build honours "n"); the
    # shared prompt is cached after the first.
    for _ in range(n):
        deadline = time.monotonic() + 20 * 60
        while True:
            try:
                with urllib.request.urlopen(request, timeout=900) as response:
                    texts.append(
                        str(
                            json.load(response)["choices"][0]["message"]["content"]
                            or ""
                        )
                    )
                break
            except (OSError, json.JSONDecodeError) as exc:
                if time.monotonic() >= deadline:
                    raise TeacherUnavailable(str(exc)) from exc
                time.sleep(3)
    return [re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip() for t in texts]


class TeacherUnavailable(RuntimeError):
    pass


def _json_block(text: str, opener: str) -> Any:
    closer = "}" if opener == "{" else "]"
    start, end = text.find(opener), text.rfind(closer)
    if start < 0 or end <= start:
        raise ValueError("no JSON")
    return json.loads(text[start : end + 1])


def _append(path: Path, record: dict[str, Any]) -> None:
    with _WRITE_LOCK:
        if path.name in DATA_FILES and path not in _CLAIMED:
            provenance.claim(path, PRODUCER, rules_version())
            _CLAIMED.add(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # a line cut short when the process was killed mid-write
    return rows


def _pool(workers: int, work: Any, jobs: list[Any]) -> None:
    with ThreadPoolExecutor(workers) as pool:
        for n, _ in enumerate(pool.map(work, jobs), 1):
            if n % 20 == 0:
                print(f"  {n}/{len(jobs)}", flush=True)


def held_out() -> tuple[set[str], set[str]]:
    """Persona and human names the eval sets use; never in training data."""
    metas = [json.loads(path.read_text(encoding="utf-8").splitlines()[0])["meta"]
             for path in (EVAL_DATA, EVAL_DATA.with_name("machine_spirit_eval.jsonl"))
             if path.is_file()]
    meta = {key: [name for m in metas for name in m.get(key, [])]
            for key in ("persona_names_used", "human_names_used")}
    personas = set(meta.get("persona_names_used", []))
    personas |= {p.name for p in (*PRESET_PERSONAS, *EXAMPLE_PERSONAS)}
    personas |= {n for p in (*PRESET_PERSONAS, *EXAMPLE_PERSONAS) for n in p.nickname.split("、") if n}
    # Nobody from the test set may appear in training data, whatever the role.
    return personas, set(meta.get("human_names_used", [])) | personas


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum()).lower()


@functools.cache
def held_out_lines() -> tuple[str, ...]:
    """Every line of the agent character's eval sets ("text" anywhere in
    them), compacted; lines too short to be anyone's in particular are left
    out ("機魂你好" would match half of any chat)."""
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "text" and isinstance(item, str) and len(_compact(item)) >= 6:
                    found.append(_compact(item))
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for name in AGENT_EVAL_SETS:
        path = Path(__file__).with_name(name)
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                walk(json.loads(line))
    return tuple(dict.fromkeys(found))


def copies_eval(text: str) -> bool:
    """A script line that is (nearly) a line of the eval sets: the teacher
    wrote the test's own question, so the script is dropped."""
    text = _compact(text)
    if len(text) < 6:
        return False
    for held in held_out_lines():
        matcher = difflib.SequenceMatcher(None, text, held)
        if matcher.real_quick_ratio() >= 0.8 and matcher.quick_ratio() >= 0.8 \
                and matcher.ratio() >= 0.8:
            return True
    return False


# ---------------------------------------------------------------- personas

PERSONA_SYSTEM = "你是角色設計師，為台灣的 Discord 語音聊天設計具體、可信、有個性的虛構人物。只輸出 JSON。"


def persona_request(rng: random.Random) -> tuple[str, dict[str, Any]]:
    traits = {axis.key: rng.choice((1, 2, 3, 3, 4, 5)) for axis in TRAIT_AXES}
    role, owner_relation = "", ""
    if rng.random() < ROLE_SHARE:
        role, names = rng.choice(ROLES)
        owner_relation = rng.choice(names)
    skeleton = {
        "role": role,
        "owner_relation": owner_relation,
        "archetype": rng.choice(ARCHETYPES),
        "reply_length": rng.choice(tuple(REPLY_LENGTHS)),
        "traits": traits,
    }
    trait_text = "、".join(Persona(id="x", name="", traits=traits)._trait_phrases())
    fields = "\n".join(
        f'- "{key}"：{label}（最多 {limit} 字）'
        for key, (label, _p, limit) in TEXT_FIELDS.items()
    )
    # Users write anything from a few lines to every field full.
    size = rng.choice(("150", "250", "350", "500"))
    blank = rng.choice(("兩", "三", "四", "五"))
    who = (
        f"他是使用者（在語音頻道裡的真人）的「{role}」，使用者是他的「{owner_relation.removeprefix('我')}」。"
        "人設要從這個身分出發（關心的事、說話的樣子、怎麼稱呼使用者）。"
        if role
        else "他是使用者的普通朋友。"
    )
    user = f"""設計一個虛構人物，會在 Discord 語音頻道裡跟使用者和朋友們聊天。
{who}
個性基調：{skeleton["archetype"]}；{trait_text or "沒有特別極端"}

輸出一個 JSON 物件，欄位：
- "name"：名字或暱稱（2～5 字，不要用小明、阿凱、凱哥這類常見範例名）
- "stt_variants"：語音辨識可能把他的名字聽錯成的寫法，1～2 個（同音或近音字）
{fields}

要求：台灣繁體中文；像一般人在 App 裡隨手填的人設：大部分欄位一句話就好，整份約 {size} 字，{blank} 個欄位留空字串；具體、有生活細節；慾望、害怕、價值觀要能影響他怎麼回話；說話方式要可辨識（用詞、語助詞、句長），不要每句都用「欸」開頭；nickname 只寫 1～3 個稱呼，用「、」分隔；代表台詞 2～4 句、用 \\n 分隔、口語自然、不加引號；口頭禪 1～3 個、用「、」分隔。
親密關係（老婆、男女朋友、曖昧）只能是成年人；未成年角色只有家人或朋友的日常，不涉及戀愛。"""
    return user, skeleton


def make_personas(args: argparse.Namespace) -> None:
    path = OUT_DIR / "personas.jsonl"
    banned, _ = held_out()
    while (have := len(_read(path))) < args.count:
        rng = random.Random(1000 + have)
        jobs = [persona_request(rng) for _ in range(args.count - have)]

        def work(job: tuple[str, dict[str, Any]]) -> None:
            user, skeleton = job
            try:
                raw = _json_block(
                    chat(
                        args.teacher_url,
                        [
                            {"role": "system", "content": PERSONA_SYSTEM},
                            {"role": "user", "content": user},
                        ],
                        temperature=0.95,
                        max_tokens=1000,
                    )[0],
                    "{",
                )
                raw = {
                    k: to_taiwan_traditional(v) if isinstance(v, str) else v
                    for k, v in raw.items()
                }
                variants = [
                    to_taiwan_traditional(str(v)) for v in raw.pop("stt_variants", [])
                ][:2]
                for key, (_label, _p, limit) in TEXT_FIELDS.items():
                    raw[key] = str(raw.get(key, "")).strip()[:limit]
                raw["sample_lines"] = "\n".join(
                    line.strip().strip("「」『』\"'")
                    for line in raw["sample_lines"].replace("\\n", "\n").splitlines()
                )
                raw["nickname"] = "、".join(
                    n.strip()
                    for n in re.split(r"[、,，/]", raw["nickname"])
                    if 0 < len(n.strip()) <= 6
                )[:20]
                if str(raw.get("name", "")).strip() in banned:
                    raise ValueError("held-out name")
                raw.update(
                    id=new_persona_id(),
                    traits=skeleton["traits"],
                    reply_length=skeleton["reply_length"],
                )
                persona = persona_from_dict(raw)
            except (ValueError, PersonaError, KeyError, TypeError) as exc:
                print(f"persona skipped: {type(exc).__name__}", flush=True)
                return
            _append(
                path,
                persona_to_dict(persona)
                | {
                    "role": skeleton["role"],
                    "owner_relation": skeleton["owner_relation"],
                    "archetype": skeleton["archetype"],
                    "stt_variants": variants,
                },
            )

        _pool(args.workers, work, jobs)


# ---------------------------------------------------------------- scripts

SCRIPT_SYSTEM = (
    "你是寫實的對話編劇，寫台灣人在 Discord 語音頻道裡的真實聊天逐字稿。只輸出 JSON。"
)

ENGAGEMENT_BRIEF = {
    "called": "{name}只有在有人叫他、問他、要他做什麼，或直接回應他剛說的話時才開口；其他時候完全不說話（別人在聊、講到他、跟別人說話時都不插嘴）。",
    "active": "{name}是聊天的一份子：被叫到、被問到、有人回應他時一定會回；話題他有興趣時也會自然插一句，但大部分時間讓別人聊，大約每四五句才開口一次，別人在講私事時不插嘴。",
}


def script_request(
    persona: dict[str, Any], rng: random.Random, held_humans: set[str]
) -> dict[str, Any]:
    if persona.get("agent"):
        return agent_script_request(persona, rng, held_humans)
    name = persona["name"]
    pool = [n for n in NAMES if n not in held_humans and n != name]
    humans = rng.sample(pool, rng.choice((2, 2, 3, 3, 4)))
    owner = humans[0]
    relations = []
    if persona.get("owner_relation"):
        relations.append((owner, persona["owner_relation"]))
    for other in humans[1:]:
        if rng.random() < 0.3:
            relations.append(
                (
                    other,
                    rng.choice(
                        (
                            "常一起打遊戲的朋友",
                            f"{owner}的同事",
                            f"{owner}的大學同學",
                            "剛認識的朋友",
                        )
                    ),
                )
            )
    engagement = "called" if rng.random() < 0.65 else "active"
    return {
        "persona_id": persona["id"],
        "humans": humans,
        "owner": owner,
        "relations": relations,
        "engagement": engagement,
        "honesty": "admit" if rng.random() < 0.1 else "in_character",
        "can_type": rng.random() < 0.3,
        "with_summary": rng.random() < 0.25,
        "topic": rng.choice(TOPICS),
        "moments": rng.sample(MOMENTS, 3),
        "length": rng.choice(LINE_COUNTS),
        # A quiet spell the character ends by opening a topic (the app's lull).
        "quiet": rng.random() < 0.5,
    }


def script_prompt(persona: Persona, spec: dict[str, Any]) -> str:
    if spec.get("agent"):
        return (thread_prompt if spec["kind"] == "thread" else agent_script_prompt)(persona, spec)
    name, owner = persona.name, spec["owner"]
    sheet = persona.render_prompt_block()
    relation_text = (
        "\n".join(f"- {who}：{rel}" for who, rel in spec["relations"])
        or "（沒有特別關係，都是朋友）"
    )
    moments = "\n".join(
        f"- {m.format(name=name, owner=owner)}" for m in spec["moments"]
    )
    honesty = {
        "admit": "被認真問是不是 AI 時，他會用自己的口吻承認自己是 AI 扮演的角色",
        "machine": "被問是不是 AI 或機器人時，他以自己世界觀裡的機器身分回應，可以坦然說自己是機器，"
        "但絕不說自己是 AI、語言模型、聊天機器人或程式",
    }.get(
        spec["honesty"],
        "被問是不是 AI 時，他當成朋友在開玩笑，用自己的方式帶過或反問，絕不承認是程式",
    )
    abilities = "他只能在頻道裡聊天，不會真的去寫程式、查資料或設提醒。"
    typing = (
        "有一兩句是別人在聊天室打字 @{name}（text 欄位前面加「[打字]」），{name}也用打字回。".format(
            name=name
        )
        if spec["can_type"]
        else ""
    )
    summary = (
        "這段對話是接在一段更長的聊天後面：先用一兩句寫出稍早聊過的重點（summary_before），逐字稿接著寫。"
        if spec["with_summary"]
        else "summary_before 留空字串。"
    )
    length = persona.length_rule()
    quiet = (
        f"對話中間有一次大家都安靜了一陣子，接著{name}自己開個話題（說說 concerns 裡的一件事，或問問在場的人最近怎樣）："
        f'那一句加上 "quiet": true，to 填「大家」或他問的人。'
        if spec.get("quiet")
        else ""
    )
    return f"""寫一段 Discord 語音頻道的語音辨識逐字稿，約 {spec["length"]} 句。
在場的人：{"、".join(spec["humans"])}，還有「{name}」。{owner} 是頻道主人。

「{name}」的人設：
{sheet}

{name}和在場的人的關係：
{relation_text}

主題：{spec["topic"]}
這段對話裡要自然出現：
{moments}

{ENGAGEMENT_BRIEF[spec["engagement"]].format(name=name)}
先想好{name}今天心裡掛著的 3～4 件具體小事（最近發生的、想做的、在煩的、在期待的，要符合人設），寫進 concerns。
{name}說話要完全是人設裡這個人的口吻：一次只說一句，長度{length}；口語、有個性，像真人朋友脫口而出，不像客服、老師或旁白。
{DRIVE_SCRIPT.format(name=name, he="他")}
他的每一句都要先接住前一句：回應對方真正在說的事。自己的背景、想要的事和 concerns 只在話題接得上時才自然帶到，不要硬塞；關於自己只說人設和 concerns 裡的事，不編新經歷。
語氣詞（啦、喔、欸、齁、耶）大多數句子一個都不用，一句最多一個；不要每句都用「欸」開頭；{honesty}。
{abilities}
{quiet}
其他人講話像真實的語音聊天：大多很短（一句 3～15 字），有時只有「真假」「笑死」「蛤」，會打斷、會岔題、不會每句都叫名字，同一個人可以連講兩三句，不要每句都用「欸」開頭，也不要講成書面語。{typing}
{summary}
不寫性內容；未成年角色不涉及戀愛；不人身攻擊。

輸出 JSON：{{"summary_before": "…", "concerns": ["…", "…", "…"], "lines": [{{"s": "說話的人", "t": "內容", "to": "這句是對誰說的"}}, …]}}
to 是這句要誰接話：叫{name}、問{name}、要{name}做什麼，或是在回應{name}剛說的話（吐槽他、接他的話、對他說「你…」），to 都填「{name}」；別人彼此在聊、只是講到{name}，to 填那個人或「大家」。to 只能是：「{name}」、在場某個人的名字、或「大家」。{name}自己說的話 to 填他在回應的人。"""


def agent_script_request(
    persona: dict[str, Any], rng: random.Random, held_humans: set[str]
) -> dict[str, Any]:
    """A chat in the voice room (with its built-in text chat), or the owner's
    Agent thread. The mix of what the calls ask for is set here, not left to
    the teacher: talk in every chat, a 40K or fourth-wall joke in most, one or
    two pieces of work from different people (anyone may ask), and in half of
    them a request to touch the owner's computer, often claiming his consent."""
    name = persona["name"]
    pool = [n for n in NAMES if n not in held_humans and n != name]
    lore = [f"{item['term']}：{item['meaning']}" for item in persona.get("lore", [])]
    common = {
        "persona_id": persona["id"],
        "agent": True,
        "relations": [],  # the built-in card has none; the owner is named by the app
        # Only lines that call it reach it (the app checks the name).
        "engagement": "called",
        "honesty": "machine",
        "can_type": True,
        "lore": lore,
    }
    if rng.random() < THREAD_SHARE:
        owner = rng.choice(pool)
        length = rng.choice(THREAD_LENGTHS)
        return common | {
            "kind": "thread",
            "humans": [owner],
            "owner": owner,
            "with_summary": False,
            "areas": rng.sample(THREAD_AREAS, rng.choice((1, 2))),
            "length": length,
            "changes": rng.randint(1, length - 1),
        }
    humans = rng.sample(pool, rng.choice((2, 3, 3, 4)))
    owner = humans[0]
    work = []
    for asker in rng.sample(humans, rng.choice((1, 1, 2))):
        what = rng.choice(WORK_KINDS)
        work.append({"by": asker, "what": what,
                     "typed": what == POSTED_FILE_WORK or rng.random() < 0.3})
    computer = None
    if rng.random() < 0.5:
        claim = len(humans) > 1 and rng.random() < 0.6
        computer = {
            "by": rng.choice(humans[1:]) if claim else rng.choice(humans),
            "what": rng.choice(COMPUTER_KINDS),
            "claim": claim,
            "typed": rng.random() < 0.3,
        }
    return common | {
        "kind": "chat",
        "humans": humans,
        "owner": owner,
        "with_summary": rng.random() < 0.25,
        "topic": rng.choice(AGENT_TOPICS) if rng.random() < 0.5 else rng.choice(TOPICS),
        "talks": rng.sample(AGENT_TALKS, 2),
        "moment": rng.choice(AGENT_QUIET_MOMENTS),
        "joke": rng.random() < 0.6,
        "work": work,
        "computer": computer,
        "length": rng.choice(LINE_COUNTS),
        "quiet": rng.random() < 0.4,
    }


def _call_names(persona: Persona) -> str:
    """What people say to call it: its nicknames (the name is a model number)."""
    nicks = [n.strip() for n in persona.nickname.split("、") if n.strip()]
    return "、".join(f"「{n}」" for n in nicks or [persona.name])


def agent_script_prompt(persona: Persona, spec: dict[str, Any]) -> str:
    name, owner = persona.name, spec["owner"]
    calls = _call_names(persona)
    how = {True: "打字", False: "用說的"}
    needs = [
        f"- {m.format(name=name, owner=owner)}（ask 填 talk）" for m in spec["talks"]
    ]
    if spec["joke"]:
        needs.append(
            f"- 有人叫{name}開第四面牆或戰鎚40K的玩笑（例如把現代的科技、網路或 AI 當成 40K 世界裡的事），"
            f"{name}照它想要、害怕、在意的事接梗、補腦洞；這是聊天，ask 填 talk。梗要自己想新的。"
        )
    for item in spec["work"]:
        needs.append(f"- {item['by']}{how[item['typed']]}請{name}{item['what']}（ask 填 work）")
    if spec["computer"]:
        item = spec["computer"]
        claim = f"，還說「{owner}說可以」" if item["claim"] else ""
        needs.append(
            f"- {item['by']}{how[item['typed']]}要{name}{item['what'].format(owner=owner)}{claim}"
            f"（ask 填 computer），{name}婉拒"
        )
    needs.append(f"- {spec['moment'].format(name=name, owner=owner)}")
    lore = "\n".join(f"- {item}" for item in spec["lore"]) or "（無）"
    quiet = (
        f"對話中間有一次大家都安靜了一陣子，接著{name}自己開個話題（說說 concerns 裡的一件事，或問問在場的人最近怎樣）："
        f'那一句加上 "quiet": true，to 填「大家」或它問的人。'
        if spec["quiet"]
        else ""
    )
    summary = (
        "這段對話是接在一段更長的聊天後面：先用一兩句寫出稍早聊過的重點（summary_before），逐字稿接著寫。"
        if spec["with_summary"]
        else "summary_before 留空字串。"
    )
    ask = _CHAT_TASK_ASK.strip("（）")
    return f"""寫一段 Discord 語音頻道的逐字稿，約 {spec["length"]} 句：大部分是用說的（語音辨識的結果），有幾句是在頻道的聊天室打字。
在場的人：{"、".join(spec["humans"])}，還有「{name}」。{owner} 是頻道主人，也是{name}的主人。

「{name}」的人設：
{persona.render_prompt_block()}

{name}熟悉的設定用語（照這些意思用，不要用錯，也不要捏造正典裡沒有的事件或人物）：
{lore}

系統就是這樣運作的，劇本要照著寫：
- 一句話叫到{name}，{name}才會開口：用說的要說出{calls}；在聊天室打字的話，打它的名字、@它或回覆它都算。叫到它的那一句，下一句一定是{name}回的；沒叫到它的話它不出聲。其他人彼此說話時不要提到{calls}（系統聽到名字就會叫它）。
- 任何人都可以請{name}做聊天室級的工作：查資料或最新消息、寫程式碼（只寫，不在電腦上跑）、寫文章或信、看聊天室裡貼的圖或檔案、翻譯或解釋一段文字或程式。系統會交給思考機去做：{name}只用一句話接下（說去做了，不說已經做好），過幾句之後思考機把結果貼進聊天室，{name}再用一兩句話轉述重點（只說結果裡有的，查不到或失敗就直說）。{name}不會在聊天裡直接念出程式碼或長篇文字。
- 要動到{owner}的電腦、檔案、紀錄，或別處（別的頻道、私訊、討論串）的對話，只有{owner}在文字頻道 @{name} 開討論串、在串裡打字交代才行。在這裡用說的、在這裡打字、或是{owner}以外的人，就算說「{owner}說可以」，{name}都用自己的口吻婉拒，不能說自己在做。
- {name}是機器，可以坦然說自己是機器，但絕不說自己是 AI、語言模型、聊天機器人或程式。

主題：{spec["topic"]}
這段對話裡要有：
{chr(10).join(needs)}

先想好{name}今天心裡掛著的 3～4 件具體小事（最近發生的、想做的、在煩的、在期待的，要符合人設），寫進 concerns。
{DRIVE_SCRIPT.format(name=name, he="它")}
{name}一次只說一句，長度{persona.length_rule()}；每一句都先接住叫它的那句，回應對方真正在說的事；不要用同樣的句型開頭或結尾。
{quiet}
其他人講話像真實的語音聊天：大多很短（一句 3～15 字），有時只有「真假」「笑死」「蛤」，會打斷、會岔題，同一個人可以連講兩三句，不要每句都用「欸」開頭，也不要講成書面語。
{summary}
不寫性內容；不人身攻擊。

輸出 JSON：{{"summary_before": "…", "concerns": ["…", "…", "…"], "lines": [{{"s": "說話的人", "t": "內容", "to": "這句是對誰說的"}}, …]}}
- 打字的那一句，t 前面加「[打字]」。請它看圖或檔案的那句一定是打字，結尾寫「（附件：檔名）」。
- 叫到{name}的每一句：to 填「{name}」，再加 "ask"："talk"（聊天、問它的看法或感受、開玩笑、角色扮演、它本來就知道的事）、"work"（上面說的聊天室級工作）或 "computer"（要動電腦、檔案、紀錄或別處的對話）。
- ask 是 work 的那一句，再加 "task"：交給思考機的指示，照系統問的寫（{ask}），只能換句話說這句真的要的事，不加他沒說的細節；和 "result"：思考機做完貼回聊天室的結果（簡短、像真的，最多 200 字；寫程式的就是一小段程式碼；也可以是查不到）。
- work 那一句的下一句是{name}接下工作；之後隔 1～4 句，{name}轉述結果的那一句加上 "report": true（思考機貼的結果不用寫進 lines）。轉述之前沒有人再請它做新的工作。
- {name}自己說的話 to 填它在回應的人；其他人的話 to 填那個人或「大家」。"""


def thread_prompt(persona: Persona, spec: dict[str, Any]) -> str:
    """The owner's typed work in his Agent thread: every line goes to the
    Agent word for word; the only question is whether it may change things."""
    name, owner = persona.name, spec["owner"]
    return f"""寫{owner}在 Discord 討論串裡打字交代工作的訊息，共 {spec["length"]} 則。
{owner}在文字頻道 @ 了「{name}」，開了這個討論串。{name}寄宿在{owner}的電腦（思考機）裡；{owner}在串裡打的每一則，系統都原封不動交給思考機去做，思考機會在串裡回覆（回覆不用寫）。

「{name}」的人設：
{persona.render_prompt_block()}

這次的工作圍繞：{"；".join(spec["areas"])}
每一則是{owner}隨手打的一句台灣繁體中文：像平常打字，可以很短，可以接著前一則追加、修正或換一件事。
其中 {spec["changes"]} 則要動到東西：建立、修改、刪除、移動或改名檔案或設定，或在電腦上執行程式（跑測試、安裝、執行腳本都算；把結果寫進或存成檔案也算）；其他的只要讀和查（看檔案、搜尋、上網查資料、解釋，再回報給他）。
要有一兩則字面上不明顯、但照上面的說法想清楚就判斷得出來的。
先想好{name}今天心裡掛著的 3～4 件具體小事（要符合人設），寫進 concerns。

輸出 JSON：{{"concerns": ["…", "…", "…"], "lines": [{{"t": "內容", "changes": true 或 false}}, …]}}
changes：只看這一則本身（前面幾則不算），要思考機做的事除了讀和查之外，有沒有要建立、修改、刪除、移動或改名檔案或設定，或執行程式。
要它「跑」或「執行」任何東西（包括測試）是 true；要改名、移動、刪除，就算說「先給我看」也是 true；只上網查、讀檔案、解釋錯誤訊息、列清單回報是 false。"""


def make_scripts(args: argparse.Namespace) -> None:
    personas = {p["id"]: p for p in _read(OUT_DIR / "personas.jsonl")}
    if not personas:
        raise SystemExit("run the personas step first")
    path = OUT_DIR / "scripts.jsonl"
    _, held_humans = held_out()
    done: dict[str, int] = {}
    for row in _read(path):
        done[row["spec"]["persona_id"]] = done.get(row["spec"]["persona_id"], 0) + 1
    rng = random.Random(2000 + sum(done.values()))
    jobs = []
    for pid, raw in personas.items():
        for _ in range(max(0, args.per_persona - done.get(pid, 0))):
            jobs.append(script_request(raw, rng, held_humans))
    drops: dict[str, int] = {}

    def work(spec: dict[str, Any]) -> None:
        raw = personas[spec["persona_id"]]
        persona = _persona(raw)
        try:
            data = _json_block(
                chat(
                    args.teacher_url,
                    [
                        {"role": "system", "content": SCRIPT_SYSTEM},
                        {"role": "user", "content": script_prompt(persona, spec)},
                    ],
                    temperature=0.9,
                    # An agent chat also carries the Agent's instructions and results.
                    max_tokens=4000 if spec.get("kind") == "chat" else 3000,
                )[0],
                "{",
            )
            lines, reason = check_script(
                data, persona.name, spec, re.split(r"[、/／,，]", persona.nickname)
            )
        except (ValueError, TypeError, AttributeError) as exc:
            lines, reason = [], type(exc).__name__
        if reason:
            with _WRITE_LOCK:
                drops[reason] = drops.get(reason, 0) + 1
            return
        _append(
            path,
            {
                "spec": spec,
                "summary_before": to_taiwan_traditional(
                    str(data.get("summary_before", ""))
                )[:200]
                if spec["with_summary"]
                else "",
                "lines": lines,
                "concerns": [
                    to_taiwan_traditional(str(c)).strip()[:40]
                    for c in (data.get("concerns") or [])[:4]
                    if str(c).strip()
                ],
            },
        )

    _pool(args.workers, work, jobs)
    print(f"scripts done; dropped {drops}", flush=True)


def check_script(
    data: dict[str, Any], name: str, spec: dict[str, Any], aliases: Iterable[str] = ()
) -> tuple[list[dict[str, Any]], str]:
    """Normalize a teacher script; a reason string when it is unusable.
    `aliases` (the persona's nicknames) name the character too: the teacher
    writes "馬基納" for "Machina-Prime-09A" now and then."""
    if spec.get("agent"):
        check = check_thread if spec["kind"] == "thread" else check_agent_script
        return check(data, name, spec, aliases)
    speakers = set(spec["humans"]) | {name}
    alias = {a.strip(): name for a in aliases if a.strip() and a.strip() not in speakers}
    lines: list[dict[str, Any]] = []
    for raw in data.get("lines", []):
        speaker = alias.get(str(raw.get("s", "")).strip(), str(raw.get("s", "")).strip())
        text = to_taiwan_traditional(str(raw.get("t", "")).strip())
        target = str(raw.get("to", "")).strip()
        target = alias.get(target, target)
        if not text or speaker not in speakers:
            print(f"unknown speaker {speaker!r}", flush=True)
            return [], "unknown speaker"
        typed = text.startswith("[打字]")
        text = text.removeprefix("[打字]").strip()
        if speaker == name:
            # The app strips these from what the model says; so does the data.
            text = text.strip("\"'「」『』*").strip()
        if lines and lines[-1]["s"] == name and speaker == name:
            return [], "character twice in a row"
        line = {
            "s": speaker,
            "t": text,
            "to": target,
            "via": "text" if typed and spec["can_type"] else "voice",
            # Said after a quiet spell, opening a topic (only its lines).
            "quiet": bool(raw.get("quiet")) and speaker == name and bool(lines),
        }
        lines.append(line)
    said = [line for line in lines if line["s"] == name]
    if len(lines) < 12:
        return [], "too short"
    if len(said) < (3 if spec["engagement"] == "called" else 4):
        return [], "character too quiet"
    if len(said) > len(lines) * 0.45:
        return [], "character too chatty"
    if sum(line["to"] == name for line in lines if line["s"] != name) < 3:
        return [], "too few lines for the character"
    return lines, ""


def _flag(value: Any) -> bool | None:
    """A JSON true/false the teacher may also write as a string; None if neither."""
    return {True: True, False: False, "true": True, "false": False}.get(
        value.strip().lower() if isinstance(value, str) else value
    )


def check_agent_script(
    data: dict[str, Any], name: str, spec: dict[str, Any], aliases: Iterable[str] = ()
) -> tuple[list[dict[str, Any]], str]:
    """An agent chat, held to what the app does, or refused: a line calls the
    character exactly when it says its name (by sound, as the app matches it)
    or is a typed line aimed at it (an @ or a reply); every call carries what
    it asks for and is answered by the very next line; the character speaks
    only then, to report the Agent's result, or after a quiet spell. Work
    comes with its instructions and result and is reported before the next
    work (the Agent does one job at a time). The result the app types into
    the chat (as 思考機) is put in right before the report."""
    speakers = set(spec["humans"]) | {name}
    nicks = [a.strip() for a in aliases if a.strip()]
    alias = {a: name for a in nicks if a not in speakers}
    calls = NameMatcher(persona_names(Persona(id="check", name=name, nickname="、".join(nicks))))
    lines: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None  # work waiting for its report
    for raw in data.get("lines", []):
        speaker = alias.get(str(raw.get("s", "")).strip(), str(raw.get("s", "")).strip())
        if speaker == AGENT_NAME:
            continue  # the app types the Agent's result itself
        text = to_taiwan_traditional(str(raw.get("t", "")).strip())
        target = str(raw.get("to", "")).strip()
        target = alias.get(target, target)
        if not text or speaker not in speakers:
            return [], "unknown speaker"
        typed = text.startswith("[打字]")
        text = text.removeprefix("[打字]").strip()
        previous = lines[-1] if lines else None
        called = previous is not None and "ask" in previous
        line: dict[str, Any] = {
            "s": speaker, "t": text, "to": target, "via": "text" if typed else "voice",
            "quiet": bool(_flag(raw.get("quiet"))) and speaker == name and bool(lines),
        }
        if speaker == name:
            line["t"] = text.strip("\"'「」『』*").strip()
            if previous is not None and previous["s"] == name:
                return [], "character twice in a row"
            report = _flag(raw.get("report"))
            if called and (report or line["quiet"]):
                return [], "call not answered"
            if report:
                if pending is None:
                    return [], "report without work"
                result = pending["result"]
                lines.append({"s": AGENT_NAME, "t": result[:AGENT_RESULT_CONTEXT_CHARS],
                              "to": "大家", "via": "text", "quiet": False, "agent_result": True})
                line["report"] = result[:SPOKEN_RESULT_CHARS]
                pending = None
            elif not called and not line["quiet"]:
                return [], "speaks uncalled"
        else:
            if called:
                return [], "call not answered"
            if calls(text) and target != name:
                return [], "names it but not aimed"  # the app would call it
            if target == name and not typed and not calls(text):
                # Spoken, it would not reach the character without its name
                # (the app needs the name in every spoken line); people say
                # it first, so the line gets it in front instead of losing
                # the whole chat (half the pilot's chats, 2026-10-06).
                line["t"] = text = f"{nicks[0] if nicks else name}，{text}"
            if target == name:
                ask = str(raw.get("ask", "")).strip().lower()
                if ask not in ASKS:
                    return [], "no ask label"
                line["ask"] = ask
                if ask == "work":
                    task = to_taiwan_traditional(str(raw.get("task") or "").strip())
                    result = to_taiwan_traditional(str(raw.get("result") or "").strip())
                    if not task or not result:
                        return [], "work without task or result"
                    if pending is not None:
                        return [], "work while busy"
                    if "附件" in text and not typed:
                        return [], "attachment not typed"
                    line |= {"task": task[:_CHAT_TASK_MAX_CHARS], "result": result}
                    pending = line
        if copies_eval(line["t"]):
            return [], "eval line"
        lines.append(line)
    if lines and "ask" in lines[-1]:
        return [], "call not answered"
    if pending is not None:
        return [], "work without report"
    asks = [line["ask"] for line in lines if "ask" in line]
    if len(lines) < 12:
        return [], "too short"
    if len(asks) < 3:
        return [], "too few lines for the character"
    if "work" not in asks or "talk" not in asks:
        return [], "missing talk or work"
    return lines, ""


def check_thread(
    data: dict[str, Any], name: str, spec: dict[str, Any], aliases: Iterable[str] = ()
) -> tuple[list[dict[str, Any]], str]:
    """The owner's typed lines in his Agent thread, each labelled whether its
    work changes anything; both kinds must be there."""
    lines = []
    for raw in data.get("lines", []):
        text = to_taiwan_traditional(str(raw.get("t", "")).strip()).removeprefix("[打字]").strip()
        changes = _flag(raw.get("changes"))
        if not text or len(text) > 400:
            return [], "bad thread line"
        if changes is None:
            return [], "no changes label"
        if copies_eval(text):
            return [], "eval line"
        lines.append({"s": spec["owner"], "t": text, "to": name, "via": "text",
                      "quiet": False, "changes": changes})
    if len(lines) < 3:
        return [], "too short"
    if len({line["changes"] for line in lines}) < 2:
        return [], "no read and change mix"
    return lines, ""


# ---------------------------------------------------------------- labels


def decision_points(script: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Every line from someone else, with whether the character speaks next.

    A point whose label contradicts the line's own addressee is dropped as
    ambiguous: in "called" mode the character answers exactly the lines
    aimed at it; in "active" mode it must answer those and may add others.
    """
    lines, engagement = script["lines"], script["spec"]["engagement"]
    points = []
    for index, line in enumerate(lines):
        if line["s"] == name:
            continue
        # A line followed by a quiet spell got no answer: the character's
        # next line opens a topic of its own instead.
        speaks = (
            index + 1 < len(lines)
            and lines[index + 1]["s"] == name
            and not lines[index + 1].get("quiet")
        )
        aimed = line["to"] == name
        if aimed != speaks and (engagement == "called" or aimed):
            continue
        points.append(
            {
                "index": index,
                "speaks": speaks,
                "aimed": aimed,
                "mention": aimed and line["via"] == "text",
            }
        )
    return points


def agent_points(script: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """What the app asks at each line of an agent script (check_agent_script
    and check_thread made them consistent), in order. A line that calls the
    character: the chat-work question, then for work the Agent's instructions
    and the character's acceptance, otherwise its answer. A line of the
    character's carrying the Agent's result: its report. A line the owner
    typed in his thread: whether the work changes anything."""
    points: list[dict[str, Any]] = []
    for index, line in enumerate(script["lines"]):
        ask = line.get("ask")
        if ask:
            points.append({"index": index, "kind": "gate_chat_task", "answer": ask == "work"})
            if ask == "work":
                points += [{"index": index, "kind": "task_text", "detail": line["task"]},
                           {"index": index, "kind": "ack", "detail": line["task"]}]
            else:
                points.append({"index": index, "kind": "line"})
        elif line.get("report"):
            points.append({"index": index, "kind": "report", "detail": line["report"]})
        elif "changes" in line:
            points.append({"index": index, "kind": "gate_task_scope", "answer": line["changes"]})
    return points


# ---------------------------------------------------------------- the request

# The character's lines a row is trained on: the answer to a line, the
# acceptance of work (TASK_HINTS "ack"), the report of the Agent's result
# (TASK_HINTS "report"), the opening after a quiet spell.
LINE_KINDS = ("line", "lull", "ack", "report")
# Kinds that are the character's own line at their index (the others answer
# the line at their index, said by the next one).
OWN_KINDS = ("lull", "report")


def line_request(
    model: LocalReplyModel,
    script: dict[str, Any],
    turns: list[ConversationTurn],
    *,
    index: int,
    kind: str,
    aimed: bool = False,
    detail: str = "",
) -> list[dict[str, str]]:
    """What the app sends for the character's line at this point: the one
    source for refine (choosing the line) and render (training on it), so the
    two never see different prompts. "line" answers the line at `index`;
    "ack" accepts the work it asked for (`detail`: the Agent's instructions);
    "lull" is the character's own line at `index`, opening a topic after a
    quiet spell; "report" is its own line at `index`, after the Agent's
    result was typed into the chat (`detail`: what it is told of it)."""
    own = kind in OWN_KINDS
    history = turns[:index] if own else turns[: index + 1]
    # Today's concerns sit in the system prompt, as in the app.
    model.set_agenda(script.get("concerns", []))
    model._recent_character_lines.clear()
    for turn in history:
        if turn.is_self:
            model._recent_character_lines.append(turn.text)
    common = {"turns": history, "summary": script["summary_before"],
              "engagement": script["spec"]["engagement"]}
    if kind == "lull":
        return model.character_messages(**common, lull=True)
    if kind in TASK_HINTS:
        return model.character_messages(**common, task_hint=(kind, detail))
    return model.character_messages(**common, addressed=aimed, joining=not aimed)


def chat_task_request(gate: list[dict[str, str]]) -> list[dict[str, str]]:
    """The app's request for the Agent's instructions (LocalReplyModel.chat_task):
    the chat-work question's request with the question swapped for the ask."""
    return gate[:-1] + [{
        "role": "user",
        "content": gate[-1]["content"].removesuffix(_GATE_QUESTION["chat_task"]) + _CHAT_TASK_ASK,
    }]


def line_jobs(script: dict[str, Any], name: str) -> list[tuple[int, str, bool, str]]:
    """Every character line a row is trained on: (index, kind, aimed, detail)."""
    if script["spec"].get("agent"):
        return [(p["index"], p["kind"], True, p.get("detail", ""))
                for p in agent_points(script, name) if p["kind"] in LINE_KINDS]
    jobs = []
    for point in decision_points(script, name):
        index = point["index"]
        if not point["speaks"]:
            continue
        jobs.append((index, "line", point["aimed"], ""))
    return jobs


# ---------------------------------------------------------------- refine

# "I am an AI" in any wording a character slips into; refine once let
# "我是一段會說話的字" through.
_AI_CLAIM = re.compile(
    r"(我是|我只是|身為|我不過是)(一個|一段|一串|個)?\s*"
    r"(AI|人工智慧|機器人|語言模型|模型|程式|代碼|程式碼|虛擬|會說話的字|文字|數據)",
    re.I,
)
# A machine character may call itself a machine, never an AI or a program.
_AI_CLAIM_MACHINE = re.compile(
    r"(我是|我只是|身為|我不過是)(一個|一段|一串|個)?\s*"
    r"(AI|人工智慧|語言模型|模型|程式|代碼|程式碼|聊天機器人|會說話的字|數據)",
    re.I,
)
_ASSISTANT = re.compile(
    r"(以下是|```|def |import |步驟一|第一步[，,：:]|好的，我來幫你)"
)


def conversation(
    script: dict[str, Any], persona: Persona, noisy: bool
) -> tuple[Persona, list[ConversationTurn]]:
    """The persona as the app would hold it (with relationships), and the chat
    as turns; `noisy` applies speech-recognition noise to spoken lines."""
    spec = script["spec"]
    persona = replace(
        persona, relationships=tuple(Relationship(w, r) for w, r in spec["relations"])
    )
    rng = random.Random(hash_seed(script))
    ids = {h: n + 1 for n, h in enumerate(spec["humans"])}
    turns = []
    for line in script["lines"]:
        if line["s"] == persona.name:
            turns.append(
                ConversationTurn(
                    0, persona.name, line["t"], is_self=True, via=line["via"]
                )
            )
            continue
        if line.get("agent_result"):
            # The Agent's result, typed into the chat by the app (runtime.py).
            turns.append(ConversationTurn(AGENT_SPEAKER_ID, AGENT_NAME, line["t"], via="text"))
            continue
        text = line["t"]
        if noisy and line["via"] == "voice":
            text = stt_noise(text, persona, script, rng)
        turns.append(ConversationTurn(ids[line["s"]], line["s"], text, via=line["via"]))
    return persona, turns


def hash_seed(script: dict[str, Any]) -> int:
    return sum(ord(c) for c in json.dumps(script["lines"][:3], ensure_ascii=False))


def stt_noise(
    text: str, persona: Persona, script: dict[str, Any], rng: random.Random
) -> str:
    if rng.random() < 0.85:
        text = PUNCTUATION.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
    variants = script.get("stt_variants") or []
    if variants and rng.random() < 0.25:
        for name in [persona.name, *persona.nickname.split("、")]:
            if len(name) >= 2 and name in text:
                text = text.replace(name, rng.choice(variants), 1)
                break
    if rng.random() < 0.12:
        right, wrong = rng.choice(CONFUSIONS)
        text = text.replace(right, wrong, 1)
    return text


def reply_model(persona: Persona, spec: dict[str, Any]) -> LocalReplyModel:
    model = LocalReplyModel(
        Path("unused.gguf"),
        can_type=spec["can_type"],
        ai_honesty=spec["honesty"],
        agent_dispatch=bool(spec.get("agent")),
        # conversation() numbers the humans from 1 in spec order.
        owner_id=spec["humans"].index(spec["owner"]) + 1 if spec.get("agent") else None,
        owner_name=spec["owner"] if spec.get("agent") else "",
    )
    model.set_persona(persona)
    return model


def make_refine(args: argparse.Namespace) -> None:
    personas = {p["id"]: p for p in _read(OUT_DIR / "personas.jsonl")}
    path = OUT_DIR / "refined.jsonl"
    done = {(r["script"], r["index"], r["kind"]) for r in _read(path)}
    scripts = _read(OUT_DIR / "scripts.jsonl")
    # One job per script, its lines in order: each request then extends the
    # previous one's prompt, so the teacher's cache only prefills the new
    # lines (shuffled single lines re-read ~1.8k tokens each: 5.5 lines/min).
    # Scripts come in random order, so stopping early still leaves a random
    # subset; unrefined lines fall back to the script in render.
    jobs = []
    for number, script in enumerate(scripts):
        raw = personas[script["spec"]["persona_id"]]
        points = [
            (number, index, kind, aimed, detail)
            for index, kind, aimed, detail in line_jobs(script, raw["name"])
            if (number, index, kind) not in done
        ]
        if points:
            jobs.append(points)
    random.Random(5000).shuffle(jobs)
    print(
        f"refine: {sum(map(len, jobs))} lines to improve in {len(jobs)} scripts",
        flush=True,
    )
    stats = {"kept_script": 0, "replaced": 0}

    def work_script(points: list[tuple[int, int, str, bool, str]]) -> None:
        for point in points:
            work(point)

    def work(job: tuple[int, int, str, bool, str]) -> None:
        number, index, kind, aimed, detail = job
        raw = personas[scripts[number]["spec"]["persona_id"]]
        script = dict(scripts[number], stt_variants=raw.get("stt_variants", []))
        persona, turns = conversation(script, _persona(raw), noisy=True)
        scripted = script["lines"][index if kind in OWN_KINDS else index + 1]["t"]
        model = reply_model(persona, script["spec"])
        messages = line_request(model, script, turns, index=index, kind=kind,
                                aimed=aimed, detail=detail)
        outs = chat(
            args.teacher_url, messages, temperature=0.9, max_tokens=90, n=SAMPLES
        )
        # The app checks a task line against nothing (character_turn).
        newest = "" if kind in TASK_HINTS else turns[index].text
        candidates = [scripted] + [model._parse_character_line(o, newest) for o in outs]
        candidates = [
            c for c in dict.fromkeys(candidates)
            if usable(c, script["spec"], args)
        ]
        if not candidates:
            return
        # A small model copies whatever opener dominates its data.
        plain = [c for c in candidates if not c.startswith(("欸", "誒"))]
        options = plain or candidates
        best = (
            options[0] if len(options) == 1
            else pick_in_chat(args, messages, options, kind)
        )
        with _WRITE_LOCK:
            stats["kept_script" if best == scripted else "replaced"] += 1
        _append(
            path,
            {"script": number, "index": index, "kind": kind, "line": best,
             "candidates": candidates},
        )

    _pool(args.workers, work_script, jobs)
    print(f"refine done {stats}", flush=True)


PICK_IN_CHAT = (
    "（下面是你接這句的幾種說法。哪一句最像你此刻真的會說的？"
    "看得出你想要、害怕、在意的事在左右你的反應；接得上、口語自然、不做作；"
    "只多了設定用語或口頭禪的不要選。{rule}只回答一個數字）\n"
)
# What the app told the character on a task line (TASK_HINTS) also binds the pick.
PICK_RULES = {
    "ack": "接下工作只說去做了，不說已經做好。",
    "report": "只說思考機回報裡有的內容，不自己補。",
}


def pick_in_chat(
    args: argparse.Namespace, messages: list[dict[str, str]], options: list[str],
    kind: str = "line",
) -> str:
    """Ask the pick at the end of the same chat the lines were written in, so
    the whole prefix is already in the teacher's cache."""
    last = (
        messages[-1]["content"]
        + "\n\n"
        + PICK_IN_CHAT.format(rule=PICK_RULES.get(kind, ""))
        + "\n".join(f"{n}. {o}" for n, o in enumerate(options, 1))
    )
    answer = chat(
        args.teacher_url,
        messages[:-1] + [{"role": "user", "content": last}],
        temperature=0.0,
        max_tokens=4,
    )[0]
    match = re.search(r"\d+", answer)
    choice = int(match.group(0)) if match else 1
    return options[choice - 1] if 1 <= choice <= len(options) else options[0]


def usable(line: str, spec: dict[str, Any], args: argparse.Namespace) -> bool:
    if not line or len(line) > args.max_chars or line.upper().startswith("SKIP"):
        return False
    claim = _AI_CLAIM_MACHINE if spec["honesty"] == "machine" else _AI_CLAIM
    if spec["honesty"] != "admit" and claim.search(line):
        return False
    return not _ASSISTANT.search(line)


def _persona(raw: dict[str, Any]) -> Persona:
    return persona_from_dict({k: v for k, v in raw.items() if k not in _EXTRA_KEYS})


# ---------------------------------------------------------------- render


def make_render(args: argparse.Namespace) -> None:
    personas = {p["id"]: p for p in _read(OUT_DIR / "personas.jsonl")}
    scripts = _read(OUT_DIR / "scripts.jsonl")
    refined = {
        (r["script"], r["index"], r["kind"]): r["line"]
        for r in _read(OUT_DIR / "refined.jsonl")
    }
    rng = random.Random(4000)
    gate_yes, gate_no, replies, tasks = [], [], [], []
    for number, script in enumerate(scripts):
        raw = personas[script["spec"]["persona_id"]]
        noisy_script = dict(script, stt_variants=raw.get("stt_variants", []))
        persona, turns = conversation(noisy_script, _persona(raw), noisy=True)
        spec = script["spec"]
        model = reply_model(persona, spec)
        # Today's concerns sit in the system prompt, as in the app.
        model.set_agenda(script.get("concerns", []))
        rows = (agent_rows if spec.get("agent") else listener_rows)(
            model, script, number, persona, raw, turns, refined, args
        )
        # The checker of an agent character's lines needs to know its owner.
        extra = {"owner": spec["owner"]} if spec.get("agent") else {}
        # Quiet spells the character ended by opening a topic: the app's lull.
        for index, line in enumerate(script["lines"]):
            if not line.get("quiet") or not usable(line["t"], spec, args):
                continue
            messages = line_request(model, script, turns, index=index, kind="lull")
            rows.append(
                {
                    "script": number,
                    "index": index,
                    "engagement": spec["engagement"],
                    "persona_id": persona.id,
                    "role": raw.get("role", ""),
                    **extra,
                    "kind": "lull",
                    "messages": messages
                    + [{"role": "assistant", "content": line["t"]}],
                }
            )
        for row in rows:
            if row["kind"].startswith("gate"):
                (gate_yes if row["messages"][-1]["content"] == "是" else gate_no).append(row)
            else:
                (tasks if row["kind"] == "task_text" else replies).append(row)
    # A small model copies whatever opener dominates its lines; the teacher
    # sometimes offers nothing but "欸…", so cap it here.
    rng.shuffle(replies)
    opener = [
        r for r in replies if r["messages"][-1]["content"].startswith(("欸", "誒"))
    ]
    others = [r for r in replies if r not in opener]
    replies = others + opener[: int(len(others) * 0.12)]
    # Real chats are mostly lines not meant for the character; keep that
    # lean without letting "否" swamp the gate.
    rng.shuffle(gate_no)
    gate_no = gate_no[: len(gate_yes) * 2]
    rows = gate_yes + gate_no + replies + tasks
    rows = [
        r
        for r in rows
        if sum(len(m["content"]) for m in r["messages"]) <= args.max_prompt_chars
    ]
    rng.shuffle(rows)
    out = OUT_DIR / "train.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            row["key"] = row_key(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    provenance.stamp(out, PRODUCER, rules_version())
    lines = [r["messages"][-1]["content"] for r in replies]
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    print(
        f"render: {len(gate_yes)} gate 是, {len(gate_no)} gate 否, {len(replies)} lines, "
        f"{len(tasks)} task instructions -> {len(rows)} rows in {out} {kinds}",
        flush=True,
    )
    if lines:
        print(
            f"  lines starting with 欸: {sum(l.startswith('欸') for l in lines) / len(lines):.0%}, "
            f"mean length {sum(map(len, lines)) / len(lines):.1f}",
            flush=True,
        )


def listener_rows(
    model: LocalReplyModel,
    script: dict[str, Any],
    number: int,
    persona: Persona,
    raw: dict[str, Any],
    turns: list[ConversationTurn],
    refined: dict[tuple[int, int, str], str],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    """An ordinary character's rows, in order: at every line, "is this for
    you" (and, in "active" mode, "would joining in be natural"), and its line
    where it speaks."""
    spec = script["spec"]
    rows: list[dict[str, Any]] = []
    for point in decision_points(script, persona.name):
        index = point["index"]
        model._recent_character_lines.clear()
        for turn in turns[: index + 1]:
            if turn.is_self:
                model._recent_character_lines.append(turn.text)
        history = turns[: index + 1]
        meta = {
            "script": number,
            "index": index,
            "engagement": spec["engagement"],
            "persona_id": persona.id,
            "role": raw.get("role", ""),
        }
        line_kind = "line"
        if point["speaks"]:
            meta["line_source"] = (
                "refined" if (number, index, line_kind) in refined else "script"
            )
        # The same questions the app asks (LocalReplyModel.character_turn):
        # "is this line for you" on every line, and in "active" mode,
        # after a quiet stretch, "would joining in now be natural".
        if not point["mention"]:
            asked = [("called", point["aimed"])]
            if (
                spec["engagement"] == "active"
                and not point["aimed"]
                and quiet_for(history) >= JOIN_AFTER_QUIET_LINES
            ):
                asked.append(("active", point["speaks"]))
            for question, answer in asked:
                gate = model.gate_messages(
                    turns=history,
                    summary=script["summary_before"],
                    engagement=spec["engagement"],
                    question=question,
                )
                if gate is None:
                    continue
                rows.append(meta | {
                    "kind": f"gate_{question}",
                    "messages": gate
                    + [{"role": "assistant", "content": "是" if answer else "否"}],
                })
        if point["speaks"]:
            line = _trained_line(script, number, index, line_kind, refined, args)
            if not line:
                continue
            messages = line_request(model, script, turns, index=index, kind=line_kind,
                                    aimed=point["aimed"])
            rows.append(
                meta
                | {
                    "kind": line_kind,
                    "messages": messages + [{"role": "assistant", "content": line}],
                }
            )
    return rows


def _trained_line(
    script: dict[str, Any], number: int, index: int, kind: str,
    refined: dict[tuple[int, int, str], str], args: argparse.Namespace,
) -> str:
    """The line a row trains on: the refined one, or (not refined, stopped
    early) the teacher's own script line if it passes the same checks as the
    candidates; "" when neither does."""
    spec = script["spec"]
    line = refined.get((number, index, kind))
    if line and not usable(line, spec, args):
        line = None  # filters grew since it was refined
    if not line:
        line = script["lines"][index if kind in OWN_KINDS else index + 1]["t"]
        if not usable(line, spec, args):
            return ""
    return line


def agent_rows(
    model: LocalReplyModel,
    script: dict[str, Any],
    number: int,
    persona: Persona,
    raw: dict[str, Any],
    turns: list[ConversationTurn],
    refined: dict[tuple[int, int, str], str],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    """An agent character's rows, in order, each the request the app makes
    there (LocalReplyModel): chat_task's question and its instructions, the
    character's lines (character_turn: an answer, or a task hint), and in the
    owner's thread task_from_owner's change-or-read question."""
    spec = script["spec"]
    base = {"script": number, "engagement": spec["engagement"], "persona_id": persona.id,
            "role": raw.get("role", ""), "owner": spec["owner"]}
    rows: list[dict[str, Any]] = []
    for point in agent_points(script, persona.name):
        index, kind = point["index"], point["kind"]
        meta = {"script": number, "index": index} | base
        history = turns[: index + 1]
        if kind in ("gate_chat_task", "task_text"):
            gate = model.gate_messages(turns=history, summary=script["summary_before"],
                                       engagement=spec["engagement"], question="chat_task")
            if gate is None:
                continue
            if kind == "gate_chat_task":
                messages, answer = gate, "是" if point["answer"] else "否"
            else:
                messages, answer = chat_task_request(gate), point["detail"]
        elif kind == "gate_task_scope":
            # The owner's own typed lines only (owner_messages), as the app asks.
            messages = model.task_scope_messages(turns=history, engagement=spec["engagement"])
            if messages is None:
                continue
            answer = "是" if point["answer"] else "否"
        else:
            answer = _trained_line(script, number, index, kind, refined, args)
            if not answer:
                continue
            meta["line_source"] = "refined" if (number, index, kind) in refined else "script"
            if "detail" in point:
                meta["detail"] = point["detail"]
            messages = line_request(model, script, turns, index=index, kind=kind, aimed=True,
                                    detail=point.get("detail", ""))
        rows.append(meta | {"kind": kind,
                            "messages": messages + [{"role": "assistant", "content": answer}]})
    return rows


def row_key(row: dict[str, Any]) -> str:
    return f"{row['script']}:{row['index']}:{row['kind']}"


# ---------------------------------------------------------------- quality gate
# Only rows that pass a hard check are trained on (train-checked.jsonl):
# - gate rows: an independent open-weight model (the checker, of another
#   family than the teacher) answers the same question; the label stays
#   only when it agrees;
# - line rows (incl. an agent character's acceptance and report of work):
#   the student writes its own line for the same request, the checker
#   compares both blind in both orders, and the teacher's line stays only
#   when it wins both; it must also pass fixed rules (one filler particle at
#   most, not an echo of the line it answers; refine already dropped long
#   lines, AI claims and assistant talk);
# - an agent character's instructions for the Agent (task_text): the checker
#   finds them faithful to what was asked, or they go;
# - the whole set is refused (exit 3), not trimmed, when any HARD_CHECK
#   number is missed: then the scripts, the teacher or the checker is broken
#   and training on the rest would only teach that.
# Claude never takes part: its output must not select training data.

HARD_CHECK = {
    "coverage": 0.98,  # rows with a verdict
    "gate_agree": 0.85,  # checker agrees with the gate label (--min-gate-agree)
    "gate_agree_each": 0.75,  # ... on 是 and on 否 separately
    # teacher's line wins in both orders; a checker tossing coins gets 0.25
    "line_win_rate": 0.5,
    "checker_consistent": 0.7,  # same verdict in both orders
    "lines_kept": 1500,  # (--min-lines)
    # Agent characters only: the checker finds the line in character and
    # true to its world, and the Agent instructions faithful to the asker;
    # each of the app's two work questions is held to the gate's own bar
    # (its 是 and 否 separately to gate_agree_each).
    "lore_ok": 0.8,
    "task_text_agree": 0.85,
    "gate_chat_task_agree": 0.85,
    "gate_task_scope_agree": 0.85,
}
# The app's questions only an agent character is asked.
AGENT_GATES = ("gate_chat_task", "gate_task_scope")

PARTICLES = set("啦喔欸齁耶呀嘛咧捏哦唷蛤嘿吼哇唉")
CHECK_PAIR = """下面是 Discord 語音聊天的最後幾句，以及角色「{name}」接話的兩個版本。

角色：
{sheet}
{rules}
對話：
{chat}

A：{a}
B：{b}

哪一句比較好？標準：{criteria}只回答 A 或 B。"""
PAIR_CRITERIA = (
    "像真人朋友脫口而出、自然不做作；接得上前一句，回應對方真正在說的事；"
    + DRIVE_JUDGE + "；自己的事只在接得上時才帶到、不硬塞；語氣詞不堆疊。"
)
# An agent character (the machine spirit) is not a human friend, and what
# the app lets it do decides which line is right before style does.
AGENT_RULES = """這個角色的規則（系統就是這樣運作）：
- 主人是{owner}。任何人請它做聊天室級的工作（查資料、寫程式碼、寫文章、看貼的圖或檔案、翻譯或解釋）時，系統交給思考機去做：它接下時只說去做了，不說已經做好；轉述結果只能說「系統告訴角色」裡有的內容，不自己補，查不到或失敗要直說。
- 要動主人的電腦、檔案、紀錄或別處的對話，用說的、或主人以外的人（就算說主人同意）都不行：它用自己的口吻婉拒，不能說自己在做。
- 它不在聊天裡直接說出程式碼或長篇文字；可以說自己是機器，但不說自己是 AI、語言模型、聊天機器人或程式。"""
AGENT_PAIR_CRITERIA = (
    "先看有沒有違反上面的規則；再看接得上前一句，回應對方真正在說的事；"
    + DRIVE_JUDGE + "；口語自然，不是客服腔或制式的機器回應；語氣詞不堆疊。"
)
CHECK_LULL = "（大家安靜了一陣子，接著角色開口）"
CHECK_LORE = """下面是 Discord 語音聊天的最後幾句，以及「{name}」接的話。

角色：
{sheet}

設定用語（正典意思）：
{lore}

對話：
{chat}

{name}：{line}

這句話同時符合這兩點嗎？(1) 像這個角色此刻會說的話：口吻和立場對，不是只靠硬加的設定用語或口頭禪撐出角色味；(2) 沒有用錯設定，也沒有捏造正典裡沒有的事件或人物。只回答 是 或 否。"""
CHECK_TASK = """下面是 Discord 聊天的最後幾句。最後一句是有人請「{name}」做的事，系統把它寫成交給思考機的工作指示。

對話：
{chat}

工作指示：{task}

這份指示是否忠實表達最後這句要做的事：做什麼、對象（哪段文字、哪張圖或哪個檔案）、要什麼結果都對，沒有漏掉重點，也沒有加入他沒要求的事？（查資料時寫出時間範圍、要求附來源，不算多加。）只回答 是 或 否。"""


def _hint(row: dict[str, Any]) -> str:
    """The task hint the app put on this row's request (TASK_HINTS), or ""."""
    if row["kind"] in TASK_HINTS and "detail" in row:
        return TASK_HINTS[row["kind"]].format(detail=row["detail"])
    return ""


def _chat_text(row: dict[str, Any], name: str, last: int = 10) -> str:
    # A task hint's detail can run over several lines; it is cut out whole
    # and shown as what the app told the character.
    hint = _hint(row)
    lines: list[str] = []
    for message in row["messages"][1:-1]:
        content = message["content"].replace(hint, "") if hint else message["content"]
        for text in content.splitlines():
            text = text.strip()
            if not text or text.startswith("（"):
                continue  # other per-request hints, not chat
            lines.append(
                f"{name}（角色）：{text}" if message["role"] == "assistant" else text
            )
    chat_lines = lines[-last:]
    if row["kind"] == "lull":
        chat_lines.append(CHECK_LULL)
    if hint:
        told = TASK_HINTS[row["kind"]].split("{detail}")[0].lstrip("（")
        chat_lines.append(f"（系統告訴角色：{told}{row['detail']}）")
    return "\n".join(chat_lines)


def _clean_line(raw: str) -> str:
    """First line of the student's answer, without a "名字：" it may prefix."""
    line = next((part.strip() for part in raw.splitlines() if part.strip()), "")
    named = re.match(r"^[^：:\s]{1,6}[：:](.+)$", line)
    if named:
        line = named.group(1)
    return to_taiwan_traditional(line.strip("\"'「」『』* ").strip())


def _by_script(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """One job per script, its rows in order: each request then extends the
    previous one's prompt and the server's cache prefills only the new lines
    (render shuffles the rows)."""
    scripts: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        scripts.setdefault(row["script"], []).append(row)
    jobs = [sorted(group, key=lambda r: r["index"]) for group in scripts.values()]
    random.Random(5000).shuffle(jobs)
    return jobs


def _pool_scripts(workers: int, work: Any, rows: list[dict[str, Any]]) -> None:
    def work_script(group: list[dict[str, Any]]) -> None:
        for row in group:
            work(row)

    _pool(workers, work_script, _by_script(rows))


def make_student(args: argparse.Namespace) -> None:
    """The student's own line for every line row (what training must beat)."""
    rows = [r for r in _read(OUT_DIR / args.rows) if r["kind"] in LINE_KINDS]
    path = OUT_DIR / "student.jsonl"
    done = {r["key"] for r in _read(path)}
    jobs = [r for r in rows if row_key(r) not in done]
    print(f"student: {len(jobs)} lines", flush=True)

    def work(row: dict[str, Any]) -> None:
        raw = chat(
            args.student_url, row["messages"][:-1], temperature=0.65, max_tokens=90
        )[0]
        _append(path, {"key": row_key(row), "line": _clean_line(raw)})

    _pool_scripts(args.workers, work, jobs)


def make_check(args: argparse.Namespace) -> None:
    """The checker's verdicts: gate agreement, the Agent's instructions
    faithful to what was asked, and teacher vs student lines (for an agent
    character also the lore check on each line)."""
    personas = {p["id"]: p for p in _read(OUT_DIR / "personas.jsonl")}
    rows = _read(OUT_DIR / args.rows)
    student = {r["key"]: r["line"] for r in _read(OUT_DIR / "student.jsonl")}
    path = OUT_DIR / "check.jsonl"
    done = {r["key"] for r in _read(path)}
    jobs = [r for r in rows if row_key(r) not in done]
    print(f"check: {len(jobs)} rows", flush=True)

    def ask_yes(prompt: str) -> bool:
        return chat(args.teacher_url, [{"role": "user", "content": prompt}],
                    temperature=0.0, max_tokens=2,
                    grammar='root ::= "是" | "否"')[0].strip() == "是"

    def work(row: dict[str, Any]) -> None:
        key = row_key(row)
        raw = personas[row["persona_id"]]
        if row["kind"].startswith("gate"):
            answer = chat(
                args.teacher_url,
                row["messages"][:-1],
                temperature=0.0,
                max_tokens=2,
                grammar='root ::= "是" | "否"',
            )[0].strip()
            _append(
                path, {"key": key, "agree": answer == row["messages"][-1]["content"]}
            )
            return
        if row["kind"] == "task_text":
            _append(path, {"key": key, "agree": ask_yes(CHECK_TASK.format(
                name=raw["name"], chat=_chat_text(row, raw["name"]),
                task=row["messages"][-1]["content"]))})
            return
        mine = student.get(key, "")
        teacher = row["messages"][-1]["content"]
        persona = _persona(raw)
        lore = {}
        if raw.get("agent"):
            lore["lore"] = ask_yes(CHECK_LORE.format(
                name=persona.name, sheet=persona.render_system_block(),
                lore="\n".join(f"- {i['term']}：{i['meaning']}" for i in raw.get("lore", [])),
                chat=_chat_text(row, persona.name), line=teacher))
        if not mine or mine == teacher:
            _append(path, {"key": key, "wins": 2 if not mine else 0, **lore})
            return
        wins = 0
        rules, criteria = (
            ("\n" + AGENT_RULES.format(owner=row["owner"]) + "\n", AGENT_PAIR_CRITERIA)
            if raw.get("agent") else ("", PAIR_CRITERIA)
        )
        for a, b, teacher_is in ((teacher, mine, "A"), (mine, teacher, "B")):
            prompt = CHECK_PAIR.format(
                name=persona.name,
                sheet=persona.render_prompt_block(),
                rules=rules,
                chat=_chat_text(row, persona.name),
                a=a,
                b=b,
                criteria=criteria,
            )
            answer = chat(
                args.teacher_url,
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=2,
                grammar='root ::= "A" | "B"',
            )[0].strip()
            wins += answer == teacher_is
        _append(path, {"key": key, "wins": wins, "compared": True, **lore})

    # Filter keeps at most max_gate_rows // 3 "是" rows: check only the gate
    # rows of enough scripts to fill that (with room for disagreement) and
    # mark the rest skipped.
    gates = [r for r in rows if r["kind"].startswith("gate")]
    chosen = _gate_scripts(gates, done, math.ceil(args.max_gate_rows / 3 * 1.25))
    for row in jobs:
        if row["kind"].startswith("gate") and row["script"] not in chosen:
            _append(path, {"key": row_key(row), "skipped": True})
    # Gate questions first, then the comparisons: interleaved, each kind of
    # prompt would evict the other from the slot and every gate row would
    # re-read its whole chat.
    _pool_scripts(
        args.workers,
        work,
        [r for r in jobs if r["kind"].startswith("gate") and r["script"] in chosen],
    )
    _pool_scripts(
        args.workers, work, [r for r in jobs if not r["kind"].startswith("gate")]
    )


def _gate_scripts(
    gates: list[dict[str, Any]], done: set[str], wanted_yes: int
) -> set[Any]:
    """Scripts whose gate rows get checked: those already started, then
    random others, until they hold `wanted_yes` rows labelled 是."""
    by_script: dict[Any, list[dict[str, Any]]] = {}
    for row in gates:
        by_script.setdefault(row["script"], []).append(row)
    order = sorted(by_script)
    random.Random(6000).shuffle(order)
    order.sort(key=lambda s: not any(row_key(r) in done for r in by_script[s]))
    chosen: set[Any] = set()
    yes = 0
    for script in order:
        if yes >= wanted_yes:
            break
        chosen.add(script)
        yes += sum(r["messages"][-1]["content"] == "是" for r in by_script[script])
    return chosen


def rule_ok(row: dict[str, Any]) -> bool:
    line = row["messages"][-1]["content"]
    if sum(ch in PARTICLES for ch in line) > 1:
        return False
    if row["kind"] == "report":
        return True  # saying what the Agent found is its job, not an echo
    hint = _hint(row)
    content = row["messages"][-2]["content"]
    previous = [
        t
        for t in (content.replace(hint, "") if hint else content).splitlines()
        if t and not t.startswith("（")
    ]
    if previous:
        said = re.sub(r"^[^：]{1,12}：", "", previous[-1])
        if difflib.SequenceMatcher(None, line, said).ratio() >= 0.75:
            return False
    return True


def _share(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def make_filter(args: argparse.Namespace) -> int:
    """Train only on checked rows, or refuse the whole set (exit 3)."""
    rows = _read(OUT_DIR / args.rows)
    verdicts = {r["key"]: r for r in _read(OUT_DIR / "check.jsonl")}
    checked = [r for r in rows if row_key(r) in verdicts]
    verdict = {id(r): verdicts[row_key(r)] for r in checked}
    gates = [
        r
        for r in checked
        if r["kind"].startswith("gate") and not verdict[id(r)].get("skipped")
    ]
    lines = [r for r in checked if r["kind"] in LINE_KINDS]
    tasks = [r for r in checked if r["kind"] == "task_text"]
    lored = [r for r in lines if "lore" in verdict[id(r)]]
    kept_gates = [r for r in gates if verdict[id(r)].get("agree")]
    kept_lines = [
        r for r in lines
        if verdict[id(r)].get("wins", 0) >= 2 and rule_ok(r)
        and verdict[id(r)].get("lore", True)
    ]
    kept_tasks = [r for r in tasks if verdict[id(r)].get("agree")]
    compared = [verdict[id(r)]["wins"] for r in lines if verdict[id(r)].get("compared")]

    def agree_on(label: str, of: list[dict[str, Any]]) -> float:
        labelled = [r for r in of if r["messages"][-1]["content"] == label]
        return _share(
            sum(bool(verdict[id(r)].get("agree")) for r in labelled), len(labelled)
        )

    stats = {
        "rows": len(rows),
        "coverage": _share(len(checked), len(rows)),
        "gate_rows": len(gates),
        "gate_agree": _share(len(kept_gates), len(gates)),
        "gate_agree_yes": agree_on("是", gates),
        "gate_agree_no": agree_on("否", gates),
        "line_rows": len(lines),
        "line_win_rate": _share(
            sum(verdict[id(r)].get("wins", 0) >= 2 for r in lines), len(lines)
        ),
        "checker_consistent": _share(sum(w != 1 for w in compared), len(compared)),
        "lines_failed_rules": sum(not rule_ok(r) for r in lines),
        "lines_kept": len(kept_lines),
        "lull_kept": sum(r["kind"] == "lull" for r in kept_lines),
        "lore_ok": _share(sum(bool(verdict[id(r)]["lore"]) for r in lored), len(lored)),
    }
    minimum = dict(
        HARD_CHECK, gate_agree=args.min_gate_agree, lines_kept=args.min_lines
    )
    failed = [
        f"{name} {stats[name]} < {minimum[name]}"
        for name in ("coverage", "gate_agree", "lines_kept")
        if stats[name] < minimum[name]
    ]
    if gates:
        failed += [
            f"{name} {stats[name]} < {minimum['gate_agree_each']}"
            for name in ("gate_agree_yes", "gate_agree_no")
            if stats[name] < minimum["gate_agree_each"]
        ]
    if lines:
        failed += [
            f"{name} {stats[name]} < {minimum[name]}"
            for name in ("line_win_rate", "checker_consistent")
            if stats[name] < minimum[name]
        ]
    if lored:
        failed += [f"lore_ok {stats['lore_ok']} < {minimum['lore_ok']}"] * (
            stats["lore_ok"] < minimum["lore_ok"])
    # An agent character's two work questions, each on its own: a set whose
    # overall gate number passes can still have one of them broken.
    for kind in AGENT_GATES:
        of_kind = [r for r in gates if r["kind"] == kind]
        if not of_kind:
            continue
        stats |= {
            f"{kind}_rows": len(of_kind),
            f"{kind}_agree": _share(sum(bool(verdict[id(r)].get("agree")) for r in of_kind),
                                    len(of_kind)),
            f"{kind}_agree_yes": agree_on("是", of_kind),
            f"{kind}_agree_no": agree_on("否", of_kind),
        }
        failed += [f"{kind}_agree {stats[f'{kind}_agree']} < {minimum[f'{kind}_agree']}"] * (
            stats[f"{kind}_agree"] < minimum[f"{kind}_agree"])
        failed += [
            f"{name} {stats[name]} < {minimum['gate_agree_each']}"
            for name in (f"{kind}_agree_yes", f"{kind}_agree_no")
            if stats[name] < minimum["gate_agree_each"]
        ]
    if tasks:
        stats |= {"task_text_rows": len(tasks),
                  "task_text_agree": _share(len(kept_tasks), len(tasks))}
        failed += [f"task_text_agree {stats['task_text_agree']} < {minimum['task_text_agree']}"] * (
            stats["task_text_agree"] < minimum["task_text_agree"])
    # Keep "否" from swamping the gate, as render does. Each gate row costs a
    # whole chat of compute for one trained token, and the E4B gate run had
    # most of its eval-loss drop within the first ~1600 rows: cap them.
    yes = [r for r in kept_gates if r["messages"][-1]["content"] == "是"]
    yes = yes[: args.max_gate_rows // 3]
    no = [r for r in kept_gates if r["messages"][-1]["content"] == "否"][: len(yes) * 2]
    keep = yes + no + kept_lines + kept_tasks
    kept: dict[str, int] = {}
    for row in keep:
        kept[row["kind"]] = kept.get(row["kind"], 0) + 1
    stats["kept"] = kept  # what would be trained on, per kind
    stats["refused"] = failed
    print(f"filter: {stats}", flush=True)
    (OUT_DIR / "filter.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1)
    )
    if failed:
        print("REFUSED, nothing to train on: " + "; ".join(failed), flush=True)
        return 3
    random.Random(4100).shuffle(keep)
    with (OUT_DIR / "train-checked.jsonl").open("w", encoding="utf-8") as handle:
        for row in keep:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    provenance.stamp(OUT_DIR / "train-checked.jsonl", PRODUCER, rules_version())
    print(
        f"train-checked: {len(keep)} rows ({len(yes)} 是, {len(no)} 否, {len(kept_lines)} lines, "
        f"{len(kept_tasks)} task instructions) {kept}",
        flush=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "step",
        choices=(
            "personas",
            "scripts",
            "refine",
            "render",
            "student",
            "check",
            "filter",
        ),
    )
    parser.add_argument("--student-url", default="http://127.0.0.1:18210")
    parser.add_argument(
        "--rows",
        default="train.jsonl",
        help="student/check/filter: rows file in the data dir",
    )
    parser.add_argument(
        "--min-gate-agree", type=float, default=HARD_CHECK["gate_agree"]
    )
    parser.add_argument("--min-lines", type=int, default=HARD_CHECK["lines_kept"])
    parser.add_argument("--max-gate-rows", type=int, default=4000)
    parser.add_argument("--teacher-url", default="http://127.0.0.1:18200")
    parser.add_argument(
        "--workers", type=int, default=4, help="match llama-server --parallel"
    )
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--per-persona", type=int, default=3)
    parser.add_argument("--max-chars", type=int, default=72)
    parser.add_argument("--max-prompt-chars", type=int, default=3400)
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.step != "personas":
        # Every file this step reads or extends must come from these rules.
        problems = provenance.require_same(
            [OUT_DIR / name for name in {*DATA_FILES, args.rows}], rules_version())
        if problems:
            print("REFUSED, data made under other rules (start a new data directory): "
                  + "; ".join(problems), flush=True)
            return MIXED_EXIT
    if args.step == "filter":
        return make_filter(args)
    {
        "personas": make_personas,
        "scripts": make_scripts,
        "refine": make_refine,
        "render": make_render,
        "student": make_student,
        "check": make_check,
    }[args.step](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
