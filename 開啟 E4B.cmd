@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo SilentTalk 尚未完成安裝，請先執行「啟動 SilentTalk.cmd」。
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "scripts\start_edge_ai.py" --open
exit /b 0
