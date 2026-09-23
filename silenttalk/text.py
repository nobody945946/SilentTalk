from __future__ import annotations

import re
import unicodedata

_INLINE_WHITESPACE = re.compile(r"[^\S\r\n]+")
_EXCESS_NEWLINES = re.compile(r"\n{3,}")


class TextValidationError(ValueError):
    pass


def normalize_text(text: str, max_length: int) -> str:
    """Apply only deterministic, meaning-preserving normalization."""
    normalized = unicodedata.normalize(
        "NFC", text.replace("\r\n", "\n").replace("\r", "\n")
    )
    normalized = "\n".join(
        _INLINE_WHITESPACE.sub(" ", line).strip() for line in normalized.split("\n")
    )
    normalized = _EXCESS_NEWLINES.sub("\n\n", normalized).strip()
    if not normalized:
        raise TextValidationError("請輸入要播放的文字。")
    if len(normalized) > max_length:
        raise TextValidationError(
            f"文字過長：最多 {max_length} 字，目前 {len(normalized)} 字。"
        )
    return normalized
