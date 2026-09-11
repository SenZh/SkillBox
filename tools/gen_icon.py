#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SkillBox 图标生成脚本。
用法: python tools/gen_icon.py

设计：圆角方形（靛蓝→紫渐变底）+ 白色等距立方体（"Box"），
      立方体三条棱用不同明度区分，象征模块化技能包。
输出：
  assets/icon.ico   Windows 快捷方式 / 应用图标（多尺寸）
  assets/icon.png   512x512 通用 PNG（favicon / 文档）
  assets/icon-256.png / icon-128.png / icon-64.png / icon-32.png
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

# 画布放大 4 倍再缩小，获得平滑边缘（超采样抗锯齿）
SS = 4
SIZE = 512
S = SIZE * SS


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def draw_gradient_bg(size):
    """绘制对角线性渐变圆角方形背景"""
    c1 = (99, 102, 241)    # indigo-500
    c2 = (139, 92, 246)    # violet-500
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # 渐变层
    grad = Image.new("RGBA", (size, size))
    px = grad.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size - 2)
            px[x, y] = lerp(c1, c2, t) + (255,)
    # 圆角遮罩
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    radius = int(size * 0.22)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def draw_box(img):
    """在背景上绘制白色等距立方体（Box）"""
    d = ImageDraw.Draw(img)
    size = img.size[0]
    # 立方体几何参数（相对于画布）
    cx = size * 0.5
    top = size * 0.26
    half_w = size * 0.24     # 顶面半宽
    half_h = size * 0.13     # 等距半高
    depth = size * 0.24      # 侧面高度

    # 顶面顶点
    top_p = (cx, top)
    right_p = (cx + half_w, top + half_h)
    bottom_p = (cx, top + 2 * half_h)
    left_p = (cx - half_w, top + half_h)
    # 底部三点
    top_b = (cx, top + depth)
    right_b = (cx + half_w, top + half_h + depth)
    bottom_b = (cx, top + 2 * half_h + depth)
    left_b = (cx - half_w, top + half_h + depth)

    # 顶面（最亮）
    d.polygon([top_p, right_p, bottom_p, left_p], fill=(255, 255, 255, 245))
    # 右面（中）
    d.polygon([right_p, bottom_p, bottom_b, right_b], fill=(226, 232, 255, 235))
    # 左面（暗）
    d.polygon([left_p, bottom_p, bottom_b, left_b], fill=(199, 210, 254, 235))
    # 顶面中线（增强立体）
    d.line([top_p, bottom_p], fill=(165, 180, 252, 200), width=max(1, int(SIZE * 0.006)))
    return img


def build_master():
    bg = draw_gradient_bg(S)
    icon = draw_box(bg)
    return icon.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    master = build_master()
    master.save(ASSETS / "icon.png")

    for sz in (256, 128, 64, 48, 32, 16):
        master.resize((sz, sz), Image.LANCZOS).save(ASSETS / f"icon-{sz}.png")

    # 多尺寸 ICO
    master.save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"[OK] 图标已生成于: {ASSETS}")
    for f in sorted(ASSETS.iterdir()):
        print(f"     {f.name}  ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
