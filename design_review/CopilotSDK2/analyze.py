#!/usr/bin/env python3
"""Build-31 review measurements. Read-only. Writes next to itself."""
import os, sys, math, collections, json
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))   # (the author, 2026-10-07: was an absolute path; the repository keeps none)
sys.path.insert(0, os.path.join(ROOT, "gen"))
from sexp import parse, kids, kid, head, val

OUT = os.path.dirname(os.path.abspath(__file__))
OX = OY = 25.0

def atom(n):
    return n[1] if isinstance(n, tuple) else n

def load(path):
    return parse(open(path).read())[0]

# ---------- netlist ----------
nl = load(os.path.join(ROOT, "build/netlist.net"))
comps = {}
for c in kids(kid(nl, "components"), "comp"):
    ref = val(kid(c, "ref"), 1)
    fields = {}
    for f in kids(kid(c, "fields") or [], "field"):
        nm = kid(f, "name")
        key = val(nm, 1) if nm else "?"
        fields[key] = val(f, 2) if len(f) > 2 else ""
    comps[ref] = {
        "value": val(kid(c, "value"), 1) if kid(c, "value") else "",
        "fp": val(kid(c, "footprint"), 1) if kid(c, "footprint") else "",
        "lib": val(kid(c, "libsource"), 2) if kid(c, "libsource") and len(kid(c, "libsource")) > 2 else "",
        "fields": fields,
    }
nets = {}
for n in kids(kid(nl, "nets"), "net"):
    name = val(kid(n, "name"), 1)
    nodes = [(val(kid(nd, "ref"), 1), val(kid(nd, "pin"), 1)) for nd in kids(n, "node")]
    nets[name] = nodes

lines = []
def P(s=""):
    lines.append(s)

P("# Netlist gates")
P(f"components {len(comps)} nets {len(nets)}")
one = []
for name, nodes in sorted(nets.items()):
    if len(nodes) <= 1 and not name.startswith("unconnected") and "no_connect" not in name.lower():
        one.append((name, nodes))
P(f"one-pin nets (excluding unconnected): {len(one)}")
for name, nodes in one:
    P(f"  {name}: {nodes}")

# power-like names
pwr = [n for n in nets if n.startswith(("+", "-")) or n in ("GND", "VBUS", "VCC")]
P("\n## power nets")
for n in sorted(pwr, key=lambda x: (-len(nets[x]), x)):
    refs = sorted({r for r, p in nets[n]})
    P(f"  {n}: {len(nets[n])} pins, {len(refs)} parts")

def pins_of(ref):
    out = {}
    for name, nodes in nets.items():
        for r, p in nodes:
            if r == ref:
                out.setdefault(p, []).append(name)
    return out

P("\n## critical pin maps")
for ref in ["U302", "U604", "U605", "U606", "D601", "F601", "F602", "J601", "J305", "U401",
            "D110", "D111", "D101", "D102", "U111", "U112", "Y501", "U502"]:
    if ref not in comps:
        P(f"  {ref} MISSING")
        continue
    pm = pins_of(ref)
    P(f"  {ref} {comps[ref]['value']} {comps[ref]['fp']}")
    for p in sorted(pm, key=lambda x: (len(x), x)):
        P(f"    pin {p}: {pm[p]}")

# design equation parts by value clusters
P("\n## values of interest")
want = {}
for ref, c in comps.items():
    v = c["value"]
    if v in ("2.2k", "2k", "499R", "24.9R", "49.9R", "9.1k", "1k", "100R", "33R", "22R", "27R",
             "5.1k", "4.7k", "15k", "3.3k", "12k", "10k", "1.2M", "499k", "75R", "2.49k",
             "10nF", "22pF", "2.2pF", "27pF", "18pF", "1nF", "100nF", "10uF", "22uF"):
        want.setdefault(v, []).append(ref)
for v, refs in sorted(want.items()):
    P(f"  {v}: {len(refs)}  {','.join(sorted(refs)[:40])}")

# polarized-ish
P("\n## polarized / diode / electrolytic candidates")
for ref, c in sorted(comps.items()):
    fp = c["fp"]
    value = c["value"]
    if ref[0] in "DQU" or "LED" in fp or "Schottky" in c["lib"] or "Polar" in fp or "CP_" in fp or "C_Elec" in fp:
        if ref[0] in "DQU" or "LED" in fp or "Elec" in fp or "Polar" in fp:
            P(f"  {ref} {value} {fp} {c['lib']}")

