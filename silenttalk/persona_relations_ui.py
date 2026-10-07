"""人設 page: pick who "你" is and edit the character sheet the LLM follows."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from silenttalk import theme
from silenttalk.persona import (
    Persona,
    Relationship,
)

ApplyCallback = Callable[[Persona], None]
StatusCallback = Callable[[str], None]
PreviewCallback = Callable[[Persona, str], None]

NONE_ID = "none"


class RelationshipEditor:
    def __init__(self, parent, on_change):
        self._relations, self._changed = parent, on_change
        self._relation_rows = []
        self._loading = False

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
                highlightthickness=0,
                font=theme.font(10),
            )
            entry.pack(fill="x", ipady=theme.px(5), ipadx=theme.px(6))
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

    def load(self, relationships):
        self._loading = True
        try:
            for frame, _, _ in self._relation_rows:
                frame.destroy()
            self._relation_rows.clear()
            for relation in relationships:
                self._add_relation_row(relation)
            if not relationships:
                self._add_relation_row()
        finally:
            self._loading = False

    def values(self):
        return tuple(
            Relationship(name.get(), relation.get())
            for _, name, relation in self._relation_rows
        )
