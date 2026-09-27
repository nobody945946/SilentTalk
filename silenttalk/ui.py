from __future__ import annotations

import queue
import sys
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from silenttalk import theme
from silenttalk.chat_ui import CharacterView, ChatHeader, Transcript
from silenttalk.copilot.persona import Persona, PersonaStore
from silenttalk.copilot.types import REPLY_LANES, ConversationTurn, ReplySuggestions
from silenttalk.hotkeys import GlobalHotkeys
from silenttalk.ime import set_ime_enabled
from silenttalk.persona_ui import PersonaPanel
from silenttalk.phrases import QuickPhrase, QuickPhraseError, QuickPhraseStore
from silenttalk.preferences import (
    PreferenceError,
    PreferenceStore,
    UserPreferences,
)
from silenttalk.settings_store import SettingsStore
from silenttalk.settings_ui import SettingsPanel
from silenttalk.speech_settings import (
    DEFAULT_RATE_MULTIPLIER,
    MAX_RATE_MULTIPLIER,
    MIN_RATE_MULTIPLIER,
)
from silenttalk.state import AppState
from silenttalk.story_ui import StoryPanel
from silenttalk.text import TextValidationError
from silenttalk.voice_styles import voice_style_choices, voice_style_label
from silenttalk.widgets import (
    Button,
    Chip,
    Disclosure,
    StatusDot,
    card,
    hint_row,
    wrap_to_width,
)

# Three places, like a phone's tab bar: talking, who you are, and settings.
# Everything else is a layer inside one of them. (key, glyph, label); glyphs
# stay in the BMP: Tk 8.6 on Windows draws astral-plane emoji inconsistently.
NAV: tuple[tuple[str, str, str], ...] = (
    ("chat", "◆", "對話"),
    ("persona", "☺", "人設"),
    ("settings", "⚙", "設定"),
)
# The chat page's modes, and where the old page names now live.
CHAT_MODES = ("character", "story", "manual")
_PAGE_ALIASES = {"voice": ("settings", "voice")}

_DISCORD_STATES = {
    AppState.STARTING: (theme.DIM, "啟動中"),
    AppState.READY: (theme.WARN, "Discord 待命"),
    AppState.OWNER_NOT_IN_VOICE: (theme.WARN, "你不在語音頻道"),
    AppState.VOICE_CONNECTED: (theme.OK, "語音已連線"),
    AppState.SYNTHESIZING: (theme.OK, "合成語音中"),
    AppState.SPEAKING: (theme.ACCENT_HI, "正在說話"),
    AppState.SHUTTING_DOWN: (theme.DIM, "關閉中"),
}


