import pytest

from silenttalk.text import TextValidationError, normalize_text


def test_normalizes_without_rewriting_meaning() -> None:
    assert (
        normalize_text("  等一下，  我馬上回來。\r\n\r\n\r\n好  ", 100)
        == "等一下， 我馬上回來。\n\n好"
    )


@pytest.mark.parametrize("value", ["", "   ", "\r\n"])
def test_rejects_empty_text(value: str) -> None:
    with pytest.raises(TextValidationError):
        normalize_text(value, 100)


def test_rejects_over_limit() -> None:
    with pytest.raises(TextValidationError, match="最多 3 字"):
        normalize_text("1234", 3)
