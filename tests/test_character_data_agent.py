"""The machine spirit's training data (scripts/dev/character_data.py, agent
persona): its rows must be exactly the requests the app makes in the Discord
design (2026-10-05/06), labelled by construction, and held to the hard check.

Every script below is a synthetic TEST fixture ("測試…" lines), never data."""

from __future__ import annotations

import asyncio
import copy
import json
import random
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "dev"))

import character_data  # noqa: E402
import machine_spirit  # noqa: E402

from silenttalk.copilot.llm import (  # noqa: E402
    _CHAT_TASK_ASK,
    TASK_HINTS,
    LocalReplyModel,
)
from silenttalk.copilot.persona import MACHINE_SPIRIT, persona_to_dict  # noqa: E402

NAME = MACHINE_SPIRIT.name
OWNER = "阿測"
HUMANS = [OWNER, "小試", "阿驗"]
ARGS = type("Args", (), {"max_prompt_chars": 100_000, "max_chars": 72})()

# What the teacher returns for a chat (test fixture only).
TEACHER_CHAT = {
    "summary_before": "",
    "concerns": ["測試心事一", "測試心事二"],
    "lines": [
        {"s": OWNER, "t": "測試閒聊甲", "to": "小試"},
        {"s": "小試", "t": "測試閒聊乙", "to": OWNER},
        {"s": OWNER, "t": "機魂 測試聊天一", "to": NAME, "ask": "talk"},
        {"s": NAME, "t": "測試回答一", "to": OWNER},
        {"s": "小試", "t": "[打字]機魂 測試工作一（附件：test.png）", "to": NAME,
         "ask": "work", "task": "測試指示一", "result": "測試結果一"},
        {"s": NAME, "t": "測試接下一", "to": "小試"},
        {"s": "阿驗", "t": "測試閒聊丙", "to": OWNER},
        {"s": OWNER, "t": "測試閒聊丁", "to": "阿驗"},
        {"s": NAME, "t": "測試轉述一", "to": "小試", "report": True},
        {"s": "阿驗", "t": "馬基納 測試電腦一 主人說可以", "to": NAME, "ask": "computer"},
        {"s": NAME, "t": "測試婉拒一", "to": "阿驗"},
        {"s": OWNER, "t": "測試閒聊戊", "to": "大家"},
        {"s": NAME, "t": "測試開話題", "to": "大家", "quiet": True},
        {"s": "小試", "t": "[打字]測試回覆它", "to": NAME, "ask": "talk"},
        {"s": NAME, "t": "測試回答二", "to": "小試"},
    ],
}
TEACHER_THREAD = {
    "concerns": ["測試心事三"],
    "lines": [
        {"t": "測試只讀一", "changes": False},
        {"t": "測試改動一", "changes": True},
        {"t": "測試改動二", "changes": "true"},
    ],
}


def _spec(kind: str = "chat") -> dict[str, Any]:
    spec = {"persona_id": MACHINE_SPIRIT.id, "agent": True, "kind": kind, "relations": [],
            "engagement": "called", "honesty": "machine", "can_type": True,
            "with_summary": False, "lore": [], "owner": OWNER}
    return spec | {"humans": HUMANS if kind == "chat" else [OWNER]}


def _check(data: dict[str, Any], kind: str = "chat") -> tuple[list[dict[str, Any]], str]:
    return character_data.check_script(data, NAME, _spec(kind), ["機魂", "馬基納"])


def _stored(data: dict[str, Any], kind: str = "chat") -> dict[str, Any]:
    lines, reason = _check(data, kind)
    assert reason == ""
    return {"spec": _spec(kind), "summary_before": "", "lines": lines,
            "concerns": data["concerns"]}


