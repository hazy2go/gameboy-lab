"""
Builds every tile the ROM uses and writes:
    build/gen/font.c, font.h   tile data + indices for the ROM
    build/gen/tiles.json       the same indices for the Mac bridge (it lays out
                               chat bubbles itself and sends raw tile numbers)
    build/gen/tiles.png        a contact sheet, to eyeball the art

Shades: 0 white, 1 light grey, 2 dark grey, 3 black.

Tile map (BG, window and sprites all read 0x8000):
      0..95   ASCII 32..127, ink on white       Claude's text, keyboard, menus
     96..191  ASCII 32..127, ink on light grey  your messages, selections
    192..     white-on-black capitals           status bar
    then      UI art: bubble frame, spark, button badges, ...

The title screen borrows tiles 96.. for its big logo, then the font is reloaded.

Run: python3 tools/gen_font.py   (the Makefile does this)
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "build" / "gen"
FONTS = ROOT / "tools" / "fonts"
FONT = ImageFont.truetype(str(FONTS / "PixelOperatorMono8.ttf"), 8)
FONT_BOLD = ImageFont.truetype(str(FONTS / "PixelOperator8-Bold.ttf"), 8)
FONT_TITLE = ImageFont.truetype(str(FONTS / "PixelOperator-Bold.ttf"), 32)

STATUS_CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.:!-/?'"

# 3x5 letters for the button badges
MINI = {
    "A": ["###", "#.#", "###", "#.#", "#.#"],
    "B": ["##.", "#.#", "##.", "#.#", "##."],
    "S": [".##", "#..", ".#.", "..#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"],
    "L": ["#..", "#..", "#..", "#..", "###"],
    "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "R": ["##.", "#.#", "##.", "#.#", "#.#"],
}


def art(s: str) -> list[list[int]]:
    m = {".": 0, ":": 1, "+": 2, "#": 3}
    return [[m[c] for c in r.strip()] for r in s.strip("\n").split("\n")]


def mask(ch: str, font=FONT, size=(8, 8), offset=(0, 0)) -> list[list[int]]:
    im = Image.new("L", size, 0)
    ImageDraw.Draw(im).text(offset, ch, font=font, fill=255)
    return [[1 if im.getpixel((x, y)) > 127 else 0 for x in range(size[0])] for y in range(size[1])]


def encode(rows: list[list[int]]) -> list[int]:
    data = []
    for row in rows:
        lo = hi = 0
        for x, v in enumerate(row):
            lo |= (v & 1) << (7 - x)
            hi |= ((v >> 1) & 1) << (7 - x)
        data += [lo, hi]
    return data


def split(px: list[list[int]]) -> list[list[list[int]]]:
    """A picture whose sides are multiples of 8 -> its tiles, row-major."""
    h, w = len(px), len(px[0])
    return [[px[ty * 8 + r][tx * 8:tx * 8 + 8] for r in range(8)]
            for ty in range(h // 8) for tx in range(w // 8)]


def pill(text: str, tiles: int) -> list[list[list[int]]]:
    """A light rounded pill with dark mini letters, for the black status bar."""
    w = tiles * 8
    px = [[3] * w for _ in range(8)]
    for y in range(1, 8):
        for x in range(w):
            inset = 1 if y in (1, 7) else 0
            if inset <= x < w - inset and y < 8:
                px[y][x] = 1
    tw = len(text) * 4 - 1
    x0 = (w - tw) // 2
    for i, ch in enumerate(text):
        for r, row in enumerate(MINI[ch]):
            for c, v in enumerate(row):
                if v == "#":
                    px[2 + r][x0 + i * 4 + c] = 3
    return split(px)


def badge(ch: str) -> list[list[int]]:
    """A light circle with a dark mini letter (A / B buttons), on black."""
    px = [[3] * 8 for _ in range(8)]
    for y in range(8):
        for x in range(8):
            if (x - 3.5) ** 2 + (y - 4) ** 2 <= 13:
                px[y][x] = 1
    for r, row in enumerate(MINI[ch]):
        for c, v in enumerate(row):
            if v == "#":
                px[2 + r][2 + c] = 3
    px[0] = [3] * 8
    return px


UI = {
    # speech bubble around your messages (light grey, dark outline, tail bottom-right)
    "T_BUB_TL": art("""
        ........
        ........
        ........
        ....++++
        ...+::::
        ..+:::::
        ..+:::::
        ..+:::::"""),
    "T_BUB_T": art("""
        ........
        ........
        ........
        ++++++++
        ::::::::
        ::::::::
        ::::::::
        ::::::::"""),
    "T_BUB_TR": art("""
        ........
        ........
        ........
        ++++....
        ::::+...
        :::::+..
        :::::+..
        :::::+.."""),
    "T_BUB_L": art("""
        ..+:::::
        ..+:::::
        ..+:::::
        ..+:::::
        ..+:::::
        ..+:::::
        ..+:::::
        ..+:::::"""),
    "T_BUB_R": art("""
        :::::+..
        :::::+..
        :::::+..
        :::::+..
        :::::+..
        :::::+..
        :::::+..
        :::::+.."""),
    "T_BUB_BL": art("""
        ..+:::::
        ..+:::::
        ...+::::
        ....++++
        ........
        ........
        ........
        ........"""),
    "T_BUB_B": art("""
        ::::::::
        ::::::::
        ::::::::
        ++++++++
        ........
        ........
        ........
        ........"""),
    "T_BUB_BR": art("""
        :::::+..
        ::::::+.
        :::::::+
        +++++++.
        ........
        ........
        ........
        ........"""),
    # Claude's marker, on white and on the black status bar
    "T_SPARK": art("""
        ....#...
        .#..#..#
        ..#.#.#.
        ...###..
        ####+###
        ...###..
        ..#.#.#.
        .#..#..#"""),
    "T_SPARK_DARK": art("""
        ####.###
        #.##.##.
        ##.#.#.#
        ###...##
        ....:...
        ###...##
        ##.#.#.#
        #.##.##."""),
    "T_RULE": art("""
        ........
        ........
        ........
        ........
        ++.++.++
        ........
        ........
        ........"""),
    "T_SPACE_KEY": art("""
        ........
        ........
        ........
        ........
        #......#
        #......#
        ########
        ........"""),
    # sprite drawn behind a keyboard glyph's ink: a rounded light key
    "T_KEY": art("""
        .::::::.
        ::::::::
        ::::::::
        ::::::::
        ::::::::
        ::::::::
        ::::::::
        .::::::."""),
    "T_BTN_A": badge("A"),
    "T_BTN_B": badge("B"),
}
PILLS = {"T_BTN_SEL": ("SEL", 2), "T_BTN_START": ("START", 3)}


