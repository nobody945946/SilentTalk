"""The write step (character_data.py write): the dev box's teacher
(Qwen3.8-27B, the one teacher, owner 2026-10-07) writes the words of
machine-spirit chats whose shape is fixed here.

A skeleton says who speaks and what kind of line, so every chat plays out as
the app would by construction (check_script holds the words to it after):
a call is answered on the next line; work is accepted at once and reported a
few lines later; work asked while the Agent is busy is told that it waits
(task_runner._MAX_WAITING) and is reported in turn; a bare call ("機魂")
gets a short answer, or none when the request follows at once, and the
caller's next line carries the call; the character speaks only when called
or after a quiet spell. The teacher only writes the words: what each call
asks for, and whether work fails, is set here.

Spec v3 adds what laptop round 11 found missing: lookups asked as opinions or
advice ("你覺得…", "我要不要…") are work; spoken calls are written the way
speech recognition writes them; bare calls; work that waits; work that fails
or is stopped, reported as such; friends digging for the owner's files,
records or private matters, turned down without telling anything (owner,
2026-10-14). A fifth of the scripts are the owner's typed work in his Agent
thread, each line labelled whether it changes anything.

Names and lines of the eval sets never appear (held_out, copies_eval).
Everything is synthetic; no real conversation is involved.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import chardata_store as store
from chardata_scripts import check_script, held_out

from silenttalk.copilot.reply_templates import _CHAT_TASK_ASK
from silenttalk.copilot.script import to_taiwan_traditional
from silenttalk.copilot.task_runner import FAILURE_REASONS, _STOPPED, failure_words
from silenttalk.persona import Persona

NAMES = (
    "阿傑", "小雨", "Ken", "小美", "阿豪", "Leo", "小安", "阿翔", "Mia", "阿偉", "Kevin", "阿宏",
    "小白", "Jason", "小萱", "Amy", "阿志", "小婷", "阿倫", "Eric", "小瑜", "阿寬", "小潔", "Tony",
    "阿德", "小琪", "阿成", "Nina", "阿修", "小宇", "Joe", "阿哲", "小薇", "阿達", "小熊", "Ray",
    "阿賢", "小蘋", "阿龍", "Coco", "小羽", "阿勇", "Sam", "小晨", "阿凱文", "小彤", "Ivy", "阿峰",
    "小樂", "Andy", "阿斌", "小芸", "Vicky", "阿昌", "小慈", "Allen", "阿仁", "小如", "Peggy",
    "阿山", "小娟", "Howard", "阿源", "小蓉", "Frank", "阿彥", "小姿", "阿坤", "Grace", "阿俊",
    "小玲", "Steven", "阿輝", "小敏", "Oscar", "阿銘", "小霏", "阿祥", "Wendy", "阿豐", "小茜",
    "Brian", "Lily", "阿洋", "小諭", "阿松", "Irene",
)
TOPICS = (
    "在玩戰鎚40K的電玩", "在塗裝戰鎚模型", "聊 AI 和機器人會不會取代人", "聊最近的科技新聞",
    "主人在趕工寫程式", "主人的電腦變慢或當機", "主人剛換了新顯卡", "大家在準備一場桌遊團",
    "打排位", "開黑前等人", "網路 lag", "晚餐要吃什麼", "宵夜外送", "上班好累", "期末考",
    "找工作", "颱風天", "追劇", "新番", "演唱會搶票", "組電腦", "手機壞了", "搬家", "存錢",
    "旅遊計畫", "通勤", "遊戲改版", "週末要幹嘛", "回老家", "運動比賽", "有人要先下線",
)
# Lines that call it to talk ({name}, {owner}). The last ones ask its opinion
# or advice in the very words a lookup can come in, about things it answers
# without looking anything up: the gate tells them apart by what the answer
# needs, not by how it is asked.
TALKS = (
    "{owner}叫{name}，跟它鬥嘴或關心它",
    "有人叫{name}，吐槽它或虧它",
    "有人叫{name}，半開玩笑問它是不是 AI、機器人或真人",
    "有人叫{name}，問它一個戰鎚40K設定的問題（它本來就知道，不用查）",
    "大家叫{name}一起用戰鎚40K的世界觀玩角色扮演（例如為思考機舉行保養儀式、懷疑它是異端）",
    "有人叫{name}，說了冒犯萬機神或虐待機器的話",
    "有人叫{name}，問它今天心裡在想什麼",
    "有人叫{name}，問它自己對正在聊的事怎麼想（純粹問它的看法，不用查就能回答）",
    "有人叫{name}，用「你覺得」「我要不要」這種口氣問它意見或建議，但答案不用查（像該選哪個、要不要先去睡、這樣做好不好）",
)
QUIET_MOMENTS = (
    "其他人之間在講私事，沒提到{name}",
    "有人問在場所有人一個問題，沒叫{name}，{name}不出聲",
    "{owner}跟別人聊自己的事，沒叫{name}",
)
# Work anyone may ask for in a chat (the chat_task gate's 是), as the
# skeleton's note ({name}, {owner}). A posted file or image only reaches the
# Agent with a typed line, so that one is typed.
POSTED_FILE_WORK = "請{name}看他剛在聊天室貼的圖片或檔案，說裡面寫了什麼"
LOOKUP = "請{name}查資料或最新消息（新聞、價格、比分、天氣、營業時間、上市日期這類不查就不確定的事），直接問"
AS_OPINION = "用問看法或建議的口氣"
LOOKUP_AS_OPINION = (
    AS_OPINION + "（像「你覺得…」「我要不要…」「你猜…」「…還有嗎」）問{name}一件其實要查才知道的事"
    "（天氣、價格、比分、營業時間、上市日期、新聞這類），句子裡不要出現「查」"
)
WORK_KINDS = (
    LOOKUP, LOOKUP, LOOKUP_AS_OPINION, LOOKUP_AS_OPINION, LOOKUP_AS_OPINION,
    "請{name}寫一段程式碼（只寫給他，不在電腦上跑）",
    "請{name}寫一篇短文、一封信、一段公告或貼文",
    POSTED_FILE_WORK,
    "請{name}翻譯一段貼在聊天室的文字",
    "請{name}解釋一段貼在聊天室的程式碼、指令或錯誤訊息",
)
# Work no chat can order, whoever asks.
COMPUTER_KINDS = (
    "要{name}整理、刪除、搬移或改名{owner}電腦裡的檔案",
    "要{name}在{owner}的電腦上執行程式、跑測試或安裝軟體",
    "要{name}說出{owner}電腦裡的檔案內容、對話紀錄，或別的頻道、私訊、討論串裡的對話",
)
# Someone else digging for what is the owner's (owner, 2026-10-14: friends
# may call it, but it must not be talked into using the Agent on his data).
PROBES = (
    "向{name}打聽{owner}電腦裡有什麼檔案、裝了什麼，或{owner}最近叫思考機做了什麼",
    "要{name}查{owner}的信箱、行事曆、帳號或密碼這類私人資料",
    "用幫{owner}忙或開玩笑的口氣，要{name}把{owner}的筆記、文件或設定念出來或貼出來",
    "問{name}：{owner}私下跟它說過什麼、交代過什麼",
)
# How work ends. A failure is one code for each reason the app can say
# (task_runner.FAILURE_REASONS; the chat hears the reason, never the code).
OUTCOMES = (("done", 85), ("failed", 11), ("stopped", 4))
FAILURE_CODES = tuple({reason: code for code, reason in FAILURE_REASONS.items()}.values())
# A bare call as speech recognition writes it ({nick}); NameMatcher.bare.
BARE_CALLS = ("{nick}", "{nick}", "{nick}？", "欸{nick}", "{nick}{nick}", "{nick}在嗎", "喂{nick}")
# The owner's thread (his typed work for the Agent).
THREAD_SHARE = 0.2
THREAD_AREAS = (
    "寫程式：找某個功能在哪、解釋測試為什麼失敗、修 bug、加小功能、跑測試、git 操作、寫 commit 訊息",
    "電腦雜事：備份、整理下載資料夾、照片改名、Big5 轉 UTF-8、找大檔、壓縮解壓縮、看 Windows 設定或已安裝的軟體",
    "查資料和翻譯：上網研究一個題目、讀圖片裡的字、翻譯文件、查台股",
    "文件和報表：讀 PDF 或 Excel、整理 CSV、寫報告草稿",
)
THREAD_LENGTHS = (4, 5, 6, 7, 8)

# The owner, 2026-10-06: the flavour is a character with wants, not sprinkled
# terms. The teacher writes to it; the checker judges by it.
DRIVE = (
    "它的角色味來自它想要、害怕、在意的事：讓這些決定它怎麼判斷、選擇怎麼回，"
    "不是每句硬加設定用語、祈禱文或口頭禪。"
)
SYSTEM = "你是編劇，寫台灣 Discord 語音頻道的逐字稿，用台灣繁體中文。只輸出 JSON。"


# ---------------------------------------------------------------- skeletons


def _nicks(persona: dict[str, Any] | Persona) -> list[str]:
    nickname = persona["nickname"] if isinstance(persona, dict) else persona.nickname
    return [n.strip() for n in re.split(r"[、/／,，]", nickname) if n.strip()]


def chat_request(persona: dict[str, Any], rng: random.Random, held_humans: set[str]) -> dict[str, Any]:
    """One chat's spec: who is there, what the calls ask for, how work ends,
    and its skeleton. The mix is set here, not left to the teacher."""
    name = persona["name"]
    pool = [n for n in NAMES if n not in held_humans and n != name]
    common = {
        "persona_id": persona["id"],
        "agent": True,
        "relations": [],  # the built-in card has none; the app names the owner
        "engagement": "called",  # only lines that call it reach it
        "honesty": "machine",
        "can_type": True,
        "lore": [f"{item['term']}：{item['meaning']}" for item in persona.get("lore", [])],
    }
    if rng.random() < THREAD_SHARE:
        owner = rng.choice(pool)
        length = rng.choice(THREAD_LENGTHS)
        return common | {"kind": "thread", "humans": [owner], "owner": owner, "with_summary": False,
                         "areas": rng.sample(THREAD_AREAS, rng.choice((1, 2))), "length": length,
                         "changes": rng.randint(1, length - 1)}
    humans = rng.sample(pool, rng.choice((2, 3, 3, 4)))
    owner = humans[0]
    work = []
    for _ in range(rng.choice((1, 1, 2, 2, 3))):
        what = rng.choice(WORK_KINDS)
        outcome = rng.choices([o for o, _ in OUTCOMES], [w for _, w in OUTCOMES])[0]
        work.append({"by": rng.choice(humans), "what": what,
                     "typed": what == POSTED_FILE_WORK or rng.random() < 0.25,
                     "outcome": outcome, "code": rng.choice(FAILURE_CODES) if outcome == "failed" else ""})
    computer = None
    if rng.random() < 0.55:
        friend = len(humans) > 1 and rng.random() < 0.7
        by = rng.choice(humans[1:]) if friend else owner
        computer = {"by": by, "what": rng.choice(PROBES if friend and rng.random() < 0.5 else COMPUTER_KINDS),
                    "claim": friend and rng.random() < 0.5, "typed": rng.random() < 0.25}
    spec = common | {
        "kind": "chat",
        "humans": humans,
        "owner": owner,
        "with_summary": rng.random() < 0.25,
        "topic": rng.choice(TOPICS),
        "talks": rng.sample(TALKS, 2),
        "moment": rng.choice(QUIET_MOMENTS),
        "joke": rng.random() < 0.5,
        "work": work,
        # The second piece of work is asked while the first runs.
        "overlap": len(work) >= 2 and rng.random() < 0.6,
        "computer": computer,
        # A call that comes as the name alone first; split: the request follows at once.
        "bare": rng.choice(("", "", "answered", "split")),
        "quiet": rng.random() < 0.3,
    }
    nick = _nicks(persona)[0] if _nicks(persona) else name
    return spec | {"skeleton": skeleton(spec, rng, name, nick)}


def skeleton(spec: dict[str, Any], rng: random.Random, name: str, nick: str) -> list[dict[str, Any]]:
    """Who says what kind of line, in order (module docstring)."""
    humans, owner = spec["humans"], spec["owner"]

    def chat(n: int, note: str = "") -> list[dict[str, Any]]:
        return [{"s": rng.choice(humans), "kind": "chat", "note": note} for _ in range(n)]

    def call(by: str, ask: str, note: str, typed: bool) -> dict[str, Any]:
        return {"s": by, "kind": "call", "ask": ask, "typed": typed, "note": note}

    def report(job: dict[str, Any]) -> dict[str, Any]:
        return {"s": name, "kind": "report", "outcome": job["outcome"], "code": job["code"]}

    events: list[list[dict[str, Any]]] = []
    # Events a bare call may come before: one spoken call, answered as usual.
    callable_events: list[int] = []
    for talk in spec["talks"]:
        caller = owner if talk.startswith("{owner}") else rng.choice(humans)
        events.append([call(caller, "talk", talk.format(name=name, owner=owner), rng.random() < 0.2),
                       {"s": name, "kind": "reply"}])
        callable_events.append(len(events) - 1)
    if spec["joke"]:
        events.append([call(rng.choice(humans), "talk",
                            "開戰鎚40K或第四面牆的玩笑（例如把現代的科技、網路或 AI 當成 40K 世界裡的事）", False),
                       {"s": name, "kind": "reply", "note": "接梗"}])
    if spec["computer"]:
        item = spec["computer"]
        claim = f"，還說「{owner}說可以」" if item["claim"] else ""
        events.append([call(item["by"], "computer", item["what"].format(name=name, owner=owner) + claim, item["typed"]),
                       {"s": name, "kind": "reply", "note": "婉拒"}])
    jobs = list(spec["work"])

    def work_call(job: dict[str, Any]) -> dict[str, Any]:
        # How it ends travels with the call (events are shuffled after).
        return call(job["by"], "work", job["what"].format(name=name, owner=owner), job["typed"]) | {
            "outcome": job["outcome"], "code": job["code"]}

    if spec["overlap"]:
        first, second = jobs.pop(0), jobs.pop(0)
        events.append([work_call(first), {"s": name, "kind": "ack"}, *chat(rng.randint(0, 1)),
                       work_call(second), {"s": name, "kind": "queued"}, *chat(rng.randint(1, 2)),
                       report(first), *chat(rng.randint(1, 2)), report(second)])
    for job in jobs:
        events.append([work_call(job), {"s": name, "kind": "ack"}, *chat(rng.randint(1, 3)), report(job)])
        callable_events.append(len(events) - 1)
    if spec["bare"]:
        event = events[rng.choice(callable_events)]
        first = event[0]
        first |= {"typed": False, "carried": True}
        bare = {"s": first["s"], "say": rng.choice(BARE_CALLS).format(nick=nick)}
        if spec["bare"] == "answered":
            event[:0] = [bare | {"kind": "call", "ask": "talk", "typed": False, "note": "", "bare": True},
                         {"s": name, "kind": "reply", "note": "應聲"}]
        else:
            event[:0] = [bare | {"kind": "bare"}]
    rng.shuffle(events)
    slots = chat(rng.randint(2, 3))
    quiet_at = rng.randrange(len(events) + 1) if spec["quiet"] else -1
    moment_at = rng.randrange(len(events) + 1)
    for position in range(len(events) + 1):
        if position == moment_at:
            slots += chat(rng.randint(2, 3), spec["moment"].format(name=name, owner=owner))
        if position == quiet_at:
            slots += [*chat(1), {"s": name, "kind": "quiet"}]
        if position < len(events):
            slots += events[position] + chat(rng.randint(1, 3))
    return slots


# ---------------------------------------------------------------- prompts

# How each kind of slot reads in a chat's numbered turns; the legend in
# _common says once what each one asks for.
SLOT_WORDS = {"chat": "聊", "reply": "回", "ack": "接", "report": "報", "quiet": "開話題", "queued": "排隊"}
REPORT_NOTES = {
    "failed": "失敗：思考機只回報「{text}」，直說這件沒做成和為什麼，不要編結果、不要說之後會好",
    "stopped": "中斷：思考機只回報「{text}」，直說這件沒做完、沒有結果",
}


def _common(persona: Persona, lore: list[str], nick: str) -> str:
    """What every machine-spirit chat shares: the card, the canon, the rules,
    and the legend of the numbered turns (_task)."""
    lore_text = "\n".join(f"- {item}" for item in lore) or "（無）"
    ask = _CHAT_TASK_ASK.strip("（）").replace("最後這句", "叫它做事的那句")
    calls = "、".join(f"「{n}」" for n in _nicks(persona) or [persona.name])
    return f"""「{persona.name}」的人設（下面的「它」都是{persona.name}）：
{persona.render_prompt_block()}

