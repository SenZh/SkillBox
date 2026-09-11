#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SkillBox 图标资源构建脚本（最终版）。

输入（手工设计的 SVG 源）:
  tools/icon_src/icon_full.svg    带文字版（正方形，符号在上 + SkillBox 文字在下）
  tools/icon_src/icon_simple.svg  简化版（正方形，放大立方体，无文字）

输出到 assets/:
  icon.svg / icon-simple.svg       矢量源
  icon.png (512)                   通用/应用图标
  icon-256/128/64/48.png           中等尺寸（带文字版）
  favicon-32/16.png                小尺寸（简化版）
  icon.ico                         多尺寸 ICO（大尺寸带文字，小尺寸用简化）
  icon.icns                        可选（macOS，需 icns 工具，缺失则跳过）

渲染依赖：系统 Edge/Chrome（headless 截图）。找不到则报错退出。
"""

import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "tools" / "icon_src"
ASSETS = BASE / "assets"
ASSETS.mkdir(exist_ok=True)

# 文字由 Pillow 用固定字体文件绘制（字形跨平台一致），字体优先 Segoe UI Bold
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\seguisb.ttf",
    "/System/Library/Fonts/SFNS.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def load_font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_text_overlay(img, text, canvas=512):
    """在图标下方居中绘制 'SkillBox' 文字（无 SVG 文字依赖）"""
    d = ImageDraw.Draw(img)
    # 字号按画布比例
    fsize = int(canvas * 0.121)  # 62 / 512
    f = load_font(fsize)
    bbox = d.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (canvas - tw) / 2 - bbox[0]
    y = int(canvas * 0.845) - th / 2 - bbox[1]  # 文字垂直中心约在 y=432
    d.text((x, y), text, font=f, fill=(255, 255, 255, 255))
    return img

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser():
    for p in EDGE_CANDIDATES + CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _write_multi_ico(ico_path: Path, full: Image.Image, simple: Image.Image,
                     full_sizes=(256, 128), simple_sizes=(64, 48, 32, 16)):
    """生成多尺寸 ICO：大尺寸带文字版，小尺寸简化版。"""
    frames = []
    for sz in sorted(list(full_sizes) + list(simple_sizes), reverse=True):
        src = full if sz in full_sizes else simple
        frames.append(src.resize((sz, sz), Image.LANCZOS))
    frames[0].save(ico_path, format="ICO",
                   sizes=[(f.width, f.height) for f in frames],
                   append_images=frames[1:])


def render_svg(browser, svg_path: Path, out_png: Path, size=512):
    """用 headless 浏览器把 SVG 渲染为 PNG（透明背景）"""
    udd = tempfile.mkdtemp(prefix="skillbox-icon-")
    url = svg_path.resolve().as_uri()
    cmd = [
        browser, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--hide-scrollbars", f"--user-data-dir={udd}",
        "--default-background-color=00000000",
        f"--window-size={size},{size}",
        f"--screenshot={out_png}", url,
    ]
    subprocess.run(cmd, capture_output=True)
    shutil.rmtree(udd, ignore_errors=True)
    if not out_png.exists():
        raise RuntimeError(f"渲染失败: {svg_path.name}")
    return out_png


def main():
    browser = find_browser()
    if not browser:
        print("[!] 未找到 Edge/Chrome，无法渲染 SVG")
        return 1

    full_svg = SRC / "icon_full.svg"
    simple_svg = SRC / "icon_simple.svg"
    for f in (full_svg, simple_svg):
        if not f.exists():
            print(f"[!] 缺少源文件: {f}")
            return 1

    # 同步矢量源到 assets
    shutil.copy2(full_svg, ASSETS / "icon.svg")
    shutil.copy2(simple_svg, ASSETS / "icon-simple.svg")

    tmp = Path(tempfile.mkdtemp(prefix="skillbox-iconrender-"))
    try:
        full_png = render_svg(browser, full_svg, tmp / "full.png", 512)
        simple_png = render_svg(browser, simple_svg, tmp / "simple.png", 512)

        full = Image.open(full_png).convert("RGBA")
        simple = Image.open(simple_png).convert("RGBA")
        # 用固定字体绘制 "SkillBox" 文字（字形跨平台一致）
        full = draw_text_overlay(full, "SkillBox", 512)

        # 中等尺寸：带文字版（文字在 <=64px 会糊，故下限取 128）
        for sz in (512, 256, 128):
            name = "icon.png" if sz == 512 else f"icon-{sz}.png"
            full.resize((sz, sz), Image.LANCZOS).save(ASSETS / name)

        # 小尺寸：简化版（无文字，保证清晰辨识）
        for sz in (64, 48, 32, 16):
            simple.resize((sz, sz), Image.LANCZOS).save(ASSETS / f"icon-{sz}.png")
        for sz in (32, 16):
            simple.resize((sz, sz), Image.LANCZOS).save(ASSETS / f"favicon-{sz}.png")

        # ICO：大尺寸（>=128）用带文字版，小尺寸（<=64）用简化版
        _write_multi_ico(ASSETS / "icon.ico", full, simple,
                         full_sizes=(256, 128), simple_sizes=(64, 48, 32, 16))
        print(f"[OK] 图标已生成 -> {ASSETS}")
        for f in sorted(ASSETS.iterdir()):
            if f.is_file() and f.suffix in (".png", ".ico", ".svg"):
                print(f"     {f.name}  ({f.stat().st_size} bytes)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
