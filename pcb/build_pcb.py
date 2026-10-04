#!/usr/bin/env python3
"""Build the board: outline, every part placed, the BGA escape, ground
stitching, every net routed, the planes, the silkscreen.  Writes
ECP5-2ADC-2DAC.kicad_pcb and build/route_report.json.

    python3 pcb/build_pcb.py            everything (several minutes)
    python3 pcb/build_pcb.py --place    placement and the escape only
"""
import os, sys, json, math, time, re
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "gen"))
import netmap, fplib, board as B, place as P, escape, router as R, silk as SK
E = P.BW - 150.0        # the east cluster's shift (floorplan.E): the board grew from 150 to 158 mm
import rules

NAME = "ECP5-2ADC-2DAC"
PCB = os.path.join(ROOT, NAME + ".kicad_pcb")
NETLIST = os.path.join(ROOT, "build", "netlist.net")
LIDX = {"F.Cu": 0, "In2.Cu": 1, "In3.Cu": 2, "B.Cu": 3}
LNAME = ["F.Cu", "In2.Cu", "In3.Cu", "B.Cu"]
VIA_STD = (0.45, 0.25)
VIA_SIG = (0.3, 0.15)       # signal vias: the same size as under the BGA
EXIT_VIA_COST = float(os.environ.get("EXIT_VIA_COST", "24"))
VIA_BGA = (0.3, 0.15)
# Power planes on In4.Cu (the GND plane fills what they leave): the core rail under the FPGA and its
# regulator, the 5 V input from the USB-C down the right edge to the bucks, 3.3 V under everything else.
# A rail pad over its plane gets a via into it; pads elsewhere are routed to the nearest point of it.
RAIL_ZONES = [
    # the 1.1 V core: a patch under the core's 1.1 V balls only (rows 56.8 and 60.0, x 70.0-73.2; the 3.3 V VCCIO
    # balls in the rows between them are joined by their own In3 island, fed through floorplan.aux_feed's gap
    # vias at the patch's edge), and a corridor south to its buck.  Build 15's polygon covered the whole FPGA
    # and 20 mm around it: 46 of the 3.3 V pads lay inside it and were each run to a via at its edge
    ("+1V1", [(69.9, 56.3), (73.6, 56.3), (73.6, 68.0), (75.5, 68.0), (75.5, 95.0), (80.5, 95.0), (80.5, 103.0),
              (66.0, 103.0), (66.0, 68.0), (69.9, 68.0)], 2),
    # 5 V: the USB jacks and the input, both bucks' INPUT sides only (U601's 3.3 V output parts between them sit on
    # the 3.3 V plane), a corridor along the bottom to the analog side
    # (the right-hand column is only as wide as the jacks' 5 V pads need, x 140.5-150: the HDMI's and the Pmods'
    #  3.3 V parts west of it sit on the 3.3 V plane; it reaches the bucks through the gap between the two Pmod
    #  sockets' pin rows, y 86-94.3)
    ("+5V", [(140.5 + E, 30.0), (P.BW, 30.0), (P.BW, 104.0), (116.0 + E, 104.0), (116.0 + E, 112.0), (36.0, 112.0),
             (36.0, 107.0), (84.0, 107.0), (84.0, 95.5), (90.0, 95.5), (90.0, 107.0), (102.0, 107.0), (102.0, 86.0),
             (136.5 + E, 86.0), (136.5 + E, 94.3), (140.5 + E, 94.3)], 2),
    # (its bottom follows the 5 V corridor's top edge: build 18's polygon ran to y 115, and the 3 mm band left under
    #  the corridor was an island of the fill that the RAILS header's 3.3 V via landed on)
    ("+3V3", [(8.0, 3.0), (P.BW, 3.0), (P.BW, 104.0), (116.0 + E, 104.0), (116.0 + E, 107.0), (36.0, 107.0), (36.0, 33.0), (8.0, 33.0)], 1),
]
RAIL_W = 0.4                # the other rails: 0.4 mm traces (Rail class minimum 0.3)
THIN_RAILS = {"+2V5_AUX"}   # rails routed at 0.2 mm: they must thread the BGA's via field
RF_W = 0.35                 # 50 ohm microstrip on F.Cu over In1 (JLC06161H-7628: 0.2104 mm of 7628, er 4.4)
# the analog strip down the left: the front ends, the DAC output stages, the noise source, the opto parts.
# Digital nets with no terminal inside it may not cross it (their return currents would flow under the analog traces).
ANALOG_REGION = (0.0, 34.0, 36.0, 112.0)
CLASS_WIDTH = {c[0]: c[1] for c in rules.CLASSES}
CLASSES_HW = R.CLASSES
CLASS_W = {c: 2.0 * hw for c, hw in R.CLASSES.items()}      # the track width a router class means


def net_class(net):
    for c, p in rules.PATTERNS:
        if p.startswith("/"):
            if re.search(p.strip("/"), net):
                return c
        elif p == net:
            return c
    return "Default"


def _pt_seg(x, y, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    tt = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy + 1e-12)))
    return math.hypot(x - x0 - tt * dx, y - y0 - tt * dy)


def in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < xi:
                inside = not inside
    return inside


def fpga_caps(nets, hints):
    out = set()
    for r, pn in nets.items():
        if not r.startswith("C"):
            continue
        vals = set(pn.values())
        if "+1V1" in vals or "+2V5_AUX" in vals:
            out.add(r)
    for r, h in hints.items():
        if r.startswith("C") and h[0] == "fpga.kicad_sch" and h[2] > 480 and "+3V3" in nets.get(r, {}).values():
            out.add(r)
    return out


