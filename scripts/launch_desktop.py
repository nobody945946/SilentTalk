"""Launch SilentTalk on the active user's interactive desktop (WinSta0\\Default)."""

import ctypes
import ctypes.wintypes
import os
import sys
import time
from pathlib import Path

class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ('cb', ctypes.wintypes.DWORD),
        ('lpReserved', ctypes.wintypes.LPWSTR),
        ('lpDesktop', ctypes.wintypes.LPWSTR),
        ('lpTitle', ctypes.wintypes.LPWSTR),
        ('dwX', ctypes.wintypes.DWORD),
        ('dwY', ctypes.wintypes.DWORD),
        ('dwXSize', ctypes.wintypes.DWORD),
        ('dwYSize', ctypes.wintypes.DWORD),
        ('dwXCountChars', ctypes.wintypes.DWORD),
        ('dwYCountChars', ctypes.wintypes.DWORD),
        ('dwFillAttribute', ctypes.wintypes.DWORD),
        ('dwFlags', ctypes.wintypes.DWORD),
        ('wShowWindow', ctypes.wintypes.WORD),
        ('cbReserved2', ctypes.wintypes.WORD),
        ('lpReserved2', ctypes.c_char_p),
        ('hStdInput', ctypes.wintypes.HANDLE),
        ('hStdOutput', ctypes.wintypes.HANDLE),
        ('hStdError', ctypes.wintypes.HANDLE),
    ]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('hProcess', ctypes.wintypes.HANDLE),
        ('hThread', ctypes.wintypes.HANDLE),
        ('dwProcessId', ctypes.wintypes.DWORD),
        ('dwThreadId', ctypes.wintypes.DWORD),
    ]

def launch_silenttalk() -> int:
    root = Path(__file__).resolve().parents[1]
    # Use the real pythonw executable
    base_pythonw = Path(r"C:\Users\A8fm0\AppData\Local\Programs\Python\Python312\pythonw.exe")
    if not base_pythonw.is_file():
        base_pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    
    app_py = root / "app.py"

    si = STARTUPINFOW()
    si.cb = ctypes.sizeof(STARTUPINFOW)
    si.lpDesktop = r"WinSta0\Default"
    pi = PROCESS_INFORMATION()

    k32 = ctypes.windll.kernel32
    cmd = f'"{base_pythonw}" "{app_py}" --silenttalk-desktop'
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    # Pass environment with PYTHONPATH pointing to venv site-packages
    env = os.environ.copy()
    venv_site = root / ".venv" / "Lib" / "site-packages"
    env["PYTHONPATH"] = str(venv_site)
    env["VIRTUAL_ENV"] = str(root / ".venv")

    # Format environment block for CreateProcessW
    env_str = "".join(f"{k}={v}\0" for k, v in env.items()) + "\0"

    ok = k32.CreateProcessW(
        None, cmd, None, None, False, flags | 0x00000400, # CREATE_UNICODE_ENVIRONMENT
        env_str, str(root), ctypes.byref(si), ctypes.byref(pi)
    )
    if not ok:
        err = ctypes.GetLastError()
        raise RuntimeError(f"CreateProcess failed: {err}")

    pid = pi.dwProcessId
    k32.CloseHandle(pi.hThread)
    k32.CloseHandle(pi.hProcess)
    return pid

if __name__ == "__main__":
    pid = launch_silenttalk()
    print(f"SilentTalk desktop launched on WinSta0\\Default. PID: {pid}")
