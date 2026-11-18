"""CONFIGS 1e on board A: the two ADC channels' timing skew, with one sine into both through a BNC tee.

SDG CH1 -> BNC tee -> two equal BNC-SMA cables -> J101 ADC A IN and J102 ADC B IN (JP101, JP201 TERM in: the tee sees
25 ohm).  The SDG is set to 1 Vpp across 50 ohm, so each input gets about 0.67 Vpp.  At each frequency both channels
are fitted at the SDG's frequency (1d: the SDG runs 1.1 ppm slow against the TCXO) and B - A is taken in phase; over
the frequencies, phase = phi0 + 360 f tau: tau is the time skew, phi0 the front ends' phase.  The fit's phase is
phi in cos(wt + phi), and a delay d makes phi = -w d: so a positive tau means B is EARLIER, its path the shorter (the
sense of the tutorial's 1.08, "B's path 0.6 to 0.7 ns the shorter").
Three ADC clockings: capture.bit (the TCXO's 25 MHz straight to both ADC clock pins), fast.bit at 25 MS/s and at
62.5 MS/s (both clocks from one register).  Run from the tutorial repo's src/verilog.  SDG CH1 off at the end."""
import json
import subprocess
import sys
import time

import numpy as np

import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))      # bringup/, wherever the project is
sys.path.insert(0, "/home/jason/mudd/133electronics/ecp5-2adc-2dac-tutorial/src/verilog")
import bench                                        # noqa: E402
import capture                                      # noqa: E402
import fast                                         # noqa: E402

OUT = sys.argv[1]
SDG_PPM = -1.1
b = bench.Bench("A")


def phases(a, bb, f, fs):
    t = np.arange(len(a)) / fs
    M = np.column_stack([np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t), np.ones(len(a))])
    out = []
    for x in (a, bb):
        c, *_ = np.linalg.lstsq(M, x, rcond=None)
        out.append((np.hypot(c[0], c[1]), np.degrees(np.arctan2(-c[1], c[0]))))
    return out


def load(name):
    subprocess.run(["make", "load-" + name], check=True, capture_output=True)
    time.sleep(1.0)


res = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "runs": []}
try:
    for design, fs, freqs in (("capture", 25e6, (1e6, 3e6, 5e6, 7e6, 10e6)),
                              ("fast25", 25e6, (1e6, 3e6, 5e6, 7e6, 10e6)),
                              ("fast62", 62.5e6, (1e6, 5e6, 10e6, 15e6, 20e6, 25e6))):
        load("capture" if design == "capture" else "fast")
        if design != "capture":
            fa = fast.Fast(fast.find_port())
            fa.rate(5 if design == "fast25" else 2)
            fa.dacs(0)
        port = capture.find_port()
        rows = []
        for fr in freqs:
            b.tone("sdg1", fr, 1.0)
            time.sleep(0.4)
            f_true = fr * (1 + SDG_PPM * 1e-6)
            dph, amps = [], []
            for _ in range(4):
                if design == "capture":
                    _, A, B = capture.capture(port, 0)
                else:
                    x = fa.capture(); A, B = x[:, 0], x[:, 1]
                (aa, pa), (ab, pb) = phases(np.asarray(A, float), np.asarray(B, float), f_true, fs)
                dph.append((pb - pa + 180) % 360 - 180); amps.append((aa, ab))
            d = float(np.mean(dph)); sd = float(np.std(dph))
            ga = float(np.mean([q[1] / q[0] for q in amps]))
            rows.append(dict(freq=fr, dphase_deg=d, sd=sd, gain_b_over_a=ga, amp_a=float(np.mean([q[0] for q in amps]))))
            print("1e %-8s %5.1f MHz: B - A %+7.3f deg (+-%.3f), %+7.3f ns; B/A amplitude %.4f; A %.0f codes"
                  % (design, fr / 1e6, d, sd, d / 360 / fr * 1e9, ga, rows[-1]["amp_a"]), flush=True)
        F = np.array([r["freq"] for r in rows]); P = np.array([r["dphase_deg"] for r in rows])
        tau, phi0 = np.polyfit(F * 360, P, 1)
        resid = P - (tau * F * 360 + phi0)
        print("1e %-8s: B's path %+.3f ns the shorter, front ends' phase %+.3f deg, the fit within %.3f deg"
              % (design, tau * 1e9, phi0, np.abs(resid).max()), flush=True)
        res["runs"].append(dict(design=design, fs=fs, rows=rows, tau_ns=tau * 1e9, phi0_deg=phi0))
finally:
    b.tone_off("sdg1")
    print("SDG CH1 off", flush=True)
    json.dump(res, open(OUT, "w"), indent=1)
