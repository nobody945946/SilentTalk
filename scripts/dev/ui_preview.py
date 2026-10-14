"""Screenshot the F8 popup in each page/state with fake data (no Discord).

Usage (from the repo root):
    Windows: python scripts/dev/ui_preview.py [--scale 1.5]
    Linux:   xvfb-run -a -s "-screen 0 2400x1600x24" \
                 .runtime/tools/ui-preview-env/bin/python scripts/dev/ui_preview.py \
                 --font "Noto Sans CJK TC" [--scale 1.5]

On Linux use the ui-preview-env interpreter (conda-forge Tk built with Xft):
the project venv's Tk has no Xft, draws Chinese with X bitmap fonts and turns
bold text into boxes, so its screenshots say nothing about the real look.
--scale emulates Windows display scaling (fonts grow, fixed pixels do not),
which is where clipped text shows up.

Needs Pillow. PNGs land in .runtime/dev/ui_preview/; open them and check the
layout after any UI change. The script also asserts the key flow (Enter
says what was typed, the mood menu changes mood, the character view starts
and pauses) and exits non-zero if it breaks.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

OUT_DIR = PROJECT_DIR / ".runtime" / "dev" / "ui_preview"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", help="override the UI font (Linux has no JhengHei)")
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="emulate Windows display scaling (1.25, 1.5): fonts grow, pixels do not",
    )
    args = parser.parse_args()
    if args.scale != 1.0:
        import tkinter as tk

        original_init = tk.Tk.__init__

        def scaled_init(self, *a, **k):  # type: ignore[no-untyped-def]
            original_init(self, *a, **k)
            # Tk's points-to-pixels factor at 96 DPI is 96/72; Windows at
            # 150% reports 144 DPI.
            self.tk.call("tk", "scaling", 96 * args.scale / 72)

        tk.Tk.__init__ = scaled_init  # type: ignore[method-assign]

    from PIL import ImageGrab

    from silenttalk.config import config_defaults
    from silenttalk.conversation import ConversationTurn
    from silenttalk.persona import (
        EXAMPLE_PERSONAS,
        MACHINE_SPIRIT,
        PersonaState,
        PersonaStore,
    )
    from silenttalk.phrases import QuickPhraseStore
    from silenttalk.preferences import PreferenceStore
    from silenttalk.settings_schema import all_settings
    from silenttalk.settings_store import SettingsStore
    from silenttalk.text import normalize_text
    from silenttalk.ui import SilentTalkUI

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="ui-preview-"))
    sent: list[str] = []
    applied: list[str] = []
    character: list[tuple[bool, str, float]] = []
    previews: list[tuple[str, str]] = []
    rerolled: list[bool] = []
    applied_settings: list[list[str]] = []
    personas = PersonaStore(temp / "personas.json")
    personas.save(PersonaState(list(EXAMPLE_PERSONAS), EXAMPLE_PERSONAS[0].id))
    ui = SilentTalkUI(
        "F8",
        "F9",
        # What the controller speaks: Tk's own Return binding has already put a
        # newline in the box when the window's Enter sends it.
        lambda text, _style, _rate: sent.append(normalize_text(text, 300)),
        lambda: None,
        lambda: None,
        QuickPhraseStore(temp / "phrases.json"),
        PreferenceStore(temp / "prefs.json"),
        personas=personas,
        apply_persona=lambda persona: applied.append(persona.mood),
        set_character_mode=lambda on, style, rate: character.append((on, style, rate)),
        preview_voice=lambda text, persona, _rate: previews.append(
            (text, persona.voice)
        ),
        reroll_agenda=lambda: rerolled.append(True),
        settings_store=SettingsStore(temp / "settings.json"),
        config_defaults=config_defaults(PROJECT_DIR),
        apply_settings=lambda tables: applied_settings.append(sorted(tables)),
        copilot_info=[("回覆模型", "gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf")],
        font_override=args.font,
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
        ui.popup.focus_force()
        ui.chat.manual.input.focus_set()
        pump(0.05)
        ui.popup.event_generate(f"<KeyPress-{keysym}>", state=0, when="now")
        pump(0.1)

    ui.show()
    ui.show_page("manual")
    shot("1_empty")

    for speaker_id, name, text in (
        (11, "阿傑", "欸我們等等要不要直接衝B點"),
        (12, "小雨", "上一把衝B被架死欸"),
        (0, "你", "我覺得可以先丟煙"),
        (11, "阿傑", "可是他們B點只有一個人在守 直接衝就好了吧"),
    ):
        ui.add_conversation_turn(
            ConversationTurn(speaker_id, name, text, is_self=speaker_id == 0)
        )
    pump()
    shot("2_transcript")
    expected = "上一把就是這樣被架，我覺得先丟煙再進比較穩"
    ui.chat.manual.input.insert("1.0", expected)
    shot("3_typing")
    press("Return")
    ui.show()
    shot("4_after_send")
    ui.chat.header._pick("開心")  # what the mood menu does
    ui.show_page("persona")
    shot("8_persona")
    for section in ui.persona_panel.fields._sections:
        section.set_open(True)
    pump()
    ui.persona_panel._scroll._canvas.yview_moveto(0.55)
    shot("9_persona_scrolled")
    ui.persona_panel._scroll._canvas.yview_moveto(0.8)
    shot("10_persona_voice")
    ui.persona_panel._preview_voice()
    ui.persona_panel._scroll._canvas.yview_moveto(1.0)
    shot("10b_persona_preview")
    ui.persona_panel._open(MACHINE_SPIRIT.id)
    ui.persona_panel._scroll._canvas.yview_moveto(0.8)
    shot("10c_machine_spirit_voice")
    ui.show_page("voice")
    shot("11_voice")
    ui.show_page("settings")
    shot("13_settings_chat")
    ui.settings_panel.show("model")
    shot("14_settings_model")
    ui.settings_panel.show("voice")
    shot("14b_settings_voice")
    record_fixture = temp / "records"
    record_fixture.mkdir()
    ui.settings_panel.set_value("copilot", "record_folder", str(record_fixture))
    ui.settings_panel.set_value("copilot", "record_transcripts", True)
    ui.settings_panel._prepare_records()
    ui.settings_panel.show("records")
    shot("14c_settings_records")
    ui.settings_panel._changed(
        next(s for s in all_settings() if s.key == "character_engagement"), "active"
    )
    ui.settings_panel.show("chat")
    shot("15_settings_changed")
    ui.show_page("character")
    concerns = [
        "昨天排位連輸五場，還在不爽，今天一定要把牌位打回來才甘願",
        "想揪大家週六打通宵，不知道小雨跟阿傑有沒有空",
        "新買的滑鼠還沒拆，下班要來試試看手感到底有沒有比較好",
        "最近公司專案一直改需求，下班只想打遊戲不想碰電腦以外的事",
    ]
    ui.set_agenda(concerns)
    pump()
    shown_agenda = ui.chat.character._mind.cget("text")
    shot("12a_character_paused")
    ui.chat.character._toggle()  # 開始
    ui.add_conversation_turn(ConversationTurn(12, "小雨", "凱哥你晚餐要吃什麼"))
    ui.add_conversation_turn(
        ConversationTurn(0, "凱哥", "欸我都可以啦，拉麵？", is_self=True)
    )
    shot("12_character")
    # Looking at another page is not leaving the character view.
    ui.show_page("persona")
    ui.show_page("chat")
    kept_running = ui._character_on and ui._mode == "character"
    # A very long line wraps; it must not widen the window.
    width_before = ui.popup.winfo_width()
    ui.add_conversation_turn(ConversationTurn(11, "阿傑", "欸" + "這句話真的很長" * 20))
    pump()
    widened = ui.popup.winfo_width() - width_before
    ui.show_page("manual")  # speaking for you again pauses the character
    ui.root.destroy()

    problems = []
    if shown_agenda != "\n".join(f"・{item}" for item in concerns):
        problems.append(
            f"today's concerns should show in the character view, got {shown_agenda!r}"
        )
    if sent != [expected]:
        problems.append(f"Enter should say the typed line once, got {sent}")
    if [on for on, _style, _rate in character] != [True, False]:
        problems.append(f"character toggle should switch on then off, got {character}")
    if previews != [("欸我的，下波我先進", "zh-TW-YunJheNeural")]:
        problems.append(
            f"voice preview should say 凱哥's first sample line in his voice, got {previews}"
        )
    saved = json.loads((temp / "settings.json").read_text(encoding="utf-8"))
    if saved != {
        "copilot": {
            "character_engagement": "active",
            "record_folder": str(record_fixture),
            "record_transcripts": True,
        }
    }:
        problems.append(f"settings page should save only what changed, got {saved}")
    if not applied_settings:
        problems.append("settings page should apply live changes")
    if not applied or applied[-1] != "開心":
        problems.append(f"the mood menu should switch mood to 開心, got {applied}")
    if personas.load().mood != "開心":
        problems.append("mood change should be saved to personas.json")
    if not kept_running:
        problems.append("visiting another page must not pause a running character")
    if widened > 0:
        problems.append(f"a long line widened the window by {widened}px")
    for problem in problems:
        print("FAIL:", problem)
    print("UI flow OK" if not problems else "UI flow BROKEN")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
