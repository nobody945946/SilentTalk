from __future__ import annotations

import queue
import sys
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from silenttalk import theme
from silenttalk.chat_workspace_ui import ChatWorkspace
from silenttalk.conversation import ConversationTurn
from silenttalk.discord_invite_ui import DiscordInviteCard
from silenttalk.hotkeys import GlobalHotkeys
from silenttalk.input_bindings_ui import InputBindings
from silenttalk.model_info_ui import build_model_info
from silenttalk.navigation_ui import NavigationRail
from silenttalk.persona import Persona, PersonaStore
from silenttalk.persona_ui import PersonaPanel
from silenttalk.phrases import QuickPhraseStore
from silenttalk.preferences import (
    PreferenceError,
    PreferenceStore,
    UserPreferences,
)
from silenttalk.settings_store import SettingsStore
from silenttalk.settings_ui import SettingsPanel
from silenttalk.state import AppState
from silenttalk.status_ui import StatusBar
from silenttalk.text import TextValidationError
from silenttalk.voice_controls_ui import VoiceControls

# Three places, like a phone's tab bar: talking, who you are, and settings.
# Everything else is a layer inside one of them. (key, glyph, label); glyphs
# stay in the BMP: Tk 8.6 on Windows draws astral-plane emoji inconsistently.
# The chat page's modes, and where the old page names now live.
CHAT_MODES = ("character", "manual")
_PAGE_ALIASES = {"voice": ("settings", "voice")}


@dataclass(frozen=True, slots=True)
class UIAction:
    kind: str
    state: AppState | None = None
    message: str = ""
    turn: ConversationTurn | None = None


