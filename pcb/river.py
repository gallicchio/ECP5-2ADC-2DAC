#!/usr/bin/env python3
"""The big buses, routed by construction: from the chip toward the FPGA, as a river.

What the Icepi Zero does with its SDRAM, done here by rule.  A bus chip (the SDRAM, a TSOP-54) sits
with its long axis pointing at the FPGA.  Every signal pad's trace leaves the pad INWARD, under the
package body, turns 45 degrees toward the FPGA and runs straight down a lane of the river that forms
between the two pad rows; a pad whose lane is on an inner layer drops through a via 0.4 mm along its
diagonal.  Nothing in a river ever crosses: a row's lanes are ordered the way the pads are (the pad
nearest the FPGA takes the outermost lane), so the lanes nest.  Where the river leaves the body it
spreads out ("the adapter") onto the FPGA's exit stubs of the same layer, in the same order -- and THAT
is where the balls are assigned: each lane takes the next free exit of its layer, nearest first.  The
FPGA ball a bus signal ends on is therefore decided by the river; pcb/pinswap.py writes the result
into build/pin_swaps.json and the whole design regenerates around it.

Layer per lane: the top layer first (no via), then In2, In3 and the back, as far as each layer's slots
in the river and its exits on the face allow.  A clock input whose PCLK ball sits in the middle of the
face gets a corridor on its layer: a column the river's lanes of that layer never enter, so the clock
can come down it from the far end of the chip (the clock balls were moved to inner-layer PCLK balls in
gen/fpga.py so the top layer never needs one).

Everything is in a local frame per FPGA face: u along the face, v toward the FPGA, the exit line at
v = V_EXIT.  Distances are preserved, so clearances computed here are board clearances.

    python3 pcb/river.py            plan the SDRAM river on the placed board, draw it, check it
"""
import os, sys, math, json, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "gen"))
import escape

TRACK_W = 0.127            # a lane
CLR = 0.16                 # copper-to-copper, as the grid router keeps (DRC asks 0.127; 0.15 for Power)
LANE = 0.3                 # lane pitch inside a river (0.173 mm between tracks)
VIA = (0.45, 0.25)         # a lane's via (size, drill), the board's standard
VIA_FINE = (0.3, 0.15)     # beside a 0.4/0.5 mm row only a small via fits (the size the BGA escape uses)
FINE_DEPTHS = (0.6, 1.4)   # a fine-pitch side row's vias stand outside the row, alternate pads at two depths
OUTSIDE_DEPTHS = (0.6, 1.4, 2.2, 3.0)   # an "outside" row (its lanes run on from the vias): four depths, one lane per (layer, depth)
VIA_D = 0.4                # a via sits this far along the pad's diagonal
PAD_END = 0.0              # the diagonal starts right at the pad's inner end
STUB = 0.6                 # the straight run into an exit
LN = ["F.Cu", "In2.Cu", "In3.Cu", "B.Cu"]
LAYER_ORDER = [0, 1, 2, 3]


class Frame:
    """Local coordinates for one face of the FPGA: u along the face, v toward the FPGA.  Each face's
    transform is a reflection or a swap, so lengths and clearances are the board's."""
    def __init__(self, face, fx, fy):
        self.face, self.fx, self.fy = face, fx, fy
        self.v_exit = (fy if face in "NS" else fx) - escape.EXIT

    def local(self, x, y):
        if self.face == "N": return (x, y)
        if self.face == "S": return (x, 2 * self.fy - y)
        if self.face == "W": return (y, x)
        return (y, 2 * self.fx - x)                       # E

    def board(self, u, v):
        if self.face == "N": return (u, v)
        if self.face == "S": return (u, 2 * self.fy - v)
        if self.face == "W": return (v, u)
        return (2 * self.fx - v, u)                       # E


def face_of(fx, fy, cx, cy):
    dx, dy = cx - fx, cy - fy
    if abs(dx) > abs(dy):
        return "E" if dx > 0 else "W"
    return "S" if dy > 0 else "N"


# ---------------------------------------------------------------------------------------------- geometry
def seg_dist(a, b, c, d):
    """distance between segments a-b and c-d (2-D)"""
    def pdist(p, a, b):
        ax, ay = a; bx, by = b; px, py = p
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2 = cross(a, b, c), cross(a, b, d)
    d3, d4 = cross(c, d, a), cross(c, d, b)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0:
        return 0.0
    return min(pdist(a, c, d), pdist(b, c, d), pdist(c, a, b), pdist(d, a, b))


def rect_seg_dist(rx, ry, hw, hh, a, b):
    """distance from an axis-aligned rectangle (centre, half sizes) to segment a-b, 0 if they touch"""
    # sample the segment finely: good enough at these sizes (segments are a few mm, pads sub-mm)
    n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.05) + 1)
    best = 1e9
    for k in range(n + 1):
        t = k / float(n)
        px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        gx, gy = max(0.0, abs(px - rx) - hw), max(0.0, abs(py - ry) - hh)
        best = min(best, math.hypot(gx, gy))
    return best


# ---------------------------------------------------------------------------------------------- the plan
class Lane:
    def __init__(self, net, padkey, row, v_pad, layer):
        self.net, self.padkey, self.row, self.v_pad, self.layer = net, padkey, row, v_pad, layer
        self.slot = None        # u of the vertical run in the river
        self.exit = None        # (ball, u_exit)
        self.pts = []           # [(layer, u, v), ...] polyline in the local frame
        self.via = None         # (u, v) or None
        self.via_size = VIA


