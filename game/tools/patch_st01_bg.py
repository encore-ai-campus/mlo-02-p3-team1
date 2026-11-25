# -*- coding: utf-8 -*-
"""ST01 배경(bg_game.png) 손질: 바닥의 깃발 받침대 2개와 반환 레버를 지우고, 레버 자리에 쓰레기통을 그린다.

지우기는 make_stage_backgrounds.py 의 패치 인페인팅(inpaint)을 그대로 쓴다.
실행: python tools/patch_st01_bg.py  (원본은 git 에서 되살릴 수 있으므로 덮어쓴다)
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_stage_backgrounds import inpaint  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "textures/stages/ST01/bg_game.png")

# 원본 좌표(1672x941) 기준 지울 영역
FLAGS = [(892, 500, 984, 626), (1060, 500, 1152, 626)]
LEVER = (1098, 588, 1222, 742)
CAN_BASE = (1160, 724)   # 쓰레기통 바닥 중앙


def draw_can(size=4):
    """쓰레기통 한 개를 크게(size 배) 그린 뒤 줄여서 부드럽게 만든다. 반환: RGBA, 바닥 중앙 기준점."""
    W, H = 120 * size, 150 * size
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = size
    cx = W // 2
    ink = (40, 34, 52, 255)
    # 바닥 그림자
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((cx - 50 * s, 128 * s, cx + 54 * s, 148 * s), fill=(0, 0, 0, 90))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(3 * s)))
    d = ImageDraw.Draw(im)
    # 몸통 (아래가 살짝 좁은 통)
    top_y, bot_y = 46 * s, 136 * s
    body = [(cx - 40 * s, top_y), (cx + 40 * s, top_y), (cx + 34 * s, bot_y), (cx - 34 * s, bot_y)]
    d.polygon(body, fill=(78, 112, 150, 255), outline=ink, width=3 * s)
    # 밝은 왼쪽 면
    d.polygon([(cx - 36 * s, top_y + 3 * s), (cx - 6 * s, top_y + 3 * s), (cx - 6 * s, bot_y - 3 * s), (cx - 31 * s, bot_y - 3 * s)], fill=(104, 146, 190, 255))
    # 세로 홈
    for x in (-22, -8, 8, 22):
        d.line([(cx + x * s, top_y + 10 * s), (cx + int(x * 0.86) * s, bot_y - 10 * s)], fill=(52, 78, 110, 255), width=3 * s)
    # 바닥 띠
    d.ellipse((cx - 34 * s, bot_y - 8 * s, cx + 34 * s, bot_y + 8 * s), fill=(58, 86, 120, 255), outline=ink, width=3 * s)
    # 파란 발광 띠 (배경의 단말기들과 같은 색)
    d.rectangle((cx - 38 * s, 64 * s, cx + 38 * s, 71 * s), fill=(110, 220, 255, 255))
    # 휴지통 그림표
    ix, iy = cx, 98 * s
    d.rounded_rectangle((ix - 15 * s, iy - 14 * s, ix + 15 * s, iy + 20 * s), radius=3 * s, fill=(240, 244, 248, 255), outline=ink, width=2 * s)
    d.rectangle((ix - 19 * s, iy - 20 * s, ix + 19 * s, iy - 14 * s), fill=(240, 244, 248, 255), outline=ink, width=2 * s)
    d.rectangle((ix - 6 * s, iy - 25 * s, ix + 6 * s, iy - 20 * s), fill=(240, 244, 248, 255), outline=ink, width=2 * s)
    for x in (-7, 0, 7):
        d.line([(ix + x * s, iy - 8 * s), (ix + x * s, iy + 14 * s)], fill=ink, width=2 * s)
    # 뚜껑 (타원) + 손잡이
    d.ellipse((cx - 46 * s, 30 * s, cx + 46 * s, 56 * s), fill=(66, 96, 132, 255), outline=ink, width=3 * s)
    d.ellipse((cx - 40 * s, 30 * s, cx + 40 * s, 50 * s), fill=(122, 164, 206, 255))
    d.rounded_rectangle((cx - 14 * s, 20 * s, cx + 14 * s, 36 * s), radius=6 * s, fill=(66, 96, 132, 255), outline=ink, width=3 * s)
    small = im.resize((W // size, H // size), Image.Resampling.LANCZOS)
    return small, (60, 140)


def main():
    img = np.array(Image.open(PATH).convert("RGB"))
    out = Image.fromarray(inpaint(img, FLAGS + [LEVER])).convert("RGBA")
    can, (ax, ay) = draw_can()
    out.alpha_composite(can, (CAN_BASE[0] - ax, CAN_BASE[1] - ay))
    out.convert("RGB").save(PATH)
    print("saved", PATH)


if __name__ == "__main__":
    main()
