/* ClaudeBoy: Claude on a Game Boy.

   The Game Boy is a terminal: a Mac-side bridge (through a Pico on the link
   cable) talks to Claude and lays the chat out (bubbles, wrapping) as tiles,
   streamed over the link. This ROM shows the chat, takes typing from an
   on-screen keyboard, and prints the last exchange on the Game Boy Printer.

   Screen: the background is the chat, scrolled smoothly with SCY over a
   32-row map ring (line n lives in map row n & 31; the ring is exactly 256
   pixels, so SCY wraps with it). The window is pinned to the bottom: a black
   status bar, growing to nine rows for the keyboard and menus.

   The chat log lives in cart SRAM (FRAM on the EverDrive) as tile numbers,
   so it survives power-off and prints exactly as it looks. */

#include <gb/gb.h>
#include <stdint.h>
#include <string.h>
#include "font.h"
#include "link.h"
#include "printer.h"
#ifdef DEMO
#include "demo.h"
#define LINK_XFER demo_xfer      /* the "bridge" is built in: nothing on the cable */
#else
#define LINK_XFER serial_xfer
#endif

#define COLS 20u
#define TEXT_X 2u              /* Claude's text column (after the spark) */

/* ------------------------------------------------------------ chat log (SRAM) */

typedef struct {
    char magic[4];
    uint16_t count;        /* lines in use; the last one is being written */
    uint16_t exch_start;   /* first line of the latest exchange (for printing) */
    uint8_t col;           /* cursor column in the last line */
} log_header_t;

#define LOG_LINES 400u
#define LOG ((log_header_t *)0xA000)
#define LOG_LINE(n) ((uint8_t *)(0xA010u + (uint16_t)((n) % LOG_LINES) * COLS))
static const char log_magic[4] = { 'C', 'L', 'G', '2' };

/* ------------------------------------------------------------ state */

#define MODE_CHAT 0u
#define MODE_KEYS 1u
#define MODE_MENU 2u

static uint8_t ui_mode;
static uint16_t view_top;      /* first log line on screen */
static uint8_t vis_rows = 17;  /* chat rows visible above the window */
static uint8_t scy_pos, scy_target;
static uint8_t frame;

static uint8_t keys, prev_keys, held_frames;

#ifdef DEMO
static uint8_t link_down = 0, bridge_ready = 1, busy, thinking, esc;   /* the bridge is built in */
#else
static uint8_t link_down = 1, bridge_ready, busy, thinking, esc;
#endif
static uint8_t ff_streak;
static uint8_t hello_timer;

#define OUTQ_SIZE 256u
static uint8_t outq[OUTQ_SIZE];
static uint8_t outq_head, outq_len;   /* uint8 wrap = ring of 256 */

#define INPUT_MAX 240u
static char input_buf[INPUT_MAX + 1];
static uint8_t input_len;
static uint8_t kb_page, kb_row, kb_col;
static uint8_t menu_sel;

static uint8_t row_buf[COLS];
static uint8_t status_shown[COLS];

/* ------------------------------------------------------------ input */

#define DPAD (J_UP | J_DOWN | J_LEFT | J_RIGHT)

static uint8_t input(void) {
    uint8_t fresh;
    prev_keys = keys;
    keys = joypad();
    fresh = keys & ~prev_keys;
    if (keys & DPAD) {
        if (fresh & DPAD) held_frames = 0;
        else if (++held_frames >= 16u) {
            held_frames = 12u;
            fresh |= keys & DPAD;
        }
    }
    return fresh;
}

static void wait(uint8_t frames) {
    while (frames--) vsync();
}

/* ------------------------------------------------------------ text helpers */

static uint8_t glyph(char c) {
    return (c >= 32 && c < 127) ? (uint8_t)(c - 32) : (uint8_t)('?' - 32);
}

/* Writes s into row_buf from x in the given tile offset; returns the next column. */
static uint8_t put_text(uint8_t x, const char *s, uint8_t offset) {
    while (*s && x < COLS) row_buf[x++] = glyph(*s++) + offset;
    return x;
}

