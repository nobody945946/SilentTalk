from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from silenttalk.config import CopilotConfig
from silenttalk.copilot.persona import PRESET_PERSONAS
from silenttalk.copilot.runtime import CopilotRuntime
from silenttalk.copilot.types import ConversationTurn, ReplySuggestions


class SlowFakeLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.release = asyncio.Event()

    async def suggest(
        self, *, context: str, trigger_speaker: str, trigger_text: str, on_partial=None
    ) -> ReplySuggestions:
        self.calls.append(trigger_text)
        await self.release.wait()
        self.release.clear()
        return ReplySuggestions(trigger_speaker, trigger_text, agree="好")

    def set_persona(self, persona: object) -> None:
        pass

    async def character_reply(
        self, *, context: str, trigger_speaker: str, trigger_text: str, addressed: bool
    ) -> str:
        self.calls.append(("character", trigger_text, addressed))
        await self.release.wait()
        self.release.clear()
        return "收到"


async def _runtime(tmp_path: Path) -> tuple[CopilotRuntime, SlowFakeLLM, list]:
    delivered: list[ReplySuggestions | ConversationTurn | str] = []
    runtime = CopilotRuntime(
        tmp_path,
        CopilotConfig(),
        owner_user_id=1,
        on_suggestions=delivered.append,
        on_error=lambda _: None,
        on_turn=delivered.append,
        on_character_line=delivered.append,
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
    assert "嗯" in runtime._context.render_for_prompt()
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
    runtime.set_persona(PRESET_PERSONAS[0])  # 凱哥
    runtime.set_character_mode(True)
    return runtime, llm, delivered


@pytest.mark.asyncio
async def test_character_answers_its_name_and_speaks_the_line(tmp_path: Path) -> None:
    runtime, llm, delivered = await _character_runtime(tmp_path)
    runtime._handle_turn(2, "阿傑", "凱哥你覺得呢")
    await _settle()
    llm.release.set()
    await _settle()

    assert llm.calls == [("character", "凱哥你覺得呢", True)]
    assert "收到" in delivered
    assert not any(isinstance(item, ReplySuggestions) for item in delivered)
    await _stop(runtime)


@pytest.mark.asyncio
async def test_character_stays_quiet_without_a_reason(tmp_path: Path) -> None:
    runtime, llm, _ = await _character_runtime(tmp_path)
    runtime.record_self("我先講一句")  # just spoke: cooldown running
    runtime._handle_turn(2, "阿傑", "我剛剛吃了拉麵")
    runtime._handle_turn(3, "小雨", "晚餐吃什麼")
    await _settle()

    assert llm.calls == []
    await _stop(runtime)


@pytest.mark.asyncio
async def test_owner_mic_counts_only_in_character_mode(tmp_path: Path) -> None:
    runtime, _, _ = await _runtime(tmp_path)
    runtime._handle_turn(1, "Owner", "我在講話")
    assert "我在講話" not in runtime._context.render_for_prompt()

    runtime.set_persona(PRESET_PERSONAS[0])
    runtime.set_character_mode(True)
    runtime._handle_turn(1, "Owner", "凱哥你好")
    assert "凱哥你好" in runtime._context.render_for_prompt()
    await _stop(runtime)


@pytest.mark.asyncio
async def test_character_drops_a_reply_once_the_chat_moved_on(tmp_path: Path) -> None:
    runtime, llm, delivered = await _character_runtime(tmp_path)
    runtime._handle_turn(2, "阿傑", "晚餐要吃什麼")  # a question: joins in
    await _settle()
    runtime._handle_turn(3, "小雨", "我要吃拉麵")
    runtime._handle_turn(2, "阿傑", "好啊那走")
    llm.release.set()
    await _settle()

    assert llm.calls[0] == ("character", "晚餐要吃什麼", False)
    assert "收到" not in delivered
    await _stop(runtime)
