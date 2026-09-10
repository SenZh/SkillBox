@echo off
title SkillBox
echo [*] Starting SkillBox...
python "%~dp0app.py"
if errorlevel 1 (
    echo.
    echo [!] SkillBox exited with error code %errorlevel%.
    pause
)
