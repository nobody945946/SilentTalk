from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from silenttalk import theme
from silenttalk.widgets import (
    Button,
    card,
    wrap_to_width,
)

# Three places, like a phone's tab bar: talking, who you are, and settings.


class DiscordInviteCard:
    def __init__(self, root, get_link, status):
        self.root, self._invite_link_getter, self.status_var = root, get_link, status
        self._invite_card_body = None

    def _build_discord_invite(
        self, parent: tk.Frame, get_link: Callable[[], str]
    ) -> None:
        box = card(parent)
        box.outer.pack(fill="x", pady=(0, theme.px(12)))
        tk.Label(
            box,
            text="邀請連結",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(11, "bold"),
        ).pack(anchor="w", pady=(theme.px(4), 0))
        wrap_to_width(
            tk.Label(
                box,
                text="讓伺服器管理員將 Bot 加入伺服器，或補齊所需權限。",
                bg=theme.PANEL,
                fg=theme.DIM,
                font=theme.font(9),
                justify="left",
                anchor="w",
            )
        ).pack(anchor="w", fill="x", pady=(0, theme.px(6)))
        self._invite_card_body = tk.Frame(box, bg=theme.PANEL)
        self._invite_card_body.pack(fill="x", pady=(theme.px(4), 0))
        self._refresh_discord_invite()

    def _refresh_discord_invite(self) -> None:
        if self._invite_card_body is None:
            return
        for child in self._invite_card_body.winfo_children():
            child.destroy()
        link = (
            self._invite_link_getter() if self._invite_link_getter is not None else ""
        )
        if link:
            row = tk.Frame(self._invite_card_body, bg=theme.PANEL)
            row.pack(fill="x", pady=(theme.px(2), 0))
            border = tk.Frame(row, bg=theme.PANEL_HI, padx=1, pady=1)
            border.pack(side="left", fill="x", expand=True)
            entry = tk.Entry(
                border,
                bg=theme.PANEL_HI,
                fg=theme.TEXT,
                relief="flat",
                highlightthickness=0,
                font=theme.font(9),
            )
            entry.insert(0, link)
            entry.configure(state="readonly")
            entry.pack(fill="x", ipady=theme.px(4), ipadx=theme.px(6))

            def copy() -> None:
                self.root.clipboard_clear()
                self.root.clipboard_append(link)
                self.status_var.set("已複製邀請連結")

            Button(row, "複製", copy, kind="secondary", size=9).pack(
                side="left", padx=(theme.px(8), 0)
            )
        else:
            tk.Label(
                self._invite_card_body,
                text="連上 Discord 後才會出現邀請連結",
                bg=theme.PANEL,
                fg=theme.DIM,
                font=theme.font(9),
                anchor="w",
            ).pack(anchor="w")
