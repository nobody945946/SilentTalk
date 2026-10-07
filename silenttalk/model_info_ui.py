from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence

from silenttalk import theme
from silenttalk.widgets import (
    card,
)

# Three places, like a phone's tab bar: talking, who you are, and settings.


def build_model_info(parent: tk.Frame, copilot_info: Sequence[tuple[str, str]]) -> None:
    info = card(parent)
    info.outer.pack(fill="x", pady=(0, theme.px(12)))
    tk.Label(
        info,
        text="現在跑的",
        bg=theme.PANEL,
        fg=theme.TEXT,
        font=theme.font(11, "bold"),
    ).pack(anchor="w")
    rows = list(copilot_info) or [("狀態", "未啟用")]
    grid = tk.Frame(info, bg=theme.PANEL)
    grid.pack(fill="x", pady=(theme.px(6), 0))
    for index, (label, value) in enumerate(rows):
        tk.Label(
            grid,
            text=label,
            bg=theme.PANEL,
            fg=theme.DIM,
            font=theme.font(9),
            anchor="w",
        ).grid(row=index, column=0, sticky="w", padx=(0, theme.px(16)), pady=1)
        tk.Label(
            grid,
            text=value,
            bg=theme.PANEL,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
        ).grid(row=index, column=1, sticky="w", pady=1)
