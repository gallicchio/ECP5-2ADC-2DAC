"""The netlist, read for the pin audits (check_power_pins.py, check_pairs.py).

    comps[ref]  = (value, footprint, 'lib:part')
    pins[ref][pin] = (pinfunction, pintype, net)
    nets[net] = [(ref, pin, pinfunction, pintype), ...]
"""
import collections
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NETLIST = os.path.join(ROOT, "build", "netlist.net")


def load(path=NETLIST):
    t = open(path).read()
    i = t.index("\t(nets")
    comps = {}
    for c in re.split(r"\n\t\t\(comp\b", t[t.index("\t(components"):i])[1:]:
        ref = re.search(r'\(ref "([^"]+)"\)', c).group(1)
        val = re.search(r'\(value "([^"]*)"\)', c)
        fp = re.search(r'\(footprint "([^"]*)"\)', c)
        lib = re.search(r'\(lib "([^"]*)"\)\s*\(part "([^"]*)"\)', c)
        comps[ref] = (val.group(1) if val else "", fp.group(1) if fp else "", (lib.group(1) + ":" + lib.group(2)) if lib else "")
    pins = collections.defaultdict(dict)
    nets = collections.defaultdict(list)
    for blk in re.split(r"\n\t\t\(net\b", t[i:])[1:]:
        name = re.search(r'\(name "([^"]*)"\)', blk).group(1)
        for m in re.finditer(r'\(node\s*\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)\s*(?:\(pinfunction "([^"]*)"\))?\s*(?:\(pintype "([^"]*)"\))?', blk):
            ref, pin, fn, ty = m.group(1), m.group(2), m.group(3) or "", m.group(4) or ""
            pins[ref][pin] = (fn, ty, name)
            nets[name].append((ref, pin, fn, ty))
    return comps, pins, nets
