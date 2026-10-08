"""Where everything goes.  The ICs and connectors are placed by hand (ANCHORS:
the floorplan); every other part is placed automatically next to the pads it
connects to, or -- for a decoupling capacitor, which connects only to rails --
next to the IC it was drawn beside on the schematic.

Board frame: 150 x 118 mm, origin top-left, x right, y down.  Floorplan:

    left edge   six edge-launch SMAs (CLK IN/OUT, ADC A/B in, DAC 1/2 out)
    x 5-35      analog: the two ADC front ends (top), the two DAC output
                stages (bottom), their LDOs and the -4.4 V pump
    x 35-50     AD9238 (upper), AD9767 (lower), facing the FPGA's west banks
    x 55-70     the ECP5, SDRAM above it (north banks), flash + JTAG below
    x 80-115    Ethernet (PHY, magnetics) upper right, FT2232H middle right
    right edge  RJ45, two USB-C, mini HDMI; microSD on the bottom edge
    top edge    Pmods, LEDs, buttons; clocks at the top left
    bottom edge 5 V in, bucks, test points, noise and photodiode headers
"""
import os, sys, math, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fplib

BW, BH = 158.0, 119.0        # Hammond 1455Q1601: a 120 mm wide board (slot-to-slot 120.5), up to 159 mm long between the end plates
# The board on KiCad's page (Jason, 2026-10-07: the board must not sit on the page's border or its title block).  The
# design frame is the board's own, (0..BW, 0..BH): the floorplan, the router, the silkscreen, placement.json and the end
# plates all work in it.  Only the written .kicad_pcb -- and so the gerbers, the drill file and the CPL, which must agree
# with them -- puts the board's corner at (OX, OY) on a custom page with 25 mm margins and the title block clear below.
OX, OY = 25.0, 25.0
PAGE_W, PAGE_H = BW + 2 * OX, BH + OY + 50.0      # 50 below the board: a 10 mm gap, KiCad's title block, the 10 mm border
EDGE = 1.0                 # parts stay this far from the edge (copper-edge 0.3 + margin)
SLOT = 3.5                 # the long edges (top, bottom) slide into an enclosure's PCB slots: no part this close to them
POWER_PREFIX = ("+", "-", "GND")
SMA_LABEL_W = 17.5                     # the strip under each SMA where its name and limits print
RIGHT_LABEL_X0, RIGHT_LABEL_X1 = 129.3, 134.8   # the standing-label strip inboard of the right-edge connectors
# Build 31 (2026-10-07, CLAUDE_PCB.md section 5): three fiducials, as far apart as the board allows, on spots that build 30
# had free of copper, silkscreen and courtyards on both sides (a 1 mm copper dot in a 2 mm mask opening, front and back);
# the copper layer numbers 1-6, each in copper on its own layer, in a row in the top slot band, where nothing else may go;
# and JLCPCB's order-number marker on the back silkscreen in the same band, so their number lands inside the extrusion.
FIDUCIALS = [(25.5, 12.5), (120.0, 7.5), (146.5, 113.0)]
LAYER_MARK = (70.0, 1.9, 2.5)         # x of the "1", y, pitch between the digits
ORDER_MARK = (95.0, 1.9)              # "JLCJLCJLCJLC" on B.SilkS

# The floorplan -- every anchor and every hand-laid cluster -- lives in pcb/floorplan.py; ANCHORS and QUIET
# are its dicts (build_pcb.bga_caps adds the FPGA's decoupling capacitors to ANCHORS before placement).
import floorplan as FPL
ANCHORS = FPL.ANCHORS
QUIET = FPL.QUIET


def is_power(net):
    return net.startswith(POWER_PREFIX)


