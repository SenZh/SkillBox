#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SkillBox 跨平台工具模块 (Platform Utilities)
集中处理平台差异：浏览器打开（含应用模式）、桌面快捷方式、CLI 安装、进程控制。
所有函数均按 sys.platform 分派，Windows / macOS / Linux 三平台可用。
"""

import os
import sys
import shutil
import subprocess
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ICON_ICO = BASE_DIR / "assets" / "icon.ico"
ICON_PNG = BASE_DIR / "assets" / "icon.png"


# ============================================================
# 浏览器：应用模式（无地址栏独立窗口）优先，回退系统默认浏览器
# ============================================================

def _find_chromium_browser():
    """
    查找本机 Chrome / Edge / Chromium 可执行文件路径。
    返回可执行文件路径字符串，找不到返回 None。
    """
    candidates = []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        candidates = [
            os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:
        candidates = [
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            shutil.which("microsoft-edge"),
            shutil.which("microsoft-edge-stable"),
        ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def open_in_app_mode(url):
    """
    以"应用模式"打开 URL：Chrome/Edge 的 --app 参数会弹出无地址栏的独立窗口，观感接近原生客户端。
    找不到 Chromium 系浏览器时，回退到系统默认浏览器。

    返回: "app"（应用模式成功）| "browser"（回退默认浏览器）
    """
    exe = _find_chromium_browser()
    if exe:
        try:
            creation_flags = 0x08000000 if sys.platform == "win32" else 0
            subprocess.Popen(
                [exe, f"--app={url}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                start_new_session=(sys.platform != "win32"),
            )
            return "app"
        except Exception:
            pass
    webbrowser.open(url)
    return "browser"


# ============================================================
# 桌面快捷方式 / 应用入口
# ============================================================

def get_desktop_dir():
    """获取当前用户桌面目录（跨平台）"""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0, None, 0, buf)  # CSIDL_DESKTOP
            if buf.value:
                return Path(buf.value)
        except Exception:
            pass
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    # macOS / Linux 常见桌面路径
    for cand in [Path.home() / "Desktop", Path.home() / "桌面"]:
        if cand.exists():
            return cand
    return Path.home() / "Desktop"


def get_start_menu_dir():
    """获取 Windows 开始菜单程序目录；非 Windows 返回 None"""
    if sys.platform != "win32":
        return None
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def _launcher_command():
    """
    返回用于快捷方式的启动命令（不含 URL 参数）。
    若已通过 PyInstaller 打包出 SkillBox.exe，则优先直接指向该 exe
    （图标/进程名最正确、无需本机 Python）；否则回退到 python(w) desktop_app.py。
    桌面托盘应用会内嵌托管服务并展示原生 WebView 窗口，关闭窗口即缩到系统托盘。
    """
    # 优先：打包好的独立可执行文件
    for exe_name in ("SkillBox.exe",):
        exe_path = BASE_DIR / "dist" / exe_name
        if exe_path.exists():
            return str(exe_path), ""

    python_exe = sys.executable
    if sys.platform == "win32":
        if python_exe.lower().endswith("python.exe"):
            pythonw = python_exe[:-len("python.exe")] + "pythonw.exe"
            if os.path.exists(pythonw):
                python_exe = pythonw
    app_script = str((BASE_DIR / "desktop_app.py").resolve())
    return python_exe, app_script


def create_desktop_shortcut():
    """
    创建桌面快捷方式，双击即可启动服务并打开 WebUI。
    - Windows: .lnk（通过 powershell WScript.Shell）
    - Linux:   .desktop
    - macOS:   .command 脚本

    返回创建后的路径，失败返回 None。
    """
    if sys.platform == "win32":
        return _create_shortcut_windows(get_desktop_dir())
    elif sys.platform == "darwin":
        return _create_shortcut_macos()
    else:
        return _create_shortcut_linux()


def _create_shortcut_windows(target_dir):
    target_dir = Path(target_dir)
    if not target_dir.exists():
        return None
    # 快捷方式直接指向桌面托盘应用：内嵌服务 + 原生窗口 + 系统托盘常驻
    python_exe, app_script = _launcher_command()
    lnk_path = target_dir / "SkillBox.lnk"
    # 优先使用自带图标，缺失时回退 python 可执行文件图标
    icon = str(ICON_ICO) if ICON_ICO.exists() else (python_exe if os.path.exists(python_exe) else "")
    args = f'"{app_script}"' if app_script else ""
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{lnk_path}'); "
        f"$sc.TargetPath = '{python_exe}'; "
        f"$sc.Arguments = '{args}'; "
        f"$sc.WorkingDirectory = '{BASE_DIR}'; "
        f"$sc.IconLocation = '{icon}'; "
        "$sc.Description = 'SkillBox - AI 技能管理器'; "
        "$sc.WindowStyle = 1; "
        "$sc.Save()"
    )
    try:
        creation_flags = 0x08000000
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, creationflags=creation_flags, timeout=30
        )
        if lnk_path.exists():
            return lnk_path
        return None
    except Exception:
        return None


def _create_shortcut_linux():
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    python_exe, app_script = _launcher_command()
    desktop_file = apps_dir / "skillbox.desktop"
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=SkillBox\n"
        "Comment=AI 技能管理器\n"
        f"Exec={python_exe} {app_script}".rstrip() + "\n"
        f"Path={BASE_DIR}\n"
        f"Icon={ICON_PNG if ICON_PNG.exists() else 'applications-system'}\n"
        "Terminal=false\n"
        "Categories=Development;\n"
    )
    desktop_file.write_text(content, encoding="utf-8")
    desktop_file.chmod(0o755)
    # 尝试同时放到桌面
    desktop = get_desktop_dir()
    if desktop.exists():
        try:
            (desktop / "SkillBox.desktop").write_text(content, encoding="utf-8")
            (desktop / "SkillBox.desktop").chmod(0o755)
        except Exception:
            pass
    return desktop_file


def _create_shortcut_macos():
    python_exe, app_script = _launcher_command()
    command_file = Path.home() / "Desktop" / "SkillBox.command"
    launch = f'"{python_exe}"' + (f' "{app_script}"' if app_script else "")
    content = (
        "#!/bin/bash\n"
        f'cd "{BASE_DIR}"\n'
        f'{launch}\n'
    )
    try:
        command_file.write_text(content, encoding="utf-8")
        command_file.chmod(0o755)
        return command_file
    except Exception:
        return None


def remove_desktop_shortcut():
    """移除已创建的桌面快捷方式，返回移除的数量"""
    removed = 0
    if sys.platform == "win32":
        p = get_desktop_dir() / "SkillBox.lnk"
        if p.exists():
            p.unlink()
            removed += 1
    elif sys.platform == "darwin":
        p = Path.home() / "Desktop" / "SkillBox.command"
        if p.exists():
            p.unlink()
            removed += 1
    else:
        for p in [Path.home() / ".local" / "share" / "applications" / "skillbox.desktop",
                  get_desktop_dir() / "SkillBox.desktop"]:
            if p.exists():
                p.unlink()
                removed += 1
    return removed
