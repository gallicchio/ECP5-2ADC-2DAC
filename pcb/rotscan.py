#!/usr/bin/env python3
"""Which way round should each big bus chip sit?  For every rotation of each
chip in CHIPS, the sum over its signal pads of the distance to where the
signal has to go: the nearest edge of the FPGA package for an FPGA net (so
the figure does not depend on which ball the pin-swapper happened to pick),
the other pads of the net otherwise.  Lower is better.  Prints a table; the
floorplan in place.py is set by hand from it.

    python3 pcb/rotscan.py
"""
import os, sys, json, math
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fplib, netmap, place as P

CHIPS = ["U305", "U103", "U201", "U401", "U502", "T401", "U306"]
fps, vals, nets, numof = netmap.load(os.path.join(ROOT, "build", "netlist.net"))
pl = json.load(open(os.path.join(ROOT, "build", "placement.json")))
fx, fy = P.ANCHORS["U1"][:2]
HALF = 7.0


def fpga_face(x, y):
    """nearest point of the package outline to (x, y)"""
    cx = min(max(x, fx - HALF), fx + HALF); cy = min(max(y, fy - HALF), fy + HALF)
    if fx - HALF < x < fx + HALF and fy - HALF < y < fy + HALF:
        return (x, y)
    return (cx, cy)


bynet = {}
for ref, pn in nets.items():
    for pad, net in pn.items():
        bynet.setdefault(net, []).append((ref, pad))
padpos = {}
for ref, (x, y, rot, lay) in pl.items():
    for p in fplib.pads_at(fplib.load(fps[ref]), x, y, rot, back=(lay == "B.Cu")):
        padpos[(ref, p["num"])] = (p["x"], p["y"])

print("%-6s %-14s %10s %10s %10s %10s   now" % ("chip", "part", "rot 0", "rot 90", "rot 180", "rot 270"))
for ref in CHIPS:
    if ref not in pl:
        continue
    x, y, rot0, lay = pl[ref]
    fp = fplib.load(fps[ref])
    row = []
    for rot in (0, 90, 180, 270):
        tot = 0.0; n = 0
        for p in fplib.pads_at(fp, x, y, rot, back=(lay == "B.Cu")):
            net = nets[ref].get(p["num"], "")
            if not net or net.startswith("unconnected") or net == "GND" or net.startswith("+") or net.startswith("-"):
                continue
            others = [(r, q) for (r, q) in bynet.get(net, []) if r != ref]
            if not others:
                continue
            if any(r == "U1" for (r, q) in others):
                tx, ty = fpga_face(p["x"], p["y"])
                d = math.hypot(p["x"] - tx, p["y"] - ty)
            else:
                d = min(math.hypot(p["x"] - padpos[(r, q)][0], p["y"] - padpos[(r, q)][1]) for (r, q) in others if (r, q) in padpos)
            tot += d; n += 1
        row.append(tot)
    best = min(range(4), key=lambda i: row[i])
    print("%-6s %-14s %10.0f %10.0f %10.0f %10.0f   %d%s" % (ref, vals.get(ref, "")[:14], row[0], row[1], row[2], row[3], rot0,
          "  <- best is %d" % (90 * best) if 90 * best != rot0 else "  (best)"))
