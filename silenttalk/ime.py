"""Turn the Windows IME off for one window while single-key controls are active.

With a Chinese IME (注音/倉頡) in Chinese mode, W/A/S/D start a composition
and never reach Tk as key presses. Story mode detaches the IME from the popup
and re-attaches the default context when leaving it.
"""

from __future__ import annotations

import ctypes
import logging
import sys

_LOG = logging.getLogger(__name__)

_IACE_DEFAULT = 0x0010


def set_ime_enabled(tk_window_id: int, enabled: bool) -> bool:
    """Returns False when the platform call is unavailable or fails."""
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        imm32 = ctypes.windll.imm32
        top = user32.GetAncestor(tk_window_id, 2) or tk_window_id  # GA_ROOT
        handles = [top, *_child_windows(user32, top)]
        flags = _IACE_DEFAULT if enabled else 0
        for hwnd in handles:
            imm32.ImmAssociateContextEx(hwnd, None, flags)
        return True
    except Exception:  # noqa: BLE001 - IME control is best effort; arrows still work.
        _LOG.debug("ime_toggle_failed", exc_info=True)
        return False


def _child_windows(user32: ctypes.WinDLL, parent: int) -> list[int]:
    found: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def collect(hwnd: int, _: int) -> bool:
        found.append(hwnd)
        return True

    user32.EnumChildWindows(parent, callback_type(collect), None)
    return found
