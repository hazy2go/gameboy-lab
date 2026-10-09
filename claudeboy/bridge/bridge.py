"""
The Mac side of ClaudeBoy (Claude on a Game Boy).

The Game Boy is a dumb terminal on the far end of a byte stream (see
src/link.h for the protocol). This script owns everything smart: the
conversation history, the Claude API call, and turning Claude's markdown
into plain ASCII wrapped to the Game Boy's 20 columns.

Two ways to reach the Game Boy:
    emu      PyBoy runs build/claudeboy.gb in a window; the link port is hooked
             straight into this script (and a fake printer, for prints).
    serial   a Raspberry Pi Pico on the link cable shows up as a USB serial
             port and passes bytes both ways (pico/main.py).

    python bridge/bridge.py emu [--engine subscription|api|fake]
    python bridge/bridge.py serial [--port /dev/cu.usbmodem1101] [--engine ...]

Engines:
    subscription  (default) replies come from Claude Code (`claude -p`), so they
                  run on the Claude subscription you're logged into on this Mac
    api           the Anthropic API with ANTHROPIC_API_KEY (billed per token)
    fake          canned replies, for trying things out offline
"""

import argparse
import collections
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROM = ROOT / "build" / "claudeboy.gb"

COLS = 20
MODEL = "claude-opus-5-5"

# Game Boy -> Mac
GB_BEGIN, GB_END, GB_NEW, GB_STOP, GB_HELLO = 0x01, 0x04, 0x05, 0x06, 0x07
# Mac -> Game Boy
MAC_NL, MAC_USER, MAC_TILE, MAC_THINKING, MAC_READY, MAC_CLEAR = 0x0A, 0x11, 0x1B, 0x14, 0x15, 0x18

# tile numbers for bubble art etc., shared with the ROM (written by tools/gen_font.py)
TILES = json.loads((ROOT / "build" / "gen" / "tiles.json").read_text())
CLAUDE_INDENT = 2        # Claude's text starts after the spark: 18 columns
BUBBLE_TEXT = 14         # widest line inside one of your bubbles

SYSTEM = """You are Claude, chatting with someone through an original Game Boy.
Their screen is 20 characters wide and 17 lines tall, and they type with a
D-pad on an on-screen keyboard, so their messages are short.

- Reply in plain text only: no markdown, no emoji, no tables, no code blocks.
  Only basic ASCII characters can be shown.
- Keep replies short, usually 2 to 5 sentences, unless they ask for more.
- For lists, put each item on its own line starting with "- ".
- Your text wraps at 18 characters, so keep lines of poems and lists
  under 18 characters when you can.
- They may ask you to keep going or to explain something more simply;
  that refers to your previous reply.
- Every reply can be printed on a Game Boy Printer as a little paper strip,
  so it's nice when a reply stands on its own."""


# ---------------------------------------------------------------- text shaping

ASCII_SWAPS = {
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
    "…": "...", "•": "-", "×": "x", "→": "->", "←": "<-", " ": " ",
    "\t": " ",
}


def to_ascii(text: str) -> str:
    text = "".join(ASCII_SWAPS.get(c, c) for c in text)
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if c == "\n" or 32 <= ord(c) < 127)