def title_tiles() -> tuple[list[list[list[int]]], int, int]:
    """Title logo: a big spark over "ClaudeBoy" ("Boy" in dark grey), as a tile block."""
    w, h = 18 * 8, 7 * 8
    ink = Image.new("L", (w, h), 0)      # 255 = black
    grey = Image.new("L", (w, h), 0)     # 255 = dark grey
    d = ImageDraw.Draw(ink)
    cx, cy = w // 2, 12
    for dx, dy in ((0, 11), (11, 0), (8, 8), (8, -8)):
        d.line([cx - dx, cy - dy, cx + dx, cy + dy], fill=255, width=3)
    d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=255)
    x0 = (w - int(FONT_TITLE.getlength("ClaudeBoy"))) // 2
    d.text((x0, 20), "Claude", font=FONT_TITLE, fill=255)
    ImageDraw.Draw(grey).text((x0 + int(FONT_TITLE.getlength("Claude")), 20), "Boy", font=FONT_TITLE, fill=255)
    px = [[3 if ink.getpixel((x, y)) > 127 else 2 if grey.getpixel((x, y)) > 127 else 0
           for x in range(w)] for y in range(h)]
    return split(px), w // 8, h // 8


def main() -> None:
    tiles: list[list[list[int]]] = []
    glyphs = [mask(chr(c)) for c in range(32, 128)]
    tiles += [[[3 if v else 0 for v in row] for row in g] for g in glyphs]
    tiles += [[[3 if v else 1 for v in row] for row in g] for g in glyphs]
    status_base = len(tiles)
    tiles += [[[0 if v else 3 for v in row] for row in mask(c, FONT_BOLD)] for c in STATUS_CHARS]
    index = {}
    for name, t in UI.items():
        index[name] = len(tiles)
        tiles.append(t)
    for name, (text, n) in PILLS.items():
        index[name] = len(tiles)
        tiles += pill(text, n)
    assert len(tiles) <= 256, f"{len(tiles)} tiles, only 256 fit"

    title, tw, th = title_tiles()
    status_map = [status_base + STATUS_CHARS.index(chr(c)) if chr(c) in STATUS_CHARS else status_base
                  for c in range(32, 128)]
    for c in "abcdefghijklmnopqrstuvwxyz":            # lowercase shows as capitals
        status_map[ord(c) - 32] = status_base + STATUS_CHARS.index(c.upper())

    GEN.mkdir(parents=True, exist_ok=True)
    defines = "\n".join(f"#define {k} {v}u" for k, v in index.items())
    (GEN / "font.h").write_text(f"""/* generated by tools/gen_font.py, do not edit */
#ifndef FONT_H
#define FONT_H

#include <stdint.h>

#define FONT_TILE_COUNT {len(tiles)}u
#define T_GREY 96u          /* add to a character tile for the grey-background version */
{defines}

#define TITLE_TILE_BASE 96u
#define TITLE_W {tw}u
#define TITLE_H {th}u

extern const uint8_t font_tiles[];
extern const uint8_t status_glyph[96];  /* ASCII 32..127 -> white-on-black tile */
extern const uint8_t title_tiles[];

#endif
""")

    def c_bytes(data):
        return "\n".join("    " + ",".join(f"0x{b:02X}" for b in data[i:i + 16]) + ","
                         for i in range(0, len(data), 16))

    font_data = [b for t in tiles for b in encode(t)]
    title_data = [b for t in title for b in encode(t)]
    (GEN / "font.c").write_text(f"""/* generated by tools/gen_font.py, do not edit */
#include <stdint.h>
#include "font.h"

const uint8_t font_tiles[] = {{
{c_bytes(font_data)}
}};

const uint8_t status_glyph[96] = {{
{c_bytes(status_map)}
}};

const uint8_t title_tiles[] = {{
{c_bytes(title_data)}
}};
""")
    (GEN / "tiles.json").write_text(json.dumps({"grey": 96, **index}, indent=1))

    # contact sheet, 16 tiles a row, 3x
    rows = (len(tiles) + 15) // 16
    sheet = Image.new("L", (16 * 9, rows * 9), 128)
    shade = [255, 170, 85, 0]
    for i, t in enumerate(tiles):
        for y in range(8):
            for x in range(8):
                sheet.putpixel(((i % 16) * 9 + x, (i // 16) * 9 + y), shade[t[y][x]])
    sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST).save(GEN / "tiles.png")
    tsheet = Image.new("L", (tw * 8, th * 8))
    for i, t in enumerate(title):
        for y in range(8):
            for x in range(8):
                tsheet.putpixel(((i % tw) * 8 + x, (i // tw) * 8 + y), shade[t[y][x]])
    tsheet.resize((tsheet.width * 3, tsheet.height * 3), Image.NEAREST).save(GEN / "title.png")
    print(f"{len(tiles)} tiles")


if __name__ == "__main__":
    main()