# DNP
P("\n## DNP / do-not-fit fields")
for ref, c in comps.items():
    blob = json.dumps(c["fields"]) + c["value"]
    if "DNP" in blob or "dnp" in blob or "do not" in blob.lower():
        P(f"  {ref} {c['value']} {c['fields']}")

open(os.path.join(OUT, "netlist_gates.txt"), "w").write("\n".join(lines) + "\n")
print("netlist written", len(lines))

# ---------- PCB ----------
print("parsing pcb...")
pcb = load(os.path.join(ROOT, "ECP5-2ADC-2DAC.kicad_pcb"))
NAMES = {}
for node in pcb:
    if isinstance(node, list) and head(node) == "net" and len(node) > 2:
        NAMES[int(atom(node[1]))] = atom(node[2])

def netname(nt):
    if not nt or len(nt) < 2:
        return ""
    if len(nt) > 2:
        return atom(nt[2])
    v = atom(nt[1])
    return NAMES.get(int(v), str(v)) if str(v).lstrip("-").isdigit() else str(v)

segs = []  # layer, x0, y0, x1, y1, net, w
vias = []
zones = []  # net, layer, pts
fps = []
texts = []
for node in pcb:
    if not isinstance(node, list):
        continue
    h = head(node)
    if h == "segment":
        s_, e_ = kid(node, "start"), kid(node, "end")
        segs.append((atom(kid(node, "layer")[1]),
                     float(atom(s_[1])) - OX, float(atom(s_[2])) - OY,
                     float(atom(e_[1])) - OX, float(atom(e_[2])) - OY,
                     netname(kid(node, "net")), float(atom(kid(node, "width")[1]))))
    elif h == "via":
        a = kid(node, "at")
        vias.append((float(atom(a[1])) - OX, float(atom(a[2])) - OY, netname(kid(node, "net")),
                     float(atom(kid(node, "size")[1])), float(atom(kid(node, "drill")[1]))))
    elif h == "zone":
        nt = kid(node, "net")
        if not nt:
            continue
        lay = atom(kid(node, "layer")[1])
        filled = kids(node, "filled_polygon")
        polys = []
        for fp_ in filled:
            pts = [(float(atom(q[1])) - OX, float(atom(q[2])) - OY) for q in kids(kid(fp_, "pts"), "xy")]
            if len(pts) >= 3:
                polys.append(pts)
        if not polys:
            pol = kid(node, "polygon")
            if pol:
                pts = [(float(atom(q[1])) - OX, float(atom(q[2])) - OY) for q in kids(kid(pol, "pts"), "xy")]
                if len(pts) >= 3:
                    polys.append(pts)
        zones.append((netname(nt), lay, polys))
    elif h == "footprint":
        a = kid(node, "at")
        props = {atom(p[1]): atom(p[2]) for p in kids(node, "property") if len(p) > 2}
        fps.append({
            "ref": props.get("Reference", "?"),
            "value": props.get("Value", ""),
            "x": float(atom(a[1])) - OX,
            "y": float(atom(a[2])) - OY,
            "rot": float(atom(a[3])) if len(a) > 3 else 0.0,
            "layer": atom(kid(node, "layer")[1]),
            "fp": atom(node[1]) if len(node) > 1 else "",
        })
    elif h == "gr_text":
        a = kid(node, "at")
        texts.append((atom(kid(node, "layer")[1]) if kid(node, "layer") else "?",
                      val(node, 1) if len(node) > 1 else "",
                      float(atom(a[1])) - OX if a else 0,
                      float(atom(a[2])) - OY if a else 0))

print(f"segs {len(segs)} vias {len(vias)} zones {len(zones)} fps {len(fps)} texts {len(texts)}")

# In1 tracks
in1 = [s for s in segs if s[0] == "In1.Cu"]
P2 = []
def Q(s=""):
    P2.append(s)
Q(f"In1.Cu segments: {len(in1)}")
for s in in1[:20]:
    Q(f"  {s}")

# via drills
drills = collections.Counter(round(v[4], 3) for v in vias)
Q(f"via drills: {dict(drills)}")
Q(f"via sizes: {dict(collections.Counter(round(v[3], 3) for v in vias))}")

