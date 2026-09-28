"""The chat page's own parts: who you are talking as, the running transcript
every mode shares, and the character view.

The page itself is assembled in silenttalk/ui.py, which owns the modes:
角色 (the bot plays the persona by itself), 選項 (W/A/S/D choices, story_ui)
and 打字 (typed input and quick phrases). Tk thread only.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence

from silenttalk import theme
from silenttalk.copilot.persona import MOODS
from silenttalk.copilot.types import ConversationTurn
from silenttalk.widgets import Avatar, Button, Segmented, card, wrap_to_width

MAX_TRANSCRIPT_TURNS = 80


class ChatHeader(tk.Frame):
    """Avatar, name and mood of the active persona, and the mode switch."""

    def __init__(
        self,
        master: tk.Misc,
        modes: Sequence[tuple[str, str]],
        *,
        on_mode: Callable[[str], None],
        on_mood: Callable[[str], None],
        on_persona: Callable[[], None],
    ) -> None:
        super().__init__(master, bg=theme.BG)
        self._on_mood = on_mood
        who = tk.Frame(self, bg=theme.BG, cursor="hand2")
        who.pack(side="left", fill="x", expand=True)
        self._avatar = Avatar(who, 40, bg=theme.BG)
        self._avatar.pack(side="left")
        text = tk.Frame(who, bg=theme.BG)
        text.pack(side="left", fill="x", expand=True, padx=(theme.px(12), 0))
        self._name = tk.Label(
            text,
            text="",
            bg=theme.BG,
            fg=theme.TEXT,
            font=theme.font(15, "bold"),
            anchor="w",
        )
        self._name.pack(anchor="w", fill="x")
        line = tk.Frame(text, bg=theme.BG)
        line.pack(anchor="w", fill="x")
        self._subtitle = tk.Label(
            line, text="", bg=theme.BG, fg=theme.MUTED, font=theme.font(10), anchor="w"
        )
        self._subtitle.pack(side="left")
        for widget in (who, self._avatar, text, self._name, self._subtitle):
            widget.bind("<Button-1>", lambda _: on_persona())

        # Mood is a menu, not seven chips: it is set once in a while.
        self._mood_button = tk.Label(
            line,
            text="",
            bg=theme.BG,
            fg=theme.DIM,
            font=theme.font(10),
            cursor="hand2",
        )
        self._mood_button.pack(side="left", padx=(theme.px(10), 0))
        self._mood_menu = tk.Menu(
            self,
            tearoff=False,
            bg=theme.PANEL_HI,
            fg=theme.TEXT,
            activebackground=theme.ACCENT,
            activeforeground=theme.ACCENT_INK,
            font=theme.font(10),
            bd=0,
        )
        for mood in MOODS:
            self._mood_menu.add_command(
                label=mood, command=lambda m=mood: self._pick(m)
            )
        self._mood_button.bind("<Button-1>", self._open_moods)

        self._modes = Segmented(self, modes, on_mode)
        self._modes.pack(side="right", anchor="center")

    def set_persona(self, name: str, subtitle: str) -> None:
        self._avatar.set_name(name)
        self._name.configure(text=name or "不使用人設")
        self._subtitle.configure(text=subtitle)

    def set_mood(self, mood: str) -> None:
        self._mood_button.configure(text=f"· 心情 {mood or '平常'} ▾")

    def set_mode(self, key: str) -> None:
        self._modes.set(key)

    def _open_moods(self, event: tk.Event) -> None:
        self._mood_menu.tk_popup(event.x_root, event.y_root + theme.px(8))

    def _pick(self, mood: str) -> None:
        self.set_mood(mood)
        self._on_mood(mood)


class Transcript(tk.Frame):
    """What everyone said, newest at the bottom, one color per speaker."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=theme.BG)
        box = card(self, bg=theme.SURFACE, padx=0, pady=0)
        box.outer.pack(fill="both", expand=True)
        self._text = tk.Text(
            box,
            height=7,
            wrap="word",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            relief="flat",
            highlightthickness=0,
            padx=theme.px(16),
            pady=theme.px(12),
            font=theme.font(11),
            cursor="arrow",
            takefocus=0,
            spacing1=theme.px(3),
            spacing3=theme.px(3),
        )
        self._text.pack(fill="both", expand=True)
        self._text.tag_configure(
            "self", foreground=theme.SELF_COLOR, font=theme.font(11, "bold")
        )
        self._text.tag_configure("muted", foreground=theme.DIM)
        self._text.tag_configure("said", foreground=theme.TEXT)
        for index, color in enumerate(theme.SPEAKER_COLORS):
            self._text.tag_configure(
                f"speaker{index}", foreground=color, font=theme.font(11, "bold")
            )
        self._turns = 0
        self._text.insert("end", "等待 Discord 語音裡有人開口…\n", "muted")
        self._text.configure(state="disabled")

    def set_height(self, lines: int) -> None:
        self._text.configure(height=lines)

    def add_turn(self, turn: ConversationTurn) -> None:
        text = self._text
        text.configure(state="normal")
        if self._turns == 0:
            text.delete("1.0", "end")
        if turn.is_self:
            # "你" when the bot speaks for you; the character's name otherwise.
            name, tag = turn.speaker_name or "你", "self"
        else:
            index = theme.SPEAKER_COLORS.index(theme.speaker_color(turn.speaker_id))
            name, tag = turn.speaker_name, f"speaker{index}"
        text.insert("end", f"{name}  ", tag)
        text.insert("end", turn.text + "\n", "said" if turn.is_self else ())
        self._turns += 1
        if self._turns > MAX_TRANSCRIPT_TURNS:
            text.delete("1.0", "2.0")
            self._turns -= 1
        text.see("end")
        text.configure(state="disabled")


