#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SkillBox Release 成果物打包脚本

一键产出发行版成果物（输出到 release/ 目录）：
  1) SkillBox-<version>-win64.zip          免安装绿色压缩包（解压即用）
  2) SkillBox-Setup-<version>.exe          Windows 安装包（Inno Setup，需已安装 ISCC）

前置：先执行 `python tools/build_exe.py` 生成 dist/SkillBox.exe。
用法：python tools/build_release.py
"""

import os
import re
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_EXE = BASE_DIR / "dist" / "SkillBox.exe"
RELEASE_DIR = BASE_DIR / "release"
TOOLS_DIR = BASE_DIR / "tools"


def read_version():
    """从 app.py 读取 __version__"""
    try:
        text = (BASE_DIR / "app.py").read_text(encoding="utf-8")
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "0.0.0"


def stage_portable_dir(version):
    """
    组装绿色免安装目录 release/SkillBox-<version>-win64/：
    含 SkillBox.exe + README/LICENSE/CHANGELOG + 内置技能与图标资源。
    """
    stage = RELEASE_DIR / f"SkillBox-{version}-win64"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)

    # 主程序
    shutil.copy2(DIST_EXE, stage / "SkillBox.exe")

    # 文档
    for doc in ("README.md", "LICENSE", "CHANGELOG.md"):
        src = BASE_DIR / doc
        if src.exists():
            shutil.copy2(src, stage / doc)

    # 资源（打包 exe 已内含，但保留一份便于查看/自定义图标）
    assets_src = BASE_DIR / "assets"
    if assets_src.exists():
        shutil.copytree(assets_src, stage / "assets", dirs_exist_ok=True)

    # 内置技能
    builtin_src = BASE_DIR / "builtin_skills"
    if builtin_src.exists():
        shutil.copytree(builtin_src, stage / "builtin_skills", dirs_exist_ok=True)

    # 使用说明
    (stage / "使用说明.txt").write_text(
        "SkillBox 免安装版使用说明\n"
        "========================================\n\n"
        "1. 双击 SkillBox.exe 即可启动桌面托盘应用；\n"
        "2. 关闭窗口会缩到右下角系统托盘，右键托盘图标可退出；\n"
        "3. 首次启动会自动把 skillbox 命令注册到用户 PATH；\n"
        "4. 配置与技能缓存保存在本目录（config.json / .skillbox_cache）。\n\n"
        "命令行：新开终端执行 skillbox status / skillbox help\n",
        encoding="utf-8",
    )
    return stage


def make_zip(stage: Path, version):
    """将绿色目录压缩为 release/SkillBox-<version>-win64.zip"""
    zip_path = RELEASE_DIR / f"SkillBox-{version}-win64.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(stage):
            for f in files:
                full = Path(root) / f
                arcname = Path(stage.name) / full.relative_to(stage)
                zf.write(full, arcname)
    return zip_path


def find_iscc():
    """查找 Inno Setup 编译器 ISCC.exe（覆盖系统级与用户级安装）"""
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        shutil.which("iscc"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        os.path.join(local_appdata, "Programs", "Inno Setup 6", "ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def build_installer(version, stage: Path):
    """调用 Inno Setup 编译安装包（未安装 ISCC 则跳过）"""
    iscc = find_iscc()
    if not iscc:
        print("[!] 未找到 Inno Setup 编译器 (ISCC.exe)，跳过安装包构建。")
        print("    下载安装后重试: https://jrsoftware.org/isdl.php")
        return None
    iss = TOOLS_DIR / "installer.iss"
    if not iss.exists():
        print(f"[!] 找不到安装脚本: {iss}")
        return None
    rc = subprocess.call([
        iscc,
        f"/DMyAppVersion={version}",
        f"/DSourceDir={stage}",
        f"/DOutputDir={RELEASE_DIR}",
        str(iss),
    ])
    if rc == 0:
        return RELEASE_DIR / f"SkillBox-Setup-{version}.exe"
    print(f"[!] Inno Setup 编译失败，返回码: {rc}")
    return None


def main():
    version = read_version()
    print("=" * 56)
    print(f"       SkillBox Release 打包 (v{version})")
    print("=" * 56)

    if not DIST_EXE.exists():
        print(f"[!] 未找到 {DIST_EXE}，请先执行: python tools/build_exe.py")
        return 1

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    stage = stage_portable_dir(version)
    print(f"[OK] 绿色目录已生成: {stage}")

    zip_path = make_zip(stage, version)
    size_mb = round(zip_path.stat().st_size / 1024 / 1024, 1)
    print(f"[OK] 免安装压缩包: {zip_path} ({size_mb} MB)")

    installer = build_installer(version, stage)
    if installer and installer.exists():
        size_mb = round(installer.stat().st_size / 1024 / 1024, 1)
        print(f"[OK] Windows 安装包: {installer} ({size_mb} MB)")

    print("=" * 56)
    print("Release 成果物已输出到: " + str(RELEASE_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
