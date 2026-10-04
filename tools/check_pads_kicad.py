#!/usr/bin/env python3
"""Ask KiCad itself where every pad of the placed board is, and compare with
what pcb/fplib.py believed when it placed and routed the part.  Any
disagreement means our idea of a rotation (0/90/180/270, front/back) is wrong
for that footprint.  Runs KiCad's own pcbnew module from the AppImage:

    tools/check_pads_kicad.py            # prints a per-footprint table and the mismatches
"""
import os, sys, subprocess, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.expanduser("~/.local/kicad10/AppDir")

if os.environ.get("_INSIDE_KICAD_PY") != "1":
    env = dict(os.environ, _INSIDE_KICAD_PY="1",
               LD_LIBRARY_PATH=APP + "/usr/lib:" + APP + "/shared/lib",
               PYTHONPATH=APP + "/shared/lib/python3.11/dist-packages")
    sys.exit(subprocess.call([APP + "/usr/bin/python3.11", __file__] + sys.argv[1:], env=env))

import pcbnew
sys.path.insert(0, os.path.join(ROOT, "pcb"))
import fplib, netmap

board = pcbnew.LoadBoard(os.path.join(ROOT, "ECP5-2ADC-2DAC.kicad_pcb"))
fps, vals, nets, numof = netmap.load(os.path.join(ROOT, "build", "netlist.net"))
placement = json.load(open(os.path.join(ROOT, "build", "placement.json")))

bad, n_pads, n_fp = [], 0, 0
worst = 0.0
by_rot = {}
for fp in board.GetFootprints():
    ref = fp.GetReference()
    if ref not in placement or ref not in fps:
        continue
    x, y, rot, layer = placement[ref]
    ours = {}
    for i, p in enumerate(fplib.pads_at(fplib.load(fps[ref]), x, y, rot, back=(layer == "B.Cu"))):
        ours.setdefault(p["num"], []).append((p["x"], p["y"]))
    n_fp += 1
    key = (rot, layer, fp.GetLayerName())
    by_rot[key] = by_rot.get(key, 0) + 1
    for pad in fp.Pads():
        num = pad.GetNumber()
        pos = pad.GetPosition()
        kx, ky = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        n_pads += 1
        cands = ours.get(num, [])
        if not cands:
            bad.append((ref, num, "no such pad in fplib"))
            continue
        d = min(((kx - ox) ** 2 + (ky - oy) ** 2) ** 0.5 for (ox, oy) in cands)
        worst = max(worst, d)
        if d > 0.02:
            bad.append((ref, num, "KiCad (%.3f, %.3f) vs ours %s, rot %s %s" % (kx, ky, [(round(a, 3), round(b, 3)) for a, b in cands], rot, layer)))

print("footprints checked: %d, pads: %d, worst disagreement %.4f mm" % (n_fp, n_pads, worst))
print("rotations seen (ours, our layer, KiCad layer): count")
for k, v in sorted(by_rot.items()):
    print("  %s: %d" % (k, v))
if bad:
    print("MISMATCHES: %d" % len(bad))
    for b in bad[:60]:
        print("  ", b)
    sys.exit(1)
print("every pad is where KiCad puts it: the rotation and back-side conventions in pcb/fplib.py agree with KiCad")
