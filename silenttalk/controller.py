from __future__ import annotations

import asyncio
import logging
import tempfile
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import discord

from silenttalk.agent_tasks import AgentTaskClient
from silenttalk.config import Settings
from silenttalk.copilot.persona import Persona
from silenttalk.copilot.runtime import CopilotRuntime, ThinkingCallback, TurnCallback
from silenttalk.copilot.types import VOICE_ROOM, ReplySuggestions
from silenttalk.discord_voice import DiscordAudioPlayer, DiscordVoiceClient
from silenttalk.speech_queue import SpeechQueue
from silenttalk.speech_settings import validate_rate_multiplier
from silenttalk.state import AppState
from silenttalk.text import normalize_text
from silenttalk.tts.edge import EdgeTTSEngine
from silenttalk.tts.local_play import play_wav, render_wav
from silenttalk.voice_styles import VOICE_STYLES, VoiceStyle

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
        *,
        on_turn: TurnCallback | None = None,
        on_thinking: ThinkingCallback | None = None,
        on_agenda: Callable[[tuple[str, ...]], None] | None = None,
    ) -> None:
        self._settings = settings
        self._status = status
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name="silenttalk-async", daemon=True
        )
        self._temp = tempfile.TemporaryDirectory(prefix="silenttalk-")
        self._copilot: CopilotRuntime | None = None
        self._agent_tasks = AgentTaskClient()
        if settings.copilot.enabled and suggestions is not None:
            self._copilot = CopilotRuntime(
                project_dir,
                settings.copilot,
                settings.discord.owner_user_id,
                on_suggestions=suggestions,
                on_error=lambda message: status(AppState.ERROR, message),
                on_turn=on_turn,
                on_thinking=on_thinking,
                on_character_line=self._speak_as_character,
                on_character_text=self._type_as_character,
                on_agenda=on_agenda,
                can_type=settings.discord.text_chat,
                agent_tasks=self._agent_tasks,
                on_agent_approval=self._agent_approval,
                on_agent_line=self._speak_agent_line,
                on_agent_private=self._agent_private,
                on_task_mark=self._mark_task,
            )
        self._discord = DiscordVoiceClient(
            settings.discord,
            status,
            pcm_callback=self._copilot.accept_pcm if self._copilot else None,
            text_callback=(
                self._copilot.accept_text
                if self._copilot and settings.discord.text_chat
                else None
            ),
            # Threads are conversations with the character, so only in character mode.
            threads_open=lambda: self._copilot is not None and self._copilot.character_mode,
        )
        self._tts = EdgeTTSEngine(settings.tts, Path(self._temp.name))
        self._queue = SpeechQueue(
            self._tts,
            DiscordAudioPlayer(self._discord, settings.audio),
            status,
            on_done=self._on_speech_done,
        )
        self._closing = False
        self._character_voice = ("default", 1.0)
        # The active persona's own voice; when set it is used for everything
        # the bot says (typed, picked or spoken by the character).
        self._persona_voice: VoiceStyle | None = None

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
                voice_style=self._persona_voice or voice_style,
                rate_multiplier=rate,
            )
        )

    def preview_voice(self, text: str, persona: Persona, rate_multiplier: float = 1.0) -> None:
        """Say `text` in the persona's voice on this PC's speakers only."""
        text = normalize_text(text, self._settings.app.max_text_length)
        rate = validate_rate_multiplier(rate_multiplier)
        style = persona.voice_style() or "default"
        self._schedule(self._preview(text, style, rate))

    async def _preview(self, text: str, style: str | VoiceStyle, rate: float) -> None:
        audio = await self._tts.synthesize(text, voice_style=style, rate_multiplier=rate)
        try:
            wav = await asyncio.to_thread(render_wav, audio, self._settings.audio.ffmpeg_path)
            await asyncio.to_thread(play_wav, wav)
        finally:
            audio.path.unlink(missing_ok=True)

    def _on_speech_done(self, job: object) -> None:
        if self._copilot is None:
            return
        text = getattr(job, "text", "")
        if isinstance(text, str) and text.strip():
            self._copilot.record_self(text)

    def apply_settings(self, tables: dict[str, dict[str, object]]) -> None:
        """Settings changed on the settings page. Everything that can take
        effect without a restart does so here; the rest is already marked
        "需重開" in the UI and is only read at startup."""
        copilot = tables.get("copilot", {})
        tts = tables.get("tts", {})
        discord = tables.get("discord", {})
        try:
            self._settings = replace(
                self._settings,
                app=replace(
                    self._settings.app,
                    max_text_length=int(
                        tables.get("app", {}).get(
                            "max_text_length", self._settings.app.max_text_length
                        )
                    ),
                ),
                tts=replace(
                    self._settings.tts,
                    voice=str(tts.get("voice", self._settings.tts.voice)),
                    rate=str(tts.get("rate", self._settings.tts.rate)),
                    pitch=str(tts.get("pitch", self._settings.tts.pitch)),
                    volume=str(tts.get("volume", self._settings.tts.volume)),
                ),
                discord=replace(
                    self._settings.discord,
                    disconnect_when_owner_leaves=bool(
                        discord.get(
                            "disconnect_when_owner_leaves",
                            self._settings.discord.disconnect_when_owner_leaves,
                        )
                    ),
                ),
            )
        except (TypeError, ValueError) as exc:
            _LOG.warning("settings_apply_failed error_type=%s", type(exc).__name__)
            self._status(AppState.ERROR, f"設定套用失敗：{exc}")
            return
        self._tts.apply_config(self._settings.tts)
        self._discord.apply_config(self._settings.discord)
        runtime = self._copilot
        if runtime is not None:
            self._loop.call_soon_threadsafe(runtime.apply_settings, dict(copilot))
        _LOG.info("settings_applied sections=%s", ",".join(sorted(tables)))

    def set_character_mode(
        self, enabled: bool, voice_style: str = "default", rate_multiplier: float = 1.0
    ) -> None:
        """Safe from any thread. In character mode the bot is the active
        persona and speaks up by itself, in this voice."""
        copilot = self._copilot
        if copilot is None:
            raise RuntimeError("Copilot 未啟用或啟動失敗。")
        if voice_style not in VOICE_STYLES:
            voice_style = "default"
        self._character_voice = (voice_style, validate_rate_multiplier(rate_multiplier))
        self._loop.call_soon_threadsafe(copilot.set_character_mode, enabled)

    def send_text(self, raw_text: str) -> None:
        """Type a line into the voice channel's text chat instead of saying it."""
        text = normalize_text(raw_text, self._settings.app.max_text_length)
        self._schedule(self._send_text(text))

    async def _send_text(self, text: str, place: int = VOICE_ROOM) -> None:
        if not await self._discord.send_text(text, place):
            self._status(AppState.ERROR, "訊息送不出去：確認 Bot 有這個頻道（或討論串）的發言權限。")
            return
        if self._copilot is not None:
            # Same rule as speech: only what actually reached the channel
            # counts as something "you" said.
            self._copilot.record_self(text, place, via="text")

    def _type_as_character(self, line: str, place: int = VOICE_ROOM) -> None:
        """Runs on the backend loop; the character answers a typed line in
        the place it came from (the voice channel's chat or a thread)."""
        if self._closing:
            return
        try:
            text = normalize_text(line, self._settings.app.max_text_length)
        except ValueError:
            return
        self._schedule(self._send_text(text, place))

    def _mark_task(self, channel_id: int, message_id: int, state: str) -> None:
        """⚙️ / ✅ / ❌ on the owner's message that handed over the work."""
        if not self._closing:
            self._schedule(self._discord.mark_task(channel_id, message_id, state))

    async def _agent_approval(self, payload: dict[str, object]) -> None:
        session_id = self._agent_tasks.session_id

        async def decide(call_id: str, approved: bool) -> bool:
            if self._agent_tasks.session_id != session_id:
                return False
            return await self._agent_tasks.approve(call_id, approved)

        await self._discord.send_approval(payload, decide)

    async def _agent_private(self, text: str) -> bool:
        return await self._discord.send_private(text)

    def _speak_agent_line(self, line: str) -> None:
        """Task acknowledgments and reports wait behind current speech."""
        if self._closing:
            return
        text = normalize_text(line[:self._settings.app.max_text_length],
                              self._settings.app.max_text_length)
        style, rate = self._character_voice
        self._schedule(self._queue.enqueue(text, voice_style=self._persona_voice or style,
                                          rate_multiplier=rate))

    def _speak_as_character(self, line: str) -> None:
        """Runs on the backend loop. Never talks over itself: if something is
        still being said (or the owner queued text), this line is dropped."""
        if self._closing or not self._queue.is_idle:
            _LOG.info("character_line_dropped reason=busy")
            return
        try:
            text = normalize_text(line, self._settings.app.max_text_length)
        except ValueError:
            text = normalize_text(
                line[: self._settings.app.max_text_length], self._settings.app.max_text_length
            )
        style, rate = self._character_voice
        self._schedule(
            self._queue.enqueue(
                text, voice_style=self._persona_voice or style, rate_multiplier=rate
            )
        )

    def regenerate_suggestions(self) -> None:
        copilot = self._copilot
        if copilot is None:
            raise RuntimeError("Copilot 未啟用或啟動失敗。")
        self._loop.call_soon_threadsafe(copilot.regenerate)

    def reroll_agenda(self) -> None:
        """A new set of the character's concerns for today."""
        copilot = self._copilot
        if copilot is not None and not self._closing:
            self._loop.call_soon_threadsafe(copilot.refresh_agenda)

    def set_persona(self, persona: Persona) -> None:
        """Safe from any thread; before start() it is applied once the loop runs."""
        self._persona_voice = persona.voice_style()
        copilot = self._copilot
        if copilot is not None and not self._closing:
            self._loop.call_soon_threadsafe(copilot.set_persona, persona)

    @property
    def copilot_enabled(self) -> bool:
        return self._copilot is not None

    def stop_playback(self) -> None:
        self._schedule(self._queue.cancel_all())

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._status(AppState.SHUTTING_DOWN, "關閉中…")
        future = asyncio.run_coroutine_threadsafe(self._shutdown_async(), self._loop)
        try:
            # Switching the shared E4B service back to its 96K base mode takes
            # about ten seconds on this laptop; wait for that handoff to finish.
            future.result(timeout=30)
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
        if self._copilot is not None:
            await self._copilot.stop_agent_task()
        await self._queue.shutdown()
        if not self._discord.is_closed():
            await self._discord.close()
        if self._copilot is not None:
            await self._copilot.stop()
