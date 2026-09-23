from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass

from silenttalk.hotkeys import GlobalHotkeys
from silenttalk.state import AppState
from silenttalk.text import TextValidationError


@dataclass(frozen=True, slots=True)
class UIAction:
    kind: str
    state: AppState | None = None
    message: str = ""


class SilentTalkUI:
    def __init__(
        self,
        speak_hotkey: str,
        stop_hotkey: str,
        submit: Callable[[str], None],
        stop_playback: Callable[[], None],
        shutdown: Callable[[], None],
    ) -> None:
        self._submit_callback = submit
        self._stop_callback = stop_playback
        self._shutdown_callback = shutdown
        self._actions: queue.SimpleQueue[UIAction] = queue.SimpleQueue()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.popup = tk.Toplevel(self.root)
        self.popup.title("SilentTalk")
        self.popup.attributes("-topmost", True)
        self.popup.resizable(False, False)
        self.popup.protocol("WM_DELETE_WINDOW", self.hide)
        self.popup.bind("<Escape>", lambda _: self.hide())
        self.popup.bind("<Return>", self._on_enter)

        self.input = tk.Text(
            self.popup,
            width=54,
            height=4,
            wrap="word",
            font=("Microsoft JhengHei UI", 12),
        )
        self.input.pack(padx=12, pady=(12, 6))
        self.status_var = tk.StringVar(value="啟動中…")
        tk.Label(self.popup, textvariable=self.status_var, anchor="w").pack(
            fill="x", padx=12, pady=(0, 6)
        )
        controls = tk.Frame(self.popup)
        controls.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(controls, text="停止播放 (F9)", command=self._stop_from_button).pack(
            side="left"
        )
        tk.Button(controls, text="退出 SilentTalk", command=self.close).pack(
            side="right"
        )
        self.popup.withdraw()

        self._hotkeys = GlobalHotkeys(
            {
                speak_hotkey: lambda: self._actions.put(UIAction("show")),
                stop_hotkey: lambda: self._actions.put(UIAction("stop")),
            }
        )
        self.root.after(50, self._poll_actions)

    def run(self) -> None:
        try:
            self._hotkeys.start()
        except Exception as exc:  # noqa: BLE001 - UI remains usable when OS hotkeys fail.
            self.set_status(AppState.ERROR, f"快捷鍵失敗：{exc}")
        self.root.mainloop()

    def set_status(self, state: AppState, message: str) -> None:
        self._actions.put(UIAction("status", state, message))

    def show(self) -> None:
        self.popup.deiconify()
        self.popup.lift()
        self.popup.focus_force()
        self.input.focus_set()

    def hide(self) -> None:
        self.input.delete("1.0", "end")
        self.popup.withdraw()

    def close(self) -> None:
        self._hotkeys.stop()
        self._shutdown_callback()
        self.root.destroy()

    def _stop_from_button(self) -> None:
        self._stop_callback()
        self.status_var.set("已停止並清空佇列")

    def _on_enter(self, event: tk.Event) -> str:
        if event.state & 0x0001:
            self.input.insert("insert", "\n")
            return "break"
        raw = self.input.get("1.0", "end-1c")
        try:
            self._submit_callback(raw)
        except TextValidationError as exc:
            self.status_var.set(str(exc))
            return "break"
        self.hide()
        return "break"

    def _poll_actions(self) -> None:
        while True:
            try:
                action = self._actions.get_nowait()
            except queue.Empty:
                break
            if action.kind == "show":
                self.show()
            elif action.kind == "stop":
                self._stop_callback()
                self.status_var.set("已停止並清空佇列")
            elif action.kind == "status":
                self.status_var.set(f"{action.state.value}: {action.message}")
        self.root.after(50, self._poll_actions)
