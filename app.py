from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from silenttalk.config import ConfigError, load_settings
from silenttalk.controller import AppController
from silenttalk.copilot.smoke import run_copilot_smoke
from silenttalk.copilot.types import ConversationTurn, ReplySuggestions
from silenttalk.logging_setup import configure_logging
from silenttalk.phrases import QuickPhraseStore
from silenttalk.preferences import PreferenceStore
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
    parser.add_argument(
        "--copilot-smoke",
        action="store_true",
        help="Check local STT + LLM on this machine (no Discord needed)",
    )
    parser.add_argument(
        "--silenttalk-desktop",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    configure_logging(project_dir)
    try:
        settings = load_settings(project_dir)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"SilentTalk 設定錯誤：{exc}", file=sys.stderr)
        return 2

    if args.copilot_smoke:
        try:
            passed = asyncio.run(run_copilot_smoke(settings, project_dir))
        except Exception as exc:  # noqa: BLE001 - CLI boundary reports smoke failures.
            print(f"Copilot smoke 失敗：{exc}", file=sys.stderr)
            return 4
        return 0 if passed else 5

    if args.voice_smoke or args.tts_smoke:
        issues = settings.validate_runtime()
        if issues:
            print("SilentTalk 環境錯誤：" + "；".join(issues), file=sys.stderr)
            return 3
        try:
            text = "等一下，我馬上回來。" if args.tts_smoke else None
            asyncio.run(run_voice_smoke(settings, text))
        except Exception as exc:  # noqa: BLE001 - CLI boundary reports smoke failures.
            print(f"Gate 1 失敗：{exc}", file=sys.stderr)
            return 4
        return 0

    ui: SilentTalkUI | None = None

    def status(state: AppState, message: str) -> None:
        if ui is not None:
            ui.set_status(state, message)

    def suggestions(payload: ReplySuggestions) -> None:
        if ui is not None:
            ui.set_suggestions(payload)

    def conversation_turn(turn: ConversationTurn) -> None:
        if ui is not None:
            ui.add_conversation_turn(turn)

    def thinking(speaker: str, text: str) -> None:
        if ui is not None:
            ui.set_suggestions_thinking(speaker, text)

    controller = AppController(
        settings,
        status,
        project_dir,
        suggestions,
        on_turn=conversation_turn,
        on_thinking=thinking,
    )
    quick_phrases = QuickPhraseStore(project_dir / "quick_phrases.json")
    preferences = PreferenceStore(project_dir / "ui_preferences.json")
    ui = SilentTalkUI(
        settings.app.speak_hotkey,
        settings.app.stop_hotkey,
        controller.submit,
        controller.stop_playback,
        controller.shutdown,
        quick_phrases,
        preferences,
        auto_popup_suggestions=settings.copilot.auto_popup,
        regenerate_suggestions=(
            controller.regenerate_suggestions if settings.copilot.enabled else None
        ),
    )

    runtime_issues = settings.validate_runtime()
    if runtime_issues:
        ui.set_status(AppState.ERROR, "；".join(runtime_issues))

    controller.start()
    ui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
