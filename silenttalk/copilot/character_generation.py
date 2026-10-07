from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import replace

from silenttalk.conversation import ConversationTurn
from silenttalk.copilot import reply_templates as templates
from silenttalk.copilot.character_state import (
    STATUSES,
    CharacterState,
    Concern,
    merge_state,
)
from silenttalk.copilot.reply_parsing import _alike_to
from silenttalk.copilot.reply_prompts import _now_words
from silenttalk.copilot.script import to_taiwan_traditional


def parse_state_update(raw: str, state: CharacterState) -> CharacterState:
    """The model's update lines ("進度|2|done|約成了") as a new state; lines
    it could not read are skipped, and anything unmentioned stays as it was."""
    active = state.active_concerns()
    updates: dict[int, tuple[str, str]] = {}
    new: list[str] = []
    views: list[str] = []
    feelings: list[tuple[str, str]] = []
    recent = mood = ""
    for line in raw.splitlines():
        parts = [
            part.strip() for part in re.split(r"[|｜]", line.strip().lstrip("-*• "))
        ]
        if len(parts) < 2 or not parts[1]:
            continue
        tag = parts[0]
        if tag == "進度" and len(parts) >= 3:
            number = re.sub(r"\D", "", parts[1])
            status = parts[2].lower()
            if number and status in STATUSES and 1 <= int(number) <= len(active):
                updates[int(number) - 1] = (status, parts[3] if len(parts) > 3 else "")
        elif tag == "新心事":
            new.append(parts[1])
        elif tag == "看法":
            views.append(parts[1])
        elif tag == "感覺" and len(parts) >= 3 and parts[2]:
            feelings.append((parts[1], to_taiwan_traditional(parts[2])))
        elif tag == "近況":
            recent = parts[1]
        elif tag == "心情":
            mood = parts[1]
    moved = []
    for index, concern in enumerate(active):
        if index in updates:
            status, note = updates[index]
            moved.append(
                Concern(
                    concern.text, status, to_taiwan_traditional(note) or concern.note
                )
            )
        else:
            moved.append(concern)
    return CharacterState(
        concerns=tuple(
            state.finished_concerns()
            + moved
            + [Concern(to_taiwan_traditional(t)) for t in new]
        ),
        recent=to_taiwan_traditional(recent),
        mood=to_taiwan_traditional(mood),
        views=tuple(to_taiwan_traditional(view) for view in views),
        feelings=tuple(feelings),
    )


async def fill_concerns(context, transport, state: CharacterState) -> CharacterState:
    """New concerns for today on top of the ones still open, following on
    from its recent life. Made from the persona and its own state only."""
    sheet = context.persona.render_prompt_block()
    missing = templates._CONCERNS_WANTED - len(state.active_concerns())
    if not sheet or missing <= 0:
        return state
    if context.memory == "off":
        messages = [
            {"role": "system", "content": f"你是下面這個人：\n{sheet}"},
            {"role": "user", "content": templates._AGENDA_ASK},
        ]
    else:
        known = state.prompt_block(full=context.memory == "full")
        messages = [
            {
                "role": "system",
                "content": f"你是下面這個人：\n{sheet}"
                + (f"\n\n{known}" if known else ""),
            },
            {
                "role": "user",
                "content": templates._FILL_ASK.format(now=_now_words(), n=missing),
            },
        ]
    raw = await asyncio.to_thread(
        transport.request_messages, messages, None, 200, False, 0.9
    )
    taken = [c.text for c in state.concerns]
    new: list[Concern] = []
    for line in raw.splitlines():
        item = to_taiwan_traditional(line.strip().lstrip("-*•0123456789.、) ").strip())
        if len(item) >= 4 and not any(_alike_to(item, old, 0.7) for old in taken):
            taken.append(item)
            new.append(Concern(item))
    return replace(state, concerns=state.concerns + tuple(new[:missing])).normalized()


async def update_state(
    context, transport, turns: Sequence[ConversationTurn]
) -> CharacterState:
    """How its life moved on in this stretch of chat: concerns shared,
    progressing, done or dropped; new ones; views it stated; feelings
    about people; recent; mood. In its own words; nothing is quoted."""
    sheet = context.persona.render_prompt_block()
    if not sheet or not turns:
        return context.life
    name = context.persona.name.strip() or "你"
    chat = "\n".join(
        f"{'你（' + name + '）' if turn.is_self else turn.speaker_name}：{turn.text}"
        for turn in turns[-templates._UPDATE_CHAT_TURNS :]
    )
    active = context.life.active_concerns()
    concerns = (
        "\n".join(
            f"{n}. {c.text}（{templates._STATUS_WORDS[c.status]}）"
            for n, c in enumerate(active, 1)
        )
        or "（目前沒有）"
    )
    full = context.memory == "full"
    known = context.life.prompt_block(full=full)
    messages = [
        {
            "role": "system",
            "content": f"你是下面這個人：\n{sheet}" + (f"\n\n{known}" if known else ""),
        },
        {
            "role": "user",
            "content": templates._UPDATE_ASK.format(
                chat=chat,
                concerns=concerns,
                full_lines=templates._UPDATE_FULL_LINES if full else "",
            ),
        },
    ]
    raw = await asyncio.to_thread(
        transport.request_messages, messages, None, 260 if full else 160, False
    )
    update = parse_state_update(raw, context.life)
    if not full:
        update = replace(update, views=(), feelings=())
    return merge_state(context.life, update)


async def summarize(transport, transcript: str, previous: str = "") -> str:
    """Fold an older stretch of chat into a couple of lines, so a long
    session keeps its thread without growing the prompt."""
    system = (
        "你是對話記錄員。把 Discord 語音聊天的一段記錄濃縮成重點，"
        "只寫真的發生過的事。保留人物、尚未結束的話題、約定、決定和專有名詞。"
        "台灣繁體中文，最多六句、320 字以內，不要換行、不要評論、不要加標題。"
    )
    earlier = f"更早的重點：{previous}\n\n" if previous else ""
    prompt = (
        f"{earlier}這段對話：\n{transcript}\n\n"
        "寫成重點（誰在聊什麼、決定了什麼、有什麼還沒結束）："
    )
    raw = await asyncio.to_thread(
        transport.request_completion, system, prompt, None, 640
    )
    text = raw.strip()
    close_index = text.lower().rfind(templates._THINK_CLOSE)
    if close_index >= 0:
        text = text[close_index + len(templates._THINK_CLOSE) :]
    return to_taiwan_traditional(" ".join(text.split()))[: templates._SUMMARY_CHARS]
