/* The link port, shared by the Claude bridge and the Game Boy Printer
   (one cable, so one at a time). */
#ifndef LINK_H
#define LINK_H

#include <stdint.h>

/* Swaps one byte with whatever is on the other end. The Game Boy drives the
   clock, so this always completes; with nothing plugged in it reads 0xFF. */
uint8_t serial_xfer(uint8_t b);

/* ---- Bridge protocol --------------------------------------------------
   Each transfer swaps one byte each way. 0x00 means "nothing to send", and
   0xFF never appears in data, so a run of 0xFF means no cable/bridge.      */

/* Game Boy -> Mac */
#define GB_BEGIN  0x01   /* a prompt follows: printable ASCII ... */
#define GB_END    0x04   /* ... end of prompt, send it to Claude */
#define GB_NEW    0x05   /* forget the conversation */
#define GB_STOP   0x06   /* stop the reply that's streaming */
#define GB_HELLO  0x07   /* anyone there? (answered with MAC_READY) */

/* Mac -> Game Boy (plus printable ASCII, drawn in the plain font) */
#define MAC_NL       0x0A   /* new line (the Mac lays out and wraps everything) */
#define MAC_USER     0x11   /* your message starts here (where printing begins) */
#define MAC_TILE     0x1B   /* next byte is a raw tile number: bubble art, grey text */
#define MAC_THINKING 0x14   /* Claude is working on it */
#define MAC_READY    0x15   /* idle, ready for a prompt */
#define MAC_CLEAR    0x18   /* wipe the chat log */

#endif
