from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from silenttalk.config import CopilotConfig
from silenttalk.copilot.character_state import (
    CharacterState,
    CharacterStateStore,
    Concern,
)
from silenttalk.copilot.persona import EXAMPLE_PERSONAS
from silenttalk.copilot.runtime import CopilotRuntime
from silenttalk.copilot.types import VOICE_ROOM, ConversationTurn, ReplySuggestions


class SlowFakeLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.release = asyncio.Event()
        # What character_turn answers; "" means the model chose SKIP.
        self.character_line = "收到"
        self.owner_name = ""
        self.state = CharacterState()
        self.agenda = ()
        # The conversation each character_turn was given.
        self.turns_seen: list[list[str]] = []

    def set_agent_dispatch(self, enabled: bool) -> None:
        self.agent_dispatch = enabled

    async def fill_concerns(self, state):
        return state

    def set_state(self, state):
        self.state = state

    def set_owner(self, user_id: int, name: str) -> None:
        self.owner_name = name

    def set_report_public(self, public: bool) -> None:
        self.report_public = public

    async def suggest(
        self, *, turns, summary: str = "", trigger_speaker: str, trigger_text: str,
        on_partial=None,
    ) -> ReplySuggestions:
        self.calls.append(trigger_text)
        await self.release.wait()
        self.release.clear()
        return ReplySuggestions(trigger_speaker, trigger_text, agree="好")

    def set_persona(self, persona: object) -> None:
        pass

    def set_max_reply_chars(self, value: int) -> None:
        pass

    def set_ai_honesty(self, mode: str) -> None:
        pass

    async def summarize(self, transcript: str, previous: str = "") -> str:
        self.calls.append(("summarize", transcript.count("\n") + 1, previous))
        return "稍早在聊晚餐"

    async def character_turn(
        self, *, turns, summary: str, addressed: bool, engagement: str
    ) -> str:
        newest = next(turn.text for turn in reversed(turns) if not turn.is_self)
        self.calls.append(("character", newest, addressed, engagement))
        self.turns_seen.append([turn.text for turn in turns])
        await self.release.wait()
        self.release.clear()
        return self.character_line


async def _runtime(
    tmp_path: Path, *, text: bool = False, config: CopilotConfig | None = None
) -> tuple[CopilotRuntime, SlowFakeLLM, list]:
    delivered: list[ReplySuggestions | ConversationTurn | str] = []
    runtime = CopilotRuntime(
        tmp_path,
        config or CopilotConfig(),
        owner_user_id=1,
        on_suggestions=delivered.append,
        on_error=lambda _: None,
        on_turn=delivered.append,
        on_character_line=lambda line: delivered.append(("spoke", line)),
        on_character_text=(
            (lambda line, place: delivered.append(
                ("typed", line) if place == VOICE_ROOM else ("typed", line, place)
            )) if text else None
        ),
    )
    llm = SlowFakeLLM()
    runtime._llm = llm  # type: ignore[assignment]
    runtime._loop = asyncio.get_running_loop()
    runtime._wake = asyncio.Event()
    runtime._worker = asyncio.create_task(runtime._suggestion_worker())
    return runtime, llm, delivered


async def _stop(runtime: CopilotRuntime) -> None:
    worker = runtime._worker
    assert worker is not None
    worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_busy_chat_generates_only_for_newest_line(tmp_path: Path) -> None:
    runtime, llm, delivered = await _runtime(tmp_path)
    runtime._handle_turn(2, "A", "第一句話")
    await _settle()
    runtime._handle_turn(3, "B", "第二句話")
    runtime._handle_turn(2, "A", "第三句話")
    llm.release.set()
    await _settle()
    llm.release.set()
    await _settle()

    assert llm.calls == ["第一句話", "第三句話"]
    suggestions = [item for item in delivered if isinstance(item, ReplySuggestions)]
    assert [item.trigger_text for item in suggestions] == ["第一句話", "第三句話"]
    turns = [item.text for item in delivered if isinstance(item, ConversationTurn)]
    assert turns == ["第一句話", "第二句話", "第三句話"]
    await _stop(runtime)


@pytest.mark.asyncio
async def test_filler_words_join_context_without_triggering(tmp_path: Path) -> None:
    runtime, llm, _ = await _runtime(tmp_path)
    runtime._handle_turn(2, "A", "嗯")
    await _settle()

    assert llm.calls == []
    assert [turn.text for turn in runtime._context(VOICE_ROOM).snapshot()] == ["嗯"]
    assert runtime.regenerate() is False
    await _stop(runtime)