# SMA / RF widths
rf_nets = [n for n in {s[5] for s in segs} if any(k in n for k in ("ADC_A", "ADC_B", "DAC_1", "DAC_2", "CLK", "SMA", "J100", "J200"))]
# better: known feed nets from names
interesting = [n for n in {s[5] for s in segs} if n and any(k in n for k in
    ("/ADC/J", "ADC_A_IN", "SMA", "CLK_EXT", "CLK_OUT", "TAP", "MDI", "USB_DP", "USB_DM", "HDMI"))]
Q("\n## track width histogram for nets containing SMA/CLK/MDI/USB/HDMI/J1")
name_set = {s[5] for s in segs}
cands = sorted(n for n in name_set if any(k in n.upper() for k in ("SMA", "CLK_EXT", "CLK_OUT", "MDI", "USB", "HDMI", "TD_", "RD_", "DP", "DM")))
# also print nets with a 0.35 segment
w35 = collections.defaultdict(float)
for L, x0, y0, x1, y1, n, w in segs:
    if abs(w - 0.35) < 0.01 or abs(w - 0.30) < 0.01:
        w35[n] += math.hypot(x1 - x0, y1 - y0)
Q("nets with 0.30 or 0.35 mm copper (mm):")
for n, L in sorted(w35.items(), key=lambda kv: -kv[1])[:40]:
    Q(f"  {L:.1f} mm  {n}")

# copper area by layer and quadrant
def poly_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0

def centroid(pts):
    a = poly_area(pts)
    if a < 1e-6:
        return pts[0]
    cx = cy = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return cx / (6 * (1 if poly_area(pts) else 1)), cy / (6 * a) if False else (cx / (6 * (poly_area(pts) or 1)), cy / (6 * (poly_area(pts) or 1)))

BW, BH = 158.0, 119.0
layers = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
quads = {
    "NW": (0, 0, BW / 2, BH / 2),
    "NE": (BW / 2, 0, BW, BH / 2),
    "SW": (0, BH / 2, BW / 2, BH),
    "SE": (BW / 2, BH / 2, BW, BH),
}
# area by layer from filled polygons (islands included; holes are separate polygons with negative? KiCad filled_polygon is the copper, holes already subtracted as separate polygons? 
# KiCad stores filled polygons as the copper regions, holes excluded. Sum is copper area. Good.
layer_area = collections.Counter()
quad_area = collections.Counter()
zone_summary = collections.Counter()
for net, lay, polys in zones:
    for pts in polys:
        ar = poly_area(pts)
        layer_area[lay] += ar
        zone_summary[(net, lay)] += ar
        # quadrant by centroid
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        for qn, (x0, y0, x1, y1) in quads.items():
            if x0 <= cx < x1 and y0 <= cy < y1:
                quad_area[(lay, qn)] += ar
                break
board_area = BW * BH
Q("\n## copper fraction from filled zone polygons (tracks extra, small)")
for lay in layers:
    Q(f"  {lay}: {layer_area[lay]:.0f} mm2  {100 * layer_area[lay] / board_area:.1f}% of board")
Q("by quadrant (zone copper only):")
for lay in layers:
    bits = []
    for qn in ("NW", "NE", "SW", "SE"):
        bits.append(f"{qn} {100 * quad_area[(lay, qn)] / (board_area / 4):.0f}%")
    Q(f"  {lay}: {', '.join(bits)}")
Q("In4 zone areas mm2:")
for (net, lay), ar in sorted(zone_summary.items()):
    if lay == "In4.Cu":
        Q(f"  {net}: {ar:.1f}")

# seam crossings: segment on In3 or B.Cu whose endpoints are in different In4 nets
# Build a point-in-polygon for each In4 net using the largest polygons. A point's In4 net is the highest-priority
# zone containing it. Priorities from the generator: +3V3=1, +5V/+1V1=2, analog=3, ADC/DAC=4. Use outline order.
PRIO = {"+3V3": 1, "+5V": 2, "+1V1": 2, "-4V2": 3, "+5VA": 3, "+3V3_ADC": 4, "+3V3_DAC": 4, "GND": 0}

