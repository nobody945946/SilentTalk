from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from silenttalk import theme
from silenttalk.widgets.layout import wrap_to_width


class Disclosure(tk.Frame):
    """A titled section that folds away: the everyday settings stay in view,
    the rest one click deeper. Put children in `.body`."""

    def __init__(
        self,
        master: tk.Misc,
        title: str,
        subtitle: str = "",
        *,
        opened: bool = False,
        bg: str = theme.PANEL,
        on_toggle: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(master, bg=bg)
        self._opened = opened
        self._on_toggle = on_toggle
        header = tk.Frame(self, bg=bg, cursor="hand2")
        header.pack(fill="x", padx=theme.px(16), pady=theme.px(12))
        self._chevron = tk.Label(
            header, text="", bg=bg, fg=theme.MUTED, font=theme.font(10), width=2
        )
        self._chevron.pack(side="left", anchor="n", pady=(theme.px(2), 0))
        text = tk.Frame(header, bg=bg)
        text.pack(side="left", fill="x", expand=True)
        title_label = tk.Label(
            text, text=title, bg=bg, fg=theme.TEXT, font=theme.font(11, "bold")
        )
        title_label.pack(anchor="w")
        parts: list[tk.Misc] = [header, self._chevron, text, title_label]
        if subtitle:
            sub = tk.Label(
                text,
                text=subtitle,
                bg=bg,
                fg=theme.DIM,
                font=theme.font(9),
                justify="left",
                anchor="w",
            )
            sub.pack(anchor="w", fill="x")
            wrap_to_width(sub)
            parts.append(sub)
        for widget in parts:
            widget.bind("<Button-1>", lambda _: self.toggle())
        self.body = tk.Frame(self, bg=bg, padx=theme.px(16))
        self._spacer = tk.Frame(self, bg=bg, height=theme.px(4))
        self._render()

    @property
    def opened(self) -> bool:
        return self._opened

    def toggle(self) -> None:
        self.set_open(not self._opened)
        if self._on_toggle is not None:
            self._on_toggle(self._opened)

    def set_open(self, opened: bool) -> None:
        self._opened = opened
        self._render()

    def _render(self) -> None:
        self._chevron.configure(text="▾" if self._opened else "▸")
        if self._opened:
            self.body.pack(fill="x")
            self._spacer.pack(fill="x", pady=(0, theme.px(10)))
        else:
            self.body.pack_forget()
            self._spacer.pack_forget()
