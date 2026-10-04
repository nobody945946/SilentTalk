"""Which rules made a training-data file, so a file never mixes two.

Long data jobs are resumable: they append to their files across restarts, and
the code that writes the prompts and rules can change in between. A file whose
first half follows yesterday's rules and second half today's teaches both
(the user: 「小心巨大檔案前後不一，汙染到訓練」). So every data file carries a
sidecar `<file>.version` (JSON: producer, version, commit) written when the
file is started:

- appending under another version is refused (start a new data directory);
- a set is only trained on when all its files carry the same version
  (character_data.py filter);
- train_lora.py refuses a file without a sidecar.

The version is a fingerprint of the files that decide the content (the app's
prompts, the generator's rules, the persona cards), not of the data.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


class MixedData(SystemExit):
    """Raised instead of writing rows under different rules into one file."""


def fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes() if path.is_file() else b"<missing>")
    return digest.hexdigest()[:16]


def sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".version")


def read_stamp(path: Path) -> dict | None:
    side = sidecar(path)
    return json.loads(side.read_text(encoding="utf-8")) if side.is_file() else None


def _commit(cwd: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except OSError:
        return ""


def stamp(path: Path, producer: str, version: str) -> None:
    """For a file written whole (or started now)."""
    sidecar(path).write_text(json.dumps(
        {"producer": producer, "version": version, "commit": _commit(path.parent)},
        ensure_ascii=False), encoding="utf-8")


def claim(path: Path, producer: str, version: str) -> None:
    """Before appending: a new file is stamped; an existing one must carry
    the same version, or the append is refused."""
    if not path.exists() or path.stat().st_size == 0:
        stamp(path, producer, version)
        return
    found = read_stamp(path)
    if found is None or found.get("version") != version:
        raise MixedData(
            f"{path} was written under other rules ({(found or {}).get('version', 'no stamp')}, now "
            f"{version}); appending would mix them. Start a new data directory."
        )


def require_same(paths: list[Path], version: str) -> list[str]:
    """Problems that refuse a set: a file with no stamp or another version."""
    problems = []
    for path in paths:
        if not path.exists():
            continue
        found = read_stamp(path)
        if found is None:
            problems.append(f"{path.name}: no version stamp")
        elif found.get("version") != version:
            problems.append(f"{path.name}: rules {found.get('version')} != {version}")
    return problems
