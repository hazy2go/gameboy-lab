/* Demo build (make demo): a stand-in for the Mac bridge that lives in the ROM
   and answers with preset replies, so ClaudeBoy runs with nothing plugged in. */
#ifndef DEMO_H
#define DEMO_H

#include <stdint.h>

/* Same contract as serial_xfer(): hand it the Game Boy's byte, get the
   bridge's byte back. Speaks the protocol in link.h. */
uint8_t demo_xfer(uint8_t b);

#endif
