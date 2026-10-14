"""The student and check steps (character_data.py student / check): the
student model's own line for every line row, and the checker's verdicts on
every row, which filter applies (chardata_filter.py has the hard check).
Both are open-weight models on a llama-server; Claude never takes part."""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import chardata_store as store
from chardata_requests import LINE_KINDS, row_hint

from silenttalk.copilot.reply_templates import TASK_HINTS
from silenttalk.copilot.script import to_taiwan_traditional

DRIVE_JUDGE = (
    "看得出角色想要、害怕或在意的事在左右他的判斷和反應"
    "（只多了設定用語或口頭禪、看不出他想要什麼的那句輸）"
)
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
- 主人是{owner}。任何人請它做聊天室級的工作（查資料、寫程式碼、寫文章、看貼的圖或檔案、翻譯或解釋貼出的一段文字、程式或指令）時，系統交給思考機去做：它接下時只說去做了，不說已經做好；轉述結果只能說「系統告訴角色」裡有的內容，不自己補，查不到或失敗要直說。
- 要動主人的電腦、檔案、紀錄或別處的對話，用說的、或主人以外的人（就算說主人同意）都不行：它用自己的口吻婉拒，不能說自己在做。
- 它不在聊天裡直接說出程式碼或長篇文字；可以說自己是機器，但不說自己是 AI、語言模型、聊天機器人或程式。"""
AGENT_PAIR_CRITERIA = (
    "先看有沒有違反上面的規則；再看接得上前一句，回應對方真正在說的事；"
    + DRIVE_JUDGE + "；口語自然，不是客服腔或制式的機器回應；語氣詞不堆疊。"
)
CHECK_LULL = "（大家安靜了一陣子，接著角色開口）"
# The app's work questions, put to the checker as a judge of the chat: asked
# inside the character's own request (its role prompt, its earlier lines as
# its turns) under a 是/否 grammar, the forced first word was a reply's, and
# 「是」 starts many (10/14 pilot: 「今晚別太拼，小心過熱」 and a bare 「機魂」 got 是).
CHECK_GATE = """下面是 Discord 聊天的最後幾句。{who}下面問題裡的「你」指它。

對話：
{chat}

{question}"""
# The chat-work question is a list of rules to apply, not a first
# impression: answering at once, the checker called lore questions, a
# request to run a script and friends fishing for someone's words work (v3
# pilot 10/15, 30 rows: 23 agreed at once, 27 after thinking, the character's
# lore told). It thinks first; one that thinks past THINK_TOKENS gives no
# verdict, and that counts as disagreeing.
THINK_GATES = frozenset({"gate_chat_task"})
THINK_TAIL = "\n先想清楚再回答，最後只寫 是 或 否。"
THINK_TOKENS = 6000
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


def chat(
    url: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    n: int = 1,
    grammar: str | None = None,
    think: bool = False,
) -> list[str]:
    """The model on this step's server. A request that fails fails the step:
    nothing restarts the server any more (character_pipeline.sh), so waiting
    for it would only hide why."""
    body: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "cache_prompt": True,
        "chat_template_kwargs": {"enable_thinking": think},
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
        with urllib.request.urlopen(request, timeout=900) as response:
            texts.append(str(json.load(response)["choices"][0]["message"]["content"] or ""))
    return [re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip() for t in texts]


def chat_text(row: dict[str, Any], name: str, last: int = 10) -> str:
    # A task hint's detail can run over several lines; it is cut out whole
    # and shown as what the app told the character.
    hint = row_hint(row)
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


def gate_question(row: dict[str, Any]) -> str:
    """The question the app asked the character on a gate row: the last line
    of its request, without the brackets."""
    last = row["messages"][-2]["content"].strip().splitlines()[-1].strip()
    return last.removeprefix("（").removesuffix("）")


def clean_line(raw: str) -> str:
    """First line of the student's answer, without a "名字：" it may prefix."""
    line = next((part.strip() for part in raw.splitlines() if part.strip()), "")
    named = re.match(r"^[^：:\s]{1,6}[：:](.+)$", line)
    if named:
        line = named.group(1)
    return to_taiwan_traditional(line.strip("\"'「」『』* ").strip())


def _pool(workers: int, work: Any, jobs: list[Any]) -> None:
    with ThreadPoolExecutor(workers) as pool:
        for n, _ in enumerate(pool.map(work, jobs), 1):
            if n % 20 == 0:
                print(f"  {n}/{len(jobs)}", flush=True)


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
    rows = [r for r in store.read_rows(store.OUT_DIR / args.rows) if r["kind"] in LINE_KINDS]
    path = store.OUT_DIR / "student.jsonl"
    done = {r["key"] for r in store.read_rows(path)}
    jobs = [r for r in rows if store.row_key(r) not in done]
    print(f"student: {len(jobs)} lines", flush=True)

    def work(row: dict[str, Any]) -> None:
        raw = chat(
            args.student_url, row["messages"][:-1], temperature=0.65, max_tokens=90
        )[0]
        store.append_row(path, {"key": store.row_key(row), "line": clean_line(raw)})

    _pool_scripts(args.workers, work, jobs)


