#!/usr/bin/env python3
"""Generate the KiCad project: every schematic sheet, the project file, the
library tables and our own symbol/footprint libraries.

    python3 gen/gen.py            # write everything
    python3 gen/gen.py --render   # ...and plot each sheet to build/sch/*.png for review
"""
import os, sys, json, subprocess, shutil, glob, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import kisch, parts, fpga

NAME = "ECP5-2ADC-2DAC"
KICAD = os.environ.get("KICAD_APPIMAGE", os.path.expanduser("~/.local/bin/kicad-10.0.6-x86_64.AppImage"))
TITLE_COMPANY = "Jason Gallicchio and Claude -- https://github.com/gallicchio"
REV = "A"
DATE = "2026-10-02"

SHEETS = [  # (module, filename, title, paper, page)
    ("sheet_fpga", "fpga.kicad_sch", "FPGA, memory, clocks, configuration", "A1", 2),
    ("sheet_adc", "adc.kicad_sch", "ADC: two DC-coupled front ends, AD9238", "A2", 3),
    ("sheet_dac", "dac.kicad_sch", "DAC: AD9767 and two DC-coupled outputs", "A2", 4),
    ("sheet_eth", "ethernet.kicad_sch", "Gigabit Ethernet: RTL8211F, magnetics, RJ45", "A2", 5),
    ("sheet_usb", "usb.kicad_sch", "USB: FT2232H JTAG+serial, FPGA USB, HDMI, microSD", "A2", 6),
    ("sheet_power", "power.kicad_sch", "Power: 5 V USB in, 3.3/1.1/2.5 V, analog rails", "A2", 7),
]


def main():
    render = "--render" in sys.argv
    j = json.load(open(os.path.join(ROOT, "build", "fpga_pins.json")))
    ids = parts.define_symbols(j)
    root = kisch.Sch(NAME, NAME + ".kicad_sch", paper="A3", title="ECP5 + 2 ADC + 2 DAC: overview",
                     rev=REV, company=TITLE_COMPANY, comments=[DATE])
    sheets = []
    pins_by_sheet = {}
    for mod, fn, title, paper, page in SHEETS:
        box_uuid = kisch.uuid_for(NAME, "sheetbox", fn)
        s = kisch.Sch(NAME, fn, paper=paper, title=title, rev=REV, company=TITLE_COMPANY,
                      comments=[DATE], root=root.uuid, sheet_box_uuid=box_uuid)
        m = importlib.import_module(mod)
        hp = m.draw(s, ids, j)          # returns the hierarchical pins it exposes: [(name, shape)]
        pins_by_sheet[fn] = (s, title, page, hp)
        sheets.append(s)
    import sheet_root
    sheet_root.draw(root, pins_by_sheet, SHEETS)
    # the touch check must see the wires before finalize() turns them into text
    touch = []
    # a reference used twice (two parts, or one part's units on two sheets with
    # different symbols) is both an annotation error and a false net merge
    from collections import Counter
    seen = Counter()
    for s in sheets:
        for (x, y, ref, num, pw) in s.pinpts:
            if not ref.startswith("#"):
                seen[(ref, num, s.filename)] += 1
    for (ref, num, fn), n in sorted(seen.items()):
        if n > 1:
            touch.append("%s: DUPLICATE reference %s (pin %s placed %d times)" % (fn, ref, num, n))
    for s in [root] + sheets:
        for m in s.touches():
            touch.append("%s: %s" % (s.filename, m))
        for m in s.nets():
            touch.append("%s: %s" % (s.filename, m))
    # where every part sits on its sheet: the board generator groups passives
    # with the IC they were drawn beside
    pos = {}
    for s in sheets:
        for (x0, y0, x1, y1, ref) in s.items:
            if ref and not ref.startswith("#") and ":" not in ref:
                pos.setdefault(ref, (s.filename, round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2)))
    json.dump(pos, open(os.path.join(ROOT, "build", "sch_positions.json"), "w"), indent=0, sort_keys=True)
    lcsc = {}
    for s in sheets:
        lcsc.update(getattr(s, "lcsc", {}))
    json.dump(lcsc, open(os.path.join(ROOT, "build", "lcsc.json"), "w"), indent=0, sort_keys=True)
    # write
    for s in sheets:
        s.save(ROOT, is_root=False)
    root.save(ROOT, is_root=True)
    write_project(j)
    write_libs()
    msgs = []
    for s in [root] + sheets:
        for m in s.overlaps():
            msgs.append("%s: %s" % (s.filename, m))
    print("%d sheets written; %d accidental touches; %d layout complaints" % (len(sheets) + 1, len(touch), len(msgs)))
    for m in touch:
        print("  TOUCH", m)
    open(os.path.join(ROOT, "build", "sch_layout.txt"), "w").write("\n".join(msgs) + "\n")   # every complaint, for grepping
    if "--layout" in sys.argv:
        for m in msgs[:80]:
            print("   ", m)
    if render:
        plot()
    return 0


def write_project(j):
    pro = os.path.join(ROOT, NAME + ".kicad_pro")
    import rules
    rules.write_project(pro, NAME)


