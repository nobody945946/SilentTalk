from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

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
            padx=theme.px(padx),
            pady=theme.px(pady),
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
            padx=theme.px(10),
            pady=theme.px(3),
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
