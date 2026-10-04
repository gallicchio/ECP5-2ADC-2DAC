"""The ADC sheet: two identical DC-coupled front ends into the AD9238.

Signal flows left to right: SMA -> termination jumper / clamp / source jumper
-> x1/x10 preamp -> x1/x10 preamp -> fully differential driver -> RC -> ADC.
Channel A on the upper half, channel B on the lower half, the converter
between them, its digital ports on the right going out on buses to the FPGA
sheet.  The noise-source block and the photodiode receiver sit along the
bottom.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from draw import *


def channel(ctx, tag, cl, base, alt_name, ids):
    """One front end on centre line y=cl.  Returns dict of key nodes."""
    s = ctx.s
    n = base // 100
    # --- SMA, termination, protection -----------------------------------
    j = part(ctx, ids["sma"], "J%d" % (100 + n), "SMA", "SMA", 30.48, cl, desc="ADC %s input, DC coupled" % tag,
             ref_at=(25.0, cl - 6.0), val_at=(25.0, cl + 4.0))
    n0 = j.pin(1)
    gnd(ctx, *j.pin(2), stub=2.54)
    s.text(21.0, cl - 10.0, "ADC %s IN" % tag, size=1.8, bold=True)
    s.text(21.0, cl - 14.5, "±1 V MAX IN", size=2.2, bold=True)
    s.text(21.0, cl + 15.5, "±1 V full scale at x1 (±0.1 V at x10)\n50 Ω or high-Z (JP%d)\nDC coupled; clamps at the rails (+5, -4.2 V)\n±10 V max (100 Ω 1206, 0.25 W)" % (base + 1), size=0.9, justify="left top")
    xt = 45.72
    s.wire(n0[0], cl, xt, cl)
    rt = R(ctx, base, "49.9R", xt, cl + 6.35)
    s.wire(xt, cl, *rt.pin(1))
    jt = part(ctx, "Jumper:Jumper_2_Open", "JP%d" % (base + 1), "TERM", "H1x2", xt, cl + 16.51, rot=90,
              ref_at=(xt + 3.0, cl + 15.5), val_at=(xt + 3.0, cl + 16.0))
    a, b = jt.pin(1), jt.pin(2)
    top, bot = (a, b) if a[1] < b[1] else (b, a)
    s.wire(*rt.pin(2), *top)
    gnd(ctx, *bot, stub=2.54)
    label_node(ctx, xt + 3.0, cl + 22.0, "shunt in = 50 Ω", side="right", size=0.9)
    rs = R(ctx, base, "100R", 57.15, cl, horiz=True, fp="R1206")          # 1206: 0.25 W, so a ±10 V source into the clamp (43 mA, 0.18 W) does not open it
    s.wire(xt, cl, *rs.pin(1))
    xc = 68.58
    s.wire(*rs.pin(2), xc, cl)
    d = part(ctx, "Diode:BAV99", "D%d" % (100 + n), "BAV99", "SOT23", xc, cl - 8.89, rot=0,
             ref_at=(xc - 4.0, cl - 12.5), val_at=(xc + 1.0, cl - 12.5))
    s.wire(*d.pin(3), xc, cl)                       # common pin on the signal
    s.wire(*d.pin(1), d.pin(1)[0] - 2.54, d.pin(1)[1]); gnd(ctx, d.pin(1)[0] - 2.54, d.pin(1)[1], "-4V2", stub=3.81, up=True)
    s.wire(*d.pin(2), d.pin(2)[0] + 2.54, d.pin(2)[1]); rail(ctx, d.pin(2)[0] + 2.54, d.pin(2)[1], "+5VA", stub=3.81)
    label_node(ctx, xc + 6.0, cl - 10.5, "clamps to\nthe rails", side="right", size=0.85)
    # --- source select: B (top) = SMA, A (bottom) = alternate, C (right) = to the preamp ---
    xj = 81.28
    jsrc = part(ctx, "Jumper:Jumper_3_Open", "JP%d" % (base + 2), "SRC", "H1x3", xj, cl, rot=90,
                ref_at=(xj - 1.5, cl + 9.0), val_at=(xj - 1.5, cl + 9.5), justify="right")
    pa, pb, pc = jsrc.pin(1), jsrc.pin(3), jsrc.pin(2)
    # up to the jumper's SMA pin on a jog clear of the clamp above the node
    s.junction(xc, cl)
    s.wire(xc, cl, xc + 8.89, cl); s.wire(xc + 8.89, cl, xc + 8.89, pb[1]); s.wire(xc + 8.89, pb[1], *pb)
    label_node(ctx, xj + 1.0, pb[1] - 0.3, "SMA", side="right", size=0.85)
    label_node(ctx, xj + 1.0, pa[1] + 1.4, alt_name, side="right", size=0.85)
    alt = (xj, pa[1] + 2.54)
    s.wire(*pa, *alt)
    nin = pc
    # --- preamp stages: OPA1612, non-inverting, x1 or x10 by jumper -----------
    x1 = 106.68
    u = "U%d" % (100 + n)
    prev = nin
    for st, (x0, unit) in enumerate([(x1, 1), (x1 + 45.72, 2)], 1):
        a_ = part(ctx, ids["opa1612"], u, "OPA1612", "SOIC8", x0, cl, unit=unit,
                  ref_at=(x0 - 5.5, cl - 6.0), val_at=(x0 - 1.0, cl - 8.3))
        pp = a_.pin("3" if unit == 1 else "5"); pn = a_.pin("2" if unit == 1 else "6"); po = a_.pin("1" if unit == 1 else "7")
        s.wire(prev[0], prev[1], pp[0] - 2.54, prev[1]); s.wire(pp[0] - 2.54, prev[1], pp[0] - 2.54, pp[1]); s.wire(pp[0] - 2.54, pp[1], *pp)
        yf = cl + 11.43
        rf = R(ctx, base, "9.1k", x0, yf, horiz=True)
        s.wire(*po, po[0] + 2.54, po[1]); s.wire(po[0] + 2.54, po[1], po[0] + 2.54, yf); s.wire(po[0] + 2.54, yf, *rf.pin(2))
        xn = pn[0] - 2.54
        s.wire(*rf.pin(1), xn, yf); s.wire(xn, yf, xn, pn[1]); s.wire(xn, pn[1], *pn)
        rg = R(ctx, base, "1k", xn, yf + 6.35, side="left")
        s.wire(xn, yf, *rg.pin(1)); gnd(ctx, *rg.pin(2), stub=2.54)
        jg = part(ctx, "Jumper:Jumper_2_Open", "JP%d" % (base + 2 + st), "GAIN", "H1x2", x0, yf + 7.62, rot=0,
                  ref_at=(x0 + 6.0, yf + 7.0), val_at=(x0 + 6.0, yf + 7.5))
        ja, jb = jg.pin(1), jg.pin(2)
        s.wire(*ja, rf.pin(1)[0] - 1.27, ja[1]); s.wire(rf.pin(1)[0] - 1.27, ja[1], rf.pin(1)[0] - 1.27, yf)
        s.wire(*jb, rf.pin(2)[0] + 1.27, jb[1]); s.wire(rf.pin(2)[0] + 1.27, jb[1], rf.pin(2)[0] + 1.27, yf)
        label_node(ctx, x0 - 4.0, yf + 19.0, "shunt: x1   open: x10", side="right", size=0.85)      # (5.5 mm lower since build 27: on the row above it sat on C1101's labels)
        prev = (po[0] + 2.54, cl)
        s.wire(po[0] + 2.54, cl, po[0] + 6.35, cl)
        prev = (po[0] + 6.35, cl)
    # monitor tap (build 26): 49.9 R into a U.FL at the second stage's output, so a scope sees the preamp
    # chain without a probe: a 50 R input sees half the signal, a 1 MR input (ADALM2000) all of it
    xtp = prev[0]
    s.junction(xtp, cl)
    rtp = R(ctx, base, "49.9R", xtp, cl + 7.62, side="left", ref="R%d" % (1000 + base + 13))      # explicit: the strip's R1..R12 keep their numbers
    s.wire(xtp, cl, *rtp.pin(1))
    jtp = part(ctx, ids["ufl"], "J%d" % (106 + n), "U.FL", "UFL", xtp + 7.62, cl + 15.24,
               ref_at=(xtp + 10.0, cl + 13.5), val_at=(xtp + 10.0, cl + 15.5), desc="monitor tap: preamp output, through 49.9 R")
    s.wire(*rtp.pin(2), xtp, cl + 15.24); s.wire(xtp, cl + 15.24, *jtp.pin(1))
    gnd(ctx, *jtp.pin(2), stub=2.54)
    s.text(xtp + 15.0, cl + 20.5, "TAP %s: preamp out, 49.9 Ω to a U.FL" % tag, size=0.85)      # (two lines right of the +5VA flag since build 27: one line ran through its stem)
    s.text(xtp + 15.0, cl + 22.5, "(50 Ω scope: x1/2)", size=0.85)
    # power unit of the OPA1612 (unit 3)
    xpw = x1 + 45.72 + 27.94
    pw = part(ctx, ids["opa1612"], u, "OPA1612", "SOIC8", xpw, cl + 33.02, unit=3,
              ref_at=(xpw + 6.0, cl + 32.0), val_at=(xpw + 6.0, cl + 33.0))
    rail(ctx, *pw.pin("8"), "+5VA", stub=3.81); gnd(ctx, *pw.pin("4"), "-4V2", stub=3.81)
    c1 = C(ctx, base, "100nF", xpw - 12.7, pw.pin("8")[1] - 3.81 + 3.81, side="left")
    s.wire(pw.pin("8")[0], pw.pin("8")[1] - 3.81, xpw - 12.7, pw.pin("8")[1] - 3.81); s.wire(xpw - 12.7, pw.pin("8")[1] - 3.81, *c1.pin(1))
    gnd(ctx, *c1.pin(2), stub=0)
    c2 = C(ctx, base, "100nF", xpw - 22.86, pw.pin("4")[1] + 3.81 - 3.81, side="left")
    s.wire(pw.pin("4")[0], pw.pin("4")[1] + 3.81, xpw - 22.86, pw.pin("4")[1] + 3.81); s.wire(xpw - 22.86, pw.pin("4")[1] + 3.81, *c2.pin(2))
    gnd(ctx, *c2.pin(1), stub=0, up=True)
    label_node(ctx, xpw - 26.0, cl + 47.5, "one 100 nF per supply pin, at the pin", side="right", size=0.85)
    # --- FDA: THS4521, gain 1, single-ended in, differential out ------------
    xf = 223.52
    f = part(ctx, ids["fda"], "U%d" % (110 + n), "THS4521", "MSOP8", xf, cl,
             ref_at=(xf + 5.5, cl - 11.0), val_at=(xf + 5.5, cl - 10.5))
    ip, im = f.pin("8"), f.pin("1")
    on, op = f.pin("5"), f.pin("4")        # THS4521: pin 4 is VOUT+, pin 5 VOUT- (datasheet); the symbol draws OUT- level with IN+
    rg1 = R(ctx, base, "499R", ip[0] - 8.89, ip[1], horiz=True, ref_at=(ip[0] - 16.0, ip[1] - 1.6), val_at=(ip[0] - 16.0, ip[1] + 1.3))   # labels west: the clamp's designator sits between the rows
    s.wire(prev[0], cl, prev[0] + 2.54, cl); s.wire(prev[0] + 2.54, cl, prev[0] + 2.54, ip[1]); s.wire(prev[0] + 2.54, ip[1], *rg1.pin(1))
    rg2 = R(ctx, base, "499R", im[0] - 8.89, im[1], horiz=True, ref_at=(ip[0] - 16.0, im[1] - 1.6), val_at=(ip[0] - 16.0, im[1] + 1.3))
    s.wire(*rg2.pin(1), rg2.pin(1)[0] - 2.54, im[1]); gnd(ctx, rg2.pin(1)[0] - 2.54, im[1], stub=2.54)
    # a BAV99 anti-parallel across the two inputs (its common pin 3 on IN+, pins 1 and 2 on IN-): whatever a
    # saturated preamp (-4.2 V through 499 Ω) makes the amplifier do, the differential input stays under one
    # diode drop (abs max 1 V); in use the inputs are within millivolts, the diodes carry nanoamps (reviews, R1).
    # Drawn as its two diodes (one unit each) standing between the two input rows; the rows are split at their
    # pins so every pin lands on a wire END.
    xd = ip[0] - 2.54                                           # pin 3 on the feedback's junction, pins 1/2 either side of it on the lower row
    dq = part(ctx, ids["ap_diode"], "D%d" % (110 + n), "BAV99", "SOT23", xd, cl, rot=0,
              ref_at=(xd - 2.4, cl + 0.5), val_at=(xd - 2.4, cl + 0.5), hide_value=True, justify="right", fsize=1.0)
    ends = {}
    for pn in ("1", "2", "3"):
        q = dq.pin(pn)
        row = ip if q[1] < cl else im                         # pin 3 on the IN+ row (upper), pins 1 and 2 on IN- (lower)
        if abs(q[1] - row[1]) > 0.01:
            s.wire(q[0], q[1], q[0], row[1])
        ends.setdefault(row, []).append(q[0])
    for row, src in ((ip, rg1.pin(2)), (im, rg2.pin(2))):
        xs_ = sorted(set(round(x, 3) for x in ends[row] + [ip[0] - 2.54]))      # the feedback resistors' junctions split the rows too
        pts = [src[0]] + xs_ + [row[0]]
        for a_, b_ in zip(pts, pts[1:]):
            s.wire(a_, row[1], b_, row[1])
        for x_ in xs_:
            if abs(x_ - (ip[0] - 2.54)) > 0.01:
                s.junction(x_, row[1])                              # (the feedback code adds its own junction there)
    label_node(ctx, xd - 24.0, cl - 29.5, "D%d: a BAV99 anti-parallel across the FDA's inputs keeps them within one diode drop in any overload" % (110 + n), side="right", size=0.8)
    yfa, yfb = cl - 25.4, cl + 25.4
    rfa = R(ctx, base, "499R", xf, yfa, horiz=True)
    s.junction(ip[0] - 2.54, ip[1]); s.wire(ip[0] - 2.54, ip[1], ip[0] - 2.54, yfa); s.wire(ip[0] - 2.54, yfa, *rfa.pin(1))
    s.wire(*rfa.pin(2), on[0] + 2.54, yfa); s.wire(on[0] + 2.54, yfa, on[0] + 2.54, on[1]); s.wire(*on, on[0] + 2.54, on[1])
    rfb = R(ctx, base, "499R", xf, yfb, horiz=True)
    s.junction(im[0] - 2.54, im[1]); s.wire(im[0] - 2.54, im[1], im[0] - 2.54, yfb); s.wire(im[0] - 2.54, yfb, *rfb.pin(1))
    s.wire(*rfb.pin(2), op[0] + 2.54, yfb); s.wire(op[0] + 2.54, yfb, op[0] + 2.54, op[1]); s.wire(*op, op[0] + 2.54, op[1])
    label_node(ctx, xf + 9.0, yfa - 1.8, "gain = 499/499 = 1", side="right", size=0.85)
    vocm, pd, vsp, vsn = f.pin("2"), f.pin("7"), f.pin("3"), f.pin("6")
    cv = C(ctx, base, "100nF", xf + 7.62, cl + 20.32, side="left")
    s.wire(*vocm, vocm[0], cl + 16.51); s.wire(vocm[0], cl + 16.51, xf + 7.62, cl + 16.51); s.wire(xf + 7.62, cl + 16.51, *cv.pin(1))
    gnd(ctx, *cv.pin(2), stub=0)
    label_node(ctx, vocm[0] - 24.0, yfb + 5.5, "VOCM open = 1.65 V (internal divider)", side="right", size=0.85)
    s.wire(*pd, pd[0], pd[1] + 2.54); s.wire(pd[0], pd[1] + 2.54, pd[0] + 6.35, pd[1] + 2.54); rail(ctx, pd[0] + 6.35, pd[1] + 2.54, "+3V3_ADC", stub=0)
    rail(ctx, *vsp, "+3V3_ADC", stub=3.81); s.wire(*vsn, vsn[0], vsn[1] + 2.54); gnd(ctx, vsn[0], vsn[1] + 2.54, stub=0)
    cs = C(ctx, base, "100nF", vsp[0] + 12.7, vsp[1] - 3.81 - 3.81, side="right")
    s.wire(vsp[0], vsp[1] - 3.81, vsp[0] + 12.7, vsp[1] - 3.81); s.wire(vsp[0] + 12.7, vsp[1] - 3.81, *cs.pin(2)); gnd(ctx, *cs.pin(1), stub=0, up=True)
    # --- series R and shunt C into the converter ------------------------------
    xr = on[0] + 2.54 + 8.89
    ra = R(ctx, base, "33R", xr, on[1], horiz=True, ref_at=(xr - 2.6, on[1] - 1.6), val_at=(xr + 4.5, on[1] - 1.6))
    rb = R(ctx, base, "33R", xr, op[1], horiz=True, ref_at=(xr - 2.6, op[1] + 3.4), val_at=(xr + 4.5, op[1] + 1.6))
    s.wire(on[0] + 2.54, on[1], *ra.pin(1)); s.wire(op[0] + 2.54, op[1], *rb.pin(1))
    xo = xr + 8.89
    s.wire(*ra.pin(2), xo, on[1]); s.wire(*rb.pin(2), xo, op[1])
    ca = C(ctx, base, "22pF", xo, on[1] - 6.35, side="right"); s.wire(xo, on[1], *ca.pin(2)); gnd(ctx, *ca.pin(1), stub=1.27, up=True)
    cb = C(ctx, base, "22pF", xo, op[1] + 6.35, side="right"); s.wire(xo, op[1], *cb.pin(1)); gnd(ctx, *cb.pin(2), stub=1.27)
    label_node(ctx, xo + 2.0, (on[1] + op[1]) / 2 + 0.6, "2 Vpp differential, 1.65 V common mode", side="right", size=0.85)
    return dict(alt=alt, out_n=(xo, on[1]), out_p=(xo, op[1]), xo=xo)


def draw(sch, ids, fpga):
    ctx = Ctx(sch, "ADC")
    s = sch
    s.text(20, 22, "ADC: two DC-coupled 12-bit channels, AD9238, 65 MSPS", size=3.0, bold=True)
    note(ctx, 20, 26, "Each channel: SMA (50 Ω or high-Z, jumper) -> 100 Ω + diode clamp to the ±4.5 V rails -> "
                      "source jumper (SMA / noise resistor / photodiode) -> two OPA1612 stages, each x1 or x10 "
                      "by jumper (so x1, x10, x100; 1.1 nV/√Hz) -> U.FL monitor tap -> THS4521 fully-differential driver at gain 1 (a BAV99 "
                      "across its inputs keeps an overload under its 1 V differential limit) "
                      "-> 33 Ω + 22 pF -> AD9238 (2 Vpp differential about 1.65 V = AVDD/2; -3 dB at 23 MHz at x1, sim/adc_frontend.cir). The ADC's internal "
                      "1.0 V reference sets the 2 Vpp span (SENSE = GND); SHARED_REF ties both channels to one "
                      "reference so their gains match for the cross-correlation experiment. Both sample clocks "
                      "come from the FPGA so the gateware owns the phase.", w=340, size=1.1)
    clA, clB = 78.74, 215.9
    A = channel(ctx, "A", clA, 100, "NOISE", ids)
    B = channel(ctx, "B", clB, 200, "ALT", ids)

    # --- the converter: one trapezoid per channel, in line with its own front
    # end (VIN- on the FDA's upper output row, VIN+ on the lower: straight
    # wires, nothing crosses), the pins both channels share in a box between
    # them, and a dashed box round the three to say they are one chip. ------
    xa = 340.36
    LIB = ids["adc"]
    units = {}
    hp = []
    for unit, ch, tagc, (vp, vn, clk), data, (otr, pdwn, oeb) in (
            (1, A, "A", ("2", "3", "63"), [57, 56, 55, 54, 51, 50, 49, 48, 47, 46, 45, 44], ("58", "60", "59")),
            (2, B, "B", ("15", "14", "18"), [38, 37, 36, 35, 34, 33, 32, 31, 30, 27, 26, 25], ("39", "21", "22"))):
        yu = ch["out_n"][1] - pin_dy(LIB, unit, vn)
        tu = part(ctx, LIB, "U103", "AD9238", "LQFP64_7", xa, yu, unit=unit,
                  ref_at=(xa - 20.0, yu - 24.0), val_at=(xa - 20.0, yu + 31.5))
        units[tagc] = tu
        s.wire(*ch["out_n"], *tu.pin(vn)); s.wire(*ch["out_p"], *tu.pin(vp))
        p = tu.pin(clk)
        r = R(ctx, 300, "33R", p[0] - 8.89, p[1], horiz=True, ref_at=(p[0] - 11.5, p[1] - 1.6), val_at=(p[0] - 4.4, p[1] - 1.6))
        s.wire(*r.pin(2), *p)
        s.wire(*r.pin(1), r.pin(1)[0] - 7.62, p[1]); s.hlabel(r.pin(1)[0] - 7.62, p[1], "ADC_%s_CLK" % tagc, shape="input", rot=180)
        label_node(ctx, p[0] - 34.0, p[1] + 4.6, "sample clock from the FPGA (the gateware owns the phase)", side="right", size=0.85)
        members = [(tu.pin(str(d))[0], tu.pin(str(d))[1], "ADC_%s_D%d" % (tagc, 11 - i)) for i, d in enumerate(data)]
        xb = tu.pin(str(data[0]))[0] + 38.1
        bus_out(ctx, xb, 0, "ADC_%s_D[11..0]" % tagc, members, x_end=xb + 22.86)
        hp.append(("ADC_%s_D[11..0]" % tagc, "output"))
        p = tu.pin(otr); s.wire(*p, p[0] + 5.08, p[1]); s.hlabel(p[0] + 5.08, p[1], "ADC_%s_OTR" % tagc, shape="output")
        hp.append(("ADC_%s_OTR" % tagc, "output"))
        p = tu.pin(pdwn); s.wire(*p, p[0] + 5.08, p[1]); s.hlabel(p[0] + 5.08, p[1], "ADC_PDWN_%s" % tagc, shape="input")
        hp.append(("ADC_PDWN_%s" % tagc, "input"))
        p = tu.pin(oeb); s.wire(*p, p[0] + 3.81, p[1]); gnd(ctx, p[0] + 3.81, p[1], stub=2.54)
        label_node(ctx, p[0] + 6.0, p[1] - 0.3, "outputs always enabled", side="right", size=0.85)
    hp += [("ADC_A_CLK", "input"), ("ADC_B_CLK", "input"), ("ADC_DCS", "input"), ("ADC_DFS", "input")]

    # the shared pins, between the channels
    ym = snap((units["A"].y + units["B"].y) / 2.0)
    cu = part(ctx, LIB, "U103", "AD9238", "LQFP64_7", xa, ym, unit=3,
              ref_at=(xa - 20.0, ym - 20.0), val_at=(xa - 20.0, ym + 21.5))
    # references: spread each REFT/REFB pair into two bars 10 mm apart
    xr = xa + 24.13
    for (pt, pb, base) in (("6", "7", 310), ("11", "10", 320)):
        rt, rb = cu.pin(pt), cu.pin(pb)
        yT, yB = rt[1] - 3.81, rb[1] + 3.81
        s.wire(*rt, xr - 2.54, rt[1]); s.wire(xr - 2.54, rt[1], xr - 2.54, yT); s.wire(xr - 2.54, yT, xr + 30.48, yT)
        s.wire(*rb, xr, rb[1]); s.wire(xr, rb[1], xr, yB); s.wire(xr, yB, xr + 40.64, yB)
        c10 = C(ctx, base, "10uF", xr + 7.62, (yT + yB) / 2, fp="C0603", side="right")
        s.wire(xr + 7.62, yT, *c10.pin(1)); s.wire(*c10.pin(2), xr + 7.62, yB)
        c1 = C(ctx, base, "100nF", xr + 17.78, (yT + yB) / 2, side="right")
        s.wire(xr + 17.78, yT, *c1.pin(1)); s.wire(*c1.pin(2), xr + 17.78, yB)
        ct = C(ctx, base, "100nF", xr + 30.48, yT - 5.08, side="right"); s.wire(xr + 30.48, yT, *ct.pin(2)); gnd(ctx, *ct.pin(1), stub=0, up=True)
        cb = C(ctx, base, "100nF", xr + 40.64, yB + 5.08, side="right"); s.wire(xr + 40.64, yB, *cb.pin(1)); gnd(ctx, *cb.pin(2), stub=0)
        label_node(ctx, xr + 44.0, (yT + yB) / 2 + 0.5, "reference pair, decoupled as the datasheet draws it", side="right", size=0.8)
    vref = cu.pin("8")
    s.wire(*vref, xr + 30.48, vref[1])
    cv1 = C(ctx, 330, "1uF", xr + 20.32, vref[1] + 5.08, side="right"); s.wire(xr + 20.32, vref[1], *cv1.pin(1)); gnd(ctx, *cv1.pin(2), stub=0)
    cv2 = C(ctx, 330, "100nF", xr + 30.48, vref[1] + 5.08, side="right"); s.wire(xr + 30.48, vref[1], *cv2.pin(1)); gnd(ctx, *cv2.pin(2), stub=0)
    label_node(ctx, xr + 37.0, vref[1] + 0.5, "1.0 V internal reference -> 2 Vpp span", side="right", size=0.85)
    # the mode pins, on the left: SENSE to ground, SHARED_REF and MUX_SELECT high, DCS/DFS from the FPGA
    sense, shared, mux, dcs, dfs = (cu.pin(n) for n in ("9", "62", "61", "19", "20"))
    s.wire(*sense, sense[0] - 6.35, sense[1]); gnd(ctx, sense[0] - 6.35, sense[1], stub=2.54)
    s.text(sense[0] - 12.0, sense[1] - 2.0, "SENSE = GND selects the internal 1.0 V reference", size=0.85, justify="right bottom")
    xs2 = shared[0] - 2.54
    s.wire(*shared, xs2, shared[1]); s.wire(xs2, shared[1], xs2, mux[1]); s.wire(*mux, xs2, mux[1]); s.junction(xs2, shared[1])
    s.wire(xs2, shared[1], xs2 - 12.7, shared[1]); rail(ctx, xs2 - 12.7, shared[1], "+3V3_ADC", stub=3.81)
    s.text(xs2 - 16.0, mux[1] + 0.5, "both high: one reference for both channels,\ntwo separate output ports", size=0.85, justify="right bottom")
    for p, nm in ((dcs, "ADC_DCS"), (dfs, "ADC_DFS")):
        s.wire(*p, p[0] - 7.62, p[1]); s.hlabel(p[0] - 7.62, p[1], nm, shape="input", rot=180)
    s.text(dfs[0] - 30.0, dfs[1] + 4.0, "from the FPGA: DCS = duty-cycle stabiliser (only above 20 MSPS),\nDFS = 0 offset binary / 1 two's complement", size=0.85, justify="right bottom")
    for nn in ("23", "24", "42", "43"):
        s.nc(*cu.pin(nn))
    # supplies on top, grounds underneath
    avdd = [cu.pin(n) for n in ("5", "12", "17", "64")]
    drv = [cu.pin(n) for n in ("29", "41", "52")]
    ya = avdd[0][1] - 5.08
    for p in avdd:
        s.wire(*p, p[0], ya)
    s.wire(avdd[0][0], ya, avdd[-1][0], ya)
    rail(ctx, avdd[0][0], ya, "+3V3_ADC", stub=7.62)
    yd = drv[0][1] - 5.08
    for p in drv:
        s.wire(*p, p[0], yd)
    s.wire(drv[0][0], yd, drv[-1][0], yd)
    rail(ctx, drv[-1][0], yd, "+3V3_DRV", stub=7.62)
    for p in [cu.pin(n) for n in ("1", "4", "13", "16", "28", "40", "53")]:
        s.wire(*p, p[0], p[1] + 2.54)
    yg = cu.pin("1")[1] + 2.54
    s.wire(cu.pin("1")[0], yg, cu.pin("53")[0], yg); gnd(ctx, cu.pin("53")[0], yg, stub=2.54)
    # the dashed box: three units, one chip
    gx0, gx1 = xa - 22.86, xa + 22.86
    gy0 = units["A"].y - 26.67 - 3.0
    gy1 = units["B"].y + 26.67 + 3.0
    s.rect(gx0, gy0, gx1 - gx0, gy1 - gy0, style="dash", width=0.25)
    s.text(gx0 + 2.0, gy0 - 1.0, "U103 AD9238: one chip, drawn as its two channels (trapezoids) and the pins they share (box)", size=1.0, bold=True)

    decouple(ctx, 340, 400.0, 272.0, "+3V3_ADC", ["10uF", "100nF", "100nF", "100nF", "100nF"], label="AVDD: one 100 nF per pin, at the pin")
    decouple(ctx, 350, 400.0, 298.0, "+3V3_DRV", ["10uF", "100nF", "100nF", "100nF"], label="DRVDD: +3V3 through a ferrite (power sheet)")
    note(ctx, 400.0, 318.0, "Grounds: AGND and DRGND are one plane on this board. The converter sits on the "
                            "analog side of the floorplan with the FPGA's bus the only digital thing near it.", w=110, size=0.95)

    # --- noise source block, bottom left -----------------------------------------
    y0 = 300.0
    s.text(20, y0 - 4, "Johnson-noise source (either channel can select it)", size=1.6, bold=True)
    note(ctx, 20, y0, "A resistor at room temperature makes √(4kTR) of noise: 1.3 nV/√Hz at 100 Ω, 12.9 nV/√Hz at 10 kΩ. "
                      "Switch one in (DIP) or plug your own into J5. With both channels on the same resistor, "
                      "the cross-spectrum averages away each amplifier's own noise and leaves the resistor's. "
                      "Switch 0 Ω in to measure the amplifiers alone.", w=108, size=0.95)
    sw = part(ctx, "Switch:SW_DIP_x04", "SW101", "DSWB04LHGET", "DIP4", 86.36, y0 + 45.72,
              ref_at=(78.0, y0 + 37.5), val_at=(78.0, y0 + 54.5))
    vals = ["0R", "100R", "1k", "10k"]
    ybar = sw.pin("1")[1] - 12.7
    rxs = []
    for i, v in enumerate(vals):
        pl = sw.pin(str(i + 1)); pr = sw.pin(str(8 - i))
        rx = pl[0] - 3.81 - i * 10.16
        rxs.append(rx)
        r = R(ctx, 400, v, rx, ybar + 5.08, side="left")
        s.wire(rx, ybar, *r.pin(1)); s.wire(*r.pin(2), rx, pl[1]); s.wire(rx, pl[1], *pl)
        s.wire(*pr, pr[0] + 2.54, pr[1])
    xn = min(rxs) - 6.35
    s.wire(xn, ybar, max(rxs), ybar)
    s.wire(sw.pin("8")[0] + 2.54, sw.pin("8")[1], sw.pin("8")[0] + 2.54, sw.pin("5")[1]); gnd(ctx, sw.pin("8")[0] + 2.54, sw.pin("5")[1], stub=2.54)
    jn = part(ctx, "Connector_Generic:Conn_01x02", "J105", "NOISE", "H1x2", xn - 10.16, y0 + 58.42, rot=180,
              ref_at=(xn - 20.0, y0 + 55.0), val_at=(xn - 20.0, y0 + 59.5))
    n1, n2 = jn.pin(1), jn.pin(2)
    hi, lo = (n1, n2) if n1[1] < n2[1] else (n2, n1)
    s.wire(*hi, xn, hi[1]); s.wire(xn, ybar, xn, hi[1]); gnd(ctx, *lo, stub=2.54)
    label_node(ctx, xn - 12.0, lo[1] + 9.5, "your own resistor", side="right", size=0.85)
    nx = 73.66
    s.wire(xn, ybar, xn, y0 + 16.0); s.wire(xn, y0 + 16.0, nx, y0 + 16.0)
    s.wire(nx, y0 + 16.0, nx, A["alt"][1]); s.wire(nx, A["alt"][1], *A["alt"])
    label_node(ctx, nx + 1.0, (y0 + 16.0 + clB) / 2, "NOISE", side="right", size=0.9)
    # channel B: a second jumper selects NOISE or the photodiode
    jb = part(ctx, "Jumper:Jumper_3_Open", "JP1203", "ALT", "H1x3", B["alt"][0] + 10.16, B["alt"][1] + 7.62, rot=90,
              ref_at=(B["alt"][0] + 15.0, B["alt"][1] + 6.5), val_at=(B["alt"][0] + 15.0, B["alt"][1] + 9.0))
    ja, jb3, jc = jb.pin(1), jb.pin(3), jb.pin(2)          # 1 = bottom, 3 = top, 2 = common (right)
    # the channel's ALT position goes to the jumper's COMMON pin; the two ends are NOISE and PHOTODIODE
    xcm = jc[0] + 2.54
    s.wire(*B["alt"], B["alt"][0], B["alt"][1] + 1.27); s.wire(B["alt"][0], B["alt"][1] + 1.27, xcm, B["alt"][1] + 1.27)
    s.wire(xcm, B["alt"][1] + 1.27, xcm, jc[1]); s.wire(xcm, jc[1], *jc)
    # top pin (3) to the NOISE line on the left
    s.wire(*jb3, nx, jb3[1]); s.junction(nx, jb3[1])
    # bottom pin (1) down to the photodiode receiver
    s.wire(*ja, ja[0], ja[1] + 2.54)
    pdn = (ja[0], ja[1] + 2.54)
    label_node(ctx, ja[0] + 1.0, ja[1] + 1.2, "PHOTODIODE", side="right", size=0.85)
    label_node(ctx, jb3[0] + 1.0, jb3[1] - 0.3, "NOISE", side="right", size=0.85)
    label_node(ctx, xcm + 1.0, jc[1] + 0.5, "JP1203: channel B's ALT source", side="right", size=0.85)

    # --- photodiode receiver (transimpedance), bottom middle ------------------------
    yp = 300.0
    xp = 150.0
    s.text(xp, yp - 4, "Photodiode receiver (channel B, jumper PHOTODIODE)", size=1.6, bold=True)
    note(ctx, xp, yp, "VBPW34S PIN photodiode, reverse biased 4.5 V, into a transimpedance amplifier: 10 kΩ -> 10 mV per µA, "
                      "2.2 pF -> 6.8 MHz with 3.5 dB of peaking at 4 MHz (sim/tia.cir; 3.3 pF flattens it). Plug an external photodiode into J6 (cathode to the top pin). Light makes the "
                      "output go positive. Aim it at the LED on another board's DAC 2 for the lock-in-across-the-room experiment.",
         w=125, size=0.95)
    tia = part(ctx, ids["opa2810"], "U105", "OPA2810", "SOIC8", xp + 55.88, yp + 48.26, unit=1,
               ref_at=(xp + 62.0, yp + 54.5), val_at=(xp + 62.0, yp + 55.0))
    tp, tm, to = tia.pin("3"), tia.pin("2"), tia.pin("1")
    s.wire(*tp, tp[0] - 6.35, tp[1]); gnd(ctx, tp[0] - 6.35, tp[1], stub=2.54)
    # rot 270: cathode up to the summing node (virtual ground), anode down to -4V4:
    # reverse biased by the negative rail
    pd = part(ctx, "Device:D_Photo", "D103", "VBPW34S", "PD", tm[0] - 15.24, tm[1] + 12.7, rot=270,
              ref_at=(tm[0] - 12.0, tm[1] + 11.0), val_at=(tm[0] - 12.0, tm[1] + 14.0))
    kk, aa = pd.pin(1), pd.pin(2)
    xs_ = tm[0] - 2.54
    ysum = kk[1] - 2.54
    s.wire(*tm, xs_, tm[1]); s.junction(xs_, tm[1]); s.wire(xs_, tm[1], xs_, ysum); s.wire(xs_, ysum, kk[0], ysum); s.wire(kk[0], ysum, *kk)
    gnd(ctx, *aa, "-4V2", stub=5.08)
    # external photodiode header, pins pointing at the diode: top pin to the cathode node, bottom to -4V4
    jpd = part(ctx, "Connector_Generic:Conn_01x02", "J106", "PD EXT", "H1x2", kk[0] - 17.78, (kk[1] + aa[1]) / 2, rot=180,
               ref_at=(kk[0] - 28.0, kk[1] - 2.0), val_at=(kk[0] - 28.0, aa[1] + 1.0))
    e1, e2 = jpd.pin(1), jpd.pin(2)
    eh, el = (e1, e2) if e1[1] < e2[1] else (e2, e1)
    s.wire(*eh, eh[0] + 2.54, eh[1]); s.wire(eh[0] + 2.54, eh[1], eh[0] + 2.54, ysum); s.wire(eh[0] + 2.54, ysum, kk[0], ysum); s.junction(kk[0], ysum)
    s.wire(*el, el[0] + 5.08, el[1]); s.wire(el[0] + 5.08, el[1], el[0] + 5.08, aa[1] + 2.54); s.wire(el[0] + 5.08, aa[1] + 2.54, aa[0], aa[1] + 2.54); s.junction(aa[0], aa[1] + 2.54)
    yf = tm[1] - 10.16
    rf = R(ctx, 400, "10k", tia.x, yf, horiz=True)
    cf = C(ctx, 400, "2.2pF", tia.x, yf - 6.35, horiz=True, ref_at=(tia.x + 2.6, yf - 8.25), val_at=(tia.x - 6.5, yf - 9.75))      # (either side above the body since build 27: below it the value sat on R1405)
    s.wire(tm[0] - 2.54, tm[1], tm[0] - 2.54, yf - 6.35); s.wire(tm[0] - 2.54, yf, *rf.pin(1)); s.wire(tm[0] - 2.54, yf - 6.35, *cf.pin(1))
    s.wire(*rf.pin(2), to[0] + 2.54, yf); s.wire(*cf.pin(2), to[0] + 2.54, yf - 6.35); s.wire(to[0] + 2.54, yf - 6.35, to[0] + 2.54, to[1]); s.wire(*to, to[0] + 2.54, to[1])
    ytt = to[1] - 10.16                                              # the tap's row, on the output's run up to the jumper
    s.wire(to[0] + 2.54, to[1], to[0] + 7.62, to[1]); s.wire(to[0] + 7.62, to[1], to[0] + 7.62, ytt); s.wire(to[0] + 7.62, ytt, to[0] + 7.62, pdn[1] + 10.16)
    # monitor tap (build 26): the receiver's output through 49.9 R into a U.FL
    s.junction(to[0] + 7.62, ytt)
    rtt = R(ctx, 400, "49.9R", to[0] + 15.24, ytt, horiz=True)
    s.wire(to[0] + 7.62, ytt, *rtt.pin(1))
    jtt = part(ctx, ids["ufl"], "J109", "U.FL", "UFL", to[0] + 26.67, ytt, ref_at=(to[0] + 29.0, ytt - 2.0), val_at=(to[0] + 29.0, ytt + 0.5),
               desc="monitor tap: photodiode receiver output, through 49.9 R")
    s.wire(*rtt.pin(2), *jtt.pin(1)); gnd(ctx, *jtt.pin(2), stub=2.54)
    label_node(ctx, to[0] + 9.0, ytt - 4.0, "TAP TIA (50 Ω scope: x1/2)", side="right", size=0.85)
    s.wire(to[0] + 7.62, pdn[1] + 10.16, pdn[0], pdn[1] + 10.16); s.wire(pdn[0], pdn[1] + 10.16, *pdn)
    label_node(ctx, to[0] + 8.5, to[1] - 4.5, "to JP203", side="right", size=0.85)      # (between the output run and the tap row: on the tap row it sat on R1406's value)
    ub = part(ctx, ids["opa2810"], "U105", "OPA2810", "SOIC8", xp + 55.88, yp + 73.66, unit=2,
              ref_at=(xp + 50.5, yp + 68.0), val_at=(xp + 55.0, yp + 65.5))
    bp, bm, bo = ub.pin("5"), ub.pin("6"), ub.pin("7")
    s.wire(*bp, bp[0] - 2.54, bp[1]); gnd(ctx, bp[0] - 2.54, bp[1], stub=2.54)
    s.wire(*bm, bm[0] - 2.54, bm[1]); s.wire(bm[0] - 2.54, bm[1], bm[0] - 2.54, bm[1] + 6.35); s.wire(bm[0] - 2.54, bm[1] + 6.35, bo[0] + 2.54, bm[1] + 6.35); s.wire(bo[0] + 2.54, bm[1] + 6.35, bo[0] + 2.54, bo[1]); s.wire(*bo, bo[0] + 2.54, bo[1])
    label_node(ctx, bo[0] + 3.5, bo[1] + 0.5, "spare half, parked as a follower", side="right", size=0.85)
    up = part(ctx, ids["opa2810"], "U105", "OPA2810", "SOIC8", xp + 100.0, yp + 60.96, unit=3,
              ref_at=(xp + 106.0, yp + 60.0), val_at=(xp + 106.0, yp + 61.0))
    rail(ctx, *up.pin("8"), "+5VA", stub=3.81); gnd(ctx, *up.pin("4"), "-4V2", stub=3.81)
    c1 = C(ctx, 400, "100nF", up.pin("8")[0] - 12.7, up.pin("8")[1] - 3.81 + 3.81, side="left")
    s.wire(up.pin("8")[0], up.pin("8")[1] - 3.81, c1.pin(1)[0], up.pin("8")[1] - 3.81); s.wire(c1.pin(1)[0], up.pin("8")[1] - 3.81, *c1.pin(1)); gnd(ctx, *c1.pin(2), stub=0)
    c2 = C(ctx, 400, "100nF", up.pin("4")[0] - 22.86, up.pin("4")[1] + 3.81 - 3.81, side="left")
    s.wire(up.pin("4")[0], up.pin("4")[1] + 3.81, c2.pin(2)[0], up.pin("4")[1] + 3.81); s.wire(c2.pin(2)[0], up.pin("4")[1] + 3.81, *c2.pin(2)); gnd(ctx, *c2.pin(1), stub=0, up=True)
    return hp
