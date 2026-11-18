"""amodp_fit_p4.py [TILE] [OUTDIR]: fit the real coil to board A's sweep of an AMOD-P p4 tile, then check it on the Icepi.

The handbook models L401 (TDK NLV32T-101J, 100 uH) as 100 uH in series with its 10 ohm DC resistance.  At 1 MHz a
ferrite coil loses more than its DC resistance says, and above a few MHz its own winding capacitance shows.  Fitted
model: the coil R(f) = R0 (f / 1.07 MHz)^k in series with L, both shunted by Cs; in series with the tile's C; between
board A's 50 ohm source and 50 ohm load.  Then the same coil goes between the Icepi's source and load (amodp.py's
BOARD_LOAD), with nothing fitted, and is compared with the Icepi's own sweep (its own AMOD-P board).
"""
import sys
import numpy as np
from scipy.optimize import least_squares
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TUT = "/home/jason/mudd/133electronics/ecp5-2adc-2dac-tutorial"
ICE = "/home/jason/mudd/133electronics/icepi-zero-dac-adc"
sys.path.insert(0, TUT + "/src/verilog")
from amodp import TILES, BOARD_LOAD, expected   # noqa: E402

t = sys.argv[1] if len(sys.argv) > 1 else "p4"
OUT = sys.argv[2] if len(sys.argv) > 2 else "."


def load(p):
    d = np.load(p)
    o = np.argsort(d["f"])
    return d["f"][o], d["h"][o]


def gain(p, f, board):
    r0, l, c, cs, k = p
    w = 2 * np.pi * f
    zl = r0 * (f / 1.07e6) ** k + 1j * w * l * 1e-6
    zl = zl / (1 + 1j * w * cs * 1e-12 * zl)
    z = zl + 1 / (1j * w * c * 1e-12)
    rs, r_l, c_l = BOARD_LOAD[board]
    zload = 1 / (1 / r_l + 1j * w * c_l)
    return (zload / (zload + rs + z)) / (zload / (zload + rs))


f, h = load(TUT + "/dev/data/amodp/ecp5_%s.npz" % t)
m = f > 2e3                                                    # the first point or two sit on the noise
s = least_squares(lambda p: (lambda r: np.r_[r.real, r.imag])(np.log(gain(p, f[m], "ecp5") / h[m])),
                  [10, 100, 220, 2, 1], bounds=([0, 50, 100, 0, 0], [500, 200, 500, 50, 3]))
r0, l, c, cs, k = s.x
n = m.sum()
print("%s on board A: coil %.1f ohm at 1.07 MHz (x f^%.2f), %.1f uH, self-C %.2f pF (SRF %.1f MHz); C %.1f pF; "
      "f0 %.4g MHz, Q %.2f (the coil alone: %.0f); misfit %.2f dB, %.1f deg rms"
      % (t, r0, k, l, cs, 1 / (2 * np.pi * np.sqrt(l * cs * 1e-18)) / 1e6, c,
         1 / (2 * np.pi * np.sqrt(l * c * 1e-18)) / 1e6, np.sqrt(l / c * 1e6) / (100 + r0), 2 * np.pi * 1.07e6 * l * 1e-6 / r0,
         np.sqrt(np.mean(s.fun[:n] ** 2)) * 20 / np.log(10), np.degrees(np.sqrt(np.mean(s.fun[n:] ** 2)))))

fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
for path, board, lab, col in ((TUT + "/dev/data/amodp/ecp5_%s.npz" % t, "ecp5", "ECP5 board A (50 ohm)", "C0"),
                              (ICE + "/dev/data/amodp/icepi_%s.npz" % t, "icepi", "Icepi Zero (20.6 k)", "C1")):
    fb, hb = load(path)
    fit = gain(s.x, fb, board)
    hb_ = expected(t, fb, board)
    i, j = np.argmax(np.abs(hb)), np.argmax(np.abs(fit))
    print("  %s: measured peak %+.1f dB at %.4g MHz; the fitted coil %+.1f dB at %.4g MHz; the handbook's %+.1f dB"
          % (board, 20 * np.log10(abs(hb[i])), fb[i] / 1e6, 20 * np.log10(abs(fit[j])), fb[j] / 1e6,
             20 * np.log10(np.abs(hb_).max())))
    a1.semilogx(fb, 20 * np.log10(np.abs(hb)), "o", ms=2.5, color=col, label=lab + ", measured")
    a1.semilogx(fb, 20 * np.log10(np.abs(fit)), "-", lw=1.2, color=col,
                label="the coil fitted to board A" + ("" if board == "ecp5" else ", on the Icepi's load (not fitted)"))
    a1.semilogx(fb, 20 * np.log10(np.abs(hb_)), ":", lw=1, color="k" if board == "ecp5" else "0.5",
                label="the handbook's circuit (10 ohm coil), " + board)
    a2.semilogx(fb, np.degrees(np.unwrap(np.angle(hb))), "o", ms=2.5, color=col)
    a2.semilogx(fb, np.degrees(np.unwrap(np.angle(fit))), "-", lw=1.2, color=col)
    a2.semilogx(fb, np.degrees(np.unwrap(np.angle(hb_))), ":", lw=1, color="k" if board == "ecp5" else "0.5")
a1.set_ylabel("gain over the through (dB)"); a2.set_ylabel("phase over the through (deg)"); a2.set_xlabel("frequency (Hz)")
a1.legend(fontsize=7.5, loc="lower center"); a1.grid(alpha=0.3, which="both"); a2.grid(alpha=0.3, which="both")
a1.set_title("AMOD-P %s: %s\nthe coil fitted to board A: %.0f ohm at 1.07 MHz (rising as f^%.1f), %.0f uH, %.1f pF across it (SRF %.0f MHz); C %.0f pF"
             % (t, TILES.get(t, ""), r0, k, l, cs, 1 / (2 * np.pi * np.sqrt(l * cs * 1e-18)) / 1e6, c), fontsize=9)
fig.tight_layout()
fig.savefig(OUT + "/amodp_fit_%s.png" % t, dpi=85)
