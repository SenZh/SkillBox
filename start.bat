@echo off
title SkillBox Starter
cd /d "%~dp0"

:: Check if already running
if exist ".skillbox.pid" (
    echo [*] SkillBox is already running in background.
    start http://127.0.0.1:7860
    exit /b 0
)

:: Launch detached background process safely using current directory
python -c "import os, subprocess; subprocess.Popen(['pythonw', 'app.py'], cwd=os.getcwd(), creationflags=0x00000008 | 0x00000200)"

:: Wait 1s
ping -n 2 127.0.0.1 >nul 2>&1

:: Open browser and exit
start http://127.0.0.1:7860
exit /b 0
