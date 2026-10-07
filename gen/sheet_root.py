"""The root sheet: a block diagram.  One box per sheet, the FPGA in the middle,
every hierarchical pin wired (bus or wire) to its partner on the other sheet."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kisch


def draw(root, pins_by_sheet, SHEETS):
    s = root
    s.text(15, 18, "ECP5 + 2 ADC + 2 DAC  --  block diagram (rev A, 2026-10-04)", size=3.5, bold=True)
    s.text(15, 24, "Each box is a sheet; every signal that crosses between sheets is drawn here as a wire or a bus. "
                   "Power rails (+5V, +3V3, +1V1, +2V5, +3V3_ADC, +3V3_DAC, +5VA, -4V2, ...) are global power symbols.", size=1.2)
    byfile = {fn: (sch, title, page, hp) for fn, (sch, title, page, hp) in pins_by_sheet.items()}
    fpga = byfile["fpga.kicad_sch"]
    fnames = {n for n, _ in fpga[3]}
    # which sheet owns the partner of each FPGA pin
    partner = {}
    for fn, (sch, title, page, hp) in byfile.items():
        if fn == "fpga.kicad_sch":
            continue
        for n, sh in hp:
            if n in fnames:
                partner[n] = fn
    missing = [n for n in fnames if n not in partner]
    if missing:
        print("ROOT: FPGA pins without a partner sheet:", missing)
    left_sheets = ["adc.kicad_sch", "dac.kicad_sch"]
    right_sheets = ["ethernet.kicad_sch", "usb.kicad_sch"]

    def inv_shape(sh):
        return {"input": "output", "output": "input"}.get(sh, sh)

    fshape = dict(fpga[3])
    # FPGA box
    xf, yf, wf = 165.0, 40.0, 80.0
    left_pins, right_pins = [], []
    for fn in left_sheets:
        for n, sh in byfile[fn][3]:
            if n in fnames:
                left_pins.append((n, fn))
    for fn in right_sheets:
        for n, sh in byfile[fn][3]:
            if n in fnames:
                right_pins.append((n, fn))
    # pins in sheet order down each side, with a gap between sheets so the
    # peripheral boxes (one per sheet, drawn around their pins) do not overlap
    pins = []
    ypos = {}
    hf = 0.0
    for side, lst in (("l", left_pins), ("r", right_pins)):
        off = 5.08
        last = None
        for n, fn in lst:
            if last is not None and fn != last:
                off += 17.78                 # (a box's "File:" line and the next box's name both live in this gap)
            pins.append((n, fshape[n], side, off)); ypos[n] = yf + off
            off += 2.54
            last = fn
        hf = max(hf, off + 5.08)
    _, fpos = s.sheet(xf, yf, wf, hf, "FPGA, memory, clocks, configuration", "fpga.kicad_sch", fpga[2], pins)
    # peripheral boxes, pins aligned with the FPGA's
    for side, sheets_ in (("l", left_sheets), ("r", right_sheets)):
        for fn in sheets_:
            sch, title, page, hp = byfile[fn]
            own = [(n, sh) for n, sh in hp if n in fnames]
            if not own:
                continue
            ys = [ypos[n] for n, _ in own]
            top = min(ys) - 5.08
            h = max(ys) - top + 5.08
            x = 45.0 if side == "l" else 285.0
            w = 70.0
            ps = [(n, sh, "r" if side == "l" else "l", ypos[n] - top) for n, sh in own]
            extra = [(n, sh) for n, sh in hp if n not in fnames]
            for k, (n, sh) in enumerate(extra):
                ps.append((n, sh, "b", 10.16 + k * 5.08))
            _, ppos = s.sheet(x, top, w, h, title.split(":")[0], fn, page, ps)
            if fn == "usb.kicad_sch":
                vb = ppos["VBUS"]
                s.wire(vb[0], vb[1], vb[0], vb[1] + 30.0)
                byfile["_vbus"] = (vb[0], vb[1] + 30.0)
            for n, sh in own:
                a, b = ppos[n], fpos[n]
                if "[" in n:
                    s.bus(a, b)
                else:
                    s.wire(a[0], a[1], b[0], b[1])
    # power sheet: below the USB box, VBUS wired up to it
    usb = byfile["usb.kicad_sch"]
    uy = max(ypos[n] for n, _ in usb[3] if n in fnames) + 5.08
    vb = byfile["_vbus"]
    px, py = vb[0] - 10.16, vb[1]
    _, ppos = s.sheet(px, py, 70.0, 25.4, "Power", "power.kicad_sch", byfile["power.kicad_sch"][2], [("VBUS", "input", "t", 10.16)])
    vp = ppos["VBUS"]
    if vp != vb:
        s.wire(vb[0], vb[1], vp[0], vp[1])
    # the USB box's VBUS pin: add it as a bottom pin -- redraw: easier to give the USB sheet box a bottom pin
    # (the USB sheet box was drawn above without VBUS; so draw VBUS from the FPGA-aligned USB box bottom edge)
    return
