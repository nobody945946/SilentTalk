"""AI 劇情模式: the conversation as a visual-novel scene with W/A/S/D choices."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from silenttalk import theme
from silenttalk.copilot.persona import MOODS
from silenttalk.copilot.types import (
    REPLY_LANES,
    ConversationTurn,
    ReplyLane,
    ReplySuggestions,
)
from silenttalk.widgets import Chip, card, hint_row

MAX_LOG_TURNS = 60

_KEY_ALIASES = {"up": "w", "left": "a", "down": "s", "right": "d"}
_CONFIRM_KEYS = {"return", "kp_enter", "space"}
# Cross layout: W on top, A/D side by side, S at the bottom.
_PLACEMENT = {"w": (0, 0, 2), "a": (1, 0, 1), "d": (1, 1, 1), "s": (2, 0, 2)}

ConfirmCallback = Callable[[str], bool]
EditCallback = Callable[[str], None]
MoodCallback = Callable[[str], None]


class StoryPanel(tk.Frame):
    """Keyboard-first reply picker. The owning window routes key presses here."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_confirm: ConfirmCallback,
        on_edit: EditCallback,
        on_regenerate: Callable[[], None] | None,
        on_mood: MoodCallback | None = None,
    ) -> None:
        super().__init__(master, bg=theme.BG, takefocus=1, highlightthickness=0)
        self._on_confirm = on_confirm
        self._on_edit = on_edit
        self._on_regenerate = on_regenerate
        self._on_mood = on_mood
        self._lanes = {lane.key: lane for lane in REPLY_LANES}
        self._choices: dict[str, str] = {lane.key: "" for lane in REPLY_LANES}
        self._selected: str | None = None
        self._sent = False
        self._thinking = False
        self._failed = False
        self._thinking_tick = 0
        self._thinking_about = ("", "")
        self._round = 0
        self._speaker_tags: dict[int, str] = {}
        self._log_turns = 0
        self._mood = MOODS[0]

        # ---- scene header --------------------------------------------------
        header = tk.Frame(self, bg=theme.BG)
        header.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(
            header,
            text="劇情模式",
            bg=theme.BG,
            fg=theme.TEXT,
            font=theme.font(14, "bold"),
        ).pack(side="left")
        self._round_var = tk.StringVar(value="序章")
        self._round_label = tk.Label(
            header,
            textvariable=self._round_var,
            bg=theme.PANEL_TOP,
            fg=theme.MUTED,
            font=theme.font(9, "bold"),
            padx=8,
        )
        self._round_label.pack(side="left", padx=(10, 0), pady=(3, 0))

        moods = tk.Frame(header, bg=theme.BG)
        moods.pack(side="right")
        tk.Label(
            moods, text="心情", bg=theme.BG, fg=theme.DIM, font=theme.font(9)
        ).pack(side="left", padx=(0, 6))
        self._mood_chips: dict[str, Chip] = {}
        for mood in MOODS:
            chip = Chip(moods, mood, lambda m=mood: self._pick_mood(m), size=8)
            chip.pack(side="left", padx=(0, 3))
            self._mood_chips[mood] = chip
        self._render_moods()

        # ---- transcript ----------------------------------------------------
        log_card = card(self, bg=theme.SURFACE, padx=0, pady=0)
        log_card.outer.pack(fill="x", padx=18)
        self._log = tk.Text(
            log_card,
            height=6,
            wrap="word",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            relief="flat",
            padx=12,
            pady=8,
            font=theme.font(10),
            cursor="arrow",
            takefocus=0,
            spacing1=2,
            spacing3=2,
        )
        self._log.pack(fill="x")
        self._log.tag_configure(
            "self", foreground=theme.SELF_COLOR, font=theme.font(10, "bold")
        )
        self._log.tag_configure("muted", foreground=theme.DIM)
        for index, color in enumerate(theme.SPEAKER_COLORS):
            self._log.tag_configure(
                f"speaker{index}", foreground=color, font=theme.font(10, "bold")
            )
        self._log.insert("end", "等待 Discord 語音裡有人開口…\n", "muted")
        self._log.configure(state="disabled")

        # ---- dialogue box (visual-novel style) -------------------------------
        dialogue_outer = tk.Frame(self, bg=theme.ACCENT, padx=0, pady=0)
        dialogue_outer.pack(fill="x", padx=18, pady=(12, 0))
        tk.Frame(dialogue_outer, bg=theme.ACCENT, width=4).pack(side="left", fill="y")
        dialogue = tk.Frame(dialogue_outer, bg=theme.PANEL, padx=14, pady=10)
        dialogue.pack(side="left", fill="both", expand=True)
        self._speaker_var = tk.StringVar(value="　")
        self._speaker_label = tk.Label(
            dialogue,
            textvariable=self._speaker_var,
            bg=theme.PANEL,
            fg=theme.ACCENT_HI,
            font=theme.font(10, "bold"),
        )
        self._speaker_label.pack(anchor="w")
        self._line_var = tk.StringVar(value="……")
        tk.Label(
            dialogue,
            textvariable=self._line_var,
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(14),
            justify="left",
            anchor="w",
            wraplength=600,
        ).pack(fill="x", pady=(2, 0))

        self._status_var = tk.StringVar(value="選項會在對方說完話後出現")
        self._status_label = tk.Label(
            self,
            textvariable=self._status_var,
            bg=theme.BG,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
            justify="left",
            wraplength=640,
        )
        self._status_label.pack(fill="x", padx=18, pady=(8, 6))

        # ---- choices ---------------------------------------------------------
        cross = tk.Frame(self, bg=theme.BG)
        cross.pack(fill="x", padx=15)
        cross.columnconfigure(0, weight=1, uniform="choice")
        cross.columnconfigure(1, weight=1, uniform="choice")
        self._cards: dict[str, _ChoiceCard] = {}
        for lane in REPLY_LANES:
            row, column, span = _PLACEMENT.get(lane.key, (3, 0, 2))
            choice = _ChoiceCard(cross, lane, wraplength=560 if span == 2 else 250)
            choice.grid(
                row=row, column=column, columnspan=span, sticky="nsew", padx=3, pady=3
            )
            choice.bind_all_parts(
                "<Button-1>", lambda _, key=lane.key: self._select(key)
            )
            choice.bind_all_parts(
                "<Double-Button-1>", lambda _, key=lane.key: self._confirm(key)
            )
            self._cards[lane.key] = choice

        hint_row(
            self,
            (
                ("W A S D", "選擇"),
                ("再按一次 / Enter", "說出"),
                ("R", "重想"),
                ("E", "拿去改"),
                ("M", "換心情"),
                ("Esc", "收起"),
            ),
        ).pack(fill="x", padx=18, pady=(10, 14))

        self._render_cards()

    # ---- public API (Tk thread only) ---------------------------------------

    def focus_panel(self) -> None:
        self.focus_set()
        if self._selected is None:
            self._select_first_available()

    def set_mood(self, mood: str) -> None:
        self._mood = mood
        self._render_moods()

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
            text = self._choices.get(self._selected or "", "")
            if text:
                self._on_edit(text)
            else:
                self._set_status("先選一個有內容的選項再改寫")
            return True
        if key == "m":
            index = MOODS.index(self._mood) if self._mood in MOODS else -1
            self._pick_mood(MOODS[(index + 1) % len(MOODS)])
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
        self._log.insert("end", f"{name}  ", tag)
        self._log.insert("end", turn.text + "\n")
        self._log_turns += 1
        if self._log_turns > MAX_LOG_TURNS:
            self._log.delete("1.0", "2.0")
            self._log_turns -= 1
        self._log.see("end")
        self._log.configure(state="disabled")

        if not turn.is_self:
            color = theme.SPEAKER_COLORS[
                int(self._speaker_tag(turn.speaker_id)[7:]) % len(theme.SPEAKER_COLORS)
            ]
            self._speaker_var.set(turn.speaker_name)
            self._speaker_label.configure(fg=color)
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
        self._failed = bool(suggestions.error)
        if suggestions.error:
            self._choices = {lane.key: "" for lane in REPLY_LANES}
            self._selected = None
            self._set_status(
                f"產生失敗：{_trim(suggestions.error, 60)}　按 R 重試", error=True
            )
            self._render_cards()
            return

        self._round += 1
        self._round_var.set(f"第 {self._round} 回合")
        self._round_label.configure(bg=theme.ACCENT, fg=theme.ACCENT_INK)
        self._choices = {lane.key: suggestions.text_for(lane) for lane in REPLY_LANES}
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
        return any(self._choices.values()) and not self._sent

    # ---- internals -----------------------------------------------------------

    def _pick_mood(self, mood: str) -> None:
        self.set_mood(mood)
        if self._on_mood is not None:
            self._on_mood(mood)
        self._set_status(f"心情換成「{mood}」，下一次的選項會帶這個語氣　R＝現在就重想")

    def _render_moods(self) -> None:
        for mood, chip in self._mood_chips.items():
            chip.set_selected(mood == self._mood)

    def _speaker_tag(self, speaker_id: int) -> str:
        tag = self._speaker_tags.get(speaker_id)
        if tag is None:
            tag = f"speaker{len(self._speaker_tags) % len(theme.SPEAKER_COLORS)}"
            self._speaker_tags[speaker_id] = tag
        return tag

    def _select(self, key: str) -> None:
        self.focus_set()
        if self._sent:
            self._set_status("這回合已經說過了，等下一句或按 R 重想")
            return
        if not self._choices.get(key):
            lane = self._lanes[key]
            self._set_status(f"{lane.key.upper()}「{lane.label}」這次沒有合適的選項")
        self._selected = key
        self._render_cards()

    def _select_first_available(self) -> None:
        for lane in REPLY_LANES:
            if self._choices.get(lane.key):
                self._selected = lane.key
                self._render_cards()
                return

    def _confirm(self, key: str) -> None:
        text = self._choices.get(key, "")
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
        self._status_label.configure(fg=theme.ERROR if error else theme.MUTED)

    def _render_cards(self) -> None:
        waiting = self._thinking or self._round == 0
        for key, choice in self._cards.items():
            choice.render(
                self._choices.get(key, ""),
                selected=key == self._selected,
                spent=self._sent,
                placeholder="思考中…"
                if self._thinking
                else "……"
                if waiting
                else "—"
                if self._failed
                else "—（這次沒有合適的）",
            )


