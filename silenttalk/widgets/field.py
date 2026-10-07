from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from silenttalk import theme
from silenttalk.widgets.layout import wrap_to_width


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
        border = tk.Frame(self, bg=theme.PANEL_HI, padx=1, pady=1)
        border.pack(fill="x", pady=(theme.px(4), 0))
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
                highlightthickness=0,
                padx=theme.px(8),
                pady=theme.px(6),
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
                highlightthickness=0,
                font=theme.font(10),
            )
            self._var.trace_add("write", lambda *_: self._changed())
        self._widget.pack(
            fill="x", ipady=theme.px(5) if not self._multi else 0, ipadx=theme.px(6)
        )
        self._widget.bind("<FocusIn>", lambda _: border.configure(bg=theme.ACCENT))
        self._widget.bind("<FocusOut>", lambda _: border.configure(bg=theme.PANEL_HI))
        if hint:
            hint_label = tk.Label(
                self,
                text=hint,
                bg=bg,
                fg=theme.DIM,
                font=theme.font(9),
                anchor="w",
                justify="left",
            )
            hint_label.pack(fill="x", pady=(theme.px(3), 0))
            wrap_to_width(hint_label)
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
