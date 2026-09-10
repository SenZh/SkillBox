@echo off
chcp 65001 > nul
title SkillBox - AI 技能管理器
echo [*] 正在启动 SkillBox 控制台...
python "%~dp0app.py"
if %errorlevel% neq 0 (
    echo [!] 启动异常退出，错误码: %errorlevel%
    pause
)
