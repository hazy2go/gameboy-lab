"""
Pico <-> Game Boy link-port bridge (MicroPython).

The Game Boy is the clock master: it drives SC at 8 KHz and shifts a byte
out on SO while shifting one in on SI, MSB first, changing data on the
falling edge and sampling on the rising edge. A PIO state machine plays the
other end of that shift register, so timing never depends on Python.

Every byte the Game Boy sends that isn't 0x00 goes to the Mac over USB;
every byte the Mac sends is queued for the Game Boy. When the queue is empty
the PIO answers 0x00 by itself ("nothing to say").

Wiring (through a 3.3 V <-> 5 V level shifter; the link port is 5 V):
    Game Boy SC  (pin 5) -> GP2   clock in
    Game Boy SO  (pin 2) -> GP3   data from the Game Boy
    Game Boy SI  (pin 3) <- GP4   data to the Game Boy
    Game Boy GND (pin 6) -- GND
    shifter HV = Pico VBUS (5 V), LV = Pico 3V3
"""

import select
import sys
import time

import micropython
import rp2
from machine import Pin

PIN_SC, PIN_SO, PIN_SI = 2, 3, 4


@rp2.asm_pio(out_init=rp2.PIO.OUT_HIGH, out_shiftdir=rp2.PIO.SHIFT_LEFT,
             in_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=False, autopush=False)
def gb_link():
    set(x, 0)
    pull(noblock)                 # next byte (top 8 bits), or x = 0 if none queued
    set(y, 7)
    label("bit")
    wait(0, gpio, 2)              # falling edge: present our bit
    out(pins, 1)
    wait(1, gpio, 2)              # rising edge: sample theirs
    in_(pins, 1)
    jmp(y_dec, "bit")
    push(noblock)


def main():
    micropython.kbd_intr(-1)      # 0x03 is data here, not Ctrl-C
    sc = Pin(PIN_SC, Pin.IN, Pin.PULL_UP)
    so = Pin(PIN_SO, Pin.IN, Pin.PULL_UP)
    si = Pin(PIN_SI, Pin.OUT, value=1)

    # Start between bytes: wait for the clock to sit idle (high) for 5 ms,
    # otherwise we could start mid-byte and every byte after would be shifted.
    quiet = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), quiet) < 5:
        if not sc.value():
            quiet = time.ticks_ms()

    sm = rp2.StateMachine(0, gb_link, freq=125_000_000, in_base=so, out_base=si)
    sm.active(1)

    usb_in = sys.stdin.buffer
    usb_out = sys.stdout.buffer
    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)
    queue = bytearray()
    led = Pin("LED", Pin.OUT)

    while True:
        got = bytearray()
        while sm.rx_fifo():
            b = sm.get() & 0xFF
            if b:
                got.append(b)
        if got:
            usb_out.write(got)
            led.toggle()
        while poll.poll(0):
            queue.extend(usb_in.read(1))
        while queue and sm.tx_fifo() < 4:
            sm.put(queue[0] << 24)
            queue = queue[1:]


main()
