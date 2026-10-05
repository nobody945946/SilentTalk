"""Ensure thread/process is attached to the interactive Windows desktop (WinSta0\\Default).

When running under a service, background scheduler, or isolated sandbox, Windows
threads may start on a hidden desktop (e.g. Service-0x0-3e7$\\Default or exebox-*).
To allow GUI windows and RegisterHotKey to display on and receive input from the
user's physical monitor, threads must explicitly attach to WinSta0\\Default.
"""

from __future__ import annotations

import ctypes
import logging
import sys

_LOG = logging.getLogger(__name__)

_WINSTA_ALL = 0x037F
_DESKTOP_ALL = 0x01FF


def get_current_desktop_name() -> str:
    """Return the name of the desktop assigned to the calling thread."""
    if sys.platform != "win32":
        return ""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        h_desk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
        if not h_desk:
            return ""
        buf = ctypes.create_unicode_buffer(512)
        needed = ctypes.c_uint()
        if user32.GetUserObjectInformationW(h_desk, 2, buf, 512, ctypes.byref(needed)):
            return buf.value
    except Exception:
        pass
    return ""


def attach_interactive_desktop() -> bool:
    """Attach the calling thread to the interactive window station and desktop.

    Returns True if successfully attached or already on Windows interactive desktop.
    Returns False on non-Windows platforms or if the API call fails.
    """
    if sys.platform != "win32":
        return False
    try:
        current = get_current_desktop_name()
        if current.lower() == "default":
            return True

        user32 = ctypes.windll.user32

        # Switch process window station to WinSta0 if possible
        h_winsta = user32.OpenWindowStationW("WinSta0", False, _WINSTA_ALL)
        if h_winsta:
            user32.SetProcessWindowStation(h_winsta)
            user32.CloseWindowStation(h_winsta)

        # Open the interactive desktop
        h_desk = user32.OpenDesktopW("Default", 0, False, _DESKTOP_ALL)
        if not h_desk:
            h_desk = user32.OpenInputDesktop(0, False, _DESKTOP_ALL)

        if h_desk:
            ok = user32.SetThreadDesktop(h_desk)
            user32.CloseDesktop(h_desk)
            return bool(ok) or (get_current_desktop_name().lower() == "default")
        return False
    except Exception:  # noqa: BLE001 - Desktop attachment is best-effort.
        _LOG.debug("attach_interactive_desktop_failed", exc_info=True)
        return False
