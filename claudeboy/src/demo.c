/* The demo's pretend bridge. It plays the Mac's half of the link protocol:
   collects a prompt, draws your bubble, "thinks" for a moment, then streams
   a preset reply a couple of characters per frame. Replies are picked by
   keyword (see tools/demo_replies.py), and "Explain simpler" / "Keep going"
   follow up on the last reply. */

#ifdef DEMO

#include <gb/gb.h>
#include <stdint.h>
#include <string.h>
#include "demo.h"
#include "demo_data.h"
#include "font.h"
#include "link.h"

#define COLS 20u
#define BUBBLE_TEXT 14u
#define PROMPT_MAX 240u

#define IDLE 0u
#define THINKING 1u
#define STREAMING 2u

static uint8_t state;
static uint8_t out[1400];          /* bytes queued for the Game Boy (bubble, controls) */
static uint16_t out_len, out_pos;
static const uint8_t *stream;      /* reply being typed out */
static uint16_t think_start;
static uint8_t think_frames;
static uint16_t last_frame;
static uint8_t budget;

static char prompt[PROMPT_MAX + 1];
static uint8_t prompt_len, collecting;

static uint8_t turn[DEMO_CATS];
static int16_t last_reply = -1;
static uint8_t used_simpler, used_more;

static void put(uint8_t b) {
    if (out_pos == out_len) out_pos = out_len = 0;
    if (out_len < sizeof(out)) out[out_len++] = b;
}

static void put_tile(uint8_t t) {
    put(MAC_TILE);
    put(t);
}

/* ---- picking a reply */

static uint8_t contains(const char *hay, const char *needle) {
    uint8_t n = (uint8_t)strlen(needle);
    for (; *hay; hay++) {
        if (strncmp(hay, needle, n) == 0) return 1;
    }
    return 0;
}

static uint8_t classify(void) {
    static char low[PROMPT_MAX + 3];
    uint8_t i;
    char c;
    low[0] = ' ';
    for (i = 0; i < prompt_len; i++) {
        c = prompt[i];
        if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
        else if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'))) c = ' ';
        low[i + 1u] = c;
    }
    low[prompt_len + 1u] = ' ';
    low[prompt_len + 2u] = 0;
    for (i = 0; i < DEMO_KEYWORDS; i++) {
        if (contains(low, demo_kw[i])) return demo_kw_cat[i];
    }
    return CAT_FALLBACK;
}

static const uint8_t *next_in(uint8_t cat) {
    uint8_t i = demo_cat_first[cat] + turn[cat] % demo_cat_count[cat];
    turn[cat]++;
    if (cat != CAT_SIMPLER && cat != CAT_MORE) {
        last_reply = i;
        used_simpler = used_more = 0;
    }
    return demo_text[i];
}

static const uint8_t *pick(void) {
    uint8_t cat = classify();
    if (cat == CAT_SIMPLER && last_reply >= 0 && demo_simpler[last_reply] && !used_simpler) {
        used_simpler = 1;
        return demo_simpler[last_reply];
    }
    if (cat == CAT_MORE && last_reply >= 0 && demo_more[last_reply] && !used_more) {
        used_more = 1;
        return demo_more[last_reply];
    }
    return next_in(cat);
}

/* ---- your bubble: word-wrapped to 14 columns, right-aligned */

static void bubble(void) {
    uint8_t starts[24], lens[24], lines = 0, w = 1;
    uint8_t i = 0, j, brk, len, k, pad;
    while (i < prompt_len && lines < 24u) {
        while (i < prompt_len && prompt[i] == ' ') i++;
        if (i >= prompt_len) break;
        j = i;
        brk = 0;
        while (j < prompt_len && j - i < BUBBLE_TEXT) {
            if (prompt[j] == ' ') brk = j;
            j++;
        }
        if (j < prompt_len && prompt[j] != ' ' && brk > i) j = brk;   /* break at a space */
        len = j - i;
        while (len && prompt[i + len - 1u] == ' ') len--;
        starts[lines] = i;
        lens[lines++] = len;
        if (len > w) w = len;
        i = j;
    }
    if (!lines) { starts[0] = 0; lens[0] = 0; lines = 1; }
    pad = COLS - w - 2u;

    for (k = 0; k < pad; k++) put(' ');
    put_tile(T_BUB_TL);
    for (k = 0; k < w; k++) put_tile(T_BUB_T);
    put_tile(T_BUB_TR);
    put(MAC_NL);
    for (i = 0; i < lines; i++) {
        for (k = 0; k < pad; k++) put(' ');
        put_tile(T_BUB_L);
        for (k = 0; k < w; k++) {
            char c = k < lens[i] ? prompt[starts[i] + k] : ' ';
            put_tile(T_GREY + (uint8_t)(c - 32));
        }
        put_tile(T_BUB_R);
        put(MAC_NL);
    }
    for (k = 0; k < pad; k++) put(' ');
    put_tile(T_BUB_BL);
    for (k = 0; k < w; k++) put_tile(T_BUB_B);
    put_tile(T_BUB_BR);
    put(MAC_NL);
}

static void start_reply(void) {
    stream = pick();
    put(MAC_USER);
    bubble();
    put_tile(T_SPARK);
    put(' ');
    put(MAC_THINKING);
    state = THINKING;
    think_start = sys_time;
    think_frames = 45u + (prompt_len & 31u);     /* a beat to "think" */
}

static void finish(void) {
    state = IDLE;
    put(MAC_NL);       /* blank line between exchanges */
    put(MAC_READY);
}

/* ---- the link */

static void receive(uint8_t b) {
    if (collecting) {
        if (b == GB_END) {
            collecting = 0;
            if (state == IDLE) start_reply();
        } else if (b == GB_BEGIN) {
            prompt_len = 0;
        } else if (b >= 32 && b < 127 && prompt_len < PROMPT_MAX) {
            prompt[prompt_len++] = (char)b;
        }
        return;
    }
    switch (b) {
    case GB_BEGIN: collecting = 1; prompt_len = 0; break;
    case GB_HELLO: if (state == IDLE) put(MAC_READY); break;
    case GB_STOP:
        if (state != IDLE) { put(MAC_NL); finish(); }
        break;
    case GB_NEW:
        state = IDLE;
        out_len = out_pos = 0;
        last_reply = -1;
        put(MAC_CLEAR);
        put(MAC_READY);
        break;
    }
}

uint8_t demo_xfer(uint8_t b) {
    uint8_t c;
    if (b) receive(b);
    if (out_pos < out_len) return out[out_pos++];
    if (state == THINKING) {
        if ((uint16_t)(sys_time - think_start) < think_frames) return 0;
        state = STREAMING;
    }
    if (state == STREAMING) {
        if (sys_time != last_frame) { last_frame = sys_time; budget = 2; }  /* ~120 chars/s */
        if (!budget) return 0;
        budget--;
        c = *stream;
        if (!c) { finish(); return out[out_pos++]; }
        stream++;
        return c;
    }
    return 0;
}

#endif