@pytest.mark.asyncio
async def test_regenerate_targets_newest_line(tmp_path: Path) -> None:
    runtime, llm, _ = await _runtime(tmp_path)
    runtime._handle_turn(2, "A", "要不要打排位")
    await _settle()
    llm.release.set()
    await _settle()

    assert runtime.regenerate() is True
    await _settle()
    llm.release.set()
    await _settle()

    assert llm.calls == ["要不要打排位", "要不要打排位"]
    await _stop(runtime)


async def _character_runtime(tmp_path: Path) -> tuple[CopilotRuntime, SlowFakeLLM, list]:
    runtime, llm, delivered = await _runtime(tmp_path)
    runtime.set_persona(EXAMPLE_PERSONAS[0])  # 凱哥
    runtime.set_character_mode(True)
    return runtime, llm, delivered


@pytest.mark.asyncio
async def test_character_speaks_what_the_model_says(tmp_path: Path) -> None:
    runtime, llm, delivered = await _character_runtime(tmp_path)
    runtime._handle_turn(2, "阿傑", "凱哥你覺得呢")
    await _settle()
    llm.release.set()
    await _settle()

    assert llm.calls == [("character", "凱哥你覺得呢", False, "called")]
    assert ("spoke", "收到") in delivered
    assert not any(isinstance(item, ReplySuggestions) for item in delivered)
    await _stop(runtime)


@pytest.mark.asyncio
async def test_character_stays_quiet_when_the_model_skips(tmp_path: Path) -> None:
    """No keyword gate in front of the model: it sees every line, including
    ones that only mention the character, and decides for itself."""
    runtime, llm, delivered = await _character_runtime(tmp_path)
    llm.character_line = ""
    runtime._handle_turn(2, "阿傑", "我剛才跟阿凱講話")
    await _settle()
    llm.release.set()
    await _settle()

    assert llm.calls == [("character", "我剛才跟阿凱講話", False, "called")]
    assert not any(isinstance(item, tuple) and item[0] == "spoke" for item in delivered)
    await _stop(runtime)


@pytest.mark.asyncio
async def test_character_sees_its_own_lines_and_the_engagement_setting(
    tmp_path: Path,
) -> None:
    runtime, llm, _ = await _character_runtime(tmp_path)
    runtime.apply_settings({"character_engagement": "active"})
    runtime.record_self("我先講一句")
    runtime._handle_turn(2, "阿傑", "我剛剛吃了拉麵")
    await _settle()

    assert llm.calls == [("character", "我剛剛吃了拉麵", False, "active")]
    turns = runtime._context(VOICE_ROOM).snapshot()
    assert [(turn.text, turn.is_self) for turn in turns] == [
        ("我先講一句", True),
        ("我剛剛吃了拉麵", False),
    ]
    llm.release.set()
    await _settle()
    await _stop(runtime)


@pytest.mark.asyncio
async def test_a_discord_mention_is_passed_on_as_addressed(tmp_path: Path) -> None:
    runtime, llm, _ = await _character_runtime(tmp_path)
    runtime._handle_turn(2, "阿傑", "你覺得呢", "text", True)
    await _settle()

    assert llm.calls == [("character", "你覺得呢", True, "called")]
    llm.release.set()
    await _settle()
    await _stop(runtime)


@pytest.mark.asyncio
async def test_owner_mic_counts_only_in_character_mode(tmp_path: Path) -> None:
    runtime, _, _ = await _runtime(tmp_path)
    packets: list[tuple[int, str, bytes]] = []
    runtime._stt.push_pcm = lambda *packet: packets.append(packet)  # type: ignore[method-assign]
    runtime.accept_pcm(1, "Owner", b"options")
    runtime._handle_turn(1, "Owner", "我在講話")
    assert packets == []
    assert "我在講話" not in [turn.text for turn in runtime._context(VOICE_ROOM).snapshot()]

    runtime.set_persona(EXAMPLE_PERSONAS[0])
    runtime.set_character_mode(True)
    runtime.accept_pcm(1, "Owner", b"character")
    runtime._handle_turn(1, "Owner", "凱哥你好")
    assert packets == [(1, "Owner", b"character")]
    assert "凱哥你好" in [turn.text for turn in runtime._context(VOICE_ROOM).snapshot()]
    await _stop(runtime)


