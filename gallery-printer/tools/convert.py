"""
Turns every picture in images/ into Game Boy tile data and writes the C sources
the ROM is built from.

Each picture becomes a full-screen 160x144 image: 20x18 = 360 unique tiles,
2 bits per pixel, 5760 bytes, stored row-major (left to right, top to bottom).
That order is what the screen code copies into VRAM *and* what the Game Boy
Printer wants (one data packet = two tile rows = 40 tiles = 640 bytes), so the
ROM can stream an image straight from cartridge ROM to the printer.

Shades: 0 = white (paper), 1 = light grey, 2 = dark grey, 3 = black (ink).

Each picture also gets a 32x32 thumbnail (4x4 tiles) for the gallery grid.

Outputs (into build/gen; files are only rewritten when their content changes,
and build/gen/.stamp is touched when anything did, so make relinks only then):
    assets.h / assets.c   the picture table (home bank)
    img_NNN.c             one banked file per picture (bankpack places them)
and a 3x preview PNG per picture in build/previews, to check before flashing.

Usage: python3 tools/convert.py [--dither bayer|fs|none] [--fit crop|pad]
"""

import argparse
import re
import shutil
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "images"
PRIVATE = ROOT / "images-private"     # your own pictures: git-ignored, left out of PUBLIC=1 builds
GEN = ROOT / "build" / "gen"
PREVIEWS = ROOT / "build" / "previews"

W, H = 160, 144
MAX_IMAGES = 200            # ~1.2 MB of ROM; the ROM itself sizes everything from IMAGE_COUNT
NAME_LEN = 16               # visible characters in the list (20 columns minus cursor/count)
EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}

# DMG-ish greens, only used for the preview PNGs
PREVIEW_PALETTE = [(224, 248, 208), (136, 192, 112), (52, 104, 86), (8, 24, 32)]

BAYER4 = [
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
]


# ---------------------------------------------------------------- pictures

def load(path: Path, fit: str) -> Image.Image:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    im = im.convert("L")
    if fit == "pad":
        im = ImageOps.pad(im, (W, H), Image.LANCZOS, color=255)
    else:
        im = ImageOps.fit(im, (W, H), Image.LANCZOS)
    return ImageOps.autocontrast(im, cutoff=1)


def is_native(path: Path) -> bool:
    """A 160x144 picture that already uses 4 or fewer greys is kept pixel-exact."""
    im = Image.open(path)
    if im.size != (W, H):
        return False
    colors = im.convert("L").getcolors(4)
    return colors is not None


def native_shades(path: Path) -> list[list[int]]:
    im = Image.open(path).convert("L")
    levels = sorted({v for _, v in im.getcolors(4)}, reverse=True)  # brightest first
    # spread whatever greys are used over white..black
    if len(levels) == 1:
        lut = {levels[0]: 0 if levels[0] > 127 else 3}
    else:
        lut = {v: round(i * 3 / (len(levels) - 1)) for i, v in enumerate(levels)}
    return [[lut[im.getpixel((x, y))] for x in range(W)] for y in range(H)]