def plan_river(b, chip, bus_nets, frame=None, lane_pitch=LANE, drop=None, layers=(0, 1, 2), **kw):
    """Plan the river of `chip` (a ref) for the nets in `bus_nets` on Build `b` (placed, escape done).
    Returns a dict with lanes, the ball assignment {net: ball}, corridors, stats; or raises.  A chip
    with two pad rows pointing at the FPGA and little room in front of it (the SDRAM) gets the
    zero-jog river below; every other chip goes to plan_chip."""
    fx, fy = b.fpga_xy
    cx, cy, rot, _ = b.pl.placed[chip]
    face = frame if isinstance(frame, str) else face_of(fx, fy, cx, cy)       # a recipe may name the face (the DAC sits south-west of the FPGA but belongs to the west face's bank)
    F = Frame(face, fx, fy) if (frame is None or isinstance(frame, str)) else frame
    cu, cv = F.local(cx, cy)
    # the chip's pads in the local frame; the two rows are the two distinct u values
    pads = [(k, p) for k, p in b.pads.items() if k[0] == chip]
    loc = {k: F.local(p["x"], p["y"]) for k, p in pads}
    byu, byv = {}, {}
    for k, p in pads:
        byu.setdefault(round(loc[k][0], 2), []).append(k)
        byv.setdefault(round(loc[k][1], 2), []).append(k)
    us = sorted(u for u, ks in byu.items() if len(ks) >= 4)          # rows along v (pointing at the FPGA)
    vs = sorted(v for v, ks in byv.items() if len(ks) >= 4)          # rows along u (facing it or away)
    if kw.get("recipe") == "phy":
        return plan_phy(b, chip, bus_nets, **{k: v for k, v in kw.items() if k != "recipe"})
    if kw.get("recipe") == "hdmi":
        return plan_hdmi(b, chip, bus_nets, **{k: v for k, v in kw.items() if k != "recipe"})
    if kw.get("recipe") == "pmod":
        return plan_pmod(b, chip, bus_nets, **{k: v for k, v in kw.items() if k != "recipe"})
    if kw.get("recipe") == "dac":
        return plan_dac(b, chip, bus_nets, **{k: v for k, v in kw.items() if k != "recipe"})
    if len(us) != 2 or vs or kw.get("jog") or F.v_exit - max(loc[k][1] for k, p in pads) > 6.0:
        return plan_chip(b, chip, bus_nets, F, pads, loc, **kw)
    u_w, u_e = us
    # pad half-length along u (the long side): the rows run along v, so the long side is along u
    p0 = pads[0][1]
    half_len = max(p0["w"], p0["h"]) / 2.0
    half_wid = min(p0["w"], p0["h"]) / 2.0
    u_in = {"W": u_w + half_len, "E": u_e - half_len}
    sgn = {"W": +1.0, "E": -1.0}
    rows = {"W": [], "E": []}
    for k, p in pads:
        if p["net"] not in bus_nets:
            continue
        row = "W" if abs(loc[k][0] - u_w) < 0.01 else "E"
        rows[row].append((loc[k][1], p["net"], k))
    for row in rows:
        rows[row].sort(reverse=True)           # nearest the FPGA (largest v) first
    v_last = max(loc[k][1] for k, p in pads)            # the row's last pad centre
    v_body = max(v_last + half_wid + 0.3, cv + 11.1 + 0.2)   # where the river leaves the package
    # ---- the exits of this face, by layer, keyed by ball; which are up for grabs
    import fpga as FP
    fj = json.load(open(os.path.join(ROOT, "build", "fpga_pins.json")))
    assign = fj["assign"]; balls = fj["balls"]
    ball_net = b.nets["U1"]
    net_ball = {n: bl for bl, n in ball_net.items()}
    fixed_sigs = set(FP.FIXED) | set(FP.NEED_PCLK) | {s for pr in FP.PAIRS for s in pr}
    fixed_balls = {assign[s] for s in fixed_sigs if s in assign}
    exits = {L: [] for L in range(4)}
    for net, (L, x, y) in b.esc["exits"].items():
        u, v = F.local(x, y)
        if abs(v - F.v_exit) > 0.05:
            continue                                   # another face
        bl = net_ball.get(net)
        exits[L].append(dict(u=u, ball=bl, net=net, free=(bl not in fixed_balls)))
    for L in exits:
        exits[L].sort(key=lambda e: e["u"])
    # ---- corridors: the clock balls of this face, one column per inner layer, nothing on F.Cu
    corridors = {L: [] for L in range(4)}
    for L in exits:
        for e in exits[L]:
            if not e["free"] and assign.get(e["net"], None) is None and e["ball"] in fixed_balls:
                pass
            if e["ball"] in fixed_balls and any(assign.get(s) == e["ball"] for s in FP.NEED_PCLK):
                if L == 0:
                    raise SystemExit("river: clock ball %s leaves on F.Cu at u=%.1f, in the way of the river" % (e["ball"], e["u"]))
                half = TRACK_W / 2.0 + CLR + TRACK_W / 2.0
                corridors[L].append((e["u"] - half, e["u"] + half))
    # ---- lane slots per layer: a lane's vertical run sits exactly on the u of a free exit of its layer,
    # so the river meets the FPGA's stubs head-on with no sideways shift at all (an earlier version packed
    # the lanes at 0.3 mm and spread them out in front of the package: the spread of an inner layer's
    # lanes onto its 0.8 mm exits crossed the clearance).  Only exits between the two via columns and
    # outside the corridors can be slots; the exits beyond the river's edges stay free for the rest.
    U0 = u_in["W"] + VIA_D + VIA[0] / 2.0 + CLR + TRACK_W / 2.0
    U1 = u_in["E"] - VIA_D - VIA[0] / 2.0 - CLR - TRACK_W / 2.0
    def slots(L):
        out = []
        for e in exits[L]:
            u = e["u"]
            if not e["free"] or u < U0 - 1e-9 or u > U1 + 1e-9:
                continue
            if any(c0 - TRACK_W / 2.0 < u < c1 + TRACK_W / 2.0 for (c0, c1) in corridors[L]):
                continue
            out.append(e)
        return out
    # on a layer with a corridor the west row's lanes stay west of it and the east row's east of it; on a
    # layer without one the two rows share the slots, the west row from the west end, the east from the east
    def groups(L):
        sl = slots(L)
        if corridors[L]:
            c0 = min(c[0] for c in corridors[L]); c1 = max(c[1] for c in corridors[L])
            return (dict(slots=[e for e in sl if e["u"] < c0]), dict(slots=[e for e in sl if e["u"] > c1]))
        return (dict(slots=sl), None)        # shared
    cap = {}
    for L in range(4):
        gw, ge = groups(L)
        if ge is None:
            cap[L] = dict(shared=True, total=len(gw["slots"]), gw=gw, ge=None)
        else:
            cap[L] = dict(shared=False, W=len(gw["slots"]), E=len(ge["slots"]), gw=gw, ge=ge)
    # ---- which pad goes on which layer: nearest the FPGA first, the top layer first.  A split layer
    # (one with a corridor) serves each row from its own side only; a shared layer's slots go first to
    # what each row cannot place elsewhere, and the rest in proportion.  The back layer is kept out of
    # it unless the three others cannot hold the bus (it is where the clocks and the leftover signals
    # pass under the river).
    nW, nE = len(rows["W"]), len(rows["E"])
    def quotas(use):
        q = {L: {"W": 0, "E": 0} for L in range(4)}
        for L in use:
            if not cap[L]["shared"]:
                q[L] = {"W": cap[L]["W"], "E": cap[L]["E"]}
        if drop:
            for L, n in drop.items():                   # keep some exits of a layer free (for the misc nets)
                for row in ("W", "E"):
                    q[L][row] = max(0, q[L][row] - n.get(row, 0))
        for L in use:
            if cap[L]["shared"]:
                t = cap[L]["total"]
                otherW = sum(q[L2]["W"] for L2 in use if L2 != L and not cap[L2]["shared"])
                otherE = sum(q[L2]["E"] for L2 in use if L2 != L and not cap[L2]["shared"])
                needW, needE = max(0, nW - otherW), max(0, nE - otherE)
                if needW + needE > t:
                    return None
                extra = t - needW - needE
                restW, restE = nW - needW, nE - needE
                xw = int(round(extra * restW / float(max(1, restW + restE))))
                q[L] = {"W": min(nW, needW + xw), "E": min(nE, needE + (extra - xw))}
        if sum(q[L]["W"] for L in use) < nW or sum(q[L]["E"] for L in use) < nE:
            return None
        return q
    quota = quotas(list(layers)) or quotas([0, 1, 2, 3])
    if quota is None:
        raise SystemExit("river: %s does not fit: rows %d/%d signals, slots %s" % (chip, nW, nE, {LN[L]: cap[L] for L in range(4)}))
    lanes = {"W": [], "E": []}
    used = {L: {"W": 0, "E": 0} for L in range(4)}
    for row in ("W", "E"):
        for (v, net, k) in rows[row]:
            L = next((L for L in LAYER_ORDER if used[L][row] < quota[L][row]), None)
            if L is None:
                raise SystemExit("river: no lane left for %s (%s row %s): quotas %s" % (net, chip, row, quota))
            used[L][row] += 1
            lanes[row].append(Lane(net, k, row, v, L))
    # ---- slots: on each layer, the row's lanes in order (nearest the FPGA = outermost); a slot IS an
    # exit, so taking it assigns the ball
    def give(l, e):
        l.slot = e["u"]; l.exit = (e["ball"], e["u"]); e["taken"] = l.net
    for L in range(4):
        gw, ge = cap[L]["gw"], cap[L]["ge"]
        lw = [l for l in lanes["W"] if l.layer == L]; le = [l for l in lanes["E"] if l.layer == L]
        if cap[L]["shared"]:
            sl = gw["slots"]
            for i, l in enumerate(lw):
                give(l, sl[i])
            for i, l in enumerate(le):
                give(l, sl[len(sl) - 1 - i])
            if lw and le and lw[-1].slot >= le[-1].slot:
                raise SystemExit("river: the two rows' lanes meet on %s" % LN[L])
        else:
            for i, l in enumerate(lw):
                give(l, gw["slots"][i])
            for i, l in enumerate(le):
                give(l, ge["slots"][len(ge["slots"]) - 1 - i])
    # ---- the geometry of every lane
    v_b = F.v_exit - STUB
    for row in ("W", "E"):
        s = sgn[row]
        ui = u_in[row]
        for l in lanes[row]:
            u_pad = u_w if row == "W" else u_e
            pts = [(0, u_pad, l.v_pad), (0, ui + s * PAD_END, l.v_pad)]
            if l.layer == 0:
                dv = abs(l.slot - (ui + s * PAD_END))
                pts.append((0, l.slot, l.v_pad + dv))
            else:
                pts.append((0, ui + s * (PAD_END + VIA_D), l.v_pad + VIA_D))
                l.via = (ui + s * (PAD_END + VIA_D), l.v_pad + VIA_D)
                dv = abs(l.slot - l.via[0])
                pts.append((l.layer, l.via[0], l.via[1]))
                pts.append((l.layer, l.slot, l.via[1] + dv))
            L = l.layer
            if pts[-1][2] > v_body:
                raise SystemExit("river: %s's diagonal ends beyond the body (v %.1f > %.1f)" % (l.net, pts[-1][2], v_body))
            pts.append((L, l.slot, v_body))
            ue = l.exit[1]
            pts.append((L, ue, v_b))
            pts.append((L, ue, F.v_exit))
            l.pts = pts
    allv = lanes["W"] + lanes["E"]
    assignment = {l.net: l.exit[0] for l in allv}
    report = dict(chip=chip, face=face, rot=rot, layout="river", lanes=len(allv),
                  per_layer={LN[L]: sum(1 for l in allv if l.layer == L) for L in range(4)},
                  vias=sum(1 for l in allv if l.via), corridors={LN[L]: corridors[L] for L in range(4) if corridors[L]},
                  slots={LN[L]: len(slots(L)) for L in range(4)},
                  free_exits={LN[L]: [e["ball"] for e in exits[L] if e["free"] and not e.get("taken")] for L in range(4)},
                  max_adapter_shift=max(abs(l.exit[1] - l.slot) for l in allv), adapter_height=v_b - v_body)
    return dict(frame=F, lanes=allv, assignment=assignment, corridors=corridors, report=report, u_rows=(u_w, u_e), u_in=u_in,
                v_body=v_body, exits=exits)


def _exits_and_corridors(b, F):
    """The face's exits by layer (keyed by ball, free or fixed) and the clock corridors, shared by both layouts."""
    import fpga as FP
    fj = json.load(open(os.path.join(ROOT, "build", "fpga_pins.json")))
    assign = fj["assign"]
    ball_net = b.nets["U1"]
    net_ball = {n: bl for bl, n in ball_net.items()}
    fixed_sigs = set(FP.FIXED) | set(FP.NEED_PCLK) | {s for pr in FP.PAIRS for s in pr}
    fixed_balls = {assign[s] for s in fixed_sigs if s in assign}
    clock_balls = {assign[s] for s in FP.NEED_PCLK if s in assign}
    exits = {L: [] for L in range(4)}
    for net, (L, x, y) in b.esc["exits"].items():
        u, v = F.local(x, y)
        if abs(v - F.v_exit) > 0.05:
            continue
        bl = net_ball.get(net)
        exits[L].append(dict(u=u, ball=bl, net=net, free=(bl not in fixed_balls)))
    for L in exits:
        exits[L].sort(key=lambda e: e["u"])
    corridors = {L: [] for L in range(4)}
    half = TRACK_W / 2.0 + CLR + TRACK_W / 2.0
    for L in exits:
        for e in exits[L]:
            if e["ball"] in clock_balls:
                # (on F.Cu a clock column cannot be crossed by a river at all: the lanes of that layer must
                #  stay on one side of it -- the block choice below never spans a corridor)
                corridors[L].append((e["u"] - half, e["u"] + half))
    return exits, corridors


