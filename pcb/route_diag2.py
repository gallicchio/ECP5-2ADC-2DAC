#!/usr/bin/env python3
"""Route one net "by hand": rebuild the router's grid from the FINISHED board
(every track and via the last build laid), lift the net's own copper, and try
the failed connection again while drawing what the router sees -- the obstacle
grid on each of the four routing layers in a postage stamp around the start
and the goal.

    python3 pcb/route_diag2.py "/FPGA, memory, clocks, configuration/SDRAM_DQ7" [more nets]

Writes build/scratch/diag/<net>.png (4 layers x 2 windows) and prints where the
search died.
"""
import os, sys, re, math, json, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_pcb as BP, router as R
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = os.path.join(ROOT, "build", "scratch", "diag")
os.makedirs(OUT, exist_ok=True)
LNAME = {0: "F.Cu", 1: "In2.Cu", 2: "In3.Cu", 3: "B.Cu"}
LIDX = {v: k for k, v in LNAME.items()}


def load_board(path):
    s = open(path, encoding="utf-8").read()
    names = {}
    for m in re.finditer(r'\(net (\d+) "([^"]*)"\)', s[:s.find("(footprint")]):
        names[int(m.group(1))] = m.group(2)
    tracks, vias = [], []
    # KiCad 10 writes the net NAME on segments and vias: (net "+5V")
    for m in re.finditer(r'\(segment\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)\s*\(width ([\d.]+)\)\s*\(layer "([^"]+)"\)\s*\(net "([^"]*)"\)', s):
        x0, y0, x1, y1, w = map(float, m.groups()[:5]); lay = m.group(6); net = m.group(7)
        tracks.append((lay, x0, y0, x1, y1, net, w))
    for m in re.finditer(r'\(via\s*(?:\(type \w+\)\s*)?\(at ([-\d.]+) ([-\d.]+)\)\s*\(size ([\d.]+)\)\s*\(drill ([\d.]+)\)\s*\(layers "([^"]+)" "([^"]+)"\)(.*?)\(net "([^"]*)"\)', s, re.S):
        x, y, size, drill = map(float, m.groups()[:4]); net = m.group(8)
        vias.append((x, y, net, size, drill))
    return tracks, vias


