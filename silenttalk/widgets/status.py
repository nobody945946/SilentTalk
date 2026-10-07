from __future__ import annotations

import tkinter as tk

from silenttalk import theme


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
