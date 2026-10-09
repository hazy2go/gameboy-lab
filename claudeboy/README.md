# ClaudeBoy

Chat with Claude on a real Game Boy: type on an on-screen keyboard, watch the
reply stream in, and print it on the Game Boy Printer. The chat log is saved
on the cart (FRAM on the EverDrive), so it survives power-off.

```
Game Boy ──link cable──▶ Raspberry Pi Pico ──USB──▶ Mac (bridge/bridge.py) ──▶ Claude API
```

The Game Boy is a terminal. The Mac bridge gets the replies, strips markdown,
and word-wraps to 20 columns. The Pico just passes bytes between the link port
and USB.

**Replies use your Claude subscription.** The bridge runs Claude Code headless
(`claude -p`, Opus at low effort, no tools), which uses the account you're logged
into, so there's no API key. Each Game Boy chat is one Claude Code session that
gets resumed every turn, and "New chat" starts a fresh one. Replies take a few
seconds to start because Claude Code boots for each message.
Alternatives: `ENGINE=api` (Anthropic API, `ANTHROPIC_API_KEY`, `claude-opus-5-5`
with refusal fallback) or `FAKE=1` (canned replies).

## Two ROMs

| ROM | What it needs | Build |
|---|---|---|
| `build/claudeboy.gb` | the Pico link bridge + Mac (live Claude) | `make` |
| `build/claudeboy-demo.gb` | nothing: preset replies built in | `make demo` |

The **demo** runs on the Game Boy by itself, so it's good for showing people. Every
quick-menu idea has several preset replies that take turns, "Explain simpler" and
"Keep going" follow up on the last reply, and typed messages are matched by keyword
(hello, who are you, Game Boy, printer, thanks, ...). Anything else gets an honest
"this is the demo" answer. Printing works too, since the link port is free.
The replies are in `tools/demo_replies.py`; edit them and run `make demo`.
`make emu-demo` plays it on the Mac.

## Try it now, without hardware

```
make emu            # Game Boy window on the Mac, live Claude (your subscription)
make emu FAKE=1     # canned replies
```

Keys in the emulator: arrows, **A** = `a`, **B** = `s`, **START** = Enter,
**SELECT** = Backspace. Prints land in `build/prints/` as PNGs. The chat log is
kept in `build/claudeboy.gb.ram`.

## Controls

| Where | Buttons |
|---|---|
| Chat | **A** type · **SELECT** quick prompts · **START** print last reply · ↑↓ scroll · **B** stop a reply |
| Keyboard | D-pad pick · **A** type · **B** delete (or close when empty) · **SELECT** abc/ABC/123 · **START** send |
| Quick menu | joke, haiku, fun fact, explain simpler, keep going, ask me something, print, new chat |

**Printing:** there's only one link port. Press START, swap the Pico's cable for
the printer, press A, then plug the Pico back in. The Game Boy reconnects by itself.

## Shopping list

| Part | Notes | ~Price |
|---|---|---|
| **Raspberry Pi Pico 2 WH** | "H" = headers already soldered. "W" = Wi-Fi, for a no-Mac version later. Any Pico works for now. | $7 |
| **Micro-USB data cable** | Must carry data, not just charge | $3 |
| **Bidirectional logic level converter**, 4-channel (BSS138) | The link port is 5 V, the Pico is 3.3 V. Usually sold in packs of 5. | $5 |
| **Half-size breadboard + male-to-male jumper wires** | No soldering needed with these | $8 |
| **A Game Boy link cable you're OK cutting** | Match the plug to your console: the original Game Boy has the big DMG plug, Pocket/Color have the small one. Cheap third-party cables are fine. Or buy a **Game Boy link port breakout board** and skip the cutting. | $5–10 |
| *Optional:* multimeter, wire stripper | Handy for finding which wire is which in a cut cable | |

Fresh **38 mm thermal paper** for the printer is worth getting too.

## Wiring

```
Game Boy link port            level shifter              Pico
 pin 2  SO (data out)  ──HV1        LV1──  GP3
 pin 3  SI (data in)   ──HV2        LV2──  GP4
 pin 5  SC (clock)     ──HV3        LV3──  GP2
 pin 6  GND            ──GND        GND──  GND
                          HV ──── Pico VBUS (5 V from USB)
                          LV ──── Pico 3V3
```

Leave link pin 1 (5 V) and pin 4 unconnected. If you cut a cable, the wire
colours vary by brand, so beep each wire to a plug pin with the multimeter.
Also, cables cross SO/SI inside, so check which wire reaches **pin 2 on the
Game Boy end**.

## Setting up the Pico

1. Hold BOOTSEL, plug the Pico into the Mac, and drag the MicroPython `.uf2`
   for your board (micropython.org/download) onto the drive that appears.
2. `make pico` copies `pico/main.py` onto it.
3. Plug the Game Boy in, run `make bridge` on the Mac, and power on the Game Boy
   with `build/claudeboy.gb`. The status bar goes NO LINK CABLE → WAITING FOR
   MAC → CLAUDE.

## How it works

- **Protocol** (`src/link.h`): every link transfer swaps one byte each way, with
  `0x00` meaning "nothing to send". The Game Boy clocks a few bytes each frame.
  A run of `0xFF` means nothing is plugged in.
- **Pico** (`pico/main.py`): a PIO state machine is the far end of the Game Boy's
  shift register, so link timing never depends on Python.
- **Screen** (`src/main.c`): the chat scrolls with SCY over a 32-row map ring.
  The window is pinned to the bottom and grows into the keyboard and menu.
  A sprite behind the glyphs is the key highlight.
- **Printing**: the last exchange is rendered with the same font tiles and sent
  in 9-packet chunks with zero margins between them, so long replies come out
  as one strip.

## Tests

`make test` runs both ROMs headlessly with a fake printer. The live ROM goes
through the real bridge protocol with canned replies: quick prompt, typed
message, print, new chat, and a reboot that has to keep the chat log. The demo
ROM is checked for quick prompts, follow-ups, keyword replies, the fallback,
and printing.
Not covered: the Pico firmware and real link-cable timing. That needs the
hardware.
