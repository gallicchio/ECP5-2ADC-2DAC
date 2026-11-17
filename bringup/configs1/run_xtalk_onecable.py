"""REVB 22 with one cable: J204 DAC 1 OUT -> J101 ADC A IN, J205 DAC 2 OUT and J102 ADC B IN empty (JP201 TERM in
terminates ADC B at 50 ohm).  DAC 1 plays: what reaches ADC B, against ADC A's tone.  DAC 2 plays into its open
connector: what reaches ADC A, against the level DAC 1 gives ADC A at the same frequency.  fast.bit loaded."""
import json
import sys
import time

import numpy as np

sys.path.insert(0, "/home/jason/mudd/133electronics/ecp5-2adc-2dac-tutorial/src/verilog")
import fast                                         # noqa: E402

OUT = sys.argv[1]
fa = fast.Fast(fast.find_port())
fa.rate(2)
fs = 62.5e6
fa.amplitude(0)
rows = []
try:
    for f in np.geomspace(100e3, 30e6, 24):
        f = fa.tone(f)
        fa.dacs(1); time.sleep(0.01); rec = fa.capture()
        a1 = fast.fit(rec[:, 0], f, fs)[0]; b1 = fast.fit(rec[:, 1], f, fs)[0]
        fl = np.mean([fast.fit(rec[:, 1], f + k * 7.3 * fs / fast.NPAIRS, fs)[0] for k in (-3, -2, 2, 3)])
        fa.dacs(2); time.sleep(0.01); rec = fa.capture()
        a2 = fast.fit(rec[:, 0], f, fs)[0]
        fl2 = np.mean([fast.fit(rec[:, 0], f + k * 7.3 * fs / fast.NPAIRS, fs)[0] for k in (-3, -2, 2, 3)])
        r = [f, 20 * np.log10(b1 / a1), 20 * np.log10(fl / a1), 20 * np.log10(a2 / a1), 20 * np.log10(fl2 / a1)]
        rows.append(r)
        print("%10.0f Hz: DAC 1 (-> ADC A) into ADC B %6.1f dBc (floor %6.1f)   DAC 2 (open) into ADC A %6.1f dBc (floor %6.1f)"
              % tuple(r), flush=True)
finally:
    fa.dacs(0)
    json.dump({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "rows": rows}, open(OUT, "w"), indent=1)
