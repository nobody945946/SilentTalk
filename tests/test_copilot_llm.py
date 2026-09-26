import json
from pathlib import Path

from silenttalk.copilot.llm import LocalReplyModel


def test_four_lane_parser_strips_thinking_and_keeps_fixed_intents() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    parsed = model._parse_suggestions(
        """<think>不要顯示這段</think>
AGREE|可以啊，這樣打比較穩。
ASK|你說的直接衝是走哪條路？
DISAGREE|我倒覺得先守一下比較好。
HUMOR|再衝一次我們就可以直接改行送頭了。""",
        "A",
        "要不要直接衝？",
    )

    assert parsed.agree == "可以啊，這樣打比較穩。"
    assert parsed.ask == "你說的直接衝是走哪條路？"
    assert parsed.disagree == "我倒覺得先守一下比較好。"
    assert parsed.humor == "再衝一次我們就可以直接改行送頭了。"


def test_parser_tolerates_small_model_decoration() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    parsed = model._parse_suggestions(
        """1. **AGREE**｜好，那我跟你一起。
- ASK: 你要幾點開始？
DISAGREE：「我覺得不太行」""",
        "A",
        "我們等等開",
    )

    assert parsed.agree == "好，那我跟你一起。"
    assert parsed.ask == "你要幾點開始？"
    assert parsed.disagree == "我覺得不太行"
    assert parsed.humor == ""


def test_parser_drops_echo_and_template_placeholders() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    parsed = model._parse_suggestions(
        """AGREE|要不要直接衝？
ASK|...
DISAGREE|先守一下吧""",
        "A",
        "要不要直接衝",
    )

    assert parsed.agree == ""
    assert parsed.ask == ""
    assert parsed.disagree == "先守一下吧"


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


def test_simplified_model_output_is_shown_in_traditional() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    parsed = model._parse_suggestions("AGREE|这个视频我也看过", "A", "昨天那部片")

    assert parsed.agree == "這個影片我也看過"


def test_stream_reports_each_completed_line() -> None:
    from silenttalk.copilot.llm import consume_stream

    pieces = ["AGREE|好", "啊\nASK|真的", "嗎？\nDISAG", "REE|不要\nHUMOR|笑死"]
    events = [b": keep-alive\n"] + [
        ("data: " + json.dumps({"choices": [{"delta": {"content": p}}]}) + "\n").encode()
        for p in pieces
    ] + [b"data: [DONE]\n"]
    seen: list[str] = []

    text = consume_stream(events, seen.append)

    assert text == "AGREE|好啊\nASK|真的嗎？\nDISAGREE|不要\nHUMOR|笑死"
    assert seen == ["AGREE|好啊", "AGREE|好啊\nASK|真的嗎？", "AGREE|好啊\nASK|真的嗎？\nDISAGREE|不要"]
