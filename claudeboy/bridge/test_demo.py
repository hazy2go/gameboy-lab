"""
Headless test of the demo ROM (make test): no bridge at all, only the fake
printer on the cable. Checks quick prompts, follow-ups, keyword replies,
the fallback, and printing.
"""

import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import bridge as br  # noqa: E402
from demo_replies import REPLIES  # noqa: E402

OUT = br.ROOT / "build" / "test"
OUT.mkdir(parents=True, exist_ok=True)

emu = br.Emulator(None, window="null", rom=br.ROOT / "build" / "claudeboy-demo.gb",
                  ram_file=io.BytesIO(bytes(8192)))
pb = emu.pb


def tick(n=1):
    pb.tick(n, True)


def press(button, settle=8):
    pb.button(button)
    tick(settle)


def cell(t):
    return chr(t + 32) if t < 96 else chr(t - 64) if t < 192 else "#"


def log_lines():
    count = pb.memory[0xA004] | pb.memory[0xA005] << 8
    return ["".join(cell(pb.memory[0xA010 + (n % 400) * 20 + x]) for x in range(20)) for n in range(count)]


def log_words():
    return " ".join(" ".join(log_lines()).split())


def first_words(text, n=4):
    return " ".join(text.split()[:n])


def text_of(r, key="text"):
    return (r if isinstance(r, str) else r[key])


def wait_reply():
    """The demo is done when the status bar shows the A hint again."""
    tick(30)
    for _ in range(60 * 20):
        tick(4)
        if not busy():
            tick(20)
            return
    raise AssertionError("reply never finished")


def busy():
    # the status bar shows the (B) STOP hint while a reply is running
    return any(pb.memory[0x9C00 + x] == br.TILES["T_BTN_B"] for x in range(20))


menu_at = [0]                    # the ROM remembers the last menu item


def menu(index):
    press("select")
    while menu_at[0] != index:
        press("down", 3)
        menu_at[0] = (menu_at[0] + 1) % 8
    press("a")
    wait_reply()


kb_at = [0, 0]                   # the ROM remembers the keyboard cursor too


def type_text(text):
    rows = ["abcdefghij", "klmnopqrst", "uvwxyz.,?!", "'-:;()&@# "]
    press("a")
    r, c = kb_at
    for ch in text:
        tr = next(i for i, row in enumerate(rows) if ch in row)
        tc = rows[tr].index(ch)
        while r != tr:
            press("down", 3)
            r = (r + 1) % 4
        while c != tc:
            press("right", 3)
            c = (c + 1) % 10
        press("a", 3)
    kb_at[:] = [r, c]
    press("start")
    wait_reply()


tick(240)
press("start", 30)
tick(30)
pb.screen.image.convert("RGB").save(OUT / "demo-0-start.png")

menu(0)                                                    # Tell me a joke
joke = REPLIES["joke"][0]
assert first_words(text_of(joke)) in log_words(), log_lines()
menu(3)                                                    # Explain simpler
assert first_words(text_of(joke, "simpler")) in log_words(), log_lines()
menu(4)                                                    # Keep going
assert first_words(text_of(joke, "more")) in log_words(), log_lines()
menu(1)                                                    # Write a haiku
assert first_words(text_of(REPLIES["haiku"][0]), 3) in log_words(), log_lines()
pb.screen.image.convert("RGB").save(OUT / "demo-1-haiku.png")

type_text("hello")
assert first_words(text_of(REPLIES["greeting"][0])) in log_words(), log_lines()
type_text("why is the sky")
assert first_words(text_of(REPLIES["fallback"][0])) in log_words(), log_lines()
pb.screen.image.convert("RGB").save(OUT / "demo-2-fallback.png")

press("start")                                            # print the last exchange
press("a", 10)
for _ in range(60 * 30):
    tick(1)
    if getattr(emu.printer, "last", None):
        break
assert getattr(emu.printer, "last", None), "demo didn't print"
tick(30)
press("a")
pb.stop(save=False)
print(f"ok: demo quick prompts, follow-ups, keywords, fallback, print ({emu.printer.last.name})")
