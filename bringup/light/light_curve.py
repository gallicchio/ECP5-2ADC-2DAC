#!/usr/bin/env python3
"""Visit 3's light path on board A: DAC 1 drives the on-board LED D201 through the LED driver (JP2009 on LED: Q201, about
48 mA at full scale), and the photodiode D103's receiver (U105, 10 k transimpedance) feeds ADC B (JP1203 on PD, JP202 on
ALT, x1).  A white card over both closes the loop.  Needs the flash's bring-up design (a JTAG refresh) and its register
interface, ecp5bu.

    python3 light_curve.py LABEL          # e.g. nocard, card, dark: 17 LED currents, ADC B's mean and noise at each
    python3 light_curve.py --plot         # every saved run on one figure

Saves light_<LABEL>.npz here.
"""
import glob
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "gateware", "bringup", "host"))
CODES = np.linspace(0, 16383, 17).round().astype(int)
MA_FS = 48.0                                        # the LED driver's current at full scale (BRINGUP.md 5.4)


def run(label):
    import ecp5bu
    bd = ecp5bu.Board(ecp5bu.find_port())
    bd.gpio(dac_sleep=0, pdwn_a=0, pdwn_b=0)
    bd.dac_config(rate=50e6)
    bd.dac(2, "dc", code=8192)
    # The board's own LEDs dark (register mode, all off): the bring-up design blinks the RGB LED's green once a second,
    # and the photodiode sees it (2026-11-18 15:20: a +-26 code beat with no card).  Each point is the mean of one
    # statistics window of 2^20 samples at 1.5625 MS/s (0.67 s: the room light's 120 Hz averages out) that began after
    # the LED current changed; 2^20 x 4095 still fits the window's 32-bit sum.
    bd.leds(0, rgb=0)
    bd.adc_config(rate=1.5625e6, stats_log2=20)
    rows = []
    try:
        for code in list(CODES) + [0]:              # up, then off again (did the dark level come back?)
            bd.dac(1, "dc", code=int(code))
            time.sleep(0.05)
            seq0 = bd.rd("STATSEQ")
            while (bd.rd("STATSEQ") - seq0) & 0xFFFF < 2:
                time.sleep(0.05)
            st = bd.adc_stats()
            t, a, b, otr = bd.capture(8192)         # 5 ms of samples: the noise within it
            b = np.asarray(b, float)
            rows.append((code, MA_FS * code / 16384, st["b"]["mean"], b.std(), st["b"]["min"], st["b"]["max"], st["a"]["mean"]))
            print("code %5d  %5.1f mA   ADC B mean %8.2f  rms %5.2f  (%d..%d over 0.67 s)" % rows[-1][:6], flush=True)
    finally:
        bd.dac(1, "dc", code=0)                     # the LED off
        bd.leds(None)                               # the board's LEDs back to the chaser
    r = np.array(rows)
    np.savez(os.path.join(HERE, "light_%s.npz" % label), rows=r, label=label, t=time.strftime("%Y-%m-%d %H:%M:%S"))
    print("saved light_%s.npz; LED off" % label)


def plot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6))
    for p in sorted(glob.glob(os.path.join(HERE, "light_*.npz"))):
        d = np.load(p)
        r = d["rows"][:-1]
        mv = (r[:, 2] - 2048) / 2048 * 1000         # mV at the ADC (x1: 2048 codes a volt)
        a1.plot(r[:, 1], mv, "o-", ms=3.5, label="%s (%s)" % (str(d["label"]), str(d["t"])[11:16]))
        a2.plot(r[:, 1], r[:, 3], "o-", ms=3.5, label=str(d["label"]))
    a1.set_xlabel("LED current (mA, nominal)"); a1.set_ylabel("ADC B: the receiver's output (mV, from 0 V)")
    a1.set_title("the photodiode's receiver against the LED's current", fontsize=9); a1.grid(alpha=0.3); a1.legend(fontsize=8)
    a2.set_xlabel("LED current (mA, nominal)"); a2.set_ylabel("ADC B rms (codes)"); a2.grid(alpha=0.3)
    a2.set_title("its noise", fontsize=9); a2.legend(fontsize=8)
    fig.suptitle("Board A: D201 -> D103 (JP2009 LED, JP1203 PD, JP202 ALT, x1)", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "light_board_a.png"), dpi=100)
    print("saved light_board_a.png")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--plot":
        plot()
    elif len(sys.argv) > 1:
        run(sys.argv[1])
    else:
        print(__doc__)