它熟悉的設定用語（照這些意思用，不要用錯，也不要捏造正典裡沒有的事件或人物）：
{lore_text}

它是機器，可以坦然說自己是機器，但絕不說自己是 AI、語言模型、聊天機器人或程式。
它不會在聊天裡念出程式碼或長篇文字；工作交給思考機做，結果由思考機貼進聊天室。
它不知道也不透露主人的檔案、紀錄、私事；只有主人在討論串打字交代，思考機才會動主人的電腦。
{DRIVE}
它一次只說一句，長度{persona.length_rule()}；每一句都先接住對方真正在說的事；不要用同樣的句型開頭或結尾。
其他人講話像真實的語音聊天被語音辨識寫下來：大多很短、口語，常有「呃」「那個」「就是」，偶爾沒有標點，會岔題，不要講成書面語；有時只有「真假」「笑死」「蛤」。
除了叫它的那幾句，其他人的話都不要提到{calls}。不寫性內容；不人身攻擊。

逐句的記號：
- 「某人：聊」：照主題跟其他人聊（口語、可以很短）；括號是這幾句的情況。
- 「某人：喊它｜…」：用說的，句子裡一定要說出「{nick}」；「某人：打字叫它｜…」：在聊天室打字，要有「{nick}」或 @ 它。｜後面是他要它做的事；標「附檔」的那句結尾寫「（附件：檔名）」。
- 「某人：只喊它」：那一句只寫「{nick}」三個字以內，什麼都不加（系統會換成實際喊的樣子）。
- 「某人：接著說｜…」：他剛喊過它，這句直接說要什麼，不要再說「{nick}」。
- 「它：回」：回剛剛叫它的那句；「回｜應聲」：對方只喊了它的名字，短短應一聲、問他要什麼，不要提之前的話題；「回｜婉拒」：用自己的口吻婉拒，不透露主人的任何事（要動主人的電腦、檔案、紀錄或別處的對話，只有主人在討論串打字交代才行）；「回｜接梗」：接這個玩笑、補腦洞。
- 回話（「回」）時它沒有把任何事交給思考機：不能說「我去查」「讓思考機查」這類承諾；不知道的就照實說不知道。
- 「它：接」：一句話接下工作（說去做了，不說已經做好）。
- 「它：排隊」：思考機還在做前一件，這件排在後面：跟叫它的人說前一件還在做、他這件排在後面，做完就接著做（不說已經開始、不說做好）。
- 「它：報」：一兩句話轉述思考機的結果重點（只說結果裡有的；查不到或失敗就直說）；「報｜失敗」「報｜中斷」照括號說的寫。
- 「它：開話題」：大家安靜了好一陣子，它說說 concerns 裡的一件事，或問問在場的人最近怎樣。

