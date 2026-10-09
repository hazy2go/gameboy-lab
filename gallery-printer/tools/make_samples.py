"""Draws two sample pictures into images/ so the ROM has something to show:
a printer test card (tone steps, gradient, fine lines) and a dithered sunset."""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ImageFont.truetype(str(ROOT / "tools" / "fonts" / "PixelOperatorMono8.ttf"), 8)


def test_card() -> Image.Image:
    # drawn at native size with exact greys, so the converter keeps it pixel-perfect
    W, H = 160, 144
    shades = [255, 170, 85, 0]
    im = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W - 1, H - 1], outline=0)
    d.rectangle([2, 2, W - 3, H - 3], outline=85)
    d.text((40, 8), "GB GALLERY", font=FONT, fill=0)
    d.text((12, 18), "PRINTER TEST CARD", font=FONT, fill=85)
    for i, s in enumerate(shades):  # four tone steps
        d.rectangle([12 + i * 34, 32, 12 + i * 34 + 33, 56], fill=s, outline=0)
    for x in range(0, 136, 2):  # 1px line pairs: does the head resolve them?
        d.line([12 + x, 64, 12 + x, 78], fill=0)
    d.ellipse([52, 84, 108, 140 - 4], outline=0, width=3)
    d.ellipse([66, 98, 94, 122], fill=85)
    for y in range(84, 132, 4):
        for x in range(10, 42, 4):
            d.rectangle([x, y, x + 1, y + 1], fill=0)
            d.rectangle([x + 112, y + 2, x + 113, y + 3], fill=85)
    return im


def sunset() -> Image.Image:
    # big grayscale picture: the converter crops, dithers and quantizes it
    W, H = 640, 576
    im = Image.new("L", (W, H))
    px = im.load()
    for y in range(H):
        for x in range(W):
            sky = 60 + 190 * (1 - y / (H * 0.62))
            sun = max(0, 1 - math.hypot(x - W * 0.62, y - H * 0.5) / 120)
            px[x, y] = int(min(255, max(0, sky + 255 * sun ** 0.6)))
    d = ImageDraw.Draw(im)
    pts = [(0, H)]
    for x in range(0, W + 20, 20):
        pts.append((x, H * 0.58 + 50 * math.sin(x / 70) + 25 * math.sin(x / 23)))
    pts.append((W, H))
    d.polygon(pts, fill=40)
    pts = [(0, H)] + [(x, H * 0.75 + 30 * math.sin(x / 50 + 1)) for x in range(0, W + 20, 20)] + [(W, H)]
    d.polygon(pts, fill=10)
    for i in range(6):  # sun glints on the water line
        y = int(H * 0.86 + i * 12)
        d.line([W * 0.62 - 60 + i * 8, y, W * 0.62 + 60 - i * 8, y], fill=200, width=3)
    return im


if __name__ == "__main__":
    out = ROOT / "images"
    out.mkdir(exist_ok=True)
    test_card().save(out / "01-test card.png")
    sunset().save(out / "02-sunset.png")
    print("wrote images/01-test card.png, images/02-sunset.png")
