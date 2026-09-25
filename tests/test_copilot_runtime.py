from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from silenttalk.config import CopilotConfig
from silenttalk.copilot.runtime import CopilotRuntime
from silenttalk.copilot.types import ConversationTurn, ReplySuggestions


class SlowFakeLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.release = asyncio.Event()

    async def suggest(
        self, *, context: str, trigger_speaker: str, trigger_text: str
    ) -> ReplySuggestions:
        self.calls.append(trigger_text)
        await self.release.wait()
        self.release.clear()
        return ReplySuggestions(trigger_speaker, trigger_text, agree="好")


async def _runtime(tmp_path: Path) -> tuple[CopilotRuntime, SlowFakeLLM, list]:
    delivered: list[ReplySuggestions | ConversationTurn] = []
    runtime = CopilotRuntime(
        tmp_path,
        CopilotConfig(),
        owner_user_id=1,
        on_suggestions=delivered.append,
        on_error=lambda _: None,
        on_turn=delivered.append,
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
