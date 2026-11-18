#!/usr/bin/env python3
"""Visit 3's noise source on board A (2026-11-18): the Johnson noise of SW101's resistors, seen by both ADCs at once.

Set-up: JP102 (ADC A SRC) on NOISE, JP202 (ADC B SRC) on ALT with JP1203 on NOISE, so both preamps (U101, U102, OPA1612)
look at the one node of J105 NOISE; all four GAIN shunts out (x10.1 x 10.1 each channel); SW101 one switch on: 0, 100,
1 k, 10 k ohm to ground (R1401-R1404).  The tutorial's fast.bit, both ADCs at 62.5 MS/s, 8192-pair records
(`noise_rec.py`, then `noise_seq.py 12 40`: 40 captures a segment, 13 s, SW101 moved by hand; its log is
`noise_seq_2026-11-18.log`).

    python3 johnson.py --reduce RAWDIR     # the raw records (not kept: 42 MB) -> johnson_spectra.npz (kept)
    python3 johnson.py                     # the analysis and the figure, from johnson_spectra.npz

What the node carries beyond the 0 ohm case (whatever does not depend on R is subtracted with it):
    S_node(f) = (4 k T R + i2 R^2) / (1 + (2 pi f R C)^2)
the resistor's own noise and the two preamps' input current noise (i2 = i_A^2 + i_B^2) across the node's impedance
R || C.  The ADCs read it times G0^2 H(f): G0 = 2048 codes/V at x1 times 10.1^2, H the two stages' poles (taken at 6
MHz: the OPA1612's GBW over 10.1).  The current noise rises below about 0.4 MHz, so the numbers come from where the
spectra are flat: 1 k at 0.6-4 MHz gives i2 (with T = 300 K), 100 ohm there then gives 4kT, and 10 k's roll-off from
its 0.3-0.55 MHz plateau gives C.  Errors from the scatter of the 13 s segments.
"""
import argparse
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SPECTRA = os.path.join(HERE, "johnson_spectra.npz")
G0 = 2048.0 * 10.1 ** 2                 # codes per volt at the node: x1 is +-1 V over 4096 codes; two stages 1 + 9.1k/1k
KB = 1.380649e-23
# which segments of the continuous record had which resistor, read from the record itself (the means step and the
# levels change at each move); the moves and the bump of the Fluke's probe are left out.  "R0/j" is the 400-capture
# run just before (14:36:34-14:38:46, 0 ohm), cut into ten chunks of 40.
SEGMENTS = {"0": ["R0/%d" % j for j in range(10)] + list(range(0, 5)), "100": list(range(6, 16)),
            "1k": [17] + list(range(19, 27)), "10k": list(range(28, 55))}
LEFT_OUT = {5: "0 -> 100 (the switch moving)", 16: "100 -> 1k", 18: "the Fluke's probe bumped (Jason)", 27: "1k -> 10k"}
R_OHM = {"0": 0.0, "100": 100.0, "1k": 1e3, "10k": 1e4}
EDGES = np.geomspace(180e3, 12e6, 23)   # log bands, 12 a decade: at least 5 FFT bins (7.6 kHz) each, so a band
#   median rejects the narrow lines; from 0.18 MHz, above the 120 kHz pair (1.13) that swamps the bands below


def spectra(recs, fs):
    n = recs.shape[1]
    w = np.hanning(n)
    norm = fs * (w ** 2).sum() / 2
    a = np.fft.rfft((recs[:, :, 0] - recs[:, :, 0].mean(1, keepdims=True)) * w, axis=1)
    b = np.fft.rfft((recs[:, :, 1] - recs[:, :, 1].mean(1, keepdims=True)) * w, axis=1)
    return (np.abs(a) ** 2).mean(0) / norm, (np.abs(b) ** 2).mean(0) / norm, (a * np.conj(b)).mean(0) / norm


def banded(f, y):
    """The median of y in each log band (robust to the narrow interference lines)."""
    return np.array([np.median(y[(f >= lo) & (f < hi)]) for lo, hi in zip(EDGES[:-1], EDGES[1:])])


