/* GB Gallery: browse pictures baked into the ROM and print them on the
   Game Boy Printer. Print counts and the tone setting live in cart SRAM
   (the EverDrive keeps it in FRAM).

   Screens: TITLE -> GRID (a page of six thumbnails) -> VIEW (full screen)
   -> PRINT (progress). The menu screens share one tile set: font, black
   header/footer bars, button badges and six thumbnail slots.

   A full-screen picture needs 360 unique tiles but the background can only
   address 256 at a time, so VIEW splits the frame: rows 0-8 read tiles from
   0x8000 (LCDC bit 4 set), and an LYC interrupt flips to the 0x8800 window
   for rows 9-17. Copying the 5760 bytes linearly to 0x8000 makes tile i land
   at index (i & 0xFF) in whichever half it is drawn, so the map is simply
   0,1,2,...,359 truncated to bytes. */

#include <gb/gb.h>
#include <stdint.h>
#include <string.h>
#include "assets.h"
#include "printer.h"
#include "ui.h"

#define VRAM_TILES ((uint8_t *)0x8000)
#define BG_MAP     ((uint8_t *)0x9800)
#define COLS 20u

#define SPLIT_LINE 71u        /* last scanline of tile row 8 */

/* grid: 3 x 2 thumbnails of 4x4 tiles */
#define GRID_COLS 3u
#define GRID_ROWS 2u
#define PER_PAGE  6u
#define THUMB_X(c) (2u + (c) * 6u)
#define THUMB_Y(r) (2u + (r) * 5u)

/* ------------------------------------------------------------ state */

static const char * const tone_name[] = { "lightest", "light", "normal", "dark", "darkest" };   /* print darkness */
static const uint8_t tone_exposure[]  = { 0x00, 0x20, 0x40, 0x60, 0x7F };
#define TONE_COUNT 5u
#define TONE_DEFAULT 2u

static uint8_t sel, tone = TONE_DEFAULT;
static uint8_t page = 0xFF;            /* thumbnails currently in VRAM */
static uint16_t prints[IMAGE_COUNT];
static uint8_t keys, prev_keys, held_frames;
static volatile uint8_t split_on;
static uint8_t row_buf[COLS];
static uint8_t frame;

/* ------------------------------------------------------------ save (SRAM) */

typedef struct {
    uint16_t hash;
    uint16_t count;
} slot_t;

typedef struct {
    char magic[4];
    uint8_t version;
    uint8_t tone;
    uint8_t last;
    uint8_t slots;
} save_header_t;

#define SAVE_HEADER ((save_header_t *)0xA000)
#define SAVE_SLOTS  ((slot_t *)0xA008)
static const char save_magic[4] = { 'G', 'B', 'G', 'P' };

static void save_write(void) {
    uint8_t i;
    ENABLE_RAM;
    SWITCH_RAM(0);
    memcpy(SAVE_HEADER->magic, save_magic, 4);
    SAVE_HEADER->version = 1;
    SAVE_HEADER->tone = tone;
    SAVE_HEADER->last = sel;
    SAVE_HEADER->slots = IMAGE_COUNT;
    for (i = 0; i < IMAGE_COUNT; i++) {
        SAVE_SLOTS[i].hash = image_hash[i];
        SAVE_SLOTS[i].count = prints[i];
    }
    DISABLE_RAM;
}

/* Counts are matched by name hash, so adding, removing or reordering
   pictures in a later build keeps everyone's history. */
static void save_load(void) {
    uint8_t i, j, n;
    ENABLE_RAM;
    SWITCH_RAM(0);
    if (memcmp(SAVE_HEADER->magic, save_magic, 4) == 0 && SAVE_HEADER->version == 1) {
        if (SAVE_HEADER->tone < TONE_COUNT) tone = SAVE_HEADER->tone;
        if (SAVE_HEADER->last < IMAGE_COUNT) sel = SAVE_HEADER->last;
        n = SAVE_HEADER->slots;
        for (i = 0; i < IMAGE_COUNT; i++) {
            for (j = 0; j < n; j++) {
                if (SAVE_SLOTS[j].hash == image_hash[i]) {
                    prints[i] = SAVE_SLOTS[j].count;
                    break;
                }
            }
        }
    }
    DISABLE_RAM;
    save_write();
}

