@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"

if not exist "config.toml" (
    echo ERROR: config.toml is missing.
    pause
    exit /b 2
)

if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo Created .env from .env.example.
    echo Enter DISCORD_BOT_TOKEN and OWNER_USER_ID, save the file, then return here.
    start "SilentTalk settings" /wait notepad.exe ".env"
)

if not exist ".venv\Scripts\python.exe" (
    call :find_python
    if errorlevel 1 exit /b 1
    echo Creating the SilentTalk virtual environment...
    !PYTHON_EXE! !PYTHON_ARGS! -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create the Python virtual environment.
        pause
        exit /b 1
    )
    if not exist ".venv\Scripts\python.exe" (
        echo ERROR: Python reported success but the virtual environment is missing.
        pause
        exit /b 1
    )
)

echo Checking Python packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: Could not install the required Python packages.
    pause
    exit /b 1
)

where llama-server.exe >nul 2>nul
if errorlevel 1 (
    where winget.exe >nul 2>nul
    if errorlevel 1 (
        echo ERROR: llama.cpp is missing and winget is unavailable.
        echo Install llama.cpp, then run this launcher again.
        pause
        exit /b 1
    )
    echo Installing lightweight local Copilot runtime ^(llama.cpp^)...
    winget install --id ggml.llamacpp -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo ERROR: llama.cpp installation failed.
        pause
        exit /b 1
    )
    set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
)

if not exist "scripts\setup_copilot.py" (
    echo ERROR: scripts\setup_copilot.py is missing.
    pause
    exit /b 1
)

echo Checking Copilot models ^(first run downloads about 650 MB^)...
".venv\Scripts\python.exe" "scripts\setup_copilot.py"
if errorlevel 1 (
    echo ERROR: Copilot model deployment failed.
    echo Check your network connection, then run this launcher again.
    pause
    exit /b 1
)

where ffmpeg.exe >nul 2>nul
if errorlevel 1 (
    where winget.exe >nul 2>nul
    if errorlevel 1 (
        echo ERROR: FFmpeg is missing and winget is unavailable.
        echo Install FFmpeg, then run this launcher again.
        pause
        exit /b 1
    )
    echo Installing FFmpeg...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo ERROR: FFmpeg installation failed.
        pause
        exit /b 1
    )
    set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
)

".venv\Scripts\python.exe" -c "from pathlib import Path; from silenttalk.config import load_settings; load_settings(Path.cwd())"
if errorlevel 1 (
    echo ERROR: config.toml is invalid.
    pause
    exit /b 2
)

if /i "%~1"=="--check" (
    echo SilentTalk startup check passed.
    exit /b 0
)

if not exist "scripts\restart_silenttalk.ps1" (
    echo ERROR: scripts\restart_silenttalk.ps1 is missing.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\restart_silenttalk.ps1" -ProjectDir "%CD%" -Pythonw "%CD%\.venv\Scripts\pythonw.exe"
if errorlevel 1 (
    echo ERROR: SilentTalk restart failed.
    pause
    exit /b 1
)

exit /b 0

:find_python
set "PYTHON_EXE="
set "PYTHON_ARGS="

where py.exe >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py.exe"
        set "PYTHON_ARGS=-3.12"
        exit /b 0
    )
)

where python.exe >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(sys.version_info[:2] != (3, 12))" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=python.exe"
        exit /b 0
    )
)

where winget.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python 3.12 is required and winget is unavailable.
    pause
    exit /b 1
)

echo Installing Python 3.12...
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo ERROR: Python 3.12 installation failed.
    pause
    exit /b 1
)

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    exit /b 0
)

echo ERROR: Python 3.12 was installed but could not be located.
echo Close this window and run the launcher again.
pause
exit /b 1
