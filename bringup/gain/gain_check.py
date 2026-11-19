#!/usr/bin/env python3
"""Channel A's gain at x1, x10 and x100, with the flash's bring-up design (ecp5bu): a cable from J204 DAC 1 OUT to J101
ADC A IN, JP101 TERM in, JP102 on SMA.  The same DAC sine is read at each gain, so each ratio does not depend on the DAC's
own accuracy; a DC staircase at x1 gives the absolute scale (ADC codes per DAC code: 0.25 by design, both ends +-1 V into
50 ohm); a sweep at x1 and x100 gives the x100 stages' frequency response.

    python3 gain_check.py x1        # all four GAIN shunts in
    python3 gain_check.py x10       # JP103 out: the first stage at x10.1
    python3 gain_check.py x100      # JP103 and JP104 out
    python3 gain_check.py x10b      # JP103 back in, JP104 out: the second stage alone at x10.1
    python3 gain_check.py --analyze

Saves gain_<stage>.npz here.  (For bringup/noise/johnson.py: its G0 assumes 2048 codes/V x 10.1^2.)
"""
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "gateware", "bringup", "host"))
F0 = 100e3
PLAN = {"x1": dict(shifts=[1, 4, 5, 8], dc=True, sweep=1), "x10": dict(shifts=[4, 5, 8], dc=False, sweep=4),
        "x100": dict(shifts=[7, 8, 9], dc=False, sweep=8), "x10b": dict(shifts=[4, 5, 8], dc=False, sweep=4)}
SWEEP = [100e3, 200e3, 500e3, 1e6, 2e6, 3e6, 5e6, 7e6, 10e6]


def board():
    import ecp5bu
    bd = ecp5bu.Board(ecp5bu.find_port())
    bd.gpio(dac_sleep=0, pdwn_a=0, pdwn_b=0)
    bd.dac_config(rate=50e6)
    bd.dac(2, "dc", code=8192)
    bd.adc_config(rate=25e6)
    return bd


def fit(t, x, f):
    m = np.column_stack([np.ones_like(t), np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t)])
    c, *_ = np.linalg.lstsq(m, x, rcond=None)
    r = x - m @ c
    return c[0], np.hypot(c[1], c[2]), np.arctan2(-c[2], c[1]), r.std()


def sine(bd, f, shift, n=4):
    fx = bd.dac(1, "sine", freq=f, shift=shift)
    time.sleep(0.05)
    out = []
    for _ in range(n):
        t, a, b, otr = bd.capture(8192)
        a = np.asarray(a, float)
        out.append(fit(np.asarray(t), a, fx) + (a.min(), a.max()))
    o = np.array(out)
    return fx, o[:, 1].mean(), o[:, 1].std() / np.sqrt(n), o[:, 3].mean(), o[:, 4].min(), o[:, 5].max(), o[:, 0].mean()


def measure(stage):
    bd = board()
    p = PLAN[stage]
    res = {"stage": stage, "t": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        rows = []
        for sh in p["shifts"]:
            fx, amp, eamp, rms, lo, hi, dc = sine(bd, F0, sh)
            rows.append((sh, fx, amp, eamp, rms, lo, hi, dc))
            print("%s  shift %d at %.0f Hz: ADC A amplitude %.3f +- %.3f codes (residual %.2f rms; codes %d..%d; mean %.1f)%s"
                  % (stage, sh, fx, amp, eamp, rms, lo, hi, dc, "  CLIPPED" if lo <= 0 or hi >= 4095 else ""), flush=True)
        res["sines"] = np.array(rows)
        if p["dc"]:
            drows = []
            for k in (-4096, -2048, 0, 2048, 4096):
                bd.dac(1, "dc", code=8192 + k)
                time.sleep(0.05)
                t, a, b, otr = bd.capture(8192)
                drows.append((8192 + k, np.mean(a)))
                print("%s  DAC code %5d: ADC A mean %.2f" % (stage, 8192 + k, drows[-1][1]), flush=True)
            d = np.array(drows)
            res["dc"] = d
            print("%s  slope %.5f ADC codes per DAC code (0.25 by design)" % (stage, np.polyfit(d[:, 0], d[:, 1], 1)[0]))
        if p["sweep"] is not None:
            srows = []
            for f in SWEEP:
                fx, amp, eamp, rms, lo, hi, dc = sine(bd, f, p["sweep"], n=2)
                srows.append((fx, amp, eamp))
                print("%s  sweep shift %d, %.3f MHz: %.3f codes" % (stage, p["sweep"], fx / 1e6, amp), flush=True)
            res["sweep"] = np.array(srows)
    finally:
        bd.dac(1, "dc", code=8192)                      # DAC 1 at 0 V (code 8192: the LED driver's 24 mA, were it working)
    np.savez(os.path.join(HERE, "gain_%s.npz" % stage), **res)
    print("saved gain_%s.npz" % stage)


def analyze():
    d = {s: np.load(os.path.join(HERE, "gain_%s.npz" % s)) for s in PLAN if os.path.exists(os.path.join(HERE, "gain_%s.npz" % s))}
    amp = {s: {int(r[0]): (r[2], r[3]) for r in d[s]["sines"]} for s in d}
    if "x1" in d:
        dc = d["x1"]["dc"]
        slope = np.polyfit(dc[:, 0], dc[:, 1], 1)[0]
        print("x1: %.5f ADC codes per DAC code (0.25 by design: %+.2f %%)" % (slope, (slope / 0.25 - 1) * 100))
    if "x1" in d and "x10" in d:
        for sh in (4, 5):
            if sh in amp["x1"] and sh in amp["x10"]:
                print("x10 / x1 at shift %d: %.4f (10.1 by design)" % (sh, amp["x10"][sh][0] / amp["x1"][sh][0]))
    if "x1" in d and "x10b" in d:
        for sh in (4, 5):
            print("x10b / x1 at shift %d: %.4f (the second stage; 10.1 by design)" % (sh, amp["x10b"][sh][0] / amp["x1"][sh][0]))
    if "x10b" in d and "x100" in d:
        print("x100 / x10b at shift 8: %.4f (the first stage, measured the other way)" % (amp["x100"][8][0] / amp["x10b"][8][0]))
    if "x10" in d and "x100" in d:
        g = amp["x100"][8][0] / amp["x10"][8][0]
        print("x100 / x10 at shift 8: %.4f (10.1 by design)" % g)
        if "x1" in d:
            g1 = amp["x10"][5][0] / amp["x1"][5][0]
            print("x100 / x1: %.2f (102.0 by design: %+.1f %%)" % (g * g1, (g * g1 / 102.01 - 1) * 100))
    if "x100" in d and "x1" in d and "sweep" in d["x100"].files:
        s100, s1 = d["x100"]["sweep"], d["x1"]["sweep"]
        r = (s100[:, 1] / s1[:, 1]) / (s100[0, 1] / s1[0, 1])
        print("x100's response against x1 (shift 8 against shift 1, normalised at 0.1 MHz):",
              " ".join("%.1f MHz %.3f" % (f / 1e6, x) for f, x in zip(s100[:, 0], r)))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--analyze":
        analyze()
    elif len(sys.argv) > 1 and sys.argv[1] in PLAN:
        measure(sys.argv[1])
    else:
        print(__doc__)
