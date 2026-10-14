from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from silenttalk.speech_settings import (
    DEFAULT_RATE_MULTIPLIER,
    validate_rate_multiplier,
)


class PreferenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UserPreferences:
    speech_rate_multiplier: float = DEFAULT_RATE_MULTIPLIER


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
        # Keys this version no longer has (ui_mode, the saved 選項/打字 mode
        # until 2026-10-15) are ignored.
        return UserPreferences(speech_rate_multiplier=rate)

    def save(self, preferences: UserPreferences) -> None:
        try:
            validate_rate_multiplier(preferences.speech_rate_multiplier)
        except ValueError as exc:
            raise PreferenceError(str(exc)) from exc

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(asdict(preferences), ensure_ascii=False, indent=2) + "\n"
        try:
            temp_path.write_text(payload, encoding="utf-8")
            temp_path.replace(self.path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise PreferenceError(f"UI 偏好設定寫入失敗：{exc}") from exc
