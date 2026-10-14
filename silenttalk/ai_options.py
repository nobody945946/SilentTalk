MEMORY_LEVELS = ("off", "light", "full")
LORA_PARTS = ("called", "active", "line", "task", "scope")
# 選項模式 removed 2026-10-15; a settings.json written before may still name it.
REMOVED_LORA_PARTS = ("options",)


AI_HONESTY_MODES: tuple[tuple[str, str], ...] = (
    ("in_character", "照角色演（不承認）"),
    ("admit", "承認自己是 AI"),
    ("machine", "機器角色（自認是機器，不說是 AI）"),
)
ENGAGEMENT_MODES: tuple[tuple[str, str], ...] = (
    ("called", "被叫到才回"),
    ("active", "會主動加入"),
)
