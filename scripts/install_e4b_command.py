from __future__ import annotations

import os
from pathlib import Path


def main() -> int:
    project_dir = Path(__file__).resolve().parents[1]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        raise SystemExit("LOCALAPPDATA is unavailable")
    links = Path(local_appdata) / "Microsoft" / "WinGet" / "Links"
    links.mkdir(parents=True, exist_ok=True)
    shim = links / "e4b.cmd"
    python = project_dir / ".venv" / "Scripts" / "python.exe"
    cli = project_dir / "e4b_core" / "cli.py"
    shim.write_text(
        f'@echo off\n"{python}" "{cli}" %*\n',
        encoding="utf-8",
    )
    print(shim)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
