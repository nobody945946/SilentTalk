from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from silenttalk import theme


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