static void win_row(uint8_t y) {
    set_win_tiles(0, y, COLS, 1, row_buf);
}

static void win_text(uint8_t y, const char *s) {
    memset(row_buf, 0, COLS);
    put_text(1, s, 0);
    win_row(y);
}

static void win_clear(uint8_t from, uint8_t to) {
    memset(row_buf, 0, COLS);
    while (from <= to) win_row(from++);
}

/* ------------------------------------------------------------ status bar */

/* Black bar: built left to right into row_buf, hints right-aligned, and only
   redrawn when it actually changes (it's refreshed every frame). */
static uint8_t sb_x;

static void sb_begin(void) {
    memset(row_buf, status_glyph[0], COLS);
    row_buf[0] = T_SPARK_DARK;
    sb_x = 2;
}

static void sb_text(const char *s) {
    while (*s && sb_x < COLS) row_buf[sb_x++] = status_glyph[(uint8_t)(*s++ - 32)];
}

static void sb_tile(uint8_t t, uint8_t n) {     /* n consecutive tiles: badges and pills */
    while (n-- && sb_x < COLS) row_buf[sb_x++] = t++;
}

/* Moves columns from..sb_x to the right edge. */
static void sb_align_right(uint8_t from) {
    uint8_t w = sb_x - from, shift = COLS - sb_x;
    if (!shift) return;
    memmove(row_buf + from + shift, row_buf + from, w);
    memset(row_buf + from, status_glyph[0], shift);
}

static void sb_end(void) {
    if (memcmp(row_buf, status_shown, COLS) == 0) return;
    memcpy(status_shown, row_buf, COLS);
    win_row(0);
}

/* left text, then up to two (badge, label) hints on the right */
static void status_bar(const char *left, uint8_t b1, uint8_t n1, const char *l1,
                       uint8_t b2, uint8_t n2, const char *l2) {
    uint8_t from;
    sb_begin();
    sb_text(left);
    from = sb_x;
    if (n1) { sb_x++; sb_tile(b1, n1); sb_text(l1); }
    if (n2) { sb_x++; sb_tile(b2, n2); sb_text(l2); }
    sb_align_right(from);
    sb_end();
}

static void chat_status(void) {
    static const char * const dots[] = { "THINKING   ", "THINKING.  ", "THINKING.. ", "THINKING..." };
    if (link_down) status_bar("NO LINK CABLE", 0, 0, 0, 0, 0, 0);
    else if (!bridge_ready) status_bar("WAITING FOR MAC", 0, 0, 0, 0, 0, 0);
    else if (thinking) status_bar(dots[(frame >> 3) & 3u], T_BTN_B, 1, "STOP", 0, 0, 0);
    else if (busy) status_bar("CLAUDE", T_BTN_B, 1, "STOP", 0, 0, 0);
    else status_bar("CLAUDE", T_BTN_A, 1, "TYPE", T_BTN_SEL, 2, "");
}

/* ------------------------------------------------------------ chat drawing */

static uint16_t oldest_line(void) {
    return LOG->count > LOG_LINES ? LOG->count - LOG_LINES : 0;
}

static uint16_t bottom_top(void) {
    uint16_t lo = oldest_line();
    if (LOG->count <= vis_rows) return lo;
    return LOG->count - vis_rows > lo ? LOG->count - vis_rows : lo;
}

static void draw_line(uint16_t n) {
    if (n < LOG->count) {
        set_bkg_tiles(0, (uint8_t)n & 31u, COLS, 1, LOG_LINE(n));
    } else {
        memset(row_buf, 0, COLS);
        set_bkg_tiles(0, (uint8_t)n & 31u, COLS, 1, row_buf);
    }
}

static void redraw_chat(void) {
    uint8_t r;
    for (r = 0; r <= vis_rows; r++) draw_line(view_top + r);
    scy_pos = scy_target = ((uint8_t)view_top & 31u) << 3;
    SCY_REG = scy_pos;
}

