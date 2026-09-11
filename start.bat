@echo off
rem SkillBox 兼容启动入口：拉起桌面托盘应用（无黑窗）
cd /d "%~dp0"
if exist "%~dp0dist\SkillBox.exe" (
    start "" "%~dp0dist\SkillBox.exe"
) else (
    start "" pythonw "%~dp0desktop_app.py"
)