/* ------------------------------------------------------------ interrupts */

static void vbl_isr(void) {
    if (split_on) LCDC_REG |= LCDCF_BG8000;
}

static void lcd_isr(void) {
    if (!split_on) return;
    while (STAT_REG & 0x03) ;      /* wait for h-blank so line 71 finishes clean */
    LCDC_REG &= ~LCDCF_BG8000;
}

/* ------------------------------------------------------------ input */

#define DPAD (J_UP | J_DOWN | J_LEFT | J_RIGHT)

/* Reads the pad once per frame; returns newly pressed buttons, plus
   auto-repeat for the d-pad when held. */
static uint8_t input(void) {
    uint8_t fresh;
    prev_keys = keys;
    keys = joypad();
    fresh = keys & ~prev_keys;
    if (keys & DPAD) {
        if (fresh & DPAD) held_frames = 0;
        else if (++held_frames >= 18u) {
            held_frames = 13u;
            fresh |= keys & DPAD;
        }
    }
    return fresh;
}

/* ------------------------------------------------------------ display */

static const uint8_t fade_steps[] = { 0xE4, 0x90, 0x40, 0x00 };

static void wait(uint8_t frames) {
    while (frames--) vsync();
}

static void fade_out(void) {
    uint8_t i;
    for (i = 1; i < 4; i++) { BGP_REG = OBP0_REG = fade_steps[i]; wait(3); }
}

static void fade_in(void) {
    uint8_t i = 3;
    while (i--) { BGP_REG = OBP0_REG = fade_steps[i]; wait(3); }
}

/* Fades to white and turns the LCD off so VRAM can be rewritten freely. */
static void screen_begin(void) {
    fade_out();
    DISPLAY_OFF;
    split_on = 0;
    HIDE_SPRITES;
}

static void screen_end(void) {
    LCDC_REG |= LCDCF_BG8000;
    SCX_REG = SCY_REG = 0;
    SHOW_BKG;
    DISPLAY_ON;
    fade_in();
}

/* Menu screens: font, bars and badges in, map blank. */
static void menu_screen(void) {
    screen_begin();
    memcpy(VRAM_TILES, ui_tiles, UI_TILE_COUNT * 16u);
    memset(BG_MAP, 0, 32u * 18u);        /* tile 0 is the space glyph */
    page = 0xFF;                         /* thumbnails need reloading */
}

static uint8_t glyph(char c) {
    return (c >= 32 && c < 127) ? (uint8_t)(c - 32) : (uint8_t)('?' - 32);
}

static uint8_t put_text(uint8_t x, const char *s) {
    while (*s && x < COLS) row_buf[x++] = glyph(*s++);
    return x;
}

static void row(uint8_t y) {
    set_bkg_tiles(0, y, COLS, 1, row_buf);
}

static void text_center(uint8_t y, const char *s) {
    memset(row_buf, 0, COLS);
    put_text((uint8_t)(COLS - strlen(s)) / 2u, s);
    row(y);
}

/* Unsigned to decimal; returns a pointer into a static buffer. */
static char num_buf[6];
static const char *num(uint16_t v) {
    char *p = num_buf + 5;
    *p = 0;
    do { *--p = '0' + (v % 10u); v /= 10u; } while (v);
    return p;
}

/* ---- black bars (header row 0, footer row 17) */

static uint8_t bar_x;

static void bar_begin(void) {
    memset(row_buf, status_glyph[0], COLS);
    row_buf[0] = T_ICON_DARK;
    bar_x = 2;
}

static void bar_text(const char *s) {
    while (*s && bar_x < COLS) row_buf[bar_x++] = status_glyph[(uint8_t)(*s++ - 32)];
}

static void bar_tile(uint8_t t, uint8_t n) {
    while (n-- && bar_x < COLS) row_buf[bar_x++] = t++;
}

