from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from silenttalk import theme


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
        self._track = tk.Frame(
            self, width=theme.px(34), height=theme.px(18), bg=theme.PANEL_TOP
        )
        self._track.pack(side="left")
        self._track.pack_propagate(False)
        self._knob = tk.Frame(
            self._track, width=theme.px(14), height=theme.px(14), bg=theme.MUTED
        )
        self._knob.place(x=theme.px(2), y=theme.px(2))
        self._text = tk.Label(
            self, text="關", bg=bg, fg=theme.MUTED, font=theme.font(9)
        )
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
        self._knob.place(x=theme.px(18 if self._value else 2), y=theme.px(2))
        self._text.configure(
            text="開" if self._value else "關",
            fg=theme.TEXT if self._value else theme.MUTED,
        )
        if notify and self._command is not None:
            self._command(self._value)
