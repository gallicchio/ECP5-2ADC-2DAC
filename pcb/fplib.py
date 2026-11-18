"""Footprints as data: pads, courtyard, body outline, and the text that goes
into the board file.  Reads KiCad 10's own libraries and the local
easyeda.pretty (upgraded to the current format by `kicad-cli fp upgrade`)."""
import os, sys, math, re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "gen"))
from sexp import parse, kids, kid, val, head

KFP = os.environ.get("KICAD10_FOOTPRINTS", os.path.join(
    os.environ["HOME"], ".local/kicad10/AppDir/share/kicad/footprints"))
LOCAL = {"easyeda": os.path.join(ROOT, "library", "easyeda", "easyeda.pretty"),
         "ours": os.path.join(ROOT, "library", "ours.pretty")}


def libdir(lib):
    return LOCAL.get(lib) or os.path.join(KFP, lib + ".pretty")


def _num(node, i, default=0.0):
    try:
        return float(node[i][1])
    except Exception:
        return default


_cache = {}


def load(fpid):
    """fpid = "Lib:Name" -> dict(text, node, pads, crtyd, smd).
    pads: [dict(num, x, y, w, h, rot, shape, th, drill, layers, bga)] in the
    footprint's own frame (mm, y down).  crtyd: (x0, y0, x1, y1)."""
    if fpid in _cache:
        return _cache[fpid]
    lib, name = fpid.split(":", 1)
    path = os.path.join(libdir(lib), name + ".kicad_mod")
    text = open(path, encoding="utf-8").read()
    node = parse(text)[0]
    pads = []
    for p in kids(node, "pad"):
        at = kid(p, "at")
        sz = kid(p, "size")
        dr = kid(p, "drill")
        lay = kid(p, "layers")
        pads.append(dict(num=val(p), x=_num(at, 1), y=_num(at, 2), rot=_num(at, 3) if len(at) > 3 else 0.0,
                         w=_num(sz, 1), h=_num(sz, 2), shape=p[3][1] if len(p) > 3 else "rect",
                         th=(p[2][1] != "smd") if len(p) > 2 else False,
                         drill=_num(dr, 1) if dr else 0.0,
                         layers=[c[1] for c in (lay or [])[1:] if isinstance(c, tuple)],
                         bga=any(head(c) == "property" and len(c) > 1 and c[1][1] == "pad_prop_bga" for c in p if isinstance(c, list))))
    xs, ys = [], []
    sxs, sys_ = [], []
    for g in node:
        if not isinstance(g, list):
            continue
        h = head(g)
        if h not in ("fp_line", "fp_rect", "fp_circle", "fp_poly", "fp_arc"):
            continue
        layer = val(kid(g, "layer")) if kid(g, "layer") else ""
        pts = []
        if h == "fp_circle":
            c, e = kid(g, "center"), kid(g, "end")
            cx_, cy_ = _num(c, 1), _num(c, 2)
            r = math.hypot(_num(e, 1) - cx_, _num(e, 2) - cy_)
            pts = [(cx_ - r, cy_ - r), (cx_ + r, cy_ + r)]
        else:
            for k in ("start", "end", "mid"):
                c = kid(g, k)
                if c:
                    pts.append((_num(c, 1), _num(c, 2)))
        pp = kid(g, "pts")
        if pp:
            pts += [(_num(c, 1), _num(c, 2)) for c in kids(pp, "xy")]
        if layer == "F.CrtYd":
            xs += [q[0] for q in pts]; ys += [q[1] for q in pts]
        elif layer in ("F.SilkS", "F.Fab"):
            sxs += [q[0] for q in pts]; sys_ += [q[1] for q in pts]
    # the courtyard must contain the pads (easyeda's courtyards are the body only)
    pxs = [p["x"] - max(p["w"], p["h"]) / 2 - 0.25 for p in pads] + [p["x"] + max(p["w"], p["h"]) / 2 + 0.25 for p in pads]
    pys = [p["y"] - max(p["w"], p["h"]) / 2 - 0.25 for p in pads] + [p["y"] + max(p["w"], p["h"]) / 2 + 0.25 for p in pads]
    if not xs:
        xs = [min(sxs) - 0.25, max(sxs) + 0.25] if sxs else []
        ys = [min(sys_) - 0.25, max(sys_) + 0.25] if sys_ else []
    xs = xs + pxs; ys = ys + pys
    # the footprint's own attribute first (KiCad's USB-C receptacle is "(attr smd)" with four through-hole shell
    # pegs: JLCPCB's SMT line places it); only a footprint that says nothing is judged by its pads
    m = re.search(r"\(attr\s+([^)]*)\)", text)
    if m and "smd" in m.group(1).split():
        smd = True
    elif m and "through_hole" in m.group(1).split():
        smd = False
    else:
        smd = all(not p["th"] for p in pads) if pads else True
    # smd: what fits it (the SMT line, even with through-hole pegs); th_any: it has a hole through the board, so it
    # occupies both sides for placement and silkscreen
    th_any = any(p["th"] for p in pads)
    fp = dict(id=fpid, name=name, text=text, node=node, pads=pads, smd=smd, th_any=th_any,
              crtyd=(min(xs), min(ys), max(xs), max(ys)))
    _cache[fpid] = fp
    return fp


def _rot(px, py, rot):
    a = math.radians(-rot)
    return px * math.cos(a) - py * math.sin(a), px * math.sin(a) + py * math.cos(a)


def pads_at(fp, x, y, rot, back=False):
    """Pads in board coordinates for a footprint at (x, y, rot); on the back
    the footprint is mirrored about its y axis before rotating."""
    out = []
    for p in fp["pads"]:
        px, py = (-p["x"], p["y"]) if back else (p["x"], p["y"])
        rx, ry = _rot(px, py, rot)
        q = dict(p)
        q["x"], q["y"] = x + rx, y + ry
        q["rot"] = (p["rot"] + rot) % 360.0
        if back:
            q["rot"] = (-p["rot"] + rot) % 360.0
        out.append(q)
    return out


def box_at(fp, x, y, rot, back=False, grow=0.0):
    x0, y0, x1, y1 = fp["crtyd"]
    if back:
        x0, x1 = -x1, -x0
    pts = [_rot(px, py, rot) for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    return (x + min(p[0] for p in pts) - grow, y + min(p[1] for p in pts) - grow,
            x + max(p[0] for p in pts) + grow, y + max(p[1] for p in pts) + grow)


def pad_rect(p):
    """(cx, cy, hw, hh, angle) for clearance checks."""
    return (p["x"], p["y"], p["w"] / 2.0, p["h"] / 2.0, p["rot"])


def gap_to_pad(px, py, p):
    cx, cy, hw, hh, ang = pad_rect(p)
    a = math.radians(ang)
    dx, dy = px - cx, py - cy
    ux = dx * math.cos(a) - dy * math.sin(a)
    uy = dx * math.sin(a) + dy * math.cos(a)
    if p["shape"] == "circle":
        return max(0.0, math.hypot(dx, dy) - hw)
    gx, gy = max(0.0, abs(ux) - hw), max(0.0, abs(uy) - hh)
    return math.hypot(gx, gy)
