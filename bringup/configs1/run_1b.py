"""CONFIGS 1b on board A: the DACs' own harmonics, on the scope (REVB 21).

fast.bit loaded; both DACs play the same tone at half of full scale (1 Vpp at the SMA into 50 ohm).  Scope CH1 on J204
DAC 1 OUT, CH2 on J205 DAC 2 OUT, both set to 50 ohm here; 10-bit mode, 1M points, the spectrum computed on the PC.
Taken at two volts per division: harmonics that move with the scale are the scope's own (siglent.md)."""
import json
import sys
import time

import numpy as np

sys.path.insert(0, "/home/jason/OpticsPCBs/ECP5-2ADC-2DAC/bringup")
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
f.dacs(3)
res = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "rows": []}
for ch in (1, 2):
    sc.channel(ch, on=True, impedance="50", coupling="DC", offset=0.0, bwlimit="FULL", probe=1)   # BNC-SMA cables: 1x
for ch in (3, 4):
    sc.channel(ch, on=False)
sc.acquire(mdepth="1M", resolution=10)
sc.trigger(source=1, level=0.0, slope="rising", mode="normal")


def lines(v, fs, f0):
    n = len(v); w = np.blackman(n)
    s = np.abs(np.fft.rfft((v - v.mean()) * w)) / (w.sum() / 2)
    df = fs / n

    def at(fx):
        k = int(round(fx / df)); return s[max(k - 4, 0):k + 5].max()
    a1 = at(f0)
    return a1, [20 * np.log10(at(h * f0) / a1) for h in (2, 3, 4, 5)]


try:
    for fr in (5e6, 10e6, 20e6):
        f0 = f.tone(fr)
        tb = 50e-6                                     # 500 us in 1M points: 2 GSa/s
        sc.timebase(scale=tb, delay=0.0)
        for vdiv in (0.2, 0.15):
            for ch in (1, 2):
                sc.channel(ch, scale=vdiv)
            time.sleep(0.5)
            sc.single(timeout=10)
            for ch in (1, 2):
                t, v, info = sc.waveform(ch)
                fs = 1 / np.median(np.diff(t[:1000]))
                a1, h = lines(np.asarray(v), fs, f0)
                r = dict(freq=f0, vdiv=vdiv, ch=ch, vpp=2 * a1, fs=fs, h2=h[0], h3=h[1], h4=h[2], h5=h[3])
                res["rows"].append(r)
                print("1b  %5.2f MHz DAC %d at %.2f V/div: %.3f Vpp at the scope; 2nd %6.1f, 3rd %6.1f, 4th %6.1f, 5th %6.1f dBc"
                      " (%.0f MSa/s)" % (f0 / 1e6, ch, vdiv, 2 * a1, h[0], h[1], h[2], h[3], fs / 1e6), flush=True)
finally:
    f.dacs(0)                                          # the DACs back to 0 V
    sc.trigger(mode="auto")
    sc.run()
    json.dump(res, open(OUT, "w"), indent=1)