def inside(px, py, poly):
    c = False
    n = len(poly)
    for i in range(n):
        xa, ya = poly[i]
        xb, yb = poly[(i + 1) % n]
        if (ya > py) != (yb > py) and px < xa + (py - ya) * (xb - xa) / ((yb - ya) or 1e-12):
            c = not c
    return c

# Use filled polygons. A point may be in a hole (not in any poly of that net) .
in4 = [(net, polys, PRIO.get(net, 0)) for net, lay, polys in zones if lay == "In4.Cu"]

def in4_net(x, y):
    best = None
    bestp = -1
    for net, polys, pri in in4:
        if pri < bestp:
            continue
        for pts in polys:
            if inside(x, y, pts):
                if pri >= bestp:
                    best, bestp = net, pri
                break
    return best or "NONE"

cross = collections.Counter()
cross_len = collections.Counter()
examples = collections.defaultdict(list)
for L, x0, y0, x1, y1, n, w in segs:
    if L not in ("In3.Cu", "B.Cu", "In2.Cu"):
        continue
    if n in ("GND", "") or n.startswith("+") or n.startswith("-"):
        continue
    a, b = in4_net(x0, y0), in4_net(x1, y1)
    if a != b and "NONE" not in (a, b):
        key = (n, L, a, b)
        cross[key] += 1
        cross_len[key] += math.hypot(x1 - x0, y1 - y0)
        if len(examples[key]) < 2:
            examples[key].append((round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1), round(w, 3)))

Q("\n## In2/In3/B.Cu signal segments whose ends sit on different In4 fills")
# collapse by net and the two fills
by_net = collections.defaultdict(lambda: [0, 0.0, set()])
for (n, L, a, b), c in cross.items():
    by_net[n][0] += c
    by_net[n][1] += cross_len[(n, L, a, b)]
    by_net[n][2].add(f"{L}:{a}->{b}")
Q(f"nets crossing a seam: {len(by_net)}  segments: {sum(cross.values())}")
for n, (c, ln, kinds) in sorted(by_net.items(), key=lambda kv: -kv[1][1])[:60]:
    Q(f"  {ln:6.1f} mm  {c:3d} segs  {n}  {sorted(kinds)}")

# GND vias near a few critical crossings
gnd_v = [(x, y) for x, y, n, s, d in vias if n == "GND"]

def nearest_gnd(x, y):
    best = 99
    for gx, gy in gnd_v:
        best = min(best, math.hypot(gx - x, gy - y))
    return best

Q("\n## nearest GND via to the midpoint of the longest seam-crossing segment of selected nets")
watch = ("ADC_", "DAC_", "CLK", "FLASH", "CCLK", "ETH_", "SDRAM", "DQ", "SPI")
shown = 0
for (n, L, a, b), c in sorted(cross.items(), key=lambda kv: -cross_len[kv[0]]):
    if not any(k in n for k in ("ADC_", "DAC_", "CLK", "FLASH", "CCLK", "MCLK", "SPI", "SD_")):
        continue
    x0, y0, x1, y1, w = examples[(n, L, a, b)][0]
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    Q(f"  {n} {L} {a}->{b} mid ({mx:.1f},{my:.1f}) nearest GND via {nearest_gnd(mx, my):.2f} mm  example w={w}")
    shown += 1
    if shown > 40:
        break

# U604 location and nearby copper
Q("\n## regulator placements")
for ref in ("U604", "U605", "U606", "U601", "U602", "D601", "F601", "F602", "L617", "L618", "L401"):
    hits = [f for f in fps if f["ref"] == ref]
    Q(f"  {ref}: {hits}")

# +5V via count into the corridor (vias of net +5V)
p5 = [v for v in vias if v[2] == "+5V"]
Q(f"\n+5V vias: {len(p5)} drills {collections.Counter(round(v[4],2) for v in p5)}")
Q(f"+3V3 vias: {sum(1 for v in vias if v[2]=='+3V3')}")
Q(f"+1V1 vias: {sum(1 for v in vias if v[2]=='+1V1')}")
Q(f"+3V3_ADC vias: {sum(1 for v in vias if v[2]=='+3V3_ADC')}")
Q(f"+5VA vias: {sum(1 for v in vias if v[2]=='+5VA')}")
Q(f"-4V2 vias: {sum(1 for v in vias if v[2]=='-4V2')}")