def main():
    want = sys.argv[1:]
    b = BP.Build(); b.place(); b.bga(); b.grid()
    G = b.G
    nx, ny = G.nx, G.ny
    tracks, vias = load_board(os.environ.get("DIAG_BOARD", os.path.join(ROOT, "ECP5-2ADC-2DAC.kicad_pcb")))
    print("board: %d tracks, %d vias" % (len(tracks), len(vias)))
    # everything the board holds goes into the grid, remembered per net so a net's own copper can be lifted
    own = collections.defaultdict(list)
    for (lay, x0, y0, x1, y1, net, w) in tracks:
        if lay not in LIDX:
            continue
        cells = G.obstacle_cells("seg", [LIDX[lay]], (x0, y0, x1, y1, w / 2.0))
        G.add(cells); own[net].append(cells)
    for (x, y, net, size, drill) in vias:
        cells = G.obstacle_cells("disc", [0, 1, 2, 3], (x, y, size / 2.0))
        G.add(cells); own[net].append(cells)
        for kk in G.disc_cells(x, y, drill / 2.0 + 0.25 + BP.VIA_STD[1] / 2.0 + 0.05):
            b.holes[kk] = 1
    rep = json.load(open(os.environ.get("DIAG_REPORT", os.path.join(ROOT, "build", "route_report.json"))))
    fails = collections.defaultdict(list)
    for f in rep.get("failed_connections", []):
        m = re.match(r"(.*): \((\d+), (\d+)\)", f)
        if m:
            fails[m.group(1)].append((int(m.group(2)), int(m.group(3))))
    for net in want:
        if net not in fails:
            print("no failed connection recorded for", net); continue
        # the net's own copper (board) and pads lifted, as the router does
        lifted = own.get(net, []) + b.ownobst.get(net, []) + [b.padcells[k] for k, p in b.pads.items() if p["net"] == net and k in b.padcells]
        for cells in lifted:
            G.sub(cells)
        # what the net already owns: cells of its tracks/vias on their layers
        owned = set()
        for (lay, x0, y0, x1, y1, n2, w) in tracks:
            if n2 == net and lay in LIDX:
                for (i, j) in ((G.cell(x0, y0)), (G.cell(x1, y1))):
                    owned.add((LIDX[lay], j * nx + i))
        for (x, y, n2, size, drill) in vias:
            if n2 == net:
                i, j = G.cell(x, y)
                for L in range(4):
                    owned.add((L, j * nx + i))
        ex = b.esc["exits"].get(net)
        if ex:
            i, j = G.cell(ex[1], ex[2]); owned.add((ex[0], j * nx + i))
        pads_of = [(k2, p) for k2, p in b.pads.items() if p["net"] == net and k2[0] != "U1"]
        for (L, k) in fails[net][:2]:
            i0, j0 = k % nx, k // nx
            if not owned:
                # nothing laid yet: the goal is the net's other pads (what the router does for its first group)
                for k2, p in pads_of:
                    ci, cj = G.cell(p["x"], p["y"])
                    if cj * nx + ci != k:
                        for Lp in ([0, 1, 2, 3] if p["th"] else [LIDX[p["layer"]]]):
                            owned.add((Lp, cj * nx + ci))
            # the goal is the net's copper AWAY from the start (the start pad's own 0.04 mm stub is not a goal)
            owned = set((LL, c) for (LL, c) in owned if abs(c % nx - i0) + abs(c // nx - j0) > 6)
            print("\n== %s: start L%d at (%.1f, %.1f); owned cells %d" % (net, L, i0 * 0.2, j0 * 0.2, len(owned)))
            # a flood across all four layers (vias where the hole grid allows): is any goal reachable at all?
            reach = set(); q = collections.deque([(L, k)]); reach.add((L, k)); hit = None
            while q and len(reach) < 400000:
                cL, c = q.popleft(); ci, cj = c % nx, c // nx
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ii, jj = ci + di, cj + dj
                    if 0 <= ii < nx and 0 <= jj < ny:
                        kk = jj * nx + ii
                        if (cL, kk) not in reach and (not G.g[(cL, "thin")][kk] or (cL, kk) in owned):
                            reach.add((cL, kk)); q.append((cL, kk))
                            if (cL, kk) in owned: hit = (cL, kk)
                if not b.holes[c] and not any(G.g[(LL, "wide")][c] for LL in range(4)):     # a via needs the wide class free, as in router.route
                    for LL in range(4):
                        if LL != cL and (LL, c) not in reach:
                            reach.add((LL, c)); q.append((LL, c))
                if hit: break
            print("   4-layer flood from the start: %d cells, goal %s" % (len(reach), "REACHED at L%d (%.1f, %.1f)" % (hit[0], (hit[1] % nx) * 0.2, (hit[1] // nx) * 0.2) if hit else "NOT reachable"))
            if not hit:
                xs = [c % nx for (LL, c) in reach]; ys = [c // nx for (LL, c) in reach]
                print("   reachable region spans x %.1f..%.1f  y %.1f..%.1f mm, layers %s" % (min(xs) * 0.2, max(xs) * 0.2, min(ys) * 0.2, max(ys) * 0.2, sorted(set(LL for (LL, c) in reach))))
            # flood from the start on its layer: how big is the pocket?
            for cls in ("thin", "mid"):
                grid = G.g[(L, cls)]
                seen = {k}; q = collections.deque([k])
                while q and len(seen) < 4000:
                    c = q.popleft(); ci, cj = c % nx, c // nx
                    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ii, jj = ci + di, cj + dj
                        if 0 <= ii < nx and 0 <= jj < ny:
                            kk = jj * nx + ii
                            if kk not in seen and not grid[kk]:
                                seen.add(kk); q.append(kk)
                print("   flood on L%d class %s from the start: %d cells%s" % (L, cls, len(seen), " (sealed pocket)" if len(seen) < 4000 else " (open)"))
            # the nearest owned cell
            if owned:
                near = min(owned, key=lambda t: abs(t[1] % nx - i0) + abs(t[1] // nx - j0))
                gi, gj = near[1] % nx, near[1] // nx
                print("   nearest owned copper: L%d at (%.1f, %.1f), %.1f mm away" % (near[0], gi * 0.2, gj * 0.2, 0.2 * math.hypot(gi - i0, gj - j0)))
            else:
                gi, gj = i0, j0
            # try the route again, generously
            bb = (max(0, min(i0, gi) - 120), max(0, min(j0, gj) - 120), min(nx - 1, max(i0, gi) + 120), min(ny - 1, max(j0, gj) + 120))
            path = G.route(net, [(L, k)], owned, "thin", bb, via_ok_fn=lambda i, j: not b.holes[j * nx + i], max_pop=2000000, via_cls="mid", via_cost=R.VIA_COST)
            print("   retry with 2M pops:", "FOUND %d cells" % len(path) if path else "no path")
            # the postage stamps: 4 layers around the start and around the goal
            fig, axes = plt.subplots(2, 4, figsize=(20, 10))
            for row, (cx, cy, title) in enumerate(((i0, j0, "start"), (gi, gj, "goal"))):
                for Lr in range(4):
                    ax = axes[row][Lr]
                    H = 45
                    img = np.zeros((2 * H + 1, 2 * H + 1, 3))
                    for dj in range(-H, H + 1):
                        for di in range(-H, H + 1):
                            ii, jj = cx + di, cy + dj
                            if not (0 <= ii < nx and 0 <= jj < ny):
                                continue
                            kk = jj * nx + ii
                            blocked = G.g[(Lr, "thin")][kk] > 0
                            col = (0.35, 0.35, 0.35) if blocked else (0.05, 0.05, 0.05)
                            if b.holes[kk]:
                                col = (0.25, 0.1, 0.1) if blocked else (0.15, 0.05, 0.05)
                            if (Lr, kk) in owned:
                                col = (0.1, 0.5, 1.0)
                            img[dj + H, di + H] = col
                    ax.imshow(img, origin="upper", extent=((cx - H) * 0.2, (cx + H) * 0.2, (cy + H) * 0.2, (cy - H) * 0.2))
                    if Lr == L and row == 0:
                        ax.plot(i0 * 0.2, j0 * 0.2, "r+", ms=14, mew=2)
                    if row == 1:
                        ax.plot(gi * 0.2, gj * 0.2, "c+", ms=14, mew=2)
                    if path:
                        xs = [pi * 0.2 for (pl, pi, pj) in path if pl == Lr]; ys = [pj * 0.2 for (pl, pi, pj) in path if pl == Lr]
                        ax.plot(xs, ys, "y.", ms=2)
                    ax.set_title("%s  %s  (%s)" % (title, LNAME[Lr], "thin class: grey = blocked, dark red = no via"), fontsize=8)
            fig.suptitle(net, fontsize=10)
            fn = os.path.join(OUT, re.sub(r"[^A-Za-z0-9_+-]+", "_", net)[-40:] + "_L%d_%d.png" % (L, k))
            fig.savefig(fn, dpi=70); plt.close(fig)
            print("   wrote", fn)
        for cells in lifted:
            G.add(cells)


if __name__ == "__main__":
    main()
