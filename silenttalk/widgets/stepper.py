from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from silenttalk import theme
from silenttalk.widgets.button import Button


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
            f"{self._value:.{self._decimals}f}"
            if self._decimals
            else f"{int(self._value)}"
        )
        self._label.configure(text=f"{shown}{self._unit}")
        if notify and self._command is not None:
            self._command(self._value)