static void bar_right(const char *s) {        /* right-aligned text */
    bar_x = COLS - (uint8_t)strlen(s) - 1u;
    bar_text(s);
}

/* footer: up to two (badge, label) hints, right-aligned */
static void footer(uint8_t b1, uint8_t n1, const char *l1, uint8_t b2, uint8_t n2, const char *l2) {
    uint8_t w = n1 + (uint8_t)strlen(l1) + (n2 ? 1u + n2 + (uint8_t)strlen(l2) : 0u);
    memset(row_buf, status_glyph[0], COLS);
    bar_x = COLS - w - 1u;
    bar_tile(b1, n1);
    bar_text(l1);
    if (n2) { bar_x++; bar_tile(b2, n2); bar_text(l2); }
    row(17);
}

/* ------------------------------------------------------------ title */

static void title_screen(void) {
    uint8_t x, y, t = TITLE_TILE_BASE;
    memcpy(VRAM_TILES, ui_tiles, 96u * 16u);
    memcpy(VRAM_TILES + TITLE_TILE_BASE * 16u, title_tiles, TITLE_W * TITLE_H * 16u);
    memset(BG_MAP, 0, 32u * 18u);
    for (y = 0; y < TITLE_H; y++)
        for (x = 0; x < TITLE_W; x++)
            set_bkg_tile_xy((COLS - TITLE_W) / 2u + x, 3u + y, t++);
    text_center(11, "print your pictures");
    screen_end();
    for (frame = 0;; frame++) {
        vsync();
        text_center(14, (frame & 32u) ? "" : "PRESS START");
        if (input() & (J_START | J_A)) break;
    }
}

/* ------------------------------------------------------------ GRID */

static void load_thumb(uint8_t slot, uint8_t i) {
    uint8_t saved = _current_bank;
    SWITCH_ROM((uint8_t)(uint16_t)image_bank[i]);
    set_bkg_data(THUMB_BASE + slot * 16u, 16, image_thumb[i]);
    SWITCH_ROM(saved);
}

static void draw_thumb_slot(uint8_t slot, uint8_t present) {
    uint8_t x0 = THUMB_X(slot % GRID_COLS), y0 = THUMB_Y(slot / GRID_COLS), y, t;
    t = THUMB_BASE + slot * 16u;
    for (y = 0; y < 4u; y++, t += 4u) {
        memset(row_buf, 0, 4);
        if (present) { row_buf[0] = t; row_buf[1] = t + 1u; row_buf[2] = t + 2u; row_buf[3] = t + 3u; }
        set_bkg_tiles(x0, y0 + y, 4, 1, row_buf);
    }
}

static void grid_page(void) {
    uint8_t p = sel / PER_PAGE, s, i;
    if (p == page) return;
    page = p;
    for (s = 0; s < PER_PAGE; s++) {
        i = p * PER_PAGE + s;
        if (i < IMAGE_COUNT) load_thumb(s, i);
        draw_thumb_slot(s, i < IMAGE_COUNT);
    }
}

static void grid_header(void) {
    char buf[8];
    uint8_t n;
    bar_begin();
    bar_text("GALLERY");
    strcpy(buf, num(sel + 1u));
    n = (uint8_t)strlen(buf);
    buf[n] = '/';
    strcpy(buf + n + 1u, num(IMAGE_COUNT));
    bar_right(buf);
    row(0);
}

static void grid_caption(void) {
    char buf[COLS + 1];
    text_center(13, image_name[sel]);
    if (prints[sel]) {
        strcpy(buf, "printed ");
        strcat(buf, num(prints[sel]));
        strcat(buf, prints[sel] == 1u ? " time" : " times");
        text_center(14, buf);
    } else {
        text_center(14, "not printed yet");
    }
}

static void grid_tone(void) {
    uint8_t i, x = 1;
    memset(row_buf, 0, COLS);
    row_buf[x++] = T_BTN_SEL;
    row_buf[x++] = T_BTN_SEL + 1u;
    x++;
    for (i = 0; i < TONE_COUNT; i++) row_buf[x++] = i <= tone ? T_PIP_ON : T_PIP_OFF;
    put_text(x + 1u, tone_name[tone]);
    row(16);
}

