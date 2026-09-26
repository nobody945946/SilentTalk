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


def test_ask_lane_gets_a_question_mark_for_tts() -> None:
    model = LocalReplyModel(Path("unused.gguf"))
    parsed = model._parse_suggestions(
        "AGREE|好啊\nASK|你買錯的是哪一款\nDISAGREE|不要吧！\nHUMOR|笑死", "Ken", "退款"
    )

    assert parsed.ask == "你買錯的是哪一款？"
    assert parsed.disagree == "不要吧！"
    assert parsed.humor == "笑死"


def test_character_line_parsing() -> None:
    from silenttalk.copilot.persona import PRESET_PERSONAS

    model = LocalReplyModel(Path("unused.gguf"))
    model.set_persona(PRESET_PERSONAS[0])

    assert model._parse_character_line("凱哥：穩啦，下波我先進\n多的", "衝B") == "穩啦，下波我先進"
    assert model._parse_character_line("SAY|好啊走", "衝B") == "好啊走"
    assert model._parse_character_line("說真的：我覺得先丟煙", "衝B") == "說真的：我覺得先丟煙"
    assert model._parse_character_line("SKIP", "衝B") == ""
    assert model._parse_character_line("衝B", "衝B") == ""


def test_character_prompt_admits_being_an_ai_character() -> None:
    from silenttalk.copilot.persona import PRESET_PERSONAS

    model = LocalReplyModel(Path("unused.gguf"))
    system = model._build_character_system_prompt(PRESET_PERSONAS[0])

    assert "誠實承認你是 AI 角色" in system
    assert "名字：凱哥" in system
    assert "不要說自己是 AI" not in system


def test_character_is_told_not_to_repeat_a_recent_catchphrase() -> None:
    import asyncio

    from silenttalk.copilot.persona import PRESET_PERSONAS

    model = LocalReplyModel(Path("unused.gguf"))
    model.set_persona(PRESET_PERSONAS[2])  # 黑焰
    prompts: list[str] = []

    def fake(system: str, prompt: str, on_lines=None, max_tokens: int = 240) -> str:
        prompts.append(prompt)
        return "哼，吾之右手尚未解放"

    model._request_completion = fake  # type: ignore[method-assign]
    kwargs = {"context": "最近對話：\nKen：打團嗎", "trigger_speaker": "Ken", "trigger_text": "打團嗎"}
    asyncio.run(model.character_reply(**kwargs))
    asyncio.run(model.character_reply(**kwargs))

    assert "你最近已經說過" not in prompts[0]
    assert "吾之右手" in prompts[1].split("你最近已經說過")[1]
    assert "口頭禪偶爾用" not in prompts[0]
