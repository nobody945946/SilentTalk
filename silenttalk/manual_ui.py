from __future__ import annotations

import tkinter as tk

from silenttalk import theme
from silenttalk.conversation import REPLY_LANES, ReplySuggestions
from silenttalk.phrases import QuickPhraseError, QuickPhraseStore
from silenttalk.voice_styles import voice_style_label
from silenttalk.widgets import (
    Button,
    Disclosure,
    card,
    hint_row,
    wrap_to_width,
)

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
        self._latest_suggestions = None
        self._suggestion_values = [""] * len(REPLY_LANES)
        self.frame = self._build_manual_page(parent)
        self._refresh_phrases()

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

    def _submit_input(self) -> None:
        raw = self.input.get("1.0", "end-1c")
        if self._submit_text(raw):
            self._clear_suggestions()
            self.hide()

    def _render_empty_suggestions(self) -> None:
        self.suggestion_list.delete(0, "end")
        for index, lane in enumerate(REPLY_LANES):
            self.suggestion_list.insert("end", f"  {lane.key.upper()}｜等待對話…")
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
            self.suggestion_list.insert("end", f"  {lane.key.upper()}｜{shown}")
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