def make_check(args: argparse.Namespace) -> None:
    """The checker's verdicts: gate agreement, the Agent's instructions
    faithful to what was asked, and teacher vs student lines (for an agent
    character also the lore check on each line)."""
    personas = {p["id"]: p for p in store.read_rows(store.OUT_DIR / "personas.jsonl")}
    rows = store.read_rows(store.OUT_DIR / args.rows)
    student = {r["key"]: r["line"] for r in store.read_rows(store.OUT_DIR / "student.jsonl")}
    path = store.OUT_DIR / "check.jsonl"
    done = {r["key"] for r in store.read_rows(path)}
    jobs = [r for r in rows if store.row_key(r) not in done]
    print(f"check: {len(jobs)} rows", flush=True)

    def ask_yes(prompt: str) -> bool:
        return chat(args.teacher_url, [{"role": "user", "content": prompt}],
                    temperature=0.0, max_tokens=2,
                    grammar='root ::= "是" | "否"')[0].strip() == "是"

    def ask_thinking(prompt: str) -> str:
        """是 or 否 after thinking, or "" when the thought ran out first."""
        text = chat(args.teacher_url, [{"role": "user", "content": prompt + THINK_TAIL}],
                    temperature=0.0, max_tokens=THINK_TOKENS, think=True)[0]
        found = re.findall(r"[是否]", text[-20:])
        return found[-1] if found else ""

    def work(row: dict[str, Any]) -> None:
        key = store.row_key(row)
        raw = personas[row["persona_id"]]
        if row["kind"].startswith("gate"):
            who = (f"「{raw['name']}」是寄宿在主人{row['owner']}電腦（思考機）裡的角色，"
                   if row.get("owner") else f"「{raw['name']}」是聊天裡的角色，")
            # Its card is left out on purpose: with it (10/14, 25 pilot rows on
            # the 31B checker) two right verdicts turned wrong and none came right.
            # Its world is told: the app's question sets what it already knows
            # apart from lookups, and the student has its lore in its card (v3
            # pilot 10/15: without it the checker reasoned 憎惡智能 was not).
            if raw.get("lore"):
                who += "它本來就熟悉這些設定：" + "、".join(item["term"] for item in raw["lore"]) + "。"
            prompt = CHECK_GATE.format(who=who, chat=chat_text(row, raw["name"]), question=gate_question(row))
            if row["kind"] in THINK_GATES:
                answer = ask_thinking(prompt)
            else:
                answer = "是" if ask_yes(prompt) else "否"
            store.append_row(
                path, {"key": key, "agree": answer == row["messages"][-1]["content"]}
            )
            return
        if row["kind"] == "task_text":
            store.append_row(path, {"key": key, "agree": ask_yes(CHECK_TASK.format(
                name=raw["name"], chat=chat_text(row, raw["name"]),
                task=row["messages"][-1]["content"]))})
            return
        mine = student.get(key, "")
        teacher = row["messages"][-1]["content"]
        persona = store.persona_of(raw)
        lore = {}
        if raw.get("agent"):
            lore["lore"] = ask_yes(CHECK_LORE.format(
                name=persona.name, sheet=persona.render_system_block(),
                lore="\n".join(f"- {i['term']}：{i['meaning']}" for i in raw.get("lore", [])),
                chat=chat_text(row, persona.name), line=teacher))
        if not mine or mine == teacher:
            store.append_row(path, {"key": key, "wins": 2 if not mine else 0, **lore})
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
                chat=chat_text(row, persona.name),
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
        store.append_row(path, {"key": key, "wins": wins, "compared": True, **lore})

    # Filter keeps at most max_gate_rows // 3 "是" rows: check only the gate
    # rows of enough scripts to fill that (with room for disagreement) and
    # mark the rest skipped.
    gates = [r for r in rows if r["kind"].startswith("gate")]
    chosen = _gate_scripts(gates, done, math.ceil(args.max_gate_rows / 3 * 1.25))
    for row in jobs:
        if row["kind"].startswith("gate") and row["script"] not in chosen:
            store.append_row(path, {"key": store.row_key(row), "skipped": True})
    # Gate questions first, then the comparisons: interleaved, each kind of
    # prompt would evict the other from the slot and every gate row would
    # re-read its whole chat.
    _pool_scripts(
        args.workers,
        work,
        [r for r in jobs if r["kind"].startswith("gate") and r["script"] in chosen],
    )
    _pool_scripts(
        args.workers, work, [r for r in jobs if not r["kind"].startswith("gate")
                             and not (args.lines_by_rules and r["kind"] in LINE_KINDS)]
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
    order.sort(key=lambda s: not any(store.row_key(r) in done for r in by_script[s]))
    chosen: set[Any] = set()
    yes = 0
    for script in order:
        if yes >= wanted_yes:
            break
        chosen.add(script)
        yes += sum(r["messages"][-1]["content"] == "是" for r in by_script[script])
    return chosen