def plan_parallel(b, chip, bus_nets, F, pads, loc, vs):
    """The chip's rows run ALONG the face: the near row's signals go straight for the FPGA on the top
    layer, converging at 45 degrees onto the exit stubs; the far row's drop through a via at the pad's
    inner end and run under the body and under the near row on the inner layers to those layers' exits.
    No river under the body; the same nesting rule (a row's lanes keep the pads' order)."""
    fx, fy = b.fpga_xy
    cx, cy, rot, _ = b.pl.placed[chip]
    cu, cv = F.local(cx, cy)
    v_far, v_near = vs
    p0 = pads[0][1]
    half_len = max(p0["w"], p0["h"]) / 2.0            # the pad's long side is along v here
    half_wid = min(p0["w"], p0["h"]) / 2.0
    rows = {"N": [], "F": []}                          # near, far: (u, net, key)
    for k, p in pads:
        if p["net"] not in bus_nets:
            continue
        row = "N" if abs(loc[k][1] - v_near) < 0.01 else "F"
        rows[row].append((loc[k][0], p["net"], k))
    for row in rows:
        rows[row].sort()
    exits, corridors = _exits_and_corridors(b, F)
    v_in_far = v_far + half_len                        # the far row's inner ends point at the FPGA
    v_out_near = v_near + half_len                     # the near row's outer ends do too
    v_body = v_near + half_wid + 0.3
    v_b = F.v_exit - STUB
    def usable(L):
        out = []
        for e in exits[L]:
            if not e["free"]:
                continue
            if any(c0 - TRACK_W / 2.0 < e["u"] < c1 + TRACK_W / 2.0 for (c0, c1) in corridors[L]):
                continue
            out.append(e)
        return out
    def block(items, ex):
        """items: [(u, net, key)] sorted by u; ex: exits sorted by u.  The contiguous block of exits that
        keeps the total shift smallest, in order; None if there are not enough."""
        n = len(items)
        if n > len(ex):
            return None
        best = None
        for s in range(0, len(ex) - n + 1):
            cost = sum(abs(ex[s + i]["u"] - items[i][0]) for i in range(n))
            if best is None or cost < best[0]:
                best = (cost, s)
        return ex[best[1]:best[1] + n]
    lanes = []
    # the near row on the top layer, the far row on In2 then In3 then the back, each row nested in u
    ex0 = usable(0)
    near = rows["N"]
    blk = block(near, ex0)
    if blk is None:
        raise SystemExit("river %s: the near row has %d signals but F.Cu has %d usable exits" % (chip, len(near), len(ex0)))
    for (u, net, k), e in zip(near, blk):
        l = Lane(net, k, "N", v_near, 0); l.slot = e["u"]; l.exit = (e["ball"], e["u"]); e["taken"] = net
        d = abs(e["u"] - u)
        l.pts = [(0, u, v_near), (0, u, v_out_near), (0, e["u"], v_out_near + d), (0, e["u"], v_b), (0, e["u"], F.v_exit)]
        if v_out_near + d > v_b:
            raise SystemExit("river %s: %s's diagonal does not fit before the exit (%.1f > %.1f)" % (chip, net, v_out_near + d, v_b))
        lanes.append(l)
    far = rows["F"]
    left = list(far)
    for L in (1, 2, 3):
        if not left:
            break
        exL = usable(L)
        # split the layer's exits at its corridor: lanes stay on their side of a corridor
        cuts = sorted(c for cs in corridors[L] for c in cs)
        if cuts:
            c0, c1 = min(cuts), max(cuts)
            groups = [[e for e in exL if e["u"] < c0], [e for e in exL if e["u"] > c1]]
            # the far row's pads left of the corridor's centre go to the left group, the rest right -- but
            # as many as fit; what does not fit falls to the next layer
            mid = (c0 + c1) / 2.0
            lft = [t for t in left if t[0] < mid]; rgt = [t for t in left if t[0] >= mid]
            parts = [(lft[-len(groups[0]):] if groups[0] else [], groups[0]), (rgt[:len(groups[1])], groups[1])]
        else:
            parts = [(left[:len(exL)], exL)]
        for items, ex in parts:
            items = [t for t in items if t in left]
            if not items:
                continue
            # nested: the block of exits for these items, in order
            blk = block(items, ex)
            if blk is None:
                continue
            for (u, net, k), e in zip(items, blk):
                l = Lane(net, k, "F", v_far, L); l.slot = e["u"]; l.exit = (e["ball"], e["u"]); e["taken"] = net
                du = e["u"] - u
                sgn = 1.0 if du > 0 else -1.0 if du < 0 else 0.0
                # the via sits 0.4 mm along the lane's diagonal (straight ahead when there is no shift)
                vu, vv = u + sgn * min(VIA_D, abs(du)), v_in_far + VIA_D
                l.via = (vu, vv)
                rest = abs(du) - min(VIA_D, abs(du))
                l.pts = [(0, u, v_far), (0, u, v_in_far), (0, vu, vv), (L, vu, vv), (L, e["u"], vv + rest), (L, e["u"], v_b), (L, e["u"], F.v_exit)]
                lanes.append(l)
                left.remove((u, net, k))
    if left:
        raise SystemExit("river %s: no inner-layer exit left for %s" % (chip, [t[1] for t in left]))
    assignment = {l.net: l.exit[0] for l in lanes}
    report = dict(chip=chip, face=F.face, rot=rot, layout="parallel", lanes=len(lanes),
                  per_layer={LN[L]: sum(1 for l in lanes if l.layer == L) for L in range(4)},
                  vias=sum(1 for l in lanes if l.via), corridors={LN[L]: corridors[L] for L in range(4) if corridors[L]},
                  free_exits={LN[L]: [e["ball"] for e in exits[L] if e["free"] and not e.get("taken")] for L in range(4)},
                  max_adapter_shift=max(abs(l.exit[1] - l.pts[1][1]) for l in lanes), adapter_height=v_b - v_body)
    return dict(frame=F, lanes=lanes, assignment=assignment, corridors=corridors, report=report, v_body=v_body, exits=exits)


# ---------------------------------------------------------------------------------------------- the general chip
def plan_chip(b, chip, bus_nets, F, pads, loc, interim=0.45, bends=None, side_via="auto", prefer=None, extra=None, side_outside=False, custom=None, **kw):
    """A chip with pads on up to four sides, in the local frame of the FPGA face it faces (u along the
    face, v toward the FPGA):

      near row  (pads along u, the side facing the FPGA)  -> top-layer lanes straight ahead (+v)
      far row   (pads along u, the side facing away)      -> a via at the pad's inner end, then +v under
                                                             the body and under the near row, on an inner layer
      side rows (pads along v, the two other sides)       -> inward along u, 45 degrees toward the FPGA,
                                                             a via 0.4 mm along the diagonal, the lane on an
                                                             inner layer to an interim slot inside the body
                                                             (outward instead when a far row's lanes run
                                                             under the body: its vias would sit in their way)
    Every lane then runs +v to the line where the body ends, jogs 45 degrees to the u of its exit, and
    runs straight onto the exit stub -- lanes keep their order on each layer, so nothing crosses.  A
    layer's lane group may instead take a 90-degree bend (`bends`: {layer: ("N"|"S", v_turn)}) when its
    exits lie around a corner: +v to v_turn, then along -u (N) or +u (S) to the exit's u, then +v.
    `prefer`: {row kind: [layers]} to steer rows to layers."""
    fx, fy = b.fpga_xy
    cx, cy, rot, _ = b.pl.placed[chip]
    cu, cv = F.local(cx, cy)
    ext_u = lambda p: (p["w"] if F.face in "NS" else p["h"])      # a pad's extent along u, v
    ext_v = lambda p: (p["h"] if F.face in "NS" else p["w"])
    byu, byv = {}, {}
    for k, p in pads:
        byu.setdefault(round(loc[k][0], 2), []).append(k)
        byv.setdefault(round(loc[k][1], 2), []).append(k)
    rows = []
    sides = sorted(u for u, ks in byu.items() if len(ks) >= 4)
    pars = sorted(v for v, ks in byv.items() if len(ks) >= 4)
    for u in sides:
        rows.append(dict(kind="sideW" if u < cu else "sideE", u=u, keys=byu[u]))
    for v in pars:
        rows.append(dict(kind="near" if v > cv else "far", v=v, keys=byv[v]))
    has_near = any(r["kind"] == "near" for r in rows)
    far_bus = any(r["kind"] == "far" and any(b.pads[k]["net"] in bus_nets for k in r["keys"]) for r in rows)
    exits, corridors = _exits_and_corridors(b, F)
    fj = json.load(open(os.path.join(ROOT, "build", "fpga_pins.json")))
    balls = fj["balls"]; ball_net = b.nets["U1"]
    banks = set(kw.get("banks") or {balls[bl]["bank"] for bl, n in ball_net.items() if n in bus_nets and bl in balls})
    for L in exits:
        for e in exits[L]:
            if balls.get(e["ball"], {}).get("bank") not in banks:
                e["free"] = False                       # another bus's bank: not this river's to take
    # a second face around the corner (`extra`: face letter and how many lanes per layer turn toward it,
    # counted from the far side of the lane order): its exits in this frame, reached along -u or +u
    xexits = {L: [] for L in range(4)}
    xdir = 1.0
    if extra:
        F2 = Frame(extra["face"], fx, fy)
        ex2, _c2 = _exits_and_corridors(b, F2)
        for L in ex2:
            for e in ex2[L]:
                if not e["free"] or balls.get(e["ball"], {}).get("bank") not in banks:
                    continue
                # the exit in this frame: F2 gives (u2, v2) with v2 = its exit line; back to the board, then here
                x, y = F2.board(e["u"], F2.v_exit)
                u, v = F.local(x, y)
                xexits[L].append(dict(u=u, v=v, ball=e["ball"], net=e["net"], free=True))
            xexits[L].sort(key=lambda e: e["v"])
        xdir = -1.0 if (any(xexits[L] for L in xexits) and min(e["u"] for L in xexits for e in xexits[L]) < cu) else 1.0
    body_u0 = min(loc[k][0] for k, p in pads); body_u1 = max(loc[k][0] for k, p in pads)
    v_body = max(loc[k][1] + ext_v(b.pads[k]) / 2.0 for k, p in pads) + 0.3
    v_b = F.v_exit - STUB
    lanes = []
    stubs = []                                       # ground pads of fine side rows: stub + via, no lane
    occupied = {L: [] for L in range(4)}             # u positions already taken on a layer (far/near rows)
    # ---- the near and far rows: their u is the pad's
    for r in rows:
        if r["kind"] not in ("near", "far"):
            continue
        keys = sorted((k for k in r["keys"] if b.pads[k]["net"] in bus_nets), key=lambda k: loc[k][0])
        for k in keys:
            p = b.pads[k]
            l = Lane(p["net"], k, r["kind"], loc[k][1], 0 if r["kind"] == "near" else None)
            l.u_start = loc[k][0]
            if r["kind"] == "near":
                l.v_start = r["v"] + ext_v(p) / 2.0
            else:
                # one column of vias at the pads' inner ends: a 0.5 mm row holds 0.3 mm vias (0.2 mm apart,
                # holes 0.35 mm apart), a 0.8 mm row the standard ones
                us_ = sorted(loc[k2][0] for k2 in r["keys"])
                pitch_ = min(b2 - a2 for a2, b2 in zip(us_, us_[1:]))
                l.via = (loc[k][0], r["v"] + ext_v(p) / 2.0 + VIA_D)
                l.via_size = VIA_FINE if pitch_ < 0.6 else VIA
                l.v_start = l.via[1]
            l.interim = loc[k][0]
            lanes.append(l)
    # ---- the side rows: inward (or outward) diagonals, interim slots from the row's end of the body
    for r in rows:
        if r["kind"] not in ("sideW", "sideE"):
            continue
        keys = sorted((k for k in r["keys"] if b.pads[k]["net"] in bus_nets), key=lambda k: -loc[k][1])   # nearest the FPGA first
        if not keys:
            continue
        sgn = 1.0 if r["kind"] == "sideW" else -1.0                 # inward along u
        vs_ = sorted(loc[k][1] for k in r["keys"])
        pitch = min(b2 - a2 for a2, b2 in zip(vs_, vs_[1:]))
        fine = pitch < 0.6
        outward = (side_via == "out") or (side_via == "auto" and (far_bus or fine))
        d = -sgn if outward else sgn                                # the stub's u direction
        p0 = b.pads[keys[0]]
        u_edge = r["u"] + d * ext_u(p0) / 2.0                        # the pad end the lane leaves from
        row_order = sorted(r["keys"], key=lambda k2: loc[k2][1])     # the stagger goes by position in the row
        for k in keys:
            p = b.pads[k]
            i = row_order.index(k)
            l = Lane(p["net"], k, r["kind"], loc[k][1], None if has_near else 0)
            l.u_edge, l.dir, l.fine = u_edge, d, fine
            if fine:
                # a 0.4/0.5 mm row: no via fits beside the neighbours' stubs, so the stub runs straight out of
                # the row to a small via; at 0.4 mm the vias of neighbouring pads stand at two depths; the lane
                # then dives back under the body on its inner layer -- or, for an "outside" row, runs on from
                # its via along the outside of the body (a row whose layers are full of the far row's lanes)
                outside = bool(side_outside and outward)
                depths = OUTSIDE_DEPTHS if outside else FINE_DEPTHS
                depth = depths[i % len(depths)] if (pitch < 0.45 or outside) else FINE_DEPTHS[0]
                l.via = (u_edge + d * depth, loc[k][1]); l.via_size = VIA_FINE
                l.outside = outside
            else:
                l.via = (u_edge + d * VIA_D, loc[k][1] + VIA_D)        # on the diagonal, 0.4 mm along
            lanes.append(l)
        if fine and outward:
            # the row's ground pads get their stitching via in the same stagger (nothing else fits beside
            # the lanes' vias); build_pcb.ground_vias finds them already done
            for k in row_order:
                p = b.pads[k]
                if p["net"] != "GND":
                    continue
                i = row_order.index(k)
                depth = FINE_DEPTHS[i % 2] if pitch < 0.45 else FINE_DEPTHS[0]
                st = Lane("GND", k, r["kind"], loc[k][1], 0)
                st.stub_only = True; st.via_size = VIA_FINE
                u_row = r["u"]
                if side_outside:
                    # an outside row: every depth outside the row carries a lane or a stub, so the ground via
                    # stands on the pad's INNER end, half in the pad, under the body's edge (nothing runs there:
                    # the far row's lanes stay inside the far row's pads)
                    st.via = (u_row - d * ext_u(p) / 2.0, loc[k][1])
                    st.pts = [(0, u_row, loc[k][1]), (0, st.via[0], st.via[1])]
                else:
                    st.via = (u_edge + d * depth, loc[k][1])
                    st.pts = [(0, u_row, loc[k][1]), (0, u_edge, loc[k][1]), (0, st.via[0], st.via[1])]
                stubs.append(st)
    reserved = []                                   # u the near row's non-bus pads need for their own vias
    for r in rows:
        if r["kind"] == "near":
            reserved += [loc[k][0] for k in r["keys"] if b.pads[k]["net"] not in bus_nets and b.pads[k]["net"] and not b.pads[k]["net"].startswith("unconnected")]
    if custom:
        more_lanes, more_stubs = custom(b, chip, F, pads, loc)
        lanes += more_lanes; stubs += more_stubs
    return _finish(b, chip, F, lanes, stubs, exits, corridors, xexits, xdir, has_near, reserved, interim, bends, extra, prefer, v_body, rot)


