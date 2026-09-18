@echo off
title GW Bleed
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run the desktop setup steps in README.md first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m gw_imposition.gui
if errorlevel 1 pause
