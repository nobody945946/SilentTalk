from pathlib import Path

from silenttalk.copilot.llm import LocalReplyModel


def test_three_lane_parser_strips_thinking_and_keeps_fixed_intents() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    parsed = model._parse_suggestions(
        """<think>不要顯示這段</think>
AGREE|可以啊，這樣打比較穩。
DISAGREE|我倒覺得先守一下比較好。
HUMOR|再衝一次我們就可以直接改行送頭了。""",
        "A",
        "要不要直接衝？",
    )

    assert parsed.agree == "可以啊，這樣打比較穩。"
    assert parsed.disagree == "我倒覺得先守一下比較好。"
    assert parsed.humor == "再衝一次我們就可以直接改行送頭了。"


def test_humor_lane_can_abstain_instead_of_forcing_a_bad_joke() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    parsed = model._parse_suggestions(
        """AGREE|好，我知道了。
DISAGREE|我想法不太一樣。
HUMOR|SKIP""",
        "B",
        "這件事先這樣。",
    )

    assert parsed.agree
    assert parsed.disagree
    assert parsed.humor == ""


def test_reply_length_is_hard_capped() -> None:
    model = LocalReplyModel(Path("unused.gguf"), max_reply_chars=24)
    parsed = model._parse_suggestions(
        "AGREE|" + ("很" * 100),
        "A",
        "test",
    )

    assert len(parsed.agree) == 25
    assert parsed.agree.endswith("…")