class Build:
    def __init__(self):
        self.fps, self.vals, self.nets, self.numof = netmap.load(NETLIST)
        self.hints = json.load(open(os.path.join(ROOT, "build", "sch_positions.json")))
        try:
            self.lcsc = json.load(open(os.path.join(ROOT, "build", "lcsc.json")))
        except Exception:
            self.lcsc = {}
        self.tracks = []        # (layer name, x0, y0, x1, y1, net, width)
        self.vias = []          # (x, y, net, size, drill)
        self.edge_vias = []     # (x, y, net): rail_vias' vias at a plane's edge for pads elsewhere (prune() drops the unused)
        # the SMA feeds: 50 ohm microstrip, 0.35 mm wide over the In1 ground plane (0.21 mm of 7628)
        self.rf = set(self.nets[r]["1"] for r in ("J301", "J302", "J101", "J102", "J204", "J205") if r in self.nets)
        self.report = {}
        self.texts = []

    # ---------------------------------------------------------------- placement
    def bga_caps(self, back):
        """The FPGA's 100 nF 0402 decoupling goes on the BACK, directly under
        the package: each capacitor spans a power ball's via and an adjacent
        ground ball's via (0.8 mm pitch, 0402 pads 0.96 mm apart), so the loop
        is the via pair and nothing else.  Fills ANCHORS; returns the refs."""
        x, y, rot = P.ANCHORS["U1"][:3]
        pads = fplib.pads_at(fplib.load(self.fps["U1"]), x, y, rot)
        pn = self.nets["U1"]
        ball = {(round(p["x"], 2), round(p["y"], 2)): pn.get(p["num"], "") for p in pads}
        import floorplan as FPL
        feeds = [(it[2], it[3]) for it in FPL.HAND if it[0] == "via" and abs(it[2] - x) < 8.0 and abs(it[3] - y) < 8.0]   # the island feed vias (floorplan.aux_feed)
        aux_keep = FPL.AUX_KEEP
        caps = sorted((r for r in back if "0402" in self.fps[r]), key=lambda r: (self.vals.get(r) != "100nF", r))
        if not caps:
            return []
        cfp = fplib.load(self.fps[caps[0]])
        CRT = (0.78, 0.38) if "BGA" in self.fps[caps[0]] else (0.91, 0.46)   # courtyard half-sizes: two capacitors may not overlap these
        padboxes = []           # (x0, y0, x1, y1, net) of the pads already placed: other nets keep 0.2 mm
        used, boxes, done = set(), [], []
        def clear(cx, cy, rr, nets2):
            """the two pads land on vias of their own nets and keep 0.2 mm from every other via"""
            for q in fplib.pads_at(cfp, cx, cy, rr, back=True):
                want = nets2[q["num"]]
                hit = None
                for (bx, by), bn in ball.items():
                    d = math.hypot(bx - q["x"], by - q["y"])
                    if d < 0.12:
                        hit = bn
                    elif d < q["w"] / 2.0 + 0.15 + 0.2 and bn != want:
                        return False
                if hit != want:
                    return False
                for (fx_, fy_) in feeds:
                    if abs(fx_ - q["x"]) < q["w"] / 2.0 + 0.35 and abs(fy_ - q["y"]) < q["h"] / 2.0 + 0.35:
                        return False
                for (kx0, ky0, kx1, ky1) in aux_keep:
                    if q["x"] + q["w"] / 2.0 + 0.15 > kx0 and q["x"] - q["w"] / 2.0 - 0.15 < kx1 and q["y"] + q["h"] / 2.0 + 0.15 > ky0 and q["y"] - q["h"] / 2.0 - 0.15 < ky1:
                        return False                                       # the VCCAUX channels (floorplan.aux_feed)
            return True
        # every legal (power ball, ground ball, rotation) a capacitor could take ...
        cands = []
        for (px, py), rail in ball.items():
            if not rail.startswith("+"):
                continue
            nets2 = None
            for r in caps:
                if rail in self.nets[r].values():
                    nets2 = self.nets[r]
                    break
            if nets2 is None:
                continue
            for dx, dy in ((0.8, 0.0), (-0.8, 0.0), (0.0, 0.8), (0.0, -0.8)):
                q = (round(px + dx, 2), round(py + dy, 2))
                if ball.get(q) != "GND":
                    continue
                cx, cy = (px + q[0]) / 2.0, (py + q[1]) / 2.0
                for rr in ((0, 180) if dy == 0.0 else (90, 270)):
                    if not clear(cx, cy, rr, nets2):
                        continue
                    hw, hh = (CRT[0], CRT[1]) if rr in (0, 180) else (CRT[1], CRT[0])
                    qb = []
                    for q2 in fplib.pads_at(cfp, cx, cy, rr, back=True):
                        w2, h2 = (q2["w"], q2["h"]) if rr in (0, 180) else (q2["h"], q2["w"])
                        qb.append((q2["x"] - w2 / 2.0, q2["y"] - h2 / 2.0, q2["x"] + w2 / 2.0, q2["y"] + h2 / 2.0, nets2[q2["num"]]))
                    cands.append(dict(rail=rail, balls=((px, py), q), at=(cx, cy, rr), box=(cx - hw, cy - hh, cx + hw, cy + hh), pads=qb))
        # ... and the largest set of them that fit together (balls used once, courtyards apart, other-net pads 0.2 mm apart)
        want = {}
        for r in caps:
            rail = [n for n in self.nets[r].values() if n != "GND"][0]
            want[rail] = want.get(rail, 0) + 1
        def compatible(c1, c2):
            if set(c1["balls"]) & set(c2["balls"]):
                return False
            b, o = c1["box"], c2["box"]
            if b[0] < o[2] - 0.01 and o[0] < b[2] - 0.01 and b[1] < o[3] - 0.01 and o[1] < b[3] - 0.01:
                return False
            for (*b1, n1) in c1["pads"]:
                for (*b2, n2) in c2["pads"]:
                    if n1 != n2 and b1[0] < b2[2] + 0.2 and b2[0] < b1[2] + 0.2 and b1[1] < b2[3] + 0.2 and b2[1] < b1[3] + 0.2:
                        return False
            return True
        n = len(cands)
        comp = [[compatible(cands[i], cands[j]) for j in range(n)] for i in range(n)]
        best = [[]]
        def dfs(i, chosen, count):
            if len(chosen) > len(best[0]):
                best[0] = chosen[:]
            if i == n or len(chosen) + (n - i) <= len(best[0]):
                return
            c = cands[i]
            if count.get(c["rail"], 0) < want.get(c["rail"], 0) and all(comp[i][j] for j in chosen):
                count[c["rail"]] = count.get(c["rail"], 0) + 1
                chosen.append(i); dfs(i + 1, chosen, count); chosen.pop()
                count[c["rail"]] -= 1
            dfs(i + 1, chosen, count)
        dfs(0, [], {})
        pool = {}
        for r in caps:
            rail = [n for n in self.nets[r].values() if n != "GND"][0]
            pool.setdefault(rail, []).append(r)
        for i in best[0]:
            c = cands[i]
            r = pool[c["rail"]].pop(0)
            P.ANCHORS[r] = (c["at"][0], c["at"][1], c["at"][2], "B.Cu")
            done.append(r)
        P.QUIET |= set(done)
        print("  BGA decoupling: %d of %d 0402 capacitors on ball pairs under the package" % (len(done), len(caps)))
        self.report["bga_caps_on_pairs"] = len(done)
        return done

    def place(self):
        back = fpga_caps(self.nets, self.hints)
        self.bga_caps(back)
        pl = P.Placer(self.fps, self.vals, self.nets, self.numof, self.hints)
        left = pl.run(back_refs=back)
        print("placed %d parts, %d unplaced %s" % (len(pl.placed), len(left), left[:10]))
        self.pl = pl
        # the microSD card slides in and out over the back of the board: that strip stays blank (a design rule of ours)
        import floorplan as FPL
        bad = FPL.sd_card_path_check(pl, lambda r: fplib.box_at(pl.fp[r], *pl.placed[r][:3], back=(pl.placed[r][3] == "B.Cu"), grow=0.0))
        self.report["sd_card_path"] = {"box": FPL.SD_CARD_PATH, "parts_in_it": bad}
        if bad:
            raise SystemExit("the microSD card's path %s is not blank: %s" % (FPL.SD_CARD_PATH, ", ".join(bad)))
        print("  microSD card path %s: blank" % (FPL.SD_CARD_PATH,))
        self.pads = {}          # (ref, num) -> pad dict (absolute)
        for ref, (x, y, rot, layer) in pl.placed.items():
            for i, p in enumerate(fplib.pads_at(pl.fp[ref], x, y, rot, back=(layer == "B.Cu"))):
                p["layer"] = layer
                p["net"] = self.nets.get(ref, {}).get(p["num"], "")
                self.pads[(ref, p["num"], i)] = p      # (ref, num, index): a connector's four "SH" pads are four pads
        self.orientation_report()

    def orientation_report(self):
        """Every two-pad part in series with a signal (both pads on signal nets): is its axis along the
        way from pad 1's partners to pad 2's partners?  Reversed or sideways ones are listed."""
        bynet = {}
        for key, p in self.pads.items():
            if p["net"]:
                bynet.setdefault(p["net"], []).append((key[0], p["x"], p["y"]))
        bad = []
        for ref in self.pl.placed:
            ps = [(k, p) for k, p in self.pads.items() if k[0] == ref]
            if len(ps) != 2 or any(P.is_power(p["net"]) or not p["net"] or p["net"].startswith("unconnected") for k, p in ps):
                continue
            (k1, p1), (k2, p2) = sorted(ps, key=lambda t: t[0][1])
            a = [(x, y) for (r2, x, y) in bynet.get(p1["net"], []) if r2 != ref]
            c = [(x, y) for (r2, x, y) in bynet.get(p2["net"], []) if r2 != ref]
            if not a or not c:
                continue
            ax, ay = sum(x for x, y in a) / len(a), sum(y for x, y in a) / len(a)
            cx, cy = sum(x for x, y in c) / len(c), sum(y for x, y in c) / len(c)
            vx, vy = cx - ax, cy - ay
            px, py = p2["x"] - p1["x"], p2["y"] - p1["y"]
            n = math.hypot(vx, vy) * math.hypot(px, py)
            if n < 1e-6 or math.hypot(vx, vy) < 1.0:
                continue
            cosang = (vx * px + vy * py) / n
            if cosang < -0.5:
                bad.append((ref, "reversed"))
            elif abs(cosang) < 0.5:
                bad.append((ref, "sideways"))
        self.report["series_orientation"] = bad
        print("  series parts not along their signal: %d %s" % (len(bad), bad[:12]))

    # ---------------------------------------------------------------- the BGA
    def bga(self):
        fj = json.load(open(os.path.join(ROOT, "build", "fpga_pins.json")))
        banks = {b: d["bank"] for b, d in fj["balls"].items()}
        x, y, rot, _ = self.pl.placed["U1"]
        pads = fplib.pads_at(self.pl.fp["U1"], x, y, rot)
        import fpga as F
        inner = {fj["assign"][s] for s in F.NEED_PCLK if s in fj["assign"]}
        spare = {bl for bl, d in fj["balls"].items() if d["io"] and self.nets["U1"].get(bl, "").startswith("unconnected")}
        import river
        e = escape.plan(pads, self.nets["U1"], x, y, banks, inner_balls=inner, spare=spare,
                        layer_pref=river.ESCAPE_LAYERS, mid_in=river.ESCAPE_MID_IN)
        self.esc = e
        self.fpga_xy = (x, y)
        seen = set()
        for (vx, vy, net) in list(e["vias"]) + list(e["feeds"]):
            k = (round(vx, 3), round(vy, 3))
            if k in seen or net.startswith("unconnected"):
                continue
            seen.add(k)
            self.vias.append((vx, vy, net, VIA_BGA[0], VIA_BGA[1]))
        for (L, x0, y0, x1, y1, net) in e["tracks"]:
            if net.startswith("unconnected"):
                continue        # a spare ball's exit is planned (a river may take it) but not laid
            self.tracks.append((LNAME[L], x0, y0, x1, y1, net, escape.W))
        self.spare_balls = spare
        print("escape: %d vias, %d tracks, %d exits, %d failed" % (len(e["vias"]), len(e["tracks"]), len(e["exits"]), len(e["fails"])))

    # ---------------------------------------------------------------- the grid
    def grid(self, pitch=R.PITCH):
        G = R.Grid(P.BW, P.BH, pitch=pitch)
        self.G = G
        self.padcells = {}
        t0 = time.time()
        # where a via centre may not go because of a drilled hole: hole-to-hole
        # 0.25 mm plus the via's own drill radius, never lifted for anybody
        self.holes = bytearray(G.n)
        for key, p in self.pads.items():
            if not any(ln.endswith(".Cu") for ln in p.get("layers", ["F.Cu"])):
                # a paste or mask aperture (a QFN's nine paste windows over its exposed pad, the connectors'
                # unnumbered mask openings) is not copper: it blocked the PHY's exposed pad in builds 1-9
                self.padcells[key] = {}
                continue
            if p["th"]:
                layers = [0, 1, 2, 3]
            else:
                layers = [LIDX[p["layer"]]]
            extra = 0.03 if pitch < 0.15 else 0.0                       # the fine grid's rounding left one track 0.002 mm short (build 14)
            if p["shape"] == "circle":
                cells = G.obstacle_cells("disc", layers, (p["x"], p["y"], p["w"] / 2.0), extra)
            else:
                cells = G.obstacle_cells("rect", layers, (p["x"], p["y"], p["w"] / 2.0, p["h"] / 2.0, p["rot"]), extra)
            if p["drill"] and p["th"]:
                hr = p["drill"] / 2.0
                # copper of other nets must keep hole clearance (0.2) from the hole, whatever the annulus
                extra = G.obstacle_cells("disc", layers, (p["x"], p["y"], hr + 0.2 - R.CLEAR))
                for k2, ks in extra.items():
                    cells[k2] = sorted(set(cells.get(k2, ())) | set(ks))
                for k in G.disc_cells(p["x"], p["y"], hr + 0.25 + VIA_STD[1] / 2.0 + 0.05):
                    self.holes[k] = 1
            self.padcells[key] = cells
            G.add(cells)
        print("  pads rasterised in %.1f s" % (time.time() - t0))
        # the BGA: F.Cu, In2, In3 are closed under the package; the back only has the vias
        fx, fy = self.fpga_xy
        half = 7.3
        keep = G.obstacle_cells("rect", [0, 1, 2], (fx, fy, half, half, 0.0), radius_extra=-R.CLEAR)
        G.add(keep)
        # copper a net already has, as CONNECTED COMPONENTS of grid cells: an exit net's escape (its
        # terminal is the exit point), an island-fed rail's feed via, each of VCCAUX's two ball vias on
        # the back, later each rail plane's vias.  The router joins everything else to the largest and
        # the other components to it; a bag of all of them would let it believe two unconnected pieces
        # were one (and route the exits back to their ball vias on B.Cu, as it used to).
        self.comps = {}           # net -> [set((L, k)), ...]
        self.ownobst = {}         # net -> [cell dicts] of the escape copper it already has (lifted while it routes)
        self.laidobst = {}        # net -> [cell dicts] of what the router laid for it (rippable)
        fx, fy = self.fpga_xy
        for (vx, vy, net, size, drill) in self.vias:
            cells = G.obstacle_cells("disc", [0, 1, 2, 3], (vx, vy, size / 2.0))
            G.add(cells)
            for k in G.disc_cells(vx, vy, drill / 2.0 + 0.25 + VIA_STD[1] / 2.0 + 0.05):
                self.holes[k] = 1
            if net not in ("GND",):
                self.ownobst.setdefault(net, []).append(cells)
                if net in self.esc["exits"] or net in self.esc["islands"]:
                    continue        # the exit point / the feed via stand for these
                ci, cj = G.cell(vx, vy)
                self.comps.setdefault(net, []).append({(3, cj * G.nx + ci)})
        for net, (L, ex, ey) in self.esc["exits"].items():
            ci, cj = G.cell(ex, ey)
            self.comps[net] = [{(L, cj * G.nx + ci)}]
        # an island-fed rail: its ball vias and feed via are joined by the island zone, one component
        for net in self.esc["islands"]:
            comp = set()
            for (vx, vy, n2, size, drill) in self.vias:
                if n2 == net and math.hypot(vx - fx, vy - fy) < 8.0:
                    ci, cj = G.cell(vx, vy)
                    comp.add((3, cj * G.nx + ci))
            if comp:
                self.comps.setdefault(net, []).append(comp)
        for (lname, x0, y0, x1, y1, net, w) in self.tracks:
            cells = G.obstacle_cells("seg", [LIDX[lname]], (x0, y0, x1, y1, w / 2.0))
            G.add(cells)
            if net not in ("GND",):
                self.ownobst.setdefault(net, []).append(cells)
        ax0, ay0, ax1, ay1 = ANALOG_REGION
        self.analog_keep = G.obstacle_cells("rect", [0, 1, 2, 3], ((ax0 + ax1) / 2.0, (ay0 + ay1) / 2.0, (ax1 - ax0) / 2.0, (ay1 - ay0) / 2.0, 0.0), radius_extra=-R.CLEAR)
        self.lanes()
        print("  grid ready in %.1f s" % (time.time() - t0))

    def lanes(self):
        """Fan-out lanes.  The first routes out of a ribbon used to turn along the FPGA's face (or along a
        QFP's pad row) right in front of the other exits (pads), walling them in -- the postage stamps of
        pcb/route_diag2.py showed 30 mm of a push-button's net lying across the north face.  Inside a
        lane, a step along the face costs LANE_PEN times more, so a route leaves straight and turns
        later, where there is room."""
        G = self.G
        fx, fy = self.fpga_xy
        d0, dm, d1, half = escape.EXIT - 0.3, escape.EXIT + 1.2, escape.EXIT + 4.0, 9.0
        G.mark_lane(fx - d1, fy - half, fx - d0, fy + half, 2)     # west face: running north-south costs 6x ...
        G.mark_lane(fx + d0, fy - half, fx + d1, fy + half, 2)     # east
        G.mark_lane(fx - half, fy - d1, fx + half, fy - d0, 1)     # north face: running east-west
        G.mark_lane(fx - half, fy + d0, fx + half, fy + d1, 1)     # south
        # ... and is impossible in the last 1.2 mm before the exits: build 7's stamps showed routes coming
        # down a neighbour's column and sliding sideways 0.4 mm in front of the exit line, walling it
        G.mark_lane(fx - dm, fy - half, fx - d0, fy + half, 4)
        G.mark_lane(fx + d0, fy - half, fx + dm, fy + half, 4)
        G.mark_lane(fx - half, fy - dm, fx + half, fy - d0, 3)
        G.mark_lane(fx - half, fy + d0, fx + half, fy + dm, 3)
        n = 0
        for key, p in self.pads.items():
            if key[0] == "U1" or p["th"]:
                continue
            px_, py_, _r, _l = self.pl.placed[key[0]]
            fine = any(k2[0] == key[0] and k2 != key and abs(q["x"] - p["x"]) + abs(q["y"] - p["y"]) < 0.9 for k2, q in self.pads.items())
            if not fine:
                continue
            along_x = p["w"] >= p["h"]           # the pad's long axis
            if along_x:
                sgn = 1.0 if p["x"] >= px_ else -1.0
                x0 = p["x"] + sgn * p["w"] / 2.0
                G.mark_lane(x0, p["y"] - 0.3, x0 + sgn * 1.6, p["y"] + 0.3, 2)
                G.mark_lane(x0, p["y"] - 0.3, x0 + sgn * 0.8, p["y"] + 0.3, 6)
            else:
                sgn = 1.0 if p["y"] >= py_ else -1.0
                y0 = p["y"] + sgn * p["h"] / 2.0
                G.mark_lane(p["x"] - 0.3, y0, p["x"] + 0.3, y0 + sgn * 1.6, 1)
                G.mark_lane(p["x"] - 0.3, y0, p["x"] + 0.3, y0 + sgn * 0.8, 5)
            # (penalty only in front of pads, never "straight only": half the pads of a 0.5 mm part sit
            #  between two cells and the one diagonal step needed to reach them must stay possible --
            #  build 8 lost every such pad; but no via in the first 0.8 mm, see router.route)
            n += 1
        print("  fan-out lanes: the FPGA's four faces and %d fine-pitch pads" % n)

    # ---------------------------------------------------------------- the bus rivers
    def rivers(self):
        """The big buses, routed by construction before anything else (pcb/river.py, planned by
        pcb/pinswap.py into build/bus_plan.json).  Their copper goes into the grid like the escape's: each
        net's own, lifted while the net routes (should it have a third terminal), an obstacle to everyone
        else.  A net whose only terminals are the chip pad and the ball is finished here."""
        import river
        self.river_done = {}
        plan_file = os.path.join(ROOT, "build", "bus_plan.json")
        if not os.path.exists(plan_file):
            print("  rivers: no build/bus_plan.json (run pcb/pinswap.py); none laid")
            return
        G = self.G
        ball_net = self.nets["U1"]
        recipes = {chip: recipe for chip, nets_of, recipe in river.BUSES}
        for chip, nets_of, recipe in river.BUSES:
            info = json.load(open(plan_file))["buses"].get(chip)
            if info is None:
                continue
            nets = set(info["nets"])
            plan = river.plan_river(self, chip, nets, **recipe)
            bad = [t for t in river.check(plan, self) if "margin only" not in t[0]] + river.check_grid(plan, self)
            wrong = [(n, bl, ball_net.get(bl)) for n, bl in plan["assignment"].items() if ball_net.get(bl) != n]
            if wrong:
                raise SystemExit("river %s: the pin swaps are not applied (%d of %d nets are not on their river's ball, e.g. %s): "
                                 "run pcb/pinswap.py and regenerate" % (chip, len(wrong), len(plan["assignment"]), wrong[0]))
            n0, v0 = len(self.tracks), len(self.vias)
            river.lay(plan, self)
            comp_cells = self._register(n0, v0)
            for l in plan["lanes"]:
                # the lane, its pad and its exit are one connected component now
                comp = comp_cells.get(l.net, set())
                for c in self.comps.get(l.net, []):
                    comp |= c
                self.comps[l.net] = [comp]
                self.river_done.setdefault(l.net, set()).add(l.padkey)
            r = plan["report"]
            print("  river %s (%s face, rot %d): %d lanes %s, %d vias, %d clearance problems" % (
                chip, r["face"], r["rot"], r["lanes"], r["per_layer"], r["vias"], len(bad)))
            self.report.setdefault("rivers", {})[chip] = dict(r, clearance_problems=len(bad), problems=bad[:20])

    def _register(self, n0, v0):
        """Put the tracks and vias appended since (n0, v0) into the grid as their nets' own copper (lifted
        while the net routes, an obstacle to everyone else); returns net -> set of (L, k) cells."""
        G = self.G
        comp_cells = {}
        for (lname, x0, y0, x1, y1, net, w) in self.tracks[n0:]:
            cells = G.obstacle_cells("seg", [LIDX[lname]], (x0, y0, x1, y1, w / 2.0))
            G.add(cells); self.ownobst.setdefault(net, []).append(cells)
            for k in G.seg_cells(x0, y0, x1, y1, max(w / 2.0 - 0.01, G.pitch * 0.5 + 1e-6)):     # every node the track's copper reaches (a 0.15 track between two rows reaches none at its own half width)
                comp_cells.setdefault(net, set()).add((LIDX[lname], k))
        for (vx, vy, net, size, drill) in self.vias[v0:]:
            cells = G.obstacle_cells("disc", [0, 1, 2, 3], (vx, vy, size / 2.0))
            G.add(cells); self.ownobst.setdefault(net, []).append(cells)
            for kk in G.disc_cells(vx, vy, drill / 2.0 + 0.25 + VIA_STD[1] / 2.0 + 0.05):
                self.holes[kk] = 1
            for k in G.disc_cells(vx, vy, size / 2.0 - 0.01):
                for L in range(4):
                    comp_cells.setdefault(net, set()).add((L, k))
        return comp_cells

    def hand(self):
        """Lay the floorplan's hand-laid copper (floorplan.HAND: tracks and vias in board coordinates --
        the ADC inputs' entry, the DAC outputs' runs, the vias to the DAC's back-side parts).  A net's
        pieces must form one connected piece (checked by geometry); it becomes one component of the
        net's copper, and every pad it lands on is finished -- the router need not reach it again."""
        import floorplan as FPL
        self.hand_done = {}
        n0, v0 = len(self.tracks), len(self.vias)
        geo = {}                    # net -> [("seg", x0, y0, x1, y1, hw, layer) | ("via", x, y, r)]
        for item in FPL.HAND:
            if item[0] == "via":
                _, net, x, y, size, drill = item
                self.vias.append((round(x, 4), round(y, 4), net, size, drill))
                geo.setdefault(net, []).append(("via", x, y, size / 2.0))
            else:
                lname, net, pts, w = item
                for (p, q) in zip(pts, pts[1:]):
                    if abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6:
                        continue
                    self.tracks.append((lname, round(p[0], 4), round(p[1], 4), round(q[0], 4), round(q[1], 4), net, w))
                    geo.setdefault(net, []).append(("seg", p[0], p[1], q[0], q[1], w / 2.0, lname))
        if not geo:
            return
        def d_pt_seg(x, y, x0, y0, x1, y1):
            dx, dy = x1 - x0, y1 - y0
            tt = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy)))
            return math.hypot(x - x0 - tt * dx, y - y0 - tt * dy)
        def touch(a, b):
            pa = [(a[1], a[2])] + ([(a[3], a[4])] if a[0] == "seg" else [])
            pb = [(b[1], b[2])] + ([(b[3], b[4])] if b[0] == "seg" else [])
            tol = (a[5] if a[0] == "seg" else a[3]) + (b[5] if b[0] == "seg" else b[3]) + 0.01
            for (x, y) in pa:
                if b[0] == "seg" and d_pt_seg(x, y, b[1], b[2], b[3], b[4]) < tol:
                    return True
                if b[0] == "via" and math.hypot(x - b[1], y - b[2]) < tol:
                    return True
            for (x, y) in pb:
                if a[0] == "seg" and d_pt_seg(x, y, a[1], a[2], a[3], a[4]) < tol:
                    return True
            return False
        G = self.G
        # ---- 1. against everything already on the board (the pads, the escape): before this copper joins the grid
        n_bad = 0
        for net, items in geo.items():
            own = [self.padcells[k] for k, p in self.pads.items() if p["net"] == net and k in self.padcells] + self.ownobst.get(net, [])
            for cs in own:
                G.sub(cs)
            for it in items:
                if it[0] == "via":
                    k = G.cell(it[1], it[2]); k = k[1] * G.nx + k[0]
                    fx_, fy_ = self.fpga_xy
                    lays = [3] if (abs(it[1] - fx_) < 7.3 and abs(it[2] - fy_) < 7.3) else range(4)      # under the package only the back is open
                    if any(G.g[(LL, "mid" if it[3] <= 0.175 else "wide")][k] for LL in lays) or self.holes[k]:
                        n_bad += 1; print("  HAND: via %s at (%.2f, %.2f) has no room" % (net.split("/")[-1], it[1], it[2]))
                else:
                    hit = [k for k in G.seg_cells(it[1], it[2], it[3], it[4], G.pitch * 0.5 + 1e-6) if G.g[(LIDX[it[6]], "thin" if it[5] <= 0.1 else "mid")][k]]
                    if hit:
                        i_, j_ = hit[0] % G.nx, hit[0] // G.nx
                        n_bad += 1; print("  HAND: track %s on %s (%.2f, %.2f)-(%.2f, %.2f) hits something at (%.1f, %.1f), %d cells" % (
                            net.split("/")[-1], it[6], it[1], it[2], it[3], it[4], i_ * G.pitch, j_ * G.pitch, len(hit)))
            for cs in own:
                G.add(cs)
        # ---- 2. the hand nets against each other, by geometry (same layer, or a via against anything)
        def gap(a, b):
            la = a[6] if a[0] == "seg" else None; lb = b[6] if b[0] == "seg" else None
            if la and lb and la != lb:
                return 9.0
            ra = a[5] if a[0] == "seg" else a[3]; rb = b[5] if b[0] == "seg" else b[3]
            if a[0] == "seg" and b[0] == "seg":
                # crossing?
                def cross(o, p, q):
                    return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
                A, B, C, D = (a[1], a[2]), (a[3], a[4]), (b[1], b[2]), (b[3], b[4])
                if cross(A, B, C) * cross(A, B, D) < 0 and cross(C, D, A) * cross(C, D, B) < 0:
                    return -1.0
                d = min(d_pt_seg(A[0], A[1], *C, *D), d_pt_seg(B[0], B[1], *C, *D), d_pt_seg(C[0], C[1], *A, *B), d_pt_seg(D[0], D[1], *A, *B))
            elif a[0] == "seg":
                d = d_pt_seg(b[1], b[2], a[1], a[2], a[3], a[4])
            elif b[0] == "seg":
                d = d_pt_seg(a[1], a[2], b[1], b[2], b[3], b[4])
            else:
                d = math.hypot(a[1] - b[1], a[2] - b[2])
            return d - ra - rb
        nets_ = sorted(geo)
        for i in range(len(nets_)):
            for j in range(i + 1, len(nets_)):
                for a in geo[nets_[i]]:
                    for bb in geo[nets_[j]]:
                        g_ = gap(a, bb)
                        if g_ < 0.127:
                            n_bad += 1
                            print("  HAND: %s and %s only %.3f apart at (%.2f, %.2f)" % (nets_[i].split("/")[-1], nets_[j].split("/")[-1], g_, a[1], a[2]))
        self._register(n0, v0)
        def cells_of(it):
            if it[0] == "via":
                return {(L, k) for k in G.disc_cells(it[1], it[2], it[3] - 0.01) for L in range(4)}
            return {(LIDX[it[6]], k) for k in G.seg_cells(it[1], it[2], it[3], it[4], max(it[5] - 0.01, G.pitch * 0.5 + 1e-6))}
        for net, items in geo.items():
            # the connected pieces (union-find over the items): one component each
            par = list(range(len(items)))
            def root(i):
                while par[i] != i:
                    par[i] = par[par[i]]; i = par[i]
                return i
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    if touch(items[i], items[j]):
                        par[root(i)] = root(j)
            groups = {}
            for i in range(len(items)):
                groups.setdefault(root(i), set()).update(cells_of(items[i]))
            if len(groups) > 1:
                print("  HAND: %s is laid in %d separate pieces (the router joins them)" % (net.split("/")[-1], len(groups)))
            self.comps.setdefault(net, []).extend(groups.values())
            # every pad this copper lands on is finished: the router need not reach it again
            for key, p in self.pads.items():
                if p["net"] != net or key[0] == "U1":
                    continue
                r = min(p["w"], p["h"]) / 2.0
                for it in items:
                    hit = (it[0] == "seg" and d_pt_seg(p["x"], p["y"], it[1], it[2], it[3], it[4]) < r + it[5]) or \
                          (it[0] == "via" and math.hypot(p["x"] - it[1], p["y"] - it[2]) < r + it[3])
                    if hit and (p["th"] or it[0] == "via" or it[6] == p["layer"]):
                        self.hand_done.setdefault(net, set()).add(key)
                        break
        print("  hand copper: %d tracks, %d vias, %d nets, %d pads finished, %d collisions" % (
            len(self.tracks) - n0, len(self.vias) - v0, len(geo), sum(len(v) for v in self.hand_done.values()), n_bad))

    def fine_grid(self, pitch):
        """Rebuild the obstacle grid at `pitch` from the pads, the escape and everything routed so far,
        with every net's copper (tracks and vias, on their layers) as that net's own, connected component."""
        self.grid(pitch=pitch)
        G = self.G
        self.laidobst = {}
        comps = {}
        for (lname, x0, y0, x1, y1, net, w) in self.tracks:
            if net == "GND":
                continue
            L = LIDX[lname]
            for k in G.seg_cells(x0, y0, x1, y1, max(w / 2.0 - 0.01, G.pitch * 0.5 + 1e-6)):
                comps.setdefault(net, set()).add((L, k))
        for (vx, vy, net, size, drill) in self.vias:
            if net == "GND":
                continue
            for k in G.disc_cells(vx, vy, size / 2.0 - 0.01):
                for L in range(4):
                    comps.setdefault(net, set()).add((L, k))
        for net, (L, ex, ey) in self.esc["exits"].items():
            ci, cj = G.cell(ex, ey)
            comps.setdefault(net, set()).add((L, cj * G.nx + ci))
        self.comps = {n: [c] for n, c in comps.items()}
        self.comps_fixed = {n: [set(c) for c in cs] for n, cs in self.comps.items()}

    def comps_all_cells(self, net):
        out = set()
        for c in self.comps_fixed.get(net, []):
            out |= c
        return out

    def foreign(self, net):
        """A digital net that has no business in the analog strip."""
        c = net_class(net)
        if not (c in ("HS", "USB", "MDI") or net.startswith("/FPGA") or net.startswith("/Gigabit")):
            return False
        ax0, ay0, ax1, ay1 = ANALOG_REGION
        for key, p in self.pads.items():
            if p["net"] == net and ax0 <= p["x"] <= ax1 and ay0 <= p["y"] <= ay1:
                return False
        return True

    # ---------------------------------------------------------------- ground vias
    def _via_beside(self, key, p, net, via=VIA_STD):
        """A via of `net` next to pad `p` with a stub from the pad, where the
        grid allows it.  Returns (vx, vy) or None."""
        G = self.G
        L = LIDX[p["layer"]]
        cells = self.padcells[key]
        G.sub(cells)
        # the pad's overlapping same-net twins go with it: the USB-C's A1/B12 and A12/B1 ground pads are
        # drawn as two pads on one spot (plus a shell pad over them), so the via always saw foreign copper
        # (and a same-net pad of ANOTHER part that overlaps it in projection -- a front resistor's ground pad over a
        #  back capacitor's -- so one via through both can stitch both: build 16's R2502.2 / C2331.2)
        twins = [k2 for k2, q in self.pads.items() if k2 != key and q["net"] == p["net"]
                 and abs(q["x"] - p["x"]) < (p["w"] + q["w"]) / 2.0 + 0.3 and abs(q["y"] - p["y"]) < (p["h"] + q["h"]) / 2.0 + 0.3]
        for k2 in twins:
            G.sub(self.padcells[k2])
        found = None
        sw = min(0.3, p["w"], p["h"])                     # the stub is never wider than its pad
        # a pad with a neighbour closer than 0.65 mm (a QFP/QFN row) only leaves outward
        px_, py_, _r, _l = self.pl.placed[key[0]]
        # a pad in a fine-pitch row: small, with a same-part neighbour closer than 0.9 mm (an exposed pad or a
        # connector's big pad has neighbours but is not one)
        fine = min(p["w"], p["h"]) <= 0.5 and any(k2[0] == key[0] and k2 != key and abs(q["x"] - p["x"]) + abs(q["y"] - p["y"]) < 0.9 for k2, q in self.pads.items())
        outward = math.degrees(math.atan2(p["y"] - py_, p["x"] - px_))
        angles = sorted(range(0, 360, 45), key=lambda a: abs((a - outward + 180) % 360 - 180))
        dists = (0.9, 1.2, 1.5, 1.9, 2.4, 3.0, 3.6)
        tries = [(dists, angles)]
        if min(p["w"], p["h"]) >= 1.5:
            tries = [((0.0, 0.6, 0.9), angles)] + tries        # an exposed pad: the via goes in the pad itself
        mates = [q for k2, q in self.pads.items() if k2[0] == key[0] and k2 != key]
        if key[0].startswith("C") and len(mates) == 1 and min(p["w"], p["h"]) >= 0.45:
            # a decoupling capacitor: a 0.3 mm via IN its ground pad (the board is a via-in-pad process
            # because of the BGA), else straight out along the capacitor's axis, away from the other pad
            q = mates[0]
            away = math.degrees(math.atan2(p["y"] - q["y"], p["x"] - q["x"]))
            tries = [((0.0,), [0]), ((0.6, 0.9, 1.2), [away])] + tries
        if fine:
            # along the pad's long axis only.  A 0.4-0.65 mm row (QFP, QFN, MSOP, jack): first INWARD, under
            # the package body (an LQFP, SOIC or jack has nothing there; a QFN's exposed pad blocks it and the
            # attempt fails harmlessly) -- a via 0.9 mm out in front of a ground pad walls in the signal pads
            # beside it (its 0.46 mm halo is wider than the pitch); then outward BEYOND the row's fan-out
            # lane, staggered pad by pad; then the old search.  A 0.8 mm row (the SDRAM): outward 0.9 mm
            # first, as build 6 had it -- the halo is narrower than the pitch, and build 8's inward vias sat
            # under the body where its bus comes in from the FPGA (it lost 10 more SDRAM bits than build 6).
            along = 0.0 if (p["w"] >= p["h"]) else 90.0
            cands_ = [along, (along + 180.0) % 360.0]
            out_a = min(cands_, key=lambda a: abs((a - outward + 180) % 360 - 180))
            in_a = max(cands_, key=lambda a: abs((a - outward + 180) % 360 - 180))
            sw = min(sw, min(p["w"], p["h"]) - 0.02)
            stagger = (sum(ord(ch) for ch in str(key[1])) % 2) * 0.8     # deterministic
            nb = min(abs(q["x"] - p["x"]) + abs(q["y"] - p["y"]) for k2, q in self.pads.items() if k2[0] == key[0] and k2 != key)
            tight = nb < 0.7
            tries = [((0.9, 1.2, 1.5, 1.9), [in_a]),
                     ((2.6 + stagger, 3.4 + stagger, 4.2 + stagger), [out_a]),
                     ((0.9, 1.2, 1.5, 1.9, 2.4), sorted(range(0, 360, 45), key=lambda a: abs((a - outward + 180) % 360 - 180)))]
            if not tight:
                tries = [((0.9, 1.2, 1.5, 1.9), [out_a])] + tries
        for dists, angles in tries:
          if found:
            break
          for d in dists:
            for a in angles:
                vx = p["x"] + d * math.cos(math.radians(a)); vy = p["y"] + d * math.sin(math.radians(a))
                ci, cj = G.cell(vx, vy)
                if not fine:
                    vx, vy = G.pos(ci, cj)
                # a fine-pitch pad's via stays exactly on the pad's axis: snapped across it, the stub ran at a
                # slant and came 0.123 mm from the next pad of a 0.5 mm row (build 8's two DRC errors)
                k = cj * G.nx + ci
                if ci < 3 or cj < 3 or ci >= G.nx - 3 or cj >= G.ny - 3:
                    continue
                vcls = "mid" if (d == 0.0 and min(p["w"], p["h"]) < 1.5) else "wide"
                if any(G.g[(LL, vcls)][k] for LL in range(4)) or self.holes[k]:
                    continue
                scls = R.width_class(sw)
                stub = G.seg_cells(p["x"], p["y"], vx, vy, sw / 2.0 + R.CLEAR)
                if any(G.g[(L, scls)][kk] for kk in stub if kk not in set(cells.get((L, scls), ()))):
                    continue
                vs = VIA_SIG if (d == 0.0 and min(p["w"], p["h"]) < 1.5) else via      # in a small pad: the small via
                self.vias.append((vx, vy, net, vs[0], vs[1]))
                if math.hypot(vx - p["x"], vy - p["y"]) > 0.01:          # a via in the pad itself needs no stub
                    self.tracks.append((p["layer"], p["x"], p["y"], vx, vy, net, sw))
                    scells = G.obstacle_cells("seg", [L], (p["x"], p["y"], vx, vy, sw / 2.0))
                    G.add(scells)
                    if net != "GND":
                        self.ownobst.setdefault(net, []).append(scells)
                vcells = G.obstacle_cells("disc", [0, 1, 2, 3], (vx, vy, vs[0] / 2.0))
                G.add(vcells)
                if net != "GND":
                    self.ownobst.setdefault(net, []).append(vcells)      # lifted while the net routes: it may land on its own via
                for kk in G.disc_cells(vx, vy, via[1] + 0.25 + 0.05):
                    self.holes[kk] = 1
                found = (vx, vy)
                break
            if found:
                break
        G.add(cells)
        for k2 in twins:
            G.add(self.padcells[k2])
        return found

    def ground_vias(self):
        n_ok = n_fail = 0
        gnd_vias = [(vx, vy) for (vx, vy, n2, _s, _d) in self.vias if n2 == "GND"]
        # a ground pad a river already gave a stub and via (pcb/river.py, the fine-pitch side rows) is done
        gnd_stubs = [(x0, y0) for (ln, x0, y0, x1, y1, n2, w) in self.tracks if n2 == "GND"]
        for key, p in sorted(self.pads.items()):
            if any(abs(sx - p["x"]) < 0.05 and abs(sy - p["y"]) < 0.05 for (sx, sy) in gnd_stubs):
                gnd_vias.append((p["x"], p["y"]))
            if p["net"] != "GND" or p["th"] or key[0] == "U1":
                continue
            if any(abs(vx - p["x"]) < p["w"] / 2.0 + 0.1 and abs(vy - p["y"]) < p["h"] / 2.0 + 0.1 for (vx, vy) in gnd_vias):
                n_ok += 1
                continue            # the pad sits on a via of the net (a ball via, or a via in an overlapping pad on the other side)
            if self._via_beside(key, p, "GND"):
                n_ok += 1
            else:
                n_fail += 1
                self.report.setdefault("gnd_unstitched", []).append("%s.%s" % key[:2])
        print("  ground vias: %d placed, %d pads left for the router" % (n_ok, n_fail))

    def rail_vias(self):
        """The planes on In4: every pad of a plane's rail that lies over the plane
        gets a via into it; a pad elsewhere gets a via at the nearest point of the
        plane, which the router then joins it to.  The plane's vias are one
        connected component of the net."""
        G = self.G
        stats = {}
        for (net, poly, pri) in RAIL_ZONES:
            # where this plane really has copper: its polygon minus every higher-priority plane's
            holes_ = [q for (n2, q, pri2) in RAIL_ZONES if pri2 > pri]
            def edge_dist(x, y, q):
                return min(_pt_seg(x, y, q[i][0], q[i][1], q[(i + 1) % len(q)][0], q[(i + 1) % len(q)][1]) for i in range(len(q)))
            def over(x, y):
                # 0.7 mm inside the plane and 0.7 mm clear of every higher plane: the fill keeps a clearance from
                # the other plane's edge, and a via on that seam dangles (build 14: ten of them)
                if not in_poly(x, y, poly) or edge_dist(x, y, poly) < 0.7:
                    return False
                return not any(in_poly(x, y, q) or edge_dist(x, y, q) < 0.7 for q in holes_)
            comp = set()
            n_in = n_out = n_fail = 0
            for key, p in sorted(self.pads.items()):
                if p["net"] != net or key[0] == "U1":
                    continue
                if any(abs(vx - p["x"]) < 0.3 and abs(vy - p["y"]) < 0.3 for (vx, vy, n2, _s, _d) in self.vias if n2 == net):
                    continue        # a decoupling capacitor on a ball via (or a pad with a hand-laid via): already on the net's copper
                ci, cj = G.cell(p["x"], p["y"])
                if over(p["x"], p["y"]):
                    if p["th"]:
                        comp |= {(L, cj * G.nx + ci) for L in range(4)}
                        n_in += 1
                        continue
                    v = self._via_beside(key, p, net)
                    if v:
                        vi, vj = G.cell(*v)
                        comp |= {(L, vj * G.nx + vi) for L in range(4)}
                        comp.add((LIDX[p["layer"]], cj * G.nx + ci))
                        n_in += 1
                    else:
                        n_fail += 1
                else:
                    # the nearest free spot inside the plane, up to 15 mm away: a via there
                    best = None
                    for dj in range(-75, 76):
                        for di in range(-75, 76):
                            if abs(di) + abs(dj) > 110:
                                continue
                            i2, j2 = ci + di, cj + dj
                            if i2 < 3 or j2 < 3 or i2 >= G.nx - 3 or j2 >= G.ny - 3:
                                continue
                            x2, y2 = G.pos(i2, j2)
                            if not over(x2, y2):
                                continue
                            d = di * di + dj * dj
                            if best is not None and d >= best[0]:
                                continue
                            k2 = j2 * G.nx + i2
                            if self.holes[k2] or any(G.g[(LL, "wide")][k2] for LL in range(4)):
                                continue
                            if any(abs(vx - x2) < 0.9 and abs(vy - y2) < 0.9 for (vx, vy, _n, _s, _d) in self.vias):
                                continue        # another via's clearance halo would cut this one off the fill (build 17: the RAILS +3V3 via)
                            best = (d, i2, j2, x2, y2)
                    if best is None:
                        n_fail += 1
                        continue
                    _, i2, j2, x2, y2 = best
                    self.vias.append((x2, y2, net, VIA_STD[0], VIA_STD[1]))
                    self.edge_vias.append((x2, y2, net))
                    vcells = G.obstacle_cells("disc", [0, 1, 2, 3], (x2, y2, VIA_STD[0] / 2.0))
                    G.add(vcells)
                    self.ownobst.setdefault(net, []).append(vcells)
                    for kk in G.disc_cells(x2, y2, VIA_STD[1] + 0.25 + 0.05):
                        self.holes[kk] = 1
                    comp |= {(L, j2 * G.nx + i2) for L in range(4)}
                    n_out += 1
            # vias of the net that already stand in the plane (the BGA's core balls and feed via in the 1.1 V plane) join it
            for (vx, vy, n2, _s, _d) in self.vias:
                if n2 == net and over(vx, vy):
                    vi, vj = G.cell(vx, vy)
                    comp |= {(L, vj * G.nx + vi) for L in range(4)}
            if comp:
                cs = self.comps.setdefault(net, [])
                cs[:] = [c for c in cs if not (c & comp)] + [comp]
            st = stats.setdefault(net, [0, 0, 0]); st[0] += n_in; st[1] += n_out; st[2] += n_fail
        for net, (a, b, c) in stats.items():
            print("  %s plane: %d pads over it (via each), %d pads elsewhere given a via at its edge, %d without room" % (net, a, b, c))
        self.report["rail_planes"] = {n: {"pads_over_plane": a, "pads_joined_at_edge": b, "no_room": c} for n, (a, b, c) in stats.items()}

    # ---------------------------------------------------------------- routing
    def terminals(self, net):
        """[(L, k, kind)] for every connection point of a net."""
        G = self.G
        out = []
        for key, p in self.pads.items():
            if p["net"] != net:
                continue
            if key[0] == "U1":
                continue            # the escape made its terminal
            if key in getattr(self, "hand_done", {}).get(net, ()):
                continue            # hand-laid copper lands on this pad: it is part of that component
            px, py = p["x"], p["y"]
            for (vx, vy, n2, _s, _d) in self.vias:
                if n2 == net and abs(vx - px) < 0.3 and abs(vy - py) < 0.3:
                    px, py = vx, vy             # a decoupling capacitor's pad on a ball via: its point is the via
                    break
            ci, cj = G.cell(px, py)
            k = cj * G.nx + ci
            layers = [0, 1, 2, 3] if p["th"] else [LIDX[p["layer"]]]
            for L in layers:
                out.append((L, k, key))
        return out

    def route_all(self, budget_s=1500):
        G = self.G
        nets = [n for n in self.numof if n and n != "GND" and not n.startswith("unconnected-")]
        # order: the FPGA's buses first (they are the hard ones), then the rest shortest first, then the rails
        fx, fy = self.fpga_xy
        dest = {}
        for key, p in self.pads.items():
            if key[0] != "U1" and p["net"]:
                dest.setdefault(p["net"], []).append((p["x"], p["y"]))
        def prio(n):
            c = net_class(n)
            if c in ("Power", "Rail"):
                return (2, 0, 0, 0)
            ex = self.esc["exits"].get(n)
            if ex:
                # the FPGA's buses first, face by face.  Along a face the exits stand 0.4 mm apart, too close
                # for anything to pass between them, so they can only fan out as a staircase: the one nearest
                # the side its destination lies on turns first, the next one turns one step further out.
                # Build 15 routed the south face west to east; its westmost exit turned east first and
                # walled the other twelve (four never got out).
                L, x, y = ex
                side = 0 if x < fx - 7 else 1 if x > fx + 7 else 2 if y < fy else 3
                pts = dest.get(n, [])
                dx = (sum(q[0] for q in pts) / len(pts) - x) if pts else 0.0
                dy = (sum(q[1] for q in pts) / len(pts) - y) if pts else 0.0
                if side in (2, 3):
                    return (0, side, 0, -x) if dx >= 0 else (0, side, 1, x)      # east-bound: east to west; west-bound: west to east
                return (0, side, 0, y) if dy <= 0 else (0, side, 1, -y)          # north-bound: north to south; south-bound: south to north
            return (1, 0, 0, 0)
        def width_of(n):
            """One width rule for both passes.  Builds 1-25 computed the first pass's width inline and never looked
            at self.rf, so all six SMA feeds went out at 0.15 mm (the cloud review of PR #2 found it; measured)."""
            if n in self.rf:
                return RF_W
            c = net_class(n); w = CLASS_WIDTH.get(c, 0.15)
            if c == "Rail":
                return 0.2 if n in THIN_RAILS else RAIL_W
            return 0.127 if (n in self.esc["exits"] and c == "Default") else w
        t_start = time.time()
        results = {}
        self.n_fixed_tracks, self.n_fixed_vias = len(self.tracks), len(self.vias)
        self.comps_fixed = {n: [set(c) for c in cs] for n, cs in self.comps.items()}
        order = sorted(nets, key=lambda n: (prio(n), n))
        for n_done, net in enumerate(order):
            if n_done % 50 == 0:
                print("  routing %d/%d, %.0f s" % (n_done, len(order), time.time() - t_start), flush=True)
            if time.time() - t_start > budget_s:
                results[net] = "skipped (time)"
                continue
            terms = self.terminals(net)
            if net in getattr(self, "river_done", {}) and all(t[2] in self.river_done[net] for t in terms):
                results[net] = True             # a river finished it: the chip pad, the lane, the ball
                continue
            # pads that are the same (TH) count once per layer but one terminal point; the net's existing
            # copper (an escape exit, a plane's vias, an island feed) counts as terminals too
            if len({t[2] for t in terms}) + len(self.comps.get(net, [])) < 2:
                continue
            ok = self.route_net(net, terms, width_of(net))
            results[net] = ok
        # one more go at what failed, now that everything else is in place
        # the retry pass searches four times harder: pcb/route_diag2.py found paths with 2 M pops for
        # connections the 600 k budget had given up on
        self.retry_mode = True
        for net in [n for n, v in results.items() if v is not True]:
            if time.time() - t_start > 0.75 * budget_s:
                break               # the last quarter of the budget is the fine grid's (build 8 left it nothing)
            results[net] = self.route_net(net, self.terminals(net), width_of(net))
        left = [n for n, v in results.items() if v is not True]
        if left and time.time() - t_start < budget_s:
            # a second, finer grid for what is left.  The 0.2 mm grid matches the BGA (0.8), the SDRAM (0.8)
            # and the 0.4 mm QFPs/QFN/jack, but the 0.5 mm LQFPs (DAC, FTDI, Si5351), the 0.65 mm MSOPs and the
            # 1.27 mm SOICs land between its cells, where a pad's only free corridor is 0.015 mm wide.  The
            # grid is rebuilt at 0.1 mm from everything laid so far and the leftover nets routed on it.
            print("  fine grid: %d nets left after %.0f s; rebuilding the grid at 0.1 mm" % (len(left), time.time() - t_start), flush=True)
            self.fine_grid(0.1)
            n_before = len(left)
            for net in left:
                if time.time() - t_start > budget_s:
                    break
                results[net] = self.route_net(net, self.terminals(net), width_of(net))
            n_after = sum(1 for n in left if results[n] is not True)
            self.report["fine_grid"] = {"nets_tried": n_before, "nets_routed": n_before - n_after}
            print("  fine grid: routed %d of the %d" % (n_before - n_after, n_before), flush=True)
        self.retry_mode = False
        self.report["routing"] = results
        n_ok = sum(1 for v in results.values() if v is True)
        print("routed %d of %d nets in %.0f s" % (n_ok, len(results), time.time() - t_start))
        self.report["unrouted"] = sorted(n for n, v in results.items() if v is not True)

    def rip(self, net):
        """Take a net's laid copper out again (its escape copper stays)."""
        G = self.G
        for cells in self.laidobst.pop(net, []):
            G.sub(cells)
        keep = self.tracks[:self.n_fixed_tracks] + [t for t in self.tracks[self.n_fixed_tracks:] if t[5] != net]
        self.tracks[:] = keep
        keep = self.vias[:self.n_fixed_vias] + [v for v in self.vias[self.n_fixed_vias:] if v[2] != net]
        self.vias[:] = keep
        self.comps[net] = [set(c) for c in self.comps_fixed.get(net, [])]

    def route_net(self, net, terms, width):
        foreign = self.foreign(net)
        if foreign:
            self.G.add(self.analog_keep)
        try:
            return self._route_net(net, terms, width)
        finally:
            if foreign:
                self.G.sub(self.analog_keep)

    def _route_net(self, net, terms, width):
        G = self.G
        cls = R.width_class(width)
        # lift the net's own pads
        own = [self.padcells[t[2]] for t in terms if isinstance(t[2], tuple) and t[2] in self.padcells]
        own += self.ownobst.get(net, []) + self.laidobst.get(net, [])
        seen = set()
        for cells in own:
            key = id(cells)
            if key in seen:
                continue
            seen.add(key)
            G.sub(cells)
        holes = self.holes
        via_ok = lambda i, j: not holes[j * G.nx + i]
        new_obst = []
        laid = []
        power = net_class(net) in ("Power", "Rail")
        via = VIA_STD if power else VIA_SIG
        via_cls = "wide" if power else "mid"
        # a bus bit leaving the BGA stays on its escape layer unless a via saves
        # a lot: every via is a post through all four routing layers that the
        # rest of the ribbon then has to get round
        via_cost = EXIT_VIA_COST if net in self.esc["exits"] else R.VIA_COST
        # group terminal points: TH pads give several (one per layer) -> one group
        groups = {}
        narrow = {}             # group -> the narrowest dimension of its pad: a track into a fine-pitch pad
        for (L, k, kind) in terms:
            key = kind if kind in ("exit",) or isinstance(kind, tuple) else (kind, k)
            groups.setdefault(key, []).append((L, k))
            if isinstance(kind, tuple) and kind in self.pads:
                q = self.pads[kind]
                narrow[key] = min(q["w"], q["h"])
        glist = list(groups.values())
        gnarrow = {id(g): narrow.get(key) for key, g in groups.items()}
        comps = sorted((set(c) for c in self.comps.get(net, [])), key=len, reverse=True)
        owned = set(comps[0]) if comps else set()
        glist = [sorted(c) for c in comps[1:]] + glist       # the other components are joined like terminals
        # greedy chain: start from the group nearest the net's existing copper, else the first
        def centre(gr):
            L, k = gr[0]
            return (k % G.nx, k // G.nx)
        remaining = glist[:]
        if not owned:
            first = remaining.pop(0)
            owned |= set(first)
        unreached = []
        ok_all = True
        for cells in own:
            pass
        while remaining:
            # nearest remaining group to the owned copper (by centre distance)
            oc = [(k % G.nx, k // G.nx) for (L, k) in list(owned)[:200]]
            def dist(gr):
                c = centre(gr)
                return min(abs(c[0] - o[0]) + abs(c[1] - o[1]) for o in oc)
            remaining.sort(key=dist)
            gr = remaining.pop(0)
            if set(gr) & owned:
                continue            # already on the net's copper (a pad on a via of the net)
            c = centre(gr)
            pts = oc + [c]
            i0 = max(0, min(p[0] for p in pts) - 40); i1 = min(G.nx - 1, max(p[0] for p in pts) + 40)
            j0 = max(0, min(p[1] for p in pts) - 40); j1 = min(G.ny - 1, max(p[1] for p in pts) + 40)
            path = None
            # a track wider than the pad it enters sticks out past it (its round end) and into the
            # neighbouring pad's clearance on a 0.4/0.5 mm pitch: this connection is laid no wider than the pad
            w_here = width
            # a path may also END on a fine-pitch pad of the net's existing copper, so the narrowest pad
            # of the whole net sets the width once the net has one narrower than its class
            nd = min([v for v in narrow.values() if v is not None] or [width])
            if nd < width:
                w_here = max(0.127, nd - 0.02)
            cls_here = R.width_class(w_here)
            used_cls, used_w = cls_here, w_here
            for try_cls, try_w in [(cls_here, w_here)] + [(c, CLASS_W[c]) for c in R.CLS if CLASSES_HW[c] < CLASSES_HW[cls_here]][::-1]:
                for margin in (40, 400):
                    bb = (max(0, min(p[0] for p in pts) - margin), max(0, min(p[1] for p in pts) - margin),
                          min(G.nx - 1, max(p[0] for p in pts) + margin), min(G.ny - 1, max(p[1] for p in pts) + margin))
                    pops = (250000 if margin < 400 else 600000) * (8 if getattr(self, "retry_mode", False) else 1)
                    path = G.route(net, gr, owned, try_cls, bb, via_ok_fn=via_ok, max_pop=pops, via_cls=via_cls, via_cost=via_cost)
                    if path:
                        break
                if path:
                    used_cls, used_w = try_cls, (try_w if try_cls != cls_here else w_here)
                    if try_cls != cls:
                        self.report.setdefault("narrowed", []).append("%s: %s -> %s" % (net, cls, try_cls))
                    break
            if not path:
                ok_all = False
                unreached.append(set(gr))
                self.report.setdefault("failed_connections", []).append("%s: %s" % (net, str(gr[0])))
                continue
            segs, vias = R.simplify(path, G.pitch)
            for (L, x0, y0, x1, y1) in segs:
                self.tracks.append((LNAME[L], x0, y0, x1, y1, net, used_w))
                new_obst.append(G.obstacle_cells("seg", [L], (x0, y0, x1, y1, used_w / 2.0)))
            for (vx, vy) in vias:
                self.vias.append((vx, vy, net, via[0], via[1]))
                new_obst.append(G.obstacle_cells("disc", [0, 1, 2, 3], (vx, vy, via[0] / 2.0)))
                for kk in G.disc_cells(vx, vy, via[1] / 2.0 + 0.25 + VIA_STD[1] / 2.0 + 0.05):
                    holes[kk] = 1
            for (L, i, j) in path:
                owned.add((L, j * G.nx + i))
                laid.append((L, i, j))
            owned |= set(gr)
        # what the net really owns on copper: its pre-existing vias plus the paths laid.  A bare
        # terminal of a connection that failed is not copper; if it were counted, a retry would
        # find every terminal "already reached" and report a connection it never made.
        self.comps[net] = [owned] + [c for c in unreached if c & set(self.comps_all_cells(net))] if not ok_all else [owned]
        # the net's copper goes into the grid only now, so its later terminals could reach its earlier tracks
        for cells in new_obst:
            G.add(cells)
        self.laidobst.setdefault(net, []).extend(new_obst)
        seen = set()
        for cells in own:
            key = id(cells)
            if key in seen:
                continue
            seen.add(key)
            G.add(cells)
        return ok_all

    # ---------------------------------------------------------------- return-path vias
    def return_vias(self, reach=1.5):
        """Every signal via changes the reference plane the return current
        rides on; a ground via within `reach` mm gives that current its path.
        Where none exists, one is added (the BGA field has its own)."""
        G = self.G
        fx, fy = self.fpga_xy
        gnd = [(vx, vy) for (vx, vy, n, _s, _d) in self.vias if n == "GND"]
        n_had = n_add = n_fail = 0
        tx_, ty_, _, _ = self.pl.placed["T401"]
        for (vx, vy, net, size, drill) in list(self.vias):
            if net == "GND" or math.hypot(vx - fx, vy - fy) < 8.5:
                continue
            if vx > tx_ - 0.7 - 1.6 and vy < ty_ + 10.0 + 1.6:
                continue        # the Ethernet island and its moat: no ground plane there for a via to reach
            if any(abs(gx - vx) <= reach and abs(gy - vy) <= reach and math.hypot(gx - vx, gy - vy) <= reach for (gx, gy) in gnd):
                n_had += 1
                continue
            done = False
            for d in (0.75, 0.9, 1.1, 1.3):
                for a in range(0, 360, 45):
                    px = vx + d * math.cos(math.radians(a)); py = vy + d * math.sin(math.radians(a))
                    ci, cj = G.cell(px, py); px, py = G.pos(ci, cj)
                    k = cj * G.nx + ci
                    if ci < 3 or cj < 3 or ci >= G.nx - 3 or cj >= G.ny - 3 or self.holes[k]:
                        continue
                    if any(G.g[(LL, "wide")][k] for LL in range(4)):
                        continue
                    self.vias.append((px, py, "GND", VIA_STD[0], VIA_STD[1]))
                    gnd.append((px, py))
                    G.add(G.obstacle_cells("disc", [0, 1, 2, 3], (px, py, VIA_STD[0] / 2.0)))
                    for kk in G.disc_cells(px, py, VIA_STD[1] + 0.25 + 0.05):
                        self.holes[kk] = 1
                    done = True
                    break
                if done:
                    break
            if done:
                n_add += 1
            else:
                n_fail += 1
        self.report["return_vias"] = {"signal_vias_with_ground_via_within_%.1fmm" % reach: n_had, "ground_vias_added": n_add, "no_room": n_fail}
        print("  return-path vias: %d signal vias already had one within %.1f mm, %d added, %d without room" % (n_had, reach, n_add, n_fail))

    # ---------------------------------------------------------------- vias nothing uses
    def prune(self):
        """rail_vias gives a pad that lies off its plane a via at the plane's edge and tells the router the
        via is part of the plane; the router may then join the pad to ANOTHER via of the plane and never
        touch this one, which then connects the plane to nothing (KiCad: "via dangling", builds 16-18: ten
        of them).  Drop every edge via that no track ends on."""
        ends = {}
        for (ln, x0, y0, x1, y1, net, w) in self.tracks:
            ends.setdefault(net, []).extend(((x0, y0), (x1, y1)))
        def used(x, y, net):
            return any(abs(ex - x) < 0.3 and abs(ey - y) < 0.3 for (ex, ey) in ends.get(net, ()))
        drop = {(round(x, 3), round(y, 3), net) for (x, y, net) in self.edge_vias if not used(x, y, net)}
        if drop:
            self.vias[:] = [v for v in self.vias if (round(v[0], 3), round(v[1], 3), v[2]) not in drop]
        self.report["edge_vias_unused_dropped"] = sorted(drop)
        print("  plane-edge vias: %d placed, %d unused and dropped" % (len(self.edge_vias), len(drop)))

    # ---------------------------------------------------------------- stubs from pads to grid points
    def pad_stubs(self):
        """A pad centre is rarely on the 0.2 mm grid; a short segment joins it
        to the cell the router used."""
        G = self.G
        done = set()
        for key, p in self.pads.items():
            if key[0] == "U1" or not p["net"] or p["net"].startswith("unconnected") or p["net"] == "GND":
                continue
            if key in done:
                continue
            done.add(key)
            ci, cj = G.cell(p["x"], p["y"]); gx, gy = G.pos(ci, cj)
            if abs(gx - p["x"]) > 1e-6 or abs(gy - p["y"]) > 1e-6:
                lname = p["layer"] if not p["th"] else "F.Cu"
                self.tracks.append((lname, p["x"], p["y"], gx, gy, p["net"], 0.127))
        for net, (L, ex, ey) in self.esc["exits"].items():
            ci, cj = G.cell(ex, ey); gx, gy = G.pos(ci, cj)
            if abs(gx - ex) > 1e-6 or abs(gy - ey) > 1e-6:
                self.tracks.append((LNAME[L], ex, ey, gx, gy, net, escape.W))

    # ---------------------------------------------------------------- silkscreen
    def _region_of(self, ref):
        """The bounding box of the section box the part belongs to (its labels stay inside it), or None."""
        sec = getattr(self.pl, "section", {}).get(ref)
        poly = getattr(self, "section_polys", {}).get(sec) if sec else None
        if not poly:
            return None
        xs = [q[0] for q in poly]; ys = [q[1] for q in poly]
        return (min(xs) + 0.3, min(ys) + 0.3, max(xs) - 0.3, max(ys) - 0.3)

    def _put(self, layer, lines, prefer, maxd=10.0, rot_ok=False, must=True, tag="", rot=None, region=None, ref=None):
        """A block of text lines [(text, size, bold)] on a free spot of
        `layer` ("F.Cu"/"B.Cu") near `prefer`; claims the spot.  Returns the
        box, or None when it does not fit and must is False.  `ref` names the
        part the text belongs to: the text then stays inside that part's
        section box (region), falling back to anywhere only when it has to."""
        occ = self.occ[layer]
        w = max(SK.text_w(t, sz, b) for t, sz, b in lines)
        h = sum(SK.text_h(sz) for t, sz, b in lines) + 0.3 * (len(lines) - 1)
        if region is None and ref is not None and layer == "F.Cu":
            region = self._region_of(ref)
        if region is not None:
            region = (region[0] + w / 2.0, region[1] + h / 2.0, region[2] - w / 2.0, region[3] - h / 2.0)   # spot() tests the centre
            if region[0] > region[2] or region[1] > region[3]:
                region = None
        sp = occ.spot(w, h, prefer, maxd=maxd, rot_ok=rot_ok, rot=rot, region=region)
        if sp is None:
            sp = occ.spot(w, h, prefer, maxd=maxd * 2.5, rot_ok=rot_ok, rot=rot, region=region)
        if sp is None and region is not None:
            self.report.setdefault("silk_outside_box", []).append(tag or lines[0][0])
            sp = occ.spot(w, h, prefer, maxd=maxd * 2.5, rot_ok=rot_ok, rot=rot)
        if sp is None:
            if not must:
                return None
            self.report.setdefault("silk_unplaced", []).append(tag or lines[0][0])
            sp = (prefer[0] - h / 2.0, prefer[1] - w / 2.0, 90) if rot == 90 else (prefer[0] - w / 2.0, prefer[1] - h / 2.0, 0)
        x0, y0, rot = sp
        lname = "F.SilkS" if layer == "F.Cu" else "B.SilkS"
        if rot == 0:
            occ.claim(x0, y0, x0 + w, y0 + h)
            y = y0
            for t, sz, b in lines:
                th = SK.text_h(sz)
                ax = x0 if layer == "F.Cu" else x0 + SK.text_w(t, sz, b)
                self.texts.append(B.text(ax, y + th / 2.0, t, lname, sz, bold=b))
                y += th + 0.3
            return (x0, y0, x0 + w, y0 + h)
        occ.claim(x0, y0, x0 + h, y0 + w)
        x = x0
        for t, sz, b in lines:
            th = SK.text_h(sz)
            self.texts.append(B.text(x + th / 2.0, y0 + w, t, lname, sz, bold=b, angle=90))
            x += th + 0.3
        return (x0, y0, x0 + h, y0 + w)

    def _title(self, layer, options):
        """The first of `options` (lists of lines) that fits the largest empty area."""
        occ = self.occ[layer]
        r = occ.largest()
        for lines in options:
            w = max(SK.text_w(t, sz, b) for t, sz, b in lines)
            h = sum(SK.text_h(sz) for t, sz, b in lines) + 0.3 * (len(lines) - 1)
            if r and r[2] - r[0] >= w + 1.0 and r[3] - r[1] >= h + 1.0:
                return self._put(layer, lines, ((r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0), maxd=4.0, tag="title")
        self._put(layer, options[-1], (P.BW / 2.0, P.BH / 2.0), maxd=60.0, tag="title")

    def silk(self):
        self.occ = {"F.Cu": SK.Occ(self.pl, "F.Cu"), "B.Cu": SK.Occ(self.pl, "B.Cu")}
        self.lines = []
        placed = self.pl.placed
        def at(ref, dx=0.0, dy=0.0):
            x, y, rot, layer = placed[ref]
            return (x + dx, y + dy)
        # ---- the section boxes first: everything else keeps off their lines
        self._section_boxes()
        # ---- the title block, front and back, where there is room
        self._title("F.Cu", [
            [("ECP5+ADC+DAC", 2.0, True), ("by Jason Gallicchio and Claude", 1.0, False), ("github.com/gallicchio", 1.0, False), ("2026-10-04   rev A", 1.0, False)],
            [("ECP5+ADC+DAC", 1.5, True), ("by Jason Gallicchio and Claude", 0.8, False), ("github.com/gallicchio  2026-10-04  rev A", 0.8, False)],
            [("ECP5+ADC+DAC  rev A  2026-10-04", 1.0, True), ("Jason Gallicchio and Claude", 0.8, False)]])
        self._title("B.Cu", [
            [("ECP5+ADC+DAC   rev A   2026-10-04", 3.0, True), ("by Jason Gallicchio and Claude", 2.0, False), ("https://github.com/gallicchio", 2.0, False)],
            [("ECP5+ADC+DAC   rev A   2026-10-04", 2.0, True), ("by Jason Gallicchio and Claude", 1.2, False), ("https://github.com/gallicchio", 1.2, False)],
            [("ECP5+ADC+DAC  rev A  2026-10-04  Jason Gallicchio and Claude  github.com/gallicchio", 1.0, True)]])
        # ---- the SMAs: name and limit, large, in the strip under each body (kept free of parts); the detail beside
        smas = [("J301", ("CLK", "IN"), "3.3V MAX", "10 MHz ref. or any clock -> FPGA PLL; 50 Ω: JP3001"),
                ("J302", ("CLK", "OUT"), "3V3 CMOS", "any FPGA clock out, 50 Ω series"),
                ("J101", ("ADC A", "IN"), "±1V MAX", "50 Ω or hi-Z (JP101), DC; gain x1/x10: JP103, JP104"),
                ("J102", ("ADC B", "IN"), "±1V MAX", "50 Ω or hi-Z (JP201), DC; gain x1/x10: JP203, JP204"),
                ("J205", ("DAC 2", "OUT"), "±1V MAX", ""),                                          # (its strip's bottom row holds the LED jumper's choices)
                ("J204", ("DAC 1", "OUT"), "±1V MAX", "into 50 Ω, DC coupled")]
        for ref, nm, warn, detail in smas:
            x, y = at(ref)
            lines = [(nm[0], 1.2, True), (nm[1], 1.2, True), (warn, 0.75, True)]      # 7 mm wide at most: the strip ends at the section box
            w = max(SK.text_w(t_, sz, b) for t_, sz, b in lines)
            h = sum(SK.text_h(sz) for t_, sz, b in lines) + 0.6
            self._put("F.Cu", lines, (1.4 + w / 2.0, y + 4.85 + h / 2.0), maxd=1.0, rot=0, tag=ref)
        for ref, nm, warn, detail in smas:      # after every name, so a detail never takes a neighbour's strip
            x, y = at(ref)
            if not detail:
                continue
            self._put("F.Cu", [(detail, 0.7, False)], (19.0 + SK.text_w(detail, 0.7) / 2.0, y + 7.3), maxd=3.0, must=False, tag=ref + " limit", ref=ref)
        # ---- the right-edge connectors: a big name beside each body.  The two USB-Cs get two lines each, between
        # the jacks and under the second one: which is the programmer and which is the FPGA's own port
        for ref, lines, xy, rot, layer in (("J401", [("ETHERNET", 2.0, True)], (132.0 + E, 5.8), 0, "F.Cu"),
                                           ("J501", [("USB", 0.9, True), ("PROG", 0.9, True)], (138.4 + E, 34.5), 90, "F.Cu"),
                                           ("J502", [("USB", 0.9, True), ("FPGA", 0.9, True)], (138.4 + E, 48.0), 90, "F.Cu"),
                                           ("J504", [("microSD", 1.5, True)], at("J504") if "J504" in placed else (0, 0), None, "B.Cu"),
                                           ("J304", [("PMOD B", 1.5, True)], (126.0 + E, 80.0), 90, "F.Cu"),
                                           ("J303", [("PMOD A", 1.5, True)], (126.0 + E, 103.0), 90, "F.Cu")):
            if ref in placed:
                self._put(layer, lines, xy, maxd=6.0, rot_ok=True, rot=rot, tag=ref)
        if "J504" in placed:
            x, y = at("J504")
            self._put("B.Cu", [("card slides in here", 0.8, False)], (x + 14.0, y), maxd=6.0, rot_ok=True, tag="J504 card")
        for ref, lines, dx, dy in (("J601", [("5 V IN", 1.0, True), ("bench supply", 0.7, False)], 1.0, -5.0),
                                   ("J305", [("JTAG (FTDI A)", 0.8, True)], 0.0, -4.0),
                                   ("J105", [("NOISE R", 0.8, True)], 4.5, 0.0),
                                   ("J106", [("PD EXT", 0.8, True)], 0.0, -4.5),
                                   ("D201", [("LED", 1.0, True)], 0.0, -4.0),
                                   ("J210", [("LED EXT", 0.8, True)], 0.0, -4.5),
                                   ("SW301", [("RESET", 0.8, True)], 0.0, -3.2),
                                   ("SW302", [("USER", 0.8, True)], 0.0, -3.2),
                                   ("SW303", [("PROG", 0.8, True)], 0.0, -3.0)):
            if ref in placed:
                self._put("F.Cu", lines, at(ref, dx, dy), maxd=8.0, rot_ok=True, tag=ref, ref=ref)
        # the noise source's four resistors: their values over them (the DIP switch below puts each one in)
        for ref in ("R1401", "R1402", "R1403", "R1404"):
            if ref in placed:
                self._put("F.Cu", [(self.vals.get(ref, ""), 0.7, False)], at(ref, 0.0, -1.5), maxd=2.0, tag=ref + " value", ref=ref)
        # ---- the chips worth knowing by name, next to them
        for ref, lines, dx, dy in (("U103", [("DUAL ADC", 1.1, True), ("AD9238", 1.0, True), ("12 bit, 65 MS/s", 0.7, False)], 0.0, -13.0),
                                   ("U201", [("DUAL DAC", 1.1, True), ("AD9767", 1.0, True), ("14 bit, 125 MS/s", 0.7, False)], 7.5, 2.5),
                                   ("U1", [("ECP5", 1.1, True), ("LFE5U-25F", 1.0, True)], -13.0, 0.0),
                                   ("U502", [("FT2232H", 1.0, True), ("JTAG + UART", 0.8, False)], 0.0, 11.5),
                                   ("U401", [("RTL8211F PHY", 0.9, True)], -11.0, 0.0),
                                   ("U301", [("Si5351A", 0.9, True)], 0.0, -4.5)):
            if ref in placed:
                self._put("F.Cu", lines, at(ref, dx, dy), maxd=9.0, rot_ok=(ref not in ("U103", "U201")), tag=ref + " name", ref=ref)
        if "T401" in placed:
            self._put("B.Cu", [("G2406S magnetics", 0.9, True)], at("T401", 0.0, 9.0), maxd=8.0, rot_ok=True, tag="T401 name")
        # ---- every clock, with its frequency: the TCXO is the FPGA's clock, the Si5351's crystal, the PHY's, the FTDI's
        for ref, lines, dx, dy in (("X301", [("FPGA CLOCK", 0.9, True), ("25 MHz TCXO", 0.8, False), ("±2.5 ppm", 0.7, False)], 0.0, -5.5),
                                   ("Y301", [("25 MHz", 0.7, False)], 0.0, -3.0),
                                   ("Y401", [("PHY 25 MHz", 0.7, True)], 0.0, 3.6),
                                   ("Y501", [("FTDI 12 MHz", 0.7, True)], 0.0, 2.8)):
            if ref in placed:
                self._put("F.Cu", lines, at(ref, dx, dy), maxd=6.0, rot_ok=True, tag=ref + " clock", ref=ref)
        # ---- pin names beside the hand-use headers, checked against the netlist (tools/trace_paths.py once found three reversed)
        for ref, names in (("J305", ["3V3", "TCK", "TMS", "TDI", "TDO", "GND"]), ("J601", ["GND", "+5V"]),
                           ("J105", ["GND", "R"]), ("J106", ["A -4.4V", "K"]), ("J210", ["A +5V", "K"])):
            allp = [p for k, p in self.pads.items() if k[0] == ref]
            vertical = len({round(p["x"], 1) for p in allp}) == 1
            for i, nm in enumerate(names):
                pads = [p for k, p in self.pads.items() if k[0] == ref and k[1] == str(i + 1)]
                if pads:
                    prefer = (pads[0]["x"] + 2.2 + SK.text_w(nm, 0.7) / 2.0, pads[0]["y"]) if vertical else (pads[0]["x"], pads[0]["y"] - 2.6)   # past the header's courtyard
                    self._put("F.Cu", [(nm, 0.7, False)], prefer, maxd=4.0, rot_ok=not vertical, tag="%s.%d" % (ref, i + 1), ref=ref)
        # the rails header: the rail's name standing over each pin of the bottom row (short forms: 3V3A/3V3D are the
        # ADC's and DAC's 3.3 V), the title under the header says the whole top row is ground
        if "J602" in placed:
            pads = {k[1]: p for k, p in self.pads.items() if k[0] == "J602"}
            short = {"+3V3_ADC": "3V3A", "+3V3_DAC": "3V3D"}
            for i in range(1, 17, 2):
                p = pads.get(str(i))
                if p:
                    nm = short.get(p["net"], p["net"])
                    w = SK.text_w(nm, 0.7)
                    top = min(q["y"] for q in pads.values())
                    self._put("F.Cu", [(nm, 0.7, False)], (p["x"], top - 1.65 - w / 2.0), maxd=1.0, rot=90, tag="J602.%d" % i)
            p1, p16 = pads.get("1"), pads.get("16")
            if p1 and p16:
                self._put("F.Cu", [("RAILS: top row = GND", 0.7, True)],
                          ((p1["x"] + p16["x"]) / 2.0, max(p1["y"], p16["y"]) + 2.8), maxd=3.0, rot=0, tag="J602 title", ref="J602")
        for i in range(1, 10):
            ref = "TP%d" % i
            if ref in placed:
                self._put("F.Cu", [(self.vals.get(ref, ""), 0.7, False)], at(ref, 0.0, -2.6), maxd=4.0, rot_ok=True, tag=ref)
        for i in range(8):
            ref = "D30%d" % (i + 1)
            if ref in placed:
                self._put("F.Cu", [("LED%d" % i, 0.7, False)], at(ref, 0.0, -2.7), maxd=1.5, rot=0, tag=ref + " name", ref=ref)
        # ---- a printed mark on every part whose footprint prints none and could go in backwards
        self._pin1_marks()
        # ---- the jumpers: what a shunt does (2 pins); the two choices either side of a line through the centre pin (3 pins)
        self._jumper_labels()
        # ---- a legend in the largest empty areas: what the jumpers and headers mean (front), the whole story (back)
        self._legend()

    def _pin1_marks(self):
        """The LCSC land patterns (easyeda:*, ours:VBPW34S) print no silkscreen at all: no outline, no pin 1, no
        cathode -- everything they draw is on F.Fab, which is not printed.  A part can then be fitted a half turn
        out with nothing on the board to say so (the GPSDO board nearly lost an oscillator that way).  So: a
        0.6 mm dot beside pad 1 of every placed part that prints no silkscreen and whose pad pattern maps onto
        itself under a half turn (the magnetics, the RGB LED), and a bar beside the cathode of a polarised two-pad
        part that prints none (the 2835 LED, the photodiode).  Keyed connectors, two-terminal passives and parts
        whose pads fix the rotation get nothing.  The marks sit just outside the courtyard, on the part's own side."""
        import re
        KEYED = ("USB_C", "TF-SMD", "HDMI", "PinHeader", "PinSocket", "RJ45", "SMA_", "DSWB", "MountingHole", "TestPoint")
        n = 0
        for ref, (x, y, rot, layer) in sorted(self.pl.placed.items()):
            fp = self.pl.fp[ref]
            pads = fp["pads"]
            name = fp["name"]
            if len(pads) < 2 or any(k in name for k in KEYED) or ref.startswith(("H", "TP")):
                continue
            if not fp["id"].startswith(("easyeda:", "ours:")):
                continue                                                   # KiCad's own footprints print their pin-1 conventions (a longer line, a chamfer, a circle)
            from sexp import kids as _kids, kid as _kid, val as _val
            silk = [(kind, g) for kind in ("fp_line", "fp_poly", "fp_circle", "fp_arc", "fp_rect") for g in _kids(fp["node"], kind)
                    if _kid(g, "layer") is not None and str(_val(_kid(g, "layer"), 1)).endswith("SilkS")]
            polarised = len(pads) == 2 and ref.startswith("D")
            if len(pads) == 2 and not polarised:
                continue                                                   # a resistor has no wrong way round
            marked = any(kind in ("fp_poly", "fp_circle") and (kind != "fp_circle" or True) for kind, g in silk)
            # (the magnetics print a 0.3 mm circle at pin 1, the 2835 LED a triangle at its cathode; the photodiode draws
            #  the diode symbol itself in eight lines; the RGB LED prints two bare lines and nothing else)
            if marked or (polarised and sum(1 for kind, g in silk if kind == "fp_line") >= 6):
                continue
            if not polarised:
                tol = 0.06
                if not all(any(abs(-p["x"] - q["x"]) < tol and abs(-p["y"] - q["y"]) < tol for q in pads) for p in pads):
                    continue                                               # the pad pattern itself fixes the rotation
            p1 = next((p for p in pads if p["num"] in ("1", "A1")), None)
            if p1 is None:
                continue
            back = layer == "B.Cu"
            # pad 1 and the courtyard in board coordinates
            lx, ly = (-p1["x"] if back else p1["x"]), p1["y"]
            a = math.radians(rot)
            px, py = x + lx * math.cos(a) + ly * math.sin(a), y - lx * math.sin(a) + ly * math.cos(a)
            bx0, by0, bx1, by1 = fplib.box_at(fp, x, y, rot, back=back, grow=0.0)
            vx, vy = px - x, py - y
            d = math.hypot(vx, vy) or 1.0
            ux, uy = vx / d, vy / d
            # walk out along the centre-to-pad-1 direction until clear of the courtyard, then a little more
            mx, my = px, py
            for _ in range(200):
                if not (bx0 <= mx <= bx1 and by0 <= my <= by1):
                    break
                mx += ux * 0.05; my += uy * 0.05
            mx += ux * 0.55; my += uy * 0.55
            lname = "B.SilkS" if back else "F.SilkS"
            if polarised:
                # a bar across the pad axis beside the cathode (pad 1 of Device:LED / D_Photo)
                nx, ny = -uy, ux
                self.lines.append(B.line(mx - nx * 0.6, my - ny * 0.6, mx + nx * 0.6, my + ny * 0.6, lname, 0.25))
                self.occ[layer].claim(min(mx - 0.6, mx + 0.6) - 0.2, min(my - 0.6, my + 0.6) - 0.2, max(mx - 0.6, mx + 0.6) + 0.2, max(my - 0.6, my + 0.6) + 0.2)
            else:
                self.lines.append(B.line(mx - 0.01, my, mx + 0.01, my, lname, 0.6))      # a 0.6 mm dot
                self.occ[layer].claim(mx - 0.5, my - 0.5, mx + 0.5, my + 0.5)
            n += 1
            self.report.setdefault("pin1_marks", []).append("%s %s (%.1f, %.1f) %s" % (ref, "cathode bar" if polarised else "pin-1 dot", mx, my, lname))
        print("  pin-1 / cathode marks printed for %d parts whose footprints print none" % n)

    def _legend(self):
        front = [("JUMPERS   TERM: shunt = 50 Ω input      GAIN: shunt = x1, open = x10      SRC: SMA | NOISE      ALT: PD | NOISE      LED: LED | EXT", 0.75, False),
                 ("HEADERS   RAILS: top row = GND, 3V3A/3V3D = the ADC's/DAC's 3.3 V      NOISE R: DIP switch ON puts the resistor in      PD EXT: anode at -4.4 V      LED EXT: anode at +5 V, cathode sinks", 0.75, False),
                 ("USB PROG: power (0.7 A: a USB-C or USB 3 port, or 5 V IN), programming and the UART (FT2232H).   USB FPGA: wired straight to the FPGA -- it does nothing until the gateware implements USB.", 0.75, False)]
        occ = self.occ["F.Cu"]
        for lines in (front, front[:2], [front[0]], [front[1]], [front[2]]):
            w = max(SK.text_w(t, sz, b) for t, sz, b in lines)
            h = sum(SK.text_h(sz) for t, sz, b in lines) + 0.3 * (len(lines) - 1)
            r = occ.largest()
            if r and r[2] - r[0] >= w + 1.0 and r[3] - r[1] >= h + 1.0:
                self._put("F.Cu", lines, ((r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0), maxd=4.0, tag="legend")
                if len(lines) == 3:
                    return
        back = [("ECP5 LFE5U-25F FPGA, 32 MB SDRAM, 16 MB flash, microSD.  AD9238 dual 12-bit ADC to 65 MS/s (±1 V, 50 Ω or hi-Z, gain x1/x10/x100).", 0.9, False),
                ("AD9767 dual 14-bit DAC to 125 MS/s (±1 V into 50 Ω); channel 2 also drives an LED.  Noise source, photodiode receiver, 25 MHz TCXO,", 0.9, False),
                ("Si5351 clock generator, CLK IN (10 MHz reference or external clock into the FPGA PLL), CLK OUT.  Gigabit Ethernet, two USB-C", 0.9, False),
                ("(PROG: power, programming, UART; FPGA: the FPGA's own USB), mini HDMI, two Pmods.  Power 5 V in by USB PROG or the 5 V IN header.", 0.9, False)]
        self._put("B.Cu", back, (P.BW / 2.0, P.BH / 2.0), maxd=60.0, must=False, tag="legend back")

    def _section_boxes(self):
        """A 0.15 mm outline on F.SilkS round every section of the floorplan (floorplan.SECTION): the
        polygon floorplan.SECTION_BOX gives, else the parts' bounding box grown 2.2 mm (room for their
        designators, which label_spots keeps inside).  The section's name sits IN the top edge, centred on
        the line, which is cut round it -- and so is any neighbouring box's edge that runs through the name
        (two strips 0.2 mm apart share the name between their lines; build 15 could not fit a name on a
        shared edge and floated it above the box, into the neighbour).  If no top edge has room the name
        stands in a vertical edge, else it sits inside the top-left corner.  An edge over a pad, or a box
        holding another section's part, is reported in route_report.json under silk_boxes."""
        import floorplan as FPL
        sec = getattr(self.pl, "section", {})
        groups = {}
        for ref, s_ in sec.items():
            if s_ and ref in self.pl.placed and self.pl.placed[ref][3] == "F.Cu":
                groups.setdefault(s_, []).append(ref)
        occ = self.occ["F.Cu"]
        notes = []
        pads_f = [(k, p) for k, p in self.pads.items() if p["th"] or p["layer"] == "F.Cu"]
        def edge_hits(x0, y0, x1, y1):
            hits = []
            for k, p in pads_f:
                hw, hh = max(p["w"], p["h"]) / 2.0 + 0.15, max(p["w"], p["h"]) / 2.0 + 0.15     # the line is 0.15 wide
                if abs(x0 - x1) < 1e-6:
                    if p["x"] - hw < x0 < p["x"] + hw and p["y"] + hh > min(y0, y1) and p["y"] - hh < max(y0, y1):
                        hits.append(k)
                else:
                    if p["y"] - hh < y0 < p["y"] + hh and p["x"] + hw > min(x0, x1) and p["x"] - hw < max(x0, x1):
                        hits.append(k)
            return hits
        def inside(poly, x, y):
            n = len(poly); c = False
            for i in range(n):
                (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
                if (ya > y) != (yb > y) and x < xa + (y - ya) * (xb - xa) / (yb - ya):
                    c = not c
            return c
        polys = {}
        for name in sorted(set(groups) | set(FPL.SECTION_BOX)):
            refs = groups.get(name, [])
            if name in FPL.SECTION_BOX:
                polys[name] = list(FPL.SECTION_BOX[name])
            elif refs:
                bb = [1e9, 1e9, -1e9, -1e9]
                for r in refs:
                    x, y, rot, lay = self.pl.placed[r]
                    x0, y0, x1, y1 = fplib.box_at(self.pl.fp[r], x, y, rot, grow=0.0)
                    bb = [min(bb[0], x0), min(bb[1], y0), max(bb[2], x1), max(bb[3], y1)]
                m = 2.2
                x0, y0, x1, y1 = max(bb[0] - m, 1.0), max(bb[1] - m, 1.0), min(bb[2] + m, P.BW - 1.0), min(bb[3] + m, P.BH - 1.0)
                polys[name] = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        self.section_polys = polys
        # ---- pass 1: a spot for every name (the lines are not in the way yet: they are cut round the names after)
        names = {}                      # name -> (x0, y0, x1, y1, text node)
        for name, poly in polys.items():
            edges = [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]
            for (a, b) in edges:
                hits = edge_hits(a[0], a[1], b[0], b[1])
                if hits:
                    notes.append("%s: an edge runs over %s" % (name, ", ".join(sorted({"%s/%s" % (k[0], k[1]) for k in hits})[:5])))
            foreign = sorted(r for r, (x, y, rot, lay) in self.pl.placed.items()
                             if lay == "F.Cu" and sec.get(r) != name and not r.startswith("H") and inside(poly, x, y))
            if foreign:
                notes.append("%s: contains %s" % (name, ", ".join(foreign[:8])))
            w, h = SK.text_w(name, 0.9, True), SK.text_h(0.9)
            ytop = min(y for x, y in poly)
            # the top edge's pieces only (a horizontal edge with the box's inside below it: a notched box has
            # several), west to east -- never the bottom edge, which is the next box's top edge
            horiz = [(a, b) for (a, b) in edges if abs(a[1] - b[1]) < 1e-6
                     and inside(poly, (a[0] + b[0]) / 2.0, a[1] + 0.3) and not inside(poly, (a[0] + b[0]) / 2.0, a[1] - 0.3)]
            horiz.sort(key=lambda e: min(e[0][0], e[1][0]))
            spot = None
            for (a, b) in horiz:
                ex0, ex1, ey = min(a[0], b[0]), max(a[0], b[0]), a[1]
                for lx in np.arange(ex0 + 0.8, ex1 - w - 0.8 + 1e-6, 0.25):
                    if occ.free(lx, ey - h / 2.0, lx + w, ey + h / 2.0):
                        spot = (lx, ey - h / 2.0, lx + w, ey + h / 2.0, B.text(lx, ey, name, "F.SilkS", 0.9, bold=True)); break
                if spot:
                    break
            if not spot:
                for (a, b) in [(a, b) for (a, b) in edges if abs(a[0] - b[0]) < 1e-6]:          # standing in a vertical edge, reading up
                    ey0, ey1, ex = min(a[1], b[1]), max(a[1], b[1]), a[0]
                    for ly in np.arange(ey1 - 0.8, ey0 + w + 0.8, -0.25):
                        if occ.free(ex - h / 2.0, ly - w, ex + h / 2.0, ly):
                            spot = (ex - h / 2.0, ly - w, ex + h / 2.0, ly, B.text(ex, ly, name, "F.SilkS", 0.9, bold=True, angle=90)); break
                    if spot:
                        break
            if not spot:                                                                       # inside the top-left corner
                xl = min(x for x, y in poly if abs(y - ytop) < 0.01)
                r_ = occ.spot(w, h, (xl + 0.8 + w / 2.0, ytop + 0.5 + h / 2.0), maxd=6.0, region=(xl, ytop, max(x for x, y in poly), max(y for x, y in poly)))
                if r_ is None:
                    r_ = (xl + 0.8, ytop + 0.5, 0)
                    self.report.setdefault("silk_unplaced", []).append("box " + name)
                x0, y0, _ = r_
                spot = (x0, y0, x0 + w, y0 + h, B.text(x0, y0 + h / 2.0, name, "F.SilkS", 0.9, bold=True))
            occ.claim(spot[0], spot[1], spot[2], spot[3])
            self.texts.append(spot[4])
            names[name] = spot[:4]
        # ---- pass 2: the lines, every edge cut where any name sits on it
        cuts = [(x0 - 0.5, y0 - 0.2, x1 + 0.5, y1 + 0.2) for (x0, y0, x1, y1) in names.values()]
        def clip(a, b):
            segs = [(0.0, 1.0)]
            for (cx0, cy0, cx1, cy1) in cuts:
                if abs(a[1] - b[1]) < 1e-6:                                                    # horizontal
                    if not (cy0 <= a[1] <= cy1):
                        continue
                    lo, hi = sorted(((cx0 - a[0]) / (b[0] - a[0]), (cx1 - a[0]) / (b[0] - a[0])))
                elif abs(a[0] - b[0]) < 1e-6:
                    if not (cx0 <= a[0] <= cx1):
                        continue
                    lo, hi = sorted(((cy0 - a[1]) / (b[1] - a[1]), (cy1 - a[1]) / (b[1] - a[1])))
                else:
                    continue
                out = []
                for (s0, s1) in segs:
                    if hi <= s0 or lo >= s1:
                        out.append((s0, s1))
                    else:
                        if lo > s0:
                            out.append((s0, lo))
                        if hi < s1:
                            out.append((hi, s1))
                segs = out
            return [(a[0] + (b[0] - a[0]) * s0, a[1] + (b[1] - a[1]) * s0, a[0] + (b[0] - a[0]) * s1, a[1] + (b[1] - a[1]) * s1) for (s0, s1) in segs]
        for name, poly in polys.items():
            edges = [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]
            for (a, b) in edges:
                for (x0, y0, x1, y1) in clip(a, b):
                    if abs(x0 - x1) > 0.3 or abs(y0 - y1) > 0.3:
                        self.lines.append(B.line(x0, y0, x1, y1, "F.SilkS", 0.15))
                        occ.claim(min(x0, x1) - 0.15, min(y0, y1) - 0.15, max(x0, x1) + 0.15, max(y0, y1) + 0.15, margin=0.0)
        if notes:
            self.report["silk_boxes"] = notes
            for n in notes:
                print("  silk box:", n)

    def _jumper_labels(self):
        """2-pin jumpers: what the shunt does, beside the pins.  3-pin jumpers: the two choices beside the
        two outer pins, on the free side of the row, with a line through the centre pin between them."""
        two = {"JP101": "50 Ω", "JP201": "50 Ω", "JP3001": "50 Ω", "JP103": "x1", "JP104": "x1", "JP203": "x1", "JP204": "x1"}   # shunt in = this
        three = {"JP102": ("NOISE", "SMA"), "JP202": ("ALT", "SMA"), "JP1203": ("PD", "NOISE"), "JP2009": ("LED", "EXT")}       # pin 1 side, pin 3 side
        occ = self.occ["F.Cu"]
        sz = 0.8                                                       # a size over the board's 0.7 mm minimum (3-pin choices)
        sz2 = 1.0                                                      # the 2-pin labels ("50 Ω", "x1") larger: they are read from across the bench
        pads_all = [p for k, p in self.pads.items() if p["th"] or p["layer"] == "F.Cu"]
        def line_clear(x0, y0, x1, y1, region=None):
            if region and not (region[0] <= min(x0, x1) and max(x0, x1) <= region[2] and region[1] <= min(y0, y1) and max(y0, y1) <= region[3]):
                return False
            if not occ.free(min(x0, x1) - 0.2, min(y0, y1) - 0.2, max(x0, x1) + 0.2, max(y0, y1) + 0.2):
                return False                                           # a text already there (the neighbour's choices)
            return not any(_pt_seg(p["x"], p["y"], x0, y0, x1, y1) < max(p["w"], p["h"]) / 2.0 + 0.35 for p in pads_all)
        for ref in sorted(set(two) | set(three)):
            if ref not in self.pl.placed:
                continue
            pads = {k[1]: p for k, p in self.pads.items() if k[0] == ref}
            if ref in two:
                p1, p2 = pads["1"], pads["2"]
                txt = two[ref]
                w, h = SK.text_w(txt, sz2, True), SK.text_h(sz2)
                ux, uy = p2["x"] - p1["x"], p2["y"] - p1["y"]
                L = math.hypot(ux, uy); ux, uy = ux / L, uy / L
                mx, my = (p1["x"] + p2["x"]) / 2.0, (p1["y"] + p2["y"]) / 2.0
                cands = []
                for d in (2.6, 3.3):
                    for s in (1.0, -1.0):
                        cands.append((mx - s * uy * d, my + s * ux * d, 0 if abs(ux) > abs(uy) else 90))     # beside the row
                for s in (1.0, -1.0):
                    along = (w if abs(ux) > abs(uy) else h) / 2.0
                    cands.append((mx + s * ux * (L / 2.0 + 1.9 + along), my + s * uy * (L / 2.0 + 1.9 + along), 0 if abs(ux) > abs(uy) else 90))   # off an end
                done = False
                region = self._region_of(ref)
                for (cx, cy, ang) in cands:
                    bw, bh = (w, h) if ang == 0 else (h, w)
                    if region and not (region[0] <= cx - bw / 2.0 and cx + bw / 2.0 <= region[2] and region[1] <= cy - bh / 2.0 and cy + bh / 2.0 <= region[3]):
                        continue
                    if occ.free(cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0):
                        occ.claim(cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0)
                        self.texts.append(B.text(cx, cy, txt, "F.SilkS", sz2, bold=True, just="center", angle=ang))
                        done = True; break
                if not done:
                    self._put("F.Cu", [(txt, sz2, True)], (mx, my - 3.0), maxd=5.0, rot_ok=True, tag=ref, ref=ref)
                continue
            p1, p2, p3 = pads["1"], pads["2"], pads["3"]
            ta, tb = three[ref]
            ux, uy = p3["x"] - p1["x"], p3["y"] - p1["y"]
            L = math.hypot(ux, uy); ux, uy = ux / L, uy / L
            ang = 0 if abs(ux) > abs(uy) else 90
            done = False
            # beside the row (both sides, two distances), else off its two ends (the line then marks the centre
            # pin on both sides of the header); the text shrinks to 0.5 before giving up
            region = self._region_of(ref)
            for size in (sz, 0.7):
                cands = []
                for d in (2.0, 2.4, 2.7, 3.0, 3.3):
                    for s in (1.0, -1.0):
                        nx, ny = -s * uy, s * ux
                        cands.append(("beside", nx, ny, d, [(p1["x"] + nx * d, p1["y"] + ny * d, ta), (p3["x"] + nx * d, p3["y"] + ny * d, tb)]))
                ends = []
                for off in (0.0, 1.0, -1.0):
                    wa, wb = SK.text_w(ta, size, True), SK.text_w(tb, size, True)
                    ea, eb = 1.9 + (wa if ang == 0 else SK.text_h(size)) / 2.0, 1.9 + (wb if ang == 0 else SK.text_h(size)) / 2.0
                    ends.append(("ends", -uy, ux, 0.0, [(p1["x"] - ux * ea - uy * off, p1["y"] - uy * ea + ux * off, ta),
                                                        (p3["x"] + ux * eb - uy * off, p3["y"] + uy * eb + ux * off, tb)]))
                cands = ends + cands if ref in ("JP1203",) else cands + ends
                for kind, nx, ny, d, items in cands:
                    boxes = []
                    for (cx, cy, txt) in items:
                        w, h = SK.text_w(txt, size, True), SK.text_h(size)
                        bw, bh = (w, h) if ang == 0 else (h, w)
                        boxes.append((cx, cy, bw, bh, txt))
                    inside = all(region is None or (region[0] <= cx - bw / 2.0 and cx + bw / 2.0 <= region[2] and region[1] <= cy - bh / 2.0 and cy + bh / 2.0 <= region[3]) for (cx, cy, bw, bh, txt) in boxes)
                    if inside and all(occ.free(cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0) for (cx, cy, bw, bh, txt) in boxes):
                        for (cx, cy, bw, bh, txt) in boxes:
                            occ.claim(cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0)
                            self.texts.append(B.text(cx, cy, txt, "F.SilkS", size, bold=True, just="center", angle=ang))
                        if kind == "beside":
                            seg = (p2["x"] + nx * 1.9, p2["y"] + ny * 1.9, p2["x"] + nx * (d + 0.5), p2["y"] + ny * (d + 0.5))   # from just past the header's outline
                            if line_clear(*seg, region=region):
                                self.lines.append(B.line(*seg, "F.SilkS", 0.15))
                        else:
                            for s in (1.0, -1.0):                      # the centre-pin mark on whichever side is clear of other pads
                                seg = (p2["x"] + s * nx * 1.9, p2["y"] + s * ny * 1.9, p2["x"] + s * nx * 2.9, p2["y"] + s * ny * 2.9)
                                if line_clear(*seg, region=region):
                                    self.lines.append(B.line(*seg, "F.SilkS", 0.15))
                        done = True; break
                if done:
                    break
            if not done:
                self.report.setdefault("silk_unplaced", []).append(ref + " choices")
                self._put("F.Cu", [("%s | %s" % (ta, tb), sz, True)], (p2["x"], p2["y"] - 3.0), maxd=6.0, rot_ok=True, tag=ref, ref=ref)

    # ---------------------------------------------------------------- designators
    def label_spots(self):
        """A spot for every designator (and the value of each IC/connector)
        that covers no part, no other label and no edge: around the part,
        nearest first.  Returns {ref: (local_x, local_y, local_angle)} for the
        reference and {ref: ...} for the value."""
        refs, vals = {}, {}
        big = lambda r: r[0] in "UJT" or r.startswith("SW") or r.startswith("X") or r.startswith("Y") or r.startswith("L")
        order = sorted(self.pl.placed.items(), key=lambda kv: -(self.pl.boxes[kv[0]][3] - self.pl.boxes[kv[0]][1]) * (self.pl.boxes[kv[0]][4] - self.pl.boxes[kv[0]][2]))
        for which in ("ref", "val"):
            for ref, (x, y, rot, layer) in order:
                if ref.startswith("H"):
                    continue
                if which == "val" and (not big(ref) or not self.vals.get(ref) or ref[0] == "J" or ref.startswith("SW")):
                    continue
                text = ref if which == "ref" else self.vals[ref]
                size = (0.8 if big(ref) else 0.7) if which == "ref" else 0.7
                occ = self.occ[layer]
                x0, y0, x1, y1 = fplib.box_at(self.pl.fp[ref], x, y, rot, back=(layer == "B.Cu"), grow=0.0)
                w, h = SK.text_w(text, size), SK.text_h(size)
                cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                cands = [(cx, y0 - 0.45 - h / 2), (cx, y1 + 0.45 + h / 2), (x0 - 0.45 - w / 2, cy), (x1 + 0.45 + w / 2, cy),
                         (x0 + w / 2, y0 - 0.45 - h / 2), (x1 - w / 2, y0 - 0.45 - h / 2), (x0 + w / 2, y1 + 0.45 + h / 2), (x1 - w / 2, y1 + 0.45 + h / 2),
                         (x0 - 0.45 - w / 2, y0 + h / 2), (x1 + 0.45 + w / 2, y0 + h / 2), (x0 - 0.45 - w / 2, y1 - h / 2), (x1 + 0.45 + w / 2, y1 - h / 2)]
                # a part of a section keeps its designator inside the section's box (the user reads a box as a unit)
                region = self._region_of(ref) if layer == "F.Cu" else None
                cands_all = cands
                if region:
                    cands = [(bx, by) for (bx, by) in cands if region[0] <= bx - w / 2 and bx + w / 2 <= region[2] and region[1] <= by - h / 2 and by + h / 2 <= region[3]]
                hit = None
                for (bx, by) in cands:
                    if occ.free(bx - w / 2, by - h / 2, bx + w / 2, by + h / 2):
                        hit = (bx, by, 0); break
                if hit is None and region:
                    sp = occ.spot(w, h, (cx, cy), maxd=6.0 if big(ref) else 4.0, rot_ok=True, region=(region[0] + w / 2, region[1] + h / 2, region[2] - w / 2, region[3] - h / 2))
                    if sp is not None:
                        hit = (sp[0] + w / 2, sp[1] + h / 2, 0) if sp[2] == 0 else (sp[0] + h / 2, sp[1] + w / 2, 90)
                    else:
                        self.report.setdefault("silk_outside_box", []).append(text)
                if hit is None:
                    sp = occ.spot(w, h, (cx, cy), maxd=6.0 if big(ref) else 4.0, rot_ok=True)
                    if sp is not None:
                        if sp[2] == 0:
                            hit = (sp[0] + w / 2, sp[1] + h / 2, 0)
                        else:
                            hit = (sp[0] + h / 2, sp[1] + w / 2, 90)
                if hit is None and which == "ref" and big(ref) and ref[0] == "U":
                    # under the body of a leaded package: visible until the chip is fitted, on no pad
                    pads = [q for k, q in self.pads.items() if k[0] == ref]
                    px0, py0, px1, py1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
                    if all(q["x"] + q["w"] / 2 + 0.2 < px0 or q["x"] - q["w"] / 2 - 0.2 > px1 or q["y"] + q["h"] / 2 + 0.2 < py0 or q["y"] - q["h"] / 2 - 0.2 > py1 for q in pads) and (px1 - px0) < (x1 - x0):
                        hit = (cx, cy, 0)
                fits = hit is not None
                if hit is None:
                    self.report.setdefault("silk_unplaced", []).append(text)
                    hit = cands_all[0] + (0,)
                bx, by, ang = hit
                if fits:
                    if ang == 0:
                        occ.claim(bx - w / 2, by - h / 2, bx + w / 2, by + h / 2)
                    else:
                        occ.claim(bx - h / 2, by - w / 2, bx + h / 2, by + w / 2)
                # back to the footprint's own frame (KiCad rotates the field with the part).  A back-side
                # footprint's file coordinates are already the board's (x is NOT negated again): checked
                # against pcbnew's own field positions, front and back, 0/90/180
                dx, dy = bx - x, by - y
                lx, ly = fplib._rot(dx, dy, -rot)
                la = ang % 360
                (refs if which == "ref" else vals)[ref] = (lx, ly, la, fits)
        return refs, vals

    # ---------------------------------------------------------------- write
    def write(self):
        B.BOARD = (P.BW, P.BH)
        out = [B.arc_rect(0, 0, P.BW, P.BH, 2.0, "Edge.Cuts", 0.1)]
        refs, vals = self.label_spots()
        for ref, (x, y, rot, layer) in self.pl.placed.items():
            fp = self.pl.fp[ref]
            x0, y0, x1, y1 = fp["crtyd"]
            r = refs.get(ref, (0, y0 - 0.6, 0, True))
            v = vals.get(ref, (0, y1 + 1.0, 0, False))
            out.append(B.footprint(fp, ref, self.vals.get(ref, ""), x, y, rot, layer, self.nets.get(ref, {}), self.numof,
                                   ref_at=r[:3], val_at=v[:3], ref_size=0.8 if (ref[0] in "UJT" or ref[:2] in ("SW", "TP")) else 0.7, val_size=0.7,
                                   ref_layer="F.SilkS" if (r[3] and not ref.startswith("H")) else "F.Fab", val_layer="F.SilkS" if v[3] else "F.Fab",
                                   hide_value=ref.startswith("H"), lcsc=self.lcsc.get(ref)))
        for (lname, x0, y0, x1, y1, net, w) in self.tracks:
            if abs(x1 - x0) < 1e-6 and abs(y1 - y0) < 1e-6:
                continue
            out.append(B.track(x0, y0, x1, y1, lname, self.numof[net], w))
        for (vx, vy, net, size, drill) in self.vias:
            out.append(B.via(vx, vy, self.numof[net], size, drill))
        # ground planes, both inner reference layers, and the islands under the core
        edge = 0.5
        poly = [(edge, edge), (P.BW - edge, edge), (P.BW - edge, P.BH - edge), (edge, P.BH - edge)]
        out.append(B.zone(self.numof["GND"], "GND", ["In1.Cu"], poly, "GND plane In1", priority=0, clearance=0.2, min_w=0.2))
        out.append(B.zone(self.numof["GND"], "GND", ["In4.Cu"], poly, "GND plane In4", priority=0, clearance=0.2, min_w=0.2))
        for i, (net, zpoly, pri) in enumerate(RAIL_ZONES):
            if net in self.numof:
                out.append(B.zone(self.numof[net], net, ["In4.Cu"], zpoly, "%s plane %d" % (net, i), priority=pri, clearance=0.2, min_w=0.2))
        for net, (lname, ipoly) in self.esc["islands"].items():
            out.append(B.zone(self.numof[net], net, [lname], ipoly, "%s core island" % net, priority=1, clearance=0.15, min_w=0.15, thermal=False))
        # the rule areas the .kicad_dru refers to
        fx, fy = self.fpga_xy
        out.append(B.rule_area("BGA_FANOUT", B.COPPER, [(fx - 8.5, fy - 8.5), (fx + 8.5, fy - 8.5), (fx + 8.5, fy + 8.5), (fx - 8.5, fy + 8.5)]))
        # the Ethernet line side: from the magnetics' line-side pads to the board edge, the jack and the Bob Smith
        # network.  No plane enters it (the ground planes stopped 0.2 mm from the line side in builds 1-16: the
        # area allowed copper pour), and gen/rules.py keeps every other net 1.5 mm from the LAN nets inside it
        jx, jy, _, _ = self.pl.placed["J401"]
        tx, ty, _, _ = self.pl.placed["T401"]
        out.append(B.rule_area("LAN_ISLAND", B.COPPER, [(tx - 0.7, 3.0), (P.BW, 3.0), (P.BW, ty + 10.0), (tx - 0.7, ty + 10.0)], no_pour=True))
        out += self.texts
        out += getattr(self, "lines", [])
        txt = B.document("\n".join(out), self.numof)
        open(PCB, "w", encoding="utf-8").write(txt)
        rf_bad = sorted({(t[5], t[6]) for t in self.tracks if t[5] in self.rf and abs(t[6] - RF_W) > 1e-6})
        self.report["rf_width_violations"] = ["%s at %.3f mm" % b for b in rf_bad]
        json.dump(self.report, open(os.path.join(ROOT, "build", "route_report.json"), "w"), indent=1)
        if rf_bad:
            raise SystemExit("FAILED: SMA feed tracks not at RF_W %.2f mm: %s" % (RF_W, self.report["rf_width_violations"]))
        json.dump({r: list(v) for r, v in self.pl.placed.items()}, open(os.path.join(ROOT, "build", "placement.json"), "w"), indent=0, sort_keys=True)


def main():
    t0 = time.time()
    b = Build()
    b.place()
    b.bga()
    if "--place" not in sys.argv:
        b.grid()
        b.hand()
        b.rivers()
        b.ground_vias()
        b.rail_vias()
        b.route_all(budget_s=float(os.environ.get("ROUTE_BUDGET", "1500")))
        b.return_vias()
        b.pad_stubs()
        b.prune()
    b.silk()
    b.write()
    print("wrote %s in %.0f s" % (PCB, time.time() - t0))


if __name__ == "__main__":
    main()