/* Viewfinder corners around the selected thumbnail: four sprites, one tile
   flipped four ways, breathing in and out by a pixel. */
static void grid_cursor(void) {
    uint8_t s = sel % PER_PAGE;
    uint8_t x = THUMB_X(s % GRID_COLS) * 8u + 8u, y = THUMB_Y(s / GRID_COLS) * 8u + 16u;
    uint8_t d = (frame & 32u) ? 4u : 3u;
    move_sprite(0, x - d, y - d);
    move_sprite(1, x + 32u - 8u + d, y - d);
    move_sprite(2, x - d, y + 32u - 8u + d);
    move_sprite(3, x + 32u - 8u + d, y + 32u - 8u + d);
}

static void grid_draw(void) {
    grid_header();
    grid_page();
    grid_caption();
    memset(row_buf, T_RULE, COLS);
    row(12);
    grid_tone();
    footer(T_BTN_A, 1, "VIEW", T_BTN_START, 3, "PRINT");
}

static void grid_show(void) {
    menu_screen();
    grid_draw();
    grid_cursor();
    SHOW_SPRITES;
    screen_end();
}

/* ------------------------------------------------------------ VIEW */

static void view_load(uint8_t i) {
    uint8_t saved = _current_bank;
    uint8_t *m = BG_MAP;
    uint8_t x, y, t = 0;

    screen_begin();
    SWITCH_ROM((uint8_t)(uint16_t)image_bank[i]);
    memcpy(VRAM_TILES, image_data[i], IMAGE_BYTES);
    SWITCH_ROM(saved);
    for (y = 0; y < 18; y++, m += 12) {
        for (x = 0; x < 20; x++) *m++ = t++;   /* wraps at 256: that's the point */
    }
    split_on = 1;
    page = 0xFF;
    screen_end();
}

/* ------------------------------------------------------------ PRINT */

#define BAR_Y 10u

static void print_bar(uint8_t filled) {  /* 0..18 cells */
    uint8_t x;
    memset(row_buf, 0, COLS);
    for (x = 0; x < 18; x++) row_buf[x + 1] = x < filled ? T_BAR_FULL : T_BAR_EMPTY;
    row(BAR_Y);
}

static uint8_t print_progress(uint8_t phase, uint8_t step) {
    char buf[COLS + 1];
    if (phase == PRN_PHASE_SEND) {
        print_bar(step * 2u);
        strcpy(buf, "sending ");
        strcat(buf, num(step));
        strcat(buf, "/9");
        text_center(BAR_Y + 2u, buf);
        /* the pad is polled here because sending blocks the main loop */
        return (input() & J_B) ? 1 : 0;
    }
    print_bar(18);
    text_center(BAR_Y + 2u, (frame++ & 16u) ? "printing.." : "printing...");
    return 0;
}

static void print_message(uint8_t result) {
    const char *a = "", *b = "";
    uint8_t s = printer_last_status;
    switch (result) {
    case PRN_OK:         a = "Done! Tear it off."; break;
    case PRN_CANCELLED:  a = "Cancelled."; break;
    case PRN_TIMEOUT:    a = "The printer stopped"; b = "answering."; break;
    case PRN_NO_PRINTER: a = "No printer found."; b = "Check cable + power."; break;
    default:
        if (s & PRN_STATUS_JAM)          { a = "Paper jam."; b = "Check the paper."; }
        else if (s & PRN_STATUS_BATTERY) { a = "Printer batteries"; b = "are low."; }
        else if (s & PRN_STATUS_OTHER)   { a = "Printer too hot"; b = "or too cold."; }
        else                             { a = "Link error."; b = "Try again."; }
    }
    text_center(BAR_Y + 2u, a);
    text_center(BAR_Y + 3u, b);
}