def quantize(im: Image.Image, dither: str) -> list[list[int]]:
    """Grayscale image -> rows of shades 0 (white) .. 3 (black)."""
    px = [[im.getpixel((x, y)) / 255.0 for x in range(W)] for y in range(H)]
    out = [[0] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            v = px[y][x]
            if dither == "bayer":
                level = int(v * 3 + (BAYER4[y & 3][x & 3] + 0.5) / 16)
            elif dither == "fs":
                level = int(round(v * 3))
            else:
                level = int(round(v * 3))
            level = max(0, min(3, level))
            if dither == "fs":
                err = v - level / 3
                for dx, dy, k in ((1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and ny < H:
                        px[ny][nx] += err * k / 16
            out[y][x] = 3 - level
    return out


def encode_tile(rows: list[list[int]]) -> list[int]:
    data = []
    for row in rows:
        lo = hi = 0
        for x, v in enumerate(row):
            lo |= (v & 1) << (7 - x)
            hi |= ((v >> 1) & 1) << (7 - x)
        data += [lo, hi]
    return data


def to_tiles(shades: list[list[int]]) -> list[int]:
    data = []
    for ty in range(H // 8):
        for tx in range(W // 8):
            data += encode_tile([shades[ty * 8 + r][tx * 8:tx * 8 + 8] for r in range(8)])
    return data


def preview(shades: list[list[int]], dest: Path) -> None:
    im = Image.new("RGB", (W, H))
    im.putdata([PREVIEW_PALETTE[v] for row in shades for v in row])
    im.resize((W * 3, H * 3), Image.NEAREST).save(dest)


def display_name(path: Path) -> str:
    name = re.sub(r"[_\-]+", " ", path.stem)
    name = re.sub(r"^\d+\s*", "", name) or path.stem   # "01-beach" sorts first, shows "beach"
    name = "".join(c if 32 <= ord(c) < 127 else "?" for c in name).strip()
    return name[:NAME_LEN] or "untitled"


def name_hash(name: str) -> int:
    """16-bit FNV-1a; the save file keys print counts by it so reordering keeps them."""
    h = 0x811C9DC5
    for b in name.encode():
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    h = (h ^ (h >> 16)) & 0xFFFF
    return h or 1  # 0 marks an empty save slot


# ---------------------------------------------------------------- thumbnails

THUMB = 32   # 4x4 tiles


def thumbnail(gray: Image.Image) -> list[list[int]]:
    """160x144 grayscale -> 32x32 shades (scaled to 36x32, center-cropped), Bayer-dithered."""
    small = gray.resize((36, 32), Image.LANCZOS).crop((2, 0, 34, 32))
    small = ImageOps.autocontrast(small, cutoff=1)
    out = []
    for y in range(THUMB):
        row = []
        for x in range(THUMB):
            v = small.getpixel((x, y)) / 255.0
            level = max(0, min(3, int(v * 3 + (BAYER4[y & 3][x & 3] + 0.5) / 16)))
            row.append(3 - level)
        out.append(row)
    return out


def thumb_tiles(px: list[list[int]]) -> list[int]:
    data = []
    for ty in range(4):
        for tx in range(4):
            data += encode_tile([px[ty * 8 + r][tx * 8:tx * 8 + 8] for r in range(8)])
    return data


# ---------------------------------------------------------------- C output

def c_bytes(data: list[int], per_line: int = 16) -> str:
    lines = []
    for i in range(0, len(data), per_line):
        lines.append("    " + ",".join(f"0x{b:02X}" for b in data[i:i + per_line]) + ",")
    return "\n".join(lines)


def c_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write(path: Path, text: str, written: set) -> bool:
    written.add(path.name)
    if path.exists() and path.read_text() == text:
        return False
    path.write_text(text)
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dither", choices=["bayer", "fs", "none"], default="bayer")
    ap.add_argument("--fit", choices=["crop", "pad"], default="crop")
    ap.add_argument("--public", action="store_true", help="only images/, not images-private/")
    args = ap.parse_args()

    dirs = [IMAGES] + ([] if args.public or not PRIVATE.is_dir() else [PRIVATE])
    paths = sorted((p for d in dirs for p in d.iterdir() if p.suffix.lower() in EXTS), key=lambda p: p.name)
    if not paths:
        raise SystemExit(f"No pictures in {IMAGES}. Drop some .png/.jpg files there.")
    if len(paths) > MAX_IMAGES:
        raise SystemExit(f"{len(paths)} pictures; the gallery holds {MAX_IMAGES}.")

    shutil.rmtree(PREVIEWS, ignore_errors=True)
    GEN.mkdir(parents=True, exist_ok=True)
    PREVIEWS.mkdir(parents=True)

    names, hashes = [], []
    written: set = set()
    changed = False
    for i, path in enumerate(paths):
        if is_native(path):
            shades = native_shades(path)
            gray = Image.new("L", (W, H))
            gray.putdata([255 - v * 85 for row in shades for v in row])
        else:
            gray = load(path, args.fit)
            shades = quantize(gray, args.dither)
        name = display_name(path)
        h = name_hash(name)
        while h in hashes:  # two pictures with the same name still get separate counters
            h = (h + 1) & 0xFFFF or 1
        names.append(name)
        hashes.append(h)
        preview(shades, PREVIEWS / f"{i:03d}-{path.stem}.png")
        changed |= write(GEN / f"img_{i:03d}.c",
            f"/* {path.name} */\n#pragma bank 255\n#include <gb/gb.h>\n#include <stdint.h>\n\n"
            f"BANKREF(img_{i:03d})\n"
            f"const uint8_t img_{i:03d}[5760] = {{\n{c_bytes(to_tiles(shades))}\n}};\n"
            f"const uint8_t thumb_{i:03d}[256] = {{\n{c_bytes(thumb_tiles(thumbnail(gray)))}\n}};\n",
            written)

    n = len(paths)
    changed |= write(GEN / "assets.h", f"""/* generated by tools/convert.py, do not edit */
#ifndef ASSETS_H
#define ASSETS_H

#include <stdint.h>

#define IMAGE_COUNT {n}u
#define IMAGE_BYTES 5760u

extern const uint8_t * const image_data[];
extern const uint8_t * const image_thumb[];  /* 4x4 tiles, same bank as image_data */
extern const void * const image_bank[];   /* bank number, stored as a symbol address */
extern const char * const image_name[];
extern const uint16_t image_hash[];

#endif
""", written)
    externs = "\n".join(f"BANKREF_EXTERN(img_{i:03d})\nextern const uint8_t img_{i:03d}[], thumb_{i:03d}[];"
                        for i in range(n))
    changed |= write(GEN / "assets.c", f"""/* generated by tools/convert.py, do not edit */
#include <gb/gb.h>
#include <stdint.h>
#include "assets.h"

{externs}

const uint8_t * const image_data[] = {{ {", ".join(f"img_{i:03d}" for i in range(n))} }};
const uint8_t * const image_thumb[] = {{ {", ".join(f"thumb_{i:03d}" for i in range(n))} }};
const void * const image_bank[] = {{ {", ".join(f"&__bank_img_{i:03d}" for i in range(n))} }};
const char * const image_name[] = {{ {", ".join(c_string(s) for s in names)} }};
const uint16_t image_hash[] = {{ {", ".join(f"0x{h:04X}" for h in hashes)} }};
""", written)
    for stale in GEN.glob("img_*.c"):
        if stale.name not in written:
            stale.unlink()
            changed = True
    stamp = GEN / ".stamp"
    if changed or not stamp.exists():
        stamp.touch()
    print(f"{n} picture(s) -> {GEN.relative_to(ROOT)}, previews in {PREVIEWS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
