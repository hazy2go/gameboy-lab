# GB Gallery

A Game Boy ROM that holds a gallery of pictures and prints them on the
**Game Boy Printer**. It runs on a DMG/Pocket/Color with an EverDrive. Print counts
and the tone setting are saved to cart SRAM, which the EverDrive keeps in FRAM.

## Use it

1. Put pictures in `images/` (png/jpg/gif/webp…), or in `images-private/` for ones
   that shouldn't go public: that folder is git-ignored and skipped by `make PUBLIC=1`. They're sorted by filename,
   and a leading number is dropped from the shown name: `01-beach.jpg` shows as `beach`.
2. `make`, then copy `build/gallery.gb` to the EverDrive SD card.
3. Check `build/previews/` first: those are exactly the pixels the Game Boy will show and print.

| Screen | Controls |
|---|---|
| Title | **START** |
| Grid (6 thumbnails a page) | D-pad pick, **A** view, **START** print, **SELECT** cycle print tone |
| View | ←→ previous/next picture, **A**/**START** print, **B** back |
| Print | **B** cancel while sending, then **A** back / **START** print again |

Print tone is the printer's exposure (lightest → darkest), saved with your print counts.

## Picture conversion

Every picture becomes 160×144 in 4 greys:

- `make DITHER=fs`: error-diffusion dithering. The default `bayer` is the ordered
  crosshatch the Game Boy Camera uses, and it tends to print cleanest.
- `make FIT=pad`: letterbox on white instead of center-cropping.
- A 160×144 picture that already uses ≤4 greys is kept pixel-exact (good for pixel art).

## How it works

- **360 tiles on a 256-tile background.** A full-screen picture needs 360 unique
  tiles. The tiles are copied linearly to `0x8000`, and an LY=71 interrupt flips LCDC
  bit 4 so the bottom half reads the `0x8800` window (`src/main.c`).
- **Printer protocol** (`src/printer.c`): INIT → 9 × DATA (640 bytes = 2 tile rows)
  → empty DATA → PRINT (margins, palette, exposure) → STATUS polls until idle.
  It streams straight from banked ROM, so nothing is buffered in RAM.
- **Menus** share one tile set (`tools/gen_ui.py`): font, black header/footer
  bars, button badges, and six 4×4-tile thumbnail slots that are reloaded per page.
  The selection is four sprites (one corner tile, flipped) that breathe in and out.
- **Banking:** each picture is its own `#pragma bank 255` file and bankpack fits
  two per 16 KB bank. The cart is MBC5+RAM+battery, sized automatically.
- **Save:** print counts are keyed by a hash of the picture name, so adding or
  reordering pictures keeps the history.

## Test without hardware

`make test` boots the ROM in PyBoy and hooks a fake printer onto the serial
routine. It walks every screen, prints, and checks that the printer received the
picture byte-for-byte. Screenshots go to `build/test/`.

Needs GBDK-2020 at `~/gbdk` (override with `make GBDK=...`) and Python 3 with Pillow.
