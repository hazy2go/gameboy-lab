# ClaudeBoy: Claude on a Game Boy
#   make             build build/claudeboy.gb
#   make emu         play it on the Mac: emulator window + live Claude (your Claude subscription,
#                    through Claude Code)
#   make emu FAKE=1  same, with canned replies
#   ENGINE=api       use the Anthropic API (ANTHROPIC_API_KEY) instead of the subscription
#   make bridge      run the bridge for the real Game Boy (Pico on USB)
#   make pico        copy pico/main.py onto the Pico (MicroPython already on it)
#   make demo        build/claudeboy-demo.gb: standalone, preset replies (tools/demo_replies.py),
#                    nothing on the link cable needed
#   make emu-demo    play the demo ROM on the Mac
#   make test        headless end-to-end tests: live ROM + demo ROM, fake printer

GBDK ?= $(HOME)/gbdk
LCC = $(GBDK)/bin/lcc
PY = .venv/bin/python

ROM = build/claudeboy.gb
DEMO_ROM = build/claudeboy-demo.gb

# MBC5 + RAM + battery (0x1B): the chat log lives in the 8 KB of cart RAM (FRAM on the EverDrive)
LCCFLAGS = -Wm-yt0x1B -Wm-ya1 -Wm-yn"CLAUDEBOY" -Isrc -Ibuild/gen

all: $(ROM)

build/gen/font.c: tools/gen_font.py tools/fonts/*
	python3 tools/gen_font.py

$(ROM): build/gen/font.c src/*.c src/*.h
	$(LCC) $(LCCFLAGS) -Wl-m -o $@ src/*.c build/gen/font.c

build/gen/demo_data.c: build/gen/font.c tools/gen_demo.py tools/demo_replies.py bridge/bridge.py
	python3 tools/gen_demo.py

demo: $(DEMO_ROM)

$(DEMO_ROM): build/gen/font.c build/gen/demo_data.c src/*.c src/*.h
	$(LCC) $(LCCFLAGS) -DDEMO -Wm-yn"CLAUDEBOY DEMO" -Wl-m -o $@ src/*.c build/gen/font.c build/gen/demo_data.c

.venv: bridge/requirements.txt
	python3 -m venv .venv && .venv/bin/pip install -q -r bridge/requirements.txt
	touch .venv

emu: all .venv
	$(PY) bridge/bridge.py emu $(if $(FAKE),--fake) $(if $(ENGINE),--engine $(ENGINE))

bridge: .venv
	$(PY) bridge/bridge.py serial $(if $(PORT),--port $(PORT)) $(if $(FAKE),--fake) $(if $(ENGINE),--engine $(ENGINE))

pico: .venv
	.venv/bin/mpremote cp pico/main.py :main.py + reset

emu-demo: demo .venv
	$(PY) bridge/bridge.py emu --rom $(DEMO_ROM)

test: all demo .venv
	$(PY) bridge/test_rom.py
	$(PY) bridge/test_demo.py

clean:
	rm -rf build

.PHONY: all demo emu emu-demo bridge pico test clean
