"""Transcripts go only to the user's records drive (AGENTS.md rule 1)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from silenttalk.config import CopilotConfig
from silenttalk.copilot.runtime import CopilotRuntime
from silenttalk.copilot.types import ConversationTurn
from silenttalk.records import MARKER, NOTICE, TranscriptRecorder, parse_ids


def _turn(speaker_id: int, name: str, text: str, **extra) -> ConversationTurn:
    return ConversationTurn(speaker_id, name, text, created_at=1_790_000_000.0, **extra)


def _lines(folder: Path) -> list[dict]:
    return [json.loads(line) for path in sorted((folder / "silenttalk").glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()]


def test_nothing_is_written_without_the_marker_or_when_off(tmp_path: Path) -> None:
    recorder = TranscriptRecorder(enabled=True, folder=str(tmp_path))
    assert not recorder.ready()
    assert not recorder.write(_turn(1, "阿遠", "哈囉"))
    assert not (tmp_path / "silenttalk").exists()
    (tmp_path / MARKER).write_text("")
    recorder.configure(enabled=False, folder=str(tmp_path), exclude=frozenset())
    assert not recorder.write(_turn(1, "阿遠", "哈囉"))
    assert not (tmp_path / "silenttalk").exists()


def test_a_missing_drive_never_falls_back_elsewhere(tmp_path: Path) -> None:
    gone = tmp_path / "E-drive-unplugged"
    recorder = TranscriptRecorder(enabled=True, folder=str(gone))
    assert not recorder.write(_turn(1, "阿遠", "哈囉"))
    assert list(tmp_path.iterdir()) == []


def test_lines_are_kept_except_for_people_who_opted_out(tmp_path: Path) -> None:
    (tmp_path / MARKER).write_text("")
    recorder = TranscriptRecorder(enabled=True, folder=str(tmp_path), exclude=parse_ids("22, 33，44 x"))
    assert parse_ids("22, 33，44 x") == {22, 33, 44}
    assert recorder.write(_turn(1, "阿遠", "機魂 在嗎", via="text"))
    assert not recorder.write(_turn(22, "小綠", "不要記我"))
    assert recorder.write(_turn(1, "阿遠", "遵命", is_self=True), character="馬基納")
    lines = _lines(tmp_path)
    assert [(l["speaker"], l["text"], l["via"], l["self"]) for l in lines] == [
        ("阿遠", "機魂 在嗎", "text", False), ("馬基納", "遵命", "voice", True)]
    assert all(set(l) == {"time", "speaker_id", "speaker", "self", "via", "text"} for l in lines)


@pytest.mark.asyncio
async def test_the_runtime_records_every_turn_and_settings_apply_live(tmp_path: Path) -> None:
    (tmp_path / MARKER).write_text("")
    runtime = CopilotRuntime(
        tmp_path, replace(CopilotConfig(), record_transcripts=False), 1,
        lambda value: None, lambda value: None,
    )
    runtime._character_mode = True
    runtime._loop = asyncio.get_running_loop()
    runtime._wake = asyncio.Event()
    runtime._handle_turn(2, "小綠", "還沒開記錄")
    assert not runtime.recording()
    runtime.apply_settings({"record_transcripts": True, "record_folder": str(tmp_path),
                            "record_exclude": "3"})
    assert runtime.recording()
    runtime._handle_turn(2, "小綠", "現在開了")
    runtime._handle_turn(3, "阿鈞", "我不想被記")
    assert [l["text"] for l in _lines(tmp_path)] == ["現在開了"]


@pytest.mark.asyncio
async def test_joining_voice_tells_the_channel_only_while_recording() -> None:
    from silenttalk.controller import AppController

    sent = []
    controller = object.__new__(AppController)

    async def send_text(text):
        sent.append(text)
        return True

    controller._discord = SimpleNamespace(send_text=send_text)
    controller._copilot = SimpleNamespace(recording=lambda: False)
    await controller._on_voice_joined()
    controller._copilot = SimpleNamespace(recording=lambda: True)
    await controller._on_voice_joined()
    assert sent == [NOTICE]
