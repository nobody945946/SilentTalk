from __future__ import annotations

from silenttalk.copilot.context import ConversationStore


def _store(**kwargs: object) -> ConversationStore:
    return ConversationStore(recent_turns=4, max_turns=100, char_budget=4000, **kwargs)  # type: ignore[arg-type]


def test_compaction_replaces_old_turns_and_keeps_the_thread() -> None:
    store = _store()
    for n in range(10):
        store.append_external(2, "阿傑", f"第{n}句")

    older = store.pending_compaction(keep=4)
    assert [turn.text for turn in older] == [f"第{n}句" for n in range(6)]

    store.compact("大家在討論晚餐，還沒決定吃什麼", len(older))
    prompt = store.render_for_prompt()

    assert "這場對話稍早的重點：大家在討論晚餐，還沒決定吃什麼" in prompt
    assert "第0句" not in prompt and "第5句" not in prompt
    assert "第9句" in prompt
    assert len(store.snapshot()) == 4


def test_turns_that_arrive_while_summarizing_are_not_dropped() -> None:
    store = _store()
    for n in range(10):
        store.append_external(2, "阿傑", f"第{n}句")
    folded = len(store.pending_compaction(keep=4))

    store.append_external(3, "小雨", "剛剛講的")  # arrives mid-summary
    store.compact("稍早的重點", folded)

    assert "剛剛講的" in store.render_for_prompt()
    assert [turn.text for turn in store.snapshot()][-1] == "剛剛講的"


def test_compaction_never_eats_the_recent_window() -> None:
    store = _store()
    for n in range(5):
        store.append_external(2, "阿傑", f"第{n}句")

    store.compact("摘要", folded=99)

    assert len(store.snapshot()) == 4
    assert "第4句" in store.render_for_prompt()


def test_the_summary_survives_a_tight_character_budget() -> None:
    store = ConversationStore(recent_turns=4, char_budget=600, older_self_turns=4)
    for n in range(12):
        store.append_self(1, f"我說的第{n}句話這裡故意寫得長一點免得預算用不完")
        store.append_external(2, "阿傑", f"阿傑第{n}句也寫長一點用掉字元預算" * 2)
    store.compact("稍早在討論排位和晚餐", folded=len(store.pending_compaction(keep=4)))

    prompt = store.render_for_prompt()

    assert "稍早在討論排位和晚餐" in prompt
    assert len(prompt) <= 600 + 200