def _finish(b, chip, F, lanes, stubs, exits, corridors, xexits, xdir, has_near, reserved, interim, bends, extra, prefer, v_body, rot):
    """Layers, interim slots, exits and geometry for a set of lanes (from plan_chip's rows or a hand recipe:
    a "custom" lane brings its own prefix polyline, layer and interim)."""
    v_b = F.v_exit - STUB
    ext_u = lambda p: (p["w"] if F.face in "NS" else p["h"])
    # ---- layers: the near row is F.Cu; the rest spread over In2, In3, B (and F.Cu for the side rows of a
    # chip without a near row) as the exits allow, nearest-the-FPGA lanes first on the best layer
    def usable(L):
        out = []
        for e in exits[L]:
            if not e["free"] or any(c0 - TRACK_W / 2.0 < e["u"] < c1 + TRACK_W / 2.0 for (c0, c1) in corridors[L]):
                continue
            out.append(e)
        return out
    free = {L: usable(L) for L in range(4)}
    xn = {L: min(len(xexits[L]), (extra or {}).get("per_layer", {}).get(L, 0)) for L in range(4)}
    cap = {L: len(free[L]) + xn[L] for L in range(4)}
    for l in lanes:
        if l.layer is not None:
            cap[l.layer] -= 1                        # the near row (F.Cu) and a recipe's preset lanes count first
    for L in range(4):
        if cap[L] < 0:
            raise SystemExit("river %s: %d more lanes preset on %s than it has exits" % (chip, -cap[L], LN[L]))
    if os.environ.get("RIVER_DEBUG"):
        print("  %s: free exits %s, extra %s, capacity after presets %s; lanes %s" % (
            chip, {LN[L]: len(free[L]) for L in range(4)}, {LN[L]: xn[L] for L in range(4)}, {LN[L]: cap[L] for L in range(4)},
            {k: sum(1 for l in lanes if (l.row if not getattr(l, "outside", False) else "outside") == k) for k in ("near", "far", "sideW", "sideE", "outside", "custom")}))
        for L in range(4):
            print("    %s free: %s" % (LN[L], ["%s@%.1f" % (e["ball"], e["u"]) for e in free[L]]))
            print("    %s extra: %s" % (LN[L], ["%s@%.1f" % (e["ball"], e["v"]) for e in xexits[L]]))
    order_pref = (prefer or {})
    used_u = set()                                   # (layer, u) of the outside lanes: two may not share a run
    for l in lanes:
        if l.layer is not None:
            continue
        if getattr(l, "outside", False):
            cands = order_pref.get(l.row, [1, 2, 3])          # never the top layer: the row's other stubs cross it there
            u = round(l.via[0], 3)
            L = next((L for L in cands if cap[L] > 0 and (L, u) not in used_u), None)
            if L is None:
                raise SystemExit("river %s: no layer left for the outside lane %s at u %.2f" % (chip, l.net, u))
            used_u.add((L, u))
            if L == 0:
                l.via = None                         # the top layer needs no via: the stub itself is the lane
        else:
            cands = order_pref.get(l.row, [1, 2, 3] if has_near else [0, 1, 2, 3])
            L = next((L for L in cands if cap[L] > 0), None)
        if L is None:
            raise SystemExit("river %s: no exit left on any layer for %s (%s)" % (chip, l.net, l.row))
        cap[L] -= 1
        l.layer = L
    # ---- interim slots for the side rows, per layer, from the row's end inward, avoiding the far/near
    # rows' lanes on that layer and each other
    for l in lanes:
        if getattr(l, "outside", False):
            l.interim = round(l.via[0] if l.via else (l.u_edge + l.dir * FINE_DEPTHS[0]), 4)       # outside: the run stays on the via's u
    for L in range(4):
        taken = sorted(l.interim for l in lanes if l.layer == L and (l.row in ("near", "far", "custom") or getattr(l, "outside", False)))
        for kind in ("sideW", "sideE"):
            group = [l for l in lanes if l.layer == L and l.row == kind and not getattr(l, "outside", False)]
            if not group:
                continue
            d = group[0].dir
            sgn = 1.0 if kind == "sideW" else -1.0
            # from the row's inner end inward (the fine-pitch vias stand outside; the others on the diagonal)
            if group[0].fine:
                p0_ = b.pads[group[0].padkey]
                u0 = group[0].u_edge - d * (ext_u(p0_) + 0.3) + sgn * 0.45     # the diagonals' start line, one step in
            else:
                u0 = group[0].via[0] + sgn * (VIA[0] / 2.0 + CLR + TRACK_W / 2.0)
            u = u0
            for l in group:
                while any(abs(u - t) < TRACK_W + CLR for t in taken) or any(abs(u - t) < VIA[0] / 2.0 + CLR + TRACK_W / 2.0 + 0.1 for t in reserved):
                    u += sgn * interim
                l.interim = round(u, 4); taken.append(u)
                u += sgn * interim
    # ---- exits: on each layer the lanes in u order take a block of free exits in u order
    v_a = v_body
    for l in lanes:
        if getattr(l, "outside", False):
            l.v_reach = l.v_pad
        elif l.row in ("sideW", "sideE"):
            if l.fine:
                p = b.pads[l.padkey]
                u_back = l.u_edge - l.dir * (ext_u(p) + 0.3)
                l.v_reach = l.v_pad + abs(l.interim - u_back)
            else:
                l.v_reach = l.via[1] + abs(l.interim - l.via[0])
        elif l.row == "custom":
            l.v_reach = l.prefix[-1][2]
        else:
            l.v_reach = l.v_start
        v_a = max(v_a, l.v_reach + 0.3)
    v_a = max(v_a, v_body)
    # hand-made lanes jog from their own u to the bundle's at one common line, past every via
    v_j = v_a
    for l in lanes:
        if l.row == "custom":
            l.v_jog = v_j
            v_a = max(v_a, v_j + abs(l.interim - l.prefix[-1][1]) + 0.3)
    for L in range(4):
        group = sorted([l for l in lanes if l.layer == L], key=lambda l: l.interim)
        if not group:
            continue
        if xn[L]:
            # the lanes nearest the extra face (largest u when it lies at +u... here: the far end of the order
            # from the primary exits, which lie at -u) turn toward it: nested with the primary bundle's bend
            k = xn[L]
            turn = group[-k:] if xdir < 0 else group[:k]
            group = group[:-k] if xdir < 0 else group[k:]
            xs = xexits[L]
            for l, e in zip(turn, xs[:k]):
                l.exit = (e["ball"], e["u"]); l.xexit = e; e["taken"] = l.net
            if not group:
                continue
        ex = free[L]
        n = len(group)
        if n > len(ex):
            raise SystemExit("river %s: %d lanes on %s but %d exits" % (chip, n, LN[L], len(ex)))
        bend = (bends or {}).get(L)
        best = None
        for s0 in range(0, len(ex) - n + 1):
            lo, hi = ex[s0]["u"], ex[s0 + n - 1]["u"]
            if any(lo < c0 < hi or lo < c1 < hi for (c0, c1) in corridors[L]):
                continue                                      # a block never spans a clock's column
            if bend:
                cost = s0                                     # a bent bundle: the exits nearest the chip
            else:
                cost = sum(abs(ex[s0 + i]["u"] - group[i].interim) for i in range(n))
            if best is None or cost < best[0]:
                best = (cost, s0)
        if best is None:
            raise SystemExit("river %s: no block of %d exits on %s clear of the clock columns" % (chip, n, LN[L]))
        s0 = best[1]
        for i, l in enumerate(group):
            e = ex[s0 + i]
            l.exit = (e["ball"], e["u"]); e["taken"] = l.net
    # ---- geometry
    for l in lanes:
        L = l.layer
        pts = []
        if l.row == "custom":
            pts = list(l.prefix)
            u0, v0 = l.prefix[-1][1], l.prefix[-1][2]
            if abs(l.interim - u0) > 1e-9:
                pts += [(L, u0, l.v_jog), (L, l.interim, l.v_jog + abs(l.interim - u0))]
        elif l.row == "near":
            pts += [(0, l.u_start, l.v_pad), (0, l.u_start, l.v_start)]
        elif l.row == "far":
            pts += [(0, l.u_start, l.v_pad), (0, l.u_start, l.via[1] - VIA_D), (0, l.u_start, l.via[1]), (L, l.u_start, l.via[1])]
        elif getattr(l, "outside", False):
            p = b.pads[l.padkey]
            u_row = l.u_edge - l.dir * ext_u(p) / 2.0
            pts += [(0, u_row, l.v_pad), (0, l.u_edge, l.v_pad), (0, l.interim, l.v_pad)]
            if L != 0:
                pts.append((L, l.interim, l.v_pad))
        else:
            p = b.pads[l.padkey]
            u_row = l.u_edge - l.dir * ext_u(p) / 2.0
            pts += [(0, u_row, l.v_pad), (0, l.u_edge, l.v_pad)]
            if L == 0:
                l.via = None
                pts.append((0, l.interim, l.v_pad + abs(l.interim - l.u_edge)))
            elif l.fine:
                # outward to the via on the top layer; on the inner layer back under the pad to the row's
                # inner end, where every lane's diagonal starts from the same line (a diagonal that started
                # at the via itself would cross the next lane's run: the vias stand at two depths)
                u_back = l.u_edge - l.dir * (ext_u(p) + 0.3)
                pts += [(0, l.via[0], l.via[1]), (L, l.via[0], l.via[1]), (L, u_back, l.v_pad), (L, l.interim, l.v_reach)]
            else:
                pts += [(0, l.via[0], l.via[1]), (L, l.via[0], l.via[1]), (L, l.interim, l.v_reach)]
        bend = (bends or {}).get(L)
        ue = l.exit[1]
        if getattr(l, "xexit", None):
            # toward the extra face: +v to the exit's v, a chamfered turn, straight along -u/+u onto the stub
            e = l.xexit
            c = 0.4
            pts += [(L, l.interim, v_a), (L, l.interim, e["v"] - c), (L, l.interim + xdir * c, e["v"]),
                    (L, e["u"] - xdir * STUB, e["v"]), (L, e["u"], e["v"])]
            l.pts = pts
            continue
        if bend:
            side, v_turn = bend[0], bend[1]
            v_turn = max(v_turn, v_a + 0.3)                  # the recipe's turn line is a minimum: after every jog
            # +v to the turn, along -u (N) / +u (S) to the exit's u, then +v: the lanes nest, the one nearest the
            # inside of the turn turning first
            grp = sorted([m for m in lanes if m.layer == L], key=lambda m: m.interim)
            o = {id(m): i for i, m in enumerate(grp)}[id(l)]
            pitch = max(0.4, min(abs(grp[i + 1].interim - grp[i].interim) for i in range(len(grp) - 1)) if len(grp) > 1 else 0.5)
            if len(bend) > 2:
                pitch = bend[2]                              # the recipe names the bundle's pitch (lanes 1.27 apart need not bend 1.27 apart)
            inner = o if side == "N" else (len(grp) - 1 - o)
            vt = v_turn + inner * pitch
            c = min(0.4, pitch / 2.0)
            pts += [(L, l.interim, v_a), (L, l.interim, vt - c), (L, l.interim - c * (1 if side == "N" else -1), vt),
                    (L, ue + c * (1 if side == "N" else -1), vt), (L, ue, vt + c), (L, ue, v_b), (L, ue, F.v_exit)]
        else:
            dv = abs(ue - l.interim)
            pts += [(L, l.interim, v_a), (L, ue, v_a + dv), (L, ue, v_b), (L, ue, F.v_exit)]
            if v_a + dv > v_b:
                raise SystemExit("river %s: %s's jog of %.1f mm does not fit before the exits (%.1f > %.1f)" % (chip, l.net, dv, v_a + dv, v_b))
        l.pts = pts
    assignment = {l.net: l.exit[0] for l in lanes}
    report = dict(chip=chip, face=F.face, rot=rot, layout="chip", lanes=len(lanes), ground_stubs=len(stubs),
                  per_layer={LN[L]: sum(1 for l in lanes if l.layer == L) for L in range(4)},
                  vias=sum(1 for l in lanes if l.via), corridors={LN[L]: corridors[L] for L in range(4) if corridors[L]},
                  free_exits={LN[L]: [e["ball"] for e in exits[L] if e["free"] and not e.get("taken")] for L in range(4)},
                  max_adapter_shift=max([abs(l.exit[1] - l.interim) for l in lanes if not getattr(l, "xexit", None) and not (bends or {}).get(l.layer)] + [0.0]),
                  adapter_height=v_b - v_a, to_extra_face=sum(1 for l in lanes if getattr(l, "xexit", None)))
    return dict(frame=F, lanes=lanes, stubs=stubs, assignment=assignment, corridors=corridors, report=report, v_body=v_body, exits=exits)


