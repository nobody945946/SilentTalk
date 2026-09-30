from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from e4b_core.api import request_base, service_status, shutdown_service
from e4b_core.runtime import E4BCoreError

AUTOSTART_NAME = "E4B Edge AI.cmd"
LEGACY_AUTOSTART_NAME = "E4B Edge AI.lnk"


def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is unavailable")
    return (
        Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )


def autostart_enabled() -> bool:
    startup = _startup_dir()
    return (startup / AUTOSTART_NAME).exists() or (
        startup / LEGACY_AUTOSTART_NAME
    ).exists()


def set_autostart(enabled: bool) -> None:
    startup = _startup_dir()
    startup.mkdir(parents=True, exist_ok=True)
    command = startup / AUTOSTART_NAME
    legacy = startup / LEGACY_AUTOSTART_NAME
    if enabled:
        pythonw = PROJECT_DIR / ".venv" / "Scripts" / "pythonw.exe"
        cli = PROJECT_DIR / "e4b_core" / "cli.py"
        command.write_text(
            f'@echo off\nstart "" "{pythonw}" "{cli}" start\n',
            encoding="utf-8",
        )
        legacy.unlink(missing_ok=True)
    else:
        command.unlink(missing_ok=True)
        legacy.unlink(missing_ok=True)


def print_status() -> None:
    status = service_status()
    if status is None:
        print("E4B stopped (GPU and model memory released)")
        return
    mode = status.get("mode")
    if mode == "base":
        print(f"E4B core running: {status.get('url')}")
    elif mode == "character":
        print("E4B core is leased to SilentTalk (character LoRA)")
    else:
        print(f"E4B core status: {mode}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="e4b", description="Local E4B Core")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("start", help="start E4B Core without opening a browser")
    subparsers.add_parser("stop", help="stop E4B Core and release GPU memory")
    subparsers.add_parser("status", help="show the current E4B Core mode")
    auto = subparsers.add_parser("autostart", help="control Windows login startup")
    auto.add_argument("state", choices=("on", "off", "status"))
    args = parser.parse_args()

    try:
        if args.command is None:
            status = request_base(PROJECT_DIR)
            webbrowser.open(str(status["url"]))
            return 0
        if args.command == "start":
            request_base(PROJECT_DIR)
            print_status()
            return 0
        if args.command == "stop":
            shutdown_service()
            print_status()
            return 0
        if args.command == "status":
            print_status()
            return 0
        if args.command == "autostart":
            if args.state == "on":
                set_autostart(True)
            elif args.state == "off":
                set_autostart(False)
            print("E4B autostart: " + ("on" if autostart_enabled() else "off"))
            return 0
    except (E4BCoreError, OSError, RuntimeError) as exc:
        print(f"E4B error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
