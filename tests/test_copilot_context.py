from __future__ import annotations

from silenttalk.copilot.context import ConversationStore


def _store(**kwargs: object) -> ConversationStore:
    return ConversationStore(max_turns=100, **kwargs)  # type: ignore[arg-type]


def test_compaction_replaces_old_turns_and_keeps_the_thread() -> None:
    store = _store()
    for n in range(10):
        store.append_external(2, "阿傑", f"第{n}句")

    older = store.pending_compaction(keep=4)
    assert [turn.text for turn in older] == [f"第{n}句" for n in range(6)]

    store.compact("大家在討論晚餐，還沒決定吃什麼", len(older), keep=4)

    assert store.summary == "大家在討論晚餐，還沒決定吃什麼"
    assert [turn.text for turn in store.snapshot()] == [f"第{n}句" for n in range(6, 10)]
    assert len(store.snapshot()) == 4


def test_turns_that_arrive_while_summarizing_are_not_dropped() -> None:
    store = _store()
    for n in range(10):
        store.append_external(2, "阿傑", f"第{n}句")
    folded = len(store.pending_compaction(keep=4))

    store.append_external(3, "小雨", "剛剛講的")  # arrives mid-summary
    store.compact("稍早的重點", folded, keep=4)

    assert [turn.text for turn in store.snapshot()][-1] == "剛剛講的"


def test_compaction_never_eats_the_recent_window() -> None:
    store = _store()
    for n in range(5):
        store.append_external(2, "阿傑", f"第{n}句")

    store.compact("摘要", folded=99, keep=4)

    assert len(store.snapshot()) == 4
    assert store.snapshot()[-1].text == "第4句"


def test_summary_has_a_fixed_size_without_losing_recent_turns() -> None:
    store = ConversationStore(summary_chars=640)
    for n in range(12):
        store.append_external(2, "阿傑", f"第{n}句")
    store.compact("重" * 800, folded=len(store.pending_compaction(keep=4)), keep=4)

    assert store.summary == "重" * 640
    assert [turn.text for turn in store.snapshot()] == [f"第{n}句" for n in range(8, 12)]
