"""選項模式: the latest line as a visual-novel dialogue box with W/A/S/D choices.

The running transcript is not here: the chat page shows one transcript for
every mode (silenttalk/chat_ui.py). Mood and the key reference live in the
chat page header, so this panel is only the choice itself.
"""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable

from silenttalk import theme
from silenttalk.conversation import (
    REPLY_LANES,
    ConversationTurn,
    ReplyLane,
    ReplySuggestions,
)
from silenttalk.persona import MOODS
from silenttalk.widgets import hint_row, wrap_to_width

# Choices you are reading or picking from stay put this long after they
# appeared or after your last key; a newer round waits behind them (R shows
# it at once). In a busy channel every line brings a new round, faster than
# anyone can read one.
HOLD_SECONDS = 6.0

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
        on_type: ConfirmCallback | None = None,
    ) -> None:
        super().__init__(master, bg=theme.BG, takefocus=1, highlightthickness=0)
        self._on_confirm = on_confirm
        self._on_edit = on_edit
        self._on_regenerate = on_regenerate
        self._on_mood = on_mood
        self._on_type = on_type
        self._lanes = {lane.key: lane for lane in REPLY_LANES}
        self._choices: dict[str, str] = {lane.key: "" for lane in REPLY_LANES}
        self._selected: str | None = None
        self._sent = False
        self._thinking = False
        self._failed = False
        self._fresh = True
        self._character = False
        self._thinking_tick = 0
        self._thinking_about = ("", "")
        self._round = 0
        self._mood = MOODS[0]
        self._shown_at = 0.0
        self._touched_at = 0.0
        # A round that started while the shown one was held: its latest
        # update waits in _incoming until the hold ends or R is pressed.
        self._hidden = False
        self._incoming: ReplySuggestions | None = None
        self._reveal_job: str | None = None
        self._latest_line = ""
        self._colors: dict[str, str] = {}

        # ---- dialogue box (visual-novel style) -------------------------------
        dialogue_outer = tk.Frame(self, bg=theme.ACCENT, padx=0, pady=0)
        dialogue_outer.pack(fill="x", pady=(theme.px(12), 0))
        tk.Frame(dialogue_outer, bg=theme.ACCENT, width=theme.px(3)).pack(
            side="left", fill="y"
        )
        dialogue = tk.Frame(
            dialogue_outer, bg=theme.PANEL, padx=theme.px(16), pady=theme.px(12)
        )
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
        wrap_to_width(
            tk.Label(
                dialogue,
                textvariable=self._line_var,
                bg=theme.PANEL,
                fg=theme.TEXT,
                font=theme.font(14),
                justify="left",
                anchor="w",
            )
        ).pack(fill="x", pady=(theme.px(2), 0))

        self._status_var = tk.StringVar(value="選項會在對方說完話後出現")
        self._status_label = tk.Label(
            self,
            textvariable=self._status_var,
            bg=theme.BG,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
            justify="left",
        )
        self._status_label.pack(fill="x", pady=(theme.px(10), theme.px(6)))
        wrap_to_width(self._status_label)

        # ---- choices ---------------------------------------------------------
        cross = tk.Frame(self, bg=theme.BG)
        cross.pack(fill="x", padx=(0, 0))
        cross.columnconfigure(0, weight=1, uniform="choice")
        cross.columnconfigure(1, weight=1, uniform="choice")
        self._cards: dict[str, _ChoiceCard] = {}
        for lane in REPLY_LANES:
            row, column, span = _PLACEMENT.get(lane.key, (3, 0, 2))
            choice = _ChoiceCard(cross, lane)
            choice.grid(
                row=row,
                column=column,
                columnspan=span,
                sticky="nsew",
                padx=(0 if column == 0 else theme.px(3), 0 if column + span == 2 else theme.px(3)),
                pady=theme.px(3),
            )
            choice.bind_all_parts(
                "<Button-1>", lambda _, key=lane.key: self._select(key)
            )
            choice.bind_all_parts(
                "<Double-Button-1>", lambda _, key=lane.key: self._confirm(key)
            )
            self._cards[lane.key] = choice

        # The key reference folds away: after a few rounds nobody reads it.
        keys = tk.Label(
            self,
            text="⌨ 快捷鍵",
            bg=theme.BG,
            fg=theme.DIM,
            font=theme.font(9),
            cursor="hand2",
        )
        keys.pack(anchor="w", pady=(theme.px(10), 0))
        self._hints = hint_row(
            self,
            (
                ("W A S D", "選擇"),
                ("再按一次 / Enter", "說出"),
                ("R", "重想"),
                ("E", "拿去改"),
                ("T", "打字送出"),
                ("M", "換心情"),
                ("Esc", "收起"),
            ),
        )
        keys.bind("<Button-1>", lambda _: self._toggle_hints())

        self._render_cards()

    # ---- public API (Tk thread only) ---------------------------------------

    def focus_panel(self) -> None:
        self.focus_set()
        if self._selected is None:
            self._select_first_available()

    def set_mood(self, mood: str) -> None:
        self._mood = mood

    def _toggle_hints(self) -> None:
        if self._hints.winfo_ismapped():
            self._hints.pack_forget()
        else:
            self._hints.pack(fill="x", pady=(theme.px(6), 0))

    def handle_key(self, keysym: str) -> bool:
        key = keysym.lower()
        key = _KEY_ALIASES.get(key, key)
        self._touched_at = time.monotonic()
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
        if key == "t":
            self._confirm(self._selected or "", typed=True)
            return True
        if key == "m":
            index = MOODS.index(self._mood) if self._mood in MOODS else -1
            self._pick_mood(MOODS[(index + 1) % len(MOODS)])
            return True
        return False

    def add_turn(self, turn: ConversationTurn) -> None:
        """The dialogue box shows the line the choices answer, so a newer
        line only replaces it while there is nothing to pick from."""
        if turn.is_self:
            return
        self._colors[turn.speaker_name] = theme.speaker_color(turn.speaker_id)
        self._latest_line = turn.text
        if not self.has_choice():
            self._show_line(turn.speaker_name, turn.text)

    def set_thinking(self, speaker: str, text: str) -> None:
        if self._held():
            self._hidden = True
            self._set_status(f"{speaker} 又說了話，新選項想好前先看這組")
            self._schedule_reveal()
            return
        # A round still waiting unseen is superseded by this one.
        self._hidden = False
        self._incoming = None
        was_thinking = self._thinking
        self._thinking = True
        self._fresh = True
        self._thinking_about = (speaker, text)
        self._render_cards()
        if not was_thinking:
            self._thinking_tick = 0
            self._tick_thinking()

    def set_suggestions(self, suggestions: ReplySuggestions) -> None:
        """Partial results (streamed lane by lane) fill in the same round; the
        user may already pick one, and later updates keep that choice. A new
        round waits while the shown one is held (HOLD_SECONDS)."""
        if self._hidden:
            self._incoming = suggestions
            if not suggestions.partial and suggestions.has_any():
                self._set_status(
                    f"{suggestions.trigger_speaker} 又說了話，新選項好了"
                    "　R＝換過去，停手幾秒會自己換"
                )
            return
        self._apply(suggestions)

    def _apply(self, suggestions: ReplySuggestions) -> None:
        fresh = self._fresh
        self._fresh = not suggestions.partial
        self._thinking = suggestions.partial
        if fresh:
            self._sent = False
            self._selected = None
        self._failed = bool(suggestions.error)
        if suggestions.error:
            self._choices = {lane.key: "" for lane in REPLY_LANES}
            self._selected = None
            self._set_status(
                f"產生失敗：{_trim(suggestions.error, 60)}　按 R 重試", error=True
            )
            self._render_cards()
            return

        if fresh:
            self._round += 1
            self._shown_at = time.monotonic()
            self._show_line(suggestions.trigger_speaker, suggestions.trigger_text)
        self._choices = {lane.key: suggestions.text_for(lane) for lane in REPLY_LANES}
        if self._selected is None or not self._choices.get(self._selected):
            self._selected = None
            self._select_first_available()
        if suggestions.partial:
            self._render_cards()
            return
        if not suggestions.has_any():
            self._set_status("這句沒有想到合適的回覆，按 R 重想")
        elif self._latest_line and suggestions.trigger_text != self._latest_line:
            # The chat moved on while generating; the box shows the line
            # these answer, the transcript the rest.
            self._set_status("選擇你的回應（之後又有人說話了，R＝針對最新一句重想）")
        else:
            self._set_status("選擇你的回應")
        self._render_cards()

    def has_choice(self) -> bool:
        return any(self._choices.values()) and not self._sent

    # ---- internals -----------------------------------------------------------

    def _held(self) -> bool:
        """Someone may be reading or picking from the shown choices."""
        if not self.has_choice() or self._character:
            return False
        last = max(self._shown_at, self._touched_at)
        return time.monotonic() - last < HOLD_SECONDS

    def _schedule_reveal(self) -> None:
        if self._reveal_job is None:
            self._reveal_job = self.after(300, self._reveal_when_free)

    def _reveal_when_free(self) -> None:
        self._reveal_job = None
        if not self._hidden:
            return
        if self._held():
            self._schedule_reveal()
            return
        self._reveal()

    def _reveal(self) -> None:
        """Show the waiting round: its latest update, or 'thinking' if none
        has arrived yet. Later updates of that round then flow in as usual."""
        self._hidden = False
        incoming, self._incoming = self._incoming, None
        self._fresh = True
        if incoming is None:
            self._choices = {lane.key: "" for lane in REPLY_LANES}
            self._selected = None
            self._thinking = True
            self._thinking_tick = 0
            self._render_cards()
            self._tick_thinking()
            return
        was_thinking = self._thinking
        self._apply(incoming)
        if self._thinking and not was_thinking:
            self._thinking_tick = 0
            self._tick_thinking()

    def _show_line(self, speaker: str, text: str) -> None:
        self._speaker_var.set(speaker)
        self._speaker_label.configure(fg=self._colors.get(speaker, theme.ACCENT_HI))
        self._line_var.set(text)

    def _pick_mood(self, mood: str) -> None:
        self.set_mood(mood)
        if self._on_mood is not None:
            self._on_mood(mood)
        self._set_status(f"心情換成「{mood}」，下一次的選項會帶這個語氣　R＝現在就重想")

    def _select(self, key: str) -> None:
        self.focus_set()
        self._touched_at = time.monotonic()
        if self._sent:
            self._set_status("這回合已經說過了，等下一句或按 R 重想")
            return
        if not self._choices.get(key):
            self._set_status(f"{key.upper()} 這次沒有選項")
        self._selected = key
        self._render_cards()

    def _select_first_available(self) -> None:
        for lane in REPLY_LANES:
            if self._choices.get(lane.key):
                self._selected = lane.key
                self._render_cards()
                return

    def _confirm(self, key: str, *, typed: bool = False) -> None:
        """Send the chosen reply: spoken by default, typed into the channel's
        chat with T (same option, different medium)."""
        text = self._choices.get(key, "")
        if typed and self._on_type is None:
            self._set_status("打字功能未啟用（config.toml 的 [discord] text_chat）")
            return
        if self._sent or not text:
            self._select(key)
            return
        self._selected = key
        send = self._on_type if typed else self._on_confirm
        assert send is not None
        if send(text):
            self._sent = True
            verb = "已打出" if typed else "已說出"
            self._set_status(f"{verb}：「{_trim(text, 40)}」— 等下一句")
        self._render_cards()

    def _regenerate(self) -> None:
        if self._hidden:
            # A newer round is waiting: R shows it instead of thinking again.
            self._reveal()
            return
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
        if not self._fresh and any(self._choices.values()):
            # Some lanes of this round are in; the rest are still streaming.
            if not self._sent:
                self._set_status(f"可以先選了，其他選項還在想{dots}")
        else:
            self._set_status(f"正在替「{speaker}：{_trim(text, 30)}」想選項{dots}")
        self._thinking_tick += 1
        self.after(400, self._tick_thinking)

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self._status_var.set(message)
        self._status_label.configure(fg=theme.ERROR if error else theme.MUTED)

    def set_character_mode(self, enabled: bool, name: str) -> None:
        """While the bot plays the persona by itself there are no choices to
        pick; the conversation log shows what it said."""
        self._character = enabled
        if enabled:
            self._choices = {lane.key: "" for lane in REPLY_LANES}
            self._selected = None
            self._set_status(f"{name or '角色'} 正在自己聊天")
        else:
            self._set_status("回到選項模式：下一句開始會出現四個選項")
        self._render_cards()

    def _render_cards(self) -> None:
        waiting = self._thinking or self._round == 0
        for key, choice in self._cards.items():
            if self._character:
                choice.render("", selected=False, spent=True, placeholder="角色模式中")
                continue
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
    """One option: colored stripe, keycap, reply text."""

    def __init__(self, master: tk.Misc, lane: ReplyLane) -> None:
        super().__init__(
            master, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.PANEL
        )
        self._color = theme.lane_color(lane.code)
        self._tint = theme.mix(theme.PANEL, self._color, 0.16)
        self._stripe = tk.Frame(
            self, bg=theme.mix(theme.PANEL, self._color, 0.45), width=theme.px(3)
        )
        self._stripe.grid(row=0, column=0, sticky="ns")
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
            row=0,
            column=1,
            sticky="n",
            padx=(theme.px(12), theme.px(12)),
            pady=theme.px(12),
        )
        self._text = tk.Label(
            self,
            text="",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(12),
            anchor="w",
            justify="left",
        )
        self._text.grid(
            row=0, column=2, sticky="ew", padx=(0, theme.px(14)), pady=theme.px(12)
        )
        wrap_to_width(self._text)
        self.columnconfigure(2, weight=1)

    def bind_all_parts(
        self, sequence: str, handler: Callable[[tk.Event], object]
    ) -> None:
        for widget in (self, self._stripe, self._keycap, self._text):
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
            highlightbackground=self._color if selected else theme.PANEL,
        )
        self._stripe.configure(
            bg=self._color if selected else theme.mix(theme.PANEL, self._color, 0.45)
        )
        self._keycap.configure(
            bg=self._color if live else theme.PANEL_TOP,
            fg=theme.ACCENT_INK if live else self._color,
        )
        self._text.configure(bg=background, fg=foreground, text=shown)


def _trim(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"
