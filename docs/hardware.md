# Hardware

Everything in this lab targets real hardware. This page lists what's on the
bench, what's being built, and how far along it is.

## On the bench

| Part | Used for | Notes |
|---|---|---|
| Game Boy (original DMG) | everything | |
| EverDrive flash cart with FRAM | running the ROMs | FRAM keeps cart saves without a battery |
| Game Boy Printer | GB Gallery, ClaudeBoy | Old thermal paper prints faintly; fresh 38 mm thermal rolls fix that |

## Build: ClaudeBoy link bridge

ClaudeBoy's live mode needs something on the link cable that can reach Claude.
The bridge is a Raspberry Pi Pico that plays the far end of the Game Boy's
serial port (a PIO state machine, so timing never depends on Python) and passes
bytes over USB to a Mac running `claudeboy/bridge/bridge.py`.

```
Game Boy ──link cable──▶ level shifter ──▶ Raspberry Pi Pico ──USB──▶ Mac ──▶ Claude
```

**Status: parts list ready, not ordered yet.** The software side is done and
tested in an emulator with a simulated cable. The Pico firmware hasn't run on
real hardware yet.

| Part | ~Price |
|---|---|
| Raspberry Pi Pico 2 WH (headers pre-soldered; Wi-Fi for a later Mac-free version) | $7 |
| Micro-USB data cable | $3 |
| 4-channel bidirectional logic level converter (BSS138), since the link port is 5 V | $5 |
| Half-size breadboard + male-to-male jumper wires | $8 |
| A Game Boy link cable to cut, or a link-port breakout board | $5–10 |

Wiring and Pico setup: [claudeboy/README.md](../claudeboy/README.md#wiring).

### Checklist

- [x] Link protocol, Mac bridge, Pico firmware written
- [x] End-to-end test in an emulator with a simulated cable
- [ ] Order parts
- [ ] Breadboard the level shifter and Pico
- [ ] First byte across the real cable (status bar: NO LINK CABLE → WAITING FOR MAC → CLAUDE)
- [ ] First real chat, first printed reply
- [ ] Tidy build: small perfboard or 3D-printed case
- [ ] Wi-Fi version on the Pico W (no Mac)

## Log

Hardware updates are posted with the software ones in
[Discussions → Announcements](https://github.com/hazy2go/gameboy-lab/discussions/categories/announcements)
and collected in [DEVLOG.md](../DEVLOG.md).