class Wrapper:
    """Streams text in, Game Boy bytes out: ASCII only, markdown stripped,
    word-wrapped to `width` columns after an `indent`, at most one blank line
    in a row. `indented=True` means the first line's indent was already sent
    (Claude's spark)."""

    def __init__(self, emit, width=COLS, indent=0, indented=False):
        self.emit = emit          # callable(bytes)
        self.width = width
        self.indent = indent
        self.indented = indented
        self.col = 0
        self.word = ""
        self.blank_lines = 0
        self.line_start = True

    def feed(self, text: str) -> None:
        for c in to_ascii(text):
            if c == "\n":
                self._flush_word()
                self._newline()
            elif c == " ":
                self._flush_word()
            else:
                self.word += c

    def finish(self) -> None:
        self._flush_word()
        if self.col:
            self._newline()

    def _newline(self) -> None:
        if self.col == 0:
            self.blank_lines += 1
            if self.blank_lines > 1 or self.line_start:
                return
        else:
            self.blank_lines = 0
        self.emit(bytes([MAC_NL]))
        self.col = 0
        self.indented = False

    def _clean(self, word: str) -> str:
        if self.col == 0 and re.fullmatch(r"#+", word):
            return ""                                   # markdown heading marker
        if self.col == 0 and word in ("*", "+"):
            return "-"                                  # bullet
        if self.col == 0 and re.fullmatch(r"\d+\)", word):
            return word[:-1] + "."
        return word.replace("**", "").replace("__", "").replace("`", "").replace("*", "")

    def _flush_word(self) -> None:
        word, self.word = self._clean(self.word), ""
        width = self.width
        while word:
            # wrap, unless the word can't fit on any line anyway: then fill this one
            if self.col and self.col + 1 + len(word) > width and (len(word) <= width or self.col + 2 > width):
                self.emit(bytes([MAC_NL]))
                self.col = 0
                self.indented = False
            if self.col == 0 and not self.indented:
                self.emit(b" " * self.indent)
                self.indented = True
            if self.col:
                self.emit(b" ")
                self.col += 1
            chunk, word = word[:width - self.col], word[width - self.col:]
            self.emit(chunk.encode())
            self.col += len(chunk)
            self.line_start = False
            self.blank_lines = 0


def tile(t: int) -> bytes:
    assert 0 < t < 0xFF, t       # 0x00 means "nothing", 0xFF means "no cable"
    return bytes([MAC_TILE, t])


def grey(text: str) -> bytes:
    return b"".join(tile(TILES["grey"] + ord(c) - 32) for c in text)


def wrap_lines(text: str, width: int) -> list[str]:
    buf = bytearray()
    w = Wrapper(buf.extend, width)
    w.feed(text)
    w.finish()
    return [line for line in buf.decode().split("\n") if line.strip()] or [""]


def bubble(text: str) -> bytes:
    """Your message as a right-aligned speech bubble, in tiles."""
    lines = wrap_lines(text, BUBBLE_TEXT)
    w = max(len(line) for line in lines)
    pad = b" " * (COLS - w - 2)
    nl = bytes([MAC_NL])
    out = pad + tile(TILES["T_BUB_TL"]) + tile(TILES["T_BUB_T"]) * w + tile(TILES["T_BUB_TR"]) + nl
    for line in lines:
        out += pad + tile(TILES["T_BUB_L"]) + grey(line.ljust(w)) + tile(TILES["T_BUB_R"]) + nl
    out += pad + tile(TILES["T_BUB_BL"]) + tile(TILES["T_BUB_B"]) * w + tile(TILES["T_BUB_BR"]) + nl
    return out


# ---------------------------------------------------------------- Claude

class ClaudeChat:
    def __init__(self):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.history = []

    def reset(self):
        self.history = []

    def reply(self, prompt: str, on_text, cancelled) -> str:
        """Streams a reply through on_text. Returns "" or an error to show."""
        an = self.anthropic
        self.history.append({"role": "user", "content": prompt})
        parts = []
        try:
            with self.client.beta.messages.stream(
                model=MODEL,
                max_tokens=4000,
                system=SYSTEM,
                messages=self.history,
                output_config={"effort": "low"},   # chat: fast first words
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",               # on a refusal, retry on a fallback model
            ) as stream:
                for text in stream.text_stream:
                    if cancelled():
                        break
                    parts.append(text)
                    on_text(text)
                if cancelled():
                    self.history.append({"role": "assistant", "content": "".join(parts) or "(stopped)"})
                    return ""
                message = stream.get_final_message()
        except an.AuthenticationError:
            self.history.pop()
            return "API key problem. Check ANTHROPIC_API_KEY on the Mac."
        except an.RateLimitError:
            self.history.pop()
            return "Rate limited. Try again in a minute."
        except an.APIStatusError as e:
            self.history.pop()
            return f"API error {e.status_code}. Try again."
        except an.APIConnectionError:
            self.history.pop()
            return "Can't reach Claude. Is the Mac online?"
        if message.stop_reason == "refusal":
            self.history.pop()
            return "Claude can't help with that one."
        self.history.append({"role": "assistant", "content": message.content})
        return ""