@pytest.mark.asyncio
async def test_character_drops_a_reply_once_the_chat_moved_on(tmp_path: Path) -> None:
    runtime, llm, delivered = await _character_runtime(tmp_path)
    runtime._handle_turn(2, "阿傑", "晚餐要吃什麼")
    await _settle()
    runtime._handle_turn(3, "小雨", "我要吃拉麵")
    runtime._handle_turn(2, "阿傑", "好啊那走")
    llm.release.set()
    await _settle()

    assert llm.calls[0] == ("character", "晚餐要吃什麼", False, "called")
    assert ("spoke", "收到") not in delivered  # the chat moved on while thinking
    await _stop(runtime)


@pytest.mark.asyncio
async def test_typed_lines_are_answered_by_typing(tmp_path: Path) -> None:
    runtime, llm, delivered = await _runtime(tmp_path, text=True)
    runtime.set_persona(EXAMPLE_PERSONAS[0])
    runtime.set_character_mode(True)
    runtime._handle_turn(2, "阿傑", "凱哥你在嗎", "text")
    await _settle()
    llm.release.set()
    await _settle()

    assert ("typed", "收到") in delivered
    assert not any(item[0] == "spoke" for item in delivered if isinstance(item, tuple))
    turns = [item for item in delivered if isinstance(item, ConversationTurn)]
    assert [turn.via for turn in turns] == ["text"]
    await _stop(runtime)


@pytest.mark.asyncio
async def test_a_thread_is_its_own_conversation_answered_in_the_thread(tmp_path: Path) -> None:
    """A thread the bot opened is a separate conversation: the character is
    given only that thread's lines, answers by typing there, and the voice
    room neither hears it nor counts it as talk (no lull reset)."""
    runtime, llm, delivered = await _runtime(tmp_path, text=True)
    runtime.set_persona(EXAMPLE_PERSONAS[0])
    runtime.set_character_mode(True)
    runtime._handle_turn(2, "阿傑", "今天好熱喔")
    heard = runtime._last_heard_at
    runtime._handle_turn(3, "小綠", "幫我想個團名", "text", True, place=777, channel_id=777, message_id=9)
    assert runtime._last_heard_at == heard
    await _settle()
    llm.release.set()  # the voice room spoke first
    await _settle()
    llm.release.set()
    await _settle()

    assert ("spoke", "收到") in delivered and ("typed", "收到", 777) in delivered
    assert llm.turns_seen == [["今天好熱喔"], ["幫我想個團名"]]
    runtime.record_self("收到", 777, via="text")  # what the controller does once it is sent
    assert [t.text for t in runtime._context(777).snapshot()] == ["幫我想個團名", "收到"]
    assert [t.text for t in runtime._context(VOICE_ROOM).snapshot()] == ["今天好熱喔"]
    turns = [item for item in delivered if isinstance(item, ConversationTurn)]
    assert [(t.place, t.via, t.is_self) for t in turns] == [
        (VOICE_ROOM, "voice", False), (777, "text", False), (777, "text", True)]
    await _stop(runtime)


@pytest.mark.asyncio
async def test_newer_lines_replace_older_ones_only_within_their_own_place(tmp_path: Path) -> None:
    runtime, llm, _ = await _runtime(tmp_path, text=True)
    runtime.set_persona(EXAMPLE_PERSONAS[0])
    runtime.set_character_mode(True)
    runtime._handle_turn(2, "阿傑", "第一句")  # being answered
    await _settle()
    runtime._handle_turn(2, "阿傑", "第二句")
    runtime._handle_turn(3, "小綠", "串裡一句", "text", True, place=777)
    runtime._handle_turn(2, "阿傑", "第三句")  # replaces 第二句, keeps its turn in line
    assert list(runtime._pending) == [VOICE_ROOM, 777]
    for _ in range(3):
        llm.release.set()
        await _settle()
    assert [call[1] for call in llm.calls] == ["第一句", "第三句", "串裡一句"]
    await _stop(runtime)


@pytest.mark.asyncio
async def test_only_the_most_recent_threads_are_kept(tmp_path: Path) -> None:
    runtime, _, _ = await _runtime(tmp_path)
    runtime.set_character_mode(True)
    for place in range(1, 18):
        runtime._handle_turn(2, "阿傑", "嗨嗨", "text", place=place)
    runtime._handle_turn(2, "阿傑", "第一個串又有人說話", "text", place=1)
    runtime._handle_turn(2, "阿傑", "嗨嗨", "text", place=18)
    threads = [place for place in runtime._contexts if place != VOICE_ROOM]
    assert threads == [*range(4, 18), 1, 18]  # 2 and 3 were quiet the longest
    await _stop(runtime)


