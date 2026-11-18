"""Widen the rails after routing, where there is room.

The router lays a rail no wider than the finest pad on its net (a 0.25 mm LQFP pin keeps +3V3_ADC at 0.23 mm
end to end: builds 1-27 shipped three rails that way and build 28 measured it).  Routing wide and narrowing
only near the fine pads moved the problem into the router (three build-28 runs lost two to five nets to the
space the wide tracks took).  So the routes are kept exactly as the router laid them, and afterwards every
track of a Power or Rail net grows toward its class width as far as the copper round it allows: the other
nets' tracks, vias and pads on its layer, the holes, the board edge and the Ethernet island's 1.5 mm rule,
each with the clearance KiCad would apply.  A track that ends inside a pad stays no wider than that pad.
Only the width changes, segment by segment, so what routed still routes and DRC sees what the router saw,
or more room."""
import math
import collections

CELL = 1.0              # mm, the bucket size of the spatial index
EDGE = 0.3              # mm, copper to the board edge (gen/rules.py min_copper_edge_clearance)
HOLE = 0.2              # mm, copper to a drilled hole (board setup)
STEP = 0.01


def _d_pt_seg(px, py, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    ll = dx * dx + dy * dy
    if ll <= 1e-12:
        return math.hypot(px - x0, py - y0)
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / ll))
    return math.hypot(x0 + t * dx - px, y0 + t * dy - py)


def _cross(ax, ay, bx, by):
    return ax * by - ay * bx


def _segs_cross(a, b):
    (x0, y0, x1, y1), (u0, v0, u1, v1) = a, b
    d1 = _cross(x1 - x0, y1 - y0, u0 - x0, v0 - y0)
    d2 = _cross(x1 - x0, y1 - y0, u1 - x0, v1 - y0)
    d3 = _cross(u1 - u0, v1 - v0, x0 - u0, y0 - v0)
    d4 = _cross(u1 - u0, v1 - v0, x1 - u0, y1 - v0)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def _d_seg_seg(a, b):
    if _segs_cross(a, b):
        return 0.0
    (x0, y0, x1, y1), (u0, v0, u1, v1) = a, b
    return min(_d_pt_seg(x0, y0, u0, v0, u1, v1), _d_pt_seg(x1, y1, u0, v0, u1, v1),
               _d_pt_seg(u0, v0, x0, y0, x1, y1), _d_pt_seg(u1, v1, x0, y0, x1, y1))


