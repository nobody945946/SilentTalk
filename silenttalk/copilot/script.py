"""Simplified -> Taiwan Traditional for STT output.

The bilingual Paraformer model is trained on Mainland Mandarin and always
writes Simplified Chinese. Converting before the text reaches context keeps the
LLM answering in Traditional and the UI readable for Taiwanese users.
"""

from __future__ import annotations

import logging
from functools import cache

_LOG = logging.getLogger(__name__)


@cache
def _converter() -> object | None:
    try:
        # opencc-python-reimplemented: pure Python, installs as module `opencc`.
        from opencc import OpenCC
    except ImportError:
        _LOG.warning("copilot_s2tw_unavailable")
        return None
    return OpenCC("s2twp")


@cache
def _characters_only() -> object | None:
    try:
        from opencc import OpenCC
    except ImportError:
        return None
    return OpenCC("s2t")


def to_taiwan_traditional(text: str) -> str:
    converter = _converter()
    if converter is None or not text:
        return text
    # s2twp also swaps phrases for Taiwanese ones, which corrupts text that is
    # already Traditional ("測試通過" -> "測試透過"). Only text that still has
    # Simplified characters is converted.
    if str(_characters_only().convert(text)) == text:  # type: ignore[attr-defined]
        return text
    return str(converter.convert(text))  # type: ignore[attr-defined]
