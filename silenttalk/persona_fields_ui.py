"""人設 page: pick who "你" is and edit the character sheet the LLM follows."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import replace

from silenttalk import theme
from silenttalk.persona import (
    REPLY_LENGTHS,
    TEXT_FIELDS,
    TRAIT_AXES,
    Persona,
)
from silenttalk.widgets import (
    Button,
    Disclosure,
    Field,
    Segmented,
    TraitSlider,
    wrap_to_width,
)

ApplyCallback = Callable[[Persona], None]
StatusCallback = Callable[[str], None]
PreviewCallback = Callable[[Persona, str], None]

NONE_ID = "none"


from silenttalk.persona_relations_ui import RelationshipEditor
from silenttalk.persona_voice_ui import PersonaVoiceEditor

SECTIONS: tuple[tuple[str, str, tuple[str, ...], bool], ...] = (
    (
        "基本",
        "別人怎麼叫你、你是誰，以及你和頻道裡每個人的關係。",
        ("nickname", "identity", "relationships"),
        True,
    ),
    (
        "他想要什麼",
        (
            "這一段最重要：想要的、怕的、在意的、最近發生的事，決定他會聊什麼、"
            "冷場時會說什麼，也是別人認識他的地方。寫得越具體越像真人。"
        ),
        ("desires", "fears", "values", "recent", "background"),
        True,
    ),
    (
        "個性",
        "他講話的感覺。不用寫他常說哪些詞：小模型會每句照抄，聽起來很假。",
        ("traits", "speech_style", "humor_style", "reply_length"),
        False,
    ),
    (
        "聲音",
        "這個角色講話的聲音；Bot 說的每句話都會用它，不影響 AI 想出來的內容。",
        ("voice",),
        False,
    ),
)
MULTILINE = {"background": 3, "sample_lines": 3, "speech_style": 2, "desires": 2}
HINTS = {
    "nickname": "用「、」分隔。語音常被聽錯的寫法也可以寫進來（例：凱哥、開哥）。",
    "recent": "例：昨天排位連輸五場、下個月要搬家。他每天會從這裡想出幾件心事。",
    "speech_style": "例：句子短、講話直接、偶爾一句台語。引號裡的詞不會交給 AI。",
}


class PersonaFields:
    def __init__(self, parent, *, on_change, on_preview):
        self._notify, self._preview_voice = on_change, on_preview
        self._loading = False
        self._fields, self._sliders = {}, {}
        self._sections = []
        for title, subtitle, keys, opened in SECTIONS:
            self._build_section(parent, title, subtitle, keys, opened)

    def _changed(self):
        if self._loading:
            return
        self._length_hint.configure(text=REPLY_LENGTHS.get(self._length.get(), ""))
        self._notify()

    def _build_section(
        self,
        parent: tk.Frame,
        title: str,
        subtitle: str,
        keys: tuple[str, ...],
        opened: bool,
    ) -> None:
        section = Disclosure(parent, title, subtitle, opened=opened)
        section.pack(fill="x", pady=(0, theme.px(12)), padx=(0, theme.px(18)))
        self._sections.append(section)
        box = section.body
        for key in keys:
            if key == "traits":
                for axis in TRAIT_AXES:
                    slider = TraitSlider(
                        box, axis.low, axis.high, lambda _v: self._changed()
                    )
                    slider.pack(anchor="w", pady=theme.px(3))
                    self._sliders[axis.key] = slider
            elif key == "reply_length":
                row = tk.Frame(box, bg=theme.PANEL)
                row.pack(fill="x", pady=(theme.px(4), theme.px(10)))
                tk.Label(
                    row,
                    text="回覆長度",
                    bg=theme.PANEL,
                    fg=theme.MUTED,
                    font=theme.font(9),
                ).pack(side="left", padx=(0, 10))
                self._length = Segmented(
                    row,
                    [("short", "短"), ("normal", "中"), ("long", "長")],
                    lambda _v: self._changed(),
                )
                self._length.pack(side="left")
                self._length_hint = tk.Label(
                    row, text="", bg=theme.PANEL, fg=theme.DIM, font=theme.font(8)
                )
                self._length_hint.pack(side="left", padx=(10, 0))
            elif key == "voice":
                self.voice = PersonaVoiceEditor(
                    box, on_change=self._changed, on_preview=self._preview_voice
                )
            elif key == "relationships":
                tk.Label(
                    box,
                    text="人際關係",
                    bg=theme.PANEL,
                    fg=theme.MUTED,
                    font=theme.font(9),
                ).pack(anchor="w")
                wrap_to_width(
                    tk.Label(
                        box,
                        text=(
                            "左邊填 Discord 顯示名稱（也填你自己），右邊從角色的角度寫這個人是誰。"
                            "例：「阿明」「我老公，結婚三年」→ 角色會把阿明當老公。"
                        ),
                        bg=theme.PANEL,
                        fg=theme.DIM,
                        font=theme.font(9),
                        justify="left",
                        anchor="w",
                    )
                ).pack(anchor="w", fill="x", pady=(0, theme.px(6)))
                self._relations = tk.Frame(box, bg=theme.PANEL)
                self._relations.pack(fill="x")
                self.relations = RelationshipEditor(self._relations, self._changed)
                Button(
                    box,
                    "＋ 新增一位",
                    self.relations._add_relation_row,
                    kind="ghost",
                    size=9,
                ).pack(anchor="w", pady=(theme.px(6), 0))
            else:
                label, _, limit = TEXT_FIELDS[key]
                field = Field(
                    box,
                    label,
                    limit=limit,
                    lines=MULTILINE.get(key, 1),
                    hint=HINTS.get(key, ""),
                    on_change=self._changed,
                )
                field.pack(fill="x", pady=(0, theme.px(10)))
                self._fields[key] = field

    def load(self, persona):
        self._loading = True
        try:
            for key, field in self._fields.items():
                field.set(str(getattr(persona, key)))
            for axis in TRAIT_AXES:
                self._sliders[axis.key].set(persona.trait(axis.key))
            self._length.set(persona.reply_length)
            self.voice.load(persona)
            self.relations.load(persona.relationships)
            self._length_hint.configure(
                text=REPLY_LENGTHS.get(persona.reply_length, "")
            )
        finally:
            self._loading = False

    def collect(self, base: Persona, name: str) -> Persona:
        return replace(
            base,
            name=name,
            traits={axis.key: self._sliders[axis.key].get() for axis in TRAIT_AXES},
            reply_length=self._length.get(),
            relationships=self.relations.values(),
            **self.voice.values(),
            **{key: field.get() for key, field in self._fields.items()},
        )