class Placer:
    def __init__(self, fps, vals, nets, numof, hints):
        self.fps, self.vals, self.nets, self.numof, self.hints = fps, vals, nets, numof, hints
        self.fp = {r: fplib.load(f) for r, f in fps.items() if f}
        self.placed = {}          # ref -> (x, y, rot, layer)
        self.boxes = {}           # ref -> (layer, x0, y0, x1, y1)
        self.keep = []            # (layer or None, x0, y0, x1, y1)
        self.padpos = {}          # (ref, pad) -> (x, y)
        self.bynet = {}           # net -> [(ref, pad)]
        for r, pn in nets.items():
            for pad, net in pn.items():
                self.bynet.setdefault(net, []).append((r, pad))

    # ---- geometry --------------------------------------------------------
    def box(self, ref, x, y, rot, layer, grow=0.5):
        return fplib.box_at(self.fp[ref], x, y, rot, back=(layer == "B.Cu"), grow=grow)

    def collides(self, ref, x, y, rot, layer, edge=True):
        """None if the spot is free, else what it hits ("edge", a ref, "keepout")."""
        x0, y0, x1, y1 = self.box(ref, x, y, rot, layer)
        if edge and (x0 < EDGE or y0 < EDGE or x1 > BW - EDGE or y1 > BH - EDGE):
            return "edge"
        for r, (l, b0, b1, b2, b3) in self.boxes.items():
            if r == ref or (l != layer and not self.fp[r]["th_any"] and not self.fp[ref]["th_any"]):
                continue
            if x0 < b2 and b0 < x1 and y0 < b3 and b1 < y1:
                return r
        for (l, b0, b1, b2, b3) in self.keep:
            if l is not None and l != layer:
                continue
            if x0 < b2 and b0 < x1 and y0 < b3 and b1 < y1:
                return "keepout"
        return None

    def free(self, ref, x, y, rot, layer):
        return self.collides(ref, x, y, rot, layer) is None

    def put(self, ref, x, y, rot, layer):
        self.placed[ref] = (x, y, rot, layer)
        x0, y0, x1, y1 = self.box(ref, x, y, rot, layer)
        self.boxes[ref] = (layer, x0, y0, x1, y1)
        for p in fplib.pads_at(self.fp[ref], x, y, rot, back=(layer == "B.Cu")):
            self.padpos[(ref, p["num"])] = (p["x"], p["y"])

    # ---- targets -----------------------------------------------------------
    def target(self, ref):
        """(tx, ty, layer) the part wants to be near, or None if nothing it
        connects to is placed yet."""
        pn = self.nets.get(ref, {})
        pts, others = [], []
        for pad, net in pn.items():
            if net.startswith("unconnected-") or is_power(net):
                continue
            for (r2, p2) in self.bynet.get(net, []):
                if r2 != ref and (r2, p2) in self.padpos:
                    pts.append(self.padpos[(r2, p2)])
                    if r2 != "U1":
                        others.append(self.padpos[(r2, p2)])
        # a part between the FPGA and something else (a series resistor, a pull-up on a button) belongs at
        # the something else: the centroid put the RGMII resistors 20 mm from the PHY, in the middle of the
        # bundle leaving the FPGA, and the SDRAM pull-ups behind the SDRAM
        if others:
            pts = others
        if pts:
            tx, ty = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            # a part whose partners are all on the back belongs on the back (the microSD's pull-ups)
            layers_ = {self.placed[r2][3] for pad, net in pn.items() if not net.startswith("unconnected-") and not is_power(net)
                       for (r2, p2) in self.bynet.get(net, []) if r2 != ref and r2 in self.placed}
            back_only = bool(layers_) and layers_ == {"B.Cu"}
            # a part drawn to a many-pin chip's pad keeps 2.5 mm clear of that chip's pad row (its fan-out
            # lane): build 7 packed the RGMII resistors against the PHY and sealed its pins
            for pad, net in pn.items():
                if net.startswith("unconnected-") or is_power(net):
                    continue
                for (r2, p2) in self.bynet.get(net, []):
                    if r2 != ref and r2 != "U1" and r2 in self.placed and len(self.nets.get(r2, {})) >= 16 and (r2, p2) in self.padpos:
                        cx, cy = self.placed[r2][0], self.placed[r2][1]
                        px, py = self.padpos[(r2, p2)]
                        d = math.hypot(px - cx, py - cy) or 1.0
                        tx, ty = px + (px - cx) / d * 2.5, py + (py - cy) / d * 2.5
                        break
                else:
                    continue
                break
            return (tx, ty, "B.Cu" if back_only else None)
        # rails only: the IC drawn nearest on the same sheet that shares a rail
        hint = self.hints.get(ref)
        best = None
        rails = {net for net in pn.values() if is_power(net) and net != "GND"}
        for net in rails:
            for (r2, p2) in self.bynet.get(net, []):
                if r2 == ref or r2 not in self.placed or r2[0] not in "UJT":
                    continue
                h2 = self.hints.get(r2)
                d = 1e9
                if hint and h2 and hint[0] == h2[0]:
                    d = math.hypot(hint[1] - h2[1], hint[2] - h2[2])
                elif hint and h2:
                    d = 5e8
                if best is None or d < best[0]:
                    best = (d, r2, p2)
        if best:
            px, py = self.padpos[(best[1], best[2])]
            return (px, py, self.placed[best[1]][3])
        return None

    def search(self, ref, tx, ty, layer, rots=(0, 90), step=0.5, rmax=40.0):
        """First free spot on a spiral around the target; the rotation that
        puts the part's pads nearest their partners wins at equal distance."""
        best = None
        r = 0.0
        while r <= rmax:
            n = max(1, int(2 * math.pi * r / step)) if r > 0 else 1
            for k in range(n):
                a = 2 * math.pi * k / n
                x, y = round((tx + r * math.cos(a)) * 2) / 2.0, round((ty + r * math.sin(a)) * 2) / 2.0
                for rot in rots:
                    if self.free(ref, x, y, rot, layer):
                        cost = r + 0.3 * self.padcost(ref, x, y, rot, layer)
                        if best is None or cost < best[0]:
                            best = (cost, x, y, rot)
                if best is not None and r > best[0] + step:
                    break
            if best is not None and r > best[0] + 2 * step:
                break
            r += step
        return best

    def padcost(self, ref, x, y, rot, layer):
        tot = 0.0
        for p in fplib.pads_at(self.fp[ref], x, y, rot, back=(layer == "B.Cu")):
            net = self.nets.get(ref, {}).get(p["num"], "")
            if net.startswith("unconnected-") or is_power(net):
                continue
            ds = [math.hypot(p["x"] - self.padpos[(r2, p2)][0], p["y"] - self.padpos[(r2, p2)][1])
                  for (r2, p2) in self.bynet.get(net, []) if r2 != ref and (r2, p2) in self.padpos]
            if ds:
                tot += min(ds)
        return tot

    # ---- the whole board -----------------------------------------------------
    def run(self, back_refs=()):
        FPL.layout(self)
        self.keep += FPL.keepouts()
        for (mx, my) in FIDUCIALS:                                   # (build 31) nothing on the fiducials or the layer markers
            self.keep.append((None, mx - 1.6, my - 1.6, mx + 1.6, my + 1.6))
        self.keep.append((None, LAYER_MARK[0] - 1.5, LAYER_MARK[1] - 1.3, LAYER_MARK[0] + 5 * LAYER_MARK[2] + 1.5, LAYER_MARK[1] + 1.3))
        self.keep.append(("B.Cu", ORDER_MARK[0] - 10.5, ORDER_MARK[1] - 1.0, ORDER_MARK[0] + 10.5, ORDER_MARK[1] + 1.0))
        # the hand-laid copper (vias through every layer, tracks on theirs) is placement's business too: build 15
        # put an FPGA capacitor on the DAC's ground via
        for item in FPL.HAND:
            if item[0] == "via":
                _, net, vx, vy, size, drill = item
                for lay in ("F.Cu", "B.Cu"):
                    self.keep.append((lay, vx - 0.55, vy - 0.55, vx + 0.55, vy + 0.55))
            else:
                lname, net, pts, w = item
                if lname in ("F.Cu", "B.Cu"):
                    xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
                    self.keep.append((lname, min(xs) - w / 2.0 - 0.3, min(ys) - w / 2.0 - 0.3, max(xs) + w / 2.0 + 0.3, max(ys) + w / 2.0 + 0.3))
        fx, fy = FPL.FPGA
        for ref in list(self.placed):
            if ref not in QUIET:
                hit = self.collides(ref, *self.placed[ref], edge=not (ref.startswith("J") or ref.startswith("H")))
                if hit and hit != ref and hit not in QUIET:
                    print("  ANCHOR COLLISION:", ref, "at", self.placed[ref][:3], "hits", hit)
        todo = [r for r in self.fp if r not in self.placed]
        order = {r: i for i, r in enumerate(sorted(todo))}
        rounds = 0
        while todo and rounds < 6:
            rounds += 1
            left = []
            for ref in sorted(todo, key=lambda r: (0 if any(not is_power(n) and not n.startswith("unconnected-") for n in self.nets.get(r, {}).values()) else 1, order[r])):
                t = self.target(ref)
                if t is None:
                    left.append(ref)
                    continue
                tx, ty, layer = t
                layer = "B.Cu" if ref in back_refs else (layer or "F.Cu")
                if ref in back_refs:
                    tx, ty = fx, fy + 13.0
                fp = self.fp[ref]
                # a two- or three-pad part may face any way: a series resistor whose pad 1 belongs on the far
                # side is placed 180 degrees round, not with its signals crossing (the orientation report in
                # build_pcb.place found 67 two-pad parts reversed or sideways with only 0 and 90 on offer)
                rots = (0, 90, 180, 270) if len(fp["pads"]) <= 3 else (0,)
                best = self.search(ref, tx, ty, layer, rots)
                if best is None:
                    left.append(ref)
                    continue
                _, x, y, rot = best
                self.put(ref, x, y, rot, layer)
            todo = left
        return todo

