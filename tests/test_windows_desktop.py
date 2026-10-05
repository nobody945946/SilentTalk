from __future__ import annotations

import sys
from unittest.mock import patch

from silenttalk.windows_desktop import attach_interactive_desktop


def test_attach_interactive_desktop_returns_bool() -> None:
    result = attach_interactive_desktop()
    assert isinstance(result, bool)
    if sys.platform == "win32":
        assert result is True


def test_attach_interactive_desktop_skips_on_non_windows() -> None:
    with patch("sys.platform", "linux"):
        assert attach_interactive_desktop() is False


def test_attach_interactive_desktop_handles_exceptions() -> None:
    with (
        patch("silenttalk.windows_desktop.get_current_desktop_name", return_value="other"),
        patch("ctypes.windll.user32.OpenDesktopW", side_effect=OSError("Boom")),
        patch("ctypes.windll.user32.OpenInputDesktop", side_effect=OSError("Boom")),
    ):
        assert attach_interactive_desktop() is False
