"""Small themed Tk building blocks shared by the SilentTalk pages.

Plain tk.Label/Canvas based so they look the same on every Windows theme; all
colors come from silenttalk.theme. Tk thread only.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from silenttalk import theme

_BUTTON_KINDS = {
    # kind: (background, hover, foreground)
    "primary": (theme.ACCENT, theme.ACCENT_HI, theme.ACCENT_INK),
    "secondary": (theme.PANEL_TOP, theme.LINE, theme.TEXT),
    "ghost": (theme.PANEL, theme.PANEL_HI, theme.MUTED),
    "danger": (
        theme.PANEL_TOP,
        theme.mix(theme.PANEL_TOP, theme.ERROR, 0.35),
        theme.ERROR,
    ),
}


class Button(tk.Label):
    """Flat clickable label with hover; `kind` picks the palette."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], object] | None = None,
        *,
        kind: str = "secondary",
        size: int = 10,
        padx: int = 14,
        pady: int = 6,
    ) -> None:
        self._colors = _BUTTON_KINDS[kind]
        self._command = command
        self._enabled = True
        super().__init__(
            master,
            text=text,
            bg=self._colors[0],
            fg=self._colors[2],
            font=theme.font(size, "bold" if kind == "primary" else "normal"),
            padx=padx,
            pady=pady,
            cursor="hand2",
        )
        self.bind("<Enter>", lambda _: self._hover(True))
        self.bind("<Leave>", lambda _: self._hover(False))
        self.bind("<Button-1>", self._click)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(
            fg=self._colors[2] if enabled else theme.DIM,
            cursor="hand2" if enabled else "arrow",
        )

    def _hover(self, inside: bool) -> None:
        if self._enabled:
            self.configure(bg=self._colors[1] if inside else self._colors[0])

    def _click(self, _: tk.Event) -> None:
        if self._enabled and self._command is not None:
            self._command()