@dataclass(frozen=True, slots=True)
class UIAction:
    kind: str
    state: AppState | None = None
    message: str = ""
    suggestions: ReplySuggestions | None = None
    turn: ConversationTurn | None = None
    speaker: str = ""


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
        auto_popup_suggestions: bool = True,
        regenerate_suggestions: Callable[[], None] | None = None,
        personas: PersonaStore | None = None,
        apply_persona: Callable[[Persona], None] | None = None,
        set_character_mode: Callable[[bool, str, float], None] | None = None,
        preview_voice: Callable[[str, Persona, float], None] | None = None,
        send_text: Callable[[str], None] | None = None,
        settings_store: SettingsStore | None = None,
        config_defaults: dict[str, dict[str, object]] | None = None,
        apply_settings: Callable[[dict[str, dict[str, object]]], None] | None = None,
        copilot_info: Sequence[tuple[str, str]] = (),
        font_override: str | None = None,
    ) -> None:
        self._submit_callback = submit
        self._stop_callback = stop_playback
        self._shutdown_callback = shutdown
        self._phrase_store = quick_phrases
        self._preference_store = preferences
        self._apply_persona_callback = apply_persona
        self._character_callback = set_character_mode
        self._preview_callback = preview_voice
        self._send_text_callback = send_text
        self._character_on = False
        self._persona_name = ""
        self._copilot_enabled = regenerate_suggestions is not None
        self._phrases: list[QuickPhrase] = []
        self._actions: queue.SimpleQueue[UIAction] = queue.SimpleQueue()
        self._style_choices = voice_style_choices()
        self._auto_popup_suggestions = auto_popup_suggestions
        self._latest_suggestions: ReplySuggestions | None = None
        self._suggestion_values: list[str] = [""] * len(REPLY_LANES)
        self._voice_style = "default"
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
        self._mode = initial_preferences.ui_mode
        # The chat mode to come back to (and to save); the chat page's
        # character view is never saved: it starts paused every time.
        self._chat_mode = self._mode if self._mode in ("story", "manual") else "manual"
        # The chat view to return to from another page, character included.
        self._chat_view = self._chat_mode

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
        self.popup.bind("<Escape>", lambda _: self.hide())
        self.popup.bind("<Return>", self._on_enter)
        self.popup.bind("<Control-Tab>", self._toggle_story_manual)
        self.popup.bind("<KeyPress>", self._on_popup_key)
        for index in range(9):
            self.popup.bind(
                f"<Control-Key-{index + 1}>",
                lambda event, phrase_index=index: self._on_quick_phrase_key(
                    phrase_index
                ),
            )

        # Bottom bar first: pack gives the last widgets whatever is left, and
        # the status line must never be squeezed out.
        self._build_status_bar(preference_error)
        body = tk.Frame(self.popup, bg=theme.BG)
        body.pack(fill="both", expand=True)
        self._build_rail(body)
        self._pages_frame = tk.Frame(body, bg=theme.BG)
        self._pages_frame.pack(side="left", fill="both", expand=True)
        self._pages_frame.rowconfigure(0, weight=1)
        self._pages_frame.columnconfigure(0, weight=1)

        self._chat_page = self._build_chat_page(
            self._pages_frame, regenerate_suggestions, send_text
        )
        self.persona_panel = PersonaPanel(
            self._pages_frame,
            personas,
            on_apply=self._apply_persona,
            on_status=self.status_var.set,
            on_preview=self._preview_voice if self._preview_callback else None,
        )
        self.settings_panel = SettingsPanel(
            self._pages_frame,
            settings_store,
            config_defaults or {},
            on_status=self.status_var.set,
            on_apply=self._settings_applied,
        )
        self._apply_settings_callback = apply_settings
        # The voice and speed used when a persona has no voice of its own,
        # and what the local AI runs on: settings, one layer down.
        self.settings_panel.add_custom_group(
            "voice", lambda parent: self._build_voice_group(parent, initial_preferences)
        )
        self.settings_panel.add_custom_group(
            "model", lambda parent: self._build_model_info(parent, copilot_info)
        )
        self._pages = {
            "chat": self._chat_page,
            "persona": self.persona_panel,
            "settings": self.settings_panel,
        }
        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        state = self.persona_panel.state
        self.story.set_mood(state.mood)
        self._apply_persona(state.active_persona(), announce=False)
        self._character_view.set_engagement(
            str(self.settings_panel.value("copilot", "character_engagement") or "called")
        )
        if not self._copilot_enabled:
            self._ai_dot.set(theme.DIM, "AI 關閉")
        self.show_page(self._mode if self._mode in CHAT_MODES else "manual", focus=False)
        self.popup.withdraw()

        self._hotkeys = GlobalHotkeys(
            {
                speak_hotkey: lambda: self._actions.put(UIAction("show")),
                stop_hotkey: lambda: self._actions.put(UIAction("stop")),
            }
        )
        self._refresh_phrases()
        self.root.after(50, self._poll_actions)

    # ---- chrome ----------------------------------------------------------------

    def _build_rail(self, body: tk.Frame) -> None:
        rail = tk.Frame(body, bg=theme.SURFACE)
        rail.pack(side="left", fill="y")
        tk.Label(
            rail, text="◢", bg=theme.SURFACE, fg=theme.ACCENT, font=theme.font(16)
        ).pack(pady=(theme.px(16), theme.px(14)))
        self._rail_items: dict[str, tuple[tk.Misc, ...]] = {}
        for key, glyph, label in NAV:
            item = tk.Frame(rail, bg=theme.SURFACE, cursor="hand2")
            item.pack(fill="x", padx=theme.px(8), pady=theme.px(2))
            icon = tk.Label(item, text=glyph, bg=theme.SURFACE, font=theme.font(15))
            icon.pack(padx=theme.px(14), pady=(theme.px(8), 0))
            text = tk.Label(item, text=label, bg=theme.SURFACE, font=theme.font(9))
            text.pack(pady=(0, theme.px(8)))
            for widget in (item, icon, text):
                widget.bind("<Button-1>", lambda _, k=key: self.show_page(k))
            self._rail_items[key] = (item, icon, text)

        stop = tk.Frame(rail, bg=theme.SURFACE, cursor="hand2")
        stop.pack(side="bottom", fill="x", pady=(0, theme.px(14)))
        stop_icon = tk.Label(
            stop, text="■", bg=theme.SURFACE, fg=theme.ERROR, font=theme.font(13)
        )
        stop_icon.pack()
        stop_text = tk.Label(
            stop,
            text=f"停止 {self._stop_hotkey}",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=theme.font(9),
        )
        stop_text.pack()
        for widget in (stop, stop_icon, stop_text):
            widget.bind("<Button-1>", lambda _: self._stop_from_button())

    def _build_status_bar(self, initial: str) -> None:
        bar = tk.Frame(self.popup, bg=theme.SURFACE)
        bar.pack(fill="x", side="bottom")
        inner = tk.Frame(bar, bg=theme.SURFACE)
        inner.pack(fill="x", padx=theme.px(14), pady=theme.px(6))
        # Connection and AI state live down here, out of the way until they
        # turn yellow or red.
        self._discord_dot = StatusDot(inner, "啟動中")
        self._discord_dot.pack(side="left")
        self._ai_dot = StatusDot(inner, "AI 待命")
        self._ai_dot.set(theme.OK)
        self._ai_dot.pack(side="left", padx=(theme.px(14), 0))
        self.status_var = tk.StringVar(value=initial or "啟動中…")
        self._status_label = tk.Label(
            inner,
            textvariable=self.status_var,
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
        )
        self._status_label.pack(side="left", fill="x", expand=True, padx=(theme.px(18), 0))
        quit_label = tk.Label(
            inner,
            text="退出",
            bg=theme.SURFACE,
            fg=theme.DIM,
            font=theme.font(9),
            cursor="hand2",
        )
        quit_label.pack(side="right")
        quit_label.bind("<Button-1>", lambda _: self.close())

    # ---- chat page ---------------------------------------------------------------

    def _build_chat_page(
        self,
        parent: tk.Frame,
        regenerate: Callable[[], None] | None,
        send_text: Callable[[str], None] | None,
    ) -> tk.Frame:
        page = tk.Frame(parent, bg=theme.BG)
        inner = tk.Frame(page, bg=theme.BG)
        inner.pack(
            fill="both",
            expand=True,
            padx=theme.px(24),
            pady=(theme.px(18), theme.px(14)),
        )
        modes = [("story", "選項"), ("manual", "打字")]
        if self._character_callback is not None:
            modes.insert(0, ("character", "角色"))
        self._chat_header = ChatHeader(
            inner,
            modes,
            on_mode=lambda key: self.show_page(key),
            on_mood=self._on_mood_pick,
            on_persona=lambda: self.show_page("persona"),
        )
        self._chat_header.pack(fill="x", pady=(0, theme.px(14)))

        # The mode's own controls are packed before the transcript so a small
        # window shrinks the transcript, never the buttons.
        self._chat_stack = tk.Frame(inner, bg=theme.BG)
        self._chat_stack.pack(side="bottom", fill="x")
        self.transcript = Transcript(inner)
        self.transcript.pack(fill="both", expand=True)

        self.story = StoryPanel(
            self._chat_stack,
            on_confirm=self._submit_story_choice,
            on_edit=self._edit_story_choice,
            on_regenerate=regenerate,
            on_mood=self._on_mood,
            on_type=self._type_story_choice if send_text else None,
        )
        self._character_view = CharacterView(
            self._chat_stack,
            on_run=self._set_character_mode,
            on_engagement=self._set_engagement,
            stop_hotkey=self._stop_hotkey,
        )
        self._manual_tab = self._build_manual_page(self._chat_stack)
        self._chat_views = {
            "story": self.story,
            "character": self._character_view,
            "manual": self._manual_tab,
        }
        return page

    # ---- manual page -------------------------------------------------------------

    def _build_manual_page(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=theme.BG)
        compose = card(page, padx=0, pady=0)
        compose.outer.pack(fill="x", pady=(theme.px(12), 0))
        self._manual_compose = compose.outer
        self.input = tk.Text(
            compose,
            height=3,
            wrap="word",
            bg=theme.PANEL,
            fg=theme.TEXT,
            insertbackground=theme.TEXT,
            relief="flat",
            highlightthickness=0,
            padx=theme.px(16),
            pady=theme.px(12),
            font=theme.font(12),
            undo=True,
        )
        self.input.pack(fill="x")
        self.input.bind("<Tab>", self._on_suggestion_tab)
        compose_bar = tk.Frame(compose, bg=theme.PANEL)
        compose_bar.pack(fill="x", padx=theme.px(14), pady=(0, theme.px(10)))
        self._voice_summary = tk.Label(
            compose_bar,
            text="",
            bg=theme.PANEL,
            fg=theme.DIM,
            font=theme.font(9),
            cursor="hand2",
        )
        self._voice_summary.pack(side="left")
        self._voice_summary.bind("<Button-1>", lambda _: self.show_page("voice"))
        Button(compose_bar, "說出來", self._submit_input, kind="primary", size=10).pack(
            side="right"
        )
        tk.Label(
            compose_bar,
            text="Enter 說出 · Shift+Enter 換行",
            bg=theme.PANEL,
            fg=theme.DIM,
            font=theme.font(9),
        ).pack(side="right", padx=theme.px(12))

        # Copilot's four ideas: only there when there is something to pick.
        self._suggest_card = card(page)
        top = tk.Frame(self._suggest_card, bg=theme.PANEL)
        top.pack(fill="x")
        tk.Label(
            top,
            text="Copilot 建議",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(10, "bold"),
        ).pack(side="left")
        hint_row(
            top, (("↑↓", "選"), ("Tab", "填入"), ("Enter", "直接說")), bg=theme.PANEL
        ).pack(side="right")
        self.suggestion_context_var = tk.StringVar(value="")
        wrap_to_width(
            tk.Label(
                self._suggest_card,
                textvariable=self.suggestion_context_var,
                bg=theme.PANEL,
                fg=theme.MUTED,
                font=theme.font(9),
                anchor="w",
                justify="left",
            )
        ).pack(fill="x", pady=(theme.px(4), theme.px(6)))
        self.suggestion_list = tk.Listbox(
            self._suggest_card,
            height=len(REPLY_LANES),
            exportselection=False,
            font=theme.font(11),
            bg=theme.PANEL,
            fg=theme.TEXT,
            selectbackground=theme.PANEL_TOP,
            selectforeground=theme.TEXT,
            highlightthickness=0,
            relief="flat",
            activestyle="none",
            bd=0,
        )
        self.suggestion_list.pack(fill="x")
        self.suggestion_list.bind("<Tab>", self._on_suggestion_tab)
        self.suggestion_list.bind("<Return>", self._on_suggestion_enter)
        self.suggestion_list.bind("<Double-Button-1>", self._on_suggestion_enter)
        self._render_empty_suggestions()

        # Quick phrases are reached with Ctrl+1-9; the list is for editing.
        self._phrases_box = Disclosure(
            page,
            "快捷句",
            "Ctrl+1～9 直接說出前九句；展開可以新增、修改、刪除。",
        )
        self._phrases_box.pack(fill="x", pady=(theme.px(12), 0))
        self.phrase_list = tk.Listbox(
            self._phrases_box.body,
            height=5,
            exportselection=False,
            font=theme.font(10),
            bg=theme.PANEL,
            fg=theme.TEXT,
            selectbackground=theme.PANEL_TOP,
            selectforeground=theme.TEXT,
            highlightthickness=0,
            relief="flat",
            activestyle="none",
            bd=0,
        )
        self.phrase_list.pack(fill="x", pady=(0, theme.px(8)))
        self.phrase_list.bind("<Double-Button-1>", self._on_phrase_double_click)
        controls = tk.Frame(self._phrases_box.body, bg=theme.PANEL)
        controls.pack(fill="x")
        Button(controls, "新增目前文字", self._add_quick_phrase, size=9).pack(
            side="left"
        )
        Button(controls, "載入", self._load_selected_phrase, kind="ghost", size=9).pack(
            side="left", padx=(theme.px(6), 0)
        )
        Button(controls, "更新", self._update_quick_phrase, kind="ghost", size=9).pack(
            side="left", padx=(theme.px(6), 0)
        )
        Button(controls, "刪除", self._delete_quick_phrase, kind="danger", size=9).pack(
            side="right"
        )
        return page

    # ---- voice (a group on the settings page) ----------------------------------------

    def _build_voice_group(
        self, parent: tk.Frame, preferences: UserPreferences
    ) -> None:
        voice = card(parent)
        voice.outer.pack(fill="x", pady=(0, theme.px(12)))
        tk.Label(
            voice,
            text="聲音風格",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(11, "bold"),
        ).pack(anchor="w")
        # Shown when the active persona has its own voice, which then wins.
        self._persona_voice_note = tk.Label(
            voice,
            text="",
            bg=theme.PANEL,
            fg=theme.DIM,
            font=theme.font(9),
            justify="left",
            anchor="w",
        )
        self._persona_voice_note.pack(anchor="w", fill="x", pady=(theme.px(2), theme.px(10)))
        wrap_to_width(self._persona_voice_note)
        chips = tk.Frame(voice, bg=theme.PANEL)
        chips.pack(anchor="w")
        self._voice_chips: dict[str, Chip] = {}
        for index, (key, label) in enumerate(self._style_choices):
            chip = Chip(chips, label, lambda k=key: self._set_style(k), size=10)
            chip.grid(
                row=index // 2,
                column=index % 2,
                sticky="w",
                padx=(0, theme.px(6)),
                pady=theme.px(3),
            )
            self._voice_chips[key] = chip

        tk.Frame(voice, bg=theme.LINE, height=1).pack(fill="x", pady=(theme.px(14), 0))
        top = tk.Frame(voice, bg=theme.PANEL)
        top.pack(fill="x", pady=(theme.px(12), 0))
        tk.Label(
            top, text="語速", bg=theme.PANEL, fg=theme.TEXT, font=theme.font(10)
        ).pack(side="left")
        initial_percent = round(preferences.speech_rate_multiplier * 100)
        self.rate_var = tk.DoubleVar(value=initial_percent)
        self.rate_text_var = tk.StringVar(value=f"{initial_percent}%")
        tk.Label(
            top,
            textvariable=self.rate_text_var,
            bg=theme.PANEL,
            fg=theme.ACCENT_HI,
            font=theme.font(11, "bold"),
        ).pack(side="right")
        row = tk.Frame(voice, bg=theme.PANEL)
        row.pack(fill="x", pady=(theme.px(6), 0))
        self.rate_scale = tk.Scale(
            row,
            from_=MIN_RATE_MULTIPLIER * 100,
            to=MAX_RATE_MULTIPLIER * 100,
            resolution=5,
            orient="horizontal",
            showvalue=False,
            variable=self.rate_var,
            command=self._on_rate_changed,
            # tk.Scale paints the slider knob with ``bg``.
            bg=theme.ACCENT,
            troughcolor=theme.PANEL_TOP,
            activebackground=theme.ACCENT_HI,
            highlightthickness=0,
            sliderrelief="flat",
            bd=0,
            width=theme.px(8),
            sliderlength=theme.px(20),
        )
        self.rate_scale.pack(side="left", fill="x", expand=True)
        Button(row, "重設 100%", self._reset_rate, kind="ghost", size=9).pack(
            side="left", padx=(theme.px(10), 0)
        )
        self.rate_scale.bind("<ButtonRelease-1>", self._persist_rate)
        self.rate_scale.bind("<KeyRelease>", self._persist_rate)
        self._set_style("default")

    def _build_model_info(
        self, parent: tk.Frame, copilot_info: Sequence[tuple[str, str]]
    ) -> None:
        info = card(parent)
        info.outer.pack(fill="x", pady=(0, theme.px(12)))
        tk.Label(
            info,
            text="現在跑的",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(11, "bold"),
        ).pack(anchor="w")
        rows = list(copilot_info) or [("狀態", "未啟用")]
        grid = tk.Frame(info, bg=theme.PANEL)
        grid.pack(fill="x", pady=(theme.px(6), 0))
        for index, (label, value) in enumerate(rows):
            tk.Label(
                grid, text=label, bg=theme.PANEL, fg=theme.DIM, font=theme.font(9), anchor="w"
            ).grid(row=index, column=0, sticky="w", padx=(0, theme.px(16)), pady=1)
            tk.Label(
                grid, text=value, bg=theme.PANEL, fg=theme.MUTED, font=theme.font(9), anchor="w"
            ).grid(row=index, column=1, sticky="w", pady=1)

    # ---- public API --------------------------------------------------------------

    def run(self) -> None:
        try:
            self._hotkeys.start()
        except Exception as exc:
            self.set_status(AppState.ERROR, f"快捷鍵失敗：{exc}")
        self.root.mainloop()

    def set_status(self, state: AppState, message: str) -> None:
        self._actions.put(UIAction("status", state, message))

    def set_suggestions(self, suggestions: ReplySuggestions) -> None:
        self._actions.put(UIAction("suggestions", suggestions=suggestions))

    def set_suggestions_thinking(self, speaker: str, text: str) -> None:
        self._actions.put(UIAction("thinking", message=text, speaker=speaker))

    def add_conversation_turn(self, turn: ConversationTurn) -> None:
        self._actions.put(UIAction("turn", turn=turn))

    def show(self) -> None:
        self._refresh_phrases()
        self.popup.deiconify()
        self.popup.lift()
        self.popup.focus_force()
        self._focus_page()

    def hide(self) -> None:
        self.input.delete("1.0", "end")
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
        story, manual) and the old page names (voice) are accepted too."""
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
        for page_key, (item, icon, text) in self._rail_items.items():
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
                self.status_var.set("角色已暫停")
        self._mode = mode
        self._chat_view = mode
        self._chat_header.set_mode(mode)
        for key, view in self._chat_views.items():
            if key == mode:
                view.pack(fill="x")
            else:
                view.pack_forget()
        if mode in ("story", "manual") and mode != self._chat_mode:
            self._chat_mode = mode
            self._persist_preferences()

    # ---- focus & keys --------------------------------------------------------------

    def _focus_page(self) -> None:
        if self._mode == "story":
            # Chinese IMEs swallow W/A/S/D; arrows keep working if this fails.
            set_ime_enabled(self.popup.winfo_id(), False)
            self.story.focus_panel()
            return
        set_ime_enabled(self.popup.winfo_id(), True)
        if self._mode == "character":
            self._character_view.focus_set()
            return
        if self._mode == "manual":
            if self._latest_suggestions is not None and not self.input.get(
                "1.0", "end-1c"
            ):
                self._select_first_available_suggestion()
                self.suggestion_list.focus_set()
            else:
                self.input.focus_set()

    def _toggle_story_manual(self, _: tk.Event) -> str:
        self.show_page("manual" if self._mode == "story" else "story")
        return "break"

    def _on_popup_key(self, event: tk.Event) -> str | None:
        if self._mode != "story" or event.state & 0x0004:  # leave Ctrl+… alone
            return None
        return "break" if self.story.handle_key(event.keysym) else None

    def _on_quick_phrase_key(self, index: int) -> str | None:
        if self._mode not in ("story", "manual"):
            return None
        return self._send_quick_phrase(index)

    def _on_enter(self, event: tk.Event) -> str | None:
        if self._mode == "story":
            self.story.handle_key("Return")
            return "break"
        if self._mode != "manual":
            return None
        if event.widget is self.suggestion_list:
            return "break"  # the listbox's own binding already handled it
        if event.state & 0x0001:
            self.input.insert("insert", "\n")
            return "break"
        self._submit_input()
        return "break"

    def _submit_input(self) -> None:
        raw = self.input.get("1.0", "end-1c")
        if self._submit_text(raw):
            self._clear_suggestions()
            self.hide()

    # ---- persona -------------------------------------------------------------------

    def _apply_persona(self, persona: Persona, *, announce: bool = True) -> None:
        self._persona_name = persona.name
        if hasattr(self, "_persona_voice_note"):
            self._persona_voice_note.configure(
                text=f"現在由人設「{persona.name}」自己的聲音說話（在人設頁改）；這裡的聲線給沒有設定聲音的人設用。"
                if persona.voice_style() is not None
                else "沒有設定自己聲音的人設、打字和快捷句都用這裡的聲線。"
            )
        subtitle = " ".join(persona.identity.split()) or (
            "中性口吻" if persona.is_blank else ""
        )
        if len(subtitle) > 28:
            subtitle = subtitle[:27] + "…"
        self._chat_header.set_persona(persona.name, subtitle)
        self._chat_header.set_mood(persona.mood)
        self._character_view.set_persona(persona.name)
        if self._apply_persona_callback is not None:
            self._apply_persona_callback(persona)

    def _preview_voice(self, persona: Persona, text: str) -> None:
        if self._preview_callback is None:
            return
        try:
            self._preview_callback(text, persona, self._rate_multiplier())
        except Exception as exc:  # noqa: BLE001 - shown to the user
            self._show_status(AppState.ERROR, f"試聽失敗：{exc}")

    def _toggle_character(self) -> None:
        self._set_character_mode(not self._character_on)

    def _set_character_mode(self, enabled: bool) -> None:
        if self._character_callback is None:
            return
        try:
            self._character_callback(
                enabled, self._voice_style, self._rate_multiplier()
            )
        except Exception as exc:  # noqa: BLE001 - shown to the user, app keeps running
            self._show_status(AppState.ERROR, str(exc))
            return
        self._character_on = enabled
        self._character_view.set_running(enabled)
        self.story.set_character_mode(enabled, self._persona_name)

    def _settings_applied(self, tables: dict[str, dict[str, object]]) -> None:
        # The character view shows the same 開口時機 as the settings page.
        self._character_view.set_engagement(
            str(tables.get("copilot", {}).get("character_engagement", "called"))
        )
        if self._apply_settings_callback is not None:
            self._apply_settings_callback(tables)

    def _set_engagement(self, value: str) -> None:
        """The character view's switch is the settings page's 開口時機."""
        self.settings_panel.set_value("copilot", "character_engagement", value)

    def _on_mood(self, mood: str) -> None:
        self.persona_panel.set_mood(mood)

    def _on_mood_pick(self, mood: str) -> None:
        self.story.set_mood(mood)
        self._on_mood(mood)

    # ---- voice & rate --------------------------------------------------------------

    def _selected_style_key(self) -> str:
        return self._voice_style

    def _set_style(self, key: str) -> None:
        if key not in self._voice_chips:
            key = "default"
        self._voice_style = key
        for chip_key, chip in self._voice_chips.items():
            chip.set_selected(chip_key == key)
        self._update_voice_summary()
        if self._character_on:
            self._set_character_mode(True)  # the character speaks in the new voice

    def _update_voice_summary(self) -> None:
        if hasattr(self, "_voice_summary") and hasattr(self, "rate_var"):
            self._voice_summary.configure(
                text=f"♪ {voice_style_label(self._voice_style)} · 語速 {self._rate_multiplier():.0%}"
            )

    def _rate_multiplier(self) -> float:
        return float(self.rate_var.get()) / 100.0

    def _on_rate_changed(self, value: str) -> None:
        self.rate_text_var.set(f"{float(value):.0f}%")
        self._update_voice_summary()

    def _reset_rate(self) -> None:
        self.rate_var.set(DEFAULT_RATE_MULTIPLIER * 100)
        self._on_rate_changed(str(DEFAULT_RATE_MULTIPLIER * 100))
        self._persist_preferences()

    def _persist_rate(self, _: tk.Event | None = None) -> None:
        self._persist_preferences()
        if self._character_on:
            self._set_character_mode(True)

    def _persist_preferences(self) -> None:
        if self._preference_store is None or not hasattr(self, "rate_var"):
            return
        try:
            self._preference_store.save(
                UserPreferences(
                    speech_rate_multiplier=self._rate_multiplier(),
                    ui_mode=self._chat_mode,
                )
            )
        except PreferenceError as exc:
            if hasattr(self, "status_var"):
                self.status_var.set(str(exc))

    def _stop_from_button(self) -> None:
        self._stop_callback()
        self.status_var.set("已停止並清空佇列")

    # ---- story mode ----------------------------------------------------------------

    def _submit_story_choice(self, text: str) -> bool:
        if not self._submit_text(text):
            return False
        self.hide()
        return True

    def _type_story_choice(self, text: str) -> bool:
        """T: type the chosen reply into the channel's chat instead of saying it."""
        if self._send_text_callback is None:
            return False
        try:
            self._send_text_callback(text)
        except (TextValidationError, ValueError) as exc:
            self.status_var.set(str(exc))
            return False
        self.hide()
        return True

    def _edit_story_choice(self, text: str) -> None:
        self.show_page("manual", focus=False)
        set_ime_enabled(self.popup.winfo_id(), True)
        self.input.delete("1.0", "end")
        self.input.insert("1.0", text)
        self.input.mark_set("insert", "end-1c")
        self.input.focus_set()

    def _submit_text(self, raw: str, voice_style: str | None = None) -> bool:
        try:
            self._submit_callback(
                raw,
                voice_style or self._selected_style_key(),
                self._rate_multiplier(),
            )
        except (TextValidationError, ValueError) as exc:
            self.status_var.set(str(exc))
            return False
        return True

    # ---- suggestions ---------------------------------------------------------------

    def _apply_suggestions(self, suggestions: ReplySuggestions) -> None:
        kept = self._selected_suggestion_index() if suggestions.partial else None
        self._latest_suggestions = suggestions
        self._suggestion_values = [text for _, text in suggestions.items()]
        trigger = " ".join(suggestions.trigger_text.split())
        if len(trigger) > 100:
            trigger = trigger[:99].rstrip() + "…"
        self.suggestion_context_var.set(
            f"回應 {suggestions.trigger_speaker}：{trigger}"
        )
        if not self._suggest_card.outer.winfo_ismapped():
            self._suggest_card.outer.pack(
                fill="x", pady=(theme.px(12), 0), after=self._manual_compose
            )
        self.suggestion_list.delete(0, "end")
        for index, (lane, value) in enumerate(suggestions.items()):
            shown = value or (
                "產生失敗"
                if suggestions.error
                else "思考中…"
                if suggestions.partial
                else "沒有合適的建議"
            )
            self.suggestion_list.insert(
                "end", f"  {lane.key.upper()}｜{shown}"
            )
            self.suggestion_list.itemconfigure(
                index,
                foreground=theme.lane_color(lane.code) if value else theme.DIM,
                selectforeground=theme.lane_color(lane.code) if value else theme.DIM,
            )
        if kept is not None and self._suggestion_values[kept]:
            self.suggestion_list.selection_set(kept)
            self.suggestion_list.activate(kept)
        else:
            self._select_first_available_suggestion()
        self.story.set_suggestions(suggestions)
        if suggestions.error:
            self._ai_dot.set(theme.ERROR, "AI 錯誤")
        elif suggestions.partial:
            self._ai_dot.set(theme.ACCENT_HI, "AI 思考中")
        else:
            self._ai_dot.set(theme.OK, "AI 待命")

        if (
            self._auto_popup_suggestions
            and suggestions.has_any()
            and not self.popup.winfo_viewable()
        ):
            self.popup.deiconify()
            self.popup.lift()

    def _render_empty_suggestions(self) -> None:
        self.suggestion_list.delete(0, "end")
        for index, lane in enumerate(REPLY_LANES):
            self.suggestion_list.insert(
                "end", f"  {lane.key.upper()}｜等待對話…"
            )
            self.suggestion_list.itemconfigure(index, foreground=theme.DIM)

    def _clear_suggestions(self) -> None:
        self._latest_suggestions = None
        self._suggestion_values = [""] * len(REPLY_LANES)
        self.suggestion_context_var.set("")
        self._render_empty_suggestions()
        self._suggest_card.outer.pack_forget()

    def _select_first_available_suggestion(self) -> None:
        self.suggestion_list.selection_clear(0, "end")
        for index, value in enumerate(self._suggestion_values):
            if value:
                self.suggestion_list.selection_set(index)
                self.suggestion_list.activate(index)
                self.suggestion_list.see(index)
                return

    def _selected_suggestion_index(self) -> int | None:
        selected = self.suggestion_list.curselection()
        return int(selected[0]) if selected else None

    def _selected_suggestion_text(self) -> str:
        selected = self.suggestion_list.curselection()
        if selected:
            index = int(selected[0])
            if 0 <= index < len(self._suggestion_values):
                return self._suggestion_values[index]
        for value in self._suggestion_values:
            if value:
                return value
        return ""

    def _on_suggestion_tab(self, _: tk.Event) -> str:
        text = self._selected_suggestion_text()
        if not text:
            self.status_var.set("目前沒有可填入的 Copilot 建議")
            return "break"
        self.input.delete("1.0", "end")
        self.input.insert("1.0", text)
        self.input.mark_set("insert", "end-1c")
        self.input.focus_set()
        return "break"

    def _on_suggestion_enter(self, _: tk.Event) -> str:
        text = self._selected_suggestion_text()
        if not text:
            self.status_var.set("這格沒有安全的建議")
            return "break"
        if self._submit_text(text):
            self._clear_suggestions()
            self.hide()
        return "break"

    # ---- quick phrases -------------------------------------------------------------

    def _send_quick_phrase(self, index: int) -> str:
        if index >= len(self._phrases):
            self.status_var.set(f"Ctrl+{index + 1} 尚未設定快捷句")
            return "break"
        phrase = self._phrases[index]
        if self._submit_text(phrase.text, phrase.voice_style):
            self._clear_suggestions()
            self.hide()
        return "break"

    def _on_phrase_double_click(self, _: tk.Event) -> str:
        index = self._selected_phrase_index()
        if index is not None:
            self._send_quick_phrase(index)
        return "break"

    def _add_quick_phrase(self) -> None:
        store = self._require_phrase_store()
        if store is None:
            return
        try:
            store.add(
                self.input.get("1.0", "end-1c"),
                self._selected_style_key(),
            )
        except QuickPhraseError as exc:
            self.status_var.set(str(exc))
            return
        self._refresh_phrases()
        self.input.delete("1.0", "end")
        self.status_var.set("已新增快捷句")

    def _load_selected_phrase(self) -> None:
        index = self._selected_phrase_index()
        if index is None:
            return
        phrase = self._phrases[index]
        self.input.delete("1.0", "end")
        self.input.insert("1.0", phrase.text)
        self._set_style(phrase.voice_style)
        self.input.focus_set()

    def _update_quick_phrase(self) -> None:
        store = self._require_phrase_store()
        index = self._selected_phrase_index()
        if store is None or index is None:
            return
        try:
            store.update(
                index,
                self.input.get("1.0", "end-1c"),
                self._selected_style_key(),
            )
        except QuickPhraseError as exc:
            self.status_var.set(str(exc))
            return
        self._refresh_phrases(select=index)
        self.status_var.set("已更新快捷句與聲線")

    def _delete_quick_phrase(self) -> None:
        store = self._require_phrase_store()
        index = self._selected_phrase_index()
        if store is None or index is None:
            return
        try:
            store.delete(index)
        except QuickPhraseError as exc:
            self.status_var.set(str(exc))
            return
        self._refresh_phrases()
        self.status_var.set("已刪除快捷句")

    def _selected_phrase_index(self) -> int | None:
        selected = self.phrase_list.curselection()
        if not selected:
            self.status_var.set("請先選擇一個快捷句")
            return None
        return int(selected[0])

    def _require_phrase_store(self) -> QuickPhraseStore | None:
        if self._phrase_store is None:
            self.status_var.set("快捷句儲存尚未設定")
            return None
        return self._phrase_store

    def _refresh_phrases(self, select: int | None = None) -> None:
        if self._phrase_store is None:
            self._phrases = []
        else:
            try:
                self._phrases = self._phrase_store.load()
            except QuickPhraseError as exc:
                self._phrases = []
                if hasattr(self, "status_var"):
                    self.status_var.set(str(exc))

        self.phrase_list.delete(0, "end")
        for index, phrase in enumerate(self._phrases):
            shortcut = f"Ctrl+{index + 1}" if index < 9 else ""
            style = voice_style_label(phrase.voice_style)
            self.phrase_list.insert(
                "end", f"  {shortcut:<7}  {phrase.text}    ♪ {style}"
            )

        if select is not None and 0 <= select < len(self._phrases):
            self.phrase_list.selection_set(select)
            self.phrase_list.see(select)

    # ---- backend → UI ----------------------------------------------------------------

    def _show_status(self, state: AppState | None, message: str) -> None:
        if state is None:
            self.status_var.set(message)
            return
        if state == AppState.ERROR:
            self._status_label.configure(fg=theme.ERROR)
            if "Copilot" in message:
                self._ai_dot.set(theme.ERROR, "AI 錯誤")
            else:
                self._discord_dot.set(theme.ERROR, "連線錯誤")
        else:
            self._status_label.configure(fg=theme.MUTED)
            color, label = _DISCORD_STATES.get(state, (theme.DIM, state.value))
            self._discord_dot.set(color, label)
        self.status_var.set(message)

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
                self.status_var.set("已停止並清空佇列")
            elif action.kind == "status":
                self._show_status(action.state, action.message)
            elif action.kind == "suggestions" and action.suggestions is not None:
                self._apply_suggestions(action.suggestions)
            elif action.kind == "thinking":
                self._ai_dot.set(theme.ACCENT_HI, "AI 思考中")
                self.story.set_thinking(action.speaker, action.message)
            elif action.kind == "turn" and action.turn is not None:
                self.transcript.add_turn(action.turn)
                self.story.add_turn(action.turn)
        self.root.after(50, self._poll_actions)
