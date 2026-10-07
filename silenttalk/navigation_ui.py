from __future__ import annotations

import tkinter as tk

from silenttalk import theme

# Three places, like a phone's tab bar: talking, who you are, and settings.

NAV = (("chat", "◆", "對話"), ("persona", "☺", "人設"), ("settings", "⚙", "設定"))


class NavigationRail:
    def __init__(self, body, *, navigate, stop, stop_hotkey):
        self.show_page, self._stop_from_button, self._stop_hotkey = (
            navigate,
            stop,
            stop_hotkey,
        )
        self._build_rail(body)

    def _build_rail(self, body: tk.Frame) -> None:
        rail = tk.Frame(body, bg=theme.SURFACE)
        rail.pack(side="left", fill="y")
        tk.Label(
            rail, text="◢", bg=theme.SURFACE, fg=theme.ACCENT, font=theme.font(16)
        ).pack(pady=(theme.px(16), theme.px(14)))
        self._rail_items: dict[str, tuple[tk.Misc, ...]] = {}
        for key, glyph, label in NAV:
            item = tk.Frame(rail, bg=theme.SURFACE, cursor="hand2")
            item.pack(fill="x", padx=theme.px(8), pady=theme.px(2))
            icon = tk.Label(item, text=glyph, bg=theme.SURFACE, font=theme.font(15))
            icon.pack(padx=theme.px(14), pady=(theme.px(8), 0))
            text = tk.Label(item, text=label, bg=theme.SURFACE, font=theme.font(9))
            text.pack(pady=(0, theme.px(8)))
            for widget in (item, icon, text):
                widget.bind("<Button-1>", lambda _, k=key: self.show_page(k))
            self._rail_items[key] = (item, icon, text)

        stop = tk.Frame(rail, bg=theme.SURFACE, cursor="hand2")
        stop.pack(side="bottom", fill="x", pady=(0, theme.px(14)))
        stop_icon = tk.Label(
            stop, text="■", bg=theme.SURFACE, fg=theme.ERROR, font=theme.font(13)
        )
        stop_icon.pack()
        stop_text = tk.Label(
            stop,
            text=f"停止 {self._stop_hotkey}",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=theme.font(9),
        )
        stop_text.pack()
        for widget in (stop, stop_icon, stop_text):
            widget.bind("<Button-1>", lambda _: self._stop_from_button())
