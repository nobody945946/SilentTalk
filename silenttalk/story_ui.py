"""AI 劇情模式: the conversation as a visual-novel scene with W/A/S/D choices."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from silenttalk.copilot.types import (
    REPLY_LANES,
    ConversationTurn,
    ReplyLane,
    ReplySuggestions,
)

FONT = "Microsoft JhengHei UI"
BG = "#15171e"
PANEL = "#1e222c"
CARD = "#262b38"
CARD_SELECTED = "#34405c"
ACCENT = "#f2c14e"
TEXT = "#eceff6"
MUTED = "#8a93a8"
DIM = "#5b6273"
SELF_COLOR = "#7fdca4"
ERROR_COLOR = "#ff8a80"
SPEAKER_COLORS = ("#8fc7ff", "#ffb38a", "#d7a6ff", "#8ae0e0", "#ffd98a")

MAX_LOG_TURNS = 60

_KEY_ALIASES = {"up": "w", "left": "a", "down": "s", "right": "d"}
_CONFIRM_KEYS = {"return", "kp_enter", "space"}

ConfirmCallback = Callable[[str], bool]
EditCallback = Callable[[str], None]


class StoryPanel(tk.Frame):
    """Keyboard-first reply picker. The owning window routes key presses here."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_confirm: ConfirmCallback,
        on_edit: EditCallback,
        on_regenerate: Callable[[], None] | None,
    ) -> None:
        super().__init__(master, bg=BG, takefocus=1, highlightthickness=0)
        self._on_confirm = on_confirm
        self._on_edit = on_edit
        self._on_regenerate = on_regenerate
        self._lanes = {lane.key: lane for lane in REPLY_LANES}
        self._options: dict[str, str] = {lane.key: "" for lane in REPLY_LANES}
        self._selected: str | None = None
        self._sent = False
        self._thinking = False
        self._thinking_tick = 0
        self._thinking_about = ("", "")
        self._round = 0
        self._speaker_tags: dict[int, str] = {}
        self._log_turns = 0

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(
            header,
            text="▍AI 劇情模式",
            bg=BG,
            fg=ACCENT,
            font=(FONT, 12, "bold"),
        ).pack(side="left")
        self._round_var = tk.StringVar(value="序章")
        tk.Label(
            header, textvariable=self._round_var, bg=BG, fg=MUTED, font=(FONT, 10)
        ).pack(side="right")

        self._log = tk.Text(
            self,
            height=7,
            width=60,
            wrap="word",
            bg=PANEL,
            fg=TEXT,
            relief="flat",
            padx=10,
            pady=6,
            font=(FONT, 10),
            cursor="arrow",
            takefocus=0,
        )
        self._log.pack(fill="x", padx=12)
        self._log.tag_configure("self", foreground=SELF_COLOR, font=(FONT, 10, "bold"))
        self._log.tag_configure("muted", foreground=MUTED)
        for index, color in enumerate(SPEAKER_COLORS):
            self._log.tag_configure(
                f"speaker{index}", foreground=color, font=(FONT, 10, "bold")
            )
        self._log.insert("end", "等待 Discord 語音裡有人開口…\n", "muted")
        self._log.configure(state="disabled")

        dialogue = tk.Frame(
            self, bg=PANEL, highlightbackground=ACCENT, highlightthickness=1
        )
        dialogue.pack(fill="x", padx=12, pady=(10, 6))
        self._speaker_var = tk.StringVar(value="　")
        tk.Label(
            dialogue,
            textvariable=self._speaker_var,
            bg=ACCENT,
            fg=BG,
            font=(FONT, 10, "bold"),
            padx=8,
        ).pack(anchor="w", padx=10, pady=(8, 2))
        self._line_var = tk.StringVar(value="……")
        tk.Label(
            dialogue,
            textvariable=self._line_var,
            bg=PANEL,
            fg=TEXT,
            font=(FONT, 13),
            justify="left",
            anchor="w",
            wraplength=560,
        ).pack(fill="x", padx=12, pady=(0, 10))

        self._status_var = tk.StringVar(value="選項會在對方說完話後出現")
        self._status_label = tk.Label(
            self,
            textvariable=self._status_var,
            bg=BG,
            fg=MUTED,
            font=(FONT, 10),
            anchor="w",
            justify="left",
            wraplength=580,
        )
        self._status_label.pack(fill="x", padx=12, pady=(2, 4))

        cross = tk.Frame(self, bg=BG)
        cross.pack(fill="x", padx=12, pady=(0, 6))
        cross.columnconfigure(0, weight=1, uniform="choice")
        cross.columnconfigure(1, weight=1, uniform="choice")
        placement = {"w": (0, 0, 2), "a": (1, 0, 1), "d": (1, 1, 1), "s": (2, 0, 2)}
        self._cards: dict[str, _ChoiceCard] = {}
        for lane in REPLY_LANES:
            row, column, span = placement[lane.key]
            card = _ChoiceCard(cross, lane, wraplength=520 if span == 2 else 250)
            card.grid(
                row=row, column=column, columnspan=span, sticky="nsew", padx=3, pady=3
            )
            card.bind_all_parts("<Button-1>", lambda _, key=lane.key: self._select(key))
            card.bind_all_parts(
                "<Double-Button-1>", lambda _, key=lane.key: self._confirm(key)
            )
            self._cards[lane.key] = card

        tk.Label(
            self,
            text=(
                "W/A/S/D 或方向鍵選擇・同一鍵再按一次或 Enter/Space 說出\n"
                "R 重想・E 拿去改寫・Ctrl+Tab 切回手動・Esc 收起"
                "（聲線與語速沿用手動分頁）"
            ),
            bg=BG,
            fg=DIM,
            font=(FONT, 9),
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(2, 10))

        self._render_cards()

    # ---- public API (Tk thread only) ---------------------------------------

    def focus_panel(self) -> None:
        self.focus_set()
        if self._selected is None:
            self._select_first_available()

    def handle_key(self, keysym: str) -> bool:
        key = keysym.lower()
        key = _KEY_ALIASES.get(key, key)
        if key in self._lanes:
            if key == self._selected and not self._sent:
                self._confirm(key)
            else:
                self._select(key)
            return True
        if key in _CONFIRM_KEYS:
            if self._selected is not None:
                self._confirm(self._selected)
            return True
        if key == "r":
            self._regenerate()
            return True
        if key == "e":
            text = self._options.get(self._selected or "", "")
            if text:
                self._on_edit(text)
            else:
                self._set_status("先選一個有內容的選項再改寫")
            return True
        return False

    def add_turn(self, turn: ConversationTurn) -> None:
        self._log.configure(state="normal")
        if self._log_turns == 0:
            self._log.delete("1.0", "end")
        if turn.is_self:
            name, tag = "你", "self"
        else:
            name, tag = turn.speaker_name, self._speaker_tag(turn.speaker_id)
        self._log.insert("end", f"{name}：", tag)
        self._log.insert("end", turn.text + "\n")
        self._log_turns += 1
        if self._log_turns > MAX_LOG_TURNS:
            self._log.delete("1.0", "2.0")
            self._log_turns -= 1
        self._log.see("end")
        self._log.configure(state="disabled")

        if not turn.is_self:
            self._speaker_var.set(turn.speaker_name)
            self._line_var.set(turn.text)

    def set_thinking(self, speaker: str, text: str) -> None:
        was_thinking = self._thinking
        self._thinking = True
        self._thinking_about = (speaker, text)
        self._render_cards()
        if not was_thinking:
            self._thinking_tick = 0
            self._tick_thinking()

    def set_suggestions(self, suggestions: ReplySuggestions) -> None:
        self._thinking = False
        self._sent = False
        if suggestions.error:
            self._options = {lane.key: "" for lane in REPLY_LANES}
            self._selected = None
            self._set_status(
                f"產生失敗：{_trim(suggestions.error, 60)}　按 R 重試", error=True
            )
            self._render_cards()
            return

        self._round += 1
        self._round_var.set(f"第 {self._round} 回合")
        self._options = {lane.key: suggestions.text_for(lane) for lane in REPLY_LANES}
        self._selected = None
        self._select_first_available()
        if not suggestions.has_any():
            self._set_status("這句沒有想到合適的回覆，按 R 重想")
        elif suggestions.trigger_text != self._line_var.get():
            # The chat moved on while generating; say which line these answer.
            self._set_status(
                f"回應較早的一句 {suggestions.trigger_speaker}："
                f"「{_trim(suggestions.trigger_text, 36)}」　R＝針對最新一句重想"
            )
        else:
            self._set_status("選擇你的回應")
        self._render_cards()

    def has_choice(self) -> bool:
        return any(self._options.values()) and not self._sent

    # ---- internals -----------------------------------------------------------

    def _speaker_tag(self, speaker_id: int) -> str:
        tag = self._speaker_tags.get(speaker_id)
        if tag is None:
            tag = f"speaker{len(self._speaker_tags) % len(SPEAKER_COLORS)}"
            self._speaker_tags[speaker_id] = tag
        return tag

    def _select(self, key: str) -> None:
        self.focus_set()
        if self._sent:
            self._set_status("這回合已經說過了，等下一句或按 R 重想")
            return
        if not self._options.get(key):
            lane = self._lanes[key]
            self._set_status(f"{lane.key.upper()}「{lane.label}」這次沒有合適的選項")
        self._selected = key
        self._render_cards()

    def _select_first_available(self) -> None:
        for lane in REPLY_LANES:
            if self._options.get(lane.key):
                self._selected = lane.key
                self._render_cards()
                return

    def _confirm(self, key: str) -> None:
        text = self._options.get(key, "")
        if self._sent or not text:
            self._select(key)
            return
        self._selected = key
        if self._on_confirm(text):
            self._sent = True
            self._set_status(f"已說出：「{_trim(text, 40)}」— 等下一句")
        self._render_cards()

    def _regenerate(self) -> None:
        if self._on_regenerate is None:
            self._set_status("Copilot 未啟用，無法重想", error=True)
            return
        try:
            self._on_regenerate()
        except RuntimeError as exc:
            self._set_status(str(exc), error=True)

    def _tick_thinking(self) -> None:
        if not self._thinking:
            return
        speaker, text = self._thinking_about
        dots = "．" * (1 + self._thinking_tick % 3)
        self._set_status(f"正在替「{speaker}：{_trim(text, 30)}」想選項{dots}")
        self._thinking_tick += 1
        self.after(400, self._tick_thinking)

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self._status_var.set(message)
        self._status_label.configure(fg=ERROR_COLOR if error else MUTED)

    def _render_cards(self) -> None:
        waiting = self._thinking or self._round == 0
        for key, card in self._cards.items():
            card.render(
                self._options.get(key, ""),
                selected=key == self._selected,
                spent=self._sent,
                placeholder="……" if waiting else "—（這次沒有合適的）",
            )