class Chip(tk.Label):
    """Rounded-looking toggle pill."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], object] | None = None,
        *,
        color: str = theme.ACCENT,
        size: int = 9,
    ) -> None:
        self._color = color
        self._selected = False
        super().__init__(
            master,
            text=text,
            font=theme.font(size),
            padx=10,
            pady=3,
            cursor="hand2",
        )
        self._render()
        if command is not None:
            self.bind("<Button-1>", lambda _: command())

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._render()

    def _render(self) -> None:
        if self._selected:
            self.configure(bg=self._color, fg=theme.ACCENT_INK)
        else:
            self.configure(bg=theme.PANEL_HI, fg=theme.MUTED)


class Segmented(tk.Frame):
    """One-of-N choice drawn as adjacent segments."""

    def __init__(
        self,
        master: tk.Misc,
        options: Sequence[tuple[str, str]],
        on_change: Callable[[str], None] | None = None,
        *,
        bg: str = theme.PANEL,
    ) -> None:
        super().__init__(master, bg=theme.LINE, padx=1, pady=1)
        self._on_change = on_change
        self._value = options[0][0]
        self._segments: dict[str, tk.Label] = {}
        for value, label in options:
            segment = tk.Label(
                self, text=label, font=theme.font(9), padx=12, pady=4, cursor="hand2"
            )
            segment.pack(side="left", padx=(0, 1))
            segment.bind("<Button-1>", lambda _, v=value: self.set(v, notify=True))
            self._segments[value] = segment
        self._render()

    def get(self) -> str:
        return self._value

    def set(self, value: str, *, notify: bool = False) -> None:
        if value not in self._segments:
            return
        self._value = value
        self._render()
        if notify and self._on_change is not None:
            self._on_change(value)

    def _render(self) -> None:
        for value, segment in self._segments.items():
            if value == self._value:
                segment.configure(bg=theme.ACCENT, fg=theme.ACCENT_INK)
            else:
                segment.configure(bg=theme.PANEL_HI, fg=theme.MUTED)


class TraitSlider(tk.Frame):
    """5-step personality axis: low word ··●·· high word, 3 = neutral."""

    DOT = 16
    GAP = 22

    def __init__(
        self,
        master: tk.Misc,
        low: str,
        high: str,
        on_change: Callable[[int], None] | None = None,
        *,
        bg: str = theme.PANEL,
    ) -> None:
        super().__init__(master, bg=bg)
        self._value = 3
        self._on_change = on_change
        self._low = tk.Label(
            self, text=low, bg=bg, font=theme.font(9), width=10, anchor="e"
        )
        self._low.pack(side="left")
        width = self.GAP * 4 + self.DOT + 8
        self._canvas = tk.Canvas(
            self,
            width=width,
            height=self.DOT + 8,
            bg=bg,
            highlightthickness=0,
            cursor="hand2",
        )
        self._canvas.pack(side="left", padx=8)
        self._high = tk.Label(
            self, text=high, bg=bg, font=theme.font(9), width=10, anchor="w"
        )
        self._high.pack(side="left")
        self._canvas.bind("<Button-1>", self._click)
        self._render()

    def get(self) -> int:
        return self._value

    def set(self, value: int) -> None:
        self._value = max(1, min(5, int(value)))
        self._render()

    def _click(self, event: tk.Event) -> None:
        step = round((event.x - 4 - self.DOT / 2) / self.GAP)
        self.set(step + 1)
        if self._on_change is not None:
            self._on_change(self._value)

    def _render(self) -> None:
        canvas = self._canvas
        canvas.delete("all")
        y = 4 + self.DOT / 2
        x0 = 4 + self.DOT / 2
        canvas.create_line(x0, y, x0 + self.GAP * 4, y, fill=theme.LINE, width=2)
        for index in range(5):
            x = x0 + index * self.GAP
            level = index + 1
            active = level == self._value
            radius = self.DOT / 2 if active else 4
            if active:
                color = theme.MUTED if level == 3 else theme.ACCENT
            else:
                color = theme.PANEL_TOP if level != 3 else theme.LINE
            canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius, fill=color, outline=""
            )
        lean_low, lean_high = self._value < 3, self._value > 3
        self._low.configure(fg=theme.TEXT if lean_low else theme.DIM)
        self._high.configure(fg=theme.TEXT if lean_high else theme.DIM)


class ScrollArea(tk.Frame):
    """Vertical scrolling container; put children in `.body`."""

    def __init__(self, master: tk.Misc, *, bg: str = theme.BG) -> None:
        super().__init__(master, bg=bg)
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._bar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self._canvas.yview,
            style="Dark.Vertical.TScrollbar",
        )
        self.body = tk.Frame(self._canvas, bg=bg)
        self._window = self._canvas.create_window((0, 0), window=self.body, anchor="nw")
        self._canvas.configure(yscrollcommand=self._bar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._bar.pack(side="right", fill="y")
        self.body.bind(
            "<Configure>",
            lambda _: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind(
            "<Configure>",
            lambda event: self._canvas.itemconfigure(self._window, width=event.width),
        )
        self.bind("<Enter>", lambda _: self._bind_wheel(True))
        self.bind("<Leave>", lambda _: self._bind_wheel(False))

    def scroll_to_top(self) -> None:
        self._canvas.yview_moveto(0)

    def _bind_wheel(self, active: bool) -> None:
        if active:
            self.bind_all("<MouseWheel>", self._on_wheel)
            self.bind_all(
                "<Button-4>", lambda _: self._canvas.yview_scroll(-3, "units")
            )
            self.bind_all("<Button-5>", lambda _: self._canvas.yview_scroll(3, "units"))
        else:
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.unbind_all(sequence)

    def _on_wheel(self, event: tk.Event) -> None:
        self._canvas.yview_scroll(
            int(-event.delta / 40) or (-1 if event.delta > 0 else 1), "units"
        )


class Avatar(tk.Canvas):
    """Colored circle with the first character of a name."""

    def __init__(
        self, master: tk.Misc, size: int = 30, *, bg: str = theme.SURFACE
    ) -> None:
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0)
        self._size = size
        self.set_name("")

    def set_name(self, name: str) -> None:
        self.delete("all")
        size = self._size
        if not name:
            self.create_oval(1, 1, size - 1, size - 1, outline=theme.LINE, width=2)
            self.create_text(
                size / 2,
                size / 2,
                text="?",
                fill=theme.DIM,
                font=theme.font(10, "bold"),
            )
            return
        color = theme.SPEAKER_COLORS[sum(map(ord, name)) % len(theme.SPEAKER_COLORS)]
        self.create_oval(1, 1, size - 1, size - 1, fill=color, outline="")
        self.create_text(
            size / 2,
            size / 2,
            text=name[0],
            fill=theme.ACCENT_INK,
            font=theme.font(max(9, size // 3), "bold"),
        )


class StatusDot(tk.Frame):
    """● label pair used in the header."""

    def __init__(self, master: tk.Misc, label: str, *, bg: str = theme.SURFACE) -> None:
        super().__init__(master, bg=bg)
        self._dot = tk.Label(self, text="●", bg=bg, fg=theme.DIM, font=theme.font(9))
        self._dot.pack(side="left")
        self._text = tk.Label(
            self, text=label, bg=bg, fg=theme.MUTED, font=theme.font(9)
        )
        self._text.pack(side="left", padx=(3, 0))

    def set(self, color: str, text: str | None = None) -> None:
        self._dot.configure(fg=color)
        if text is not None:
            self._text.configure(text=text)


class Field(tk.Frame):
    """Label + single- or multi-line input + live 'n/limit' counter."""

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        *,
        limit: int,
        lines: int = 1,
        hint: str = "",
        on_change: Callable[[], None] | None = None,
        bg: str = theme.PANEL,
    ) -> None:
        super().__init__(master, bg=bg)
        self._limit = limit
        self._on_change = on_change
        self._loading = False
        top = tk.Frame(self, bg=bg)
        top.pack(fill="x")
        tk.Label(top, text=label, bg=bg, fg=theme.MUTED, font=theme.font(9)).pack(
            side="left"
        )
        self._counter = tk.Label(top, text="", bg=bg, fg=theme.DIM, font=theme.font(8))
        self._counter.pack(side="right")
        border = tk.Frame(self, bg=theme.LINE, padx=1, pady=1)
        border.pack(fill="x", pady=(3, 0))
        self._border = border
        self._multi = lines > 1
        if self._multi:
            self._widget: tk.Text | tk.Entry = tk.Text(
                border,
                height=lines,
                wrap="word",
                bg=theme.PANEL_HI,
                fg=theme.TEXT,
                insertbackground=theme.TEXT,
                relief="flat",
                padx=8,
                pady=6,
                font=theme.font(10),
                undo=True,
            )
            self._widget.bind("<<Modified>>", self._modified)
        else:
            self._var = tk.StringVar()
            self._widget = tk.Entry(
                border,
                textvariable=self._var,
                bg=theme.PANEL_HI,
                fg=theme.TEXT,
                insertbackground=theme.TEXT,
                relief="flat",
                font=theme.font(10),
            )
            self._var.trace_add("write", lambda *_: self._changed())
        self._widget.pack(fill="x", ipady=4 if not self._multi else 0)
        self._widget.bind("<FocusIn>", lambda _: border.configure(bg=theme.ACCENT))
        self._widget.bind("<FocusOut>", lambda _: border.configure(bg=theme.LINE))
        if hint:
            tk.Label(
                self,
                text=hint,
                bg=bg,
                fg=theme.DIM,
                font=theme.font(8),
                anchor="w",
                justify="left",
                wraplength=520,
            ).pack(fill="x", pady=(2, 0))
        self._update_counter()

    def get(self) -> str:
        if isinstance(self._widget, tk.Text):
            return self._widget.get("1.0", "end-1c")
        return self._var.get()

    def set(self, value: str) -> None:
        self._loading = True
        try:
            if isinstance(self._widget, tk.Text):
                self._widget.delete("1.0", "end")
                self._widget.insert("1.0", value)
                self._widget.edit_modified(False)
                self._widget.edit_reset()
            else:
                self._var.set(value)
        finally:
            self._loading = False
        self._update_counter()

    def _modified(self, _: tk.Event) -> None:
        widget = self._widget
        if isinstance(widget, tk.Text) and widget.edit_modified():
            widget.edit_modified(False)
            self._changed()

    def _changed(self) -> None:
        self._update_counter()
        if not self._loading and self._on_change is not None:
            self._on_change()

    def _update_counter(self) -> None:
        count = len(self.get().strip())
        over = count > self._limit
        self._counter.configure(
            text=f"{count}/{self._limit}" if count else "",
            fg=theme.ERROR if over else theme.DIM,
        )


class Toggle(tk.Frame):
    """On/off switch with the state spelled out, for a settings row."""

    def __init__(
        self,
        master: tk.Misc,
        command: Callable[[bool], object] | None = None,
        *,
        bg: str = theme.PANEL,
    ) -> None:
        super().__init__(master, bg=bg, cursor="hand2")
        self._value = False
        self._command = command
        self._track = tk.Frame(self, width=34, height=18, bg=theme.PANEL_TOP)
        self._track.pack(side="left")
        self._track.pack_propagate(False)
        self._knob = tk.Frame(self._track, width=14, height=14, bg=theme.MUTED)
        self._knob.place(x=2, y=2)
        self._text = tk.Label(self, text="關", bg=bg, fg=theme.MUTED, font=theme.font(9))
        self._text.pack(side="left", padx=(8, 0))
        for widget in (self, self._track, self._knob, self._text):
            widget.bind("<Button-1>", lambda _: self._toggle())

    def _toggle(self) -> None:
        self.set(not self._value, notify=True)

    def get(self) -> bool:
        return self._value

    def set(self, value: bool, *, notify: bool = False) -> None:
        self._value = bool(value)
        self._track.configure(bg=theme.ACCENT if self._value else theme.PANEL_TOP)
        self._knob.configure(bg=theme.ACCENT_INK if self._value else theme.MUTED)
        self._knob.place(x=18 if self._value else 2, y=2)
        self._text.configure(
            text="開" if self._value else "關",
            fg=theme.TEXT if self._value else theme.MUTED,
        )
        if notify and self._command is not None:
            self._command(self._value)


class Stepper(tk.Frame):
    """Number with - / + buttons: no keyboard needed, no invalid states."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        minimum: float,
        maximum: float,
        step: float = 1.0,
        decimals: int = 0,
        unit: str = "",
        command: Callable[[float], object] | None = None,
        bg: str = theme.PANEL,
    ) -> None:
        super().__init__(master, bg=bg)
        self._min, self._max, self._step = minimum, maximum, step
        self._decimals = decimals
        self._unit = unit
        self._command = command
        self._value = minimum
        self._down = Button(self, "−", lambda: self._nudge(-1), kind="ghost", size=10)
        self._down.pack(side="left")
        self._label = tk.Label(
            self, text="", width=8, bg=bg, fg=theme.TEXT, font=theme.font(10, "bold")
        )
        self._label.pack(side="left")
        self._up = Button(self, "＋", lambda: self._nudge(1), kind="ghost", size=10)
        self._up.pack(side="left")

    def _nudge(self, direction: int) -> None:
        self.set(self._value + direction * self._step, notify=True)

    def get(self) -> float:
        return self._value

    def set(self, value: float, *, notify: bool = False) -> None:
        self._value = max(self._min, min(self._max, float(value)))
        shown = (
            f"{self._value:.{self._decimals}f}" if self._decimals else f"{int(self._value)}"
        )
        self._label.configure(text=f"{shown}{self._unit}")
        if notify and self._command is not None:
            self._command(self._value)


