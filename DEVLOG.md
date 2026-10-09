# Devlog

Updates are also posted in [Discussions → Announcements](https://github.com/hazy2go/gameboy-lab/discussions/categories/announcements).

## 2026-10-10: the lab opens

**GB Gallery.** A cartridge that holds a gallery of pictures and prints them on
the Game Boy Printer. Pictures are dithered to 4 greys at build time, and a
mid-frame interrupt lets a full-screen picture use 360 unique tiles. The ROM
streams a picture straight from cartridge ROM to the printer. It's printed on
real hardware, but the old thermal paper prints faintly, so fresh paper is on
the list. It now has a thumbnail grid UI with viewfinder corners.

**ClaudeBoy.** Chat with Claude on a Game Boy. Speech bubbles, an on-screen
keyboard, quick ideas, replies that stream in word by word, a chat log saved on
the cart, and START prints the last exchange. The Mac bridge uses a Claude
subscription through Claude Code, or the API. Everything is tested end to end
in an emulator with a simulated link cable.

**ClaudeBoy demo.** A standalone ROM with preset replies (jokes, haiku, fun
facts, follow-ups, keyword answers), so it runs anywhere with nothing plugged in.

**Hardware.** The link bridge (Raspberry Pi Pico + level shifter) is designed
and its parts list is written. Next: order parts and get the first byte across
a real cable. See [docs/hardware.md](docs/hardware.md).
