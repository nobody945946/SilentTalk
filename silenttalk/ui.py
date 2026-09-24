from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk

from silenttalk.copilot.types import ReplySuggestions
from silenttalk.hotkeys import GlobalHotkeys
from silenttalk.phrases import QuickPhrase, QuickPhraseError, QuickPhraseStore
from silenttalk.preferences import (
    PreferenceError,
    PreferenceStore,
    UserPreferences,
)
from silenttalk.speech_settings import (
    DEFAULT_RATE_MULTIPLIER,
    MAX_RATE_MULTIPLIER,
    MIN_RATE_MULTIPLIER,
)
from silenttalk.state import AppState
from silenttalk.text import TextValidationError
from silenttalk.voice_styles import voice_style_choices, voice_style_label


@dataclass(frozen=True, slots=True)
class UIAction:
    kind: str
    state: AppState | None = None
    message: str = ""
    suggestions: ReplySuggestions | None = None


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
    ) -> None:
        self._submit_callback = submit
        self._stop_callback = stop_playback
        self._shutdown_callback = shutdown
        self._phrase_store = quick_phrases
        self._preference_store = preferences
        self._phrases: list[QuickPhrase] = []
        self._actions: queue.SimpleQueue[UIAction] = queue.SimpleQueue()
        self._style_choices = voice_style_choices()
        self._style_by_label = {label: key for key, label in self._style_choices}
        self._label_by_style = {key: label for key, label in self._style_choices}
        self._auto_popup_suggestions = auto_popup_suggestions
        self._latest_suggestions: ReplySuggestions | None = None
        self._suggestion_values: list[str] = ["", "", ""]

        preference_error = ""
        try:
            initial_preferences = (
                preferences.load() if preferences is not None else UserPreferences()
            )
        except PreferenceError as exc:
            initial_preferences = UserPreferences()
            preference_error = str(exc)

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.popup = tk.Toplevel(self.root)
        self.popup.title("SilentTalk")
        self.popup.attributes("-topmost", True)
        self.popup.resizable(False, False)
        self.popup.protocol("WM_DELETE_WINDOW", self.hide)
        self.popup.bind("<Escape>", lambda _: self.hide())
        self.popup.bind("<Return>", self._on_enter)
        for index in range(9):
            self.popup.bind(
                f"<Control-Key-{index + 1}>",
                lambda event, phrase_index=index: self._send_quick_phrase(
                    phrase_index
                ),
            )

        self.input = tk.Text(
            self.popup,
            width=54,
            height=4,
            wrap="word",
            font=("Microsoft JhengHei UI", 12),
        )
        self.input.pack(padx=12, pady=(12, 6))
        self.input.bind("<Tab>", self._on_suggestion_tab)

        suggestion_frame = tk.LabelFrame(
            self.popup,
            text="Copilot 回覆建議｜↑↓ 選擇・Tab 填入・Enter 直接說",
        )
        suggestion_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.suggestion_context_var = tk.StringVar(value="等待 Discord 對話…")
        tk.Label(
            suggestion_frame,
            textvariable=self.suggestion_context_var,
            anchor="w",
            justify="left",
            wraplength=560,
        ).pack(fill="x", padx=8, pady=(6, 3))

        self.suggestion_list = tk.Listbox(
            suggestion_frame,
            width=72,
            height=3,
            exportselection=False,
            font=("Microsoft JhengHei UI", 10),
        )
        self.suggestion_list.pack(fill="x", padx=8, pady=(0, 7))
        self.suggestion_list.bind("<Tab>", self._on_suggestion_tab)
        self.suggestion_list.bind("<Return>", self._on_suggestion_enter)
        self.suggestion_list.bind("<Double-Button-1>", self._on_suggestion_enter)
        self._render_empty_suggestions()

        voice_row = tk.Frame(self.popup)
        voice_row.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(voice_row, text="聲線：").pack(side="left")
        self.voice_style_var = tk.StringVar(value=self._label_by_style["default"])
        self.voice_style_combo = ttk.Combobox(
            voice_row,
            textvariable=self.voice_style_var,
            values=[label for _, label in self._style_choices],
            state="readonly",
            width=28,
        )
        self.voice_style_combo.pack(side="left")
        tk.Label(
            voice_row,
            text="（快捷句會記住自己的聲線）",
        ).pack(side="left", padx=(8, 0))

        speed_row = tk.Frame(self.popup)
        speed_row.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(speed_row, text="語速：").pack(side="left")
        initial_percent = round(initial_preferences.speech_rate_multiplier * 100)
        self.rate_var = tk.DoubleVar(value=initial_percent)
        self.rate_text_var = tk.StringVar(value=f"{initial_percent}%")
        self.rate_scale = tk.Scale(
            speed_row,
            from_=MIN_RATE_MULTIPLIER * 100,
            to=MAX_RATE_MULTIPLIER * 100,
            resolution=5,
            orient="horizontal",
            showvalue=False,
            variable=self.rate_var,
            length=220,
            command=self._on_rate_changed,
        )
        self.rate_scale.pack(side="left")
        tk.Label(speed_row, textvariable=self.rate_text_var, width=5).pack(side="left")
        tk.Button(
            speed_row,
            text="100%",
            width=6,
            command=self._reset_rate,
        ).pack(side="left", padx=(6, 0))
        tk.Label(
            speed_row,
            text="（套用到手打與所有快捷句）",
        ).pack(side="left", padx=(8, 0))
        self.rate_scale.bind("<ButtonRelease-1>", self._persist_rate)
        self.rate_scale.bind("<KeyRelease>", self._persist_rate)

        phrase_frame = tk.LabelFrame(self.popup, text="快捷句")
        phrase_frame.pack(fill="x", padx=12, pady=(0, 6))

        self.phrase_list = tk.Listbox(
            phrase_frame,
            width=72,
            height=6,
            exportselection=False,
            font=("Microsoft JhengHei UI", 10),
        )
        self.phrase_list.pack(fill="x", padx=8, pady=(8, 4))
        self.phrase_list.bind("<Double-Button-1>", self._on_phrase_double_click)

        phrase_controls = tk.Frame(phrase_frame)
        phrase_controls.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(
            phrase_controls,
            text="新增目前文字",
            command=self._add_quick_phrase,
        ).pack(side="left")
        tk.Button(
            phrase_controls,
            text="載入選取",
            command=self._load_selected_phrase,
        ).pack(side="left", padx=(6, 0))
        tk.Button(
            phrase_controls,
            text="更新選取",
            command=self._update_quick_phrase,
        ).pack(side="left", padx=(6, 0))
        tk.Button(
            phrase_controls,
            text="刪除選取",
            command=self._delete_quick_phrase,
        ).pack(side="right")

        self.status_var = tk.StringVar(value=preference_error or "啟動中…")
        tk.Label(self.popup, textvariable=self.status_var, anchor="w").pack(
            fill="x", padx=12, pady=(0, 6)
        )

        controls = tk.Frame(self.popup)
        controls.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(
            controls,
            text="停止播放 (F9)",
            command=self._stop_from_button,
        ).pack(side="left")
        tk.Button(
            controls,
            text="退出 SilentTalk",
            command=self.close,
        ).pack(side="right")
        self.popup.withdraw()

        self._hotkeys = GlobalHotkeys(
            {
                speak_hotkey: lambda: self._actions.put(UIAction("show")),
                stop_hotkey: lambda: self._actions.put(UIAction("stop")),
            }
        )
        self._refresh_phrases()
        self.root.after(50, self._poll_actions)

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

    def show(self) -> None:
        self._refresh_phrases()
        self.popup.deiconify()
        self.popup.lift()
        self.popup.focus_force()
        if self._latest_suggestions is not None:
            self._select_first_available_suggestion()
            self.suggestion_list.focus_set()
        else:
            self.input.focus_set()

    def hide(self) -> None:
        self.input.delete("1.0", "end")
        self.popup.withdraw()

    def close(self) -> None:
        self._persist_rate()
        self._hotkeys.stop()
        self._shutdown_callback()
        self.root.destroy()

    def _selected_style_key(self) -> str:
        return self._style_by_label.get(self.voice_style_var.get(), "default")

    def _set_style(self, key: str) -> None:
        self.voice_style_var.set(
            self._label_by_style.get(key, self._label_by_style["default"])
        )

    def _rate_multiplier(self) -> float:
        return float(self.rate_var.get()) / 100.0

    def _on_rate_changed(self, value: str) -> None:
        self.rate_text_var.set(f"{float(value):.0f}%")

    def _reset_rate(self) -> None:
        self.rate_var.set(DEFAULT_RATE_MULTIPLIER * 100)
        self._on_rate_changed(str(DEFAULT_RATE_MULTIPLIER * 100))
        self._persist_rate()

    def _persist_rate(self, _: tk.Event | None = None) -> None:
        if self._preference_store is None:
            return
        try:
            self._preference_store.save(
                UserPreferences(speech_rate_multiplier=self._rate_multiplier())
            )
        except PreferenceError as exc:
            if hasattr(self, "status_var"):
                self.status_var.set(str(exc))

    def _stop_from_button(self) -> None:
        self._stop_callback()
        self.status_var.set("已停止並清空佇列")

    def _on_enter(self, event: tk.Event) -> str:
        if event.state & 0x0001:
            self.input.insert("insert", "\n")
            return "break"
        raw = self.input.get("1.0", "end-1c")
        if self._submit_text(raw):
            self._clear_suggestions()
            self.hide()
        return "break"

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

    def _apply_suggestions(self, suggestions: ReplySuggestions) -> None:
        self._latest_suggestions = suggestions
        self._suggestion_values = [
            suggestions.agree,
            suggestions.disagree,
            suggestions.humor,
        ]
        trigger = " ".join(suggestions.trigger_text.split())
        if len(trigger) > 100:
            trigger = trigger[:99].rstrip() + "…"
        self.suggestion_context_var.set(
            f"{suggestions.trigger_speaker}：{trigger}"
        )
        self.suggestion_list.delete(0, "end")
        labels = ("同意", "反對", "玩笑／打圓場")
        for label, value in zip(labels, self._suggestion_values, strict=True):
            shown = value or "— 沒有安全的建議 —"
            self.suggestion_list.insert("end", f"{label}｜{shown}")
        self._select_first_available_suggestion()

        if self._auto_popup_suggestions and not self.popup.winfo_viewable():
            self.popup.deiconify()
            self.popup.lift()

    def _render_empty_suggestions(self) -> None:
        self.suggestion_list.delete(0, "end")
        self.suggestion_list.insert("end", "同意｜等待對話…")
        self.suggestion_list.insert("end", "反對｜等待對話…")
        self.suggestion_list.insert("end", "玩笑／打圓場｜等待對話…")

    def _clear_suggestions(self) -> None:
        self._latest_suggestions = None
        self._suggestion_values = ["", "", ""]
        self.suggestion_context_var.set("等待 Discord 對話…")
        self._render_empty_suggestions()

    def _select_first_available_suggestion(self) -> None:
        self.suggestion_list.selection_clear(0, "end")
        for index, value in enumerate(self._suggestion_values):
            if value:
                self.suggestion_list.selection_set(index)
                self.suggestion_list.activate(index)
                self.suggestion_list.see(index)
                return

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
            shortcut = f"Ctrl+{index + 1}" if index < 9 else "      "
            style = voice_style_label(phrase.voice_style)
            self.phrase_list.insert(
                "end", f"{shortcut:<7} [{style}] {phrase.text}"
            )

        if select is not None and 0 <= select < len(self._phrases):
            self.phrase_list.selection_set(select)
            self.phrase_list.see(select)

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
                if action.state is not None:
                    self.status_var.set(f"{action.state.value}: {action.message}")
                else:
                    self.status_var.set(action.message)
            elif action.kind == "suggestions" and action.suggestions is not None:
                self._apply_suggestions(action.suggestions)
        self.root.after(50, self._poll_actions)