def plan_phy(b, chip, bus_nets, resistor_x=(98.5, 95.0), compact=(15.0, 0.5), v_turn=54.5, **kw):
    """The RGMII bus, by hand.  The PHY (a QFN, nothing may pass under it) has its TX group on the side
    facing away from the FPGA and its RX group on the side facing it; both go through 22 R series
    resistors.  Each resistor stands in a column beside the PHY, in line with its signal: the TX
    resistors in a column west of the TX pads' corner, one per 1.2 mm, the PHY's 0.4 mm pads reaching
    them through nested stubs (north, then west); the RX resistors in a column straight west of the RX
    pads, reached through a 45-degree fan.  From the resistors' far pads the lanes gather into one
    nested bundle at 0.5 mm, bend south in front of the FPGA's east face and run in onto bank 2's exits
    north of the HDMI pairs' fixed balls -- the TX lanes on the top layer, the RX lanes through a via
    after their resistor on In2/In3.  RXC (a fixed PCLK ball) and MDC/MDIO are not in the river."""
    fx, fy = b.fpga_xy
    cx, cy, rot, _ = b.pl.placed[chip]
    F = Frame("E", fx, fy)
    pads = {k[1]: p for k, p in b.pads.items() if k[0] == chip}
    # the lines, by the PHY-side net name: (PHY pad number, resistor ref) from the netlist
    phy_net = {num: p["net"] for num, p in pads.items()}
    res_of = {}
    for ref, pn in b.nets.items():
        if not ref.startswith("R") or len(pn) != 2:
            continue
        nets_ = set(pn.values())
        for num, net in phy_net.items():
            if net in nets_ and any(n2 in bus_nets for n2 in nets_):
                far = [n2 for n2 in nets_ if n2 != net][0]
                res_of[num] = (ref, far)
    tx = [(num, pads[num]) for num in ("20", "19", "18", "17", "16", "15") if num in res_of]     # TXC .. TXD3, west to east
    rx = [(num, pads[num]) for num in ("22", "23", "24", "25", "26") if num in res_of]           # RXD3 .. RXCTL, north to south
    if len(tx) != 6 or len(rx) != 5:
        raise SystemExit("river %s: expected 6 TX and 5 RX lines with series resistors, found %d and %d" % (chip, len(tx), len(rx)))
    exits, corridors = _exits_and_corridors(b, F)
    fj = json.load(open(os.path.join(ROOT, "build", "fpga_pins.json")))
    balls = fj["balls"]; ball_net = b.nets["U1"]
    banks = {balls[bl]["bank"] for bl, n in ball_net.items() if n in bus_nets and bl in balls}
    for L in exits:
        for e in exits[L]:
            if balls.get(e["ball"], {}).get("bank") not in banks:
                e["free"] = False
    lanes, stubs = [], []
    def rpads(ref):
        q = {k[1]: p for k, p in b.pads.items() if k[0] == ref}
        return q["1"], q["2"]
    # ---- TX: north out of the pad, west to the resistor's east pad; the lane from its west pad
    x_r = resistor_x[0]
    for k, (num, p) in enumerate(tx):
        ref, far_net = res_of[num]
        p1, p2 = rpads(ref)
        if p2["net"] != p["net"] or abs(p2["x"] - (x_r + 0.825)) > 0.05:
            raise SystemExit("river %s: %s must stand at x %.2f rot 0 with its pad 2 (%s) east, toward the PHY" % (chip, ref, x_r, p["net"]))
        y_r = p1["y"]
        st = Lane(p["net"], (chip, num, 0), "custom", 0, 0); st.stub_only = True; st.via = None
        st.pts = [(0, p["y"], F.local(p["x"], p["y"])[1]), (0, y_r, F.local(p["x"], p["y"])[1]), (0, y_r, F.local(p2["x"], p2["y"])[1])]
        stubs.append(st)
        l = Lane(far_net, (ref, "1", 0), "custom", y_r, 0)
        l.prefix = [(0, y_r, F.local(p1["x"], p1["y"])[1])]
        l.fine = False; l.via = None
        lanes.append(l)
    # ---- RX: west out of the pad, a 45-degree fan to the resistor's east pad; from its west pad a via
    # 0.6 mm on, then the lane on an inner layer
    x_r = resistor_x[1]
    for k, (num, p) in enumerate(rx):
        ref, far_net = res_of[num]
        p1, p2 = rpads(ref)
        if p2["net"] != p["net"] or abs(p2["x"] - (x_r + 0.825)) > 0.05:
            raise SystemExit("river %s: %s must stand at x %.2f rot 0 with its pad 2 (%s) east, toward the PHY" % (chip, ref, x_r, p["net"]))
        y_r = p1["y"]
        x0 = p["x"] - 0.6
        d = abs(y_r - p["y"])
        st = Lane(p["net"], (chip, num, 0), "custom", 0, 0); st.stub_only = True; st.via = None
        st.pts = [(0, p["y"], F.local(p["x"], 0)[1]), (0, p["y"], F.local(x0, 0)[1]), (0, y_r, F.local(x0 - d, 0)[1]), (0, y_r, F.local(p2["x"], 0)[1])]
        stubs.append(st)
        L = 1 if k < 4 else 2
        l = Lane(far_net, (ref, "1", 0), "custom", y_r, L)
        vx = p1["x"] - 0.6
        l.via = (y_r, F.local(vx, 0)[1]); l.via_size = VIA
        l.prefix = [(0, y_r, F.local(p1["x"], 0)[1]), (0, y_r, l.via[1]), (L, y_r, l.via[1])]
        l.fine = False
        lanes.append(l)
    # the RXC line's stub through its resistor (the lane beyond it is the router's: J16 is a fixed PCLK ball)
    if "27" in res_of:
        ref, far_net = res_of["27"]; p = pads["27"]; p1, p2 = rpads(ref)
        if abs(p2["x"] - (x_r + 0.825)) < 0.05 and p2["net"] == p["net"]:
            y_r = p1["y"]; x0 = p["x"] - 0.6; d = abs(y_r - p["y"])
            st = Lane(p["net"], (chip, "27", 0), "custom", 0, 0); st.stub_only = True; st.via = None
            st.pts = [(0, p["y"], F.local(p["x"], 0)[1]), (0, p["y"], F.local(x0, 0)[1]), (0, y_r, F.local(x0 - d, 0)[1]), (0, y_r, F.local(p2["x"], 0)[1])]
            stubs.append(st)
    # ---- the bundle: compact pitch, lanes in u order, then the bend south toward the exits
    for i, l in enumerate(sorted(lanes, key=lambda l: l.v_pad)):
        l.interim = compact[0] + i * compact[1]
    bends = {0: ("S", v_turn), 1: ("S", v_turn), 2: ("S", v_turn)}
    v_body = max(l.prefix[-1][2] for l in lanes) + 0.3
    plan = _finish(b, chip, F, lanes, stubs, exits, corridors, {L: [] for L in range(4)}, 1.0, True, [], 0.5, bends, None, None, v_body, rot)
    plan["report"]["layout"] = "phy"
    return plan


