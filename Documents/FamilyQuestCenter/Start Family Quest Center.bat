@REM Family Quest Center Developer Notes
@REM File: Start Family Quest Center.bat
@REM Purpose: Starts Family Quest Center on a Windows computer.
@REM Maintenance: Keep paths relative so the package remains portable.
@REM Documentation updated: 2026-07-31

@echo off
title Family Quest Center

cd /d "%~dp0"

start "" cmd /c "timeout /t 2 >nul && start http://127.0.0.1:5000"

python app.py

pause