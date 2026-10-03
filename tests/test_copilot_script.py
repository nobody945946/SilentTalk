from silenttalk.copilot.script import to_taiwan_traditional


def test_stt_output_is_converted_to_taiwan_traditional_wording() -> None:
    assert to_taiwan_traditional("他们B点只有一个人 网络 视频") == "他們B點只有一個人 網路 影片"


def test_traditional_text_is_left_as_written() -> None:
    from silenttalk.copilot.script import to_taiwan_traditional

    # s2twp's phrase table would turn 通過 (passed) into 透過 (through).
    assert to_taiwan_traditional("三個測試全部通過") == "三個測試全部通過"
    assert to_taiwan_traditional("我们去吃饭吧") == "我們去吃飯吧"
