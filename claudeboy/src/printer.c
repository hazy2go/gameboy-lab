/* Game Boy Printer protocol (same as gallery-printer, split into steps).

   Packet: 88 33 cmd 00 len_lo len_hi data... sum_lo sum_hi 00 00
   The printer answers 0x81 then its status during the last two bytes. */

#include <gb/gb.h>
#include <stdint.h>
#include "link.h"
#include "printer.h"

#define CMD_INIT   0x01
#define CMD_PRINT  0x02
#define CMD_DATA   0x04
#define CMD_STATUS 0x0F

#define NOBODY 0xFF

#define STATUS_FAIL (PRN_STATUS_CHECKSUM | PRN_STATUS_PACKET | PRN_STATUS_JAM | \
                     PRN_STATUS_OTHER | PRN_STATUS_BATTERY)

uint8_t printer_last_status;

static uint8_t packet(uint8_t cmd, const uint8_t *data, uint16_t len) {
    uint16_t sum = cmd + (uint8_t)len + (uint8_t)(len >> 8);
    uint8_t alive;

    serial_xfer(0x88);
    serial_xfer(0x33);
    serial_xfer(cmd);
    serial_xfer(0x00);
    serial_xfer((uint8_t)len);
    serial_xfer((uint8_t)(len >> 8));
    while (len--) {
        sum += *data;
        serial_xfer(*data++);
    }
    serial_xfer((uint8_t)sum);
    serial_xfer((uint8_t)(sum >> 8));
    alive = serial_xfer(0x00);
    printer_last_status = serial_xfer(0x00);
    if (alive != 0x81) printer_last_status = NOBODY;
    return printer_last_status;
}

static uint8_t check(uint8_t status) {
    if (status == NOBODY) return PRN_NO_PRINTER;
    return (status & STATUS_FAIL) ? PRN_ERROR : PRN_OK;
}

uint8_t printer_begin(void) {
    return check(packet(CMD_INIT, 0, 0));
}

uint8_t printer_data(const uint8_t *p) {
    return check(packet(CMD_DATA, p, PRN_PACKET_BYTES));
}

uint8_t printer_run(uint8_t margins, uint8_t exposure) {
    uint8_t args[4];
    uint8_t r, status, seen_busy = 0;
    uint16_t frames;

    if ((r = check(packet(CMD_DATA, 0, 0)))) return r;
    args[0] = 1;            /* one copy */
    args[1] = margins;
    args[2] = 0xE4;         /* palette: identity */
    args[3] = exposure & 0x7F;
    if ((r = check(packet(CMD_PRINT, args, 4)))) return r;

    /* poll ~12x a second until the paper stops (the printer drops a quiet host) */
    for (frames = 0; frames < 60u * 45u; frames += 5) {
        r = 5;
        while (r--) vsync();
        status = packet(CMD_STATUS, 0, 0);
        if ((r = check(status))) return r;
        if (status & PRN_STATUS_BUSY) seen_busy = 1;
        else if (!(status & PRN_STATUS_UNPROC) && (seen_busy || frames > 120u)) return PRN_OK;
    }
    return PRN_TIMEOUT;
}
