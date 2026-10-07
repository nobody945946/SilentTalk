"""人設 page: pick who "你" is and edit the character sheet the LLM follows."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import replace

from silenttalk import theme
from silenttalk.persona import (
    MACHINE_SPIRIT,
    Persona,
    PersonaError,
    PersonaState,
    PersonaStore,
    blank_persona,
    new_persona_id,
    validate_persona,
)
from silenttalk.persona_fields_ui import PersonaFields
from silenttalk.persona_preview_ui import PersonaPreview
from silenttalk.widgets.avatar import Avatar
from silenttalk.widgets.button import Button
from silenttalk.widgets.scroll import ScrollArea

ApplyCallback = Callable[[Persona], None]
StatusCallback = Callable[[str], None]
PreviewCallback = Callable[[Persona, str], None]

NONE_ID = "none"

# (section title, subtitle, fields, open at first). Fields are keys of
# TEXT_FIELDS, or the special "traits" / "reply_length" / "relationships" /
# "voice" editors. Only what reaches the model (Persona.render_prompt_block)
# is here: catchphrases, sample lines, pet peeves, knowledge, secrets and
# boundaries were copied word for word or did nothing for a small model.
# Older personas keep those values in personas.json; they are just not shown.


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
        self._store = store
        self._on_apply = on_apply
        self._on_status = on_status
        self._state = PersonaState([])
        self._editing: str = NONE_ID
        self._dirty = False
        self._loading = False

        # ---- left: persona list ----------------------------------------------
        left = tk.Frame(self, bg=theme.SURFACE, width=theme.px(230))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(
            left,
            text="人設",
            bg=theme.SURFACE,
            fg=theme.TEXT,
            font=theme.font(15, "bold"),
        ).pack(anchor="w", padx=theme.px(18), pady=(theme.px(18), 0))
        tk.Label(
            left,
            text="Bot 扮演或替你說話時的身分",
            bg=theme.SURFACE,
            fg=theme.DIM,
            font=theme.font(9),
        ).pack(anchor="w", padx=theme.px(18), pady=(0, theme.px(12)))
        self._list = tk.Frame(left, bg=theme.SURFACE)
        self._list.pack(fill="x")
        actions = tk.Frame(left, bg=theme.SURFACE)
        actions.pack(fill="x", side="bottom", padx=theme.px(12), pady=theme.px(14))
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
        bar.pack(fill="x", padx=theme.px(24), pady=(theme.px(18), theme.px(12)))
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
            highlightthickness=1,
            highlightbackground=theme.BG,
            highlightcolor=theme.ACCENT,
            font=theme.font(15, "bold"),
            width=14,
        )
        self._name_entry.pack(anchor="w", fill="x")
        # Looks like a title until you hover it; then it shows it is editable.
        self._name_entry.bind(
            "<Enter>",
            lambda _: self._name_entry.configure(highlightbackground=theme.LINE),
        )
        self._name_entry.bind(
            "<Leave>",
            lambda _: self._name_entry.configure(highlightbackground=theme.BG),
        )
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
        self._scroll.pack(fill="both", expand=True, padx=(theme.px(24), 0))
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
        self.fields = PersonaFields(
            self._editor, on_change=self._changed, on_preview=self._preview_voice
        )
        self.preview = PersonaPreview(self._editor)

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

    def _preview_voice(self) -> None:
        persona = self._current()
        if persona is None or self._on_preview is None:
            return
        draft = self.fields.collect(self._current(), self._name_var.get())
        lines = [
            line.strip() for line in draft.sample_lines.splitlines() if line.strip()
        ]
        text = lines[0] if lines else f"你好，我是{draft.name or '這個角色'}。"
        self._on_status("試聽中…")
        self._on_preview(draft, text)

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
        marker = tk.Frame(row, bg=theme.ACCENT if editing else bg, width=theme.px(3))
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
                self.fields.load(persona)
                if persona.id == MACHINE_SPIRIT.id:
                    self._delete_button.pack_forget()
                else:
                    self._delete_button.pack(side="left")
                self._save_button.pack(side="left", padx=(6, 0))
                self._use_button.pack_forget()
                self._use_button.pack(side="left", padx=(6, 0))
        finally:
            self._loading = False
        self._dirty = False
        self._update_chrome()
        self._update_preview()

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
        if persona.id == MACHINE_SPIRIT.id:
            parts.append("內建角色，不能刪除")
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

    def _update_preview(self) -> None:
        persona = self._current()
        if persona is None:
            return
        try:
            draft = self.fields.collect(persona, self._name_var.get())
            self.preview.render(replace(draft, mood=self._state.mood))
        except (TypeError, ValueError):
            return

    # ---- actions -----------------------------------------------------------------

    def _save(self, *, apply: bool, quiet: bool = False) -> bool:
        persona = self._current()
        if persona is None:
            return True
        try:
            updated = validate_persona(
                self.fields.collect(self._current(), self._name_var.get())
            )
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
        if persona.id == MACHINE_SPIRIT.id:
            self._on_status("機魂是內建角色，不能刪除；可編輯或複製人設。")
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
