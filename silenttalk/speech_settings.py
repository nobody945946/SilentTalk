from __future__ import annotations

import re

MIN_RATE_MULTIPLIER = 0.60
MAX_RATE_MULTIPLIER = 1.40
DEFAULT_RATE_MULTIPLIER = 1.00

_RATE_PATTERN = re.compile(r"^([+-]?\d+(?:\.\d+)?)%$")


def validate_rate_multiplier(value: float) -> float:
    rate = float(value)
    if not MIN_RATE_MULTIPLIER <= rate <= MAX_RATE_MULTIPLIER:
        raise ValueError(
            f"語速倍率必須介於 {MIN_RATE_MULTIPLIER:.0%}～{MAX_RATE_MULTIPLIER:.0%}。"
        )
    return rate


def combine_edge_rate(base_rate: str, multiplier: float) -> str:
    """Multiply an EdgeTTS rate string (e.g. -12%) by a UI speed multiplier."""
    rate_multiplier = validate_rate_multiplier(multiplier)
    match = _RATE_PATTERN.fullmatch(base_rate.strip())
    if match is None:
        raise ValueError(f"無法解析 TTS rate：{base_rate}")

    base_percent = float(match.group(1))
    base_multiplier = 1.0 + base_percent / 100.0
    effective_percent = (base_multiplier * rate_multiplier - 1.0) * 100.0
    rounded = int(round(effective_percent))
    sign = "+" if rounded >= 0 else ""
    return f"{sign}{rounded}%"
