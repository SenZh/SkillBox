@echo off
title SkillBox Autostart Registrar
cd /d "%~dp0"

echo [*] Registering SkillBox to Windows Startup (Current User)...
python -c "import app; app.set_autostart(True); print('[OK] Successfully registered SkillBox to startup!')"

echo.
echo You can also toggle this anytime in SkillBox WebUI Settings page.
timeout /t 2 >nul
