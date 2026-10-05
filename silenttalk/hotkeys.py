from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
from collections.abc import Callable

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
_KEYS = {f"F{number}": 0x6F + number for number in range(1, 13)}


class GlobalHotkeys:
    def __init__(self, bindings: dict[str, Callable[[], None]]) -> None:
        unknown = [key for key in bindings if key.upper() not in _KEYS]
        if unknown:
            raise ValueError(f"不支援的快捷鍵：{', '.join(unknown)}")
        self._bindings = {
            index + 1: (_KEYS[key.upper()], callback)
            for index, (key, callback) in enumerate(bindings.items())
        }
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._error: Exception | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="global-hotkeys", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout=3)
        if self._error:
            raise self._error
        if not self._ready.is_set():
            raise RuntimeError("全域快捷鍵註冊逾時。")

    def _run(self) -> None:
        from silenttalk.windows_desktop import attach_interactive_desktop

        attach_interactive_desktop()
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        registered: list[int] = []
        try:
            for hotkey_id, (virtual_key, _) in self._bindings.items():
                if not user32.RegisterHotKey(None, hotkey_id, 0, virtual_key):
                    raise RuntimeError(
                        f"無法註冊快捷鍵 ID {hotkey_id}；可能已被其他程式占用。"
                    )
                registered.append(hotkey_id)
            self._ready.set()
            message = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY:
                    callback = self._bindings[int(message.wParam)][1]
                    callback()
        except Exception as exc:  # noqa: BLE001 - transfer thread failures to the UI thread.
            self._error = exc
            self._ready.set()
        finally:
            for hotkey_id in registered:
                user32.UnregisterHotKey(None, hotkey_id)

    def stop(self) -> None:
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._thread = None
        self._thread_id = None
