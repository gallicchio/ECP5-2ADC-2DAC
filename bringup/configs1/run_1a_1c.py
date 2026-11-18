"""CONFIGS 1a and 1c on board A: the ADC side alone (REVB 21) and cross-talk on the ADC side (REVB 22).

fast.bit loaded (ADCs at 62.5 MS/s); the DACs idle.  SDG CH1 -> J101 ADC A IN, 33220A -> J102 ADC B IN (TERM in on
both: 50 ohm).  Every generator off at the end, whatever happens."""
import json
import sys
import time

import numpy as np

sys.path.insert(0, "/home/jason/OpticsPCBs/ECP5-2ADC-2DAC/bringup")
sys.path.insert(0, "/home/jason/mudd/133electronics/ecp5-2adc-2dac-tutorial/src/verilog")
import bench                                        # noqa: E402
import fast                                         # noqa: E402

OUT = sys.argv[1]
FS = 62.5e6
b = bench.Bench("A")
f = fast.Fast(fast.find_port())
f.rate(2)
f.dacs(0)                                           # both DACs idle at 0 V (they go to the scope now, not the ADCs)
time.sleep(0.05)
res = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "1a": [], "1c": [], "quiet": None}


def caps(n=8):
    return [f.capture() for _ in range(n)]


def spectrum_lines(xs, ch, freq):
    a1 = h2 = h3 = 0.0
    for x in xs:
        a, d2, d3 = fast.harmonics(x[:, ch], freq, FS)
        a1 += a / len(xs); h2 += a * 10 ** (d2 / 20) / len(xs); h3 += a * 10 ** (d3 / 20) / len(xs)
    return a1, 20 * np.log10(h2 / a1), 20 * np.log10(h3 / a1)


try:
    # the quiet record: nothing on, what each ADC sees (codes rms)
    xs = caps(4)
    res["quiet"] = [float(np.mean([x[:, c].std() for x in xs])) for c in (0, 1)]
    print("quiet: ADC A %.2f, ADC B %.2f codes rms" % tuple(res["quiet"]), flush=True)

    # ---- 1a: the SDG into ADC A, at 1 Vpp and at 0 dBm (0.632 Vpp, where its own harmonics are specified) ---------
    hp = b.hpgen
    hp.output(on=False)                              # the 33220A off first, whatever state it was left in
    print("33220A:", hp.q("*IDN?").strip(), "output off", flush=True)
    for vpp in ((1.0, 0.632) if "1a" in sys.argv[2:] else ()):
        for fr in (5e6, 10e6, 20e6):
            b.tone("sdg1", fr, vpp)
            time.sleep(0.4)
            xs = caps()
            a1, h2, h3 = spectrum_lines(xs, 0, fr)
            r = dict(freq=fr, vpp=vpp, a1=a1, h2=h2, h3=h3)
            res["1a"].append(r)
            print("1a  %4.1f MHz %.3f Vpp into ADC A: %7.1f codes; 2nd %6.1f dBc, 3rd %6.1f dBc" % (fr / 1e6, vpp, a1, h2, h3),
                  flush=True)
    b.tone_off("sdg1")

    # ---- 1c: the 33220A at DC 0 V, output on, terminates ADC B with a 50 ohm source; the SDG into ADC A ------------
    hp.output(on=False, load=50)
    hp.dc(0.0)
    hp.output(on=True)
    b.record("gen", quiet=True, source="hp", wave="dc", volts=0.0, on=True)
    for fr in (3e6, 10e6, 30e6):
        b.tone("sdg1", fr, 1.0)
        time.sleep(0.4)
        xs = caps()
        aa = np.mean([fast.fit(x[:, 0], fr, FS)[0] for x in xs])
        # B at the same frequency: the SDG is not on the board's clock, so fit its frequency from A first
        bb = []
        for x in xs:
            n = len(x); w = np.blackman(n)
            sa = np.abs(np.fft.rfft((x[:, 0] - x[:, 0].mean()) * w)); k = int(np.argmax(sa))
            sb = np.abs(np.fft.rfft((x[:, 1] - x[:, 1].mean()) * w))
            bb.append(sb[max(k - 2, 0):k + 3].max() / sa[max(k - 2, 0):k + 3].max())
        db = 20 * np.log10(np.mean(bb))
        res["1c"].append(dict(freq=fr, a=aa, b_dbc=db))
        print("1c  %4.1f MHz 1 Vpp into ADC A (%.0f codes): ADC B sees %6.1f dBc" % (fr / 1e6, aa, db), flush=True)
finally:
    failed = b.generators_off()
    print("generators off%s" % ("" if not failed else ": FAILED to switch " + "; ".join(failed)), flush=True)
    json.dump(res, open(OUT, "w"), indent=1)