/* Moving by one line glides (scroll_step); bigger jumps redraw at once. */
static void scroll_to(uint16_t top) {
    if (top == view_top + 1u) {
        draw_line(top + vis_rows);             /* the row coming up from under the window */
        draw_line(top + vis_rows - 1u);
    } else if (top + 1u == view_top) {
        draw_line(top);
    } else if (top != view_top) {
        view_top = top;
        redraw_chat();
        return;
    }
    view_top = top;
    scy_target = ((uint8_t)top & 31u) << 3;
}

static void scroll_step(void) {
    uint8_t d = scy_target - scy_pos;          /* wraps: 1..127 = down, 129..255 = up */
    uint8_t step;
    if (!d) return;
    if (d < 128u) {
        step = d > 16u ? 4u : 2u;
        scy_pos += step > d ? d : step;
    } else {
        d = (uint8_t)-d;
        step = d > 16u ? 4u : 2u;
        scy_pos -= step > d ? d : step;
    }
    SCY_REG = scy_pos;
}

static uint8_t following(void) {
    return view_top >= bottom_top();
}

/* ------------------------------------------------------------ chat log */

static void log_newline(void) {
    uint8_t follow = following();
    LOG->count++;
    LOG->col = 0;
    memset(LOG_LINE(LOG->count - 1u), 0, COLS);
    if (follow) scroll_to(bottom_top());
    else draw_line(LOG->count - 1u);
}

static void log_put(uint8_t tile) {
    uint16_t n;
    if (LOG->col >= COLS) log_newline();
    n = LOG->count - 1u;
    LOG_LINE(n)[LOG->col] = tile;
    if (n >= view_top && n <= view_top + vis_rows) set_bkg_tile_xy(LOG->col, (uint8_t)n & 31u, tile);
    LOG->col++;
}

static void log_text(uint8_t x, const char *s) {
    while (LOG->col < x) log_put(0);
    while (*s) log_put(glyph(*s++));
    log_newline();
}

/* An empty chat starts with a hello from Claude (written here, so it's there
   before any cable is plugged in). */
static void log_reset(void) {
    memcpy(LOG->magic, log_magic, 4);
    LOG->count = 1;
    LOG->col = 0;
    memset(LOG_LINE(0), 0, COLS);
    view_top = 0;
    log_newline();
    log_put(T_SPARK);
    log_text(TEXT_X, "Hi! I'm Claude.");
    log_text(TEXT_X, "Ask me anything.");
    log_newline();
    log_text(TEXT_X, "Press A to type,");
    log_text(TEXT_X, "SELECT for ideas.");
    log_newline();
    LOG->exch_start = LOG->count - 1u;
}

/* ------------------------------------------------------------ thinking dots */

/* While Claude thinks, three dots pulse after the spark on the current line.
   They're drawn on screen only; the log keeps the real cells. */
static void dots_draw(void) {
    uint16_t n = LOG->count - 1u;
    uint8_t i, phase = (frame >> 3) & 3u;
    if (n < view_top || n > view_top + vis_rows || LOG->col + 3u > COLS) return;
    for (i = 0; i < 3u; i++) {
        set_bkg_tile_xy(LOG->col + i, (uint8_t)n & 31u, i < phase ? glyph('.') : 0);
    }
}

static void set_thinking(uint8_t on) {
    uint16_t n = LOG->count - 1u;
    if (thinking && !on && n >= view_top && n <= view_top + vis_rows) draw_line(n);
    thinking = on;
}

/* ------------------------------------------------------------ link */

static void send(uint8_t b) {
    if (outq_len < 255u) outq[(uint8_t)(outq_head + outq_len++)] = b;
}

static void on_byte(uint8_t c) {
    if (esc) {                       /* raw tile number */
        esc = 0;
        set_thinking(0);
        log_put(c);
        return;
    }
    if (c >= 32 && c < 127) {
        set_thinking(0);
        log_put(glyph(c));
        return;
    }
    switch (c) {
    case MAC_TILE:     esc = 1; break;
    case MAC_NL:       set_thinking(0); log_newline(); break;
    case MAC_USER:     LOG->exch_start = LOG->col ? LOG->count : LOG->count - 1u; break;
    case MAC_THINKING: thinking = 1; break;
    case MAC_READY:    bridge_ready = 1; busy = 0; set_thinking(0); break;
    case MAC_CLEAR:    set_thinking(0); log_reset(); redraw_chat(); break;
    }
}

