#!/usr/bin/env python3
"""Walk the signal paths through the netlist and print them, one chain per line:
from each SMA, header, photodiode, oscillator and converter pin through every
series part (R, C, L, ferrite, fuse, jumper, switch, buffer, op-amp, transistor)
to whatever ends the path (an IC pin, a connector, a rail).  Shunt parts on each
net are listed in brackets.  This is the review Jason asked for: "trace through
all of the signal paths ... make sure everything makes sense".

    python3 tools/trace_paths.py  >  docs/SIGNAL_PATHS.md
"""
import os, sys, re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "pcb"))
import netmap

fps, vals, nets, numof = netmap.load(os.path.join(ROOT, "build", "netlist.net"))
bynet = {}
for ref, pn in nets.items():
    for pad, net in pn.items():
        bynet.setdefault(net, []).append((ref, pad))


def is_power(net):
    return net == "GND" or net.startswith("+") or net.startswith("-")


# how a signal passes through a part: pad -> [pads it continues on]
DUAL_OPAMP = {"2": ["1"], "3": ["1"], "6": ["7"], "5": ["7"]}            # OPA1612 / OPA2810 (SOIC-8): -IN/+IN -> OUT
FDA = {"1": ["4", "5"], "8": ["4", "5"]}                                  # THS4521: VIN-/VIN+ -> VOUT+/VOUT-
BUF = {"2": ["4"]}                                                        # SOT-23-5 single gate: IN -> OUT
BJT = {"1": ["3"], "2": ["3"]}                                            # SOT-23 BJT: B -> C, E -> C
DIP4 = {"1": ["8"], "2": ["7"], "3": ["6"], "4": ["5"], "8": ["1"], "7": ["2"], "6": ["3"], "5": ["4"]}


def passes(ref, pad):
    v = vals.get(ref, "")
    pn = nets.get(ref, {})
    pads = sorted(pn)
    if ref[0] in "RCLF" or ref.startswith("FB"):
        if len(pads) == 2:
            return [p for p in pads if p != pad]
        return []
    if ref.startswith("JP"):
        if len(pads) == 2:
            return [p for p in pads if p != pad]
        if len(pads) == 3:
            return ["1", "3"] if pad == "2" else ["2"]
    if ref.startswith("SW") and "DSWB" in v:
        return DIP4.get(pad, [])
    if ref.startswith("Q"):
        return BJT.get(pad, [])
    if ref.startswith("U"):
        if v.startswith("OPA1612") or v.startswith("OPA2810"):
            return DUAL_OPAMP.get(pad, [])
        if v.startswith("THS4521"):
            return FDA.get(pad, [])
        if v.startswith("SN74LVC1G"):
            return BUF.get(pad, [])
    if ref.startswith("D") and vals.get(ref, "") in ("B5819W",):
        return [p for p in pads if p != pad]
    return []


def part_name(ref, pad):
    v = vals.get(ref, "")
    return "%s(%s).%s" % (ref, v, pad) if v else "%s.%s" % (ref, pad)


def trace(start_ref, start_pad, depth=0, seen=None, out=None, indent=""):
    """Depth-first: print every chain from (ref, pad)."""
    if seen is None:
        seen = set()
    net = nets[start_ref][start_pad]
    if (start_ref, start_pad) in seen:
        return
    seen.add((start_ref, start_pad))
    others = [(r, p) for (r, p) in bynet.get(net, []) if (r, p) != (start_ref, start_pad)]
    shunts, nexts, ends = [], [], []
    for (r, p) in others:
        cont = passes(r, p)
        if r.startswith("TP"):
            shunts.append("TP %s" % r)
            continue
        if cont:
            # a series part: where its other pin(s) go
            for p2 in cont:
                n2 = nets[r][p2]
                if is_power(n2):
                    shunts.append("%s %s to %s" % (r, vals.get(r, ""), n2))
                else:
                    nexts.append((r, p, p2, n2))
        else:
            ends.append((r, p))
    line = "%s%s  [net %s]" % (indent, part_name(start_ref, start_pad), net)
    if shunts:
        line += "   {%s}" % "; ".join(shunts)
    if ends:
        line += "   -> " + ", ".join(part_name(r, p) for (r, p) in ends)
    print(line)
    if depth > 14:
        print(indent + "  ...")
        return
    for (r, p, p2, n2) in nexts:
        print("%s  via %s pin %s -> pin %s" % (indent, r + ("(%s)" % vals.get(r, "") if vals.get(r) else ""), p, p2))
        if (r, p2) in seen:
            print("%s    (already shown)" % indent)
            continue
        trace(r, p2, depth + 1, seen, out, indent + "    ")


