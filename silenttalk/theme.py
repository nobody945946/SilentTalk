"""Design tokens for the Tk UI: one dark palette, one type scale.

Every widget reads colors from here and fonts through `font()`, so a palette
change is a one-file edit. `init_fonts()` must run after the Tk root exists.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# First installed family wins. Windows ships JhengHei; the others keep Linux
# previews (scripts/dev/ui_preview.py) readable instead of tofu boxes.
FONT_CANDIDATES = (
    "Microsoft JhengHei UI",
    "Microsoft JhengHei",
    "Noto Sans CJK TC",
    "Noto Sans TC",
    "PingFang TC",
)
FONT = FONT_CANDIDATES[0]
MONO = "Consolas"

# Surfaces, darkest to lightest.
BG = "#0e1016"
SURFACE = "#141720"
PANEL = "#1a1e29"
PANEL_HI = "#222736"
PANEL_TOP = "#2a3042"
LINE = "#2c3244"

TEXT = "#e9ecf4"
MUTED = "#9aa2b6"
DIM = "#646c80"

ACCENT = "#8b7cff"
ACCENT_HI = "#a699ff"
ACCENT_INK = "#0f0c26"

OK = "#5fd38d"
WARN = "#f5b94f"
ERROR = "#ff7b72"

SELF_COLOR = ACCENT_HI
SPEAKER_COLORS = ("#7cc4ff", "#ffb38a", "#e0a6ff", "#7ee0d6", "#ffd98a", "#ff9fbf")

# One color per reply lane code (see copilot/types.py REPLY_LANES).
LANE_COLORS = {
    "AGREE": "#5fd39a",
    "ASK": "#6fb3ff",
    "DISAGREE": "#ff8a78",
    "HUMOR": "#ffc857",
}


def lane_color(code: str) -> str:
    return LANE_COLORS.get(code, ACCENT)


def font(size: int = 10, weight: str = "normal") -> tuple:
    return (FONT, size) if weight == "normal" else (FONT, size, weight)


def mono(size: int = 9) -> tuple:
    return (MONO, size)


def mix(color: str, other: str, amount: float) -> str:
    """Blend two #rrggbb colors; amount=0 -> color, 1 -> other."""
    a = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(
        f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b, strict=True)
    )


def init_fonts(root: tk.Misc, override: str | None = None) -> str:
    global FONT, MONO
    families = set(tkfont.families(root))
    if override:
        FONT = override
    else:
        FONT = next((f for f in FONT_CANDIDATES if f in families), "TkDefaultFont")
    MONO = next(
        (f for f in ("Cascadia Mono", "Consolas", "DejaVu Sans Mono") if f in families),
        "TkFixedFont",
    )
    return FONT


def style_ttk(root: tk.Misc) -> None:
    """Dark look for the few ttk widgets we keep (combobox, scrollbar)."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        return
    style.configure(
        "TCombobox",
        fieldbackground=PANEL_HI,
        background=PANEL_TOP,
        foreground=TEXT,
        arrowcolor=MUTED,
        bordercolor=LINE,
        lightcolor=PANEL_HI,
        darkcolor=PANEL_HI,
        selectbackground=PANEL_HI,
        selectforeground=TEXT,
        padding=6,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", PANEL_HI)],
        foreground=[("readonly", TEXT)],
        bordercolor=[("focus", ACCENT)],
    )
    root.option_add("*TCombobox*Listbox.background", PANEL_HI)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_INK)
    root.option_add("*TCombobox*Listbox.font", font(10))
    style.configure(
        "Dark.Vertical.TScrollbar",
        background=PANEL_TOP,
        troughcolor=SURFACE,
        bordercolor=SURFACE,
        lightcolor=PANEL_TOP,
        darkcolor=PANEL_TOP,
        arrowcolor=MUTED,
        gripcount=0,
        arrowsize=10,
    )
    style.map("Dark.Vertical.TScrollbar", background=[("active", LINE)])
