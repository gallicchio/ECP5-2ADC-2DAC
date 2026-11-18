"""REVB 22 with the DAC cables crossed (J204 DAC 1 OUT -> J102 ADC B IN, J205 DAC 2 OUT -> J101 ADC A IN): fast.py's
cross-talk sweep with the channels' roles swapped.  DAC 1 plays: its own path is ADC B, the victim ADC A; DAC 2 plays:
its path ADC A, the victim ADC B.  fast.bit loaded; run from the tutorial repo's src/verilog."""
import json
import sys
import time

import numpy as np

sys.path.insert(0, "/home/jason/mudd/133electronics/ecp5-2adc-2dac-tutorial/src/verilog")
import fast                                         # noqa: E402

OUT = sys.argv[1]
fa = fast.Fast(fast.find_port())
fs = fa.rate(2) if fa.rate(2) else 62.5e6
fs = 62.5e6
fa.amplitude(0)
rows = []
try:
    for f in np.geomspace(100e3, 30e6, 24):
        f = fa.tone(f)
        r = [f]
        for mask, agg, vic in ((1, 1, 0), (2, 0, 1)):
            fa.dacs(mask)
            time.sleep(0.01)
            rec = fa.capture()
            a_agg, a_vic = fast.fit(rec[:, agg], f, fs)[0], fast.fit(rec[:, vic], f, fs)[0]
            floor = np.mean([fast.fit(rec[:, vic], f + k * 7.3 * fs / fast.NPAIRS, fs)[0] for k in (-3, -2, 2, 3)])
            r += [20 * np.log10(a_vic / a_agg), 20 * np.log10(floor / a_agg)]
        rows.append(r)
        print("%10.0f Hz: DAC 1 (-> ADC B) leaks into ADC A %6.1f dBc (floor %6.1f)   DAC 2 (-> ADC A) into ADC B %6.1f dBc"
              " (floor %6.1f)" % tuple(r), flush=True)
finally:
    fa.dacs(0)
    json.dump({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "rows": rows}, open(OUT, "w"), indent=1)