def reduce(raw):
    r0 = np.load(os.path.join(raw, "board_a_R0.npz"))
    fs = float(r0["fs"])
    n = r0["rec"].shape[1]
    f = np.fft.rfftfreq(n, 1 / fs)
    per, tot = {}, {}
    for name, segs in SEGMENTS.items():
        rows, sums = [], [0.0, 0.0, 0.0j]
        for s in segs:
            if isinstance(s, str):
                j = int(s.split("/")[1])
                rec = r0["rec"][40 * j:40 * (j + 1)].astype(float)
            else:
                rec = np.load(os.path.join(raw, "seq", "seg_%03d.npz" % s))["rec"].astype(float)
            pa, pb, pab = spectra(rec, fs)
            rows.append(np.array([banded(f, pa), banded(f, pb), banded(f, pab.real), banded(f, pab.imag)]))
            sums = [sums[0] + pa, sums[1] + pb, sums[2] + pab]
        per[name] = np.array(rows)
        tot[name] = [x / len(segs) for x in sums]
        print("%-4s %d segments of 40 captures" % (name, len(segs)))
    timeline = []
    for i in range(55):
        d = np.load(os.path.join(raw, "seq", "seg_%03d.npz" % i))
        band = (f > 100e3) & (f < 1e6)
        timeline.append((float(d["t0"]), np.median(d["pab"].real[band]), np.median(d["paa"][band]), d["rec"][:, :, 0].mean()))
    np.savez_compressed(SPECTRA, f=f, fs=fs, n=n, edges=EDGES, timeline=np.array(timeline), left_out=str(LEFT_OUT),
                        **{"%s_seg" % k: v for k, v in per.items()},
                        **{"%s_%s" % (k, q): v[i].astype(np.complex64 if q == "pab" else np.float32)
                           for k, v in tot.items() for i, q in enumerate(("paa", "pbb", "pab"))})
    print("saved", SPECTRA)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reduce", metavar="RAWDIR")
    a = ap.parse_args()
    if a.reduce:
        reduce(a.reduce)
    d = np.load(SPECTRA)
    edges = d["edges"]
    fb = np.sqrt(edges[:-1] * edges[1:])
    H = 1 / (1 + (fb / 6e6) ** 2) ** 2                      # the two x10.1 stages, poles taken at 6 MHz (GBW / 10.1)
    m, e = {}, {}                                             # mean, error (segment scatter / sqrt n): paa, pbb, Re, Im
    for k in R_OHM:
        s = d[k + "_seg"]
        m[k] = s.mean(0)
        e[k] = s.std(0, ddof=1) / np.sqrt(len(s))
    # the shared part beyond 0 ohm, at the node: V^2/Hz (the chain's nominal gain and poles divided out)
    v = {k: (m[k][2] - m["0"][2]) / G0 ** 2 / H for k in ("100", "1k", "10k")}
    ev = {k: np.hypot(e[k][2], e["0"][2]) / G0 ** 2 / H for k in v}
    hi = (fb > 0.6e6) & (fb < 4e6)                            # where 100 ohm and 1 k are flat (1 k's RC corner is ~8 MHz)
    plat = (fb > 0.3e6) & (fb < 0.55e6)                       # 10 k's plateau, below its RC corner
    kt300 = 4 * KB * 300
    v100, v1k = np.median(v["100"][hi]), np.median(v["1k"][hi])
    i2 = (v1k - kt300 * 1e3) / 1e6                            # with T = 300 K: what 1 k has beyond 4kTR
    kt4 = (v100 - i2 * 1e4) / 100                             # then 100 ohm's 4kT (the current noise is 4 % of it)
    e100 = 1.2533 * np.sqrt(np.mean(ev["100"][hi] ** 2) / hi.sum())     # the median's error
    ekt4 = e100 / 100
    p10 = np.median(v["10k"][plat])
    from scipy.optimize import least_squares
    sel = (fb > 0.3e6) & (fb < 3e6)
    fitc = least_squares(lambda q: np.log(v["10k"][sel]) - np.log(q[0] / (1 + (2 * np.pi * fb[sel] * 1e4 * q[1]) ** 2)),
                         [p10, 20e-12], x_scale=[p10, 20e-12])
    p10f, cnode = fitc.x
    i2_10k = (p10f - kt300 * 1e4) / 1e8
    print("the shared part beyond 0 ohm, at the node (nV/rtHz; the chain's nominal gain x %.0f codes/V divided out):" % G0)
    print("  100 ohm %.2f (0.6-4 MHz; 4kTR at 300 K: %.2f);  1 k %.2f (0.6-4 MHz; 4kTR %.2f);  10 k %.1f (0.3-0.55 MHz; 4kTR %.1f)"
          % (np.sqrt(v100) * 1e9, np.sqrt(kt300 * 100) * 1e9, np.sqrt(v1k) * 1e9, np.sqrt(kt300 * 1e3) * 1e9,
             np.sqrt(p10) * 1e9, np.sqrt(kt300 * 1e4) * 1e9))
    print("  the preamps' input current noise, both together, with T = 300 K: %.1f pA/rtHz from 1 k (0.6-4 MHz), %.1f from 10 k's "
          "plateau (0.3-0.55 MHz); each about %.1f; the data sheet 1.7 at 1 kHz" % (np.sqrt(i2) * 1e12, np.sqrt(i2_10k) * 1e12,
                                                                                   np.sqrt(i2 / 2) * 1e12))
    print("  the node: 10 k rolls off as one pole at %.2f MHz: C = %.0f pF" % (1 / (2 * np.pi * 1e4 * cnode) / 1e6, cnode * 1e12))
    print("  from 100 ohm, less 1 k's current noise: 4kT = %.3g +- %.2g J: T = %.0f +- %.0f K, or k_B = %.3g +- %.2g J/K at 300 K"
          % (kt4, ekt4, kt4 / 4 / KB, ekt4 / 4 / KB, kt4 / 1200, ekt4 / 1200))
    coh0 = m["0"][2] / np.sqrt(m["0"][0] * m["0"][1])
    lo = (fb > 0.18e6) & (fb < 1e6)
    print("  0 ohm: the channels share %.0f %% of their noise power at 0.18-1 MHz, %.0f %% at 1-5 MHz; at the node, "
          "%.1f nV/rtHz shared and %.1f in A alone (0.18-1 MHz)"
          % (100 * np.median(coh0[lo]), 100 * np.median(coh0[(fb > 1e6) & (fb < 5e6)]),
             np.sqrt(np.median(m["0"][2][lo]) / G0 ** 2) * 1e9, np.sqrt(np.median(m["0"][0][lo]) / G0 ** 2) * 1e9))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(17, 5.4))
    cols = {"100": "C0", "1k": "C1", "10k": "C3"}
    ff = np.geomspace(1.8e5, 1.2e7, 200)
    for k in ("100", "1k", "10k"):
        r = R_OHM[k]
        vv = np.clip(v[k], 1e-30, None)
        a1.errorbar(fb / 1e6, np.sqrt(vv) * 1e9, yerr=0.5 * ev[k] / np.sqrt(vv) * 1e9, fmt="o", ms=3.5, color=cols[k],
                    label="%s ohm" % k.replace("k", " k"))
        a1.loglog(ff / 1e6, np.sqrt((kt300 * r + i2 * r * r) / (1 + (2 * np.pi * ff * r * cnode) ** 2)) * 1e9, "-",
                  color=cols[k], lw=1)
        a1.loglog(ff / 1e6, np.sqrt(kt300 * r) * 1e9 * np.ones_like(ff), ":", color=cols[k], lw=0.9)
    a1.set_xlabel("frequency (MHz)"); a1.set_ylabel("nV/rtHz at the node")
    a1.set_title("the two channels' shared noise beyond 0 ohm.  dotted: 4kTR at 300 K;\nlines: 4kTR + (%.1f pA/rtHz x R)^2, "
                 "across R || %.0f pF" % (np.sqrt(i2) * 1e12, cnode * 1e12), fontsize=9)
    a1.grid(alpha=0.3, which="both"); a1.legend(fontsize=8); a1.set_ylim(0.5, 200)
    f = d["f"]
    sm = lambda x: np.convolve(x, np.ones(9) / 9, mode="same")
    band = (f > 50e3) & (f < 12e6)
    for q, lab, col in (("0_paa", "ADC A alone", "C0"), ("0_pbb", "ADC B alone", "C1")):
        a2.loglog(f[band] / 1e6, np.sqrt(sm(d[q])[band] / G0 ** 2) * 1e9, lw=0.7, color=col, label=lab)
    a2.loglog(f[band] / 1e6, np.sqrt(np.clip(sm(d["0_pab"].real), 1e-30, None)[band] / G0 ** 2) * 1e9, lw=0.7, color="k",
              label="shared (Re A x B*)")
    a2.axhline(np.sqrt(kt300 * 100) * 1e9, color="C0", ls=":", lw=0.8)
    a2.text(0.06, np.sqrt(kt300 * 100) * 1e9 * 1.1, "4kTR, 100 ohm", fontsize=8, color="C0")
    a2.set_xlabel("frequency (MHz)"); a2.set_ylabel("nV/rtHz, referred to the node")
    a2.set_title("SW101 at 0 ohm: the floor every resistor sits on;\nmost of it is shared by the two channels", fontsize=9)
    a2.grid(alpha=0.3, which="both"); a2.legend(fontsize=8); a2.set_ylim(0.5, 100)
    tl = d["timeline"]
    t = (tl[:, 0] - tl[0, 0]) / 60
    a3.semilogy(t, tl[:, 1], "o-", ms=3, label="shared (Re A x B*), 0.1-1 MHz median")
    a3.semilogy(t, tl[:, 2], "s-", ms=3, mfc="none", label="ADC A alone")
    for j in eval(str(d["left_out"])):
        a3.axvline(t[j], color="0.6", lw=0.8, ls="--")
    for k, segs in SEGMENTS.items():
        s_ = [x for x in segs if not isinstance(x, str)]
        a3.text(np.mean(t[s_]), 3e-4, k + " ohm", ha="center", fontsize=9)
    a3.set_xlabel("minutes from 14:39:26"); a3.set_ylabel("codes^2/Hz"); a3.grid(alpha=0.3, which="both")
    a3.set_title("the continuous record, SW101 moved by hand\n(dashed: left out: the moves, a bumped probe)", fontsize=9)
    a3.legend(fontsize=8, loc="center right"); a3.set_ylim(5e-7, 6e-4)
    fig.suptitle("Board A, 2026-11-18: SW101's resistors seen by both ADC channels at x100 (JP102 NOISE, JP202 ALT, JP1203 NOISE)",
                 fontsize=10)
    fig.tight_layout()
    out = os.path.join(HERE, "johnson_board_a.png")
    fig.savefig(out, dpi=100)
    print("saved", out)


if __name__ == "__main__":
    main()
