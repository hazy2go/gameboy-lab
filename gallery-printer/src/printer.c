/* Game Boy Printer protocol.

   Every exchange is one packet, sent with the Game Boy as clock master:
       88 33  cmd  compression  len_lo len_hi  data...  sum_lo sum_hi  00 00
   The checksum is the 16-bit sum of everything from cmd through the data.
   While the last two 00 bytes go out, the printer answers 0x81 ("I'm here")
   and then its status byte.

   A print job: INIT, DATA x9 (640 bytes each), an empty DATA to say "that's
   all", PRINT, then STATUS polls until the paper stops moving. */

#include <gb/gb.h>
#include <stdint.h>
#include "printer.h"

#define CMD_INIT   0x01
#define CMD_PRINT  0x02
#define CMD_DATA   0x04
#define CMD_STATUS 0x0F

#define ALIVE 0x81
#define NOBODY 0xFF        /* sentinel status when nothing answered */

#define PACKET_BYTES 640u

#define STATUS_FAIL (PRN_STATUS_CHECKSUM | PRN_STATUS_PACKET | PRN_STATUS_JAM | \
                     PRN_STATUS_OTHER | PRN_STATUS_BATTERY)

uint8_t printer_last_status;

static uint8_t xfer(uint8_t b) {
    SB_REG = b;
    SC_REG = 0x81;             /* start, internal clock (8 KHz) */
    while (SC_REG & 0x80) ;
    return SB_REG;
}

static uint8_t packet(uint8_t cmd, const uint8_t *data, uint16_t len) {
    uint16_t sum = cmd + (uint8_t)len + (uint8_t)(len >> 8);
    uint8_t alive;

    xfer(0x88);
    xfer(0x33);
    xfer(cmd);
    xfer(0x00);                /* no compression */
    xfer((uint8_t)len);
    xfer((uint8_t)(len >> 8));
    while (len--) {
        sum += *data;
        xfer(*data++);
    }
    xfer((uint8_t)sum);
    xfer((uint8_t)(sum >> 8));
    alive = xfer(0x00);
    printer_last_status = xfer(0x00);
    if (alive != ALIVE) printer_last_status = NOBODY;
    return printer_last_status;
}

static uint8_t failed(uint8_t status) {
    return status == NOBODY || (status & STATUS_FAIL);
}

static uint8_t result(uint8_t status) {
    return status == NOBODY ? PRN_NO_PRINTER : PRN_ERROR;
}

static void wait_frames(uint8_t n) {
    while (n--) vsync();
}

uint8_t printer_print(uint8_t bank, const uint8_t *tiles, uint8_t exposure,
                      printer_progress_fn progress) {
    static const uint8_t print_args[4] = { 0x01, 0x13, 0xE4, 0x00 };
    uint8_t args[4];
    uint8_t saved_bank = _current_bank;
    uint8_t status, i, ret = PRN_OK;
    uint16_t frames;
    uint8_t seen_busy;

    status = packet(CMD_INIT, 0, 0);
    if (failed(status)) return result(status);

    SWITCH_ROM(bank);
    for (i = 0; i < PRN_PACKETS; i++) {
        if (progress(PRN_PHASE_SEND, i)) { ret = PRN_CANCELLED; break; }
        status = packet(CMD_DATA, tiles + (uint16_t)i * PACKET_BYTES, PACKET_BYTES);
        if (failed(status)) { ret = result(status); break; }
    }
    SWITCH_ROM(saved_bank);
    if (ret != PRN_OK) {
        packet(CMD_INIT, 0, 0);    /* drop whatever made it into the buffer */
        return ret;
    }
    progress(PRN_PHASE_SEND, PRN_PACKETS);

    status = packet(CMD_DATA, 0, 0);
    if (failed(status)) return result(status);

    /* sheets: 1, margins: 1 line before / 3 after, palette: identity, exposure */
    for (i = 0; i < 4; i++) args[i] = print_args[i];
    args[3] = exposure & 0x7F;
    status = packet(CMD_PRINT, args, 4);
    if (failed(status)) return result(status);

    /* A print takes several seconds. Poll ~12x a second (the printer gives up
       on a host that goes quiet) and stop once it's idle with nothing pending. */
    seen_busy = 0;
    for (frames = 0; frames < 60u * 45u; frames += 5) {
        wait_frames(5);
        status = packet(CMD_STATUS, 0, 0);
        if (failed(status)) return result(status);
        if (status & PRN_STATUS_BUSY) {
            seen_busy = 1;
            progress(PRN_PHASE_PRINT, 0);
        } else if (!(status & PRN_STATUS_UNPROC) && (seen_busy || frames > 120u)) {
            return PRN_OK;
        }
    }
    return PRN_TIMEOUT;
}