/* Swaps up to 8 bytes a frame (~8 ms), stopping early when both sides are idle. */
static void link_poll(void) {
    uint8_t n, out, in;
    if (!bridge_ready && (hello_timer == 255u || ++hello_timer >= 90u)) {
        hello_timer = 0;
        send(GB_HELLO);
    }
    for (n = 0; n < 8u; n++) {
        out = 0;
        if (outq_len) { out = outq[outq_head++]; outq_len--; }
        in = LINK_XFER(out);
        if (in == 0xFF) {
            if (ff_streak < 255u) ff_streak++;
            if (ff_streak >= 8u && !link_down) {
                link_down = 1;
                bridge_ready = busy = esc = 0;
                set_thinking(0);
            }
            if (!outq_len) break;
            continue;
        }
        ff_streak = 0;
        link_down = 0;
        if (in) on_byte(in);
        else if (!outq_len) break;
    }
}

static void submit(const char *s, uint8_t len) {
    if (!bridge_ready || busy || !len) return;
    send(GB_BEGIN);
    while (len--) send((uint8_t)*s++);
    send(GB_END);
    busy = 1;
}

/* ------------------------------------------------------------ window */

#define WIN_OPEN_Y 72u          /* window top when keyboard/menu is open */
#define WIN_CLOSED_Y 136u

static void set_window(uint8_t open) {
    move_win(7, open ? WIN_OPEN_Y : WIN_CLOSED_Y);
    vis_rows = open ? 9u : 17u;
    if (open || following()) view_top = bottom_top();
    redraw_chat();
}

static void close_overlay(void) {
    ui_mode = MODE_CHAT;
    HIDE_SPRITES;
    set_window(0);
}

/* ------------------------------------------------------------ keyboard */

#define KB_ROWS 4u
#define KB_COLS 10u
#define KB_SPACE ' '

static const char * const kb_pages[3][KB_ROWS] = {
    { "abcdefghij", "klmnopqrst", "uvwxyz.,?!", "'-:;()&@# " },
    { "ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ.,?!", "\"+=*/%$<> " },
    { "1234567890", ".,?!'\"-:;/", "()[]{}<>+=", "*&@#%$^~| " },
};
static const char * const kb_page_name[] = { "ABC", "CAPS", "123" };

/* typed text: a grey band (it becomes your bubble), last 3 lines shown */
static void kb_draw_input(void) {
    uint8_t start = 0, r, x, i;
    if (input_len >= 54u) start = (uint8_t)(((input_len - 54u) / 18u + 1u) * 18u);
    for (r = 0; r < 3u; r++) {
        memset(row_buf, T_GREY, COLS);
        for (x = 0; x < 18u; x++) {
            i = start + r * 18u + x;
            if (i < input_len) row_buf[x + 1u] = glyph(input_buf[i]) + T_GREY;
            else if (i == input_len && (frame & 32u)) row_buf[x + 1u] = glyph('_') + T_GREY;
        }
        win_row(1u + r);
    }
}

static void kb_draw_keys(void) {
    uint8_t r, k;
    for (r = 0; r < KB_ROWS; r++) {
        memset(row_buf, 0, COLS);
        for (k = 0; k < KB_COLS; k++) {
            char c = kb_pages[kb_page][r][k];
            row_buf[k * 2u + 1u] = c == KB_SPACE ? T_SPACE_KEY : glyph(c);
        }
        win_row(5u + r);
    }
}

static void kb_cursor(void) {
    move_sprite(0, (kb_col * 2u + 1u) * 8u + 8u, WIN_OPEN_Y + (5u + kb_row) * 8u + 16u);
}

static void kb_status(void) {
    sb_begin();
    sb_tile(T_BTN_SEL, 2);
    sb_text(kb_page_name[kb_page]);
    sb_x = 10;
    sb_tile(T_BTN_B, 1);
    sb_text("DEL");
    sb_x++;
    sb_tile(T_BTN_START, 3);
    sb_text("GO");
    sb_end();
}

