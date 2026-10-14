from __future__ import annotations

import tkinter as tk

from silenttalk import theme
from silenttalk.phrases import QuickPhraseError, QuickPhraseStore
from silenttalk.voice_styles import voice_style_label
from silenttalk.widgets.button import Button
from silenttalk.widgets.disclosure import Disclosure
from silenttalk.widgets.layout import card

# Three places, like a phone's tab bar: talking, who you are, and settings.


class ManualSpeechPanel:
    def __init__(
        self, parent, *, phrases, status, submit, hide, navigate, get_style, set_style
    ):
        self._phrase_store = phrases
        self.status_var = status
        self._submit_text, self.hide, self.show_page = submit, hide, navigate
        self._selected_style_key, self._set_style = get_style, set_style
        self._phrases = []
        self.frame = self._build_manual_page(parent)
        self._refresh_phrases()

    def _build_manual_page(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=theme.BG)
        compose = card(page, padx=0, pady=0)
        compose.outer.pack(fill="x", pady=(theme.px(12), 0))
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

    def _submit_input(self) -> None:
        raw = self.input.get("1.0", "end-1c")
        if self._submit_text(raw):
            self.hide()

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
            shortcut = f"Ctrl+{index + 1}" if index < 9 else ""
            style = voice_style_label(phrase.voice_style)
            self.phrase_list.insert(
                "end", f"  {shortcut:<7}  {phrase.text}    ♪ {style}"
            )

        if select is not None and 0 <= select < len(self._phrases):
            self.phrase_list.selection_set(select)
            self.phrase_list.see(select)