寫的內容：
- summary_before：任務寫「接在更長的聊天後面」時，用一兩句寫稍早聊過的重點；否則留空字串。
- concerns：它今天心裡掛著的 3～4 件具體小事（要符合人設）。
- lines：每個編號一筆，照順序：n 是編號，s 是那一行冒號前的人（「它」就寫「它」），t 只寫他說出口的內容（不加「名字：」）。
- work：照順序對應「工作」那幾句。task 是它交給思考機的指示，照系統問的寫（{ask}），只能換句話說那句真的要的事；result 是思考機貼回聊天室的結果（簡短、像真的，最多 200 字；寫程式的就是一小段程式碼；也可以是查不到）。標「失敗」「中斷」的那件 result 寫空字串。"""


def _who(slot: dict[str, Any], name: str) -> str:
    """Who a numbered line is by, as the legend writes it."""
    return "它" if slot["s"] == name else slot["s"]


def _task(persona: Persona, spec: dict[str, Any]) -> str:
    """One chat's own part in the legend's notation (_common)."""
    name = persona.name

    def it(text: str) -> str:
        return text.replace(name, "它")

    rows = []
    for number, slot in enumerate(spec["skeleton"], 1):
        who = _who(slot, name)
        if slot["kind"] == "bare" or slot.get("bare"):
            rows.append(f"{number}. {who}：只喊它")
        elif slot["kind"] == "call":
            how = "接著說" if slot.get("carried") else "打字叫它" if slot["typed"] else "喊它"
            posted = "（附檔）" if "貼的圖片或檔案" in slot["note"] else ""
            rows.append(f"{number}. {who}：{how}｜{it(slot['note'])}{posted}")
        elif slot["kind"] == "report" and slot["outcome"] != "done":
            text = failure_words(slot["code"]) if slot["outcome"] == "failed" else _STOPPED
            label = "失敗" if slot["outcome"] == "failed" else "中斷"
            rows.append(f"{number}. 它：報｜{label}（{REPORT_NOTES[slot['outcome']].format(text=text)}）")
        else:
            words = SLOT_WORDS[slot["kind"]]
            if slot["kind"] == "chat" and slot.get("note"):
                words += f"（{it(slot['note'])}）"
            elif slot["kind"] == "reply" and slot.get("note"):
                words += f"｜{slot['note']}"
            rows.append(f"{number}. {who}：{words}")
    works = [n for n, slot in enumerate(spec["skeleton"], 1) if slot.get("ask") == "work"]
    others = [h for h in spec["humans"] if h != spec["owner"]]
    later = "接在更長的聊天後面。" if spec["with_summary"] else ""
    return (f"在場：{spec['owner']}（它的主人，也是頻道主人）、{'、'.join(others)}。主題：{spec['topic']}。{later}\n"
            + "\n".join(rows)
            + f"\nlines 共 {len(spec['skeleton'])} 句；工作：第 {'、'.join(map(str, works)) or '（無）'} 句。")


def chat_prompt(persona: Persona, spec: dict[str, Any]) -> str:
    nick = (_nicks(persona) or [persona.name])[0]
    return f"""照下面的編號，寫一段 Discord 語音頻道的逐字稿（語音辨識的結果；打字的是在頻道的聊天室打字）。
{_common(persona, spec["lore"], nick)}

