from silenttalk.copilot.context import ConversationStore


def test_prompt_keeps_recent_turns_and_older_owner_statements() -> None:
    store = ConversationStore(
        recent_turns=4,
        max_turns=20,
        char_budget=2000,
        older_self_turns=2,
    )
    store.append_external(1, "A", "很早以前的外部訊息")
    store.append_self(999, "我等等要先走")
    store.append_external(2, "B", "第一個最近訊息")
    store.append_external(3, "C", "第二個最近訊息")
    store.append_external(2, "B", "第三個最近訊息")
    store.append_external(3, "C", "第四個最近訊息")

    prompt = store.render_for_prompt()

    assert "我等等要先走" in prompt
    assert "第一個最近訊息" in prompt
    assert "第四個最近訊息" in prompt
    assert "很早以前的外部訊息" not in prompt


def test_session_history_is_bounded() -> None:
    store = ConversationStore(recent_turns=4, max_turns=6)
    for index in range(10):
        store.append_external(index, f"U{index}", f"訊息 {index}")

    snapshot = store.snapshot()

    assert len(snapshot) == 6
    assert snapshot[0].text == "訊息 4"
    assert snapshot[-1].text == "訊息 9"
