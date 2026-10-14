from __future__ import annotations

import tkinter as tk


class InputBindings:
    def __init__(self, popup, *, mode, hide, manual):
        self._mode = mode
        self.manual = manual
        popup.bind("<Escape>", lambda _: hide())
        popup.bind("<Return>", self._on_enter)
        for index in range(9):
            popup.bind(
                f"<Control-Key-{index + 1}>",
                lambda event, phrase_index=index: self._on_quick_phrase_key(
                    phrase_index
                ),
            )

    def _on_enter(self, event: tk.Event) -> str | None:
        if self._mode() != "manual":
            return None
        if event.state & 0x0001:
            self.manual.input.insert("insert", "\n")
            return "break"
        self.manual._submit_input()
        return "break"

    def _on_quick_phrase_key(self, index: int) -> str | None:
        if self._mode() != "manual":
            return None
        return self.manual._send_quick_phrase(index)
