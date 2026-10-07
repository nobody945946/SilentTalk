"""人設 page: pick who "你" is and edit the character sheet the LLM follows."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from silenttalk import theme
from silenttalk.persona import (
    Persona,
)
from silenttalk.voice_styles import (
    PERSONA_VOICES,
    VOICE_EFFECTS,
)
from silenttalk.widgets.button import Button, Chip
from silenttalk.widgets.selection import Segmented
from silenttalk.widgets.stepper import Stepper

ApplyCallback = Callable[[Persona], None]
StatusCallback = Callable[[str], None]
PreviewCallback = Callable[[Persona, str], None]

NONE_ID = "none"


class PersonaVoiceEditor:
    def __init__(self, parent, *, on_change, on_preview):
        self._changed, self._preview_voice = on_change, on_preview
        self._voice = ""
        self._voice_chips = {}
        self._build_voice(parent)

    def _build_voice(self, box: tk.Frame) -> None:
        grid = tk.Frame(box, bg=theme.PANEL)
        grid.pack(anchor="w", pady=(0, 8))
        for index, (voice, label) in enumerate(PERSONA_VOICES):
            chip = Chip(grid, label, lambda v=voice: self._pick_voice(v), size=9)
            chip.grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 6), pady=2)
            self._voice_chips[voice] = chip
        self._voice_knobs: dict[str, Stepper | Segmented] = {}
        for key, label, limit, unit in (
            ("voice_pitch", "音高", 50, "Hz"),
            ("voice_speed", "語速", 40, "%"),
            ("voice_effect", "音效", 0, ""),
        ):
            row = tk.Frame(box, bg=theme.PANEL)
            row.pack(fill="x", pady=(2, 4))
            tk.Label(
                row,
                text=label,
                width=4,
                anchor="w",
                bg=theme.PANEL,
                fg=theme.MUTED,
                font=theme.font(9),
            ).pack(side="left", padx=(0, 10))
            if key == "voice_effect":
                knob = Segmented(
                    row,
                    [(k, name) for k, (name, _) in VOICE_EFFECTS.items()],
                    lambda _v: self._changed(),
                )
            else:
                knob = Stepper(
                    row,
                    minimum=-limit,
                    maximum=limit,
                    unit=unit,
                    command=lambda _v: self._changed(),
                )
            knob.pack(side="left")
            self._voice_knobs[key] = knob
        actions = tk.Frame(box, bg=theme.PANEL)
        actions.pack(fill="x", pady=(6, 0))
        Button(actions, "▶ 試聽", self._preview_voice, kind="secondary", size=9).pack(
            side="left"
        )
        tk.Label(
            actions,
            text="用代表台詞的第一句，在這台電腦播放，不會送進 Discord。語速頁的整體語速會再疊加。",
            bg=theme.PANEL,
            fg=theme.DIM,
            font=theme.font(8),
        ).pack(side="left", padx=(10, 0))

    def _pick_voice(self, voice: str) -> None:
        self._voice = voice
        for key, chip in self._voice_chips.items():
            chip.set_selected(key == voice)
        self._changed()

    def load(self, persona):
        self._pick_voice(persona.voice)
        for key, control in self._voice_knobs.items():
            control.set(getattr(persona, key))

    def values(self):
        return dict(
            voice=self._voice,
            voice_pitch=int(self._voice_knobs["voice_pitch"].get() or 0),
            voice_speed=int(self._voice_knobs["voice_speed"].get() or 0),
            voice_effect=self._voice_knobs["voice_effect"].get(),
        )