@pytest.mark.asyncio
async def test_typed_lines_fall_back_to_speech_when_text_is_off(tmp_path: Path) -> None:
    runtime, llm, delivered = await _runtime(tmp_path)  # no on_character_text
    runtime.set_persona(EXAMPLE_PERSONAS[0])
    runtime.set_character_mode(True)
    runtime._handle_turn(2, "阿傑", "凱哥你在嗎", "text")
    await _settle()
    llm.release.set()
    await _settle()

    assert ("spoke", "收到") in delivered
    await _stop(runtime)


@pytest.mark.asyncio
async def test_a_long_session_is_compacted_instead_of_truncated(tmp_path: Path) -> None:
    """Uninterrupted chat: old turns become a summary, recent ones stay
    verbatim, and the prompt stops growing."""
    runtime, llm, _ = await _runtime(
        tmp_path,
        config=CopilotConfig(compact_keep_turns=6, compact_batch_turns=6),
    )

    for n in range(12):
        runtime._handle_turn(2, "阿傑", f"第{n}句話")
    await _settle()
    await _settle()

    assert any(call[0] == "summarize" for call in llm.calls if isinstance(call, tuple))
    assert runtime._context(VOICE_ROOM).summary == "稍早在聊晚餐"
    texts = [turn.text for turn in runtime._context(VOICE_ROOM).snapshot()]
    assert "第0句話" not in texts and "第11句話" in texts
    assert len(runtime._context(VOICE_ROOM).snapshot()) == 6
    await _stop(runtime)


@pytest.mark.asyncio
async def test_compaction_can_be_turned_off(tmp_path: Path) -> None:
    runtime, llm, _ = await _runtime(
        tmp_path,
        config=CopilotConfig(
            compact_keep_turns=6, compact_batch_turns=6,
            compact_context=False,
        ),
    )

    for n in range(12):
        runtime._handle_turn(2, "阿傑", f"第{n}句話")
    await _settle()
    await _settle()

    assert not any(call[0] == "summarize" for call in llm.calls if isinstance(call, tuple))
    # Without compaction the old turns are simply dropped from the prompt.
    assert runtime._context(VOICE_ROOM).summary == ""
    await _stop(runtime)


def _with_life(llm: SlowFakeLLM, update: CharacterState | None = None) -> list[str]:
    """Give the fake model a CharacterState, top-ups and updates; returns a
    log of what was asked of it."""
    asked: list[str] = []
    llm.state = CharacterState()  # type: ignore[attr-defined]
    llm.agenda = ()  # type: ignore[attr-defined]
    llm.set_state = lambda state: setattr(llm, "state", state)  # type: ignore[attr-defined]

    async def fill_concerns(state: CharacterState) -> CharacterState:
        asked.append("fill")
        fresh = tuple(Concern(t) for t in ("剛烤好草莓蛋糕", "想約大家週末打球"))
        return replace(state, concerns=state.concerns + fresh[: 4 - len(state.active_concerns())])

    async def update_state(turns) -> CharacterState:
        asked.append("update")
        return update or llm.state  # type: ignore[attr-defined]

    llm.fill_concerns = fill_concerns  # type: ignore[attr-defined]
    llm.update_state = update_state  # type: ignore[attr-defined]
    return asked


@pytest.mark.asyncio
async def test_a_new_persona_gets_todays_concerns(tmp_path: Path) -> None:
    runtime, llm, _ = await _runtime(tmp_path)
    shown: list[tuple[str, ...]] = []
    runtime._on_agenda = shown.append
    _with_life(llm)
    runtime.set_persona(EXAMPLE_PERSONAS[0])
    await _settle()

    assert shown == [("剛烤好草莓蛋糕", "想約大家週末打球")]
    assert not (tmp_path / "character_state.json").exists()  # memory "off"
    await _stop(runtime)


@pytest.mark.asyncio
async def test_light_memory_carries_its_life_and_updates_only_when_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from silenttalk.copilot import runtime as runtime_module

    monkeypatch.setattr(runtime_module, "_LULL_POLL_SECONDS", 0.01)
    monkeypatch.setattr(runtime_module, "_QUIET_UPDATE_SECONDS", 0.3)
    store = CharacterStateStore(tmp_path / "character_state.json")
    store.save(EXAMPLE_PERSONAS[0].id, CharacterState(concerns=(Concern("想揪大家週六打通宵"),)))
    runtime, llm, _ = await _runtime(
        tmp_path, config=CopilotConfig(character_memory="light", character_lull_seconds=0)
    )
    moved_on = CharacterState(
        concerns=(Concern("想揪大家週六打通宵", "done", "約成了"), Concern("週六前買好零食"))
    )
    asked = _with_life(llm, moved_on)
    runtime.set_persona(EXAMPLE_PERSONAS[0])
    await _settle()
    # Last time's concern is back, topped up to four.
    assert [c.text for c in llm.state.active_concerns()][0] == "想揪大家週六打通宵"  # type: ignore[attr-defined]

    for n in range(5):
        runtime._handle_turn(2, "A", f"聊天中第{n}句")
        llm.release.set()
        await asyncio.sleep(0.05)
    assert "update" not in asked  # never mid-chat
    await asyncio.sleep(0.6)
    assert asked.count("update") == 1  # once the room has been quiet a while
    saved = store.load(EXAMPLE_PERSONAS[0].id)
    assert {c.text: c.status for c in saved.concerns}["想揪大家週六打通宵"] == "done"
    await _stop(runtime)


