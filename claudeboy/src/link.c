#include <gb/gb.h>
#include <stdint.h>
#include "link.h"

uint8_t serial_xfer(uint8_t b) {
    SB_REG = b;
    SC_REG = 0x81;             /* start, internal clock (8 KHz, ~1 ms a byte) */
    while (SC_REG & 0x80) ;
    return SB_REG;
}
