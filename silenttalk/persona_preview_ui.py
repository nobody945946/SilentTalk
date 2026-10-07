"""人設 page: pick who "你" is and edit the character sheet the LLM follows."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from silenttalk import theme
from silenttalk.persona import (
    RECOMMENDED_PROMPT_CHARS,
    Persona,
)
from silenttalk.widgets import (
    Disclosure,
    wrap_to_width,
)

ApplyCallback = Callable[[Persona], None]
StatusCallback = Callable[[str], None]
PreviewCallback = Callable[[Persona, str], None]

NONE_ID = "none"


class PersonaPreview:
    def __init__(self, parent):
        self._build_preview(parent)

    def _build_preview(self, parent: tk.Frame) -> None:
        section = Disclosure(
            parent,
            "AI 實際看到的人設",
            "上面寫的東西整理後給模型的樣子，以及長度。",
            bg=theme.SURFACE,
        )
        section.pack(fill="x", pady=(0, theme.px(18)), padx=(0, theme.px(18)))
        box = section.body
        top = tk.Frame(box, bg=theme.SURFACE)
        top.pack(fill="x")
        self._meter_text = tk.Label(
            top, text="", bg=theme.SURFACE, fg=theme.MUTED, font=theme.font(9)
        )
        self._meter_text.pack(side="left")
        self._meter = tk.Canvas(
            box, height=theme.px(6), bg=theme.SURFACE, highlightthickness=0
        )
        self._meter.pack(fill="x", pady=(theme.px(6), theme.px(8)))
        self._preview = tk.Text(
            box,
            height=8,
            wrap="word",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            relief="flat",
            font=theme.font(9),
            takefocus=0,
        )
        self._preview.pack(fill="x")
        note = tk.Label(
            box,
            text=(
                f"建議控制在 {RECOMMENDED_PROMPT_CHARS} 字內：太長的人設會讓本機小模型"
                "開始不照四行格式，也會讓第一次回覆變慢（之後會被快取）。"
            ),
            bg=theme.SURFACE,
            fg=theme.DIM,
            font=theme.font(9),
            justify="left",
            anchor="w",
        )
        wrap_to_width(note).pack(anchor="w", fill="x", pady=(theme.px(6), 0))

    def render(self, persona: Persona) -> None:
        sheet = persona.render_prompt_block()
        notes = [
            f"{r.name}：{r.relation}"
            for r in persona.relationships
            if r.name and r.relation
        ]
        shown = sheet or "（空白：AI 會用中性口吻）"
        if notes:
            shown += "\n\n〔對話中出現才加入〕\n" + "\n".join(notes)
        self._preview.configure(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.insert("1.0", shown)
        self._preview.configure(
            state="disabled", height=min(14, max(4, shown.count("\n") + 2))
        )
        length = len(sheet)
        ratio = min(1.0, length / RECOMMENDED_PROMPT_CHARS)
        color = (
            theme.OK
            if ratio < 0.8
            else (theme.WARN if length <= RECOMMENDED_PROMPT_CHARS else theme.ERROR)
        )
        self._meter_text.configure(
            text=f"{length} / {RECOMMENDED_PROMPT_CHARS} 字", fg=color
        )
        self._meter.update_idletasks()
        width = max(1, self._meter.winfo_width())
        self._meter.delete("all")
        self._meter.create_rectangle(0, 0, width, 6, fill=theme.PANEL_TOP, outline="")
        self._meter.create_rectangle(0, 0, width * ratio, 6, fill=color, outline="")
