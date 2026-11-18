#!/usr/bin/env python3
"""Which FPGA ball carries which signal, decided by the board.

A data bit is a data bit: the gateware does not care which ball D5 is on, so
the physical order wins.  gen/fpga.py hands each bus to a bank by rule; this
script, once the board is placed and the BGA escape is planned, decides the
real ball of every free signal:

  1. the big buses are routed first, by construction, as rivers (pcb/river.py):
     a river's lanes arrive at the package in the order the chip's pads dictate
     and each lane takes the nearest free exit stub of its layer -- THAT exit's
     ball is the signal's ball, whatever bank it is in (every bank's VCCIO is
     3.3 V on this board);
  2. everything else is matched to the balls left over by MINIMUM TOTAL
     DISTANCE between a ball's escape exit and the signal's destination pad
     (a minimum-length matching of a planar bundle is crossing-free).  Banks a
     river reached into are pooled, the others are matched on their own.

Fixed signals stay put: the sysCONFIG/JTAG pins, the primary-clock inputs
(they need PCLK balls) and the GPDI LVDS pairs.

    python3 pcb/pinswap.py          # writes build/pin_swaps.json and build/bus_plan.json

gen/fpga.py applies build/pin_swaps.json on its next run; build.py therefore
generates twice.  The second run plans the same rivers on the same geometry
and finds nothing to change: the fixed point.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gen"))
import numpy as np
from scipy.optimize import linear_sum_assignment
import build_pcb, river
import fpga as F

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "build", "pin_swaps.json")
PLAN = os.path.join(ROOT, "build", "bus_plan.json")

BUSES = river.BUSES         # the bus chips routed as rivers, in order, with their nets and recipes


def main():
    b = build_pcb.Build()
    b.place()
    b.bga()
    pins = json.load(open(os.path.join(ROOT, "build", "fpga_pins.json")))
    assign = pins["assign"]; balls = pins["balls"]
    ball_net = b.nets["U1"]                     # ball -> net name (an unconnected ball has an "unconnected-" name)
    net_ball = {n: bl for bl, n in ball_net.items()}
    sig_of_net = {ball_net[bl]: s for s, bl in assign.items() if bl in ball_net}
    exit_of_ball = {net_ball[net]: ex for net, ex in b.esc["exits"].items() if net in net_ball}
    dest = {}
    for key, p in b.pads.items():
        if key[0] == "U1" or not p["net"]:
            continue
        dest.setdefault(p["net"], []).append((p["x"], p["y"]))
    fixed = set(F.FIXED) | set(F.NEED_PCLK) | {s for pr in F.PAIRS for s in pr}
    fixed_balls = {assign[s] for s in fixed if s in assign}
    swaps = {}
    report = {"buses": {}, "pools": {}}
    bus_plan = {"buses": {}}
    river_balls, river_sigs = set(), set()
    groups = []                                  # the banks each river reached into: one pool each
    # ---- 1. the rivers
    b.grid()
    for chip, nets_of, recipe in BUSES:
        nets = set(nets_of(b))
        plan = river.plan_river(b, chip, nets, **recipe)
        bad = [t for t in river.check(plan, b) if "margin only" not in t[0]] + river.check_grid(plan, b)
        r = plan["report"]
        for net, ball in plan["assignment"].items():
            sig = sig_of_net[net]
            swaps[sig] = ball; river_balls.add(ball); river_sigs.add(sig)
        groups.append({balls[bl]["bank"] for bl in plan["assignment"].values()})
        moved = sum(1 for net, ball in plan["assignment"].items() if assign[sig_of_net[net]] != ball)
        report["buses"][chip] = dict(r, moved=moved, clearance_problems=len(bad))
        bus_plan["buses"][chip] = dict(nets=sorted(nets), rot=r["rot"], report=r)
        print("river %s (%s face, rot %d): %d lanes %s, %d vias, %d balls moved, %d clearance problems" % (
            chip, r["face"], r["rot"], r["lanes"], r["per_layer"], r["vias"], moved, len(bad)))
        for w, d in bad[:10]:
            print("    CLEARANCE", w, d)
    # ---- 2. everything else, by distance.  A pool is a region of the package's rim, by where the balls' exits
    # lie: the north face together with the east face NORTH of the HDMI wall (the four TMDS pairs run from the
    # east face to the jack at y 56.4-58.0 on all four layers; nothing crosses them between the FPGA and
    # x 137), the east face south of the wall together with the south face, and the west face.  A signal
    # joins the pool its ball's exit lies in, except that an east-face signal joins the pool on its
    # destination's side of the wall.  (The FTDI's JTAG lines are fixed on the south face and go round the
    # west of the FPGA.)
    WALL = 58.8                 # the TMDS lanes run at y 58.0-59.6 (rows J/K): a free ball's exit is north or south of that
    fx, fy = b.fpga_xy
    def pool_of_ball(bl):
        L, ex, ey = exit_of_ball[bl]
        if ey < fy - 7.9:
            return "north"
        if ex > fx + 7.9:
            return "north" if ey < WALL else "south"
        if ey > fy + 7.9:
            return "south"
        return "west"
    pools = {}
    for s, bl in assign.items():
        if s in fixed or s in river_sigs or bl not in exit_of_ball:
            continue
        key = pool_of_ball(bl)
        L, ex, ey = exit_of_ball[bl]
        if ex > fx + 7.9 or key in ("north", "south"):
            net = ball_net.get(bl, "")
            pts = dest.get(net, [])
            if pts:
                yd = sum(y for x, y in pts) / len(pts)
                if ex > fx + 7.9 or (key == "north" and yd > WALL + 10.0) or (key == "south" and yd < WALL - 10.0):
                    key = "north" if yd < WALL else "south"
        pools.setdefault(key, [set(), set()])[0].add(s)
    for bl, d in balls.items():
        if not d["io"] or bl in river_balls or bl in fixed_balls or bl not in exit_of_ball:
            continue
        if bl in assign.values() and sig_of_net.get(ball_net.get(bl)) in fixed:
            continue
        pools.setdefault(pool_of_ball(bl), [set(), set()])[1].add(bl)
    for key, (sigs, bls) in sorted(pools.items()):
        print("pool %s: %d signals, %d balls" % (key, len(sigs), len(bls)))
    for key, (sigs, bls) in sorted(pools.items()):
        sigs = sorted(sigs); bls = sorted(bls)
        if len(bls) < len(sigs):
            print("pinswap: pool %s has %d signals and only %d balls: %s" % (key, len(sigs), len(bls), sorted(sigs)))
            sys.exit(3)                 # (1 means "the pinout changed, regenerate": a shortage must not look like that)
        de = []
        for s in sigs:
            net = ball_net.get(assign[s], "")
            pts = dest.get(net, [])
            de.append((sum(x for x, y in pts) / len(pts), sum(y for x, y in pts) / len(pts)) if pts else None)
        cost = np.zeros((len(sigs), len(bls)))
        for i, s in enumerate(sigs):
            for j, bl in enumerate(bls):
                L, ex, ey = exit_of_ball[bl]
                cost[i][j] = 0.0 if de[i] is None else ((ex - de[i][0]) ** 2 + (ey - de[i][1]) ** 2) ** 0.5
                if assign[s] != bl:
                    cost[i][j] += 0.5           # a move must gain half a millimetre: a fixed point, not a flip-flop
        before = sum(cost[i][bls.index(assign[s])] if assign[s] in bls else 0.0 for i, s in enumerate(sigs))
        rows, cols = linear_sum_assignment(cost)
        after = float(cost[rows, cols].sum())
        moved = 0
        for i, j in zip(rows, cols):
            if assign[sigs[i]] != bls[j]:
                moved += 1
            swaps[sigs[i]] = bls[j]
        report["pools"][str(key)] = dict(signals=len(sigs), balls=len(bls), length_before_mm=round(float(before), 1), length_after_mm=round(after, 1), moved=moved)
        print("pool %s: %2d signals on %2d balls, exit-to-pad length %6.1f -> %6.1f mm, %d moved" % (key, len(sigs), len(bls), before, after, moved))
    changed = any(assign.get(s) != bl for s, bl in swaps.items())
    if len(set(swaps.values())) != len(swaps):
        raise SystemExit("pinswap: two signals on one ball")
    json.dump({"swaps": swaps, "report": report}, open(OUT, "w"), indent=1, sort_keys=True)
    json.dump(bus_plan, open(PLAN, "w"), indent=1, sort_keys=True)
    print("wrote %s (%s)" % (OUT, "changes the pinout: regenerate" if changed else "no change: the pinout is at its fixed point"))
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