def plan_dac(b, chip, bus_nets, **kw):
    """The AD9767 (rot 0, west of the FPGA): port 2's data on the east row (the near row, top layer), port
    1's on the west row (the far row: vias at the pads' inner ends, lanes under the body), the four bits
    on the south row as outside lanes, and the four write/clock lines: their 33 R stand in a row south
    of the chip, reached through nested stubs; the lane starts at each resistor's far pad through a via
    (two resistor rows, two layers: four distinct runs) and joins the river as its southernmost lanes."""
    fx, fy = b.fpga_xy
    cx, cy, rot, _ = b.pl.placed[chip]
    F = Frame("W", fx, fy)
    pads = [(k, p) for k, p in b.pads.items() if k[0] == chip]
    loc = {k: F.local(p["x"], p["y"]) for k, p in pads}
    clk_nets = {n for n in bus_nets if any(n.endswith(s) for s in ("DAC_WRT1", "DAC_WRT2", "DAC_CLK1", "DAC_CLK2"))}
    data_nets = set(bus_nets) - clk_nets
    def custom(b, chip, F, pads, loc):
        lanes, stubs = [], []
        res = {}
        for ref, pn in b.nets.items():
            if ref.startswith("R") and len(pn) == 2 and any(n in clk_nets for n in pn.values()):
                far = [n for n in pn.values() if n in clk_nets][0]; near = [n for n in pn.values() if n not in clk_nets][0]
                res[near] = (ref, far)
        for k, p in pads:
            if p["net"] not in res:
                continue
            ref, far = res[p["net"]]
            q = {kk[1]: pp for kk, pp in b.pads.items() if kk[0] == ref}
            p1, p2 = q["1"], q["2"]                                # 1: the FPGA side (far), 2: the DAC side
            if p2["net"] != p["net"] or p2["y"] > p1["y"]:                 # pad 2 north of pad 1 (y grows downward)
                raise SystemExit("river %s: %s must stand south of the chip with its pad 2 (%s) up" % (chip, ref, p["net"]))
            u_p, v_p = loc[k]
            u_edge = u_p + p["h"] / 2.0 if F.face in "WE" else u_p + p["w"] / 2.0        # the pad's outer (south) end
            u_r2, v_r2 = F.local(p2["x"], p2["y"]); u_r1, v_r1 = F.local(p1["x"], p1["y"])
            d = abs(v_r2 - v_p)
            u_fan = u_r2 - 0.5 - d                               # the fan's corner: 45 degrees into the resistor's pad
            st = Lane(p["net"], k, "custom", 0, 0); st.stub_only = True; st.via = None
            st.pts = [(0, u_p, v_p), (0, u_edge, v_p), (0, u_fan, v_p), (0, u_r2 - 0.5, v_r2), (0, u_r2, v_r2)]
            stubs.append(st)
            l = Lane(far, (ref, "1", 0), "custom", u_r1, None)
            l.fine = False
            l.via = (u_r1 + 0.9, v_r1); l.via_size = VIA_FINE
            l.prefix = [(0, u_r1, v_r1), (0, l.via[0], l.via[1])]
            l.interim = round(l.via[0], 4)
            l.clock_lane = True
            lanes.append(l)
        # two resistor rows: within a row, the via of each resistor further from the FPGA stands 0.5 mm
        # deeper, so its lane (which runs toward the FPGA on the via's u) passes the vias east of it -- a via
        # blocks every layer, so sharing a u was never enough.  Every lane then has its own u; the four
        # alternate In2 / In3, nearest the chip first.
        rows_ = {}
        for l in lanes:
            rows_.setdefault(round(l.prefix[0][1], 3), []).append(l)       # keyed by pad 1's u: the resistor row
        for u_row, grp in rows_.items():
            grp.sort(key=lambda l: -l.via[1])                                # nearest the FPGA (largest v) first
            for i, l in enumerate(grp):
                l.via = (round(l.via[0] + 0.5 * i, 4), l.via[1])
                l.prefix = [(0, u_row, l.via[1]), (0, l.via[0], l.via[1])]
                l.interim = round(l.via[0], 4)
        for i, l in enumerate(sorted(lanes, key=lambda l: l.interim)):
            L = (1, 2)[i % 2]
            l.layer = L
            l.prefix.append((L, l.via[0], l.via[1]))
        return lanes, stubs
    plan = plan_chip(b, chip, data_nets, F, pads, loc, custom=custom, **{k: v for k, v in kw.items() if k != "frame"})
    plan["report"]["layout"] = "dac"
    return plan


# The HDMI pairs' balls are fixed (LVDS pairs); the escape puts each pair on ONE layer, in the order
# the jack's pads and the coupling capacitors dictate (D2 at the top, then D1, D0, CK): CK on F.Cu, D0
# on In2, D2 on In3 (H12 toward the centre first so it lands north of H13), D1 on the back.
ESCAPE_LAYERS = {"J12": [2], "K12": [3], "K13": [3], "E8": [3]}   # J12: the D2 pair's comp half joins J13 on In3; K12/K13 (CEC, HPD): the back, off the TMDS rows; E8: ETH_RXC, on the back
ESCAPE_MID_IN = {"J13"}                       # D2's true half takes row J's inner midline (58.0) so P lies above N; the rest fall right by default:
                                              # F.Cu D0 58.4/58.8 (J16 own row, J15), CK 59.2/59.6 (K16, K15); In2 D1 58.8/59.6 (J14, K14); In3 D2 58.0/58.8 (J13, J12)


