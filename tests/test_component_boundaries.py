from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def test_leaf_components_do_not_import_their_composers() -> None:
    composers = {
        "silenttalk.ui",
        "silenttalk.persona_ui",
        "silenttalk.discord_voice",
        "silenttalk.copilot.runtime",
        "silenttalk.copilot.llm",
    }
    components = (
        "manual_ui",
        "voice_controls_ui",
        "status_ui",
        "navigation_ui",
        "discord_invite_ui",
        "model_info_ui",
        "chat_workspace_ui",
        "persona_fields_ui",
        "persona_voice_ui",
        "persona_relations_ui",
        "persona_preview_ui",
        "discord_channels",
        "discord_messages",
        "discord_playback",
        "discord_approval",
        "voice_stats",
        "copilot/task_runner",
        "copilot/character_life",
        "copilot/sessions",
        "copilot/replies",
        "copilot/reply_prompts",
        "copilot/reply_transport",
        "copilot/reply_parsing",
        "copilot/character_generation",
    )
    for component in components:
        path = PROJECT / "silenttalk" / f"{component}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in composers, (component, node.module)
            elif isinstance(node, ast.Import):
                assert not {alias.name for alias in node.names} & composers


def test_speech_and_ui_import_without_any_ai_implementation() -> None:
    code = """
import sys
class NoAI:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'silenttalk.copilot' or fullname.startswith('silenttalk.copilot.'):
            raise ImportError('synthetic unavailable AI package')
sys.meta_path.insert(0, NoAI())
from silenttalk.config import config_defaults
from silenttalk.controller import AppController
from silenttalk.ui import SilentTalkUI
from silenttalk.speech_queue import SpeechQueue
from silenttalk.discord_playback import DiscordAudioPlayer
assert not any(name.startswith('silenttalk.copilot') for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
