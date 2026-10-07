from __future__ import annotations

import tkinter as tk


class InputBindings:
    def __init__(self, popup, *, mode, navigate, hide, manual, story):
        self._mode = mode
        self.show_page = navigate
        self.manual, self.story = manual, story
        popup.bind("<Escape>", lambda _: hide())
        popup.bind("<Return>", self._on_enter)
        popup.bind("<Control-Tab>", self._toggle_story_manual)
        popup.bind("<KeyPress>", self._on_popup_key)
        for index in range(9):
            popup.bind(
                f"<Control-Key-{index + 1}>",
                lambda event, phrase_index=index: self._on_quick_phrase_key(
                    phrase_index
                ),
            )

    def _on_enter(self, event: tk.Event) -> str | None:
        if self._mode() == "story":
            self.story.handle_key("Return")
            return "break"
        if self._mode() != "manual":
            return None
        if event.widget is self.manual.suggestion_list:
            return "break"  # the listbox's own binding already handled it
        if event.state & 0x0001:
            self.manual.input.insert("insert", "\n")
            return "break"
        self.manual._submit_input()
        return "break"

    def _on_popup_key(self, event: tk.Event) -> str | None:
        if self._mode() != "story" or event.state & 0x0004:  # leave Ctrl+… alone
            return None
        return "break" if self.story.handle_key(event.keysym) else None

    def _toggle_story_manual(self, _: tk.Event) -> str:
        self.show_page("manual" if self._mode() == "story" else "story")
        return "break"

    def _on_quick_phrase_key(self, index: int) -> str | None:
        if self._mode() not in ("story", "manual"):
            return None
        return self.manual._send_quick_phrase(index)