STARTS = [
    ("ADC A input, SMA J101", "J101", "1"),
    ("ADC B input, SMA J102", "J102", "1"),
    ("NOISE header J105 (R, pin 2)", "J105", "2"),
    ("photodiode D103 cathode", "D103", "1"),
    ("photodiode D103 anode", "D103", "2"),
    ("PD EXT header J106 (K, pin 2)", "J106", "2"),
    ("DAC port 1 IOUTA", "U201", None),
    ("DAC port 1 IOUTB", "U201", None),
    ("DAC port 2 IOUTA", "U201", None),
    ("DAC port 2 IOUTB", "U201", None),
    ("LED EXT header J210", "J210", "2"),
    ("CLK IN SMA J301", "J301", "1"),
    ("TCXO X301 output", "X301", "3"),
    ("Si5351 U301 CLK0", "U301", None),
    ("Si5351 U301 CLK1", "U301", None),
    ("Si5351 U301 CLK2", "U301", None),
    ("CLK OUT SMA J302 (traced backwards)", "J302", "1"),
    ("ADC clock A (from the FPGA)", "U103", None),
    ("ADC clock B (from the FPGA)", "U103", None),
    ("DAC CLK1 (from the FPGA)", "U201", None),
    ("DAC CLK2 (from the FPGA)", "U201", None),
]


def pad_of(ref, netpat):
    for p, n in nets[ref].items():
        if re.search(netpat, n):
            return p
    return None


if __name__ == "__main__":
    print("# Signal paths, traced through the netlist\n")
    print("Generated by `tools/trace_paths.py` from `build/netlist.net`.  Each line is a node of the path:")
    print("the part and pin the signal is at, the net, {shunt parts on that net}, and -> the pins that end the path.\n")
    special = {("DAC port 1 IOUTA", "U201"): r"IOUT1A|/DAC/DAC_P1_OUTA|OUTA1", ("DAC port 1 IOUTB", "U201"): r"IOUT1B|OUTB1",
               ("DAC port 2 IOUTA", "U201"): r"IOUT2A|OUTA2", ("DAC port 2 IOUTB", "U201"): r"IOUT2B|OUTB2",
               ("Si5351 U301 CLK0", "U301"): r"SI_CLK0|CLK0", ("Si5351 U301 CLK1", "U301"): r"SI_CLK1|CLK1",
               ("Si5351 U301 CLK2", "U301"): r"SI_CLK2|CLK2",
               ("ADC clock A (from the FPGA)", "U103"): r"CLK_A", ("ADC clock B (from the FPGA)", "U103"): r"CLK_B",
               ("DAC CLK1 (from the FPGA)", "U201"): r"CLK1", ("DAC CLK2 (from the FPGA)", "U201"): r"CLK2"}
    for title, ref, pad in STARTS:
        if pad is None:
            pad = pad_of(ref, special[(title, ref)])
        print("\n## %s\n" % title)
        if pad is None or ref not in nets or pad not in nets[ref]:
            print("(no such pin: %s %s)" % (ref, pad))
            continue
        print("```")
        trace(ref, pad)
        print("```")
