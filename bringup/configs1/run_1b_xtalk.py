"""REVB 22 on the DAC side alone: one DAC plays a tone at half of full scale, the other sits at 0 V; the scope (CH1 J204
DAC 1 OUT, CH2 J205 DAC 2 OUT, 50 ohm, probe 1x, 10-bit, 1M points) sees how much of the tone reaches the quiet DAC's
output, in dB below the playing one.  fast.bit loaded; run from the tutorial repo's src/verilog."""
import json
import sys
import time

import numpy as np

import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))      # bringup/, wherever the project is
sys.path.insert(0, "/home/jason/mudd/133electronics/ecp5-2adc-2dac-tutorial/src/verilog")
import bench                                        # noqa: E402
import fast                                         # noqa: E402

OUT = sys.argv[1]
b = bench.Bench("A")
b.require(["SDS2104X:1", "SDS2104X:2"], "the scope's CH1 and CH2")
sc = b.scope
f = fast.Fast(fast.find_port())
f.rate(2)
f.amplitude(0)
res = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "rows": []}
for ch in (1, 2):
    sc.channel(ch, on=True, impedance="50", coupling="DC", offset=0.0, bwlimit="FULL", probe=1)
sc.acquire(mdepth="1M", resolution=10)
sc.timebase(scale=50e-6, delay=0.0)


def amp(v, fs, f0):
    n = len(v); w = np.blackman(n)
    s = np.abs(np.fft.rfft((v - v.mean()) * w)) / (w.sum() / 2)
    k = int(round(f0 / (fs / n)))
    return s[max(k - 4, 0):k + 5].max()


try:
    for loud in (1, 2):
        quiet = 3 - loud
        f.dacs(loud)
        sc.channel(loud, scale=0.15)
        sc.channel(quiet, scale=0.005)
        sc.trigger(source=loud, level=0.0, slope="rising", mode="normal")
        for fr in (3e6, 10e6, 30e6):
            f0 = f.tone(fr)
            time.sleep(0.5)
            sc.single(timeout=10)
            t, vl, _ = sc.waveform(loud)
            _, vq, _ = sc.waveform(quiet)
            fs = 1 / np.median(np.diff(t[:1000]))
            al, aq = amp(np.asarray(vl), fs, f0), amp(np.asarray(vq), fs, f0)
            db = 20 * np.log10(aq / al)
            res["rows"].append(dict(loud=loud, freq=f0, loud_vpp=2 * al, quiet_mvpp=2e3 * aq, db=db))
            print("DAC %d plays %5.2f MHz (%.3f Vpp): DAC %d's output carries %.3f mVpp of it, %6.1f dB below"
                  % (loud, f0 / 1e6, 2 * al, quiet, 2e3 * aq, db), flush=True)
finally:
    f.dacs(0)
    sc.trigger(mode="auto")
    sc.run()
    json.dump(res, open(OUT, "w"), indent=1)
