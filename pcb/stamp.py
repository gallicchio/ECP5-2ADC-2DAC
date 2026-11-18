#!/usr/bin/env python3
"""A readable postage stamp of one region of a finished board, one panel per routing layer,
with the router's fan-out lanes drawn over it -- what pcb/route_diag2.py shows as a raster,
here as the real geometry at a scale where a 0.4 mm pitch can be read.

    python3 pcb/stamp.py BOARD.kicad_pcb X0 Y0 X1 Y1 [net-substring ...]

Writes build/scratch/diag/stamp_<x0>_<y0>.png.  Pads grey, tracks white (the named nets
cyan, GND dim), vias red rings, the FPGA exits as small marks, lanes as a yellow wash
(parallel steps cost more) and orange (parallel steps impossible)."""
import os, sys, re, math
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_pcb as BP, router as R, route_diag2 as D
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
import numpy as np

LN = ["F.Cu", "In2.Cu", "In3.Cu", "B.Cu"]


def main():
    board = sys.argv[1]
    x0, y0, x1, y1 = map(float, sys.argv[2:6])
    want = sys.argv[6:]
    b = BP.Build(); b.place(); b.bga(); b.grid()
    G = b.G
    tracks, vias = D.load_board(board)
    fig, axes = plt.subplots(1, 4, figsize=(26, 7.5))
    i0, j0 = G.cell(x0, y0); i1, j1 = G.cell(x1, y1)
    lane = np.zeros((j1 - j0 + 1, i1 - i0 + 1))
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            lane[j - j0, i - i0] = G.lane[j * G.nx + i]
    for L, ax in enumerate(axes):
        ax.set_facecolor("black")
        # lanes: a wash
        img = np.zeros(lane.shape + (4,))
        img[(lane == 1) | (lane == 2)] = (1.0, 0.9, 0.2, 0.25)
        img[(lane == 3) | (lane == 4)] = (1.0, 0.5, 0.0, 0.45)
        ax.imshow(img, extent=((i0 - 0.5) * G.pitch, (i1 + 0.5) * G.pitch, (j1 + 0.5) * G.pitch, (j0 - 0.5) * G.pitch), origin="upper", interpolation="nearest")
        # pads of this layer
        for key, p in b.pads.items():
            if not (x0 - 2 < p["x"] < x1 + 2 and y0 - 2 < p["y"] < y1 + 2):
                continue
            if not (p["th"] or BP.LIDX[p["layer"]] == L):
                continue
            col = (0.55, 0.55, 0.55) if key[0] != "U1" else (0.35, 0.35, 0.35)
            if any(w in (p["net"] or "") for w in want):
                col = (0.0, 0.8, 0.9)
            if p["shape"] == "circle":
                ax.add_patch(Circle((p["x"], p["y"]), p["w"] / 2.0, color=col))
            else:
                r = math.radians(p["rot"]); c, s = math.cos(r), math.sin(r)
                w, h = p["w"], p["h"]
                cx, cy = p["x"] - (c * w - s * h) / 2.0, p["y"] - (s * w + c * h) / 2.0
                ax.add_patch(Rectangle((cx, cy), w, h, angle=p["rot"], color=col))
        for (lay, ax0, ay0, ax1, ay1, net, w) in tracks:
            if lay != LN[L]:
                continue
            if max(ax0, ax1) < x0 - 1 or min(ax0, ax1) > x1 + 1 or max(ay0, ay1) < y0 - 1 or min(ay0, ay1) > y1 + 1:
                continue
            col = "white"
            if net == "GND":
                col = (0.4, 0.4, 0.4)
            if any(wd in net for wd in want):
                col = (0.0, 0.9, 1.0)
            ax.plot([ax0, ax1], [ay0, ay1], color=col, lw=max(0.8, w * 14), solid_capstyle="round")
        for (vx, vy, net, size, drill) in vias:
            if x0 - 1 < vx < x1 + 1 and y0 - 1 < vy < y1 + 1:
                col = (0.9, 0.2, 0.2)
                if any(wd in net for wd in want):
                    col = (0.0, 0.9, 1.0)
                ax.add_patch(Circle((vx, vy), size / 2.0, fill=False, color=col, lw=1.2))
        for net, (eL, ex, ey) in b.esc["exits"].items():
            if eL == L and x0 < ex < x1 and y0 < ey < y1:
                col = (0.0, 0.9, 1.0) if any(wd in net for wd in want) else (1.0, 0.3, 1.0)
                ax.plot(ex, ey, "+", color=col, ms=6, mew=1.2)
        ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect("equal")
        ax.set_title("%s   %s" % (LN[L], os.path.basename(board)), fontsize=9)
        ax.grid(True, color=(0.2, 0.2, 0.2), lw=0.3)
    fig.suptitle("lanes: yellow = steps along the face/row cost %gx, orange = impossible; vias red, exits magenta; %s cyan" % (R.LANE_PEN, ", ".join(want) or "-"), fontsize=9)
    out = os.path.join(ROOT, "build", "scratch", "diag", "stamp_%s_%d_%d.png" % (os.path.basename(board).replace(".kicad_pcb", ""), x0, y0))
    fig.savefig(out, dpi=80, bbox_inches="tight"); plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    main()