def plan_hdmi(b, chip, bus_nets, jog_x=136.9, **kw):
    """The four TMDS pairs, by hand, with one jog each.  The coupling capacitors stand in two columns
    just west of the jack, one per jack pad in the jack's order, on rows 0.6 mm apart (floorplan.hdmi_caps):
    the east column's capacitors face their jack pads straight on, the west column's sit on the rows
    between them, so their short jack-side stubs (a 0.2 mm jog, between the pads' shield pins) pass
    between the east column's parts.  From each capacitor's FPGA-side pad the lane runs west on its pair's
    layer -- the clock pair on the top layer, the others through a via IN the pad -- to one line, where
    every lane takes its single 45-degree jog to the row of its fixed ball and then runs straight into the
    east face.  A pair's two lanes jog the same way on the same layer, 0.6 mm apart, so their diagonals stay
    0.42 mm apart and never cross; the pairs cross each other freely on different layers."""
    fx, fy = b.fpga_xy
    F = Frame("E", fx, fy)
    exits, corridors = _exits_and_corridors(b, F)
    ball_net = b.nets["U1"]
    for L in exits:
        for e in exits[L]:
            e["free"] = ball_net.get(e["ball"]) in bus_nets        # only the pairs' own balls: fixed, in place
    layer_of, u_exit = {}, {}
    for L in exits:
        for e in exits[L]:
            if e["free"]:
                layer_of[e["net"]] = L; u_exit[e["net"]] = e["u"]
    caps = {}
    for k, p in b.pads.items():
        if k[0].startswith("C") and p["net"] in bus_nets:
            caps[p["net"]] = (k[0], k[1], p)
    if len(caps) != len(bus_nets):
        raise SystemExit("river %s: %d of %d HDMI lines have a coupling capacitor on them" % (chip, len(caps), len(bus_nets)))
    jack = {p["net"]: p for k, p in b.pads.items() if k[0] == chip and p["net"] and not p["net"].startswith("unconnected")}
    lanes, stubs = [], []
    v_jog = F.local(jog_x, 0)[1]
    for net, (ref, num, p) in caps.items():
        L = layer_of.get(net)
        if L is None:
            raise SystemExit("river %s: %s has no exit on the east face" % (chip, net))
        u, v = F.local(p["x"], p["y"])
        other = [q for k, q in b.pads.items() if k[0] == ref and k[1] != num][0]
        if other["x"] < p["x"]:
            raise SystemExit("river %s: %s must face the FPGA with its %s pad (floorplan.hdmi_caps)" % (chip, ref, net))
        l = Lane(net, (ref, num, 0), "custom", u, L)
        l.fine = False; l.via = None
        pts = [(0, u, v)]
        if L != 0:
            l.via = (u, v); l.via_size = VIA_FINE                   # in the pad: the lane leaves on its layer at once
            pts.append((L, u, v))
        ue = u_exit[net]
        pts += [(L, u, v_jog), (L, ue, v_jog + abs(ue - u))]
        l.prefix = pts
        l.interim = ue
        lanes.append(l)
        # the jack side: out of the pad's west end, a jog of whatever the row differs, straight into the capacitor
        jp = jack.get(other["net"])
        if jp is None:
            raise SystemExit("river %s: %s's jack side (%s) is not on the jack" % (chip, ref, other["net"]))
        u_c, v_c = F.local(other["x"], other["y"]); u_j, v_j = F.local(jp["x"], jp["y"])
        v_end = v_j + max(jp["w"], jp["h"]) / 2.0                    # the pad's west end
        d = abs(u_c - u_j)
        st = Lane(other["net"], (ref, "2", 0), "custom", 0, 0); st.stub_only = True; st.via = None
        st.pts = [(0, u_j, v_j), (0, u_j, v_end + 0.2), (0, u_c, v_end + 0.2 + d), (0, u_c, v_c)]
        stubs.append(st)
    v_body = max(l.prefix[-1][2] for l in lanes) + 0.3
    plan = _finish(b, chip, F, lanes, stubs, exits, corridors, {L: [] for L in range(4)}, 1.0, True, [], 0.5, None, None, None, v_body, 0)
    plan["report"]["layout"] = "hdmi"
    return plan


def plan_pmod(b, chip, bus_nets, turn_x=127.5, pitch=0.4, **kw):
    """The sixteen Pmod lines: from their series resistors' far pads (two columns east of the bend, rows
    1.27 mm apart) straight west, on the top layer or through a via 0.9 mm past the pad, to one bundle
    that bends north (nested, `pitch` apart, the northmost lane innermost) in front of the east face and
    turns west into bank 3's lower rows.  Four lanes per inner layer, nine on top; the back stays free,
    so the HDMI's slow lines can cross the bundle there."""
    fx, fy = b.fpga_xy
    F = Frame("E", fx, fy)
    exits, corridors = _exits_and_corridors(b, F)
    fj = json.load(open(os.path.join(ROOT, "build", "fpga_pins.json")))
    balls = fj["balls"]
    banks = set(kw.get("banks") or {"3"})
    for L in exits:
        for e in exits[L]:
            if balls.get(e["ball"], {}).get("bank") not in banks:
                e["free"] = False
    lanes = []
    for net in sorted(bus_nets):
        res = [(k, p) for k, p in b.pads.items() if k[0].startswith("R") and p["net"] == net]
        if len(res) != 1:
            raise SystemExit("river %s: %s has %d resistor pads, not one" % (chip, net, len(res)))
        k, p = res[0]
        u, v = F.local(p["x"], p["y"])
        l = Lane(net, k, "custom", u, None)
        l.fine = False
        l.via = (u, v + 0.9); l.via_size = VIA_FINE
        l.prefix = [(0, u, v), (0, u, v + 0.9)]                       # the layer change (if any) happens at the via
        l.interim = u
        lanes.append(l)
    v_body = max(l.prefix[-1][2] for l in lanes) + 0.3
    v_turn = F.local(turn_x, 0)[1]
    bends = {L: ("N", v_turn, pitch) for L in range(4)}
    plan = _finish(b, chip, F, lanes, [], exits, corridors, {L: [] for L in range(4)}, 1.0, False, [], 0.5, bends, None,
                   kw.get("prefer", {"custom": [0, 1, 2]}), v_body, 0)
    for l in plan["lanes"]:
        if l.layer == 0:
            l.via = None                                               # a top-layer lane needs no via: the stub runs on
        else:
            l.pts.insert(2, (l.layer, l.via[0], l.via[1]))             # the lane on its layer starts at the via, not at the body line
    plan["report"]["layout"] = "pmod"
    return plan


def check_grid(plan, b):
    """The river against everything else on the board as the grid holds it (every pad, the escape): a
    lane's cells on its layer must be free once its own net's pads and copper are lifted."""
    F = plan["frame"]; G = b.G
    bad = []
    ball_net = b.nets["U1"]
    for l in plan["lanes"] + plan.get("stubs", []):
        old_net = ball_net.get(l.exit[0]) if l.exit else None
        own = [b.padcells[k] for k, p in b.pads.items() if p["net"] == l.net and k in b.padcells] + b.ownobst.get(l.net, [])
        if old_net and old_net != l.net:
            own = own + b.ownobst.get(old_net, [])      # the escape of the ball this lane takes (its net moves here next pass)
        for cells in own:
            G.sub(cells)
        for (p, q) in zip(l.pts, l.pts[1:]):
            if p[0] != q[0]:
                continue
            x0, y0 = F.board(p[1], p[2]); x1, y1 = F.board(q[1], q[2])
            # (half a pitch, not zero: a zero-radius disc only counts a sample that falls exactly on a node,
            #  which a lane between two rows never does -- builds 12-13 checked almost nothing here)
            hit = [k for k in G.seg_cells(x0, y0, x1, y1, G.pitch * 0.5 + 1e-6) if G.g[(p[0], "thin")][k]]
            if hit:
                i, j = hit[0] % G.nx, hit[0] // G.nx
                bad.append(("lane %s on %s hits something at (%.1f, %.1f)" % (l.net, LN[p[0]], i * G.pitch, j * G.pitch), len(hit)))
        if l.via:
            x, y = F.board(*l.via)
            cls = "wide" if l.via_size[0] > 0.35 else "mid"
            k = G.cell(x, y); k = k[1] * G.nx + k[0]
            if any(G.g[(LL, cls)][k] for LL in range(4)) or b.holes[k]:
                bad.append(("via %s at (%.1f, %.1f) has no room" % (l.net, x, y), 1))
        for cells in own:
            G.add(cells)
    return bad


# ---------------------------------------------------------------------------------------------- checks
def check(plan, b):
    """Every clearance a river must keep: lane to lane, lane to via, lane to the chip's other pads, and
    lane to the escape's copper near the exits.  Returns a list of (what, distance)."""
    F = plan["frame"]
    bad = []
    segs = []           # (layer, net, a, b)
    vias = []           # (net, (u, v), radius)
    for l in plan["lanes"] + plan.get("stubs", []):
        for (p, q) in zip(l.pts, l.pts[1:]):
            if p[0] == q[0] and (abs(p[1] - q[1]) > 1e-9 or abs(p[2] - q[2]) > 1e-9):
                segs.append((p[0], l.net, (p[1], p[2]), (q[1], q[2])))
        if l.via:
            vias.append((l.net, l.via, l.via_size[0] / 2.0))
    need = TRACK_W + CLR
    DRC = 0.127
    for i in range(len(segs)):
        Li, ni, ai, bi = segs[i]
        for j in range(i + 1, len(segs)):
            Lj, nj, aj, bj = segs[j]
            if Li != Lj or ni == nj:
                continue
            d = seg_dist(ai, bi, aj, bj)
            if d < need - 1e-6:
                bad.append((("lane %s / lane %s on %s" % (ni, nj, LN[Li])) + ("" if d - TRACK_W < DRC - 1e-6 else " (margin only)"), round(d - TRACK_W, 3)))
    for (nv, (uv, vv), rv) in vias:
        for (L, n, a, c) in segs:
            if n == nv:
                continue
            d = seg_dist((uv, vv), (uv, vv), a, c)
            if d < rv + TRACK_W / 2.0 + CLR - 1e-6:
                bad.append(("via %s / lane %s on %s" % (nv, n, LN[L]) + ("" if d - rv - TRACK_W / 2.0 < DRC - 1e-6 else " (margin only)"), round(d - rv - TRACK_W / 2.0, 3)))
        for (n2, (u2, v2), r2) in vias:
            if n2 != nv:
                d = math.hypot(uv - u2, vv - v2)
                if d < rv + r2 + CLR - 1e-6:
                    bad.append(("via %s / via %s" % (nv, n2) + ("" if d - rv - r2 < DRC - 1e-6 else " (margin only)"), round(d - rv - r2, 3)))
    # the chip's pads (other nets) vs the lanes on F.Cu
    chip = plan["report"]["chip"]
    for k, p in b.pads.items():
        if k[0] != chip:
            continue
        pu, pv = F.local(p["x"], p["y"])
        wx, wy = (p["w"], p["h"]) if int(round(p["rot"])) % 180 == 0 else (p["h"], p["w"])          # the pad's board extents
        hw, hh = (wx / 2.0, wy / 2.0) if F.face in "NS" else (wy / 2.0, wx / 2.0)                  # ... in the local frame
        for (L, n, a, c) in segs:
            if L != 0 or n == p["net"]:
                continue
            d = rect_seg_dist(pu, pv, hw, hh, a, c)
            if d < TRACK_W / 2.0 + CLR - 1e-6:
                bad.append(("pad %s.%s (%s) / lane %s" % (k[0], k[1], p["net"], n), round(d - TRACK_W / 2.0, 3)))
        for (nv, (uv, vv), rv) in vias:
            if nv == p["net"]:
                continue
            gx, gy = max(0.0, abs(uv - pu) - hw), max(0.0, abs(vv - pv) - hh)
            d = math.hypot(gx, gy)
            if d < rv + CLR - 1e-6:
                bad.append(("pad %s.%s / via %s" % (k[0], k[1], nv) + ("" if d - rv < DRC - 1e-6 else " (margin only)"), round(d - rv, 3)))
    # the escape's copper (other nets) near the exits: tracks and vias.  The ball a lane takes may still
    # carry another net's name in this pass (the swap is applied on the next generation): that copper is
    # the lane's own.
    ball_net = b.nets["U1"]
    own_old = {l.net: ball_net.get(l.exit[0]) for l in plan["lanes"]}
    for (lname, x0, y0, x1, y1, net, w) in b.tracks:
        a = F.local(x0, y0); c = F.local(x1, y1)
        if max(a[1], c[1]) < F.v_exit - 1.0:
            continue
        L = LN.index(lname) if lname in LN else -1
        for (Ls, n, sa, sc) in segs:
            if Ls != L or n == net or own_old.get(n) == net:
                continue
            if max(sa[1], sc[1]) < F.v_exit - 1.5:
                continue
            d = seg_dist(a, c, sa, sc)
            if d < w / 2.0 + TRACK_W / 2.0 + CLR - 1e-6:
                bad.append(("escape %s / lane %s on %s" % (net, n, lname), round(d - w / 2.0 - TRACK_W / 2.0, 3)))
    return bad


