from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk

from silenttalk.hotkeys import GlobalHotkeys
from silenttalk.phrases import QuickPhrase, QuickPhraseError, QuickPhraseStore
from silenttalk.state import AppState
from silenttalk.text import TextValidationError
from silenttalk.voice_styles import voice_style_choices, voice_style_label


@dataclass(frozen=True, slots=True)
class UIAction:
    kind: str
    state: AppState | None = None
    message: str = ""


class SilentTalkUI:
    def __init__(
        self,
        speak_hotkey: str,
        stop_hotkey: str,
        submit: Callable[[str, str], None],
        stop_playback: Callable[[], None],
        shutdown: Callable[[], None],
        quick_phrases: QuickPhraseStore | None = None,
    ) -> None:
        self._submit_callback = submit
        self._stop_callback = stop_playback
        self._shutdown_callback = shutdown
        self._phrase_store = quick_phrases
        self._phrases: list[QuickPhrase] = []
        self._actions: queue.SimpleQueue[UIAction] = queue.SimpleQueue()
        self._style_choices = voice_style_choices()
        self._style_by_label = {label: key for key, label in self._style_choices}
        self._label_by_style = {key: label for key, label in self._style_choices}

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

        voice_row = tk.Frame(self.popup)
        voice_row.pack(fill="x", padx=12, pady=(0, 8))
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
            text="（只影響這一句；快捷句會記住自己的聲線）",
        ).pack(side="left", padx=(8, 0))

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

        self.status_var = tk.StringVar(value="啟動中…")
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
        except Exception as exc:  # noqa: BLE001 - UI remains usable when OS hotkeys fail.
            self.set_status(AppState.ERROR, f"快捷鍵失敗：{exc}")
        self.root.mainloop()

    def set_status(self, state: AppState, message: str) -> None:
        self._actions.put(UIAction("status", state, message))

    def show(self) -> None:
        self._refresh_phrases()
        self.popup.deiconify()
        self.popup.lift()
        self.popup.focus_force()
        self.input.focus_set()

    def hide(self) -> None:
        self.input.delete("1.0", "end")
        self.popup.withdraw()

    def close(self) -> None:
        self._hotkeys.stop()
        self._shutdown_callback()
        self.root.destroy()

    def _selected_style_key(self) -> str:
        return self._style_by_label.get(self.voice_style_var.get(), "default")

    def _set_style(self, key: str) -> None:
        self.voice_style_var.set(self._label_by_style.get(key, self._label_by_style["default"]))

    def _stop_from_button(self) -> None:
        self._stop_callback()
        self.status_var.set("已停止並清空佇列")

    def _on_enter(self, event: tk.Event) -> str:
        if event.state & 0x0001:
            self.input.insert("insert", "\n")
            return "break"
        raw = self.input.get("1.0", "end-1c")
        if self._submit_text(raw):
            self.hide()
        return "break"

    def _submit_text(self, raw: str, voice_style: str | None = None) -> bool:
        try:
            self._submit_callback(raw, voice_style or self._selected_style_key())
        except (TextValidationError, ValueError) as exc:
            self.status_var.set(str(exc))
            return False
        return True

    def _send_quick_phrase(self, index: int) -> str:
        if index >= len(self._phrases):
            self.status_var.set(f"Ctrl+{index + 1} 尚未設定快捷句")
            return "break"
        phrase = self._phrases[index]
        if self._submit_text(phrase.text, phrase.voice_style):
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
                self.status_var.set(f"{action.state.value}: {action.message}")
        self.root.after(50, self._poll_actions)