class _ChoiceCard(tk.Frame):
    """One lane: colored stripe, keycap, lane name, reply text."""

    def __init__(self, master: tk.Misc, lane: ReplyLane, *, wraplength: int) -> None:
        super().__init__(
            master, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.LINE
        )
        self._color = theme.lane_color(lane.code)
        self._tint = theme.mix(theme.PANEL, self._color, 0.16)
        self._stripe = tk.Frame(
            self, bg=theme.mix(theme.PANEL, self._color, 0.45), width=4
        )
        self._stripe.grid(row=0, column=0, rowspan=2, sticky="ns")
        self._keycap = tk.Label(
            self,
            text=lane.key.upper(),
            bg=theme.PANEL_TOP,
            fg=self._color,
            font=theme.font(12, "bold"),
            width=2,
            pady=2,
        )
        self._keycap.grid(
            row=0, column=1, rowspan=2, sticky="n", padx=(10, 10), pady=10
        )
        self._label = tk.Label(
            self,
            text=lane.label,
            bg=theme.PANEL,
            fg=self._color,
            font=theme.font(9, "bold"),
            anchor="w",
        )
        self._label.grid(row=0, column=2, sticky="w", pady=(8, 0))
        self._text = tk.Label(
            self,
            text="",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(12),
            anchor="w",
            justify="left",
            wraplength=wraplength,
        )
        self._text.grid(row=1, column=2, sticky="w", padx=(0, 12), pady=(0, 10))
        self.columnconfigure(2, weight=1)

    def bind_all_parts(
        self, sequence: str, handler: Callable[[tk.Event], object]
    ) -> None:
        for widget in (self, self._stripe, self._keycap, self._label, self._text):
            widget.bind(sequence, handler)
            widget.configure(cursor="hand2")

    def render(
        self, text: str, *, selected: bool, spent: bool, placeholder: str
    ) -> None:
        background = self._tint if selected else theme.PANEL
        if not text:
            foreground, shown = theme.DIM, placeholder
        else:
            foreground, shown = (theme.MUTED if spent else theme.TEXT), text
        live = selected and bool(text) and not spent
        self.configure(
            bg=background,
            highlightbackground=self._color if selected else theme.LINE,
        )
        self._stripe.configure(
            bg=self._color if selected else theme.mix(theme.PANEL, self._color, 0.45)
        )
        self._keycap.configure(
            bg=self._color if live else theme.PANEL_TOP,
            fg=theme.ACCENT_INK if live else self._color,
        )
        self._label.configure(bg=background)
        self._text.configure(bg=background, fg=foreground, text=shown)


def _trim(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"
