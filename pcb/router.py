"""A four-layer grid router (F.Cu, In2.Cu, In3.Cu, B.Cu) with A* per net.

Grid pitch 0.2 mm.  Obstacles live in reference-counted cell grids, one per
(layer, width class): an obstacle of radius R blocks every cell closer than
R + clearance + hw(class) to it, so a route of that class is legal wherever
its cells are free.  A net's own pads are lifted out of the grids before it
is routed and put back after, which is what lets a track start inside its pad.
Vias are through vias (0.45/0.25, 0.3/0.15 under the BGA) and need a free
cell on every layer in the "wide" grids.

Multi-terminal nets are built one terminal at a time: every cell the net
already owns is a goal for the next terminal.
"""
import heapq, math
from array import array

PITCH = 0.2
NL = 4
LAYERS = ["F.Cu", "In2.Cu", "In3.Cu", "B.Cu"]
CLEAR = 0.16          # the Power class asks 0.15 (DRC found 0.148 after grid rounding); everything else 0.127
CLASSES = {"thin": 0.075, "mid": 0.15, "wide": 0.25}     # half widths
CLS = ["thin", "mid", "wide"]
VIA_COST = 24.0           # about 5 mm of track
LANE_PEN = 6.0            # a step along a face / a pad row inside its fan-out lane costs this much more
LANE_VIA_PEN = 4.0        # a via inside a lane costs this much more (build 7/8 forbade it: the ADC's supply
                          # pins and a dozen others lost the only via spot they had, right in front of the pad)
TURN_COST = 1.0
DIR_PENALTY = {0: (1.0, 1.0), 1: (1.0, 1.6), 2: (1.6, 1.0), 3: (1.0, 1.0)}   # (horizontal, vertical) per layer


def width_class(w):
    hw = w / 2.0
    for c in CLS:
        if hw <= CLASSES[c] + 1e-6:
            return c
    return "wide"


