#!/usr/bin/env python3
"""Why does a net not route?  For every net, flood-fill from each terminal on
its own layer (own copper lifted, as the router sees it) and report the ones
whose terminal is sealed in a pocket."""
import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_pcb as BP, router as R

b = BP.Build(); b.place(); b.bga(); b.grid(); b.ground_vias()
G = b.G
nx, ny = G.nx, G.ny
nets = [n for n in b.numof if n and n != "GND" and not n.startswith("unconnected-")]


def flood(L, k, cls, limit=3000):
    grid = G.g[(L, cls)]
    seen = {k}; q = collections.deque([k])
    while q and len(seen) < limit:
        c = q.popleft(); i, j = c % nx, c // nx
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ii, jj = i + di, j + dj
            if 0 <= ii < nx and 0 <= jj < ny:
                kk = jj * nx + ii
                if kk not in seen and not grid[kk]:
                    seen.add(kk); q.append(kk)
    return len(seen)


stats = collections.Counter()
examples = collections.defaultdict(list)
for net in nets:
    terms = b.terminals(net)
    if len({t[2] for t in terms}) < 2:
        continue
    cls = R.width_class(BP.CLASS_WIDTH.get(BP.net_class(net), 0.15))
    own = [b.padcells[t[2]] for t in terms if isinstance(t[2], tuple) and t[2] in b.padcells] + b.ownobst.get(net, [])
    seen = set()
    for c in own:
        if id(c) in seen:
            continue
        seen.add(id(c)); G.sub(c)
    sealed = []
    for (L, k, kind) in terms:
        n = flood(L, k, cls)
        if n < 400:
            sealed.append(("%s.%s" % (kind[0], kind[1]) if isinstance(kind, tuple) else kind, R.LAYERS[L], n))
    seen = set()
    for c in own:
        if id(c) in seen:
            continue
        seen.add(id(c)); G.add(c)
    stats["nets"] += 1
    if sealed:
        stats["sealed:" + cls] += 1
        examples[cls].append((net, sealed[:3]))
print(dict(stats))
for cls, ex in examples.items():
    print("==", cls)
    for net, s in ex[:25]:
        print("  ", net, s)
