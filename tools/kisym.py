#!/usr/bin/env python3
"""Print the pins of a stock KiCad 10 symbol:  python3 kisym.py Interface_USB FT2232HL"""
import os, sys, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gen"))
from sexp import parse, head, kids, kid, val, num
SYMDIR = os.path.expanduser("~/.local/kicad10/AppDir/share/kicad/symbols")

def load(lib, name):
    p = os.path.join(SYMDIR, lib + ".kicad_symdir", name + ".kicad_sym")
    if not os.path.exists(p):
        p = os.path.join(SYMDIR, lib + ".kicad_sym")
    doc = parse(open(p, encoding="utf-8").read())[0]
    syms = {val(s): s for s in kids(doc, "symbol")}
    node = syms[name]
    ext = kid(node, "extends")
    pins = []
    if ext:
        parent = syms.get(val(ext))
        if parent is None:
            pp = os.path.join(SYMDIR, lib + ".kicad_symdir", val(ext) + ".kicad_sym")
            parent = {val(s): s for s in kids(parse(open(pp).read())[0], "symbol")}[val(ext)]
        node = parent
    for sub in kids(node, "symbol"):
        unit = val(sub).split("_")[-2]
        for p in kids(sub, "pin"):
            at = kid(p, "at")
            pins.append((unit, val(kid(p, "number")), val(kid(p, "name")), val(p, 1), num(at, 1), num(at, 2), num(at, 3)))
    return pins, (val(ext) if ext else None)

if __name__ == "__main__":
    lib, name = sys.argv[1], sys.argv[2]
    pins, ext = load(lib, name)
    print("%s:%s  (%d pins%s)" % (lib, name, len(pins), ", extends " + ext if ext else ""))
    for u, n, nm, et, x, y, a in sorted(pins, key=lambda t: (t[0], int(t[1]) if t[1].isdigit() else 999, t[1])):
        print("  unit %s  pin %-4s %-18s %-14s at (%6.2f,%6.2f) %3d" % (u, n, nm, et, x, y, a))
