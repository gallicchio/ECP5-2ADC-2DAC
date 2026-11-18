"""CONFIGS 1d on board A: CLK IN's limits with a sine.  clocks.bit loaded; SDG CH2 -> J301 CLK IN (JP3001 TERM in: 50
ohm).  At each frequency, amplitudes from 1 Vpp down: the count against the frequency set.  SDG CH2 off at the end."""
import json
import sys
import time

sys.path.insert(0, "/home/jason/OpticsPCBs/ECP5-2ADC-2DAC/bringup")
sys.path.insert(0, "/home/jason/mudd/133electronics/ecp5-2adc-2dac-tutorial/src/verilog")
import bench                                        # noqa: E402
import clocks                                       # noqa: E402

OUT = sys.argv[1]
b = bench.Bench("A")
c = clocks.Clocks(clocks.find_port())
res = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "rows": []}
try:
    for fr in (1e6, 10e6, 30e6):
        for vpp in (1.0, 0.3, 0.1, 0.03, 0.01):
            b.tone("sdg2", fr, vpp)
            c.s.reset_input_buffer()
            c.counts()                                 # a second already under way when the tone changed: discard
            got = [c.counts()[0] for _ in range(2)]
            ppm = [(g / fr - 1) * 1e6 for g in got]
            ok = all(abs(p) < 20 for p in ppm)
            res["rows"].append(dict(freq=fr, vpp=vpp, counts=got, ppm=ppm, ok=ok))
            print("1d  %4.0f MHz %.3f Vpp into CLK IN: %s  (%s ppm)  %s" % (fr / 1e6, vpp, got, ", ".join("%+.1f" % p for p in ppm),
                                                                      "exact" if ok else "WRONG"), flush=True)
finally:
    b.tone_off("sdg2")
    print("SDG CH2 off", flush=True)
    json.dump(res, open(OUT, "w"), indent=1)