def _inside(px, py, poly):
    c = False
    n = len(poly)
    for i in range(n):
        (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
        if (ya > py) != (yb > py) and px < xa + (py - ya) * (xb - xa) / (yb - ya):
            c = not c
    return c


def _d_seg_poly(seg, poly):
    x0, y0, x1, y1 = seg
    if _inside(x0, y0, poly) or _inside(x1, y1, poly):
        return 0.0
    best = 1e9
    n = len(poly)
    for i in range(n):
        (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
        best = min(best, _d_seg_seg(seg, (xa, ya, xb, yb)))
    return best


def _rect(x, y, w, h, rot):
    r = math.radians(-rot)
    c, s = math.cos(r), math.sin(r)
    out = []
    for px, py in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        out.append((x + px * c - py * s, y + px * s + py * c))
    return out


class _Index:
    def __init__(self):
        self.cells = collections.defaultdict(list)

    def add(self, oid, x0, y0, x1, y1):
        for i in range(int(math.floor(x0 / CELL)), int(math.floor(x1 / CELL)) + 1):
            for j in range(int(math.floor(y0 / CELL)), int(math.floor(y1 / CELL)) + 1):
                self.cells[(i, j)].append(oid)

    def near(self, x0, y0, x1, y1):
        out = set()
        for i in range(int(math.floor(x0 / CELL)), int(math.floor(x1 / CELL)) + 1):
            for j in range(int(math.floor(y0 / CELL)), int(math.floor(y1 / CELL)) + 1):
                out.update(self.cells.get((i, j), ()))
        return out


def fatten(tracks, vias, pads, target_of, clear_of, first=0, bw=None, bh=None, lan_of=None, report=None):
    """tracks: [(layer, x0, y0, x1, y1, net, w)], vias: [(x, y, net, size, drill)], pads: [dict(x, y, w, h, rot,
    layer, th, net, drill?, shape?)].  target_of(net) -> the width to grow to, or None to leave the net alone.
    clear_of(net_a, net_b) -> the clearance between the two nets' copper.  Tracks before index `first` (hand
    copper, the escape) are never changed.  lan_of(net) -> True for the Ethernet line side (1.5 mm from every
    other net).  Returns a new tracks list in the same order."""
    tracks = list(tracks)
    objs = []           # (kind, layer or "*", net, geometry, hole_r)
    index = _Index()
    for i, (L, x0, y0, x1, y1, net, w) in enumerate(tracks):
        objs.append(("seg", L, net, [x0, y0, x1, y1, w], 0.0))
        index.add(i, min(x0, x1) - w, min(y0, y1) - w, max(x0, x1) + w, max(y0, y1) + w)
    n_tracks = len(objs)
    for (x, y, net, size, drill) in vias:
        objs.append(("via", "*", net, (x, y, size / 2.0), drill / 2.0))
        index.add(len(objs) - 1, x - size, y - size, x + size, y + size)
    for p in pads:
        layer = "*" if p.get("th") else p["layer"]
        shape = p.get("shape", "rect")
        hole = (p.get("drill") or 0.0) / 2.0
        if p.get("th") and not hole:
            hole = 0.3 * min(p["w"], p["h"])
        if shape in ("circle",) or (shape == "oval" and abs(p["w"] - p["h"]) < 1e-6):
            geom = ("circle", p["x"], p["y"], p["w"] / 2.0)
        else:
            geom = ("poly", _rect(p["x"], p["y"], p["w"], p["h"], p.get("rot", 0.0)))
        objs.append(("pad", layer, p["net"], geom, hole))
        r = max(p["w"], p["h"])
        index.add(len(objs) - 1, p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r)
    pad_polys_by_net = collections.defaultdict(list)
    for o in objs[n_tracks + len(vias):]:
        pad_polys_by_net[o[2]].append(o[3])
    grown = collections.defaultdict(lambda: collections.defaultdict(float))
    for i in range(first, len(tracks)):
        L, x0, y0, x1, y1, net, w = tracks[i]
        target = target_of(net)
        if not target or target <= w + 1e-9 or w <= 0.13:
            continue
        seg = (x0, y0, x1, y1)
        w_max = target
        # the board edge
        if bw is not None:
            d_edge = min(x0, x1, y0, y1, bw - x0, bw - x1, bh - y0, bh - y1) - EDGE
            w_max = min(w_max, 2.0 * d_edge)
        # a track that enters a pad of its own net stays no wider than that pad
        for geom in pad_polys_by_net.get(net, ()):
            if geom[0] == "poly" and (_inside(x0, y0, geom[1]) or _inside(x1, y1, geom[1])):
                poly = geom[1]
                a = math.hypot(poly[1][0] - poly[0][0], poly[1][1] - poly[0][1]); b = math.hypot(poly[2][0] - poly[1][0], poly[2][1] - poly[1][1])
                w_max = min(w_max, min(a, b))
            elif geom[0] == "circle" and (math.hypot(x0 - geom[1], y0 - geom[2]) <= geom[3] or math.hypot(x1 - geom[1], y1 - geom[2]) <= geom[3]):
                w_max = min(w_max, 2.0 * geom[3])
        if w_max <= w + 1e-9:
            continue
        reach = w_max / 2.0 + 1.6
        for oid in index.near(min(x0, x1) - reach, min(y0, y1) - reach, max(x0, x1) + reach, max(y0, y1) + reach):
            if oid == i:
                continue
            kind, oL, onet, geom, hole = objs[oid]
            if onet == net:
                continue
            if oL != "*" and oL != L:
                continue
            clr = clear_of(net, onet)
            if lan_of and lan_of(onet):
                clr = max(clr, 1.5)
            if kind == "seg":
                d = _d_seg_seg(seg, tuple(geom[:4])) - geom[4] / 2.0
            elif kind == "via":
                d = _d_pt_seg(geom[0], geom[1], *seg) - geom[2]
            elif geom[0] == "circle":
                d = _d_pt_seg(geom[1], geom[2], *seg) - geom[3]
            else:
                d = _d_seg_poly(seg, geom[1])
            w_max = min(w_max, 2.0 * (d - clr))
            if hole > 0:
                if kind == "via":
                    dh = _d_pt_seg(geom[0], geom[1], *seg) - hole - HOLE
                elif geom[0] == "circle":
                    dh = _d_pt_seg(geom[1], geom[2], *seg) - hole - HOLE
                else:
                    cx = sum(p[0] for p in geom[1]) / 4.0; cy = sum(p[1] for p in geom[1]) / 4.0
                    dh = _d_pt_seg(cx, cy, *seg) - hole - HOLE
                w_max = min(w_max, 2.0 * dh)
            if w_max <= w + 1e-9:
                break
        w_new = math.floor(w_max / STEP + 1e-9) * STEP
        if w_new > w + 1e-9:
            tracks[i] = (L, x0, y0, x1, y1, net, round(w_new, 3))
            objs[i][3][4] = w_new
            grown[net][round(w_new, 2)] += math.hypot(x1 - x0, y1 - y0)
    if report is not None:
        report["fattened"] = {n: {"%.2f" % k: round(v, 1) for k, v in sorted(d.items())} for n, d in sorted(grown.items())}
    return tracks