static void kb_open(void) {
    ui_mode = MODE_KEYS;
    memset(row_buf, 0, COLS);
    win_row(4);
    kb_draw_input();
    kb_draw_keys();
    kb_status();
    kb_cursor();
    SHOW_SPRITES;
    set_window(1);
}

static void kb_update(uint8_t k) {
    if (k & J_UP) kb_row = kb_row ? kb_row - 1u : KB_ROWS - 1u;
    if (k & J_DOWN) kb_row = kb_row + 1u < KB_ROWS ? kb_row + 1u : 0;
    if (k & J_LEFT) kb_col = kb_col ? kb_col - 1u : KB_COLS - 1u;
    if (k & J_RIGHT) kb_col = kb_col + 1u < KB_COLS ? kb_col + 1u : 0;
    if (k & DPAD) kb_cursor();
    if (k & J_SELECT) {
        kb_page = (kb_page + 1u) % 3u;
        kb_draw_keys();
        kb_status();
    }
    if ((k & J_A) && input_len < INPUT_MAX) {
        input_buf[input_len++] = kb_pages[kb_page][kb_row][kb_col];
        if (kb_page == 1 && kb_row < 3u) {   /* one capital, then back to lowercase */
            kb_page = 0;
            kb_draw_keys();
            kb_status();
        }
    }
    if (k & J_B) {
        if (input_len) input_len--;
        else { close_overlay(); return; }
    }
    if ((k & J_START) && input_len && bridge_ready && !busy) {
        submit(input_buf, input_len);
        input_len = 0;
        close_overlay();
        return;
    }
    if ((k & (J_A | J_B)) || (frame & 31u) == 0) kb_draw_input();   /* text, blinking cursor */
}

/* ------------------------------------------------------------ printing */

#define PRINT_EXPOSURE 0x60u    /* a bit darker than normal: old paper is faint */

static uint8_t print_buf[PRN_PACKET_BYTES];

static void print_fill(uint8_t half, uint16_t n, uint16_t end) {
    uint8_t *dst = print_buf + (uint16_t)half * (PRN_PACKET_BYTES / 2u);
    uint8_t *cells = LOG_LINE(n);
    uint8_t x;
    if (n >= end) {
        memset(dst, 0, PRN_PACKET_BYTES / 2u);
        return;
    }
    for (x = 0; x < COLS; x++, dst += 16) {
        memcpy(dst, font_tiles + (uint16_t)cells[x] * 16u, 16);
    }
}

static void wait_ab(void) {
    uint8_t k;
    do { vsync(); k = input(); } while (!(k & (J_A | J_B)));
}

static const char *print_error(uint8_t r) {
    uint8_t s = printer_last_status;
    if (r == PRN_NO_PRINTER) return "No printer found.";
    if (r == PRN_TIMEOUT) return "Printer timed out.";
    if (s & PRN_STATUS_JAM) return "Paper jam.";
    if (s & PRN_STATUS_BATTERY) return "Printer battery low";
    if (s & PRN_STATUS_OTHER) return "Too hot or cold.";
    return "Link error.";
}

/* A row of button hints on white, e.g. (A) PRINT  (B) CANCEL */
static void hint_row(uint8_t y, uint8_t b1, const char *l1, uint8_t b2, const char *l2) {
    uint8_t x;
    memset(row_buf, 0, COLS);
    row_buf[1] = b1;
    x = put_text(3, l1, 0) + 2u;
    if (b2) {
        row_buf[x] = b2;
        put_text(x + 2u, l2, 0);
    }
    win_row(y);
}

static void progress_bar(uint8_t y, uint8_t done, uint8_t total) {
    uint8_t filled = (uint8_t)((uint16_t)done * 18u / total);
    memset(row_buf, 0, COLS);
    memset(row_buf + 1, T_GREY, 18);          /* light track */
    memset(row_buf + 1, T_KEY, filled);       /* no darker tile to spare; reuse the key shape */
    win_row(y);
}