def _enable_crisp_text() -> None:
    """Per-monitor DPI awareness: sharp text on 125-150% laptop scaling."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


class SilentTalkUI:
    def __init__(
        self,
        speak_hotkey: str,
        stop_hotkey: str,
        submit: Callable[[str, str, float], None],
        stop_playback: Callable[[], None],
        shutdown: Callable[[], None],
        quick_phrases: QuickPhraseStore | None = None,
        preferences: PreferenceStore | None = None,
        *,
        personas: PersonaStore | None = None,
        apply_persona: Callable[[Persona], None] | None = None,
        set_character_mode: Callable[[bool, str, float], None] | None = None,
        preview_voice: Callable[[str, Persona, float], None] | None = None,
        reroll_agenda: Callable[[], None] | None = None,
        settings_store: SettingsStore | None = None,
        config_defaults: dict[str, dict[str, object]] | None = None,
        apply_settings: Callable[[dict[str, dict[str, object]]], None] | None = None,
        copilot_info: Sequence[tuple[str, str]] = (),
        font_override: str | None = None,
        invite_link: Callable[[], str] | None = None,
        start_character_mode: bool = False,
    ) -> None:
        self._submit_callback = submit
        self._quick_phrases = quick_phrases
        self._stop_callback = stop_playback
        self._shutdown_callback = shutdown
        self._preference_store = preferences
        self._apply_persona_callback = apply_persona
        self._character_callback = set_character_mode
        self._preview_callback = preview_voice
        self._reroll_agenda_callback = reroll_agenda
        self._character_on = False
        self._actions: queue.SimpleQueue[UIAction] = queue.SimpleQueue()
        self._speak_hotkey = speak_hotkey
        self._stop_hotkey = stop_hotkey

        preference_error = ""
        try:
            initial_preferences = (
                preferences.load() if preferences is not None else UserPreferences()
            )
        except PreferenceError as exc:
            initial_preferences = UserPreferences()
            preference_error = str(exc)
        # The chat view to return to from another page, character included.
        # The character view starts paused every time, so typing comes first.
        self._mode = self._chat_view = "manual"

        _enable_crisp_text()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        theme.init_fonts(self.root, font_override)
        theme.style_ttk(self.root)

        self.popup = tk.Toplevel(self.root, bg=theme.BG)
        self.popup.title("SilentTalk")
        self.popup.attributes("-topmost", True)
        # An explicit size, scaled and kept on screen: without one the window
        # grows to whatever its content asks for (a long line, a big card).
        width = min(theme.px(920), self.popup.winfo_screenwidth() - theme.px(40))
        height = min(theme.px(700), self.popup.winfo_screenheight() - theme.px(90))
        self.popup.geometry(f"{width}x{height}")
        self.popup.minsize(min(theme.px(760), width), min(theme.px(560), height))
        self.popup.protocol("WM_DELETE_WINDOW", self.hide)

        # Bottom bar first: pack gives the last widgets whatever is left, and
        # the status line must never be squeezed out.
        self.status = StatusBar(
            self.popup,
            on_close=self.close,
            error=preference_error,
        )
        self.voice = VoiceControls(
            preferences=initial_preferences,
            on_change=self._voice_changed,
            on_commit=self._persist_preferences,
            on_summary=self._voice_summary,
        )
        self.invite = DiscordInviteCard(self.root, invite_link, self.status.status_var)
        body = tk.Frame(self.popup, bg=theme.BG)
        body.pack(fill="both", expand=True)
        self.rail = NavigationRail(
            body,
            navigate=self.show_page,
            stop=self._stop_from_button,
            stop_hotkey=self._stop_hotkey,
        )
        self._pages_frame = tk.Frame(body, bg=theme.BG)
        self._pages_frame.pack(side="left", fill="both", expand=True)
        self._pages_frame.rowconfigure(0, weight=1)
        self._pages_frame.columnconfigure(0, weight=1)

        self.chat = ChatWorkspace(
            self._pages_frame,
            navigate=self.show_page,
            on_mood=self._on_mood,
            on_run=self._set_character_mode if self._character_callback else None,
            on_engagement=self._set_engagement,
            stop_hotkey=self._stop_hotkey,
            on_reroll=self._reroll_agenda_callback,
            manual_options=dict(
                phrases=quick_phrases,
                status=self.status.status_var,
                submit=self._submit_text,
                hide=self.hide,
                navigate=self.show_page,
                get_style=self.voice._selected_style_key,
                set_style=self.voice._set_style,
            ),
        )
        self.bindings = InputBindings(
            self.popup,
            mode=lambda: self._mode,
            hide=self.hide,
            manual=self.chat.manual,
        )
        self.persona_panel = PersonaPanel(
            self._pages_frame,
            personas,
            on_apply=self._apply_persona,
            on_status=self.status.status_var.set,
            on_preview=self._preview_voice if self._preview_callback else None,
        )
        self.settings_panel = SettingsPanel(
            self._pages_frame,
            settings_store,
            config_defaults or {},
            on_status=self.status.status_var.set,
            on_apply=self._settings_applied,
        )
        self._apply_settings_callback = apply_settings
        # The voice and speed used when a persona has no voice of its own,
        # and what the local AI runs on: settings, one layer down.
        self.settings_panel.add_custom_group(
            "voice",
            lambda parent: self.voice._build_voice_group(parent, initial_preferences),
        )
        self.settings_panel.add_custom_group(
            "model", lambda parent: build_model_info(parent, copilot_info)
        )
        if invite_link is not None:
            self.settings_panel.add_custom_group(
                "discord",
                lambda parent: self.invite._build_discord_invite(parent, invite_link),
                on_show=self.invite._refresh_discord_invite,
            )
        self._pages = {
            "chat": self.chat.frame,
            "persona": self.persona_panel,
            "settings": self.settings_panel,
        }
        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        state = self.persona_panel.state
        self._apply_persona(state.active_persona(), announce=False)
        self.chat.character.set_engagement(
            str(
                self.settings_panel.value("copilot", "character_engagement") or "called"
            )
        )
        if start_character_mode and self._character_callback is not None:
            self.show_page("character", focus=False)
            self._set_character_mode(True)
        else:
            self.show_page("manual", focus=False)
        self.popup.withdraw()

        self._hotkeys = GlobalHotkeys(
            {
                speak_hotkey: lambda: self._actions.put(UIAction("show")),
                stop_hotkey: lambda: self._actions.put(UIAction("stop")),
            }
        )
        self.chat.manual._refresh_phrases()
        self.root.after(50, self._poll_actions)

    # ---- public API --------------------------------------------------------------

    def run(self) -> None:
        try:
            self._hotkeys.start()
        except Exception as exc:  # noqa: BLE001 - hotkey thread failures are reported in the UI.
            self.set_status(AppState.ERROR, f"快捷鍵失敗：{exc}")
        self.root.mainloop()

    def set_status(self, state: AppState, message: str) -> None:
        self._actions.put(UIAction("status", state, message))

    def set_ai_status(self, message: str) -> None:
        self._actions.put(UIAction("ai_status", message=message))

    def set_agenda(self, items: Sequence[str]) -> None:
        """Safe from any thread: the character's concerns for today."""
        self._actions.put(UIAction("agenda", message="\n".join(items)))

    def add_conversation_turn(self, turn: ConversationTurn) -> None:
        self._actions.put(UIAction("turn", turn=turn))

    def show(self) -> None:
        self.chat.manual._refresh_phrases()
        self.popup.deiconify()
        self.popup.lift()
        self.popup.focus_force()
        self._focus_page()

    def hide(self) -> None:
        self.chat.manual.input.delete("1.0", "end")
        self.persona_panel.flush()
        self.popup.withdraw()

    def close(self) -> None:
        self.persona_panel.flush()
        self._persist_preferences()
        self._hotkeys.stop()
        self._shutdown_callback()
        self.root.destroy()

    def show_page(self, key: str, *, focus: bool = True) -> None:
        """Pages: chat, persona, settings. The chat page's modes (character,
        manual) and the old page names (voice) are accepted too."""
        sub = ""
        if key in _PAGE_ALIASES:
            key, sub = _PAGE_ALIASES[key]
        if key in CHAT_MODES:
            self._show_chat_mode(key)
            page = "chat"
        elif key == "chat":
            self._show_chat_mode(self._chat_view)
            page = "chat"
        elif key in self._pages:
            if self._mode == "persona" and key != "persona":
                self.persona_panel.flush()
            self._mode = key
            page = key
        else:
            return
        if sub:
            self.settings_panel.show(sub)
        self._pages[page].tkraise()
        for page_key, (item, icon, text) in self.rail._rail_items.items():
            selected = page_key == page
            bg = theme.PANEL if selected else theme.SURFACE
            for widget in (item, icon, text):
                widget.configure(bg=bg)
            icon.configure(fg=theme.ACCENT_HI if selected else theme.DIM)
            text.configure(fg=theme.TEXT if selected else theme.DIM)
        if focus:
            self._focus_page()

    def _show_chat_mode(self, mode: str) -> None:
        if self._mode == "persona":
            self.persona_panel.flush()
        if mode != "character" and self._character_on:
            # The bot plays the persona *or* speaks for you, never both.
            self._set_character_mode(False)
            if self._character_on:
                # Pausing failed (the error is in the status line): stay.
                mode = "character"
            else:
                self.status.status_var.set("角色已暫停")
        self._mode = mode
        self._chat_view = mode
        self.chat.header.set_mode(mode)
        for key, view in self.chat.views.items():
            if key == mode:
                view.pack(fill="x")
            else:
                view.pack_forget()

    # ---- focus & keys --------------------------------------------------------------

    def _focus_page(self) -> None:
        if self._mode == "character":
            self.chat.character.focus_set()
        elif self._mode == "manual":
            self.chat.manual.input.focus_set()

    # ---- persona -------------------------------------------------------------------

    def _apply_persona(self, persona: Persona, *, announce: bool = True) -> None:
        if hasattr(self, "_persona_voice_note"):
            self.voice._persona_voice_note.configure(
                text=f"現在由人設「{persona.name}」自己的聲音說話（在人設頁改）；這裡的聲線給沒有設定聲音的人設用。"
                if persona.voice_style() is not None
                else "沒有設定自己聲音的人設、打字和快捷句都用這裡的聲線。"
            )
        subtitle = " ".join(persona.identity.split()) or (
            "中性口吻" if persona.is_blank else ""
        )
        if len(subtitle) > 28:
            subtitle = subtitle[:27] + "…"
        self.chat.header.set_persona(persona.name, subtitle)
        self.chat.header.set_mood(persona.mood)
        self.chat.character.set_persona(persona.name)
        if self._apply_persona_callback is not None:
            self._apply_persona_callback(persona)

    def _preview_voice(self, persona: Persona, text: str) -> None:
        if self._preview_callback is None:
            return
        try:
            self._preview_callback(text, persona, self.voice._rate_multiplier())
        except Exception as exc:  # noqa: BLE001 - shown to the user
            self.status._show_status(AppState.ERROR, f"試聽失敗：{exc}")

    def _toggle_character(self) -> None:
        self._set_character_mode(not self._character_on)

    def _set_character_mode(self, enabled: bool) -> None:
        if self._character_callback is None:
            return
        try:
            self._character_callback(
                enabled, self.voice._voice_style, self.voice._rate_multiplier()
            )
        except Exception as exc:  # noqa: BLE001 - shown to the user, app keeps running
            self.status._show_status(AppState.ERROR, str(exc))
            return
        self._character_on = enabled
        self.chat.character.set_running(enabled)

    def _settings_applied(self, tables: dict[str, dict[str, object]]) -> None:
        # The character view shows the same 開口時機 as the settings page.
        self.chat.character.set_engagement(
            str(tables.get("copilot", {}).get("character_engagement", "called"))
        )
        if self._apply_settings_callback is not None:
            self._apply_settings_callback(tables)

    def _set_engagement(self, value: str) -> None:
        """The character view's switch is the settings page's 開口時機."""
        self.settings_panel.set_value("copilot", "character_engagement", value)

    def _on_mood(self, mood: str) -> None:
        self.persona_panel.set_mood(mood)

    # ---- voice & rate --------------------------------------------------------------

    def _persist_preferences(self) -> None:
        if self._preference_store is None or not hasattr(self.voice, "rate_var"):
            return
        try:
            self._preference_store.save(
                UserPreferences(speech_rate_multiplier=self.voice._rate_multiplier())
            )
        except PreferenceError as exc:
            if hasattr(self.status, "status_var"):
                self.status.status_var.set(str(exc))

    def _stop_from_button(self) -> None:
        self._stop_callback()
        self.status.status_var.set("已停止並清空佇列")

    # ---- typing --------------------------------------------------------------------

    def _submit_text(self, raw: str, voice_style: str | None = None) -> bool:
        try:
            self._submit_callback(
                raw,
                voice_style or self.voice._selected_style_key(),
                self.voice._rate_multiplier(),
            )
        except (TextValidationError, ValueError) as exc:
            self.status.status_var.set(str(exc))
            return False
        return True

    # ---- backend → UI ----------------------------------------------------------------

    def _poll_actions(self) -> None:
        while True:
            try:
                action = self._actions.get_nowait()
            except queue.Empty:
                break
            if action.kind == "show":
                self.show()
            elif action.kind == "stop":
                self._stop_callback()
                self.status.status_var.set("已停止並清空佇列")
            elif action.kind == "status":
                self.status._show_status(action.state, action.message)
            elif action.kind == "ai_status":
                self.status.set_ai_status(action.message)
            elif action.kind == "agenda":
                self.chat.character.set_agenda(
                    [item for item in action.message.splitlines() if item]
                )
            elif action.kind == "turn" and action.turn is not None:
                self.chat.transcript.add_turn(action.turn)
        self.root.after(50, self._poll_actions)

    def _voice_changed(self):
        if self._character_on:
            self._set_character_mode(True)

    def _voice_summary(self, text):
        self.chat.manual._voice_summary.configure(text=text)
