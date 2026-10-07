from __future__ import annotations

import tkinter as tk

from silenttalk import theme
from silenttalk.state import AppState
from silenttalk.widgets.status import StatusDot

# Three places, like a phone's tab bar: talking, who you are, and settings.

_DISCORD_STATES = {
    AppState.STARTING: (theme.DIM, "啟動中"),
    AppState.READY: (theme.WARN, "Discord 待命"),
    AppState.OWNER_NOT_IN_VOICE: (theme.WARN, "你不在語音頻道"),
    AppState.VOICE_CONNECTED: (theme.OK, "語音已連線"),
    AppState.SYNTHESIZING: (theme.OK, "合成語音中"),
    AppState.SPEAKING: (theme.ACCENT_HI, "正在說話"),
    AppState.SHUTTING_DOWN: (theme.DIM, "關閉中"),
}


class StatusBar:
    def __init__(self, popup, *, on_close, copilot_enabled, error):
        self.popup, self.close = popup, on_close
        self._copilot_enabled = copilot_enabled
        self._build_status_bar(error)

    def _build_status_bar(self, initial: str) -> None:
        bar = tk.Frame(self.popup, bg=theme.SURFACE)
        bar.pack(fill="x", side="bottom")
        inner = tk.Frame(bar, bg=theme.SURFACE)
        inner.pack(fill="x", padx=theme.px(14), pady=theme.px(6))
        # Connection and AI state live down here, out of the way until they
        # turn yellow or red.
        self._discord_dot = StatusDot(inner, "啟動中")
        self._discord_dot.pack(side="left")
        self._ai_dot = StatusDot(inner, "AI 待命")
        self._ai_dot.set(theme.OK)
        self._ai_dot.pack(side="left", padx=(theme.px(14), 0))
        self.status_var = tk.StringVar(value=initial or "啟動中…")
        self._status_label = tk.Label(
            inner,
            textvariable=self.status_var,
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
        )
        self._status_label.pack(
            side="left", fill="x", expand=True, padx=(theme.px(18), 0)
        )
        quit_label = tk.Label(
            inner,
            text="退出",
            bg=theme.SURFACE,
            fg=theme.DIM,
            font=theme.font(9),
            cursor="hand2",
        )
        quit_label.pack(side="right")
        quit_label.bind("<Button-1>", lambda _: self.close())

    def _show_status(self, state: AppState | None, message: str) -> None:
        if state is None:
            self.status_var.set(message)
            return
        if state == AppState.ERROR:
            self._status_label.configure(fg=theme.ERROR)
            self._discord_dot.set(theme.ERROR, "語音錯誤")
        else:
            self._status_label.configure(fg=theme.MUTED)
            color, label = _DISCORD_STATES.get(state, (theme.DIM, state.value))
            self._discord_dot.set(color, label)
        self.status_var.set(message)

    def set_ai_status(self, message: str) -> None:
        self._ai_dot.set(theme.OK if message == "AI 待命" else theme.WARN, message)
