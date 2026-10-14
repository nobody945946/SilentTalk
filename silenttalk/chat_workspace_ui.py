from __future__ import annotations

import tkinter as tk

from silenttalk import theme
from silenttalk.chat_ui import CharacterView, ChatHeader, Transcript
from silenttalk.manual_ui import ManualSpeechPanel


class ChatWorkspace:
    def __init__(
        self,
        parent,
        *,
        navigate,
        on_mood,
        on_run,
        on_engagement,
        stop_hotkey,
        on_reroll,
        manual_options,
    ):
        self.show_page = navigate
        self._on_mood = on_mood
        self._set_character_mode, self._set_engagement = on_run, on_engagement
        self._character_callback = on_run
        self._stop_hotkey, self._reroll_agenda_callback = stop_hotkey, on_reroll
        self._manual_options = manual_options
        self.frame = self._build_chat_page(parent)

    def _build_chat_page(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=theme.BG)
        inner = tk.Frame(page, bg=theme.BG)
        inner.pack(
            fill="both",
            expand=True,
            padx=theme.px(24),
            pady=(theme.px(18), theme.px(14)),
        )
        modes = [("manual", "打字")]
        if self._character_callback is not None:
            modes.insert(0, ("character", "角色"))
        self.header = ChatHeader(
            inner,
            modes,
            on_mode=lambda key: self.show_page(key),
            on_mood=self._on_mood,
            on_persona=lambda: self.show_page("persona"),
        )
        self.header.pack(fill="x", pady=(0, theme.px(14)))

        # The mode's own controls are packed before the transcript so a small
        # window shrinks the transcript, never the buttons.
        self.stack = tk.Frame(inner, bg=theme.BG)
        self.stack.pack(side="bottom", fill="x")
        self.transcript = Transcript(inner)
        self.transcript.pack(fill="both", expand=True)

        self.character = CharacterView(
            self.stack,
            on_run=self._set_character_mode,
            on_engagement=self._set_engagement,
            stop_hotkey=self._stop_hotkey,
            on_reroll_agenda=self._reroll_agenda_callback,
        )
        self.manual = ManualSpeechPanel(self.stack, **self._manual_options)
        self.manual_frame = self.manual.frame
        self.views = {
            "character": self.character,
            "manual": self.manual_frame,
        }
        return page
