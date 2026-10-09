"""
Captures the README visuals from the real ROMs (headless PyBoy), recoloured
to the original Game Boy's green palette:

    docs/media/claudeboy.gif         the demo ROM answering a quick prompt
    docs/media/*.png                 screenshots, 3x
    docs/media/banner.png            the strip at the top of the README

Run from the repo root with the claudeboy venv:
    claudeboy/.venv/bin/python scripts/make_media.py
(build first: make -C claudeboy demo && make -C gallery-printer PUBLIC=1)
"""

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "docs" / "media"
MEDIA.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "claudeboy" / "bridge"))
import bridge as br  # noqa: E402

GREEN = [(224, 248, 208), (136, 192, 112), (52, 104, 86), (8, 24, 32)]
SCALE = 3


def green(im: Image.Image, scale=SCALE) -> Image.Image:
    g = im.convert("L")
    levels = sorted(set(g.getdata()), reverse=True)
    lut = {v: GREEN[min(3, round(i * 3 / max(1, len(levels) - 1)))] if len(levels) < 4 else
           GREEN[[255, 170, 85, 0].index(min([255, 170, 85, 0], key=lambda s: abs(s - v)))]
           for i, v in enumerate(levels)}
    out = Image.new("RGB", g.size)
    out.putdata([lut[v] for v in g.getdata()])
    return out.resize((g.width * scale, g.height * scale), Image.NEAREST)


def boot(rom: Path, bridge=None):
    emu = br.Emulator(bridge, window="null", rom=rom, ram_file=io.BytesIO(bytes(8192)))
    emu.pb.tick(240, False)
    return emu


def frame(pb) -> Image.Image:
    return pb.screen.image.copy()


# ---- ClaudeBoy demo: title -> ideas -> joke streaming in
emu = boot(ROOT / "claudeboy" / "build" / "claudeboy-demo.gb")
pb = emu.pb
frames, durations = [], []


def grab(n, every=3):
    for i in range(n):
        pb.tick(1, True)
        if i % every == 0:
            frames.append(green(frame(pb), 2))
            durations.append(every * 1000 // 60)


grab(150)                                  # title, PRESS START blinking
green(frame(pb)).save(MEDIA / "claudeboy-title.png")
pb.button("start"); grab(60)
green(frame(pb)).save(MEDIA / "claudeboy-welcome.png")
pb.button("select"); grab(45)
green(frame(pb)).save(MEDIA / "claudeboy-ideas.png")
pb.button("a"); grab(330)                  # bubble, thinking dots, reply streams in
pb.button("select"); grab(20)
for _ in range(3):
    pb.button("down"); grab(10)
pb.button("a"); grab(300)                  # "Explain simpler" follow-up
green(frame(pb)).save(MEDIA / "claudeboy-chat.png")
pb.button("a"); grab(20)
for ch, moves in (("h", 7), ("i", 1)):
    for _ in range(moves):
        pb.button("right"); grab(6)
    pb.button("a"); grab(10)
green(frame(pb)).save(MEDIA / "claudeboy-keyboard.png")
pb.button("start"); grab(240)
frames[0].save(MEDIA / "claudeboy.gif", save_all=True, append_images=frames[1:],
               duration=durations, loop=0, optimize=True)
pb.stop(save=False)

# ---- Gallery: title, grid, print screen (fake printer)
emu = boot(ROOT / "gallery-printer" / "build" / "gallery.gb", bridge=None)
pb = emu.pb
pb.tick(30, True)
green(frame(pb)).save(MEDIA / "gallery-title.png")
pb.button("start"); pb.tick(60, True)
pb.button("right"); pb.tick(40, True)
green(frame(pb)).save(MEDIA / "gallery-grid.png")
pb.button("a"); pb.tick(60, True)
green(frame(pb)).save(MEDIA / "gallery-view.png")
pb.button("start"); pb.tick(5, True)
for _ in range(60 * 20):
    pb.tick(1, False)
    if getattr(emu.printer, "last", None):
        break
pb.tick(90, True)
green(frame(pb)).save(MEDIA / "gallery-print.png")
pb.stop(save=False)

# ---- banner: four screens on a dark strip
shots = ["claudeboy-title", "claudeboy-chat", "gallery-grid", "gallery-print"]
w, h, pad = 160 * 2, 144 * 2, 28
banner = Image.new("RGB", (pad + len(shots) * (w + pad), h + 2 * pad), (24, 28, 32))
d = ImageDraw.Draw(banner)
for i, name in enumerate(shots):
    im = Image.open(MEDIA / f"{name}.png").resize((w, h), Image.NEAREST)
    x = pad + i * (w + pad)
    d.rounded_rectangle([x - 8, pad - 8, x + w + 8, pad + h + 8], radius=10, fill=(150, 152, 160))
    banner.paste(im, (x, pad))
banner.save(MEDIA / "banner.png")
print("media written to", MEDIA.relative_to(ROOT))