ENGAGEMENTS: tuple[tuple[str, str], ...] = (
    ("called", "被叫到才回"),
    ("active", "會主動加入"),
)
_ENGAGEMENT_HELP = {
    "called": "有人叫它、問它或回應它的時候才接話。",
    "active": "被叫到一定回，安靜一陣子後也會自己插話。",
}


class CharacterView(tk.Frame):
    """The bot is the persona: start or pause it, and say how chatty it is."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_run: Callable[[bool], None],
        on_engagement: Callable[[str], None],
        stop_hotkey: str,
        on_reroll_agenda: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, bg=theme.BG)
        self._on_run = on_run
        self._on_engagement = on_engagement
        self._on_reroll_agenda = on_reroll_agenda
        self._running = False
        self._name = ""

        box = card(self)
        box.outer.pack(fill="x", pady=(theme.px(12), 0))
        top = tk.Frame(box, bg=theme.PANEL)
        top.pack(fill="x")
        state = tk.Frame(top, bg=theme.PANEL)
        state.pack(side="left", fill="x", expand=True)
        self._dot = tk.Label(
            state, text="●", bg=theme.PANEL, fg=theme.DIM, font=theme.font(12)
        )
        self._dot.pack(side="left")
        self._state = tk.Label(
            state, text="", bg=theme.PANEL, fg=theme.TEXT, font=theme.font(14, "bold")
        )
        self._state.pack(side="left", padx=(theme.px(8), 0))
        self._button = Button(
            top, "開始", self._toggle, kind="primary", size=11, padx=22, pady=8
        )
        self._button.pack(side="right")

        self._detail = tk.Label(
            box,
            text="",
            bg=theme.PANEL,
            fg=theme.MUTED,
            font=theme.font(10),
            justify="left",
            anchor="w",
        )
        self._detail.pack(fill="x", pady=(theme.px(6), theme.px(14)))
        wrap_to_width(self._detail)

        tk.Frame(box, bg=theme.LINE, height=1).pack(fill="x")
        when = tk.Frame(box, bg=theme.PANEL)
        when.pack(fill="x", pady=(theme.px(14), 0))
        tk.Label(
            when, text="開口時機", bg=theme.PANEL, fg=theme.TEXT, font=theme.font(10)
        ).pack(side="left")
        self._engagement = Segmented(when, ENGAGEMENTS, self._pick_engagement)
        self._engagement.pack(side="right")
        self._engagement_help = tk.Label(
            box,
            text="",
            bg=theme.PANEL,
            fg=theme.DIM,
            font=theme.font(9),
            justify="left",
            anchor="w",
        )
        self._engagement_help.pack(fill="x", pady=(theme.px(6), 0))
        wrap_to_width(self._engagement_help)

        # What is on the character's mind today: what it brings up in a lull
        # and what it relates to while talking. Made from the persona, kept
        # in memory only; "換一批" asks for another set.
        mind = card(self)
        mind.outer.pack(fill="x", pady=(theme.px(12), 0))
        head = tk.Frame(mind, bg=theme.PANEL)
        head.pack(fill="x")
        self._mind_title = tk.Label(
            head, text="今天在想", bg=theme.PANEL, fg=theme.TEXT, font=theme.font(11, "bold")
        )
        self._mind_title.pack(side="left")
        if on_reroll_agenda is not None:
            reroll = tk.Label(
                head, text="換一批", bg=theme.PANEL, fg=theme.ACCENT_HI,
                font=theme.font(10), cursor="hand2",
            )
            reroll.pack(side="right")
            reroll.bind("<Button-1>", lambda _: self._reroll())
        self._mind = tk.Label(
            mind,
            text="選好人設後會自動想好。",
            bg=theme.PANEL,
            fg=theme.MUTED,
            font=theme.font(10),
            justify="left",
            anchor="w",
        )
        self._mind.pack(fill="x", pady=(theme.px(8), 0))
        wrap_to_width(self._mind)

        tk.Label(
            self,
            text=f"{stop_hotkey} 隨時讓它閉嘴（清掉正在說和排隊的話）",
            bg=theme.BG,
            fg=theme.DIM,
            font=theme.font(9),
        ).pack(anchor="w", pady=(theme.px(10), 0))
        self.set_engagement("called")
        self._render()

    def set_persona(self, name: str) -> None:
        self._name = name
        self._render()

    def set_agenda(self, items: Sequence[str]) -> None:
        self._mind.configure(
            text="\n".join(f"・{item}" for item in items) if items else "這次沒有想到什麼，按「換一批」再想一次。"
        )

    def _reroll(self) -> None:
        self._mind.configure(text="想一下……")
        if self._on_reroll_agenda is not None:
            self._on_reroll_agenda()

    def set_running(self, running: bool) -> None:
        self._running = running
        self._render()

    def set_engagement(self, value: str) -> None:
        self._engagement.set(value if value in _ENGAGEMENT_HELP else "called")
        self._engagement_help.configure(text=_ENGAGEMENT_HELP[self._engagement.get()])

    def _toggle(self) -> None:
        self._on_run(not self._running)

    def _pick_engagement(self, value: str) -> None:
        self._engagement_help.configure(text=_ENGAGEMENT_HELP[value])
        self._on_engagement(value)

    def _render(self) -> None:
        name = self._name or "角色"
        if self._running:
            self._dot.configure(fg=theme.OK)
            self._state.configure(text=f"{name} 正在聽")
            self._detail.configure(
                text=f"{name} 會自己決定要不要接話，說的話會出現在上面的對話裡。"
            )
            self._button.configure(text="暫停")
        else:
            self._dot.configure(fg=theme.DIM)
            self._state.configure(text="已暫停")
            self._detail.configure(
                text=f"按「開始」讓 Bot 變成 {name}，自己在語音頻道裡聊天。每次打開 SilentTalk 都是暫停的，不會突然開口。"
            )
            self._button.configure(text="開始")