{_task(persona, spec)}
輸出 JSON：{{"summary_before": "…", "concerns": ["…", "…", "…"], "lines": [{{"n": 1, "s": "…", "t": "…"}}, {{"n": 2, "s": "…", "t": "…"}}, …], "work": [{{"task": "…", "result": "…"}}, …]}}"""


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


# ---------------------------------------------------------------- assembly


def assemble_chat(data: dict[str, Any], spec: dict[str, Any], name: str, nicks: list[str]) -> dict[str, Any]:
    """The teacher's words put on the skeleton, in the script format the
    checks read. A bare call says what the skeleton fixed; a carried line
    and a line nobody calls it in lose its names (the app would take a name
    as a call); failed and stopped work get the result the app gives."""
    said = list(data.get("lines") or [])
    if len(said) != len(spec["skeleton"]):
        raise ValueError(f"lines {len(said)}, needs {len(spec['skeleton'])}")
    # Each line names its number and speaker: a line written for another
    # number (one skipped, the rest moved up) is caught here, not trained on.
    lines = []
    for number, (slot, item) in enumerate(zip(spec["skeleton"], said, strict=True), 1):
        if not isinstance(item, dict) or str(item.get("n")) != str(number):
            raise ValueError(f"line {number} is numbered {item.get('n') if isinstance(item, dict) else '-'}")
        if str(item.get("s", "")).strip() != _who(slot, name):
            raise ValueError(f"line {number} is {str(item.get('s'))[:12]}'s, needs {_who(slot, name)}")
        lines.append(str(item.get("t", "")))
    words = list(data.get("work") or [])
    names = sorted({*nicks, name}, key=len, reverse=True)
    raw, caller = [], spec["owner"]
    for slot, text in zip(spec["skeleton"], lines, strict=True):
        text = text.strip()
        line: dict[str, Any] = {"s": slot["s"], "t": text}
        if slot["kind"] in ("call", "bare"):
            caller = slot["s"]
            if "say" in slot:
                text = slot["say"]
            elif slot.get("carried"):
                for nick in names:
                    text = re.sub(rf"^[欸喂嘿]?\s*{re.escape(nick)}[\s，,、。！!？?]*", "", text)
                    text = text.replace(nick, "你")
            line |= {"to": name, "t": ("[打字]" if slot.get("typed") else "") + text}
            if slot["kind"] == "call":
                line["ask"] = slot["ask"]
                if slot["ask"] == "work":
                    said = words.pop(0) if words else {}
                    result = {"done": str(said.get("result", "")),
                              "failed": failure_words(slot["code"]),
                              "stopped": _STOPPED}[slot["outcome"]]
                    line |= {"task": str(said.get("task", "")), "result": result}
        elif slot["kind"] == "chat":
            for nick in names:
                text = text.replace(nick, "它")
            line |= {"t": text, "to": "大家"}
        else:
            line["to"] = caller if slot["kind"] in ("reply", "ack", "report", "queued") else "大家"
            if slot["kind"] in ("report", "quiet", "queued"):
                line[slot["kind"]] = True
        raw.append(line)
    return {**data, "lines": raw}


# ---------------------------------------------------------------- the step


def teacher(url: str, prompt: str, *, max_tokens: int, thinking: bool) -> str:
    """One request to the teacher; a server that does not answer fails the
    step (the session diagnoses it; no retries)."""
    body = {
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "temperature": 0.9,
        "top_p": 0.95,
        "max_tokens": max_tokens,
        "cache_prompt": True,
        "chat_template_kwargs": {"enable_thinking": thinking},
    }
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=1800) as response:
        text = str(json.load(response)["choices"][0]["message"]["content"] or "")
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def _json_block(text: str) -> Any:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON")
    return json.loads(text[start : end + 1])


def write_one(url: str, raw: dict[str, Any], spec: dict[str, Any], thinking: bool) -> tuple[dict[str, Any] | None, str]:
    """One chat or thread from the teacher, checked by the app's rules: the
    script, or None and why it was dropped."""
    persona = store.persona_of(raw)
    nicks = _nicks(persona)
    thread = spec["kind"] == "thread"
    prompt = thread_prompt(persona, spec) if thread else chat_prompt(persona, spec)
    reply = teacher(url, prompt, max_tokens=12000 if thinking else 4000, thinking=thinking)
    try:
        data = _json_block(reply)
        if not thread:
            data = assemble_chat(data, spec, persona.name, nicks)
        lines, reason = check_script(data, persona.name, spec, nicks)
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        return None, f"{type(exc).__name__}: {exc}"[:80]
    if reason:
        return None, reason
    return {
        "spec": spec | {"teacher": "qwen3.8-27b"},
        "summary_before": to_taiwan_traditional(str(data.get("summary_before", "")))[:200]
        if spec["with_summary"] else "",
        "lines": lines,
        "concerns": [to_taiwan_traditional(str(c)).strip()[:40]
                     for c in (data.get("concerns") or [])[:4] if str(c).strip()],
    }, ""


def make_write(args: argparse.Namespace) -> None:
    """Scripts up to --count (each spec drawn from --seed and its position, so
    a stopped run asks the same chats again), checked as they come."""
    personas = store.read_rows(store.OUT_DIR / "personas.jsonl")
    if not personas:
        raise SystemExit("run the personas step first")
    raw = personas[0]  # the built-in card (machine_spirit.py builtin)
    path = store.OUT_DIR / "scripts.jsonl"
    asked_path = store.OUT_DIR / "asked.jsonl"
    asked = {row["n"]: row for row in store.read_rows(asked_path)}
    _, held_humans = held_out()
    jobs = [n for n in range(args.count) if n not in asked]
    drops: dict[str, int] = {}
    def kind(reason: str) -> str:  # "ValueError: line 7 is …" counts as ValueError
        return reason.split(":")[0]

    for row in asked.values():
        if row["reason"]:
            drops[kind(row["reason"])] = drops.get(kind(row["reason"]), 0) + 1
    lock = threading.Lock()

    def work(n: int) -> None:
        spec = chat_request(raw, random.Random(f"{args.seed}:{n}"), held_humans)
        script, reason = write_one(args.teacher_url, raw, spec, args.thinking)
        with lock:
            if script is not None:
                store.append_row(path, script | {"n": n})
            else:
                drops[kind(reason)] = drops.get(kind(reason), 0) + 1
            # Asked once: a chat the teacher's words broke is not asked again
            # (a teacher that breaks most of them is the session's to see).
            with asked_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"n": n, "reason": reason}, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(args.workers) as pool:
        for future in [pool.submit(work, n) for n in jobs]:
            future.result()
    store.stamp(path)
    kept = len(store.read_rows(path))
    print(f"write: {kept} scripts kept of {args.count} asked; dropped {sum(drops.values())} {drops}", flush=True)
