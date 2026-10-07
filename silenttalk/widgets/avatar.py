from __future__ import annotations

import tkinter as tk

from silenttalk import theme


class Avatar(tk.Canvas):
    """Colored circle with the first character of a name."""

    def __init__(
        self, master: tk.Misc, size: int = 30, *, bg: str = theme.SURFACE
    ) -> None:
        size = theme.px(size)
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
                # Negative size = pixels: the glyph scales with the canvas,
                # never past it (points grow with Windows scaling).
                font=(theme.FONT, -round(size * 0.45), "bold"),
            )
            return
        color = theme.SPEAKER_COLORS[sum(map(ord, name)) % len(theme.SPEAKER_COLORS)]
        self.create_oval(1, 1, size - 1, size - 1, fill=color, outline="")
        self.create_text(
            size / 2,
            size / 2,
            text=name[0],
            fill=theme.ACCENT_INK,
            font=(theme.FONT, -round(size * 0.45), "bold"),
        )
