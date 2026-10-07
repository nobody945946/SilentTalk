from __future__ import annotations

import tkinter as tk

from silenttalk import theme
from silenttalk.preferences import (
    UserPreferences,
)
from silenttalk.speech_settings import (
    DEFAULT_RATE_MULTIPLIER,
    MAX_RATE_MULTIPLIER,
    MIN_RATE_MULTIPLIER,
)
from silenttalk.voice_styles import voice_style_choices, voice_style_label
from silenttalk.widgets.button import Button, Chip
from silenttalk.widgets.layout import card, wrap_to_width

# Three places, like a phone's tab bar: talking, who you are, and settings.


class VoiceControls:
    def __init__(self, *, preferences, on_change, on_commit, on_summary):
        self._preferences = preferences
        self._changed, self._persist_preferences = on_change, on_commit
        self._summary = on_summary
        self._voice_style = "default"
        self._style_choices = voice_style_choices()
        self.rate_var = tk.DoubleVar(value=preferences.speech_rate_multiplier * 100)

    def _build_voice_group(
        self, parent: tk.Frame, preferences: UserPreferences
    ) -> None:
        voice = card(parent)
        voice.outer.pack(fill="x", pady=(0, theme.px(12)))
        tk.Label(
            voice,
            text="聲音風格",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(11, "bold"),
        ).pack(anchor="w")
        # Shown when the active persona has its own voice, which then wins.
        self._persona_voice_note = tk.Label(
            voice,
            text="",
            bg=theme.PANEL,
            fg=theme.DIM,
            font=theme.font(9),
            justify="left",
            anchor="w",
        )
        self._persona_voice_note.pack(
            anchor="w", fill="x", pady=(theme.px(2), theme.px(10))
        )
        wrap_to_width(self._persona_voice_note)
        chips = tk.Frame(voice, bg=theme.PANEL)
        chips.pack(anchor="w")
        self._voice_chips: dict[str, Chip] = {}
        for index, (key, label) in enumerate(self._style_choices):
            chip = Chip(chips, label, lambda k=key: self._set_style(k), size=10)
            chip.grid(
                row=index // 2,
                column=index % 2,
                sticky="w",
                padx=(0, theme.px(6)),
                pady=theme.px(3),
            )
            self._voice_chips[key] = chip

        tk.Frame(voice, bg=theme.LINE, height=1).pack(fill="x", pady=(theme.px(14), 0))
        top = tk.Frame(voice, bg=theme.PANEL)
        top.pack(fill="x", pady=(theme.px(12), 0))
        tk.Label(
            top, text="語速", bg=theme.PANEL, fg=theme.TEXT, font=theme.font(10)
        ).pack(side="left")
        initial_percent = round(preferences.speech_rate_multiplier * 100)
        self.rate_var = tk.DoubleVar(value=initial_percent)
        self.rate_text_var = tk.StringVar(value=f"{initial_percent}%")
        tk.Label(
            top,
            textvariable=self.rate_text_var,
            bg=theme.PANEL,
            fg=theme.ACCENT_HI,
            font=theme.font(11, "bold"),
        ).pack(side="right")
        row = tk.Frame(voice, bg=theme.PANEL)
        row.pack(fill="x", pady=(theme.px(6), 0))
        self.rate_scale = tk.Scale(
            row,
            from_=MIN_RATE_MULTIPLIER * 100,
            to=MAX_RATE_MULTIPLIER * 100,
            resolution=5,
            orient="horizontal",
            showvalue=False,
            variable=self.rate_var,
            command=self._on_rate_changed,
            # tk.Scale paints the slider knob with ``bg``.
            bg=theme.ACCENT,
            troughcolor=theme.PANEL_TOP,
            activebackground=theme.ACCENT_HI,
            highlightthickness=0,
            sliderrelief="flat",
            bd=0,
            width=theme.px(8),
            sliderlength=theme.px(20),
        )
        self.rate_scale.pack(side="left", fill="x", expand=True)
        Button(row, "重設 100%", self._reset_rate, kind="ghost", size=9).pack(
            side="left", padx=(theme.px(10), 0)
        )
        self.rate_scale.bind("<ButtonRelease-1>", self._persist_rate)
        self.rate_scale.bind("<KeyRelease>", self._persist_rate)
        self._set_style("default")

    def _selected_style_key(self) -> str:
        return self._voice_style

    def _set_style(self, key: str) -> None:
        if key not in self._voice_chips:
            key = "default"
        self._voice_style = key
        for chip_key, chip in self._voice_chips.items():
            chip.set_selected(chip_key == key)
        self._update_voice_summary()
        self._changed()

    def _rate_multiplier(self) -> float:
        return float(self.rate_var.get()) / 100.0

    def _on_rate_changed(self, value: str) -> None:
        self.rate_text_var.set(f"{float(value):.0f}%")
        self._update_voice_summary()

    def _reset_rate(self) -> None:
        self.rate_var.set(DEFAULT_RATE_MULTIPLIER * 100)
        self._on_rate_changed(str(DEFAULT_RATE_MULTIPLIER * 100))
        self._persist_preferences()

    def _persist_rate(self, _: tk.Event | None = None) -> None:
        self._persist_preferences()
        self._changed()

    def _update_voice_summary(self):
        self._summary(
            f"♪ {voice_style_label(self._voice_style)} · 語速 {self._rate_multiplier():.0%}"
        )
