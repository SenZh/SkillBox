#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SkillBox 单文件 exe 打包脚本 (PyInstaller)

将 desktop_app.py 打包为带 SkillBox 图标、无控制台黑窗的单文件 exe。
产物：dist/SkillBox.exe，双击即启动桌面托盘应用（内嵌服务 + 原生窗口 + 系统托盘）。

依赖：pip install pyinstaller
用法：python tools/build_exe.py
"""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ICON = BASE_DIR / "assets" / "icon.ico"
ENTRY = BASE_DIR / "desktop_app.py"
NAME = "SkillBox"


def main():
    try:
        import PyInstaller  # noqa: F401
    except Exception:
        print("[!] 未安装 PyInstaller，请先执行: pip install pyinstaller")
        return 1

    if not ENTRY.exists():
        print(f"[!] 找不到入口文件: {ENTRY}")
        return 1

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",              # 无控制台黑窗
        "--name", NAME,
        # pywebview 的后端与隐式依赖需要显式收集
        "--collect-all", "webview",
        "--collect-all", "pystray",
        "--collect-all", "PIL",
        # 资源目录：图标、内置技能
        "--add-data", f"assets{os.pathsep}assets",
        "--add-data", f"builtin_skills{os.pathsep}builtin_skills",
    ]
    if ICON.exists():
        cmd += ["--icon", str(ICON)]
    cmd.append(str(ENTRY))

    print("[*] 开始打包 SkillBox.exe ...")
    print("    命令:", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(BASE_DIR))
    if rc == 0:
        print("[OK] 打包完成: dist/SkillBox.exe")
    else:
        print(f"[!] 打包失败，返回码: {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
