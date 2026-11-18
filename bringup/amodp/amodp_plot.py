import sys, numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, "/home/jason/mudd/133electronics/ecp5-2adc-2dac-tutorial/src/verilog")
from amodp import TILES, expected
t = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "."

fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
for (p, lab, bn), col in zip((("/home/jason/mudd/133electronics/ecp5-2adc-2dac-tutorial/dev/data/amodp/ecp5_%s.npz" % t, "ECP5 board A, ADC A at 50 ohm", "ecp5"),
               ("/home/jason/mudd/133electronics/icepi-zero-dac-adc/dev/data/amodp/icepi_%s.npz" % t, "Icepi Zero, ADC 20.6 k", "icepi")), ("C0", "C1")):
    try: d = np.load(p)
    except Exception: continue
    o = np.argsort(d["f"]); f, h = d["f"][o], d["h"][o]
    vp = bool(d["via_p1"]) if "via_p1" in d.files else False
    a1.semilogx(f, 20 * np.log10(np.abs(h)), "o-", ms=2.5, lw=1, color=col, label=lab + (" (then p1)" if vp else ""))
    a2.semilogx(f, np.degrees(np.unwrap(np.angle(h))), "o-", ms=2.5, lw=1, color=col)
    e = expected(t, f, bn, vp) if t != "p0" else None
    if e is not None:
        a1.semilogx(f, 20 * np.log10(np.abs(e)), "--", color="k" if col == "C0" else "0.5", lw=1, label="expected, " + bn)
        a2.semilogx(f, np.degrees(np.unwrap(np.angle(e))), "--", color="k" if col == "C0" else "0.5", lw=1)
a1.set_ylabel("gain over the through (dB)" if t != "p0" else "gain from 1 kHz (dB)")
a2.set_ylabel("phase over the through (deg)" if t != "p0" else "phase (deg)"); a2.set_xlabel("frequency (Hz)")
a1.legend(fontsize=8); a1.grid(alpha=0.3, which="both"); a2.grid(alpha=0.3, which="both")
a1.set_title("AMOD-P %s: %s" % (t, TILES.get(t, "")), fontsize=11)
fig.tight_layout(); fig.savefig(OUT + "/amodp_both_%s.png" % t, dpi=85)
