"""
Builds the gallery's UI tiles and writes build/gen/ui.c + ui.h
(and build/gen/ui-tiles.png / title.png contact sheets, to eyeball the art).

Tile map on the menu screens (the full-screen picture view uses all of VRAM):
      0..95   ASCII 32..127, ink on white
     96..     white-on-black capitals (header and footer bars)
    then      UI art: badges, pills, viewfinder corner, tone pips, ...
    160..255  six 4x4-tile thumbnails (one page of the grid)

The title screen borrows tiles 96.. for its logo, then they're reloaded.

Run: python3 tools/gen_ui.py   (the Makefile does this)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "build" / "gen"
FONTS = ROOT / "tools" / "fonts"
FONT = ImageFont.truetype(str(FONTS / "PixelOperatorMono8.ttf"), 8)
FONT_BOLD = ImageFont.truetype(str(FONTS / "PixelOperator8-Bold.ttf"), 8)
FONT_TITLE = ImageFont.truetype(str(FONTS / "PixelOperator-Bold.ttf"), 32)

THUMB_BASE = 160
STATUS_CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.:!-/?'"

MINI = {  # 3x5 letters for button badges
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


def mask(ch: str, font=FONT) -> list[list[int]]:
    im = Image.new("L", (8, 8), 0)
    ImageDraw.Draw(im).text((0, 0), ch, font=font, fill=255)
    return [[1 if im.getpixel((x, y)) > 127 else 0 for x in range(8)] for y in range(8)]


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
    h, w = len(px), len(px[0])
    return [[px[ty * 8 + r][tx * 8:tx * 8 + 8] for r in range(8)]
            for ty in range(h // 8) for tx in range(w // 8)]


def pill(text: str, tiles: int) -> list[list[list[int]]]:
    """Light rounded pill with dark mini letters, for the black bars."""
    w = tiles * 8
    px = [[3] * w for _ in range(8)]
    for y in range(1, 8):
        inset = 1 if y in (1, 7) else 0
        for x in range(inset, w - inset):
            px[y][x] = 1
    x0 = (w - (len(text) * 4 - 1)) // 2
    for i, ch in enumerate(text):
        for r, row in enumerate(MINI[ch]):
            for c, v in enumerate(row):
                if v == "#":
                    px[2 + r][x0 + i * 4 + c] = 3
    return split(px)


def badge(ch: str) -> list[list[int]]:
    """Light circle with a dark mini letter (A / B), on black."""
    px = [[3] * 8 for _ in range(8)]
    for y in range(1, 8):
        for x in range(8):
            if (x - 3.5) ** 2 + (y - 4) ** 2 <= 13:
                px[y][x] = 1
    for r, row in enumerate(MINI[ch]):
        for c, v in enumerate(row):
            if v == "#":
                px[2 + r][2 + c] = 3
    return px


UI = {
    "T_ICON": art("""
        ........
        .######.
        .#::::#.
        .#:##:#.
        .#####:.
        .#++++#.
        .######.
        ........"""),   # little picture frame, white-on-black bars use it inverted below
    "T_ICON_DARK": None,
    # viewfinder corner (top-left); sprites flip it for the other three corners
    "T_CORNER": art("""
        ######..
        ######..
        ##......
        ##......
        ##......
        ##......
        ........
        ........"""),
    "T_PIP_ON": art("""
        ........
        .######.
        .######.
        .######.
        .######.
        .######.
        .######.
        ........"""),
    "T_PIP_OFF": art("""
        ........
        .++++++.
        .+....+.
        .+....+.
        .+....+.
        .+....+.
        .++++++.
        ........"""),
    "T_BAR_EMPTY": art("""
        ........
        ........
        ++++++++
        ::::::::
        ::::::::
        ++++++++
        ........
        ........"""),
    "T_BAR_FULL": art("""
        ........
        ........
        ########
        ########
        ########
        ########
        ........
        ........"""),
    "T_RULE": art("""
        ........
        ........
        ........
        ........
        ++.++.++
        ........
        ........
        ........"""),
    "T_BTN_A": badge("A"),
    "T_BTN_B": badge("B"),
}
UI["T_ICON_DARK"] = [[3 - v if v in (0, 3) else v for v in row] for row in UI["T_ICON"]]
PILLS = {"T_BTN_SEL": ("SEL", 2), "T_BTN_START": ("START", 3)}


def title_tiles():
    """Title logo: a print-out curling out of a slot, over "Gallery"."""
    w, h = 16 * 8, 7 * 8
    ink = Image.new("L", (w, h), 0)
    grey = Image.new("L", (w, h), 0)
    d, g = ImageDraw.Draw(ink), ImageDraw.Draw(grey)
    cx = w // 2
    d.rectangle([cx - 16, 2, cx + 15, 7], fill=255)                 # printer slot
    g.rectangle([cx - 11, 6, cx + 10, 21], fill=255)                # paper
    d.rectangle([cx - 8, 9, cx + 7, 17], outline=255)               # little picture on it
    d.line([cx - 6, 16, cx - 2, 12, cx + 1, 15, cx + 3, 13, cx + 6, 16], fill=255)
    x0 = (w - int(FONT_TITLE.getlength("Gallery"))) // 2
    d.text((x0, 18), "Gallery", font=FONT_TITLE, fill=255)
    px = [[3 if ink.getpixel((x, y)) > 127 else 1 if grey.getpixel((x, y)) > 127 else 0
           for x in range(w)] for y in range(h)]
    return split(px), w // 8, h // 8


def sheet(tiles, cols, path):
    shade = [255, 170, 85, 0]
    rows = (len(tiles) + cols - 1) // cols
    im = Image.new("L", (cols * 8, rows * 8), 255)
    for i, t in enumerate(tiles):
        for y in range(8):
            for x in range(8):
                im.putpixel(((i % cols) * 8 + x, (i // cols) * 8 + y), shade[t[y][x]])
    im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(path)


def main() -> None:
    tiles = [[[3 if v else 0 for v in row] for row in mask(chr(c))] for c in range(32, 128)]
    status_base = len(tiles)
    tiles += [[[0 if v else 3 for v in row] for row in mask(c, FONT_BOLD)] for c in STATUS_CHARS]
    index = {}
    for name, t in UI.items():
        index[name] = len(tiles)
        tiles.append(t)
    for name, (text, n) in PILLS.items():
        index[name] = len(tiles)
        tiles += pill(text, n)
    assert len(tiles) <= THUMB_BASE, f"UI tiles run into the thumbnails ({len(tiles)})"

    status_map = [status_base + STATUS_CHARS.index(chr(c)) if chr(c) in STATUS_CHARS else status_base
                  for c in range(32, 128)]
    for c in "abcdefghijklmnopqrstuvwxyz":
        status_map[ord(c) - 32] = status_base + STATUS_CHARS.index(c.upper())
    title, tw, th = title_tiles()

    def c_bytes(data):
        return "\n".join("    " + ",".join(f"0x{b:02X}" for b in data[i:i + 16]) + ","
                         for i in range(0, len(data), 16))

    GEN.mkdir(parents=True, exist_ok=True)
    defines = "\n".join(f"#define {k} {v}u" for k, v in index.items())
    (GEN / "ui.h").write_text(f"""/* generated by tools/gen_ui.py, do not edit */
#ifndef UI_H
#define UI_H

#include <stdint.h>

#define UI_TILE_COUNT {len(tiles)}u
#define THUMB_BASE {THUMB_BASE}u
{defines}

#define TITLE_TILE_BASE 96u
#define TITLE_W {tw}u
#define TITLE_H {th}u

extern const uint8_t ui_tiles[];
extern const uint8_t status_glyph[96];   /* ASCII 32..127 -> white-on-black tile */
extern const uint8_t title_tiles[];

#endif
""")
    (GEN / "ui.c").write_text(f"""/* generated by tools/gen_ui.py, do not edit */
#include <stdint.h>
#include "ui.h"

const uint8_t ui_tiles[] = {{
{c_bytes([b for t in tiles for b in encode(t)])}
}};

const uint8_t status_glyph[96] = {{
{c_bytes(status_map)}
}};

const uint8_t title_tiles[] = {{
{c_bytes([b for t in title for b in encode(t)])}
}};
""")
    sheet(tiles, 16, GEN / "ui-tiles.png")
    sheet(title, tw, GEN / "title.png")
    print(f"{len(tiles)} UI tiles")


if __name__ == "__main__":
    main()
