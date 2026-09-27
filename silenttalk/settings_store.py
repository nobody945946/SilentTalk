"""User settings from the UI, kept apart from config.toml.

config.toml stays the readable file of defaults (with its comments); this
file holds only what the user changed on the settings page, so an upgrade
still brings new defaults and nothing is silently rewritten.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SETTINGS_FILE = "settings.json"


class SettingsError(ValueError):
    pass


class SettingsStore:
    """{"copilot": {"character_engagement": "active"}, ...} on top of the TOML."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SettingsError(f"設定檔讀取失敗：{exc}") from exc
        if not isinstance(raw, dict):
            raise SettingsError("設定檔格式錯誤：必須是物件。")
        return {
            str(section): dict(values)
            for section, values in raw.items()
            if isinstance(values, dict)
        }

    def save(self, overrides: dict[str, dict[str, Any]]) -> None:
        payload = {
            section: values for section, values in sorted(overrides.items()) if values
        }
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(self.path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise SettingsError(f"設定檔寫入失敗：{exc}") from exc


def merge(base: dict[str, Any], overrides: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """TOML tables with the user's values applied on top, per key."""
    merged = {key: dict(value) if isinstance(value, dict) else value
              for key, value in base.items()}
    for section, values in overrides.items():
        table = merged.get(section)
        merged[section] = {**table, **values} if isinstance(table, dict) else dict(values)
    return merged