# ---------------------------------------------------------------------------------------------- laying
def lay(plan, b):
    """Append the plan's copper to Build b (tracks and vias in board coordinates); returns the nets."""
    F = plan["frame"]
    nets = []
    for l in plan["lanes"] + plan.get("stubs", []):
        for (p, q) in zip(l.pts, l.pts[1:]):
            if p[0] != q[0] or (abs(p[1] - q[1]) < 1e-9 and abs(p[2] - q[2]) < 1e-9):
                continue
            x0, y0 = F.board(p[1], p[2]); x1, y1 = F.board(q[1], q[2])
            b.tracks.append((LN[p[0]], round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4), l.net, TRACK_W))
        if l.via:
            x, y = F.board(*l.via)
            b.vias.append((round(x, 4), round(y, 4), l.net, l.via_size[0], l.via_size[1]))
        if not getattr(l, "stub_only", False):
            nets.append(l.net)
    return nets


# ---------------------------------------------------------------------------------------------- drawing
def draw(plan, b, png, pad=3.0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle
    F = plan["frame"]
    chip = plan["report"]["chip"]
    xs = [p["x"] for k, p in b.pads.items() if k[0] == chip]; ys = [p["y"] for k, p in b.pads.items() if k[0] == chip]
    fx, fy = b.fpga_xy
    x0, x1 = min(min(xs), fx - 9) - pad, max(max(xs), fx + 9) + pad
    y0, y1 = min(min(ys), fy - 9) - pad, max(max(ys), fy - 7) + 1.0
    if F.face != "N":
        x0, x1 = min(xs + [fx - 9]) - pad, max(xs + [fx + 9]) + pad
        y0, y1 = min(ys + [fy - 9]) - pad, max(ys + [fy + 9]) + pad
    col = {0: "#ff5050", 1: "#ffc000", 2: "#d060ff", 3: "#50a0ff"}
    fig, ax = plt.subplots(figsize=(14, 14 * (y1 - y0) / (x1 - x0)))
    ax.set_facecolor("black")
    for k, p in b.pads.items():
        if x0 - 1 < p["x"] < x1 + 1 and y0 - 1 < p["y"] < y1 + 1:
            c = (0.45, 0.45, 0.45) if k[0] != "U1" else (0.3, 0.3, 0.3)
            if p["shape"] == "circle":
                ax.add_patch(Circle((p["x"], p["y"]), p["w"] / 2.0, color=c))
            else:
                r = math.radians(p["rot"]); ca, sa = math.cos(r), math.sin(r)
                w, h = p["w"], p["h"]
                ax.add_patch(Rectangle((p["x"] - (ca * w - sa * h) / 2.0, p["y"] - (sa * w + ca * h) / 2.0), w, h, angle=p["rot"], color=c))
    for (lname, ax0, ay0, ax1, ay1, net, w) in b.tracks:
        if lname in LN and (x0 < ax0 < x1 or x0 < ax1 < x1) and (y0 < ay0 < y1 or y0 < ay1 < y1):
            ax.plot([ax0, ax1], [ay0, ay1], color=col[LN.index(lname)], lw=w * 10, alpha=0.5)
    for (vx, vy, net, size, drill) in b.vias:
        if x0 < vx < x1 and y0 < vy < y1:
            ax.add_patch(Circle((vx, vy), size / 2.0, fill=False, color="white", lw=0.8))
    for l in plan["lanes"] + plan.get("stubs", []):
        for (p, q) in zip(l.pts, l.pts[1:]):
            if p[0] != q[0]:
                continue
            bx0, by0 = F.board(p[1], p[2]); bx1, by1 = F.board(q[1], q[2])
            ax.plot([bx0, bx1], [by0, by1], color=col[p[0]] if l.net != "GND" else "#80ff80", lw=TRACK_W * 12, solid_capstyle="round")
        if l.via:
            vx, vy = F.board(*l.via)
            ax.add_patch(Circle((vx, vy), VIA[0] / 2.0, color="white", alpha=0.9))
    for L, cs in plan["corridors"].items():
        for (c0, c1) in cs:
            bx0, by0 = F.board(c0, plan["v_body"] - 30); bx1, by1 = F.board(c1, F.v_exit)
            ax.add_patch(Rectangle((min(bx0, bx1), min(by0, by1)), abs(bx1 - bx0), abs(by1 - by0), color=col[L], alpha=0.15))
    ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect("equal")
    ax.grid(True, color=(0.25, 0.25, 0.25), lw=0.3)
    r = plan["report"]
    ax.set_title("%s river (%s), rot %d: %d lanes %s, %d vias, shift <= %.2f mm over %.1f mm" % (
        chip, r.get("layout", "river"), r["rot"], r["lanes"], r["per_layer"], r["vias"], r["max_adapter_shift"], r["adapter_height"]), fontsize=10)
    fig.savefig(png, dpi=110, bbox_inches="tight"); plt.close(fig)
    return png


def sdram_nets(b):
    return sorted(n for n in b.numof if "SDRAM_" in n)


def adc_nets(b):
    return sorted(n for n in b.numof if "ADC_A_D" in n or "ADC_B_D" in n or "ADC_A_OTR" in n or "ADC_B_OTR" in n)


def dac_nets(b):
    """the 28 data bits and the four write/clock lines (through their 33 R: the FPGA-side nets)"""
    return sorted(n for n in b.numof if "DAC_P1_D" in n or "DAC_P2_D" in n or any(n.endswith(s) for s in ("DAC_WRT1", "DAC_WRT2", "DAC_CLK1", "DAC_CLK2")))


def hdmi_nets(b):
    return sorted(n for n in b.numof if any(n.endswith(s) for s in ("GPDI_CK_P", "GPDI_CK_N", "GPDI_D0_P", "GPDI_D0_N", "GPDI_D1_P", "GPDI_D1_N", "GPDI_D2_P", "GPDI_D2_N")))


def pmod_nets(b):
    """the sixteen Pmod lines on the FPGA side of their series resistors"""
    return sorted(n for n in b.numof if n.split("/")[-1].startswith("PMOD"))


def eth_nets(b):
    """the RGMII lines on the FPGA side of their series resistors (RXC stays with the router: fixed PCLK ball)"""
    return sorted(n for n in b.numof if any(n.endswith(s) for s in ("ETH_TXD0", "ETH_TXD1", "ETH_TXD2", "ETH_TXD3", "ETH_TXC", "ETH_TX_CTL",
                                                                   "ETH_RXD0", "ETH_RXD1", "ETH_RXD2", "ETH_RXD3", "ETH_RX_CTL")))


# The buses routed as rivers, in order: chip, its nets, and the recipe (the "by hand" part: which way a
# bundle bends, how many lanes per layer go round the corner to a second face, where the side rows' vias
# stand).  pcb/pinswap.py plans these to decide the balls; build_pcb.rivers() plans them again, identically,
# to lay the copper.
E = __import__('place').BW - 150.0   # the east cluster's shift (floorplan.E): the Pmod bend and the HDMI jog follow their jacks
BUSES = [
    ("U305", sdram_nets, {}),
    ("U103", adc_nets, {}),
    ("U201", dac_nets, dict(recipe="dac", bends={0: ("N", 57.0), 1: ("N", 57.0), 2: ("N", 57.0), 3: ("N", 57.0)},
                            extra=dict(face="S", per_layer={0: 4, 1: 6, 2: 6, 3: 4}), side_via="out", side_outside=True, banks={"6", "8"})),
    ("U401", eth_nets, dict(recipe="phy", compact=(15.0, 0.5), v_turn=55.5)),
    ("J503", hdmi_nets, dict(recipe="hdmi", jog_x=136.9 + E)),
    ("J303", pmod_nets, dict(recipe="pmod", turn_x=124.0 + E)),           # the bend 3.5 mm west of the HDMI's jogs (the jack at y 62)
]


if __name__ == "__main__":
    import build_pcb as BP
    b = BP.Build(); b.place(); b.bga()
    plan = plan_river(b, "U305", set(sdram_nets(b)))
    print(json.dumps(plan["report"], indent=1))
    bad = check(plan, b)
    print("clearance problems:", len(bad))
    for w, d in bad[:30]:
        print("   ", w, d)
    os.makedirs(os.path.join(ROOT, "build", "scratch", "diag"), exist_ok=True)
    print("drew", draw(plan, b, os.path.join(ROOT, "build", "scratch", "diag", "river_sdram.png")))
