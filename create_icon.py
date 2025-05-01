#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
创建一个简单的图标文件
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    """创建一个简单的图标文件"""
    # 创建一个512x512的图像
    size = 512
    img = Image.new('RGBA', (size, size), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 绘制一个漂亮的渐变背景
    for y in range(size):
        r = int(255 * (1 - y / size))
        g = int(100 + 100 * (y / size))
        b = int(200 * (y / size))
        for x in range(size):
            draw.point((x, y), fill=(r, g, b, 255))
    
    # 绘制一个圆
    margin = 20
    draw.ellipse((margin, margin, size - margin, size - margin), 
                fill=(255, 255, 255, 180))
    
    # 绘制视频播放按钮
    triangle_size = size // 3
    center_x, center_y = size // 2, size // 2
    play_button = [
        (center_x - triangle_size // 3, center_y - triangle_size // 2),
        (center_x + triangle_size // 2, center_y),
        (center_x - triangle_size // 3, center_y + triangle_size // 2)
    ]
    draw.polygon(play_button, fill=(50, 50, 200, 255))
    
    # 保存为各种尺寸的图标
    img.save('icon_large.png')
    
    # 创建ico文件
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    for s in sizes:
        resized_img = img.resize((s, s), Image.LANCZOS)
        images.append(resized_img)
    
    # 保存为ico文件
    img.save('icon.ico', format='ICO', sizes=[(s, s) for s in sizes])
    print("图标文件已创建: icon.ico")

if __name__ == "__main__":
    create_icon() 