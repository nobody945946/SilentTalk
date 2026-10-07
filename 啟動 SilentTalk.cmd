@echo off
setlocal
cd /d "%~dp0"
set "BOOTSTRAP_ARGS="
if /i "%~1"=="--check" set "BOOTSTRAP_ARGS=-Check -SetupOnly"
if /i "%~1"=="--setup-only" set "BOOTSTRAP_ARGS=-SetupOnly"
if /i "%~1"=="--tts-only" set "BOOTSTRAP_ARGS=-TtsOnly"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1" -ProjectDir "%~dp0." %BOOTSTRAP_ARGS%
if errorlevel 1 (
    echo ERROR: SilentTalk setup or startup failed. Run this launcher again to resume.
    pause
    exit /b 1
)
exit /b 0
