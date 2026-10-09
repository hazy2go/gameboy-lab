"""
Headless end-to-end test (make test): the real ROM in PyBoy, the real bridge
protocol and text wrapping, canned Claude replies, and a fake printer.

Walks: boot -> quick-prompt menu -> typed message -> stop -> print -> new chat
-> reboot with the same cart RAM (chat log must survive). Screenshots land in
build/test/.
"""

import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bridge as br  # noqa: E402

OUT = br.ROOT / "build" / "test"
OUT.mkdir(parents=True, exist_ok=True)

logs = []
b = br.Bridge(br.FakeChat(), log=logs.append)
ram = io.BytesIO(bytes(8192))
emu = br.Emulator(b, window="null", ram_file=ram)
pb = emu.pb


def tick(n=1):
    for _ in range(n):
        pb.tick(1, True)


def press(button, settle=8):
    pb.button(button)
    tick(settle)


def wait_idle(timeout=10):
    """Run frames until the bridge has finished replying and sent everything."""
    end = time.time() + timeout
    while time.time() < end:
        tick(4)
        if not b.busy and not b.out:
            tick(30)
            return
    raise AssertionError("bridge never went idle")


def shot(name):
    pb.screen.image.convert("RGB").save(OUT / f"{name}.png")


def screen_text():
    """Reads the visible chat back out of VRAM (BG map rows from SCY)."""
    scy = pb.memory[0xFF42] // 8
    rows = []
    for r in range(17):
        row = ""
        for x in range(20):
            t = pb.memory[0x9800 + ((scy + r) & 31) * 32 + x]
            row += chr((t % 96) + 32) if t < 192 else "#"
        rows.append(row)
    return "\n".join(rows)


def cell(t):
    if t < 96:
        return chr(t + 32)             # plain text
    if t < 192:
        return chr(t - 64)             # grey text (your bubbles)
    return "#"                         # art


def log_text():
    """Reads the chat log (tile numbers) straight out of cart RAM."""
    count = pb.memory[0xA004] | pb.memory[0xA005] << 8
    return ["".join(cell(pb.memory[0xA010 + (n % 400) * 20 + x]) for x in range(20)) for n in range(count)]


tick(240)
shot("0-title")
press("start", 30)
tick(240)
shot("1-boot")
assert any("Hi! I'm Claude." in l for l in log_text()), log_text()

# quick prompt from the menu
press("select")
shot("2-menu")
press("a")
wait_idle()
shot("3-joke")
assert logs[-1] == "> Tell me a joke", logs
assert any("stand-in" in l for l in log_text()), log_text()

# type "hi" on the keyboard: h is row 0 col 7, i is col 8
press("a")
for _ in range(7):
    press("right", 3)
press("a", 3)
press("right", 3)
press("a", 3)
shot("4-typing")
press("start")
wait_idle()
shot("5-reply")
assert logs[-1] == "> hi", logs
lines = log_text()
assert any(l.strip() == "#hi#" for l in lines), lines        # inside a bubble

# print the last exchange (the fake printer stands in for a cable swap)
press("start")
shot("6-print-prompt")
press("a", 10)
for _ in range(60 * 30):
    tick(1)
    if getattr(emu.printer, "last", None):
        break
tick(30)
shot("7-printed")
assert getattr(emu.printer, "last", None), "nothing printed"
press("a")
wait_idle()

# new chat clears the log
press("select")
for _ in range(7):
    press("down", 3)
press("a")
wait_idle()
assert logs[-1] == "[new chat]", logs
assert any("Hi! I'm Claude." in l for l in log_text()) and not any("stand-in" in l for l in log_text()), log_text()

# the log survives a power cycle
press("select")
press("down", 3)          # menu remembers "New chat"; wrap around to "Tell me a joke"
press("a")
wait_idle()
before = log_text()
assert any("stand-in" in l for l in before), before
ram.seek(0)               # PyBoy writes cart RAM at the file position
pb.stop(save=True, ram_file=ram)
ram.seek(0)
emu2 = br.Emulator(br.Bridge(br.FakeChat(), log=logs.append), window="null", ram_file=ram)
pb = emu2.pb
tick(240)
press("start", 30)
tick(240)
shot("8-after-reboot")
assert log_text() == before, "chat log lost across reboot"
pb.stop(save=False)

print(f"ok: menu prompt, typed prompt, print ({emu.printer.last.name}), new chat, reboot; "
      f"screenshots in {OUT.relative_to(br.ROOT)}")