class SubscriptionChat:
    """Replies through Claude Code in headless mode (`claude -p`), which runs on
    the subscription you're logged into, so there's no API key and no per-token bill.
    Claude Code keeps the conversation as a session and we resume it every turn.
    It runs with no tools, no MCP servers and no project settings: a plain chat."""

    def __init__(self):
        self.exe = shutil.which("claude")
        if not self.exe:
            raise SystemExit("Claude Code (`claude`) isn't on PATH. Install it and log in, "
                             "or use --engine api / --engine fake.")
        self.cwd = ROOT / "build" / "session"     # sessions are stored per directory
        self.cwd.mkdir(parents=True, exist_ok=True)
        self.session = None

    def reset(self):
        self.session = None

    def reply(self, prompt, on_text, cancelled):
        sid = self.session or str(uuid.uuid4())
        args = [self.exe, "-p",
                "--output-format", "stream-json", "--include-partial-messages", "--verbose",
                "--model", "opus", "--effort", "low",
                "--system-prompt", SYSTEM,
                "--tools", "", "--strict-mcp-config", "--setting-sources", "",
                "--disable-slash-commands"]
        args += ["--resume", sid] if self.session else ["--session-id", sid]
        # the prompt goes in on stdin so a message like "-v" isn't read as a flag
        proc = subprocess.Popen(args, cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        proc.stdin.write(prompt)
        proc.stdin.close()
        result = None
        for line in proc.stdout:
            if cancelled():
                proc.terminate()
                break
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "stream_event":
                ev = event["event"]
                if ev.get("type") == "content_block_delta" and ev["delta"].get("type") == "text_delta":
                    on_text(ev["delta"]["text"])
            elif event.get("type") == "result":
                result = event
        proc.wait()
        if cancelled():
            if self.session is None and proc.returncode == 0:
                self.session = sid
            return ""
        if result and not result.get("is_error"):
            self.session = sid
            return ""
        detail = (result or {}).get("result") or proc.stderr.read()
        print(f"\n[claude -p failed: {detail.strip()[:300]}]")
        if re.search(r"log ?in|auth", detail, re.I):
            return "Claude Code isn't logged in. Run `claude` on the Mac and log in."
        if re.search(r"limit", detail, re.I):
            return "Usage limit reached. Try again later."
        return "Claude Code error. See the Mac terminal."


class FakeChat:
    """Canned replies for trying things out without an API key."""

    REPLIES = [
        "Hi! I'm a stand-in for Claude. Restart the bridge without --fake "
        "to talk to the real thing.",
        "Why did the Game Boy go to therapy? It had too many unresolved *links*.",
        "Pixels on green glass\nA printer hums its warm song\nPaper remembers",
        "Fun fact: the Game Boy CPU runs at about 4.19 MHz, and the printer "
        "prints at 160 dots per line.\n\n- Short reply\n- With a list",
    ]

    def __init__(self):
        self.n = 0

    def reset(self):
        self.n = 0

    def reply(self, prompt, on_text, cancelled):
        text = self.REPLIES[self.n % len(self.REPLIES)]
        self.n += 1
        time.sleep(0.6)
        for piece in re.findall(r"\S+\s*|\s+", text):
            if cancelled():
                return ""
            on_text(piece)
            time.sleep(0.04)
        return ""


# ---------------------------------------------------------------- protocol

class Bridge:
    """Game Boy protocol state. Bytes from the Game Boy go in through
    on_gb_byte(); bytes for the Game Boy come out of next_byte()."""

    def __init__(self, chat, log=print):
        self.chat = chat
        self.log = log
        self.out = collections.deque()
        self.lock = threading.Lock()
        self.prompt = None          # bytearray while a prompt is coming in
        self.worker = None
        self.cancel = threading.Event()
        self.send(bytes([MAC_READY]))

    # -- output
    def send(self, data: bytes) -> None:
        with self.lock:
            self.out.extend(data)

    def next_byte(self) -> int:
        with self.lock:
            return self.out.popleft() if self.out else 0

    @property
    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    # -- input
    def on_gb_byte(self, b: int) -> None:
        if self.prompt is not None:
            if b == GB_END:
                text, self.prompt = self.prompt.decode("ascii", "replace"), None
                self._start(text)
            elif 32 <= b < 127:
                self.prompt.append(b)
            elif b == GB_BEGIN:
                self.prompt = bytearray()
            return
        if b == GB_BEGIN:
            self.prompt = bytearray()
        elif b == GB_HELLO:
            if not self.busy:
                self.send(bytes([MAC_READY]))
        elif b == GB_STOP:
            self.cancel.set()
        elif b == GB_NEW:
            self.cancel.set()
            if self.worker:
                self.worker.join()
            self.chat.reset()
            self.send(bytes([MAC_CLEAR, MAC_READY]))
            self.log("[new chat]")

    def _start(self, prompt: str) -> None:
        if self.busy or not prompt.strip():
            return
        self.log(f"> {prompt}")
        self.cancel.clear()
        self.send(bytes([MAC_USER]) + bubble(prompt))
        self.send(tile(TILES["T_SPARK"]) + b" " + bytes([MAC_THINKING]))   # dots pulse after the spark
        self.worker = threading.Thread(target=self._reply, args=(prompt,), daemon=True)
        self.worker.start()

    def _reply(self, prompt: str) -> None:
        wrap = Wrapper(self.send, COLS - CLAUDE_INDENT, CLAUDE_INDENT, indented=True)
        started = []

        def on_text(text):
            started.append(True)
            wrap.feed(text)
            sys.stdout.write(text)
            sys.stdout.flush()

        error = self.chat.reply(prompt, on_text, self.cancel.is_set)
        if self.cancel.is_set():
            wrap.feed(" [stopped]")
        if error:
            wrap.feed(("\n" if started else "") + error)
            self.log(f"\n[{error}]")
        wrap.finish()
        self.send(bytes([MAC_NL, MAC_READY]))     # blank line between exchanges
        print()


# ---------------------------------------------------------------- transports

class PrinterSim:
    """Just enough Game Boy Printer to accept prints in the emulator.
    Each finished print is saved as a PNG in build/prints/."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.pkt, self.need, self.buf, self.busy, self.strip = [], None, [], 0, []

    def exchange(self, b: int) -> int:
        p = self.pkt
        if not p and b != 0x88:
            return 0
        p.append(b)
        if len(p) == 2 and b != 0x33:
            self.pkt = []
            return 0
        if len(p) == 6:
            self.need = 10 + (p[4] | p[5] << 8)
        if self.need and len(p) == self.need - 1:
            return 0x81
        if self.need and len(p) == self.need:
            cmd, n = p[2], p[4] | p[5] << 8
            status = 0
            if cmd == 0x01:
                self.buf = []
            elif cmd == 0x04 and n:
                self.buf += p[6:6 + n]
            elif cmd == 0x02:
                self.strip += self.buf
                self.buf, self.busy = [], 3
                if p[7] & 0x0F:            # margin after: the strip is finished
                    self._save()
            elif cmd == 0x0F and self.busy:
                self.busy -= 1
                status |= 0x02
            if self.buf:
                status |= 0x08
            self.pkt, self.need = [], None
            return status
        return 0

    def _save(self):
        from PIL import Image
        data, self.strip = self.strip, []
        h = len(data) // 640 * 16
        im = Image.new("L", (160, h))
        px = im.load()
        for t in range(len(data) // 16):
            tx, ty = t % 20, t // 20
            for r in range(8):
                lo, hi = data[t * 16 + r * 2], data[t * 16 + r * 2 + 1]
                for c in range(8):
                    v = ((lo >> (7 - c)) & 1) | (((hi >> (7 - c)) & 1) << 1)
                    px[tx * 8 + c, ty * 8 + r] = 255 - v * 85
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"print-{time.strftime('%H%M%S')}.png"
        im.resize((320, h * 2), Image.NEAREST).save(path)
        self.last = path
        print(f"\n[printed -> {path.relative_to(ROOT)}]")


def find_xfer(rom: bytes) -> int:
    """Address of serial_xfer(): ldh (SB),a / ld a,$81 / ldh (SC),a / wait / ldh a,(SB) / ret"""
    sig = bytes([0xE0, 0x01, 0x3E, 0x81, 0xE0, 0x02, 0xF0, 0x02, 0x07, 0x38, 0xFB, 0xF0, 0x01, 0xC9])
    at = rom.find(sig)
    if not 0 < at < 0x4000:
        raise SystemExit("serial_xfer not found in the ROM's home bank")
    return at


class Emulator:
    """PyBoy with the link port wired to the bridge (and to a fake printer
    whenever the ROM starts a printer packet, as if you'd swapped cables)."""

    def __init__(self, bridge, window="SDL2", rom=ROM, ram_file=None):
        from pyboy import PyBoy
        self.bridge = bridge
        self.printer = PrinterSim(ROOT / "build" / "prints")
        rom_bytes = rom.read_bytes()
        xfer = find_xfer(rom_bytes)
        # the chat log (cart RAM) is kept in build/claudeboy.gb.ram between runs
        extra = {"ram_file": ram_file} if ram_file is not None else {}
        self.pb = PyBoy(str(rom), window=window, sound_emulated=False, scale=4, **extra)
        self.reply = 0
        self.pb.hook_register(0, xfer, self._on_xfer, None)
        self.pb.hook_register(0, xfer + 13, self._on_ret, None)

    def _on_xfer(self, _):
        b = self.pb.register_file.A
        if b == 0x88 or self.printer.pkt:
            self.reply = self.printer.exchange(b)
        elif self.bridge is None:          # demo ROM: nothing on the cable but the printer
            self.reply = 0xFF
        else:
            if b:
                self.bridge.on_gb_byte(b)
            self.reply = self.bridge.next_byte()

    def _on_ret(self, _):
        self.pb.register_file.A = self.reply

    def run(self):
        print("Emulator keys: arrows, A = a, B = s, START = Enter, SELECT = Backspace")
        while self.pb.tick():
            pass
        self.pb.stop()


class SerialLink:
    def __init__(self, bridge, port=None):
        import serial
        from serial.tools import list_ports
        if not port:
            ports = [p.device for p in list_ports.comports() if "usbmodem" in p.device]
            if not ports:
                raise SystemExit("No Pico found (looked for /dev/cu.usbmodem*). Is it plugged in?")
            port = ports[0]
        self.bridge = bridge
        self.port = serial.Serial(port, 115200, timeout=0.01)
        print(f"Bridge on {port}. Ctrl-C to quit.")

    def run(self):
        try:
            while True:
                for b in self.port.read(256):
                    self.bridge.on_gb_byte(b)
                out = bytearray()
                while (b := self.bridge.next_byte()):
                    out.append(b)
                if out:
                    self.port.write(out)
        except KeyboardInterrupt:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transport", choices=["emu", "serial"])
    ap.add_argument("--port")
    ap.add_argument("--engine", choices=["subscription", "api", "fake"], default="subscription")
    ap.add_argument("--fake", action="store_true", help="same as --engine fake")
    ap.add_argument("--rom", type=Path, help="ROM to run in the emulator (the demo ROM needs no bridge)")
    args = ap.parse_args()

    if args.rom and "demo" in args.rom.name:
        print("Demo ROM: preset replies, no bridge.")
        Emulator(None, rom=args.rom).run()
        return

    engine = "fake" if args.fake else args.engine
    if engine == "fake":
        chat = FakeChat()
    elif engine == "subscription":
        chat = SubscriptionChat()
    else:
        import os
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise SystemExit("Set ANTHROPIC_API_KEY first, or use the default subscription engine.")
        chat = ClaudeChat()
    print(f"Replies from: {engine}")
    bridge = Bridge(chat)
    if args.transport == "emu":
        Emulator(bridge).run()
    else:
        SerialLink(bridge, args.port).run()


if __name__ == "__main__":
    main()
