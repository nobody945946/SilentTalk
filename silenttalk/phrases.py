from __future__ import annotations

import json
from pathlib import Path


class QuickPhraseError(ValueError):
    pass


class QuickPhraseStore:
    """Persist user-defined quick phrases in a small local JSON file."""

    def __init__(self, path: Path, max_phrases: int = 50) -> None:
        self.path = path
        self.max_phrases = max_phrases

    def load(self) -> list[str]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QuickPhraseError(f"快捷句檔案讀取失敗：{exc}") from exc

        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise QuickPhraseError("快捷句檔案格式錯誤：必須是字串陣列。")

        phrases = [item.strip() for item in raw]
        if any(not item for item in phrases):
            raise QuickPhraseError("快捷句檔案格式錯誤：不可包含空白項目。")
        if len(phrases) > self.max_phrases:
            raise QuickPhraseError(
                f"快捷句數量超過上限：最多 {self.max_phrases} 句。"
            )
        return phrases

    def add(self, text: str) -> list[str]:
        phrase = self._validate_text(text)
        phrases = self.load()
        if len(phrases) >= self.max_phrases:
            raise QuickPhraseError(f"快捷句最多 {self.max_phrases} 句。")
        if phrase in phrases:
            raise QuickPhraseError("這句快捷句已存在。")
        phrases.append(phrase)
        self._save(phrases)
        return phrases

    def update(self, index: int, text: str) -> list[str]:
        phrase = self._validate_text(text)
        phrases = self.load()
        self._validate_index(index, phrases)
        if phrase in phrases and phrases[index] != phrase:
            raise QuickPhraseError("這句快捷句已存在。")
        phrases[index] = phrase
        self._save(phrases)
        return phrases

    def delete(self, index: int) -> list[str]:
        phrases = self.load()
        self._validate_index(index, phrases)
        del phrases[index]
        self._save(phrases)
        return phrases

    @staticmethod
    def _validate_text(text: str) -> str:
        phrase = text.strip()
        if not phrase:
            raise QuickPhraseError("快捷句不可為空白。")
        return phrase

    @staticmethod
    def _validate_index(index: int, phrases: list[str]) -> None:
        if index < 0 or index >= len(phrases):
            raise QuickPhraseError("找不到指定的快捷句。")

    def _save(self, phrases: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(phrases, ensure_ascii=False, indent=2) + "\n"
        try:
            temp_path.write_text(payload, encoding="utf-8")
            temp_path.replace(self.path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise QuickPhraseError(f"快捷句檔案寫入失敗：{exc}") from exc
