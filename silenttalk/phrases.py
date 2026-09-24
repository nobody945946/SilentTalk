from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from silenttalk.voice_styles import VOICE_STYLES


class QuickPhraseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class QuickPhrase:
    text: str
    voice_style: str = "default"


DEFAULT_QUICK_PHRASES: tuple[QuickPhrase, ...] = (
    QuickPhrase("For the Emperor!", "space_marine"),
    QuickPhrase("The Emperor protects!", "space_marine_commander"),
    QuickPhrase("For the Omnissiah!", "mechanicus"),
    QuickPhrase("No pity! No remorse! No fear!", "chaplain"),
    QuickPhrase("Blood for the Blood God!", "chaos"),
    QuickPhrase("WAAAGH!", "ork"),
)


class QuickPhraseStore:
    """Persist quick phrases together with their per-phrase voice style."""

    def __init__(self, path: Path, max_phrases: int = 50) -> None:
        self.path = path
        self.max_phrases = max_phrases

    def load(self) -> list[QuickPhrase]:
        if not self.path.exists():
            return list(DEFAULT_QUICK_PHRASES)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QuickPhraseError(f"快捷句檔案讀取失敗：{exc}") from exc

        if not isinstance(raw, list):
            raise QuickPhraseError("快捷句檔案格式錯誤：必須是陣列。")

        phrases: list[QuickPhrase] = []
        for item in raw:
            # Backward compatibility: old releases stored a plain string array.
            if isinstance(item, str):
                phrase = QuickPhrase(item.strip(), "default")
            elif isinstance(item, dict):
                text = item.get("text")
                style = item.get("voice_style", "default")
                if not isinstance(text, str) or not isinstance(style, str):
                    raise QuickPhraseError("快捷句物件格式錯誤。")
                phrase = QuickPhrase(text.strip(), style)
            else:
                raise QuickPhraseError("快捷句格式錯誤：項目必須是字串或物件。")
            self._validate_phrase(phrase)
            phrases.append(phrase)

        if len(phrases) > self.max_phrases:
            raise QuickPhraseError(
                f"快捷句數量超過上限：最多 {self.max_phrases} 句。"
            )
        return phrases

    def add(self, text: str, voice_style: str = "default") -> list[QuickPhrase]:
        phrase = self._make_phrase(text, voice_style)
        phrases = self.load()
        if len(phrases) >= self.max_phrases:
            raise QuickPhraseError(f"快捷句最多 {self.max_phrases} 句。")
        if any(existing.text == phrase.text for existing in phrases):
            raise QuickPhraseError("這句快捷句已存在。")
        phrases.append(phrase)
        self._save(phrases)
        return phrases

    def update(
        self, index: int, text: str, voice_style: str = "default"
    ) -> list[QuickPhrase]:
        phrase = self._make_phrase(text, voice_style)
        phrases = self.load()
        self._validate_index(index, phrases)
        if any(
            i != index and existing.text == phrase.text
            for i, existing in enumerate(phrases)
        ):
            raise QuickPhraseError("這句快捷句已存在。")
        phrases[index] = phrase
        self._save(phrases)
        return phrases

    def delete(self, index: int) -> list[QuickPhrase]:
        phrases = self.load()
        self._validate_index(index, phrases)
        del phrases[index]
        self._save(phrases)
        return phrases

    @classmethod
    def _make_phrase(cls, text: str, voice_style: str) -> QuickPhrase:
        phrase = QuickPhrase(text.strip(), voice_style)
        cls._validate_phrase(phrase)
        return phrase

    @staticmethod
    def _validate_phrase(phrase: QuickPhrase) -> None:
        if not phrase.text:
            raise QuickPhraseError("快捷句不可為空白。")
        if phrase.voice_style not in VOICE_STYLES:
            raise QuickPhraseError(f"未知快捷句聲線：{phrase.voice_style}")

    @staticmethod
    def _validate_index(index: int, phrases: list[QuickPhrase]) -> None:
        if index < 0 or index >= len(phrases):
            raise QuickPhraseError("找不到指定的快捷句。")

    def _save(self, phrases: list[QuickPhrase]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(
            [
                {"text": phrase.text, "voice_style": phrase.voice_style}
                for phrase in phrases
            ],
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        try:
            temp_path.write_text(payload, encoding="utf-8")
            temp_path.replace(self.path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise QuickPhraseError(f"快捷句檔案寫入失敗：{exc}") from exc
