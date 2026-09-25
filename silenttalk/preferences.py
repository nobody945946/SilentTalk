from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from silenttalk.speech_settings import (
    DEFAULT_RATE_MULTIPLIER,
    validate_rate_multiplier,
)

UI_MODES = ("manual", "story")


class PreferenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UserPreferences:
    speech_rate_multiplier: float = DEFAULT_RATE_MULTIPLIER
    ui_mode: str = "manual"


class PreferenceStore:
    """Persist lightweight local UI preferences outside config.toml."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> UserPreferences:
        if not self.path.exists():
            return UserPreferences()

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PreferenceError(f"UI 偏好設定讀取失敗：{exc}") from exc

        if not isinstance(raw, dict):
            raise PreferenceError("UI 偏好設定格式錯誤。")

        try:
            rate = validate_rate_multiplier(
                float(raw.get("speech_rate_multiplier", DEFAULT_RATE_MULTIPLIER))
            )
        except (TypeError, ValueError) as exc:
            raise PreferenceError(f"UI 語速設定無效：{exc}") from exc

        mode = str(raw.get("ui_mode", "manual"))
        if mode not in UI_MODES:
            mode = "manual"
        return UserPreferences(speech_rate_multiplier=rate, ui_mode=mode)

    def save(self, preferences: UserPreferences) -> None:
        try:
            validate_rate_multiplier(preferences.speech_rate_multiplier)
        except ValueError as exc:
            raise PreferenceError(str(exc)) from exc
        if preferences.ui_mode not in UI_MODES:
            raise PreferenceError(f"未知 UI 模式：{preferences.ui_mode}")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(asdict(preferences), ensure_ascii=False, indent=2) + "\n"
        try:
            temp_path.write_text(payload, encoding="utf-8")
            temp_path.replace(self.path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise PreferenceError(f"UI 偏好設定寫入失敗：{exc}") from exc