def keycap(
    master: tk.Misc,
    text: str,
    *,
    color: str = theme.PANEL_TOP,
    fg: str = theme.TEXT,
    bg: str = theme.BG,
) -> tk.Label:
    return tk.Label(
        master,
        text=text,
        bg=color,
        fg=fg,
        font=theme.font(8, "bold"),
        padx=5,
        pady=0,
    )


def hint_row(
    master: tk.Misc, items: Sequence[tuple[str, str]], *, bg: str = theme.BG
) -> tk.Frame:
    """[key] action  [key] action … in one line."""
    row = tk.Frame(master, bg=bg)
    for key, action in items:
        keycap(row, key).pack(side="left")
        tk.Label(row, text=action, bg=bg, fg=theme.DIM, font=theme.font(8)).pack(
            side="left", padx=(3, 10)
        )
    return row


def section_title(
    master: tk.Misc, title: str, subtitle: str = "", *, bg: str = theme.BG
) -> tk.Frame:
    frame = tk.Frame(master, bg=bg)
    tk.Label(frame, text=title, bg=bg, fg=theme.TEXT, font=theme.font(11, "bold")).pack(
        anchor="w"
    )
    if subtitle:
        tk.Label(
            frame,
            text=subtitle,
            bg=bg,
            fg=theme.DIM,
            font=theme.font(9),
            justify="left",
            anchor="w",
            wraplength=560,
        ).pack(anchor="w", fill="x")
    return frame


def card(
    master: tk.Misc, *, bg: str = theme.PANEL, padx: int = 14, pady: int = 12
) -> tk.Frame:
    """A panel with a 1px outline; returns the inner frame to fill."""
    outer = tk.Frame(master, bg=theme.LINE, padx=1, pady=1)
    inner = tk.Frame(outer, bg=bg, padx=padx, pady=pady)
    inner.pack(fill="both", expand=True)
    inner.outer = outer  # type: ignore[attr-defined]
    return inner
