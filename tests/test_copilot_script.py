from silenttalk.copilot.script import to_taiwan_traditional


def test_stt_output_is_converted_to_taiwan_traditional_wording() -> None:
    assert to_taiwan_traditional("他们B点只有一个人 网络 视频") == "他們B點只有一個人 網路 影片"
