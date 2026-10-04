"""Render the board (or a window of it) to a PNG so it can be looked at.
    python3 pcb/plot.py out.png [x0 y0 x1 y1] [--back]"""
import os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "gen")); sys.path.insert(0, HERE)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Polygon
from sexp import parse, kids, kid, val, head
import fplib

COL = {"F.Cu": "#d04040", "In1.Cu": "#50a050", "In2.Cu": "#d0a000", "In3.Cu": "#d060d0", "In4.Cu": "#40a0a0",
       "B.Cu": "#4060e0", "F.SilkS": "#e8e8e8", "B.SilkS": "#a0a0ff", "Edge.Cuts": "#f0f000"}


def num(node, i):
    return float(node[i][1])


def rot(x, y, a):
    r = math.radians(-a)
    return x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)


def render(path, png, x0=0, y0=0, x1=None, y1=None, back=False, refs=True, dpi=100):
    from place import BW, BH
    x1 = BW if x1 is None else x1
    y1 = BH if y1 is None else y1
    doc = parse(open(path, encoding="utf-8").read())[0]
    scale = min(2400.0 / (x1 - x0), 2400.0 / (y1 - y0))
    fig = plt.figure(figsize=((x1 - x0) * scale / dpi, (y1 - y0) * scale / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_facecolor("#101418")
    lw = lambda w: max(0.4, w * scale / 25.4 * 72 / dpi * 0.98)
    side = "B" if back else "F"
    for node in doc:
        if not isinstance(node, list):
            continue
        h = head(node)
        if h == "segment":
            s, e = kid(node, "start"), kid(node, "end")
            lyr = val(kid(node, "layer"))
            if back and lyr == "F.Cu" or (not back and lyr == "B.Cu"):
                alpha = 0.25
            else:
                alpha = 0.9
            ax.plot([num(s, 1), num(e, 1)], [num(s, 2), num(e, 2)], color=COL.get(lyr, "#888"), lw=lw(num(kid(node, "width"), 1)),
                    solid_capstyle="round", alpha=alpha, zorder=3 if lyr in ("F.Cu", "B.Cu") else 2)
        elif h == "via":
            a = kid(node, "at")
            ax.add_patch(Circle((num(a, 1), num(a, 2)), num(kid(node, "size"), 1) / 2, color="#e8e8e8", zorder=4))
        elif h in ("gr_line", "gr_arc"):
            lyr = val(kid(node, "layer"))
            if lyr in ("Edge.Cuts", side + ".SilkS"):
                s, e = kid(node, "start"), kid(node, "end")
                ax.plot([num(s, 1), num(e, 1)], [num(s, 2), num(e, 2)], color=COL[lyr], lw=1.0 if lyr == "Edge.Cuts" else 0.8, zorder=5)
        elif h == "gr_text":
            lyr = val(kid(node, "layer"))
            if lyr == side + ".SilkS":
                a = kid(node, "at")
                sz = num(kid(kid(kid(node, "effects"), "font"), "size"), 1)
                ax.text(num(a, 1), num(a, 2), val(node), color="#f0f0f0", fontsize=max(4, sz * scale / dpi * 72 * 0.8 / 2.2),
                        ha="left", va="bottom", zorder=6)
        elif h == "zone":
            pass
        elif h == "footprint":
            a = kid(node, "at")
            fx, fy = num(a, 1), num(a, 2)
            fa = num(a, 3) if len(a) > 3 else 0.0
            lyr = val(kid(node, "layer"))
            mine = (lyr == "B.Cu") == back
            if not (x0 - 15 < fx < x1 + 15 and y0 - 15 < fy < y1 + 15):
                continue
            ref = ""; refat = None; refsilk = False
            for pr in kids(node, "property"):
                if val(pr) == "Reference":
                    ref = val(pr, 2)
                    at = kid(pr, "at"); refat = (num(at, 1), num(at, 2))
                    refsilk = val(kid(pr, "layer")).endswith("SilkS")      # F.Fab designators are not printed: drawn dim
            for ln in kids(node, "fp_line") + kids(node, "fp_rect"):
                ll = val(kid(ln, "layer"))
                if ll not in ("F.CrtYd", "B.CrtYd", "F.SilkS", "B.SilkS"):
                    continue
                if (ll.startswith("B.")) != back:
                    continue
                s, e = kid(ln, "start"), kid(ln, "end")
                p = rot(num(s, 1), num(s, 2), fa); q = rot(num(e, 1), num(e, 2), fa)
                c = "#505050" if ll.endswith("CrtYd") else "#d0d0d0"
                if head(ln) == "fp_rect":
                    xs = [p[0], q[0], q[0], p[0], p[0]]; ys = [p[1], p[1], q[1], q[1], p[1]]
                    ax.plot([fx + v for v in xs], [fy + v for v in ys], color=c, lw=0.5, zorder=2)
                else:
                    ax.plot([fx + p[0], fx + q[0]], [fy + p[1], fy + q[1]], color=c, lw=0.5, zorder=2)
            for p in kids(node, "pad"):
                pa = kid(p, "at")
                px, py = rot(num(pa, 1), num(pa, 2), fa)
                pr_ = num(pa, 3) if len(pa) > 3 else 0.0
                sz = kid(p, "size")
                w, hh = num(sz, 1), num(sz, 2)
                th = p[2][1] != "smd"
                col = "#f0c040" if th else ("#d04040" if mine else "#4060e0")
                if abs(pr_ % 180 - 90) < 1:
                    w, hh = hh, w
                alpha = 0.9 if (mine or th) else 0.3
                ax.add_patch(Rectangle((fx + px - w / 2, fy + py - hh / 2), w, hh, color=col, alpha=alpha, zorder=3 if mine else 1))
            if refs and ref and mine:
                rx, ry = rot(refat[0], refat[1], fa) if refat else (0, 0)
                ax.text(fx + rx, fy + ry, ref, color="#ffffff" if refsilk else "#5a5a5a", fontsize=max(3, 0.9 * scale / dpi * 72 * 0.8 / 2.2), ha="center", va="center", zorder=7)
    ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect("equal"); ax.axis("off")
    fig.savefig(png, dpi=dpi, facecolor="#101418")
    plt.close(fig)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    png = a[0]
    win = [float(v) for v in a[1:5]] if len(a) >= 5 else []
    render(os.path.join(ROOT, "ECP5-2ADC-2DAC.kicad_pcb"), png, *win, back="--back" in sys.argv, refs="--norefs" not in sys.argv)
    print("wrote", png)
