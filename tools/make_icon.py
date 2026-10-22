# -*- coding: utf-8 -*-
"""生成 exe 图标（与托盘图标同款：蓝底 + 四宫格）。"""
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 蓝色圆角底板
d.rounded_rectangle([12, 40, S - 12, S - 40], radius=38, fill=(59, 130, 246, 255))

# 四个白色小格
w, h, gap = 62, 44, 14
total_w = w * 2 + gap
total_h = h * 2 + gap
x0 = (S - total_w) // 2
y0 = (S - total_h) // 2
for i in range(2):
    for j in range(2):
        x = x0 + i * (w + gap)
        y = y0 + j * (h + gap)
        d.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=(255, 255, 255, 255))

img.save(os.path.join(OUT, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(os.path.join(OUT, "icon.png"))
print("saved icon.ico / icon.png")
