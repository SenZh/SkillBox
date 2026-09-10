@echo off
title SkillBox Status
cd /d "%~dp0"

echo ========================================
echo        SkillBox Service Status
echo ========================================
if exist ".skillbox.pid" (
    set /p PIDINFO=<.skillbox.pid
    echo [Status] RUNNING (PID:PORT = %PIDINFO%)
) else (
    echo [Status] STOPPED
)
echo ========================================
pause
