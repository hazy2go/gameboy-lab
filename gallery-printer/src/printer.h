/* Game Boy Printer over the link cable. */
#ifndef PRINTER_H
#define PRINTER_H

#include <stdint.h>

/* Status byte bits, as reported by the printer after every packet. */
#define PRN_STATUS_CHECKSUM  0x01
#define PRN_STATUS_BUSY      0x02
#define PRN_STATUS_FULL      0x04
#define PRN_STATUS_UNPROC    0x08
#define PRN_STATUS_PACKET    0x10
#define PRN_STATUS_JAM       0x20
#define PRN_STATUS_OTHER     0x40   /* in practice: too hot or too cold */
#define PRN_STATUS_BATTERY   0x80

/* printer_print() results */
#define PRN_OK          0
#define PRN_NO_PRINTER  1
#define PRN_CANCELLED   2
#define PRN_TIMEOUT     3
#define PRN_ERROR       4   /* see printer_last_status for which bits */

extern uint8_t printer_last_status;

/* Phases reported to the progress callback. */
#define PRN_PHASE_SEND  0   /* step = data packets sent so far, 0..PRN_PACKETS */
#define PRN_PHASE_PRINT 1   /* printer is feeding paper */

#define PRN_PACKETS 9       /* 160x144 = 18 tile rows, 2 rows per packet */

/* Called between packets; return nonzero to cancel. */
typedef uint8_t (*printer_progress_fn)(uint8_t phase, uint8_t step);

/* Prints one full-screen picture: 5760 bytes of row-major 2bpp tiles in ROM
   bank `bank`. exposure: 0x00 lightest .. 0x40 normal .. 0x7F darkest.
   Must run from the home bank since it switches ROM banks. */
uint8_t printer_print(uint8_t bank, const uint8_t *tiles, uint8_t exposure,
                      printer_progress_fn progress);

#endif