KFP = os.path.expanduser("~/.local/kicad10/AppDir/usr/share/kicad/footprints")


def write_footprints(lib):
    """The two footprints of our own, derived from library ones so nothing is hand-drawn:
    a 0402 whose courtyard is trimmed to 1.56 x 0.76 mm so it can sit on two adjacent 0.8 mm
    BGA ball vias, and LCSC's VBPW34S photodiode with pads 1 and 2 swapped so pad 1 is the
    cathode, as KiCad's D_Photo symbol (pin 1 = K) expects; the LCSC footprint and EasyEDA's own
    symbol for C145262 have pad 1 = anode."""
    import re
    out = os.path.join(lib, "ours.pretty")
    os.makedirs(out, exist_ok=True)
    src = open(os.path.join(KFP, "Capacitor_SMD.pretty", "C_0402_1005Metric.kicad_mod")).read()
    t = src.replace('(footprint "C_0402_1005Metric"', '(footprint "C_0402_1005Metric_BGA"', 1)
    t = t.replace("(start -0.91 -0.46)", "(start -0.78 -0.38)").replace("(end 0.91 0.46)", "(end 0.78 0.38)")
    assert "(start -0.78 -0.38)" in t and "(end 0.78 0.38)" in t
    t = t.replace('(descr "', '(descr "Courtyard trimmed to 1.56 x 0.76 mm so the capacitor can sit on two adjacent 0.8 mm BGA ball vias; ', 1)
    open(os.path.join(out, "C_0402_1005Metric_BGA.kicad_mod"), "w").write(t)
    src = open(os.path.join(ROOT, "library", "easyeda", "easyeda.pretty", "SENSOR-SMD_L4.4-W3.9.kicad_mod")).read()
    t = src.replace('(footprint "SENSOR-SMD_L4.4-W3.9"', '(footprint "VBPW34S_K1_A2"', 1)
    t = t.replace('(pad "1" smd rect', '(pad "X" smd rect', 1).replace('(pad "2" smd rect', '(pad "1" smd rect', 1).replace('(pad "X" smd rect', '(pad "2" smd rect', 1)
    assert t.count('(pad "1"') == 1 and t.count('(pad "2"') == 1
    t = t.replace("(center -3.25 1.95)", "(center 3.25 1.95)").replace("(end -3.22 1.95)", "(end 3.22 1.95)")
    t = re.sub(r'\(model "[^"]*"', '(model "${KIPRJMOD}/library/easyeda/easyeda.3dshapes/SENSOR-SMD_L4.4-W3.9.wrl"', t)
    open(os.path.join(out, "VBPW34S_K1_A2.kicad_mod"), "w").write(t)


def write_libs():
    """Our generated symbols into library/ours.kicad_sym, our two footprints, and the library tables."""
    lib = os.path.join(ROOT, "library")
    os.makedirs(lib, exist_ok=True)
    write_footprints(lib)
    syms = [lid for lid in kisch.SYMS._sym if lid.startswith("ours:")]
    out = ['(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor") (generator_version "9.0")']
    for lid in sorted(syms):
        node, _ = kisch.SYMS.get(lid)
        txt = kisch.ser(node, 1)
        out.append(txt)
    out.append(")")
    open(os.path.join(lib, "ours.kicad_sym"), "w").write("\n".join(out) + "\n")
    open(os.path.join(ROOT, "sym-lib-table"), "w").write(
        '(sym_lib_table\n  (version 7)\n'
        '  (lib (name "ours")(type "KiCad")(uri "${KIPRJMOD}/library/ours.kicad_sym")(options "")(descr "generated symbols"))\n'
        '  (lib (name "easyeda")(type "KiCad")(uri "${KIPRJMOD}/library/easyeda/easyeda.kicad_sym")(options "")(descr "LCSC parts via easyeda2kicad"))\n)\n')
    open(os.path.join(ROOT, "fp-lib-table"), "w").write(
        '(fp_lib_table\n  (version 7)\n'
        '  (lib (name "ours")(type "KiCad")(uri "${KIPRJMOD}/library/ours.pretty")(options "")(descr "our footprints"))\n'
        '  (lib (name "easyeda")(type "KiCad")(uri "${KIPRJMOD}/library/easyeda/easyeda.pretty")(options "")(descr "LCSC footprints via easyeda2kicad"))\n)\n')


def plot():
    out = os.path.join(ROOT, "build", "sch")
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(os.path.join(out, "*")):
        os.remove(f)
    r = subprocess.run([KICAD, "kicad-cli", "sch", "export", "svg", "-o", out, "--no-background-color",
                        os.path.join(ROOT, NAME + ".kicad_sch")], capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
    for svg in sorted(glob.glob(os.path.join(out, "*.svg"))):
        png = svg[:-4] + ".png"
        subprocess.run(["inkscape", svg, "--export-type=png", "--export-width=4000",
                        "--export-background=white", "-o", png], capture_output=True)
    print("plotted:", [os.path.basename(p) for p in sorted(glob.glob(os.path.join(out, "*.png")))])


if __name__ == "__main__":
    sys.exit(main())