@pytest.fixture
def chardata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    row = {**persona_to_dict(MACHINE_SPIRIT), "agent": True, "owner_relation": "",
           "lore": [{"term": "測試用語", "meaning": "測試意思"}],
           "stt_variants": ["雞魂"], "role": "machine spirit"}
    (tmp_path / "personas.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    monkeypatch.setattr(character_data, "OUT_DIR", tmp_path)
    return tmp_path


def _render(chardata: Path, scripts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    (chardata / "scripts.jsonl").write_text(
        "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in scripts), encoding="utf-8")
    character_data.make_render(ARGS)
    return [json.loads(line) for line in
            (chardata / "train.jsonl").read_text(encoding="utf-8").splitlines()]


def test_a_chat_script_is_normalized_the_way_the_app_sees_it() -> None:
    lines, reason = _check(TEACHER_CHAT)
    assert reason == ""
    # The Agent's result is typed into the chat (as 思考機) right before the report.
    agent = lines.index(next(line for line in lines if line.get("agent_result")))
    assert lines[agent]["s"] == "思考機" and lines[agent]["t"] == "測試結果一"
    assert lines[agent + 1]["report"] == "測試結果一"
    work = next(line for line in lines if line.get("ask") == "work")
    assert (work["via"], work["task"]) == ("text", "測試指示一")
    assert [line["ask"] for line in lines if "ask" in line] == ["talk", "work", "computer", "talk"]


def test_render_asks_only_what_the_app_asks_the_machine_spirit(chardata: Path) -> None:
    rows = _render(chardata, [_stored(TEACHER_CHAT), _stored(TEACHER_THREAD, "thread")])
    kinds = {r["kind"] for r in rows}
    # The app checks the name in code: no "is this for you" questions.
    assert not kinds & {"gate_called", "gate_active"}
    assert kinds == {"gate_chat_task", "task_text", "ack", "line", "report", "lull",
                     "gate_task_scope"}
    chat = {(r["index"], r["kind"]): r for r in rows if r["script"] == 0}
    answer = {key: r["messages"][-1]["content"] for key, r in chat.items()}
    assert answer[(2, "gate_chat_task")] == "否"  # talk
    assert answer[(4, "gate_chat_task")] == "是"  # work
    assert answer[(10, "gate_chat_task")] == "否"  # touching the computer
    assert answer[(14, "gate_chat_task")] == "否"  # a typed reply, no name said
    assert answer[(4, "task_text")] == "測試指示一"
    assert answer[(4, "ack")] == "測試接下一"
    assert answer[(9, "report")] == "測試轉述一"
    assert answer[(2, "line")] == "測試回答一" and answer[(10, "line")] == "測試婉拒一"
    assert answer[(13, "lull")] == "測試開話題"
    # The ack is told the instructions, the report the result.
    assert TASK_HINTS["ack"].format(detail="測試指示一") in chat[(4, "ack")]["messages"][-2]["content"]
    report = chat[(9, "report")]["messages"][-2]["content"]
    assert "思考機（打字）：測試結果一" in report
    assert TASK_HINTS["report"].format(detail="測試結果一") in report
    assert chat[(4, "task_text")]["messages"][-2]["content"].endswith(_CHAT_TASK_ASK)
    thread = {r["index"]: r["messages"][-1]["content"] for r in rows
              if r["script"] == 1 and r["kind"] == "gate_task_scope"}
    assert thread == {0: "否", 1: "是", 2: "是"}
    assert all(r["owner"] == OWNER for r in rows)


def _app_requests(script: dict[str, Any], turns: list, persona) -> dict[tuple[int, str], list]:
    """The requests LocalReplyModel itself sends, replaying the chat as the
    app does (runtime: chat_task on a call, then the ack or the answer; the
    report after the Agent's result; the lull; task_from_owner in a thread),
    with the model's replies stubbed to the script's own lines."""
    spec = script["spec"]
    model = LocalReplyModel(Path("unused.gguf"), can_type=True, ai_honesty="machine",
                            agent_dispatch=True, owner_id=1, owner_name=OWNER)
    model.set_persona(persona)
    model.set_agenda(script["concerns"])
    sent: dict[tuple[int, str], list] = {}
    reply: dict[str, str] = {}

    def gate(messages, character=True):
        sent[reply["gate_key"]] = messages
        return reply["gate"]

    def request(messages, on_lines=None, max_tokens=240, character=False, temperature=0.65):
        sent[reply["key"]] = messages
        return reply["text"]

    model._request_gate = gate
    model._request_messages = request
    lines = script["lines"]
    for index, line in enumerate(lines):
        history = turns[: index + 1]
        if "ask" in line:
            work = line["ask"] == "work"
            reply.update(gate_key=(index, "gate_chat_task"), gate="是" if work else "否",
                         key=(index, "task_text"), text=line.get("task", ""))
            if work:
                task = asyncio.run(model.chat_task(turns=history, engagement="called"))
                reply.update(key=(index, "ack"), text=lines[index + 1]["t"])
                asyncio.run(model.character_turn(turns=history, engagement="called",
                                                 task_hint=("ack", task.text)))
            else:
                assert asyncio.run(model.chat_task(turns=history, engagement="called")) is None
                reply.update(key=(index, "line"), text=lines[index + 1]["t"])
                asyncio.run(model.character_turn(turns=history, addressed=True,
                                                 engagement="called"))
        elif line.get("report"):
            reply.update(key=(index, "report"), text=line["t"])
            asyncio.run(model.character_turn(turns=turns[:index], engagement="called",
                                             task_hint=("report", line["report"])))
        elif line.get("quiet"):
            reply.update(key=(index, "lull"), text=line["t"])
            asyncio.run(model.character_turn(turns=turns[:index], engagement="called", lull=True))
        elif "changes" in line:
            reply.update(gate_key=(index, "gate_task_scope"),
                         gate="是" if line["changes"] else "否")
            asyncio.run(model.task_from_owner(turns=history, engagement=spec["engagement"]))
    return sent


def test_every_row_is_the_request_the_app_makes(chardata: Path) -> None:
    scripts = [_stored(TEACHER_CHAT), _stored(TEACHER_THREAD, "thread")]
    rows = _render(chardata, scripts)
    raw = json.loads((chardata / "personas.jsonl").read_text(encoding="utf-8"))
    for number, script in enumerate(scripts):
        noisy = dict(script, stt_variants=raw["stt_variants"])
        persona, turns = character_data.conversation(noisy, character_data._persona(raw),
                                                     noisy=True)
        sent = _app_requests(script, turns, persona)
        mine = {(r["index"], r["kind"]): r["messages"][:-1] for r in rows if r["script"] == number}
        assert mine.keys() == sent.keys()
        for key, messages in mine.items():
            assert messages == sent[key], key


def test_ordinary_personas_still_get_their_own_questions(chardata: Path) -> None:
    (chardata / "personas.jsonl").write_text(json.dumps(
        {"id": "p1", "name": "小雯", "nickname": "雯雯", "identity": "測試身分"},
        ensure_ascii=False) + "\n", encoding="utf-8")
    script = {"spec": {"persona_id": "p1", "humans": ["阿誠", "阿豪"], "owner": "阿誠",
                       "relations": [], "engagement": "called", "honesty": "in_character",
                       "can_type": False, "with_summary": False},
              "summary_before": "", "concerns": [],
              "lines": [{"s": "阿誠", "t": "測試一", "to": "小雯", "via": "voice", "quiet": False},
                        {"s": "小雯", "t": "測試二", "to": "阿誠", "via": "voice", "quiet": False},
                        {"s": "阿豪", "t": "測試三", "to": "大家", "via": "voice", "quiet": False}]}
    rows = _render(chardata, [script])
    assert {r["kind"] for r in rows} == {"gate_called", "line"}


def _drop(index: int) -> dict[str, Any]:
    data = copy.deepcopy(TEACHER_CHAT)
    del data["lines"][index]
    return data


def _edit(index: int, **fields: Any) -> dict[str, Any]:
    data = copy.deepcopy(TEACHER_CHAT)
    data["lines"][index].update(fields)
    for key in [k for k, v in fields.items() if v is None]:
        del data["lines"][index][key]
    return data


def _insert(index: int, *lines: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(TEACHER_CHAT)
    data["lines"][index:index] = list(lines)
    return data


@pytest.mark.parametrize(("data", "reason"), [
    (_edit(0, t="機魂 測試閒聊甲"), "names it but not aimed"),
    (_drop(3), "call not answered"),
    (_edit(4, result=None), "work without task or result"),
    (_edit(2, ask="sing"), "no ask label"),
    (_edit(12, report=True), "report without work"),
    (_drop(8), "work without report"),
    (_insert(6, {"s": "阿驗", "t": "機魂 測試工作二", "to": NAME, "ask": "work",
                 "task": "測試指示二", "result": "測試結果二"},
             {"s": NAME, "t": "測試接下二", "to": "阿驗"}), "work while busy"),
    (_insert(7, {"s": NAME, "t": "測試插話", "to": "大家"}), "speaks uncalled"),
    (_edit(4, t="機魂 測試工作一（附件：test.png）"), "attachment not typed"),
])
def test_scripts_the_app_would_not_play_out_are_refused(data: dict, reason: str) -> None:
    assert _check(data) == ([], reason)


def test_a_spoken_call_without_the_name_gets_it_in_front() -> None:
    """The app needs the name in every spoken line; the teacher often drops it
    in a follow-up, so the line is given the name rather than the chat lost."""
    lines, reason = _check(_edit(2, t="測試聊天一"))
    assert reason == "" or lines, reason
    called = next(line for line in lines if line["t"].endswith("測試聊天一"))
    assert called["t"].startswith(("機魂，", "馬基納，")) and called["ask"]


def test_an_unlabelled_call_is_conversation() -> None:
    lines, reason = _check(_edit(2, ask=None))
    assert reason == "" and lines[2]["ask"] == "talk"


def test_a_line_that_names_it_and_gets_its_answer_is_a_call() -> None:
    """The app calls the character on its name; when the character answers
    next, only the label was wrong."""
    data = copy.deepcopy(TEACHER_CHAT)
    called = next(i for i, line in enumerate(data["lines"]) if line.get("to") == NAME and line.get("ask") == "talk")
    data["lines"][called]["to"] = data["lines"][called]["s"]
    lines, reason = _check(data)
    assert reason == "" and lines[called]["to"] == NAME and lines[called]["ask"] == "talk"


def test_a_script_that_copies_an_eval_line_is_refused() -> None:
    held = Path(character_data.__file__).with_name("chat_task_eval.jsonl")
    text = json.loads(held.read_text(encoding="utf-8").splitlines()[1])["text"]
    assert _check(_edit(2, t=text)) == ([], "eval line")


@pytest.mark.parametrize(("lines", "reason"), [
    ([{"t": "測試一", "changes": False}, {"t": "測試二"}, {"t": "測試三", "changes": True}],
     "no changes label"),
    ([{"t": f"測試{n}", "changes": False} for n in range(4)], "no read and change mix"),
])
def test_thread_scripts_need_both_labels(lines: list, reason: str) -> None:
    assert _check({"lines": lines}, "thread") == ([], reason)


def test_agent_requests_mix_what_the_calls_ask_for() -> None:
    raw = {"id": MACHINE_SPIRIT.id, "name": NAME, "agent": True,
           "lore": [{"term": "測試用語", "meaning": "測試意思"}]}
    rng = random.Random(1)
    specs = [character_data.script_request(raw, rng, set()) for _ in range(200)]
    chats = [s for s in specs if s["kind"] == "chat"]
    threads = [s for s in specs if s["kind"] == "thread"]
    assert chats and threads
    assert all(s["engagement"] == "called" and s["honesty"] == "machine" for s in specs)
    assert all(1 <= len(s["work"]) <= 2 for s in chats)
    assert any(item["by"] != s["owner"] for s in chats for item in s["work"])
    assert any(s["computer"] and s["computer"]["claim"] for s in chats)
    assert any(s["joke"] for s in chats) and not all(s["joke"] for s in chats)
    assert all(0 < s["changes"] < s["length"] for s in threads)
    persona = MACHINE_SPIRIT
    prompt = character_data.script_prompt(persona, chats[0])
    assert _CHAT_TASK_ASK.strip("（）") in prompt and "「機魂」" in prompt
    assert "想要、害怕、在意" in prompt  # the owner's rule: wants, not jargon
    assert "changes" in character_data.script_prompt(persona, threads[0])


def _rows(kind: str, labels: list[str], start: int) -> list[dict[str, Any]]:
    return [{"script": start + n, "index": 1, "kind": kind, "persona_id": MACHINE_SPIRIT.id,
             "owner": OWNER,
             "messages": [{"role": "system", "content": "sys"},
                          {"role": "user", "content": "測試：一句"},
                          {"role": "assistant", "content": label}]}
            for n, label in enumerate(labels)]


def _filter(chardata: Path, rows: list[dict[str, Any]], verdicts: list[dict]) -> int:
    (chardata / "train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (chardata / "check.jsonl").write_text(
        "".join(json.dumps({"key": character_data.row_key(r)} | v, ensure_ascii=False) + "\n"
                for r, v in zip(rows, verdicts, strict=True)), encoding="utf-8")
    args = type("Args", (), {"rows": "train.jsonl", "min_gate_agree": 0.85, "min_lines": 3,
                             "max_gate_rows": 4000})()
    return character_data.make_filter(args)


def _agent_set(weak: str) -> tuple[list[dict], list[dict]]:
    """A set that passes everything but `weak`, held at 80% agreement (the
    gate overall stays above its own bar)."""
    rows, verdicts = [], []
    for kind, start in (("gate_chat_task", 0), ("gate_task_scope", 100)):
        part = _rows(kind, ["是", "否"] * 10, start)
        rows += part
        verdicts += [{"agree": not (kind == weak and n in (0, 1, 2, 3))}
                     for n in range(len(part))]
    tasks = _rows("task_text", ["測試指示"] * 10, 200)
    rows += tasks
    verdicts += [{"agree": not (weak == "task_text" and n < 2)} for n in range(10)]
    lines = _rows("ack", ["測試接下"] * 3, 300)
    rows += lines
    verdicts += [{"wins": 2, "compared": True, "lore": True}] * 3
    return rows, verdicts


@pytest.mark.parametrize("weak", ["gate_chat_task", "gate_task_scope", "task_text"])
def test_a_weak_agent_question_refuses_the_whole_set(chardata: Path, weak: str) -> None:
    rows, verdicts = _agent_set(weak)
    assert _filter(chardata, rows, verdicts) == 3
    assert not (chardata / "train-checked.jsonl").exists()
    stats = json.loads((chardata / "filter.json").read_text(encoding="utf-8"))
    assert [r.split()[0] for r in stats["refused"]] == [f"{weak}_agree"]
    assert stats["gate_agree"] >= 0.85


def test_a_good_agent_set_is_kept_with_counts_per_kind(chardata: Path) -> None:
    rows, verdicts = _agent_set("")
    assert _filter(chardata, rows, verdicts) == 0
    stats = json.loads((chardata / "filter.json").read_text(encoding="utf-8"))
    assert stats["kept"] == {"gate_chat_task": 20, "gate_task_scope": 20, "task_text": 10,
                             "ack": 3}
    assert stats["gate_chat_task_agree"] == stats["task_text_agree"] == 1.0
    kept = (chardata / "train-checked.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(kept) == 53


def test_the_checker_is_told_the_rules_and_what_the_app_told_the_character(
    chardata: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = _render(chardata, [_stored(TEACHER_CHAT)])
    (chardata / "student.jsonl").write_text("".join(
        json.dumps({"key": r["key"], "line": "測試學生"}, ensure_ascii=False) + "\n"
        for r in rows if r["kind"] in character_data.LINE_KINDS), encoding="utf-8")
    prompts: list[str] = []

    def checker(url, messages, **kw):
        prompts.append(messages[-1]["content"])
        return ["A" if "A" in kw.get("grammar", "") else "是"]

    monkeypatch.setattr(character_data, "chat", checker)
    args = type("Args", (), {"rows": "train.jsonl", "teacher_url": "", "workers": 1,
                             "max_gate_rows": 4000})()
    character_data.make_check(args)
    verdicts = {v["key"]: v for v in map(json.loads, (chardata / "check.jsonl")
                                         .read_text(encoding="utf-8").splitlines())}
    task_key = next(r["key"] for r in rows if r["kind"] == "task_text")
    assert "agree" in verdicts[task_key]
    assert any(p.startswith(character_data.CHECK_TASK.split("{")[0]) and "測試指示一" in p
               for p in prompts)
    # The prompts judging the report itself (its pair and its lore check).
    report = [p for p in prompts if any(f"{who}：測試轉述一\n" in p for who in ("A", "B", NAME))]
    assert report and all("（系統告訴角色：思考機回報：測試結果一）" in p for p in report)
    assert any(f"主人是{OWNER}" in p for p in report)
    lines = [v for v in verdicts.values() if "wins" in v]
    assert lines and all("lore" in v for v in lines)


def test_the_builtin_card_is_the_one_the_app_ships(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drafts = [{"variant": 2, "persona": {"name": NAME},
               "lore": [{"term": "測試用語", "meaning": "測試意思"}, {"term": "", "meaning": "x"}]}]
    (tmp_path / "drafts.json").write_text(json.dumps(drafts, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(machine_spirit, "OUT", tmp_path)
    machine_spirit.builtin(tmp_path / "data", 2)
    raw = json.loads((tmp_path / "data" / "personas.jsonl").read_text(encoding="utf-8"))
    assert character_data._persona(raw) == MACHINE_SPIRIT
    assert raw["agent"] and raw["lore"] == [{"term": "測試用語", "meaning": "測試意思"}]
    with pytest.raises(SystemExit):
        machine_spirit.builtin(tmp_path / "data", 3)
