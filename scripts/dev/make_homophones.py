"""Write silenttalk/copilot/data/homophones.txt: every Han character by its
toneless pinyin, one syllable per line ("ji<TAB>機雞基幾…").

The character is called by voice ("機魂"), and speech recognition writes
whatever characters sound alike (雞魂, 基魂, 幾魂). The app reads only the
lines for the syllables in its names, so matching costs a few kilobytes
instead of a 50 MB pinyin dictionary. pypinyin is needed here only.

    .venv/bin/python scripts/dev/make_homophones.py
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from pathlib import Path

import pypinyin
from pypinyin.pinyin_dict import pinyin_dict

OUT = Path(__file__).resolve().parents[2] / "silenttalk/copilot/data/homophones.txt"


def toneless(reading: str) -> str:
    plain = unicodedata.normalize("NFD", reading)
    return "".join(ch for ch in plain if not unicodedata.combining(ch)).replace("ü", "v")


def main() -> None:
    by_syllable: dict[str, set[str]] = defaultdict(set)
    for code, readings in pinyin_dict.items():
        char = chr(code)
        if not ("㐀" <= char <= "鿿"):
            continue
        for reading in readings.split(","):
            by_syllable[toneless(reading.strip())].add(char)
    lines = [f"# toneless pinyin -> characters; scripts/dev/make_homophones.py, pypinyin {pypinyin.__version__}"]
    lines += [f"{syllable}\t{''.join(sorted(chars))}" for syllable, chars in sorted(by_syllable.items())]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(by_syllable)} syllables -> {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
