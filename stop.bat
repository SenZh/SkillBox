@echo off
title SkillBox Stopper
cd /d "%~dp0"

if exist ".skillbox.pid" (
    for /f "tokens=1 delims=:" %%a in (.skillbox.pid) do (
        taskkill /F /PID %%a >nul 2>&1
    )
    del /f /q ".skillbox.pid" >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":7860" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

ping -n 2 127.0.0.1 >nul 2>&1
exit
