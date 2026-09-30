@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo SilentTalk 尚未完成安裝，請先執行「啟動 SilentTalk.cmd」。
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "scripts\install_e4b_command.py" >nul
if errorlevel 1 (
    echo 無法安裝全域 e4b 指令。
    pause
    exit /b 1
)

call "%LOCALAPPDATA%\Microsoft\WinGet\Links\e4b.cmd"
exit /b 0
