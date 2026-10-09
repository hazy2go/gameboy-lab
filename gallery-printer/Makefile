# GB Gallery: pictures in images/ -> build/gallery.gb
#   make                 build (bayer dithering, center crop)
#   make DITHER=fs       error-diffusion dithering instead
#   make FIT=pad         letterbox instead of cropping
#   make samples         regenerate the sample pictures
#   make PUBLIC=1        leave out images-private/ (for published ROMs)

GBDK ?= $(HOME)/gbdk
LCC = $(GBDK)/bin/lcc
DITHER ?= bayer
FIT ?= crop

ROM = build/gallery.gb
GEN_STAMP = build/gen/.stamp

# MBC5 + RAM + battery (0x1B), ROM banks sized automatically, one 8 KB SRAM bank
LCCFLAGS = -Wm-yt0x1B -Wm-yoA -Wm-ya1 -Wm-yn"GB GALLERY" -autobank -Wb-ext=.rel -Isrc -Ibuild/gen

all: convert $(ROM)

# Always converts and relinks: picture names may contain spaces (which make
# can't track), and switching PUBLIC=1 on and off within one second would
# otherwise leave a stale ROM, since make only compares whole seconds.
convert:
	python3 tools/convert.py --dither $(DITHER) --fit $(FIT) $(if $(PUBLIC),--public)

build/gen/ui.c: tools/gen_ui.py tools/fonts/*
	python3 tools/gen_ui.py

$(ROM): convert build/gen/ui.c src/*.c src/*.h
	$(LCC) $(LCCFLAGS) -Wl-m -o $@ src/*.c build/gen/*.c
	@$(GBDK)/bin/romusage $(ROM:.gb=.map) -g 2>/dev/null | tail -n 12 || true

samples:
	python3 tools/make_samples.py

clean:
	rm -rf build

.PHONY: all convert samples clean test $(ROM)

# headless emulator run with a simulated printer (see tools/test_rom.py)
test: all .venv
	.venv/bin/python tools/test_rom.py

.venv:
	python3 -m venv .venv && .venv/bin/pip install -q pyboy pillow
