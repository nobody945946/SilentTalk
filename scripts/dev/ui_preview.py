"""Screenshot the F8 popup in each story-mode state with fake data (no Discord).

Usage (from the repo root):
    Windows: python scripts/dev/ui_preview.py
    Linux:   xvfb-run -a python scripts/dev/ui_preview.py --font "Noto Sans CJK TC"
Needs Pillow (pip install pillow). PNGs land in .runtime/dev/ui_preview/;
open them and check the layout after any change to ui.py or story_ui.py.
The script also asserts the key flow (double-press sends, R regenerates) and
exits non-zero if it breaks.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

from silenttalk import story_ui

OUT_DIR = PROJECT_DIR / ".runtime" / "dev" / "ui_preview"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", help="override the UI font (Linux has no JhengHei)")
    args = parser.parse_args()
    if args.font:
        story_ui.FONT = args.font

    from PIL import ImageGrab

    from silenttalk.copilot.types import ConversationTurn, ReplySuggestions
    from silenttalk.phrases import QuickPhraseStore
    from silenttalk.preferences import PreferenceStore
    from silenttalk.ui import SilentTalkUI

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="ui-preview-"))
    sent: list[str] = []
    regenerated: list[bool] = []
    ui = SilentTalkUI(
        "F8",
        "F9",
        lambda text, _style, _rate: sent.append(text),
        lambda: None,
        lambda: None,
        QuickPhraseStore(temp / "phrases.json"),
        PreferenceStore(temp / "prefs.json"),
        regenerate_suggestions=lambda: regenerated.append(True),
    )

    def pump(seconds: float = 0.3) -> None:
        end = time.time() + seconds
        while time.time() < end:
            ui.root.update()
            time.sleep(0.02)

    def shot(name: str) -> None:
        pump(0.4)
        x, y = ui.popup.winfo_rootx(), ui.popup.winfo_rooty()
        box = (x, y, x + ui.popup.winfo_width(), y + ui.popup.winfo_height())
        ImageGrab.grab(bbox=box).save(OUT_DIR / f"{name}.png")
        print(f"saved {OUT_DIR / name}.png")

    def press(keysym: str) -> None:
        ui.story.focus_set()
        pump(0.05)
        ui.popup.event_generate(f"<KeyPress-{keysym}>", when="now")
        pump(0.1)

    ui.show()
    ui.notebook.select(ui.story)
    shot("1_empty")

    trigger = "可是他們B點只有一個人在守 直接衝就好了吧"
    for speaker_id, name, text in (
        (11, "阿傑", "欸我們等等要不要直接衝B點"),
        (12, "小雨", "上一把衝B被架死欸"),
        (0, "你", "我覺得可以先丟煙"),
        (11, "阿傑", trigger),
    ):
        ui.add_conversation_turn(
            ConversationTurn(speaker_id, name, text, is_self=speaker_id == 0)
        )
    ui.set_suggestions_thinking("阿傑", trigger)
    pump(1.0)
    shot("2_thinking")

    ui.set_suggestions(
        ReplySuggestions(
            "阿傑",
            trigger,
            agree="好啊，一個人守我們三個衝一定吃得下",
            ask="你確定只有一個嗎？剛剛是誰看到的？",
            disagree="上一把就是這樣被架，我覺得先丟煙再進比較穩",
        )
    )
    pump()
    shot("3_choices")
    press("d")
    shot("4_selected_d")
    press("d")
    ui.show()
    shot("5_after_send")
    ui.set_suggestions(
        ReplySuggestions("小雨", "x", error="本機回覆模型失敗：timed out")
    )
    shot("6_error")
    press("r")
    ui.notebook.select(ui._manual_tab)
    shot("7_manual_tab")
    ui.root.destroy()

    expected = "上一把就是這樣被架，我覺得先丟煙再進比較穩"
    problems = []
    if sent != [expected]:
        problems.append(f"double-press D should send once, got {sent}")
    if regenerated != [True]:
        problems.append("R should call regenerate once")
    for problem in problems:
        print("FAIL:", problem)
    print("UI flow OK" if not problems else "UI flow BROKEN")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