class Grid:
    def __init__(self, w, h, margin=0.6, pitch=PITCH):
        self.pitch = pitch
        self.nx, self.ny = int(w / pitch) + 1, int(h / pitch) + 1
        self.n = self.nx * self.ny
        self.g = {(L, c): array("H", bytes(2 * self.n)) for L in range(NL) for c in CLS}
        self.lane = bytearray(self.n)       # fan-out lanes: 1 = steps along x penalised, 2 = along y
        self.owner = {}      # (L, k) -> set of net names occupying (for goals)
        m = int(margin / self.pitch)
        edge = set()
        for i in range(self.nx):
            for j in range(self.ny):
                if i < m or j < m or i >= self.nx - m or j >= self.ny - m:
                    edge.add(j * self.nx + i)
        for key, a in self.g.items():
            for k in edge:
                a[k] = 1

    def cell(self, x, y):
        return (int(round(x / self.pitch)), int(round(y / self.pitch)))

    def pos(self, i, j):
        return (i * self.pitch, j * self.pitch)

    # ---- rasterising obstacles -------------------------------------------
    def disc_cells(self, x, y, r):
        ci, cj = self.cell(x, y)
        n = int(math.ceil(r / self.pitch)) + 1
        r2 = r * r
        out = []
        for di in range(-n, n + 1):
            i = ci + di
            if i < 0 or i >= self.nx:
                continue
            dx2 = (i * self.pitch - x) ** 2
            for dj in range(-n, n + 1):
                j = cj + dj
                if 0 <= j < self.ny and dx2 + (j * self.pitch - y) ** 2 <= r2:
                    out.append(j * self.nx + i)
        return out

    def seg_cells(self, x0, y0, x1, y1, r):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L / (self.pitch * 0.5)))
        out = set()
        for k in range(n + 1):
            t = k / float(n)
            out.update(self.disc_cells(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r))
        return out

    def rect_cells(self, x, y, hw, hh, ang, r):
        """cells within r of an (hw x hh) rectangle rotated ang about (x, y)"""
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        rr = math.hypot(hw, hh) + r
        ci, cj = self.cell(x, y)
        n = int(math.ceil(rr / self.pitch)) + 1
        out = []
        for di in range(-n, n + 1):
            i = ci + di
            if i < 0 or i >= self.nx:
                continue
            for dj in range(-n, n + 1):
                j = cj + dj
                if not (0 <= j < self.ny):
                    continue
                dx, dy = i * self.pitch - x, j * self.pitch - y
                ux, uy = dx * ca + dy * sa, -dx * sa + dy * ca
                gx, gy = max(0.0, abs(ux) - hw), max(0.0, abs(uy) - hh)
                if gx * gx + gy * gy <= r * r:
                    out.append(j * self.nx + i)
        return out

    def obstacle_cells(self, kind, layers, geom, radius_extra=0.0):
        """Per (layer, class) cell lists for an obstacle.  kind: disc (x, y, r)
        or rect (x, y, hw, hh, ang) or seg (x0, y0, x1, y1, r)."""
        out = {}
        for c in CLS:
            r = CLEAR + CLASSES[c] + radius_extra
            if kind == "disc":
                cells = self.disc_cells(geom[0], geom[1], geom[2] + r)
            elif kind == "rect":
                cells = self.rect_cells(geom[0], geom[1], geom[2], geom[3], geom[4], r)
            else:
                cells = self.seg_cells(geom[0], geom[1], geom[2], geom[3], geom[4] + r)
            for L in layers:
                out[(L, c)] = cells
        return out

    def add(self, cells):
        for key, ks in cells.items():
            a = self.g[key]
            for k in ks:
                a[k] += 1

    def sub(self, cells):
        for key, ks in cells.items():
            a = self.g[key]
            for k in ks:
                if a[k] > 0:
                    a[k] -= 1

    def mark_lane(self, x0, y0, x1, y1, kind):
        """Cells in the box get lane `kind`: 1 = moves along x are penalised, 2 = moves along y;
        3 and 4 the same but forbidden outright (the inner band in front of an exit); 5 and 6 penalised
        and no via may stand there (the first 0.8 mm in front of a fine-pitch pad)."""
        i0, j0 = self.cell(min(x0, x1), min(y0, y1)); i1, j1 = self.cell(max(x0, x1), max(y0, y1))
        for j in range(max(0, j0), min(self.ny - 1, j1) + 1):
            base = j * self.nx
            for i in range(max(0, i0), min(self.nx - 1, i1) + 1):
                self.lane[base + i] = kind

    def own(self, net, L, k):
        self.owner.setdefault(net, set()).add((L, k))

    # ---- the search -------------------------------------------------------
    def route(self, net, starts, goals, cls, bbox, allow_via=True, via_ok_fn=None, bonus=None, layers=None, max_pop=400000, via_cls="wide", via_cost=VIA_COST):
        """starts/goals: iterables of (L, k).  Returns the path [(L, i, j), ...]
        or None.  bbox: (i0, j0, i1, j1) search window.  via_cls: the grid
        class whose half width matches the via's radius ("mid" for a 0.3 mm
        via, "wide" for 0.45)."""
        i0, j0, i1, j1 = bbox
        nx = self.nx
        grid = [self.g[(L, cls)] for L in range(NL)]
        wide = [self.g[(L, via_cls)] for L in range(NL)]
        lane = self.lane
        goal = set(goals)
        if not goal:
            return None
        gpts = [(k % nx, k // nx) for (L, k) in goal]
        # heuristic: distance to the nearest goal (as the crow flies, in cells)
        def h(i, j):
            best = 1e18
            for gi, gj in gpts:
                d = abs(gi - i) + abs(gj - j)
                if d < best:
                    best = d
            return best * 0.95
        if len(gpts) > 40:
            # too many goals to scan each time: use the nearest few to the first start
            si, sj = starts[0][1] % nx, starts[0][1] // nx
            gpts = sorted(gpts, key=lambda p: abs(p[0] - si) + abs(p[1] - sj))[:40]
        pq = []
        best = {}
        par = {}
        for (L, k) in starts:
            if (L, k) in goal:
                return [(L, k % nx, k // nx)]
            best[(L, k)] = 0.0
            heapq.heappush(pq, (h(k % nx, k // nx), 0.0, L, k, -1))
        use_layers = layers if layers is not None else range(NL)
        pops = 0
        found = None
        # 8 neighbours: (di, dj, cost, dir)
        NB = [(1, 0, 1.0, 0), (-1, 0, 1.0, 0), (0, 1, 1.0, 1), (0, -1, 1.0, 1),
              (1, 1, 1.414, 2), (1, -1, 1.414, 3), (-1, 1, 1.414, 3), (-1, -1, 1.414, 2)]
        while pq:
            f, gc, L, k, d = heapq.heappop(pq)
            if best.get((L, k), 1e18) < gc - 1e-9:
                continue
            pops += 1
            if pops > max_pop:
                break
            if (L, k) in goal:
                found = (L, k)
                break
            i, j = k % nx, k // nx
            ph, pv = DIR_PENALTY[L]
            bl = bonus.get(L) if bonus else None
            for di, dj, c, nd in NB:
                ii, jj = i + di, j + dj
                if ii < i0 or jj < j0 or ii > i1 or jj > j1:
                    continue
                kk = jj * nx + ii
                if grid[L][kk] and (L, kk) not in goal:
                    continue
                if di and dj:
                    # no corner cutting: both orthogonal neighbours must be free
                    if grid[L][j * nx + ii] or grid[L][jj * nx + i]:
                        continue
                    cc = c * (ph + pv) / 2.0
                else:
                    cc = c * (ph if di else pv)
                ln = lane[kk]
                if ln:
                    pstep = (di if ln in (1, 3, 5) else dj)
                    if pstep:
                        if ln in (3, 4):
                            continue        # the last stretch in front of an exit: straight only
                        cc *= LANE_PEN      # the rest of the fan-out lane: leave straight, turn later
                if d >= 0 and d != nd:
                    cc += TURN_COST
                if bl is not None and bl[kk]:
                    cc *= 0.5
                ng = gc + cc
                if ng < best.get((L, kk), 1e18):
                    best[(L, kk)] = ng
                    par[(L, kk)] = (L, k)
                    heapq.heappush(pq, (ng + h(ii, jj), ng, L, kk, nd))
            if allow_via and lane[k] < 5:
                # a via here: every layer's wide grid must be free at this cell.  Inside a fan-out lane it
                # costs LANE_VIA_PEN times more (a via 0.4 mm beside an exit or a fine-pitch pad walls it
                # in), so a route leaves the lane before it changes layer unless it has no other way; in
                # the first 0.8 mm in front of a fine-pitch pad (kinds 5/6) it is impossible: build 9 put a
                # VREF via 0.25 mm in front of the AD9238's west row and walled three pads at once.
                if all(not wide[LL][k] for LL in range(NL)) and (via_ok_fn is None or via_ok_fn(i, j)):
                    vc = via_cost * LANE_VIA_PEN if lane[k] else via_cost
                    for LL in use_layers:
                        if LL == L:
                            continue
                        ng = gc + vc
                        if ng < best.get((LL, k), 1e18):
                            best[(LL, k)] = ng
                            par[(LL, k)] = (L, k)
                            heapq.heappush(pq, (ng + h(i, j), ng, LL, k, -1))
        if found is None:
            return None
        path = []
        cur = found
        while cur is not None:
            path.append((cur[0], cur[1] % nx, cur[1] // nx))
            cur = par.get(cur)
        path.reverse()
        return path


def simplify(path, pitch=PITCH):
    """Merge runs of equal direction on one layer into segments; vias where
    the layer changes.  Returns (segments [(L, x0, y0, x1, y1)], vias [(x, y)])."""
    segs, vias = [], []
    if not path:
        return segs, vias
    i = 0
    while i < len(path):
        L, a, b = path[i]
        j = i
        # extend while the same layer and the same step direction
        if i + 1 < len(path) and path[i + 1][0] == L:
            d = (path[i + 1][1] - a, path[i + 1][2] - b)
            j = i + 1
            while j + 1 < len(path) and path[j + 1][0] == L and (path[j + 1][1] - path[j][1], path[j + 1][2] - path[j][2]) == d:
                j += 1
            segs.append((L, a * pitch, b * pitch, path[j][1] * pitch, path[j][2] * pitch))
            i = j
        else:
            if i + 1 < len(path) and path[i + 1][0] != L:
                vias.append((a * pitch, b * pitch))
            i += 1
    return segs, vias
