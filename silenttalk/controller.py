from __future__ import annotations

import asyncio
import logging
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

import discord

from silenttalk.config import Settings
from silenttalk.copilot.runtime import CopilotRuntime
from silenttalk.copilot.types import ReplySuggestions
from silenttalk.discord_voice import DiscordAudioPlayer, DiscordVoiceClient
from silenttalk.speech_queue import SpeechQueue
from silenttalk.speech_settings import validate_rate_multiplier
from silenttalk.state import AppState
from silenttalk.text import normalize_text
from silenttalk.tts.edge import EdgeTTSEngine
from silenttalk.voice_styles import VOICE_STYLES

_LOG = logging.getLogger(__name__)
StatusCallback = Callable[[AppState, str], None]
SuggestionCallback = Callable[[ReplySuggestions], None]


class AppController:
    def __init__(
        self,
        settings: Settings,
        status: StatusCallback,
        project_dir: Path,
        suggestions: SuggestionCallback | None = None,
    ) -> None:
        self._settings = settings
        self._status = status
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name="silenttalk-async", daemon=True
        )
        self._temp = tempfile.TemporaryDirectory(prefix="silenttalk-")
        self._copilot: CopilotRuntime | None = None
        if settings.copilot.enabled and suggestions is not None:
            self._copilot = CopilotRuntime(
                project_dir,
                settings.copilot,
                settings.discord.owner_user_id,
                on_suggestions=suggestions,
                on_error=lambda message: status(AppState.ERROR, message),
            )
        self._discord = DiscordVoiceClient(
            settings.discord,
            status,
            pcm_callback=self._copilot.accept_pcm if self._copilot else None,
        )
        self._tts = EdgeTTSEngine(settings.tts, Path(self._temp.name))
        self._queue = SpeechQueue(
            self._tts,
            DiscordAudioPlayer(self._discord, settings.audio),
            status,
            on_done=self._on_speech_done,
        )
        self._closing = False

    def start(self) -> None:
        self._thread.start()
        self._schedule(self._bootstrap())

    def submit(
        self,
        raw_text: str,
        voice_style: str = "default",
        rate_multiplier: float = 1.0,
    ) -> None:
        text = normalize_text(raw_text, self._settings.app.max_text_length)
        if voice_style not in VOICE_STYLES:
            raise ValueError(f"未知聲線：{voice_style}")
        rate = validate_rate_multiplier(rate_multiplier)
        self._schedule(
            self._queue.enqueue(
                text,
                voice_style=voice_style,
                rate_multiplier=rate,
            )
        )

    def _on_speech_done(self, job: object) -> None:
        if self._copilot is None:
            return
        text = getattr(job, "text", "")
        if isinstance(text, str) and text.strip():
            self._copilot.record_self(text)

    def stop_playback(self) -> None:
        self._schedule(self._queue.cancel_all())

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._status(AppState.SHUTTING_DOWN, "關閉中…")
        future = asyncio.run_coroutine_threadsafe(self._shutdown_async(), self._loop)
        try:
            future.result(timeout=10)
        except Exception:  # noqa: BLE001 - shutdown must continue after any subsystem failure.
            _LOG.exception("shutdown_failed")
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._temp.cleanup()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        self._loop.close()

    def _schedule(self, coroutine: object) -> None:
        if self._closing:
            if hasattr(coroutine, "close"):
                coroutine.close()  # type: ignore[attr-defined]
            return
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)  # type: ignore[arg-type]

        def report_error(done: object) -> None:
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001 - background boundary reports to the UI.
                _LOG.exception("background_action_failed")
                self._status(AppState.ERROR, str(exc))

        future.add_done_callback(report_error)

    async def _bootstrap(self) -> None:
        self._queue.start()
        try:
            await self._tts.initialize()
        except Exception as exc:  # noqa: BLE001 - online TTS failure is recoverable by design.
            _LOG.warning(
                "tts_initialization_deferred error_type=%s", type(exc).__name__
            )
            self._status(AppState.ERROR, f"TTS 暫時不可用：{exc}")

        if self._copilot is not None:
            try:
                await self._copilot.start()
            except Exception as exc:  # noqa: BLE001 - TTS-only mode must remain usable.
                _LOG.exception("copilot_startup_failed")
                self._status(AppState.ERROR, f"Copilot 啟動失敗：{exc}")
                self._discord.set_pcm_callback(None)
                try:
                    await self._copilot.stop()
                except Exception:
                    _LOG.debug("copilot_partial_shutdown_failed", exc_info=True)
                self._copilot = None

        try:
            await self._discord.start(self._settings.discord.token, reconnect=True)
        except discord.LoginFailure:
            self._status(AppState.ERROR, "Discord Bot Token 無效。")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep the local UI alive on gateway failures.
            _LOG.exception("discord_connection_failed")
            self._status(AppState.ERROR, f"Discord 連線失敗：{exc}")

    async def _shutdown_async(self) -> None:
        await self._queue.shutdown()
        if not self._discord.is_closed():
            await self._discord.close()
        if self._copilot is not None:
            await self._copilot.stop()
