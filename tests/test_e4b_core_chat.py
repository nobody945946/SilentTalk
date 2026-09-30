from __future__ import annotations

from pathlib import Path

from e4b_core.chat import NativeChat
from e4b_core.web import NATIVE_CHAT_HTML


class FakeChat(NativeChat):
    def _input_tokens(self, messages: list[dict[str, str]]) -> int:
        return sum(len(message["content"]) for message in messages)

    def _summarize(self, prior_summary: str, older: list[dict[str, str]]) -> str:
        return f"durable memory for {len(older)} messages"

    def _stream_completion(self, messages: list[dict[str, str]]):
        yield "answer"


def test_native_chat_compacts_semantically_and_emits_notice() -> None:
    chat = FakeChat(model_port=18089, compact_at_tokens=700, keep_recent_tokens=80)
    session = chat.session("session-123")
    session.messages = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": "x" * 100}
        for index in range(10)
    ]

    events = list(chat.stream_reply("session-123", "continue this conversation"))

    assert events[0][0] == "compacted"
    assert "已整理" in str(events[0][1]["message"])
    assert session.compaction_count == 1
    assert session.summary.startswith("durable memory")
    assert session.messages[-1] == {"role": "assistant", "content": "answer"}
    assert len(session.messages) < 12


def test_native_chat_does_not_claim_compaction_when_it_did_not_run() -> None:
    chat = FakeChat(model_port=18089, compact_at_tokens=10_000)

    events = list(chat.stream_reply("session-456", "hello"))

    assert [name for name, _ in events] == ["delta", "done"]


def test_native_chat_memory_is_ram_only_and_resettable() -> None:
    chat = FakeChat(model_port=18089)
    chat.session("session-789").messages.append({"role": "user", "content": "x"})

    chat.reset("session-789")

    assert chat.session("session-789").messages == []
    assert not hasattr(chat, "storage_path")


def test_native_web_ui_handles_compaction_notice() -> None:
    assert "event: 'compacted'" not in NATIVE_CHAT_HTML
    assert "type==='compacted'" in NATIVE_CHAT_HTML
    assert "96K context" in NATIVE_CHAT_HTML


def test_e4b_core_never_imports_silenttalk() -> None:
    root = Path(__file__).resolve().parents[1] / "e4b_core"
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

    assert "from silenttalk" not in sources
    assert "import silenttalk" not in sources