/* Prints from the start of the last exchange to the end of the log. Everything
   happens in the open window; the chat stays visible above it. */
static void print_last(void) {
    uint16_t first = LOG->exch_start, end = LOG->count, n;
    uint8_t r = PRN_OK, packets, p, in_chunk, margins;

    if (LOG->col == 0 && end > first) end--;             /* trailing empty line */
    ui_mode = MODE_MENU;
    HIDE_SPRITES;
    win_clear(1, 8);
    status_bar("PRINT", 0, 0, 0, 0, 0, 0);
    set_window(1);
    if (end <= first) {
        win_text(2, "Nothing to print");
        win_text(3, "yet.");
        hint_row(7, T_BTN_A, "OK", 0, 0);
        wait_ab();
        close_overlay();
        return;
    }
#ifdef DEMO
    win_text(2, "Plug in the Game");
    win_text(3, "Boy Printer.");
#else
    win_text(2, "Unplug the link");
    win_text(3, "cable and plug in");
    win_text(4, "the printer.");
#endif
    hint_row(7, T_BTN_A, "PRINT", T_BTN_B, "CANCEL");
    wait_ab();
    if (!(keys & J_A)) { close_overlay(); return; }

    win_clear(2, 7);
    win_text(2, "Printing...");
    packets = (uint8_t)((end - first + 1u) / 2u);

    r = printer_begin();
    for (p = 0, in_chunk = 0, n = first; r == PRN_OK && p < packets; p++) {
        progress_bar(4, p, packets);
        print_fill(0, n++, end);
        print_fill(1, n++, end);
        r = printer_data(print_buf);
        if (r == PRN_OK && (++in_chunk == PRN_BUFFER_PACKETS || p + 1u == packets)) {
            /* one strip: feed before the first chunk, after the last */
            margins = (p + 1u == in_chunk ? 0x10u : 0) | (p + 1u == packets ? 0x03u : 0);
            win_text(2, "Feeding paper...");
            r = printer_run(margins, PRINT_EXPOSURE);
            win_text(2, "Printing...");
            in_chunk = 0;
        }
    }
    win_clear(2, 7);
    win_text(2, r == PRN_OK ? "Done! Tear it off." : print_error(r));
#ifndef DEMO
    win_text(4, "Plug the link cable");
    win_text(5, "back in.");
#endif
    hint_row(7, T_BTN_A, "OK", 0, 0);
    wait_ab();
#ifndef DEMO
    ff_streak = 0;
    bridge_ready = 0;          /* re-handshake with the bridge right away */
    hello_timer = 255u;
#endif
    close_overlay();
}

/* ------------------------------------------------------------ menu */

static const char * const menu_items[] = {
    "Tell me a joke",
    "Write a haiku",
    "Tell me a fun fact",
    "Explain simpler",
    "Keep going",
    "Ask me something",
    "Print last reply",
    "New chat",
};
#define MENU_COUNT 8u
#define MENU_PRINT 6u
#define MENU_NEW 7u

static void menu_draw(void) {
    uint8_t i, offset;
    for (i = 0; i < MENU_COUNT; i++) {
        offset = i == menu_sel ? T_GREY : 0;
        memset(row_buf, offset, COLS);
        put_text(2, menu_items[i], offset);
        if (i == menu_sel) row_buf[0] = offset + glyph('>');
        win_row(1u + i);
    }
}

static void menu_open(void) {
    ui_mode = MODE_MENU;
    status_bar("IDEAS", T_BTN_A, 1, "GO", T_BTN_B, 1, "BACK");
    menu_draw();
    set_window(1);
}

static void menu_update(uint8_t k) {
    if (k & J_UP) { menu_sel = menu_sel ? menu_sel - 1u : MENU_COUNT - 1u; menu_draw(); }
    if (k & J_DOWN) { menu_sel = menu_sel + 1u < MENU_COUNT ? menu_sel + 1u : 0; menu_draw(); }
    if (k & (J_B | J_SELECT)) close_overlay();
    if (k & J_A) {
        if (menu_sel == MENU_PRINT) {
            print_last();
        } else if (menu_sel == MENU_NEW) {
            if (bridge_ready && !busy) send(GB_NEW);
            close_overlay();
        } else {
            submit(menu_items[menu_sel], (uint8_t)strlen(menu_items[menu_sel]));
            close_overlay();
        }
    }
}

