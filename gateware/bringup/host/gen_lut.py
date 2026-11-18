#!/usr/bin/env python3
"""Write rtl/sine_lut.hex: 1024 samples of one sine period, 16-bit two's complement, amplitude 8191
(the DAC is 14 bits: 8192 + value is a full-scale sine).  The RTL reads it with $readmemh; the
testbench reads the same file, so the simulation checks the hardware against the file, not a formula."""
import math, os
here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, '..', 'rtl', 'sine_lut.hex')
with open(out, 'w') as f:
    for i in range(1024):
        v = int(round(8191 * math.sin(2 * math.pi * i / 1024)))
        f.write('%04x\n' % (v & 0xFFFF))
print('wrote', os.path.normpath(out))
