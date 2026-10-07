"""The DAC sheet: AD9767 fed by two 14-bit buses from the FPGA, two DC-coupled
output stages, and the LED driver option on channel 2."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from draw import *


def output_stage(ctx, tag, cl, base, an, pa, pb, ids, uref, led=False):
    """Current outputs IOUTA/IOUTB (pins pa/pb of the analog unit) -> 24.9R
    loads -> difference amplifier (gain 4) -> 49.9R -> SMA.  Returns the node
    voltage VA (unipolar, 0..0.5 V) for the LED driver."""
    s = ctx.s
    A0, B0 = an.pin(pa), an.pin(pb)
    # the port's IOUTA/IOUTB pins are on this stage's own rows (cl -/+ 3.81): straight wires out of the trapezoid
    xl = A0[0] + 20.32
    yA, yB = cl - 3.81, cl + 3.81
    assert abs(A0[1] - yA) < 0.01 and abs(B0[1] - yB) < 0.01, (A0, B0, cl)
    s.wire(*A0, xl, yA); s.wire(*B0, xl + 10.16, yB)
    A, B = (xl, yA), (xl + 10.16, yB)
    # IOUTA's load stands UP from its node (ground on top), IOUTB's hangs down: hanging, IOUTA's stood across the IOUTB wire
    ra = R(ctx, base, "24.9R", xl, yA - 7.62 + 1.27, side="left"); s.wire(xl, yA, *ra.pin(2)); gnd(ctx, *ra.pin(1), stub=1.27, up=True)
    rb = R(ctx, base, "24.9R", xl + 10.16, yB + 7.62 + 1.27, side="right"); s.wire(xl + 10.16, yB, *rb.pin(1)); gnd(ctx, *rb.pin(2), stub=1.27)
    label_node(ctx, A0[0] + 1.5, yB + 3.5, "IOUTA and IOUTB each: 0 to +0.48 V\n(19.2 mA x 24.9 Ω), complementary", side="right", size=0.85)      # (two lines under the IOUTB wire)
    # the node's name, for the LED driver (a local label: a wire to it crossed both IOUT wires and port 2's stage)
    s.label(A0[0] + 2.54, yA, "VA%s" % tag, size=0.9)
    # difference amplifier
    xo = xl + 48.26
    amp = part(ctx, ids["opa2810"], uref, "OPA2810", "SOIC8", xo, cl, unit=1,
               ref_at=(xo - 1.0, cl - 6.0), val_at=(xo - 1.0, cl - 5.7))      # designator over value, above the triangle's flat part (build 28)
    ip, im, out = amp.pin("3"), amp.pin("2"), amp.pin("1")
    rgp = R(ctx, base, "499R", ip[0] - 10.16, ip[1], horiz=True, ref_at=(ip[0] - 14.0, ip[1] - 1.6), val_at=(ip[0] - 8.6, ip[1] - 3.4), fsize=1.0)      # both on the row above the body
    s.wire(xl, A[1], rgp.pin(1)[0] - 2.54, A[1]); s.wire(rgp.pin(1)[0] - 2.54, A[1], rgp.pin(1)[0] - 2.54, ip[1]); s.wire(rgp.pin(1)[0] - 2.54, ip[1], *rgp.pin(1))
    s.wire(*rgp.pin(2), *ip)
    rgm = R(ctx, base, "499R", im[0] - 10.16, im[1], horiz=True, ref_at=(im[0] - 14.0, im[1] + 3.4), val_at=(im[0] - 8.0, im[1] + 1.6), fsize=1.0)      # both on the row below it
    s.wire(xl + 10.16, B[1], rgm.pin(1)[0] - 5.08, B[1]); s.wire(rgm.pin(1)[0] - 5.08, B[1], rgm.pin(1)[0] - 5.08, im[1]); s.wire(rgm.pin(1)[0] - 5.08, im[1], *rgm.pin(1))
    s.wire(*rgm.pin(2), *im)
    # + input to ground through 2k; feedback 2k || 2.2 pF from the output to the - input
    rtp = R(ctx, base, "2.2k", ip[0] - 1.27, ip[1] - 8.89, side="right")        # 2.2 k since 2026-10-07: gain 4.41 makes the output a round ±2 V
    s.wire(ip[0] - 1.27, ip[1], *rtp.pin(2)); gnd(ctx, *rtp.pin(1), stub=1.27, up=True)
    # 2.2 pF across it too (build 26): the 2 k || 2.2 pF feedback on the - side needs the same impedance on the +
    # side above 10 MHz, or the difference amplifier's common-mode rejection goes with the frequency (reviews, R6)
    ctp = C(ctx, base, "2.2pF", ip[0] - 6.35, ip[1] - 8.89, side="left", ref="C%d" % (ctx.off + base + 2))    # explicit: the feedback 2.2 pF stays C2401/C2501
    s.wire(*rtp.pin(2), *ctp.pin(2)); s.wire(*rtp.pin(1), *ctp.pin(1)); s.junction(*rtp.pin(2)); s.junction(*rtp.pin(1))
    yf = cl + 11.43
    rf = R(ctx, base, "2.2k", xo, yf, horiz=True)
    cf = C(ctx, base, "2.2pF", xo, yf + 6.35, horiz=True, ref_at=(xo + 2.6, yf + 4.45), val_at=(xo - 8.0, yf + 2.95))      # (labels either side above the body since build 27: the Vout note goes under it)
    s.wire(im[0] - 1.27, im[1], im[0] - 1.27, yf + 6.35); s.wire(im[0] - 1.27, yf, *rf.pin(1)); s.wire(im[0] - 1.27, yf + 6.35, *cf.pin(1))
    s.wire(*rf.pin(2), out[0] + 2.54, yf); s.wire(*cf.pin(2), out[0] + 2.54, yf + 6.35); s.wire(out[0] + 2.54, yf + 6.35, out[0] + 2.54, out[1]); s.wire(*out, out[0] + 2.54, out[1])
    label_node(ctx, xo - 8.0, yf + 10.5, "Vout = 4.4 x (VA - VB): ±2.0 V unloaded, ±1.0 V into 50 Ω; -3 dB at 12.3 MHz", side="right", size=0.85)
    label_node(ctx, xo - 8.0, yf + 12.5, "(2.2 kΩ || 2.2 pF); a full-scale sine is slew-limited above 10 MHz (sim/dac_stage.cir)", side="right", size=0.85)
    # output series resistor and SMA
    xr = out[0] + 11.43
    ro = R(ctx, base, "49.9R", xr, cl, horiz=True)
    s.wire(out[0] + 2.54, out[1], *ro.pin(1))
    j = part(ctx, ids["sma_out"], "J%d" % (200 + base // 100), "SMA", "SMA", xr + 17.78, cl,
             ref_at=(xr + 20.0, cl - 6.0), val_at=(xr + 20.0, cl + 4.0))
    s.wire(*ro.pin(2), *j.pin(1)); gnd(ctx, *j.pin(2), stub=2.54)
    s.text(xr + 12.0, cl - 10.0, "DAC %s OUT" % tag, size=1.8, bold=True)
    s.text(xr + 8.0, cl - 14.5, "±1 V MAX OUT", size=2.2, bold=True)
    s.text(xr + 8.0, cl + 14.0, "±1 V into 50 Ω\n±2 V open circuit\n50 Ω source, DC coupled", size=0.9, justify="left top")      # (full scale to 10 MHz: in the Vout note; a fourth line here sat on the +5VA flag)
    return A, amp


def draw(sch, ids, fpga):
    ctx = Ctx(sch, "DAC")
    s = sch
    s.text(20, 22, "DAC: AD9767 dual 14-bit, 125 MSPS, two DC-coupled outputs", size=3.0, bold=True)
    note(ctx, 20, 26, "The FPGA writes 14 bits per port with its own WRT and CLK (dual-port mode; drive MODE low and the "
                      "same four pins become IQWRT/IQCLK/IQRESET/IQSEL for interleaved I/Q).\n"
                      "Each DAC sources 0-19.2 mA into 24.9 Ω on complementary outputs;\n"
                      "an OPA2810 takes the difference with gain 4.4: ±2 V unloaded, ±1 V into 50 Ω, DC coupled, centred on 0 V.\n"
                      "Channel 1's unipolar node also feeds a voltage-to-current stage that drives an "
                      "LED (on board, or your own on J210) for the optical experiments.", w=220, size=1.1)
    hp = []
    # --- the converter: one trapezoid per port (the 14-bit bus and its WRT/CLK
    # on the tall left side, the complementary current outputs on the short
    # right side, in line with that port's output stage), the shared pins in
    # a box underneath, and a dashed box round the three: one chip. ------------
    LIB = ids["dac"]
    xd = 200.0
    ports = {}
    for unit, port, yc, base in ((1, 1, 90.0, 100), (2, 2, 190.0, 200)):
        du = part(ctx, LIB, "U201", "AD9767", "LQFP48", xd, yc, unit=unit,
                  ref_at=(xd + 8.0, yc - 20.0), val_at=(xd + 8.0, yc - 17.5))      # (value under the designator since build 28: at yc + 25 it sat on the CLK row)
        ports[port] = du
        members = []
        for i in range(14):
            pin_ = str(1 + i) if port == 1 else str(23 + i)       # DB13 (MSB) is pin 1 / pin 23 on the AD9767
            p = du.pin(pin_)
            members.append((p[0], p[1], "DAC_P%d_D%d" % (port, 13 - i)))
        bus_out(ctx, xd - 38.1, 0, "DAC_P%d_D[13..0]" % port, members, x_end=xd - 60.96, shape="input")
        hp.append(("DAC_P%d_D[13..0]" % port, "input"))
        for k, (pin_, nm) in enumerate((("17", "DAC_WRT1"), ("18", "DAC_CLK1")) if port == 1 else (("20", "DAC_WRT2"), ("19", "DAC_CLK2"))):
            p = du.pin(pin_)                                          # on the sloped bottom edge, pointing up
            yk = p[1] + 5.08 + k * 2.54                               # two rows under the converter, WRT above CLK
            s.wire(*p, p[0], yk)
            xr_ = xd - 55.88
            r = R(ctx, base, "33R", xr_, yk, horiz=True, ref_at=(xr_ - 2.6, yk - 1.6) if k == 0 else (xr_ - 2.6, yk + 3.4), val_at=(xr_ + 4.5, yk - 3.4) if k == 0 else (xr_ + 4.5, yk + 1.6))
            s.wire(*r.pin(2), p[0], yk); s.wire(*r.pin(1), r.pin(1)[0] - 7.62, yk)
            s.hlabel(r.pin(1)[0] - 7.62, yk, nm, shape="input", rot=180)
            hp.append((nm, "input"))
        if port == 1:           # (once: under port 2 it ran into the shared unit's supply flags)
            label_node(ctx, xd - 48.0, du.pin("18")[1] + 12.5, "WRT latches the data, CLK updates the output (each port its own): from the FPGA, up into the converter", side="right", size=0.85)
    # --- the shared pins, under the two ports ------------------------------------
    yc3 = 254.0
    bc = unit_body(LIB, 3)
    cu = part(ctx, LIB, "U201", "AD9767", "LQFP48", xd, yc3, unit=3,
              ref_at=(xd + 8.0, yc3 + bc[1] - 0.6), val_at=(xd - 18.0, yc3 + bc[3] + 0.6))      # just outside the box: designator right of the DVDD pins, value left of the ground pins
    mode, sleep, gain = cu.pin("48"), cu.pin("37"), cu.pin("42")
    s.wire(*mode, mode[0] - 20.32, mode[1]); s.hlabel(mode[0] - 20.32, mode[1], "DAC_MODE", shape="input", rot=180)
    pullup(ctx, 300, mode[0] - 6.35, mode[1], "10k", "+3V3_DAC_D")
    label_node(ctx, mode[0] - 52.0, mode[1] - 2.0, "MODE high = dual port (pull-up)", side="right", size=0.85)
    s.wire(*sleep, sleep[0] - 20.32, sleep[1]); s.hlabel(sleep[0] - 20.32, sleep[1], "DAC_SLEEP", shape="input", rot=180)
    pullup(ctx, 300, sleep[0] - 13.97, sleep[1], "10k", "GND", down=True)
    label_node(ctx, sleep[0] - 30.0, sleep[1] + 19.0, "SLEEP low = running (default by pull-down)", side="right", size=0.85)
    s.wire(*gain, gain[0] - 5.08, gain[1]); gnd(ctx, gain[0] - 5.08, gain[1], stub=2.54)
    label_node(ctx, gain[0] - 30.0, gain[1] + 17.5, "GAINCTRL low: one FSADJ resistor per DAC", side="right", size=0.85)
    hp += [("DAC_MODE", "input"), ("DAC_SLEEP", "input")]
    # the three rows are 2.54 apart: the top one's part hangs furthest right so nothing crosses
    for pin_, base, dx in (("44", 310, 20.32), ("41", 320, 12.7)):
        p = cu.pin(pin_)
        r = R(ctx, base, "2k", p[0] + dx, p[1] + 5.08, side="right", fsize=1.0)      # (7.62 apart: at 1.27 "R2321" reached R2311)
        s.wire(*p, p[0] + dx, p[1]); s.wire(p[0] + dx, p[1], *r.pin(1)); gnd(ctx, *r.pin(2), stub=1.27)
    label_node(ctx, cu.pin("44")[0] + 29.0, cu.pin("44")[1] + 5.5, "FSADJ: IOUTFS = 32 x 1.2 V / 2 kΩ = 19.2 mA", side="right", size=0.85)      # (right of R2311, with REFIO's under it)
    p = cu.pin("43")
    c = C(ctx, 330, "100nF", p[0] + 5.08, p[1] + 5.08, side="right")
    s.wire(*p, p[0] + 5.08, p[1]); s.wire(p[0] + 5.08, p[1], *c.pin(1)); gnd(ctx, *c.pin(2), stub=1.27)
    label_node(ctx, cu.pin("44")[0] + 29.0, cu.pin("44")[1] + 7.5, "REFIO: internal 1.2 V reference", side="right", size=0.85)
    # supplies on top (the two flags pulled apart so their names do not collide), grounds underneath
    a, d1, d2 = cu.pin("47"), cu.pin("16"), cu.pin("22")
    s.wire(*a, a[0], a[1] - 5.08); s.wire(a[0], a[1] - 5.08, a[0] - 10.16, a[1] - 5.08); rail(ctx, a[0] - 10.16, a[1] - 5.08, "+3V3_DAC", stub=5.08)
    s.wire(*d1, d1[0], d1[1] - 5.08); s.wire(*d2, d2[0], d2[1] - 5.08); s.wire(d1[0], d1[1] - 5.08, d2[0] + 10.16, d2[1] - 5.08)
    rail(ctx, d2[0] + 10.16, d2[1] - 5.08, "+3V3_DAC_D", stub=5.08)
    for nn in ("38", "15", "21"):
        p = cu.pin(nn); s.wire(*p, p[0], p[1] + 2.54)
    s.wire(cu.pin("38")[0], cu.pin("38")[1] + 2.54, cu.pin("21")[0], cu.pin("21")[1] + 2.54); gnd(ctx, cu.pin("21")[0], cu.pin("21")[1] + 2.54, stub=2.54)
    # the dashed box: three units, one chip
    gx0, gx1 = xd - 21.59, xd + 21.59
    gy0, gy1 = ports[1].y - 21.59 - 3.0, cu.pin("38")[1] + 3.0          # (the bottom edge from the ground pins' ends: the box's height follows its pin names)
    s.rect(gx0, gy0, gx1 - gx0, gy1 - gy0, style="dash", width=0.25)
    s.text(gx0 + 2.0, gy0 - 1.0, "U201 AD9767: one chip, drawn as its two ports (trapezoids) and the pins they share (box)", size=1.0, bold=True)

    # --- output stages ---------------------------------------------------------
    va1, amp1 = output_stage(ctx, "1", ports[1].y, 400, ports[1], "46", "45", ids, "U202")
    va2, amp2 = output_stage(ctx, "2", ports[2].y, 500, ports[2], "39", "40", ids, "U203")
    # the IOUT pins are on the analog unit at y ~ 125-150; route from the unit's right side to the stages
    # (output_stage wired straight right from the pins; the stages sit at those y's -- adjust below)
    # amplifier power units
    for uref, amp in (("U202", amp1), ("U203", amp2)):
        pw = part(ctx, ids["opa2810"], uref, "OPA2810", "SOIC8", amp.x + 40.64, amp.y + 45.72, unit=3,
                  ref_at=(amp.x + 46.5, amp.y + 44.7), val_at=(amp.x + 46.5, amp.y + 45.7))      # (10 mm lower since build 28: the Vout note ran through its +5VA flag)
        rail(ctx, *pw.pin("8"), "+5VA", stub=3.81); gnd(ctx, *pw.pin("4"), "-4V2", stub=3.81)
        c1 = C(ctx, 600 if uref == "U202" else 700, "100nF", pw.pin("8")[0] - 12.7, pw.pin("8")[1], side="left")
        s.wire(pw.pin("8")[0], pw.pin("8")[1] - 3.81, c1.pin(1)[0], pw.pin("8")[1] - 3.81); s.wire(c1.pin(1)[0], pw.pin("8")[1] - 3.81, *c1.pin(1)); gnd(ctx, *c1.pin(2), stub=0)
        c2 = C(ctx, 600 if uref == "U202" else 700, "100nF", pw.pin("4")[0] - 22.86, pw.pin("4")[1], side="left")
        s.wire(pw.pin("4")[0], pw.pin("4")[1] + 3.81, c2.pin(2)[0], pw.pin("4")[1] + 3.81); s.wire(c2.pin(2)[0], pw.pin("4")[1] + 3.81, *c2.pin(2)); gnd(ctx, *c2.pin(1), stub=0, up=True)
    # channel 2's spare half parked (the LED driver is channel 1's, the upper jack, since 2026-10-07)
    ub = part(ctx, ids["opa2810"], "U203", "OPA2810", "SOIC8", amp2.x, amp2.y + 35.56, unit=2,
              ref_at=(amp2.x - 1.0, amp2.y + 29.56), val_at=(amp2.x - 1.0, amp2.y + 29.86))
    bp, bm, bo = ub.pin("5"), ub.pin("6"), ub.pin("7")
    s.wire(*bp, bp[0] - 2.54, bp[1]); gnd(ctx, bp[0] - 2.54, bp[1], stub=2.54)
    s.wire(*bm, bm[0] - 2.54, bm[1]); s.wire(bm[0] - 2.54, bm[1], bm[0] - 2.54, bm[1] + 6.35); s.wire(bm[0] - 2.54, bm[1] + 6.35, bo[0] + 2.54, bm[1] + 6.35); s.wire(bo[0] + 2.54, bm[1] + 6.35, bo[0] + 2.54, bo[1]); s.wire(*bo, bo[0] + 2.54, bo[1])
    label_node(ctx, bo[0] + 3.5, bo[1] + 0.5, "spare half, parked", side="right", size=0.85)
    # --- LED driver on channel 1: V to I, 0..50 mA -------------------------------
    yl = 300.0
    xl0 = 300.0
    s.text(xl0, yl - 4, "LED driver (channel 1): the DAC's unipolar node drives a current source", size=1.6, bold=True)
    note(ctx, xl0, yl, "I_LED = VA1 / 10 Ω = 0 to 48 mA, linear in the DAC code.\n"
                       "DC coupled: a code of 8192 is a 24 mA bias, and a sine on top of it is intensity modulation.\n"
                       "JP2009 picks the on-board red LED (625 nm) or your own on J210 (anode to +5 V, cathode to the driver).\n"
                       "Bandwidth is set by the transistor and the OPA2810: a few MHz.", w=150, size=0.95)
    d = part(ctx, ids["opa2810"], "U202", "OPA2810", "SOIC8", xl0 + 40.0, yl + 48.0, unit=2,
             ref_at=(xl0 + 39.0, yl + 42.0), val_at=(xl0 + 39.0, yl + 42.3))      # (10 mm lower since build 28: the LED's +5V flag stood in the note)
    dp, dm, do = d.pin("5"), d.pin("6"), d.pin("7")
    s.wire(*dp, dp[0] - 7.62, dp[1]); s.label(dp[0] - 7.62, dp[1], "VA1", size=0.9, justify="right bottom")      # the stage's IOUTA node, by name
    label_node(ctx, dp[0] - 34.0, dp[1] - 2.4, "VA1 (DAC 1's IOUTA node) = 0..0.48 V", side="right", size=0.85)
    rb = R(ctx, 500, "100R", do[0] + 8.89, do[1], horiz=True)
    s.wire(*do, *rb.pin(1))
    q = part(ctx, "Transistor_BJT:SS8050", "Q201", "SS8050", "SOT23", rb.pin(2)[0] + 7.62, do[1], rot=0,
             ref_at=(rb.pin(2)[0] + 12.0, do[1] - 1.5), val_at=(rb.pin(2)[0] + 12.0, do[1] + 0.0))
    s.wire(*rb.pin(2), *q.pin(1))
    e, c_ = q.pin(2), q.pin(3)
    rs = R(ctx, 500, "10R", e[0], e[1] + 6.35, side="right")
    s.wire(*e, *rs.pin(1)); gnd(ctx, *rs.pin(2), stub=1.27)
    s.wire(*dm, dm[0] - 2.54, dm[1]); s.wire(dm[0] - 2.54, dm[1], dm[0] - 2.54, e[1] + 12.7); s.wire(dm[0] - 2.54, e[1] + 12.7, e[0] - 5.08, e[1] + 12.7)
    s.wire(e[0] - 5.08, e[1] + 12.7, e[0] - 5.08, e[1] + 1.27); s.wire(e[0] - 5.08, e[1] + 1.27, e[0], e[1] + 1.27)
    label_node(ctx, e[0] + 9.0, e[1] + 8.0, "10 Ω sense: 48 mA full scale", side="right", size=0.85)
    jl = part(ctx, "Jumper:Jumper_3_Open", "JP2009", "LED", "H1x3", c_[0], c_[1] - 10.16, rot=0,
              ref_at=(c_[0] + 7.0, c_[1] - 11.5), val_at=(c_[0] + 7.0, c_[1] - 9.3))      # designator above the wire to J210, value below it
    ja, jb, jc = jl.pin(1), jl.pin(3), jl.pin(2)
    s.wire(*c_, *jc)
    led = part(ctx, "Device:LED", "D201", "XL-2835SURC-05", "LED2835", ja[0] - 10.16, ja[1] - 7.62, rot=90,
               ref_at=(ja[0] - 7.5, ja[1] - 9.0), val_at=(ja[0] - 7.5, ja[1] - 8.5))
    lk, la = led.pin(1), led.pin(2)
    s.wire(*ja, ja[0] - 10.16, ja[1]); s.wire(ja[0] - 10.16, ja[1], *lk); rail(ctx, *la, "+5V", stub=2.54)
    label_node(ctx, ja[0] - 24.0, ja[1] + 5.0, "on-board red LED", side="right", size=0.85)
    jx = part(ctx, "Connector_Generic:Conn_01x02", "J210", "LED EXT", "H1x2", jb[0] + 17.78, jb[1] - 1.27, rot=0,
              ref_at=(jb[0] + 20.5, jb[1] - 4.5), val_at=(jb[0] + 20.5, jb[1] + 2.5))
    x1, x2 = jx.pin(1), jx.pin(2)
    hi, lo = (x1, x2) if x1[1] < x2[1] else (x2, x1)
    s.wire(*jb, lo[0], jb[1]) if lo[1] == jb[1] else (s.wire(*jb, jb[0] + 5.08, jb[1]), s.wire(jb[0] + 5.08, jb[1], jb[0] + 5.08, lo[1]), s.wire(jb[0] + 5.08, lo[1], *lo))
    s.wire(*hi, hi[0] - 2.54, hi[1]); rail(ctx, hi[0] - 2.54, hi[1], "+5V", stub=2.54)
    label_node(ctx, jb[0] + 20.0, jb[1] + 8.0, "your LED: anode to pin 1 (+5 V)", side="right", size=0.85)
    decouple(ctx, 340, 150.0, 285.0, "+3V3_DAC", ["10uF", "100nF"], label="AVDD")
    decouple(ctx, 350, 150.0, 310.0, "+3V3_DAC_D", ["10uF", "100nF", "100nF"], label="DVDD1, DVDD2: +3V3 through a ferrite (power sheet)")
    note(ctx, 20, 340.0, "Timing: data is latched by WRT and the DAC updates on CLK; tie them to the same FPGA clock for the simple case.\n"
                         "14 bits at 125 MSPS, straight binary (code 0 = IOUTA off = -2 V unloaded).", w=160, size=0.95)
    return hp
