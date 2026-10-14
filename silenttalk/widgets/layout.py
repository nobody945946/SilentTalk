from __future__ import annotations

import tkinter as tk

from silenttalk import theme


def wrap_to_width(label: tk.Label, margin: int = 0) -> tk.Label:
    """Wrap a label at the width it actually gets. A fixed wraplength in pixels
    breaks lines far too early or too late once Windows scaling changes the
    font size."""

    def resize(event: tk.Event) -> None:
        width = event.width - theme.px(margin)
        # cget returns a Tcl object (a screen distance), not an int.
        if width > 40 and str(label.cget("wraplength")) != str(width):
            label.configure(wraplength=width)

    # Until the first layout, cap the line: an unwrapped label asks for its
    # whole text on one line, and a long line would widen the window itself.
    if str(label.cget("wraplength")) in ("0", ""):
        label.configure(wraplength=theme.px(420))
    label.bind("<Configure>", resize, add="+")
    return label


def section_title(
    master: tk.Misc, title: str, subtitle: str = "", *, bg: str = theme.BG
) -> tk.Frame:
    frame = tk.Frame(master, bg=bg)
    tk.Label(frame, text=title, bg=bg, fg=theme.TEXT, font=theme.font(15, "bold")).pack(
        anchor="w"
    )
    if subtitle:
        wrap_to_width(
            tk.Label(
                frame,
                text=subtitle,
                bg=bg,
                fg=theme.MUTED,
                font=theme.font(10),
                justify="left",
                anchor="w",
            )
        ).pack(anchor="w", fill="x", pady=(theme.px(2), 0))
    return frame


def card(
    master: tk.Misc,
    *,
    bg: str = theme.PANEL,
    padx: int = 16,
    pady: int = 14,
    outline: bool = False,
) -> tk.Frame:
    """A raised panel; returns the inner frame to fill (pack `.outer`). Depth
    comes from the surface color; an outline only where a card sits on a
    surface of the same color."""
    outer = tk.Frame(
        master, bg=theme.LINE if outline else bg, padx=int(outline), pady=int(outline)
    )
    inner = tk.Frame(outer, bg=bg, padx=theme.px(padx), pady=theme.px(pady))
    inner.pack(fill="both", expand=True)
    inner.outer = outer  # type: ignore[attr-defined]
    return inner
