"""
Headless test: boots build/gallery.gb in PyBoy with a fake Game Boy Printer
hooked onto the ROM's serial routine, walks every screen, prints a picture
and checks the printer received exactly the picture's tiles.

Screenshots and the "printed" image land in build/test/.
Run with `make test` (creates .venv with pyboy + pillow on first use).
"""
import sys
from pathlib import Path
from PIL import Image
from pyboy import PyBoy

proj = Path(__file__).resolve().parent.parent
out = proj / "build" / "test"; out.mkdir(parents=True, exist_ok=True)
rom = (proj / "build/gallery.gb").read_bytes()
# xfer(): ldh (SB),a / ld a,$81 / ldh (SC),a / .wait: ldh a,(SC) / rlca / jr c,.wait / ldh a,(SB) / ret
XFER = rom.find(bytes([0xE0, 0x01, 0x3E, 0x81, 0xE0, 0x02, 0xF0, 0x02, 0x07, 0x38, 0xFB, 0xF0, 0x01, 0xC9]))
assert 0 < XFER < 0x4000, "serial routine not found in the home bank"
LOOP, READ = XFER + 6, XFER + 13

class Printer:
    def __init__(s):
        s.buf = []; s.state = 0; s.pkt = []; s.need = None; s.busy = 0; s.prints = []; s.packets = []; s.connected = True
    def byte(s, b):
        """Byte from the Game Boy -> byte the printer shifts back."""
        if not s.connected: return 0xFF
        p = s.pkt
        if not p and b != 0x88: return 0
        p.append(b)
        if len(p) == 2 and b != 0x33: s.pkt = []; return 0
        if len(p) == 6: s.need = 6 + (p[4] | p[5] << 8) + 4
        if s.need and len(p) == s.need - 1: return 0x81
        if s.need and len(p) == s.need:
            cmd, n = p[2], p[4] | p[5] << 8
            data = p[6:6 + n]; chk = p[6 + n] | p[7 + n] << 8
            ok = chk == (sum(p[2:6 + n]) & 0xFFFF)
            s.packets.append((cmd, n, ok))
            status = 0 if ok else 1
            if cmd == 1: s.buf = []
            elif cmd == 4 and n: s.buf += data
            elif cmd == 2: s.prints.append((bytes(s.buf), data)); s.busy = 6; s.buf = []
            elif cmd == 15 and s.busy: s.busy -= 1; status |= 2
            if s.buf: status |= 8
            s.pkt = []; s.need = None
            return status
        return 0

prn = Printer(); pending = [0]
pb = PyBoy(str(proj / "build/gallery.gb"), window="null", sound_emulated=False)
def on_xfer(_): pending[0] = prn.byte(pb.register_file.A)
def on_loop(_): pb.memory[0xFF02] = pb.memory[0xFF02] & 0x7F
def on_read(_): pb.register_file.A = pending[0]  # at the ret: override what ldh a,(SB) read
pb.hook_register(0, XFER, on_xfer, None)
pb.hook_register(0, LOOP, on_loop, None)
pb.hook_register(0, READ, on_read, None)

def shot(name, frames=40):
    pb.tick(frames, True); pb.screen.image.convert("RGB").save(out / f"{name}.png")

pb.tick(240, True)                     # boot logo
shot("0-title", 1)
pb.button("start"); shot("1-grid", 60)
pb.button("right"); shot("2-grid-right", 20)
pb.button("select"); shot("3-tone", 20)
pb.button("left"); pb.tick(10); pb.button("a"); shot("4-view-testcard", 60)
pb.button("right"); shot("5-view-sunset", 60)
pb.button("start"); pb.tick(5)
for i in range(60 * 20):
    pb.tick(1, False)
    if prn.prints and not prn.busy: break
shot("6-print-done", 120)
cmds = [c for c, n, ok in prn.packets]
assert all(ok for _, _, ok in prn.packets), "bad checksum"
assert cmds[:12] == [1] + [4] * 10 + [2], cmds
assert len(prn.prints) == 1
for k, (data, args) in enumerate(prn.prints):
    assert bytes(args) == bytes([1, 0x13, 0xE4, 0x60]), bytes(args).hex()  # tone was set to DARK
    first = rom.find(data[:640])
    assert first >= 0 and rom[first:first + 5760] == data, "printed data differs from the ROM picture"
    im = Image.new("L", (160, len(data) // 640 * 16))
    px = im.load()
    for t in range(len(data) // 16):
        tx, ty = t % 20, t // 20
        for r in range(8):
            lo, hi = data[t * 16 + r * 2], data[t * 16 + r * 2 + 1]
            for c in range(8):
                v = ((lo >> (7 - c)) & 1) | (((hi >> (7 - c)) & 1) << 1)
                px[tx * 8 + c, ty * 8 + r] = 255 - v * 85
    im.save(out / f"printed-{k}.png")
pb.button("a"); shot("7-back-to-view", 60)
pb.button("b"); shot("8-grid-after", 60)
prn.connected = False
pb.button("start"); pb.tick(5)
shot("9-no-printer", 200)
pb.stop(save=False)
print(f"ok: {len(cmds)} packets, picture printed byte-exact; screenshots in {out.relative_to(proj)}")
