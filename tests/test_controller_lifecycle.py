from __future__ import annotations

import asyncio
import builtins
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from silenttalk.config import (
    AppConfig,
    AudioConfig,
    CopilotConfig,
    DiscordConfig,
    Settings,
    TTSConfig,
)
from silenttalk.controller import AppController
from silenttalk.speech_queue import SpeechQueue
from silenttalk.tts.base import AudioResult


def controller_with(copilot: object) -> AppController:
    controller = object.__new__(AppController)
    controller._settings = SimpleNamespace(
        discord=SimpleNamespace(token="unused", text_chat=True)
    )
    controller._status = Mock()
    controller._on_ai_status = Mock()
    controller._copilot_requested = True
    controller._queue = SimpleNamespace(start=Mock(), shutdown=AsyncMock())
    controller._discord = SimpleNamespace(
        start=AsyncMock(),
        close=AsyncMock(),
        is_closed=lambda: False,
        messages=SimpleNamespace(names=None),
        set_pcm_callback=Mock(),
        set_text_callback=Mock(),
    )
    controller._copilot = copilot
    controller._copilot_startup = None
    controller._closing = False
    return controller


@pytest.mark.asyncio
async def test_slow_ai_startup_does_not_hold_the_voice_gateway() -> None:
    waiting = asyncio.Event()
    copilot = SimpleNamespace(
        start=AsyncMock(side_effect=waiting.wait),
        stop=AsyncMock(),
        accepts_name=Mock(),
        accept_pcm=Mock(),
        accept_text=Mock(),
    )
    controller = controller_with(copilot)
    player = SimpleNamespace(play=AsyncMock(), stop=AsyncMock())
    tts = SimpleNamespace(
        synthesize=AsyncMock(return_value=AudioResult(None, None, None, "mp3")),
        shutdown=AsyncMock(),
    )
    controller._queue = SpeechQueue(tts, player, lambda *_: None)
    try:
        await asyncio.wait_for(controller._bootstrap(), timeout=0.2)
        controller._discord.start.assert_awaited_once_with("unused", reconnect=True)
        await controller._queue.enqueue("synthetic independent speech")
        await asyncio.wait_for(controller._queue.wait_idle(), timeout=1)
        player.play.assert_awaited_once()
        assert not waiting.is_set()
    finally:
        await controller._shutdown_async()


@pytest.mark.asyncio
async def test_ai_failure_retries_without_stopping_manual_speech_or_gateway(
    monkeypatch,
) -> None:
    monkeypatch.setattr("silenttalk.controller._COPILOT_RETRY_SECONDS", 0.01)
    copilot = SimpleNamespace(
        start=AsyncMock(
            side_effect=[RuntimeError("synthetic AI startup failure"), None]
        ),
        stop=AsyncMock(side_effect=RuntimeError("synthetic AI cleanup failure")),
        accepts_name=Mock(),
        accept_pcm=Mock(),
        accept_text=Mock(),
    )
    controller = controller_with(copilot)
    await controller._bootstrap()
    await asyncio.wait_for(controller._copilot_startup, timeout=1)

    assert controller._copilot is copilot
    assert copilot.start.await_count == 2
    controller._queue.start.assert_called_once()
    controller._queue.shutdown.assert_not_awaited()
    controller._discord.start.assert_awaited_once()
    controller._discord.close.assert_not_awaited()
    assert controller._discord.set_pcm_callback.call_args_list[0].args == (None,)
    controller._discord.set_pcm_callback.assert_called_with(copilot.accept_pcm)
    controller._discord.set_text_callback.assert_called_with(copilot.accept_text)
    await controller._shutdown_async()


@pytest.mark.asyncio
async def test_one_shutdown_failure_does_not_skip_other_components() -> None:
    copilot = SimpleNamespace(
        start=AsyncMock(), stop=AsyncMock(side_effect=RuntimeError("AI"))
    )
    controller = controller_with(copilot)
    controller._queue.shutdown.side_effect = RuntimeError("speech")

    await controller._shutdown_async()

    controller._queue.shutdown.assert_awaited_once()
    controller._discord.close.assert_awaited_once()
    copilot.stop.assert_awaited_once()


def test_ai_import_failure_keeps_manual_speech_constructible(
    tmp_path, monkeypatch
) -> None:
    original_import = builtins.__import__

    def import_without_ai(name, *args, **kwargs):
        if name == "silenttalk.copilot.runtime":
            raise ImportError("synthetic unavailable AI module")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_ai)
    settings = Settings(
        AppConfig(),
        TTSConfig(),
        DiscordConfig("unused", 123),
        AudioConfig(),
        CopilotConfig(),
    )
    controller = AppController(settings, Mock(), tmp_path)
    try:
        assert not controller.copilot_enabled
        assert isinstance(controller._queue, SpeechQueue)
        assert controller._discord._pcm_callback is None
    finally:
        controller._loop.close()
        controller._temp.cleanup()


@pytest.mark.asyncio
async def test_failed_ai_construction_recovers_with_the_selected_persona_and_mode(
    tmp_path, monkeypatch
) -> None:
    from silenttalk.persona import MACHINE_SPIRIT

    runtime = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        set_persona=Mock(),
        set_character_mode=Mock(),
        accept_pcm=Mock(),
        accept_text=Mock(),
        accepts_name=Mock(),
    )
    controller = controller_with(None)
    controller._active_persona = MACHINE_SPIRIT
    controller._desired_character_mode = True
    controller._copilot_factory = Mock(
        side_effect=[ImportError("synthetic AI failure"), runtime]
    )
    monkeypatch.setattr("silenttalk.controller._COPILOT_RETRY_SECONDS", 0.01)

    await controller._bootstrap()
    await asyncio.wait_for(controller._copilot_startup, timeout=1)

    runtime.set_persona.assert_called_once_with(MACHINE_SPIRIT)
    runtime.set_character_mode.assert_called_once_with(True)
    controller._status.assert_not_called()
    controller._discord.close.assert_not_awaited()
    controller._queue.shutdown.assert_not_awaited()
    assert controller._discord.messages.names == runtime.accepts_name
    await controller._shutdown_async()