@pytest.mark.asyncio
async def test_clearing_forgets_its_life(tmp_path: Path) -> None:
    store = CharacterStateStore(tmp_path / "character_state.json")
    store.save(EXAMPLE_PERSONAS[0].id, CharacterState(concerns=(Concern("想揪大家週六打通宵"),)))
    runtime, llm, _ = await _runtime(tmp_path, config=CopilotConfig(character_memory="light"))
    _with_life(llm)
    runtime.set_persona(EXAMPLE_PERSONAS[0])
    await _settle()
    runtime.clear_life()
    await _settle()

    texts = [c.text for c in store.load(EXAMPLE_PERSONAS[0].id).concerns]
    assert "想揪大家週六打通宵" not in texts
    await _stop(runtime)


@pytest.mark.asyncio
async def test_a_lull_opens_one_topic_until_someone_speaks_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from silenttalk.copilot import runtime as runtime_module

    monkeypatch.setattr(runtime_module, "_LULL_POLL_SECONDS", 0.01)
    runtime, llm, delivered = await _runtime(
        tmp_path, config=CopilotConfig(character_lull_seconds=0.05)
    )
    asked: list[bool] = []

    async def character_turn(*, turns, summary, engagement, addressed=False, lull=False) -> str:
        asked.append(lull)
        return "我今天烤了草莓蛋糕" if lull else ""

    llm.character_turn = character_turn  # type: ignore[method-assign]
    runtime.set_character_mode(True)
    # No lull before anyone has said anything.
    await asyncio.sleep(0.2)
    assert asked == []

    runtime._handle_turn(2, "A", "欸大家好")
    await asyncio.sleep(0.3)
    spoken = [item for item in delivered if isinstance(item, tuple)]
    assert spoken == [("spoke", "我今天烤了草莓蛋糕")]
    assert asked == [False, True]  # the line itself, then one lull
    # Still quiet: it does not talk to an empty room again.
    await asyncio.sleep(0.2)
    assert asked == [False, True]

    runtime._handle_turn(3, "B", "真的假的")
    await asyncio.sleep(0.3)
    assert asked == [False, True, False, True]
    await _stop(runtime)


@pytest.mark.asyncio
async def test_no_lull_topics_outside_character_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from silenttalk.copilot import runtime as runtime_module

    monkeypatch.setattr(runtime_module, "_LULL_POLL_SECONDS", 0.01)
    runtime, llm, delivered = await _runtime(
        tmp_path, config=CopilotConfig(character_lull_seconds=0.05)
    )
    runtime._handle_turn(2, "A", "欸大家好")
    llm.release.set()
    await asyncio.sleep(0.3)

    assert not [item for item in delivered if isinstance(item, tuple)]
    await _stop(runtime)


@pytest.mark.asyncio
async def test_a_lull_line_is_dropped_if_someone_speaks_meanwhile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from silenttalk.copilot import runtime as runtime_module

    monkeypatch.setattr(runtime_module, "_LULL_POLL_SECONDS", 0.01)
    runtime, llm, delivered = await _runtime(
        tmp_path, config=CopilotConfig(character_lull_seconds=0.05)
    )
    thinking = asyncio.Event()

    async def character_turn(*, turns, summary, engagement, addressed=False, lull=False) -> str:
        if not lull:
            return ""
        thinking.set()
        await llm.release.wait()
        return "我今天烤了草莓蛋糕"

    llm.character_turn = character_turn  # type: ignore[method-assign]
    runtime.set_character_mode(True)
    runtime._handle_turn(2, "A", "欸大家好")
    await asyncio.wait_for(thinking.wait(), 2)
    runtime._handle_turn(3, "B", "我回來了")  # the lull is over
    llm.release.set()
    await asyncio.sleep(0.05)

    assert ("spoke", "我今天烤了草莓蛋糕") not in delivered
    await _stop(runtime)
