"""The settings page: every config.toml value, grouped, one screen at a time.

Rendered from settings_schema.PAGES, so adding a setting is one entry there.
Changes are written to settings.json (config.toml keeps the defaults) and
applied live where they can be; the rest is marked as needing a restart.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Any

from silenttalk import theme
from silenttalk.settings_schema import PAGES, Page, Setting
from silenttalk.settings_store import SettingsError, SettingsStore
from silenttalk.widgets import (
    Chip,
    Disclosure,
    ScrollArea,
    Segmented,
    Stepper,
    Toggle,
    card,
    wrap_to_width,
)

StatusCallback = Callable[[str], None]
# Called with the merged section tables after a successful save, so the app
# can apply what does not need a restart.
ApplyCallback = Callable[[dict[str, dict[str, Any]]], None]


class SettingsPanel(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        store: SettingsStore | None,
        defaults: dict[str, dict[str, Any]],
        *,
        on_status: StatusCallback,
        on_apply: ApplyCallback | None = None,
    ) -> None:
        super().__init__(master, bg=theme.BG)
        self._store = store
        self._defaults = defaults
        self._on_status = on_status
        self._on_apply = on_apply
        self._overrides: dict[str, dict[str, Any]] = {}
        self._editors: dict[tuple[str, str], Any] = {}
        self._reset_chips: dict[tuple[str, str], Chip] = {}
        self._page_bodies: dict[str, tk.Frame] = {}
        self._page_items: dict[str, tuple[tk.Frame, tk.Label]] = {}
        self._custom_slots: dict[str, tk.Frame] = {}
        self._custom_show_hooks: dict[str, list[Callable[[], None]]] = {}
        self._settings: dict[tuple[str, str], Setting] = {}
        self._restart_pending = False

        # A list of categories on the left, as in macOS System Settings and
        # Windows 11 Settings; one category's settings on the right.
        left = tk.Frame(self, bg=theme.SURFACE)
        left.pack(side="left", fill="y")
        tk.Label(
            left, text="設定", bg=theme.SURFACE, fg=theme.TEXT,
            font=theme.font(15, "bold"),
        ).pack(anchor="w", padx=theme.px(18), pady=(theme.px(18), 0))
        tk.Label(
            left, text="改完自動存檔", bg=theme.SURFACE, fg=theme.DIM,
            font=theme.font(9),
        ).pack(anchor="w", padx=theme.px(18), pady=(0, theme.px(12)))
        self._nav = tk.Frame(left, bg=theme.SURFACE)
        self._nav.pack(fill="x", padx=theme.px(8))
        self._restart_note = tk.Label(
            left, text="", bg=theme.SURFACE, fg=theme.WARN, font=theme.font(9),
            justify="left", anchor="w",
        )
        self._restart_note.pack(side="bottom", fill="x", padx=theme.px(18), pady=theme.px(14))
        wrap_to_width(self._restart_note)

        right = tk.Frame(self, bg=theme.BG)
        right.pack(side="left", fill="both", expand=True)
        self._scroll = ScrollArea(right)
        self._scroll.pack(fill="both", expand=True, padx=(theme.px(24), 0), pady=(theme.px(18), 0))

        for page in PAGES:
            item = tk.Frame(self._nav, bg=theme.SURFACE, cursor="hand2")
            item.pack(fill="x", pady=1)
            label = tk.Label(
                item, text=page.label, bg=theme.SURFACE, fg=theme.MUTED,
                font=theme.font(10), anchor="w", padx=theme.px(12), pady=theme.px(6),
            )
            label.pack(fill="x")
            for widget in (item, label):
                widget.bind("<Button-1>", lambda _, key=page.key: self.show(key))
            self._page_items[page.key] = (item, label)
            self._page_bodies[page.key] = self._build_page(page)
        # Widest label + padding, measured instead of a fixed pixel width.
        left.configure(width=max(theme.px(150), left.winfo_reqwidth()))

        self.reload()
        self.show(PAGES[0].key)

    # ---- public ----------------------------------------------------------------

    def reload(self) -> None:
        if self._store is not None:
            try:
                self._overrides = self._store.load()
            except SettingsError as exc:
                self._on_status(str(exc))
                self._overrides = {}
        for (section, key), editor in self._editors.items():
            editor.set(self._value_of(section, key))
            self._render_reset(section, key)

    def show(self, page_key: str) -> None:
        if page_key not in self._page_bodies:
            return
        for key, body in self._page_bodies.items():
            body.pack_forget()
            item, label = self._page_items[key]
            selected = key == page_key
            item.configure(bg=theme.PANEL if selected else theme.SURFACE)
            label.configure(
                bg=theme.PANEL if selected else theme.SURFACE,
                fg=theme.TEXT if selected else theme.MUTED,
            )
        self._page_bodies[page_key].pack(fill="x", padx=(0, theme.px(18)))
        self._scroll.scroll_to_top()
        for hook in self._custom_show_hooks.get(page_key, []):
            hook()

    def add_custom_group(
        self,
        page_key: str,
        build: Callable[[tk.Frame], None],
        *,
        on_show: Callable[[], None] | None = None,
    ) -> None:
        """Settings kept outside config.toml (the voice picker, what the model
        runs on) at the top of a page, built by the owner."""
        build(self._custom_slots[page_key])
        if on_show is not None:
            self._custom_show_hooks.setdefault(page_key, []).append(on_show)

    def value(self, section: str, key: str) -> Any:
        return self._value_of(section, key)

    def set_value(self, section: str, key: str, value: Any) -> None:
        """Change a setting from elsewhere in the UI, exactly as its editor
        here would: shown, saved and applied."""
        setting = self._settings.get((section, key))
        if setting is None:
            return
        self._editors[(section, key)].set(value)
        self._changed(setting, value)

    # ---- building --------------------------------------------------------------

    def _build_page(self, page: Page) -> tk.Frame:
        body = tk.Frame(self._scroll.body, bg=theme.BG)
        tk.Label(
            body, text=page.label, bg=theme.BG, fg=theme.TEXT, font=theme.font(15, "bold")
        ).pack(anchor="w", pady=(0, theme.px(12)))
        self._custom_slots[page.key] = tk.Frame(body, bg=theme.BG)
        self._custom_slots[page.key].pack(fill="x")
        everyday = [group for group in page.groups if not group.advanced]
        advanced = [group for group in page.groups if group.advanced]
        for group in everyday:
            box = card(body)
            box.outer.pack(fill="x", pady=(0, theme.px(12)))
            self._build_group(box, group)
        if advanced:
            # Rarely touched: one click deeper.
            more = Disclosure(body, "進階", "、".join(group.title for group in advanced))
            more.pack(fill="x", pady=(0, theme.px(12)))
            for group in advanced:
                self._build_group(more.body, group)
        return body

    def _build_group(self, box: tk.Frame, group: Any) -> None:
        tk.Label(
            box, text=group.title, bg=theme.PANEL, fg=theme.TEXT,
            font=theme.font(11, "bold"),
        ).pack(anchor="w", pady=(theme.px(4), 0))
        if group.subtitle:
            wrap_to_width(
                tk.Label(
                    box, text=group.subtitle, bg=theme.PANEL, fg=theme.DIM,
                    font=theme.font(9), justify="left", anchor="w",
                )
            ).pack(anchor="w", fill="x", pady=(0, theme.px(4)))
        for setting in group.settings:
            self._build_row(box, setting)

    def _build_row(self, parent: tk.Frame, setting: Setting) -> None:
        self._settings[(setting.section, setting.key)] = setting
        row = tk.Frame(parent, bg=theme.PANEL)
        row.pack(fill="x", pady=(theme.px(8), 0))
        head = tk.Frame(row, bg=theme.PANEL)
        head.pack(fill="x")
        tk.Label(
            head, text=setting.label, bg=theme.PANEL, fg=theme.TEXT,
            font=theme.font(10),
        ).pack(side="left")
        if setting.restart:
            tk.Label(
                head, text="需重開", bg=theme.PANEL, fg=theme.WARN, font=theme.font(9)
            ).pack(side="left", padx=(theme.px(6), 0))
        reset = Chip(head, "回預設", lambda s=setting: self._reset(s), size=9)
        self._reset_chips[(setting.section, setting.key)] = reset

        editor = self._build_editor(row, setting)
        editor.pack(anchor="w", pady=(theme.px(6), 0))
        self._editors[(setting.section, setting.key)] = editor
        if setting.help:
            wrap_to_width(
                tk.Label(
                    row, text=setting.help, bg=theme.PANEL, fg=theme.DIM,
                    font=theme.font(9), justify="left", anchor="w",
                )
            ).pack(anchor="w", fill="x", pady=(theme.px(4), 0))
        tk.Frame(row, bg=theme.LINE, height=1).pack(fill="x", pady=(theme.px(10), 0))

    def _build_editor(self, row: tk.Frame, setting: Setting) -> Any:
        change = lambda value, s=setting: self._changed(s, value)  # noqa: E731
        if setting.kind == "bool":
            return Toggle(row, change)
        if setting.kind == "choice":
            wide = len(setting.choices) > 3 or any(
                len(label) > 14 for _value, label in setting.choices
            )
            if wide:
                return _ChoiceGrid(row, setting.choices, change)
            return Segmented(row, [(value, label) for value, label in setting.choices], change)
        if setting.kind in ("int", "float"):
            return Stepper(
                row,
                minimum=setting.minimum,
                maximum=setting.maximum,
                step=setting.step,
                decimals=1 if setting.kind == "float" and setting.step < 1 else 0,
                unit=setting.unit,
                command=change,
            )
        return _TextEditor(row, change)

    # ---- state -----------------------------------------------------------------

    def _value_of(self, section: str, key: str) -> Any:
        override = self._overrides.get(section, {})
        if key in override:
            return override[key]
        return self._defaults.get(section, {}).get(key)

    def _changed(self, setting: Setting, value: Any) -> None:
        if setting.kind == "int":
            value = int(value)
        default = self._defaults.get(setting.section, {}).get(setting.key)
        section = self._overrides.setdefault(setting.section, {})
        if _same(value, default):
            section.pop(setting.key, None)
        else:
            section[setting.key] = value
        self._render_reset(setting.section, setting.key)
        self._save(setting)

    def _reset(self, setting: Setting) -> None:
        self._overrides.get(setting.section, {}).pop(setting.key, None)
        editor = self._editors[(setting.section, setting.key)]
        editor.set(self._defaults.get(setting.section, {}).get(setting.key))
        self._render_reset(setting.section, setting.key)
        self._save(setting)

    def _render_reset(self, section: str, key: str) -> None:
        chip = self._reset_chips.get((section, key))
        if chip is None:
            return
        if key in self._overrides.get(section, {}):
            chip.pack(side="right")
        else:
            chip.pack_forget()

    def _save(self, setting: Setting) -> None:
        if self._store is None:
            return
        try:
            self._store.save(self._overrides)
        except SettingsError as exc:
            self._on_status(str(exc))
            return
        if setting.restart:
            self._restart_pending = True
            self._restart_note.configure(text="有設定要重新啟動 SilentTalk 才會生效")
            self._on_status(f"已存檔：「{setting.label}」重新啟動後生效")
        else:
            self._on_status(f"已套用：{setting.label}")
        if self._on_apply is not None:
            self._on_apply(
                {
                    name: {**self._defaults.get(name, {}), **values}
                    for name, values in (
                        (name, self._overrides.get(name, {}))
                        for name in self._defaults
                    )
                }
            )


class _ChoiceGrid(tk.Frame):
    """Chips laid out in rows: for choices that would overflow a segmented
    control (a dozen voices, long model names)."""

    def __init__(
        self,
        master: tk.Misc,
        choices: tuple[tuple[str, str], ...],
        command: Callable[[str], object],
        *,
        columns: int = 2,
    ) -> None:
        super().__init__(master, bg=theme.PANEL)
        self._command = command
        self._value = ""
        self._chips: dict[str, Chip] = {}
        for index, (value, label) in enumerate(choices):
            chip = Chip(self, label, lambda v=value: self._pick(v), size=9)
            chip.grid(row=index // columns, column=index % columns, sticky="w",
                      padx=(0, 6), pady=2)
            self._chips[value] = chip

    def _pick(self, value: str) -> None:
        self.set(value, notify=True)

    def get(self) -> str:
        return self._value

    def set(self, value: Any, *, notify: bool = False) -> None:
        self._value = "" if value is None else str(value)
        for key, chip in self._chips.items():
            chip.set_selected(key == self._value)
        if notify:
            self._command(self._value)


class _TextEditor(tk.Frame):
    """Free text (a path, a "+0%" tweak): applied when you leave the box."""

    def __init__(self, master: tk.Misc, command: Callable[[str], object]) -> None:
        super().__init__(master, bg=theme.PANEL)
        self._command = command
        self._var = tk.StringVar()
        border = tk.Frame(self, bg=theme.PANEL_HI, padx=1, pady=1)
        border.pack(fill="x")
        entry = tk.Entry(
            border, textvariable=self._var, width=34, bg=theme.PANEL_HI,
            fg=theme.TEXT, insertbackground=theme.TEXT, relief="flat",
            highlightthickness=0, font=theme.font(10),
        )
        entry.pack(fill="x", ipady=theme.px(5), ipadx=theme.px(6))
        entry.bind("<FocusIn>", lambda _: border.configure(bg=theme.ACCENT))
        entry.bind("<FocusOut>", lambda _: self._commit(border))
        entry.bind("<Return>", lambda _: self._commit(border))

    def _commit(self, border: tk.Frame) -> None:
        border.configure(bg=theme.PANEL_HI)
        self._command(self._var.get().strip())

    def get(self) -> str:
        return self._var.get().strip()

    def set(self, value: Any, *, notify: bool = False) -> None:
        self._var.set("" if value is None else str(value))
        if notify:
            self._command(self.get())


def _same(value: Any, default: Any) -> bool:
    if isinstance(value, bool) or isinstance(default, bool):
        return bool(value) == bool(default)
    if isinstance(value, int | float) and isinstance(default, int | float):
        return abs(float(value) - float(default)) < 1e-9
    return str(value) == str(default)