# fiducials: footprints or pads
Q("\n## texts containing JLC / fiducial-ish / layer digits near y<5")
for lay, t, x, y in texts:
    if y < 8 or "JLC" in t or "FID" in t.upper() or t in list("123456"):
        if y < 15 or "JLC" in t:
            Q(f"  {lay} ({x:.1f},{y:.1f}) {t!r}")

# shared ground vias: for converter decap pads, but we don't have pad nets easily without walking footprints.
# Count GND vias that are within 0.4 mm of more than one non-via... skip, do pad-level below.

# footprint pads
Q("\n## ground-pad via sharing for U103 U201 U401 U1 decoupling (pads within 0.35 mm of same GND via)")
# collect GND pads of those refs
gnd_pads = []
for node in pcb:
    if not isinstance(node, list) or head(node) != "footprint":
        continue
    a = kid(node, "at")
    fx, fy = float(atom(a[1])) - OX, float(atom(a[2])) - OY
    fa = float(atom(a[3])) if len(a) > 3 else 0.0
    props = {atom(p[1]): atom(p[2]) for p in kids(node, "property") if len(p) > 2}
    ref = props.get("Reference", "?")
    if ref not in ("U103", "U201", "U401", "U1", "U604", "U111", "U112"):
        continue
    back = atom(kid(node, "layer")[1]) == "B.Cu"
    rad = math.radians(-fa)
    for p in kids(node, "pad"):
        nt = kid(p, "net")
        net = netname(nt) if nt else ""
        if net != "GND":
            continue
        pa = kid(p, "at")
        px, py = float(atom(pa[1])), float(atom(pa[2]))
        if back:
            px = -px
        rx = px * math.cos(rad) - py * math.sin(rad)
        ry = px * math.sin(rad) + py * math.cos(rad)
        gnd_pads.append((ref, atom(p[1]), fx + rx, fy + ry))

# map each pad to nearest gnd via
via_users = collections.defaultdict(list)
for ref, num, x, y in gnd_pads:
    best = None
    bestd = 99
    for i, (vx, vy, n, s, d) in enumerate(vias):
        if n != "GND":
            continue
        dist = math.hypot(vx - x, vy - y)
        if dist < bestd:
            bestd = dist
            best = (i, dist)
    if best and best[1] < 0.6:
        via_users[best[0]].append((ref, num, round(best[1], 3)))
shared = {i: u for i, u in via_users.items() if len(u) >= 2}
Q(f"GND pads considered: {len(gnd_pads)}; vias within 0.6 mm shared by >=2 of those pads: {len(shared)}")
for i, u in list(shared.items())[:25]:
    Q(f"  via {vias[i][0]:.2f},{vias[i][1]:.2f} users {u}")

# U604 thermal: GND pin location and nearby GND vias / copper
Q("\n## U604 pins and nearby GND vias")
for node in pcb:
    if not isinstance(node, list) or head(node) != "footprint":
        continue
    props = {atom(p[1]): atom(p[2]) for p in kids(node, "property") if len(p) > 2}
    if props.get("Reference") != "U604":
        continue
    a = kid(node, "at")
    fx, fy = float(atom(a[1])) - OX, float(atom(a[2])) - OY
    fa = float(atom(a[3])) if len(a) > 3 else 0.0
    back = atom(kid(node, "layer")[1]) == "B.Cu"
    rad = math.radians(-fa)
    Q(f"U604 at ({fx:.2f},{fy:.2f}) rot {fa} layer {atom(kid(node,'layer')[1])}")
    for p in kids(node, "pad"):
        nt = kid(p, "net")
        net = netname(nt) if nt else ""
        pa = kid(p, "at")
        px, py = float(atom(pa[1])), float(atom(pa[2]))
        if back:
            px = -px
        rx = px * math.cos(rad) - py * math.sin(rad)
        ry = px * math.sin(rad) + py * math.cos(rad)
        x, y = fx + rx, fy + ry
        near = nearest_gnd(x, y)
        Q(f"  pad {atom(p[1])} {net} ({x:.2f},{y:.2f}) nearest GND via {near:.2f} mm")

open(os.path.join(OUT, "pcb_measure.txt"), "w").write("\n".join(P2) + "\n")
print("pcb written", len(P2))
