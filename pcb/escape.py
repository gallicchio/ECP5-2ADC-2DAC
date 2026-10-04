"""The BGA escape, by construction.

Every ball in rings 1-6 gets a via in its pad (0.3 mm on a 0.15 mm hole,
filled and capped at the fab); the signal balls of rings 7 and 8 leave on
F.Cu directly (ring 7 between the ring-8 pads).  A signal track runs from its
ball to the nearest package edge along the midline between two ball rows (or
columns), where it has 0.19 mm to the neighbouring pads and vias, and ends
1 mm outside the package: that end is the net's terminal for the router.

Which layer: ring 8 and 7 F.Cu, ring 6 In2.Cu, ring 5 In3.Cu, ring 4 either,
chosen so no two tracks share a midline on a layer (one track fits between
two vias).  Power balls: the 1.1 V core and 3.3 V VCCIO balls are joined by
small zone islands under the core on In2/In3, each fed through one extra via
placed in a gap between four balls; VCCAUX (two balls) is routed on B.Cu.
"""
import math, json, os

ROWS = "ABCDEFGHJKLMNPRT"
PITCH = 0.8
EXIT = 8.0                  # distance from the package centre to the track ends
VIA = (0.3, 0.15)           # size, drill under the BGA
W = 0.1                     # escape track width
LAYER = {"F": 0, "In2": 1, "In3": 2, "B": 3}


def rc(num):
    return ROWS.index(num[0]), int(num[1:]) - 1


def plan(pads, padnet, cx, cy, banks, inner_balls=(), spare=(), layer_pref=None, mid_in=()):
    """pads: BGA pad dicts in board coordinates; padnet: {num: net};
    banks: {ball: bank string}; inner_balls: ring-4 balls that should leave on an
    inner layer (or the back) rather than F.Cu when they can -- the clock inputs,
    so the bus rivers of pcb/river.py keep the top layer.  Returns a dict of
    vias, tracks, exits, island polygons and feed vias."""
    out = dict(vias=[], tracks=[], exits={}, feeds=[], islands={}, fails=[])
    taken = set()        # (layer, side, midline) reservations
    byball = {p["num"]: p for p in pads}
    order = []
    for p in pads:
        r, c = rc(p["num"])
        ring = int(max(abs(r - 7.5), abs(c - 7.5)) + 0.5)
        order.append((-ring, p["num"]))
    order.sort()
    for _, num in order:
        p = byball[num]
        net = padnet.get(num, "")
        r, c = rc(num)
        ring = int(max(abs(r - 7.5), abs(c - 7.5)) + 0.5)
        x, y = p["x"], p["y"]
        if not net or (net.startswith("unconnected") and num not in spare):
            continue            # (a spare I/O ball gets its exit planned too: a bus river may take it; its
                                #  copper is only laid once a signal is on it, see build_pcb.bga)
        if net == "GND" or net.startswith("+"):
            out["vias"].append((x, y, net))
            continue
        # exit side: nearest edge, ties broken toward the bank's own side
        d = {"N": r, "S": 15 - r, "W": c, "E": 15 - c}
        bank = banks.get(num, "")
        pref = {"0": "N", "1": "N", "2": "E", "3": "E", "6": "W", "7": "W", "8": "S"}.get(bank, "N")
        side = min(d, key=lambda k: (d[k], 0 if k == pref else 1))
        if ring >= 7:
            layers = [0]
        elif ring == 6:
            layers = [1]
        elif ring == 5:
            layers = [2]
        else:
            # ring 4: F.Cu's second midline (ring 7 uses one per row), then the
            # inner layers' spare midlines, then the back
            layers = [0, 1, 2, 3]
            if num in inner_balls:
                layers = [1, 2, 3, 0]
        if layer_pref and num in layer_pref:
            layers = list(layer_pref[num])          # a ball told where to go (the HDMI pairs, one layer per pair)
        if ring == 8 and ((side in "WE" and c in (0, 15)) or (side in "NS" and r in (0, 15))):
            # outermost: straight out along its own row / column on F.Cu
            L = 0
            if side == "W":
                ex, ey = cx - EXIT, y
            elif side == "E":
                ex, ey = cx + EXIT, y
            elif side == "N":
                ex, ey = x, cy - EXIT
            else:
                ex, ey = x, cy + EXIT
            out["tracks"].append((L, x, y, ex, ey, net))
            out["exits"][net] = (L, ex, ey)
            continue
        # a midline: the one away from the package centre first (or toward it, for a ball told so)
        if side in "WE":
            mids = [r - 0.5, r + 0.5] if r <= 7 else [r + 0.5, r - 0.5]
        else:
            mids = [c - 0.5, c + 0.5] if c <= 7 else [c + 0.5, c - 0.5]
        if num in mid_in:
            mids = mids[::-1]
        done = False
        for L in layers:
            for m in mids:
                key = (L, side, m)
                if key in taken:
                    continue
                taken.add(key)
                if L > 0:
                    out["vias"].append((x, y, net))
                if side in "WE":
                    ym = cy + (m - 7.5) * PITCH
                    jx = x - 0.4 if side == "W" else x + 0.4
                    ex = cx - EXIT if side == "W" else cx + EXIT
                    out["tracks"].append((L, x, y, jx, ym, net))
                    out["tracks"].append((L, jx, ym, ex, ym, net))
                    out["exits"][net] = (L, ex, ym)
                else:
                    xm = cx + (m - 7.5) * PITCH
                    jy = y - 0.4 if side == "N" else y + 0.4
                    ey = cy - EXIT if side == "N" else cy + EXIT
                    out["tracks"].append((L, x, y, xm, jy, net))
                    out["tracks"].append((L, xm, jy, xm, ey, net))
                    out["exits"][net] = (L, xm, ey)
                done = True
                break
            if done:
                break
        if not done:
            out["fails"].append(num)
    # power islands under the core (rings 1-3: the central 6 x 6 balls) and one feed via each
    core = 3 * PITCH + 0.35
    poly = [(cx - core, cy - core), (cx + core, cy - core), (cx + core, cy + core), (cx - core, cy + core)]
    out["islands"] = {"+1V1": ("In2.Cu", poly), "+3V3": ("In3.Cu", poly)}
    # feed vias in the gaps between balls (0.4, 0.4) off a ball centre, inside the core
    gaps = [(cx + (i + 0.5) * PITCH, cy + (j + 0.5) * PITCH) for i in range(-3, 3) for j in range(-3, 3)]
    gaps.sort(key=lambda g: math.hypot(g[0] - cx, g[1] - cy))
    out["feeds"].append((gaps[0][0], gaps[0][1], "+1V1"))
    out["feeds"].append((gaps[3][0], gaps[3][1], "+3V3"))
    return out
