"""人設 page: pick who "你" is and edit the character sheet the LLM follows."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import replace

from silenttalk import theme
from silenttalk.copilot.persona import (
    RECOMMENDED_PROMPT_CHARS,
    REPLY_LENGTHS,
    TEXT_FIELDS,
    TRAIT_AXES,
    Persona,
    PersonaError,
    PersonaState,
    PersonaStore,
    Relationship,
    blank_persona,
    new_persona_id,
    validate_persona,
)
from silenttalk.voice_styles import (
    PERSONA_VOICES,
    PITCH_STEPS,
    SPEED_STEPS,
    VOICE_EFFECTS,
)
from silenttalk.widgets import (
    Avatar,
    Button,
    Chip,
    Field,
    ScrollArea,
    Segmented,
    TraitSlider,
    card,
)

ApplyCallback = Callable[[Persona], None]
StatusCallback = Callable[[str], None]
PreviewCallback = Callable[[Persona, str], None]

NONE_ID = "none"

# (section title, subtitle, fields). Fields are keys of TEXT_FIELDS, or the
# special "traits" / "reply_length" / "relationships" editors.
SECTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "基本資料",
        "你是誰。名字會讓 AI 用第一人稱代入。",
        ("nickname", "identity", "background"),
    ),
    ("個性", "點圓點調整；正中間＝不特別強調，不會寫進 prompt。", ("traits",)),
    (
        "內心",
        "慾望決定你會想把話題帶去哪；雷點決定你什麼時候會反對。",
        ("desires", "fears", "values", "pet_peeves", "secret"),
    ),
    (
        "說話方式",
        "代表台詞是小模型最能抓住語氣的線索，建議至少寫兩句。",
        ("speech_style", "catchphrases", "humor_style", "reply_length", "sample_lines"),
    ),
    (
        "近況與專長",
        "讓回覆有料可聊，也避免 AI 假裝懂你不懂的東西。",
        ("recent", "knowledge"),
    ),
    (
        "人際關係",
        "寫 Discord 顯示名稱。只有當這個人出現在對話裡，關係才會被放進 prompt。",
        ("relationships",),
    ),
    ("底線", "無論如何都不能說出口的話。", ("boundaries",)),
    (
        "聲音",
        "這個角色講話的聲音。設定後，Bot 說的每句話（手動、選項、角色模式）都用它；不會影響 AI 想出來的內容。",
        ("voice",),
    ),
)
MULTILINE = {"background": 3, "sample_lines": 3, "speech_style": 2, "desires": 2}
HINTS = {
    "catchphrases": "例：穩啦、笑死。AI 只會偶爾帶到，不會每句都用。",
    "sample_lines": "一行一句，最多取前 4 句。",
    "secret": "AI 知道但不會主動講，會影響迴避或轉移話題的方式。",
}


class PersonaPanel(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        store: PersonaStore | None,
        *,
        on_apply: ApplyCallback,
        on_status: StatusCallback,
        on_preview: PreviewCallback | None = None,
    ) -> None:
        super().__init__(master, bg=theme.BG)
        self._on_preview = on_preview
        self._voice = ""
        self._voice_chips: dict[str, Chip] = {}
        self._store = store
        self._on_apply = on_apply
        self._on_status = on_status
        self._state = PersonaState([])
        self._editing: str = NONE_ID
        self._dirty = False
        self._loading = False
        self._fields: dict[str, Field] = {}
        self._sliders: dict[str, TraitSlider] = {}
        self._relation_rows: list[tuple[tk.Frame, tk.StringVar, tk.StringVar]] = []

        # ---- left: persona list ----------------------------------------------
        left = tk.Frame(self, bg=theme.SURFACE, width=210)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(
            left,
            text="人設",
            bg=theme.SURFACE,
            fg=theme.TEXT,
            font=theme.font(14, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(
            left,
            text="AI 會用這個身分替你想回覆",
            bg=theme.SURFACE,
            fg=theme.DIM,
            font=theme.font(9),
        ).pack(anchor="w", padx=16, pady=(0, 10))
        self._list = tk.Frame(left, bg=theme.SURFACE)
        self._list.pack(fill="x")
        actions = tk.Frame(left, bg=theme.SURFACE)
        actions.pack(fill="x", side="bottom", padx=12, pady=12)
        Button(actions, "＋ 新人設", self._new, kind="secondary", size=9).pack(
            side="left", fill="x", expand=True
        )
        Button(actions, "複製", self._duplicate, kind="ghost", size=9).pack(
            side="left", padx=(6, 0)
        )

        # ---- right: editor ---------------------------------------------------
        right = tk.Frame(self, bg=theme.BG)
        right.pack(side="left", fill="both", expand=True)

        bar = tk.Frame(right, bg=theme.BG)
        bar.pack(fill="x", padx=18, pady=(14, 8))
        self._avatar = Avatar(bar, 40, bg=theme.BG)
        self._avatar.pack(side="left")
        name_box = tk.Frame(bar, bg=theme.BG)
        name_box.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self._name_var = tk.StringVar()
        self._name_entry = tk.Entry(
            name_box,
            textvariable=self._name_var,
            bg=theme.BG,
            fg=theme.TEXT,
            insertbackground=theme.TEXT,
            relief="flat",
            font=theme.font(15, "bold"),
            width=14,
        )
        self._name_entry.pack(anchor="w", fill="x")
        self._name_var.trace_add("write", lambda *_: self._changed())
        self._subtitle = tk.Label(
            name_box, text="", bg=theme.BG, fg=theme.DIM, font=theme.font(9), anchor="w"
        )
        self._subtitle.pack(anchor="w")
        buttons = tk.Frame(bar, bg=theme.BG)
        buttons.pack(side="right")
        self._delete_button = Button(
            buttons, "刪除", self._delete, kind="danger", size=9
        )
        self._delete_button.pack(side="left")
        self._save_button = Button(
            buttons, "儲存", self._save_clicked, kind="secondary", size=9
        )
        self._save_button.pack(side="left", padx=(6, 0))
        self._use_button = Button(
            buttons, "使用這個人設", self._use, kind="primary", size=9
        )
        self._use_button.pack(side="left", padx=(6, 0))

        self._scroll = ScrollArea(right)
        self._scroll.pack(fill="both", expand=True, padx=(18, 0))
        body = self._scroll.body
        self._blank_note = tk.Label(
            body,
            text=(
                "目前不使用人設：AI 用中性的口吻替你回覆。\n"
                "左邊選一個範本，或按「＋ 新人設」開始設計你的角色。"
            ),
            bg=theme.BG,
            fg=theme.MUTED,
            font=theme.font(11),
            justify="left",
        )
        self._editor = tk.Frame(body, bg=theme.BG)
        for title, subtitle, keys in SECTIONS:
            self._build_section(self._editor, title, subtitle, keys)
        self._build_preview(self._editor)

        self.reload()

    # ---- public ----------------------------------------------------------------

    def reload(self) -> None:
        if self._store is not None:
            try:
                self._state = self._store.load()
            except PersonaError as exc:
                self._on_status(str(exc))
                self._state = PersonaState([])
        self._editing = self._state.active
        self._render_list()
        self._load_editor()

    @property
    def state(self) -> PersonaState:
        return self._state

    def set_mood(self, mood: str) -> None:
        """Called from story mode; mood is global so it saves immediately."""
        self._state.mood = mood
        self._persist()
        self._on_apply(self._state.active_persona())
        self._update_preview()

    def flush(self) -> None:
        """Save pending edits (window hidden / page switched)."""
        if self._dirty:
            self._save(apply=True, quiet=True)

    # ---- building --------------------------------------------------------------

    def _build_section(
        self, parent: tk.Frame, title: str, subtitle: str, keys: tuple[str, ...]
    ) -> None:
        box = card(parent)
        box.outer.pack(fill="x", pady=(0, 12), padx=(0, 14))
        tk.Label(
            box, text=title, bg=theme.PANEL, fg=theme.TEXT, font=theme.font(11, "bold")
        ).pack(anchor="w")
        tk.Label(
            box,
            text=subtitle,
            bg=theme.PANEL,
            fg=theme.DIM,
            font=theme.font(9),
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        for key in keys:
            if key == "traits":
                for axis in TRAIT_AXES:
                    slider = TraitSlider(
                        box, axis.low, axis.high, lambda _v: self._changed()
                    )
                    slider.pack(anchor="w", pady=3)
                    self._sliders[axis.key] = slider
            elif key == "reply_length":
                row = tk.Frame(box, bg=theme.PANEL)
                row.pack(fill="x", pady=(2, 8))
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
                self._build_voice(box)
            elif key == "relationships":
                self._relations = tk.Frame(box, bg=theme.PANEL)
                self._relations.pack(fill="x")
                Button(
                    box, "＋ 新增一位", self._add_relation_row, kind="ghost", size=9
                ).pack(anchor="w", pady=(6, 0))
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
                field.pack(fill="x", pady=(0, 8))
                self._fields[key] = field

    def _build_voice(self, box: tk.Frame) -> None:
        grid = tk.Frame(box, bg=theme.PANEL)
        grid.pack(anchor="w", pady=(0, 8))
        for index, (voice, label) in enumerate(PERSONA_VOICES):
            chip = Chip(grid, label, lambda v=voice: self._pick_voice(v), size=9)
            chip.grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 6), pady=2)
            self._voice_chips[voice] = chip
        self._voice_knobs: dict[str, Segmented] = {}
        for key, label, steps in (
            ("voice_pitch", "音高", [(str(v), t) for v, t in PITCH_STEPS]),
            ("voice_speed", "語速", [(str(v), t) for v, t in SPEED_STEPS]),
            ("voice_effect", "音效", [(k, name) for k, (name, _) in VOICE_EFFECTS.items()]),
        ):
            row = tk.Frame(box, bg=theme.PANEL)
            row.pack(fill="x", pady=(2, 4))
            tk.Label(
                row, text=label, width=4, anchor="w", bg=theme.PANEL, fg=theme.MUTED,
                font=theme.font(9),
            ).pack(side="left", padx=(0, 10))
            knob = Segmented(row, steps, lambda _v: self._changed())
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
            bg=theme.PANEL, fg=theme.DIM, font=theme.font(8),
        ).pack(side="left", padx=(10, 0))

    def _pick_voice(self, voice: str) -> None:
        self._voice = voice
        for key, chip in self._voice_chips.items():
            chip.set_selected(key == voice)
        self._changed()

    def _preview_voice(self) -> None:
        persona = self._current()
        if persona is None or self._on_preview is None:
            return
        draft = self._collect()
        lines = [line.strip() for line in draft.sample_lines.splitlines() if line.strip()]
        text = lines[0] if lines else f"你好，我是{draft.name or '這個角色'}。"
        self._on_status("試聽中…")
        self._on_preview(draft, text)

    def _build_preview(self, parent: tk.Frame) -> None:
        box = card(parent, bg=theme.SURFACE)
        box.outer.pack(fill="x", pady=(0, 16), padx=(0, 14))
        top = tk.Frame(box, bg=theme.SURFACE)
        top.pack(fill="x")
        tk.Label(
            top,
            text="AI 實際看到的人設",
            bg=theme.SURFACE,
            fg=theme.TEXT,
            font=theme.font(11, "bold"),
        ).pack(side="left")
        self._meter_text = tk.Label(
            top, text="", bg=theme.SURFACE, fg=theme.MUTED, font=theme.font(9)
        )
        self._meter_text.pack(side="right")
        self._meter = tk.Canvas(box, height=6, bg=theme.SURFACE, highlightthickness=0)
        self._meter.pack(fill="x", pady=(6, 8))
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
        tk.Label(
            box,
            text=(
                f"建議控制在 {RECOMMENDED_PROMPT_CHARS} 字內：太長的人設會讓本機小模型"
                "開始不照四行格式，也會讓第一次回覆變慢（之後會被快取）。"
            ),
            bg=theme.SURFACE,
            fg=theme.DIM,
            font=theme.font(8),
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

    # ---- list --------------------------------------------------------------------

    def _render_list(self) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        entries = [(NONE_ID, "不使用人設", "中性口吻")] + [
            (p.id, p.name or "（未命名）", p.identity or "—")
            for p in self._state.personas
        ]
        for persona_id, name, subtitle in entries:
            self._list_row(persona_id, name, subtitle)

    def _list_row(self, persona_id: str, name: str, subtitle: str) -> None:
        editing = persona_id == self._editing
        active = persona_id == self._state.active
        bg = theme.PANEL_HI if editing else theme.SURFACE
        row = tk.Frame(self._list, bg=bg, cursor="hand2")
        row.pack(fill="x", padx=8, pady=1)
        marker = tk.Frame(row, bg=theme.ACCENT if editing else bg, width=3)
        marker.pack(side="left", fill="y")
        avatar = Avatar(row, 28, bg=bg)
        avatar.set_name("" if persona_id == NONE_ID else name)
        avatar.pack(side="left", padx=(8, 8), pady=7)
        text = tk.Frame(row, bg=bg)
        text.pack(side="left", fill="x", expand=True)
        title = tk.Frame(text, bg=bg)
        title.pack(anchor="w")
        tk.Label(
            title, text=name, bg=bg, fg=theme.TEXT, font=theme.font(10, "bold")
        ).pack(side="left")
        if active:
            tk.Label(
                title,
                text="使用中",
                bg=theme.OK,
                fg=theme.ACCENT_INK,
                font=theme.font(7, "bold"),
                padx=4,
            ).pack(side="left", padx=(6, 0))
        tk.Label(
            text,
            text=_trim(subtitle, 13),
            bg=bg,
            fg=theme.DIM,
            font=theme.font(8),
            anchor="w",
        ).pack(anchor="w")
        for widget in (
            row,
            marker,
            avatar,
            text,
            title,
            *text.winfo_children(),
            *title.winfo_children(),
        ):
            widget.bind("<Button-1>", lambda _, pid=persona_id: self._open(pid))
            widget.bind(
                "<Double-Button-1>", lambda _, pid=persona_id: self._activate(pid)
            )

    # ---- editor ------------------------------------------------------------------

    def _open(self, persona_id: str) -> None:
        if persona_id == self._editing:
            return
        if self._dirty and not self._save(apply=True, quiet=True):
            return
        self._editing = persona_id
        self._render_list()
        self._load_editor()
        self._scroll.scroll_to_top()

    def _current(self) -> Persona | None:
        return self._state.find(self._editing)

    def _load_editor(self) -> None:
        persona = self._current()
        self._loading = True
        try:
            if persona is None:
                self._editing = NONE_ID
                self._editor.pack_forget()
                self._blank_note.pack(anchor="w", pady=20)
                self._name_var.set("不使用人設")
                self._name_entry.configure(
                    state="disabled",
                    disabledbackground=theme.BG,
                    disabledforeground=theme.TEXT,
                )
                self._avatar.set_name("")
                self._delete_button.pack_forget()
                self._save_button.pack_forget()
            else:
                self._blank_note.pack_forget()
                self._editor.pack(fill="x")
                self._name_entry.configure(state="normal")
                self._name_var.set(persona.name)
                self._avatar.set_name(persona.name)
                for key, field in self._fields.items():
                    field.set(str(getattr(persona, key)))
                for axis in TRAIT_AXES:
                    self._sliders[axis.key].set(persona.trait(axis.key))
                self._length.set(persona.reply_length)
                self._pick_voice(persona.voice)
                self._voice_knobs["voice_pitch"].set(str(_nearest(persona.voice_pitch, PITCH_STEPS)))
                self._voice_knobs["voice_speed"].set(str(_nearest(persona.voice_speed, SPEED_STEPS)))
                self._voice_knobs["voice_effect"].set(persona.voice_effect)
                for frame, _, _ in self._relation_rows:
                    frame.destroy()
                self._relation_rows.clear()
                for rel in persona.relationships:
                    self._add_relation_row(rel)
                if not persona.relationships:
                    self._add_relation_row()
                self._delete_button.pack(side="left")
                self._save_button.pack(side="left", padx=(6, 0))
                self._use_button.pack_forget()
                self._use_button.pack(side="left", padx=(6, 0))
        finally:
            self._loading = False
        self._dirty = False
        self._update_chrome()
        self._update_preview()

    def _add_relation_row(self, rel: Relationship | None = None) -> None:
        frame = tk.Frame(self._relations, bg=theme.PANEL)
        frame.pack(fill="x", pady=2)
        name_var = tk.StringVar(value=rel.name if rel else "")
        relation_var = tk.StringVar(value=rel.relation if rel else "")
        for var, width, placeholder_width in ((name_var, 10, 0), (relation_var, 40, 1)):
            border = tk.Frame(frame, bg=theme.LINE, padx=1, pady=1)
            border.pack(
                side="left", padx=(0, 6), fill="x", expand=bool(placeholder_width)
            )
            entry = tk.Entry(
                border,
                textvariable=var,
                width=width,
                bg=theme.PANEL_HI,
                fg=theme.TEXT,
                insertbackground=theme.TEXT,
                relief="flat",
                font=theme.font(10),
            )
            entry.pack(fill="x", ipady=3)
            var.trace_add("write", lambda *_: self._changed())
        remove = tk.Label(
            frame,
            text="✕",
            bg=theme.PANEL,
            fg=theme.DIM,
            cursor="hand2",
            font=theme.font(10),
        )
        remove.pack(side="left")
        entry_row = (frame, name_var, relation_var)
        remove.bind("<Button-1>", lambda _: self._remove_relation_row(entry_row))
        self._relation_rows.append(entry_row)
        if rel is None and not self._loading:
            self._changed()

    def _remove_relation_row(
        self, row: tuple[tk.Frame, tk.StringVar, tk.StringVar]
    ) -> None:
        row[0].destroy()
        self._relation_rows.remove(row)
        self._changed()

    def _collect(self) -> Persona:
        base = self._current()
        assert base is not None
        values: dict[str, object] = {
            key: field.get() for key, field in self._fields.items()
        }
        return replace(
            base,
            name=self._name_var.get(),
            traits={axis.key: self._sliders[axis.key].get() for axis in TRAIT_AXES},
            reply_length=self._length.get(),
            voice=self._voice,
            voice_pitch=int(self._voice_knobs["voice_pitch"].get() or 0),
            voice_speed=int(self._voice_knobs["voice_speed"].get() or 0),
            voice_effect=self._voice_knobs["voice_effect"].get(),
            relationships=tuple(
                Relationship(name.get(), relation.get())
                for _, name, relation in self._relation_rows
            ),
            **values,  # type: ignore[arg-type]
        )

    def _changed(self) -> None:
        if self._loading or self._current() is None:
            return
        self._dirty = True
        self._avatar.set_name(self._name_var.get().strip())
        self._update_chrome()
        self._update_preview()

    def _update_chrome(self) -> None:
        persona = self._current()
        if persona is None:
            active = self._state.active == NONE_ID
            self._subtitle.configure(
                text="使用中" if active else "AI 用中性口吻",
                fg=theme.OK if active else theme.DIM,
            )
            self._use_button.configure(text="已在使用" if active else "改回不使用人設")
            self._use_button.set_enabled(not active)
            return
        active = persona.id == self._state.active
        parts = ["● 使用中" if active else "未使用"]
        if self._dirty:
            parts.append("未儲存的修改")
        self._subtitle.configure(
            text="　".join(parts),
            fg=theme.WARN if self._dirty else (theme.OK if active else theme.DIM),
        )
        self._use_button.configure(
            text="已在使用" if active and not self._dirty else "使用這個人設"
        )
        self._use_button.set_enabled(self._dirty or not active)
        self._save_button.set_enabled(self._dirty)
        self._length_hint.configure(text=REPLY_LENGTHS.get(self._length.get(), ""))

    def _update_preview(self) -> None:
        if self._current() is None:
            return
        try:
            persona = replace(self._collect(), mood=self._state.mood)
        except (TypeError, ValueError):
            return
        sheet = persona.render_system_block()
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

    # ---- actions -----------------------------------------------------------------

    def _save(self, *, apply: bool, quiet: bool = False) -> bool:
        persona = self._current()
        if persona is None:
            return True
        try:
            updated = validate_persona(self._collect())
        except PersonaError as exc:
            self._on_status(str(exc))
            return False
        self._state.personas = [
            updated if p.id == updated.id else p for p in self._state.personas
        ]
        if not self._persist():
            return False
        self._dirty = False
        self._render_list()
        self._update_chrome()
        if apply and updated.id == self._state.active:
            self._on_apply(self._state.active_persona())
        if not quiet:
            self._on_status(f"已儲存人設「{updated.name or '未命名'}」")
        return True

    def _save_clicked(self) -> None:
        self._save(apply=True)

    def _use(self) -> None:
        if self._current() is not None and not self._save(apply=False, quiet=True):
            return
        self._activate(self._editing)

    def _activate(self, persona_id: str) -> None:
        if self._dirty and not self._save(apply=False, quiet=True):
            return
        self._state.active = persona_id
        self._persist()
        self._editing = persona_id
        self._render_list()
        self._load_editor()
        persona = self._state.active_persona()
        self._on_apply(persona)
        self._on_status(
            f"現在以「{persona.name}」的身分回覆"
            if persona.name
            else "已改回不使用人設"
        )

    def _new(self) -> None:
        self._add(replace(blank_persona(new_persona_id()), name="新人設"))

    def _duplicate(self) -> None:
        source = self._current()
        if source is None:
            self._new()
            return
        if self._dirty and not self._save(apply=True, quiet=True):
            return
        self._add(
            replace(source, id=new_persona_id(), name=_trim(source.name + " 副本", 24))
        )

    def _add(self, persona: Persona) -> None:
        if self._dirty and not self._save(apply=True, quiet=True):
            return
        if (
            self._store is not None
            and len(self._state.personas) >= self._store.max_personas
        ):
            self._on_status(f"人設最多 {self._store.max_personas} 個")
            return
        self._state.personas.append(persona)
        self._persist()
        self._editing = persona.id
        self._render_list()
        self._load_editor()
        self._scroll.scroll_to_top()
        self._name_entry.focus_set()
        self._name_entry.select_range(0, "end")

    def _delete(self) -> None:
        persona = self._current()
        if persona is None:
            return
        if not getattr(self, "_confirm_delete", False):
            self._confirm_delete = True
            self._delete_button.configure(text="再按一次確認刪除")
            self.after(3000, self._reset_delete)
            return
        self._reset_delete()
        self._state.personas = [p for p in self._state.personas if p.id != persona.id]
        was_active = self._state.active == persona.id
        if was_active:
            self._state.active = NONE_ID
        self._persist()
        self._dirty = False
        self._editing = NONE_ID
        self._render_list()
        self._load_editor()
        if was_active:
            self._on_apply(self._state.active_persona())
        self._on_status(f"已刪除人設「{persona.name or '未命名'}」")

    def _reset_delete(self) -> None:
        self._confirm_delete = False
        self._delete_button.configure(text="刪除")

    def _persist(self) -> bool:
        if self._store is None:
            return True
        try:
            self._store.save(self._state)
        except PersonaError as exc:
            self._on_status(str(exc))
            return False
        return True


def _trim(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _nearest(value: int, steps: tuple[tuple[int, str], ...]) -> int:
    """Hand-edited personas.json may hold any value; show the closest step."""
    return min((step for step, _ in steps), key=lambda step: abs(step - value))
