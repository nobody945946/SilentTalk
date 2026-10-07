from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence

from silenttalk import theme


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
        # A sunken track with the chosen segment raised, as Windows 11 and
        # macOS draw it.
        super().__init__(master, bg=theme.PANEL_HI, padx=theme.px(2), pady=theme.px(2))
        self._on_change = on_change
        self._value = options[0][0]
        self._segments: dict[str, tk.Label] = {}
        for value, label in options:
            segment = tk.Label(
                self,
                text=label,
                font=theme.font(10),
                padx=theme.px(14),
                pady=theme.px(4),
                cursor="hand2",
            )
            segment.pack(side="left", padx=(0, theme.px(2)))
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
                segment.configure(bg=theme.SELECTED, fg=theme.TEXT)
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
        self.DOT = theme.px(16)
        self.GAP = theme.px(22)
        self._value = 3
        self._on_change = on_change
        self._low = tk.Label(
            self, text=low, bg=bg, font=theme.font(9), width=14, anchor="e"
        )
        self._low.pack(side="left")
        width = self.GAP * 4 + self.DOT + theme.px(8)
        self._canvas = tk.Canvas(
            self,
            width=width,
            height=self.DOT + theme.px(8),
            bg=bg,
            highlightthickness=0,
            cursor="hand2",
        )
        self._canvas.pack(side="left", padx=8)
        self._high = tk.Label(
            self, text=high, bg=bg, font=theme.font(9), width=14, anchor="w"
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
        step = round((event.x - theme.px(4) - self.DOT / 2) / self.GAP)
        self.set(step + 1)
        if self._on_change is not None:
            self._on_change(self._value)

    def _render(self) -> None:
        canvas = self._canvas
        canvas.delete("all")
        y = theme.px(4) + self.DOT / 2
        x0 = theme.px(4) + self.DOT / 2
        canvas.create_line(
            x0, y, x0 + self.GAP * 4, y, fill=theme.LINE, width=theme.px(2)
        )
        for index in range(5):
            x = x0 + index * self.GAP
            level = index + 1
            active = level == self._value
            radius = self.DOT / 2 if active else theme.px(4)
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
