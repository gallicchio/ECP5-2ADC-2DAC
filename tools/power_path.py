"""python3 tools/power_path.py [board.kicad_pcb]

DC resistance from each rail's source to every power pin of the FPGA, the ADC and the DAC, along the copper the
board actually has: tracks (1 oz outer, 0.5 oz inner), vias (1 mOhm), and the In4 planes (0 Ohm between the vias
and pads inside a zone of the net).  Dijkstra on resistance; the result is the worst pin per rail and chip."""
import sys, re, math, heapq, collections
sys.path.insert(0, "gen"); sys.path.insert(0, "pcb")
from sexp import parse, kids, kid, head
OX = OY = 25.0
RHO = 1.72e-8                      # ohm m, copper
T = {"F.Cu": 35e-6, "B.Cu": 35e-6, "In1.Cu": 17.5e-6, "In2.Cu": 17.5e-6, "In3.Cu": 17.5e-6, "In4.Cu": 17.5e-6}
def atom(n): return n[1] if isinstance(n, tuple) else n
def rot(x, y, a):
    r = math.radians(-a); return x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)
def inside(px, py, poly):
    c = False; n = len(poly)
    for i in range(n):
        (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
        if (ya > py) != (yb > py) and px < xa + (py - ya) * (xb - xa) / (yb - ya): c = not c
    return c
doc = parse(open(sys.argv[1] if len(sys.argv) > 1 else "ECP5-2ADC-2DAC.kicad_pcb").read())[0]
segs, vias, pads, zones = [], [], [], []
NAMES = {}
for node in doc:
    if isinstance(node, list) and head(node) == "net" and len(node) > 2:
        NAMES[int(atom(node[1]))] = atom(node[2])
def netname(nt):
    if not nt or len(nt) < 2: return ""
    if len(nt) > 2: return atom(nt[2])
    v = atom(nt[1])
    return NAMES.get(int(v), v) if str(v).lstrip("-").isdigit() else v
for node in doc:
    if not isinstance(node, list): continue
    h = head(node)
    if h == "segment":
        s_, e_ = kid(node, "start"), kid(node, "end")
        segs.append((atom(kid(node, "layer")[1]), float(atom(s_[1])) - OX, float(atom(s_[2])) - OY, float(atom(e_[1])) - OX, float(atom(e_[2])) - OY, netname(kid(node, "net")), float(atom(kid(node, "width")[1]))))
    elif h == "via":
        a = kid(node, "at"); vias.append((float(atom(a[1])) - OX, float(atom(a[2])) - OY, netname(kid(node, "net"))))
    elif h == "zone":
        nt = kid(node, "net")
        if not nt or len(nt) < 2: continue
        net = netname(nt); lay = kid(node, "layer"); lay = atom(lay[1]) if lay else "?"
        pol = kid(node, "polygon")
        if pol:
            pts = [(float(atom(q[1])) - OX, float(atom(q[2])) - OY) for q in kids(kid(pol, "pts"), "xy")]
            zones.append((net, lay, pts))
    elif h == "footprint":
        a = kid(node, "at"); fx, fy = float(atom(a[1])) - OX, float(atom(a[2])) - OY; fa = float(atom(a[3])) if len(a) > 3 else 0.0
        props = {atom(p[1]): atom(p[2]) for p in kids(node, "property") if len(p) > 2}
        ref = props.get("Reference", "?"); lyr = atom(kid(node, "layer")[1])
        for p in kids(node, "pad"):
            nt = kid(p, "net"); net = netname(nt) if nt else ""
            if not net: continue
            pa = kid(p, "at"); px, py = rot(float(atom(pa[1])), float(atom(pa[2])), fa)
            kind = atom(p[2]); sz = kid(p, "size")
            pads.append((ref, atom(p[1]), fx + px, fy + py, net, lyr, kind in ("thru_hole", "np_thru_hole"), max(float(atom(sz[1])), float(atom(sz[2])))))
print("%d segments, %d vias, %d pads, %d zones (%s)" % (len(segs), len(vias), len(pads), len(zones), sorted({(z[0], z[1]) for z in zones})))
# the graph per net: nodes keyed by (layer, x, y) rounded; vias join all layers; plane zones join their vias/TH pads
def key(L, x, y): return (L, round(x, 2), round(y, 2))
RAILS = ["+1V1", "+3V3", "+2V5_AUX", "+3V3_ADC", "+3V3_DRV", "+3V3_DAC", "+3V3_DAC_D", "+5V", "+5VA", "-4V2", "+3V3_ETH", "+1V0_PHY", "+1V8_FTDI", "+2V5"]
CHIPS = {"U1": "FPGA", "U103": "AD9238", "U201": "AD9767", "U401": "RTL8211F", "U502": "FT2232H", "U305": "SDRAM", "U101": "OPA1612 A", "U102": "OPA1612 B", "U111": "THS4521 A", "U202": "OPA2810 1", "U105": "TIA"}
SOURCES = {"+1V1": ["L618"], "+3V3": ["L617"], "+5V": ["F501", "J601", "D601"], "+2V5_AUX": ["U603"], "+3V3_ADC": ["FB8201", "FB8211", "FB8221", "FB8231", "FB8301", "FB8311"],
           "+3V3_DRV": ["FB8201", "FB8211", "FB8221", "FB8231", "FB8301", "FB8311"], "+3V3_DAC": ["FB8201", "FB8211", "FB8221", "FB8231", "FB8301", "FB8311"],
           "+3V3_DAC_D": ["FB8201", "FB8211", "FB8221", "FB8231", "FB8301", "FB8311"], "+5VA": ["FB8201", "FB8211", "FB8221", "FB8231", "FB8301", "FB8311", "U604"],
           "-4V2": ["FB8301", "FB8231", "FB8311", "U606"], "+3V3_ETH": ["FB8201", "FB8211", "FB8221", "FB8231", "FB8301", "FB8311"], "+1V0_PHY": ["L401"], "+1V8_FTDI": ["U502", "C6241", "FB6241"], "+2V5": ["U603", "U605"]}
for net in RAILS:
    adj = collections.defaultdict(list)
    def link(a, b, r):
        adj[a].append((b, r)); adj[b].append((a, r))
    for (L, x0, y0, x1, y1, n, w) in segs:
        if n != net: continue
        length = math.hypot(x1 - x0, y1 - y0) * 1e-3
        r = RHO * length / (w * 1e-3 * T.get(L, 35e-6)) if length > 0 else 0.0
        link(key(L, x0, y0), key(L, x1, y1), r)
    layers = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
    plane = ("PLANE", net)
    zpolys = [(lay, pts) for (zn, lay, pts) in zones if zn == net]
    for (x, y, n) in vias:
        if n != net: continue
        for i in range(len(layers) - 1):
            link(key(layers[i], x, y), key(layers[i + 1], x, y), 0.001)
        for lay, pts in zpolys:
            if inside(x, y, pts): link(key(lay, x, y), plane, 0.0005)
    own = [(L, x0, y0, x1, y1, w) for (L, x0, y0, x1, y1, n, w) in segs if n == net]
    for (L, x0, y0, x1, y1, w) in own:
        for (px, py) in ((x0, y0), (x1, y1)):
            for (L2, u0, v0, u1, v1, w2) in own:
                if L2 != L or (u0, v0, u1, v1) == (x0, y0, x1, y1): continue
                dx, dy = u1 - u0, v1 - v0; ll = dx * dx + dy * dy
                if ll < 1e-9: continue
                t = ((px - u0) * dx + (py - v0) * dy) / ll
                if t <= 0.02 or t >= 0.98: continue
                qx, qy = u0 + t * dx, v0 + t * dy
                if math.hypot(px - qx, py - qy) <= w2 / 2.0 + 0.05:
                    length = math.sqrt(ll) * 1e-3; r = RHO * length / (w2 * 1e-3 * T.get(L2, 35e-6))
                    j = key(L2, qx, qy)
                    link(key(L2, u0, v0), j, r * t); link(j, key(L2, u1, v1), r * (1 - t)); link(key(L, px, py), j, 0.0)
    # a via on a track's interior (the router drops vias on path points that simplify() folds into one straight
    # segment): KiCad sees the annulus on the copper; an endpoint model saw nothing (the +3V3_DRV gap, Prompt 29)
    own_vias = [(x, y) for (x, y, n) in vias if n == net]
    for (vx, vy) in own_vias:
        for (L2, u0, v0, u1, v1, w2) in own:
            dx, dy = u1 - u0, v1 - v0; ll = dx * dx + dy * dy
            if ll < 1e-9: continue
            t = ((vx - u0) * dx + (vy - v0) * dy) / ll
            if t <= 0.02 or t >= 0.98: continue
            qx, qy = u0 + t * dx, v0 + t * dy
            if math.hypot(vx - qx, vy - qy) <= w2 / 2.0 + 0.2:
                length = math.sqrt(ll) * 1e-3; r = RHO * length / (w2 * 1e-3 * T.get(L2, 35e-6))
                j = key(L2, qx, qy)
                link(key(L2, u0, v0), j, r * t); link(j, key(L2, u1, v1), r * (1 - t)); link(key(L2, vx, vy), j, 0.0002)
    # a track that ends on a via's rim rather than its centre is still joined to it in copper
    endpoints = collections.defaultdict(list)
    for (L, x0, y0, x1, y1, w) in own:
        endpoints[L].append((x0, y0)); endpoints[L].append((x1, y1))
    for (vx, vy) in own_vias:
        for L in layers:
            for (ex, ey) in endpoints.get(L, []):
                if 0 < math.hypot(ex - vx, ey - vy) <= 0.35:
                    link(key(L, ex, ey), key(L, vx, vy), 0.0002)
    pad_nodes = {}
    pad_geom = []
    for (ref, num, x, y, n, lyr, th, size) in pads:
        if n != net: continue
        if th:
            for i in range(len(layers) - 1):
                link(key(layers[i], x, y), key(layers[i + 1], x, y), 0.001)
            for lay, pts in zpolys:
                if inside(x, y, pts): link(key(lay, x, y), plane, 0.0005)
            node = key("F.Cu", x, y)
        else:
            node = key(lyr, x, y)
        pad_nodes[(ref, num)] = node
        pad_geom.append((x, y, size / 2.0 + 0.1, layers if th else [lyr]))
    # every node of the net inside a pad's copper joins the pad, on each layer the pad is on (a through-hole pad on all
    # six): the +5VA gap of Prompt 29 was a B.Cu track ending inside the RAILS header's pin, joined on F.Cu only
    nodes_by_layer = collections.defaultdict(list)
    for k in list(adj.keys()):
        if k != plane: nodes_by_layer[k[0]].append(k)
    for (x, y, r, lays) in pad_geom:
        for lay in lays:
            pn = key(lay, x, y)
            for k in nodes_by_layer.get(lay, []):
                if k != pn and math.hypot(k[1] - x, k[2] - y) <= r:
                    link(pn, k, 0.0002)
    src_refs = sorted({ref for (ref, num) in pad_nodes if ref.startswith(("FB", "L6", "L4", "U60", "U8", "F5", "J601", "J501"))})
    src = [nd for (ref, num), nd in pad_nodes.items() if ref in src_refs]
    print("%-11s parts: %s; sources: %s" % (net, " ".join(sorted({ref for (ref, num) in pad_nodes if not ref.startswith(("C", "R", "JP", "J6", "TP"))})), " ".join(src_refs) or "-"))
    if plane in adj: src.append(plane)
    if not src:
        print("%-11s no source found" % net); continue
    dist = {s_: 0.0 for s_ in src}; pq = [(0.0, s_) for s_ in src]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e9): continue
        for v, r in adj[u]:
            nd_ = d + r
            if nd_ < dist.get(v, 1e9):
                dist[v] = nd_; heapq.heappush(pq, (nd_, v))
    out = collections.defaultdict(list)
    for (ref, num), nd in pad_nodes.items():
        if ref in CHIPS:
            out[ref].append((dist.get(nd, float("inf")), num))
    for ref in sorted(out):
        ds = sorted(out[ref])
        unreached = [n for d, n in ds if d == float("inf")]
        reached = [d for d, n in ds if d != float("inf")]
        ok = [(d, n) for d, n in ds if d != float("inf")]
        print("%-11s -> %-8s %2d pins: worst %6.1f mOhm (pin %s), best %5.1f, median %5.1f%s" % (net, CHIPS[ref], len(ds), (ok[-1][0] * 1e3 if ok else float('nan')), (ok[-1][1] if ok else '-'), (ok[0][0] * 1e3 if ok else float('nan')), (ok[len(ok) // 2][0] * 1e3 if ok else float('nan')), ("  UNREACHED %s" % unreached if unreached else "")))
