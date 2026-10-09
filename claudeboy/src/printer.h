/* Game Boy Printer, in chunks: a print job is any number of 640-byte data
   packets (two rows of 20 tiles); every 9 packets fill the printer's buffer
   and get printed with zero margins so the paper comes out as one strip. */
#ifndef PRINTER_H
#define PRINTER_H

#include <stdint.h>

#define PRN_STATUS_CHECKSUM  0x01
#define PRN_STATUS_BUSY      0x02
#define PRN_STATUS_UNPROC    0x08
#define PRN_STATUS_PACKET    0x10
#define PRN_STATUS_JAM       0x20
#define PRN_STATUS_OTHER     0x40   /* too hot or too cold */
#define PRN_STATUS_BATTERY   0x80

#define PRN_OK          0
#define PRN_NO_PRINTER  1
#define PRN_TIMEOUT     2
#define PRN_ERROR       3   /* bits in printer_last_status */

#define PRN_PACKET_BYTES   640u
#define PRN_BUFFER_PACKETS 9u

extern uint8_t printer_last_status;

uint8_t printer_begin(void);
uint8_t printer_data(const uint8_t *packet);
/* margins: high nibble = feed before, low nibble = feed after */
uint8_t printer_run(uint8_t margins, uint8_t exposure);

#endif