static void print_screen(uint8_t i) {
    uint8_t result, k, x, y, t;
    char buf[COLS + 1];

    menu_screen();
    bar_begin();
    bar_text("PRINT");
    row(0);
    load_thumb(0, i);                        /* big-ish preview in slot 0 */
    for (y = 0, t = THUMB_BASE; y < 4u; y++)
        for (x = 0; x < 4u; x++) set_bkg_tile_xy(8u + x, 2u + y, t++);
    text_center(7, image_name[i]);
    strcpy(buf, "tone: ");
    strcat(buf, tone_name[tone]);
    text_center(8, buf);
    print_bar(0);
    screen_end();

    for (;;) {
        footer(T_BTN_B, 1, "CANCEL", 0, 0, "");
        text_center(BAR_Y + 3u, "");
        text_center(BAR_Y + 5u, "");
        print_bar(0);
        result = printer_print((uint8_t)(uint16_t)image_bank[i], image_data[i],
                               tone_exposure[tone], print_progress);
        if (result == PRN_OK) {
            if (prints[i] < 0xFFFFu) prints[i]++;
            save_write();
        }
        print_message(result);
        strcpy(buf, "printed ");
        strcat(buf, num(prints[i]));
        strcat(buf, prints[i] == 1u ? " time" : " times");
        text_center(BAR_Y + 5u, buf);
        footer(T_BTN_A, 1, "BACK", T_BTN_START, 3, "AGAIN");

        do { vsync(); k = input(); } while (!(k & (J_A | J_B | J_START)));
        if (!(k & J_START)) return;
    }
}

/* ------------------------------------------------------------ main loops */

static void view_loop(void) {
    uint8_t k;
    view_load(sel);
    for (;;) {
        vsync();
        k = input();
        if (k & J_B) return;
        if (k & (J_LEFT | J_RIGHT)) {
            if (k & J_LEFT) sel = sel ? sel - 1u : IMAGE_COUNT - 1u;
            else sel = (sel + 1u < IMAGE_COUNT) ? sel + 1u : 0;
            view_load(sel);
        }
        if (k & (J_A | J_START)) {
            print_screen(sel);
            view_load(sel);
        }
    }
}

static void grid_move(uint8_t k) {
    if (k & J_LEFT) sel = sel ? sel - 1u : IMAGE_COUNT - 1u;
    if (k & J_RIGHT) sel = sel + 1u < IMAGE_COUNT ? sel + 1u : 0;
    if (k & J_UP) sel = sel >= GRID_COLS ? sel - GRID_COLS : sel;
    if (k & J_DOWN) {
        if (sel + GRID_COLS < IMAGE_COUNT) sel += GRID_COLS;
        else if ((IMAGE_COUNT - 1u) / GRID_COLS > sel / GRID_COLS) sel = IMAGE_COUNT - 1u;  /* short last row */
    }
}

static void grid_loop(void) {
    uint8_t k, old;
    grid_show();
    for (;;) {
        vsync();
        frame++;
        k = input();
        old = sel;
        if (k & DPAD) grid_move(k);
        if (sel != old) {
            grid_header();
            grid_page();
            grid_caption();
        }
        grid_cursor();
        if (k & J_SELECT) {
            tone = (tone + 1u) % TONE_COUNT;
            grid_tone();
            save_write();
        }
        if (k & J_A) {
            save_write();
            view_loop();
            grid_show();
        }
        if (k & J_START) {
            print_screen(sel);
            grid_show();
        }
    }
}

void main(void) {
    uint8_t s;

    DISPLAY_OFF;
    BGP_REG = OBP0_REG = 0x00;
    HIDE_WIN;
    for (s = 0; s < 4u; s++) set_sprite_tile(s, T_CORNER);
    set_sprite_prop(1, S_FLIPX);
    set_sprite_prop(2, S_FLIPY);
    set_sprite_prop(3, S_FLIPX | S_FLIPY);

    save_load();

    CRITICAL {
        STAT_REG = 0x40;          /* interrupt on LY == LYC */
        LYC_REG = SPLIT_LINE;
        add_VBL(vbl_isr);
        add_LCD(lcd_isr);
    }
    set_interrupts(VBL_IFLAG | LCD_IFLAG);

    LCDC_REG |= LCDCF_BG8000;
    title_screen();
    grid_loop();
}