class _ChoiceCard(tk.Frame):
    def __init__(self, master: tk.Misc, lane: ReplyLane, *, wraplength: int) -> None:
        super().__init__(
            master, bg=CARD, highlightthickness=2, highlightbackground=CARD
        )
        self._keycap = tk.Label(
            self,
            text=lane.key.upper(),
            bg=MUTED,
            fg=BG,
            font=(FONT, 11, "bold"),
            width=2,
        )
        self._keycap.grid(row=0, column=0, rowspan=2, sticky="n", padx=(8, 8), pady=8)
        self._label = tk.Label(
            self, text=lane.label, bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w"
        )
        self._label.grid(row=0, column=1, sticky="w", pady=(6, 0))
        self._text = tk.Label(
            self,
            text="",
            bg=CARD,
            fg=TEXT,
            font=(FONT, 11),
            anchor="w",
            justify="left",
            wraplength=wraplength,
        )
        self._text.grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 8))
        self.columnconfigure(1, weight=1)

    def bind_all_parts(
        self, sequence: str, handler: Callable[[tk.Event], object]
    ) -> None:
        for widget in (self, self._keycap, self._label, self._text):
            widget.bind(sequence, handler)

    def render(
        self, text: str, *, selected: bool, spent: bool, placeholder: str
    ) -> None:
        background = CARD_SELECTED if selected else CARD
        if not text:
            foreground, shown = DIM, placeholder
        else:
            foreground, shown = (MUTED if spent else TEXT), text
        self.configure(bg=background, highlightbackground=ACCENT if selected else CARD)
        self._keycap.configure(bg=ACCENT if selected and text else MUTED)
        self._label.configure(bg=background)
        self._text.configure(bg=background, fg=foreground, text=shown)


def _trim(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"
