@echo off
title SkillBox Autostart Remover
cd /d "%~dp0"

echo [*] Removing SkillBox from Windows Startup...
python -c "import app; app.set_autostart(False); print('[OK] Successfully removed SkillBox from startup!')"

echo.
timeout /t 2 >nul
