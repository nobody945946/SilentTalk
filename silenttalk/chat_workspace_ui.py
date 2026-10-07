from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from silenttalk import theme
from silenttalk.chat_ui import CharacterView, ChatHeader, Transcript
from silenttalk.manual_ui import ManualSpeechPanel
from silenttalk.story_ui import StoryPanel


class ChatWorkspace:
    def __init__(
        self,
        parent,
        *,
        navigate,
        on_mood_pick,
        on_mood,
        on_confirm,
        on_edit,
        regenerate,
        send_text,
        on_run,
        on_engagement,
        stop_hotkey,
        on_reroll,
        manual_options,
    ):
        self.show_page = navigate
        self._on_mood_pick, self._on_mood = on_mood_pick, on_mood
        self._submit_story_choice, self._edit_story_choice = on_confirm, on_edit
        self._type_story_choice = send_text
        self._set_character_mode, self._set_engagement = on_run, on_engagement
        self._character_callback = on_run
        self._stop_hotkey, self._reroll_agenda_callback = stop_hotkey, on_reroll
        self._manual_options = manual_options
        self.frame = self._build_chat_page(parent, regenerate, send_text)

    def _build_chat_page(
        self,
        parent: tk.Frame,
        regenerate: Callable[[], None] | None,
        send_text: Callable[[str], None] | None,
    ) -> tk.Frame:
        page = tk.Frame(parent, bg=theme.BG)
        inner = tk.Frame(page, bg=theme.BG)
        inner.pack(
            fill="both",
            expand=True,
            padx=theme.px(24),
            pady=(theme.px(18), theme.px(14)),
        )
        modes = [("story", "選項"), ("manual", "打字")]
        if self._character_callback is not None:
            modes.insert(0, ("character", "角色"))
        self.header = ChatHeader(
            inner,
            modes,
            on_mode=lambda key: self.show_page(key),
            on_mood=self._on_mood_pick,
            on_persona=lambda: self.show_page("persona"),
        )
        self.header.pack(fill="x", pady=(0, theme.px(14)))

        # The mode's own controls are packed before the transcript so a small
        # window shrinks the transcript, never the buttons.
        self.stack = tk.Frame(inner, bg=theme.BG)
        self.stack.pack(side="bottom", fill="x")
        self.transcript = Transcript(inner)
        self.transcript.pack(fill="both", expand=True)

        self.story = StoryPanel(
            self.stack,
            on_confirm=self._submit_story_choice,
            on_edit=self._edit_story_choice,
            on_regenerate=regenerate,
            on_mood=self._on_mood,
            on_type=self._type_story_choice if send_text else None,
        )
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
            "story": self.story,
            "character": self.character,
            "manual": self.manual_frame,
        }
        return page
