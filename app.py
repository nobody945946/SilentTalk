from __future__ import annotations

import argparse
import asyncio
import atexit
import os
import sys
from pathlib import Path

from silenttalk.config import ConfigError, load_settings
from silenttalk.controller import AppController
from silenttalk.logging_setup import configure_logging
from silenttalk.phrases import QuickPhraseStore
from silenttalk.smoke import run_voice_smoke
from silenttalk.state import AppState
from silenttalk.ui import SilentTalkUI


def main() -> int:
    parser = argparse.ArgumentParser(description="SilentTalk Discord voice relay")
    parser.add_argument(
        "--voice-smoke",
        action="store_true",
        help="Gate 1: join the owner's current voice channel and play a fixed test tone",
    )
    parser.add_argument(
        "--tts-smoke",
        action="store_true",
        help="Gate 2: synthesize a fixed zh-TW sentence and play it in Discord voice",
    )
    args = parser.parse_args()
    project_dir = Path(__file__).resolve().parent
    configure_logging(project_dir)

    pid_dir = Path(os.getenv("LOCALAPPDATA", project_dir)) / "SilentTalk"
    pid_file = pid_dir / "silenttalk.pid"
    pid_dir.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="ascii")

    def _remove_pid_file() -> None:
        try:
            if pid_file.exists() and pid_file.read_text(encoding="ascii").strip() == str(os.getpid()):
                pid_file.unlink()
        except OSError:
            pass

    atexit.register(_remove_pid_file)
    try:
        settings = load_settings(project_dir)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"SilentTalk 設定錯誤：{exc}", file=sys.stderr)
        return 2

    if args.voice_smoke or args.tts_smoke:
        issues = settings.validate_runtime()
        if issues:
            print("SilentTalk 環境錯誤：" + "；".join(issues), file=sys.stderr)
            return 3
        try:
            text = "等一下，我馬上回來。" if args.tts_smoke else None
            asyncio.run(run_voice_smoke(settings, text))
        except Exception as exc:  # noqa: BLE001 - CLI boundary must report every Gate 1 failure.
            print(f"Gate 1 失敗：{exc}", file=sys.stderr)
            return 4
        return 0

    ui: SilentTalkUI | None = None

    def status(state: AppState, message: str) -> None:
        if ui is not None:
            ui.set_status(state, message)

    controller = AppController(settings, status)
    quick_phrases = QuickPhraseStore(project_dir / "quick_phrases.json")
    ui = SilentTalkUI(
        settings.app.speak_hotkey,
        settings.app.stop_hotkey,
        controller.submit,
        controller.stop_playback,
        controller.shutdown,
        quick_phrases,
    )
    runtime_issues = settings.validate_runtime()
    if runtime_issues:
        ui.set_status(AppState.ERROR, "；".join(runtime_issues))
    controller.start()
    ui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
