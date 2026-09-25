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


def to_taiwan_traditional(text: str) -> str:
    converter = _converter()
    if converter is None or not text:
        return text
    return str(converter.convert(text))  # type: ignore[attr-defined]