/* ------------------------------------------------------------ title */

static const uint8_t fade_steps[] = { 0xE4, 0x90, 0x40, 0x00 };

static void fade_out(void) {
    uint8_t i;
    for (i = 1; i < 4u; i++) { BGP_REG = OBP0_REG = fade_steps[i]; wait(4); }
}

static void fade_in(void) {
    uint8_t i = 3;
    while (i--) { BGP_REG = OBP0_REG = fade_steps[i]; wait(4); }
}

static void center(uint8_t y, const char *s) {
    memset(row_buf, 0, COLS);
    put_text((uint8_t)(COLS - strlen(s)) / 2u, s, 0);
    set_bkg_tiles(0, y, COLS, 1, row_buf);
}

static void title_screen(void) {
    uint8_t x, y, t = TITLE_TILE_BASE;
    memcpy((uint8_t *)0x8000 + TITLE_TILE_BASE * 16u, title_tiles, TITLE_W * TITLE_H * 16u);
    for (y = 0; y < TITLE_H; y++)
        for (x = 0; x < TITLE_W; x++)
            set_bkg_tile_xy((COLS - TITLE_W) / 2u + x, 3u + y, t++);
    center(11, "Chat with Claude");
#ifdef DEMO
    center(12, "demo edition");
#endif
    SHOW_BKG;
    DISPLAY_ON;
    fade_in();
    for (frame = 0;; frame++) {
        vsync();
        center(14, (frame & 32u) ? "" : "PRESS START");
        if (input() & (J_START | J_A)) break;
    }
    fade_out();
}

/* ------------------------------------------------------------ main */

static void chat_update(uint8_t k) {
    if ((k & J_UP) && view_top > oldest_line()) scroll_to(view_top - 1u);
    if ((k & J_DOWN) && view_top < bottom_top()) scroll_to(view_top + 1u);
    if (k & J_A) {
        if (!busy) kb_open();
    } else if (k & J_B) {
        if (busy) send(GB_STOP);
    } else if (k & J_SELECT) {
        menu_open();
    } else if (k & J_START) {
        print_last();
    }
}

void main(void) {
    uint8_t k;

    DISPLAY_OFF;
    memcpy((uint8_t *)0x8000, font_tiles, FONT_TILE_COUNT * 16u);
    memset((uint8_t *)0x9800, 0, 0x800);     /* both maps: spaces */
    BGP_REG = OBP0_REG = 0x00;               /* start white, fade in */
    LCDC_REG |= LCDCF_BG8000 | LCDCF_WIN9C00;
    set_sprite_tile(0, T_KEY);
    set_sprite_prop(0, S_PRIORITY);           /* behind the glyph's ink */

    title_screen();

    DISPLAY_OFF;
    memcpy((uint8_t *)0x8000, font_tiles, FONT_TILE_COUNT * 16u);   /* the title borrowed some */
    memset((uint8_t *)0x9800, 0, 0x400);

    ENABLE_RAM;
    SWITCH_RAM(0);
    if (memcmp(LOG->magic, log_magic, 4) != 0 || LOG->count == 0 || LOG->col > COLS) {
        log_reset();
    }
    view_top = bottom_top();
    redraw_chat();
    move_win(7, WIN_CLOSED_Y);
    chat_status();

    SHOW_BKG;
    SHOW_WIN;
    DISPLAY_ON;
    fade_in();

    for (;;) {
        vsync();
        frame++;
        scroll_step();
        k = input();
        link_poll();
        switch (ui_mode) {
        case MODE_CHAT:
            chat_update(k);
            if (ui_mode == MODE_CHAT) chat_status();
            if (thinking && (frame & 7u) == 0) dots_draw();
            break;
        case MODE_KEYS: kb_update(k); break;
        case MODE_MENU: menu_update(k); break;
        }
    }
}
