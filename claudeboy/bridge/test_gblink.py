"""The bridge over the gb-link-usb firmware, without hardware: a pseudo-terminal plays the Pico. It must receive the
bridge-mode magic first, then the Game Boy side (hello, idle 0x00 bytes, a typed prompt) gets the canned reply.
    .venv/bin/python bridge/test_gblink.py"""
import os
import sys
import faulthandler; faulthandler.dump_traceback_later(25, exit=True)
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bridge as B  # noqa: E402

master, slave = os.openpty()
os.set_blocking(master, False)
link = B.SerialLink(B.Bridge(B.FakeChat(), log=lambda *a: None), os.ttyname(slave), "gblink")
threading.Thread(target=link.run, daemon=True).start()

def read_all(t):
    got, end = bytearray(), time.time() + t
    while time.time() < end:
        try:
            got += os.read(master, 4096)
        except BlockingIOError:
            time.sleep(0.01)
    return bytes(got)

first = read_all(0.5)
assert first.startswith(B.SerialLink.GBLINK_MAGIC), f"no bridge magic first: {first[:16]!r}"
print("magic ok; then", first[len(B.SerialLink.GBLINK_MAGIC):][:4])
os.write(master, bytes([0, 0, B.GB_HELLO, 0, 0, B.GB_BEGIN]) + b"tell me a joke" + bytes([B.GB_END, 0, 0]))
out = read_all(3.0)
assert bytes([B.MAC_USER]) in out and bytes([B.MAC_THINKING]) in out, "no bubble/thinking"
assert out.rstrip(b"\0").endswith(bytes([B.MAC_READY])), "reply did not end with READY"
text = bytes(b for b in out if 32 <= b < 127).decode()
print("reply bytes:", len(out), "| text:", text[:120])
print("PASS")
