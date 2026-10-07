"""USB and the small ports: FT2232H (JTAG on channel A, serial on channel B,
at the same time), the FTDI USB-C that also powers the board, the FPGA's own
USB-C, the mini-HDMI (GPDI) and the microSD."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from draw import *


def usbc(ctx, ref, x, y, ids, name, base):
    """A USB-C receptacle at (x, y) with its CC resistors.  Returns the D+,
    D- and VBUS nodes to its right; the VBUS wire runs on past the CC
    resistors to (xv, y) so the ESD diode's supply pin can tie in there."""
    s = ctx.s
    j = part(ctx, "Connector:USB_C_Receptacle_USB2.0_16P", ref, "USB4105-GF-A-120", "USBC", x, y,
             ref_at=(x - 10.0, y - 23.0), val_at=(x + 3.5, y + 25.0))      # (value right of the GND stem since build 28: it ran through it)
    s.text(x - 10.0, y - 26.0, name, size=1.6, bold=True)
    vb = j.pin("A4"); cc1, cc2 = j.pin("A5"), j.pin("B5")
    dp1, dp2, dm1, dm2 = j.pin("A6"), j.pin("B6"), j.pin("A7"), j.pin("B7")
    xr = vb[0] + 7.62
    xv = vb[0] + 50.8
    s.wire(*vb, xv, vb[1])
    # Rd on each CC: 5.1 k to ground, flat on the row; CC2's finishes first so
    # CC1's wire can run on past it
    for cc, x0 in ((cc1, vb[0] + 39.37), (cc2, vb[0] + 29.21)):
        r = R(ctx, base, "5.1k", x0 + 3.81, cc[1], horiz=True,
              ref_at=(x0 + 1.2, cc[1] - 1.6) if cc is cc1 else (x0 + 9.5, cc[1] + 1.6),
              val_at=(x0 + 7.6, cc[1] - 3.4) if cc is cc1 else (x0 + 9.5, cc[1] + 1.9), fsize=1.27 if cc is cc1 else 1.0)      # (CC1's both above its body, CC2's stacked right of its ground)
        s.wire(*cc, *r.pin(1)); gnd(ctx, *r.pin(2), stub=0)
    label_node(ctx, vb[0] + 20.0, cc1[1] - 0.9, "Rd: we are a device", side="right", size=0.85)
    # the two D+ pins and the two D- pins join
    s.wire(*dp1, *dp2); s.wire(*dm1, *dm2)
    s.wire(*dp2, xr, dp2[1]); s.wire(*dm2, xr, dm2[1])
    g = j.pin("A1"); gnd(ctx, *g, stub=2.54)
    sh = j.pin("SH"); s.wire(*sh, sh[0], g[1] + 2.54); s.wire(sh[0], g[1] + 2.54, g[0], g[1] + 2.54)
    for p in (j.pin("A8"), j.pin("B8")):
        s.nc(*p)
    return (xr, dp2[1]), (xr, dm2[1]), (xv, vb[1])


def esd(ctx, ref, dp, dm, vb):
    """USBLC6-2SC6 after a USB-C: D- on I/O1 (pins 1/6, the upper pair), D+ on
    I/O2 (pins 3/4).  Its VBUS pin ties to the VBUS wire's far end."""
    s = ctx.s
    e = part(ctx, "Power_Protection:USBLC6-2SC6", ref, "USBLC6-2SC6", "SOT23-6", dp[0] + 15.24, (dp[1] + dm[1]) / 2 + 1.27,
             ref_at=(dp[0] + 11.0, dp[1] + 8.5), val_at=(dp[0] + 11.0, dp[1] + 8.8), justify="right")      # (below left since build 28: on the right they sat on the 15 k pull-downs)
    e1, e3, e4, e6, ev, eg = e.pin(1), e.pin(3), e.pin(4), e.pin(6), e.pin(5), e.pin(2)
    s.wire(*dm, e1[0], dm[1]); s.wire(e1[0], dm[1], *e1)
    s.wire(*dp, e3[0], dp[1]); s.wire(e3[0], dp[1], *e3)
    s.wire(*ev, vb[0], ev[1]); s.wire(vb[0], ev[1], *vb); s.junction(*vb)
    gnd(ctx, *eg, stub=2.54)
    return e6, e4       # D- out, D+ out


def draw(sch, ids, fpga):
    ctx = Ctx(sch, "USB")
    s = sch
    s.text(20, 22, "USB: FT2232H (JTAG + serial at once), USB USER (a soft USB device), HDMI, microSD", size=3.0, bold=True)
    note(ctx, 20, 26, "USB PROG: the FT2232H gives two USB channels through one cable. Channel A is the JTAG programmer\n"
                      "(openFPGALoader -c ft2232), channel B the serial console, so the console stays open while a bitstream\n"
                      "loads and the whole boot can be captured. Its USB-C also powers the board (VBUS to the power sheet).\n"
                      "USB USER: the second USB-C goes straight to FPGA pins (ULX3S style) for a soft USB device\n"
                      "(full speed: 27 Ω series, 15 kΩ pull-downs, a 1.5 kΩ pull-up on D+ switched by an FPGA pin).\n"
                      "GPDI is the ULX3S / Icepi 22 nF-coupled HDMI; its DDC I2C is level shifted to 5 V. The microSD is wired 4-bit with pull-ups.", w=230, size=1.1)
    hp = []
    # --- FTDI USB-C -----------------------------------------------------------------
    dp, dm, vb = usbc(ctx, "J501", 50.0, 110.0, ids, "USB-C: PROGRAM / SERIAL / POWER", 1200)
    s.wire(*vb, vb[0] + 7.62, vb[1]); s.hlabel(vb[0] + 7.62, vb[1], "VBUS", shape="output")
    hp.append(("VBUS", "output"))
    label_node(ctx, vb[0] - 48.0, vb[1] - 1.0, "5 V in: the board's only supply", side="right", size=0.85)
    e6, e4 = esd(ctx, "U501", dp, dm, vb)
    # FT2232H
    xf = 170.0
    u = part(ctx, "Interface_USB:FT2232HL", "U502", "FT2232HL", "LQFP64_10", xf, 150.0, ref_at=(xf + 20.0, 86.0), val_at=(xf - 32.0, 212.0))
    dmp, dpp = u.pin("8"), u.pin("7")
    s.wire(*e6, dmp[0] - 5.08, e6[1]); s.wire(dmp[0] - 5.08, e6[1], dmp[0] - 5.08, dmp[1]); s.wire(dmp[0] - 5.08, dmp[1], *dmp)
    s.wire(*e4, dpp[0] - 7.62, e4[1]); s.wire(dpp[0] - 7.62, e4[1], dpp[0] - 7.62, dpp[1]); s.wire(dpp[0] - 7.62, dpp[1], *dpp)
    # REF, RESET, TEST
    ref = u.pin("6")
    # REF's 12 k stands UP from its wire, its ground on top, in the column between the D+/D- jogs and the RESET#
    # pull-up: hanging down it stood across the RESET# wire (builds to 27)
    rr = R(ctx, 1220, "12k", ref[0] - 12.7, ref[1] - 6.35, side="left"); s.wire(*ref, ref[0] - 12.7, ref[1]); s.wire(ref[0] - 12.7, ref[1], *rr.pin(2)); gnd(ctx, *rr.pin(1), stub=1.27, up=True)
    rst = u.pin("14")
    # RESET#: one wire west from the pin, its 10 k pull-up on the way and the FTDI OFF jumper at its end
    s.wire(*rst, rst[0] - 38.1, rst[1]); pullup(ctx, 1220, rst[0] - 25.4, rst[1], "10k", "+3V3", side="left")
    s.text(rst[0] - 1.3, rst[1] + 2.9, "R6221: 12 k 1 %, the USB drive-current reference", size=0.85, justify="right bottom")
    # FTDI OFF (2026-10-07): a shunt holds RESET# low, the FT2232H tri-states its pins, and the JTAG header J305 (FPGA
    # sheet) takes an external programmer without a fight: channel A's default (UART) mode drives TXD, which is TCK.
    jr = part(ctx, "Jumper:Jumper_2_Open", "JP501", "FTDI OFF", "H1x2", rst[0] - 38.1, rst[1] + 5.08, rot=90,
              ref_at=(rst[0] - 40.0, rst[1] + 3.8), val_at=(rst[0] - 40.0, rst[1] + 4.1), justify="right")
    ja_, jb_ = jr.pin(1), jr.pin(2)
    jt_, jbt_ = (ja_, jb_) if ja_[1] < jb_[1] else (jb_, ja_)
    assert abs(jt_[1] - rst[1]) < 0.01 and abs(jt_[0] - (rst[0] - 38.1)) < 0.01, (jt_, rst)
    gnd(ctx, *jbt_, stub=2.54)
    label_node(ctx, rst[0] - 35.2, rst[1] + 12.0, "FTDI OFF: a shunt holds RESET# low;\nthe FT2232H tri-states, and J305\ntakes an external JTAG programmer", side="right", size=0.85)      # (three short lines: a long one ran into the chip)
    tst = u.pin("13"); s.wire(*tst, tst[0] - 2.54, tst[1]); gnd(ctx, tst[0] - 2.54, tst[1], stub=2.54)
    # crystal, 12 MHz: jogs of 2.54 to the 7.62 mm pin pitch, caps to the left
    osci, osco = u.pin("2"), u.pin("3")
    # four pads: 1 and 3 are the crystal, 2 and 4 the grounded case (the YXC drawing)
    y = part(ctx, "Device:Crystal_GND24", "Y501", "12MHz", "XTAL3225", osci[0] - 17.78, 193.04, rot=270,
             ref_at=(osci[0] - 21.2, 186.0), val_at=(osci[0] - 21.2, 186.3), lcsc="C9002", justify="right")      # (above left since build 28: on the right they ran into the chip's pins)
    ya, yb = sorted([y.pin(1), y.pin(3)], key=lambda q: q[1])
    # (KiCad draws the symbol's two ground pins on one point: one stub, pointing away from the crystal, serves both)
    g2_ = y.pin(2); dx_ = 2.54 if g2_[0] > y.x else -2.54
    s.wire(*g2_, g2_[0] + dx_, g2_[1]); s.power("GND", g2_[0] + dx_, g2_[1], down=True, rot=90 if dx_ > 0 else 270)
    xa, xb = osci[0] - 5.08, osci[0] - 10.16
    s.wire(*osci, xa, osci[1]); s.wire(xa, osci[1], xa, ya[1]); s.wire(xa, ya[1], *ya)
    s.wire(*osco, xb, osco[1]); s.wire(xb, osco[1], xb, yb[1]); s.wire(xb, yb[1], *yb)
    for pp, base in ((ya, 1210), (yb, 1215)):
        c = C(ctx, base, "27pF", pp[0] - 20.32, pp[1], horiz=True, ref_at=(pp[0] - 27.7, pp[1] - 1.9), val_at=(pp[0] - 21.5, pp[1] - 4.0))      # (clear of the case ground's name, which lies 12-14 mm left of the crystal)
        s.wire(*pp, *c.pin(2)); s.wire(*c.pin(1), c.pin(1)[0] - 2.54, pp[1]); s.power("GND", c.pin(1)[0] - 2.54, pp[1], down=True, rot=270)      # (grounds on their side: hanging, the upper one's name sat on the lower capacitor)
    # EEPROM: CS and CLK straight across; the data line has its pull-up and the
    # 2.2 k DO link on the EEPROM's free side and comes round underneath
    ecs, eclk, edat = u.pin("63"), u.pin("62"), u.pin("61")
    xe = ecs[0] - 25.4
    ee = part(ctx, ids["eeprom"], "U503", "93LC56BT-I/OT", "SOT23-6", xe, ecs[1], ref_at=(xe - 8.0, ecs[1] - 9.5), val_at=(xe + 2.0, ecs[1] - 9.5))
    cs_, clk_, di, do_ = ee.pin("5"), ee.pin("4"), ee.pin("3"), ee.pin("1")
    s.wire(*cs_, ecs[0] - 2.54, cs_[1]); s.wire(ecs[0] - 2.54, cs_[1], ecs[0] - 2.54, ecs[1]); s.wire(ecs[0] - 2.54, ecs[1], *ecs)
    s.wire(*clk_, ecs[0] - 5.08, clk_[1]); s.wire(ecs[0] - 5.08, clk_[1], ecs[0] - 5.08, eclk[1]); s.wire(ecs[0] - 5.08, eclk[1], *eclk)
    xn = di[0] - 10.16
    s.wire(*di, xn, di[1]); pullup(ctx, 1230, xn, di[1], "10k", "+3V3", side="left")
    rd = R(ctx, 1230, "2.2k", xn + 3.81, do_[1], horiz=True, ref_at=(xn + 1.2, do_[1] + 3.4), val_at=(xn + 1.2, do_[1] + 3.7))      # (both under the body since build 28: the designator sat on it)
    s.wire(*do_, *rd.pin(2)); s.junction(xn, do_[1])
    yd = 184.15
    s.wire(xn, di[1], xn, yd); s.wire(xn, yd, edat[0] - 7.62, yd); s.wire(edat[0] - 7.62, yd, edat[0] - 7.62, edat[1]); s.wire(edat[0] - 7.62, edat[1], *edat)
    rail(ctx, *ee.pin("6"), "+3V3", stub=0); gnd(ctx, *ee.pin("2"), stub=0)      # (no stubs since build 28: the box grew for its VCC/VSS names)
    label_node(ctx, 45.0, ecs[1] - 2.0, "optional: a blank EEPROM still enumerates;\nprogram it with ftdi_eeprom for a custom name", side="right", size=0.85)
    # power pins: VREGIN 3.3 V; VREGOUT 1.8 V feeds VCORE x3 directly and VPHY + VPLL through a bead
    vregin, vregout = u.pin("50"), u.pin("49")
    s.wire(*vregin, vregin[0] - 7.62, vregin[1]); rail(ctx, vregin[0] - 7.62, vregin[1], "+3V3", stub=3.81)
    tops = [u.pin(n) for n in ("12", "37", "64")]
    vphy, vpll = u.pin("4"), u.pin("9")
    vio = [u.pin(n) for n in ("20", "31", "42", "56")]
    ybar = tops[0][1] - 6.35
    yfeed = ybar - 7.62
    for p in tops:
        s.wire(*p, p[0], ybar)
    s.wire(tops[0][0], ybar, tops[-1][0], ybar); s.junction(tops[1][0], ybar)
    xo = vregout[0] - 10.16
    s.wire(*vregout, xo, vregout[1]); s.wire(xo, vregout[1], xo, yfeed); s.wire(xo, yfeed, tops[0][0], yfeed); s.wire(tops[0][0], yfeed, tops[0][0], ybar)
    rail(ctx, xo, yfeed, "+1V8_FTDI", stub=0)
    label_node(ctx, tops[0][0] - 24.0, yfeed - 2.0, "VREGOUT: internal 1.8 V, feeds VCORE x3, VPLL, VPHY", side="right", size=0.85)
    ypb = vphy[1] - 2.54
    s.wire(*vphy, vphy[0], ypb); s.wire(*vpll, vpll[0], ypb); s.wire(vphy[0], ypb, vpll[0], ypb); s.junction(vphy[0], ypb)
    fb = part(ctx, "Device:FerriteBead", ctx.ref("FB", 1240), "600R@100MHz", "L0603", vphy[0], ypb - 5.08, rot=0, lcsc="C85833",
              ref_at=(vphy[0] - 3.2, ypb - 6.6), val_at=(vphy[0] - 3.2, ypb - 6.3), justify="right")
    fa, fb_ = sorted([fb.pin(1), fb.pin(2)], key=lambda q: q[1])
    s.wire(vphy[0], ypb, *fb_); s.wire(*fa, vphy[0], yfeed); s.junction(vphy[0], yfeed); pwr_flag(ctx, vpll[0], ypb)
    cv = C(ctx, 1240, "100nF", vphy[0] - 6.35, ypb, horiz=True, ref_at=(vphy[0] - 11.5, ypb + 3.4), val_at=(vphy[0] - 11.5, ypb + 3.7))
    s.wire(vphy[0], ypb, *cv.pin(2)); s.power("GND", *cv.pin(1), down=True, rot=270)
    yv = vio[0][1] - 11.43
    for p in vio:
        s.wire(*p, p[0], yv)
    s.wire(vio[0][0], yv, vio[-1][0], yv); rail(ctx, vio[-1][0], yv, "+3V3", stub=5.08)
    for p in vio[1:-1]:
        s.junction(p[0], yv)
    gnds = [u.pin(n) for n in ("1", "5", "11", "15", "25", "35", "47", "51", "10")]
    yg = max(p[1] for p in gnds) + 3.81
    for p in gnds:
        s.wire(*p, p[0], yg)
    s.wire(min(p[0] for p in gnds), yg, max(p[0] for p in gnds), yg); gnd(ctx, max(p[0] for p in gnds), yg, stub=2.54)
    for p in sorted(gnds)[1:-1]:
        s.junction(p[0], yg)
    decouple(ctx, 1250, 230.0, 60.0, "+1V8_FTDI", ["4.7uF", "100nF", "100nF", "100nF"], label="1.8 V: 100 nF per VCORE pin")
    decouple(ctx, 1260, 230.0, 82.0, "+3V3", ["4.7uF", "100nF", "100nF", "100nF", "100nF"], label="VCCIO x4, VREGIN")
    # channel A = JTAG, channel B = UART
    jt = [("16", "JTAG_TCK"), ("17", "JTAG_TDI"), ("18", "JTAG_TDO"), ("19", "JTAG_TMS")]
    # the 33 R on the 2.54 mm pin pitch: designators only, in the half row above each wire; "33 Ω each" once
    s.text(u.pin("16")[0] + 5.9, u.pin("16")[1] - 2.6, "33 Ω each", size=0.85)
    for pin_, nm in jt:
        p = u.pin(pin_)
        r = R(ctx, 1270, "33R", p[0] + 8.89, p[1], horiz=True, ref_at=(p[0] + 1.27, p[1] - 1.27), val_at=(p[0] + 1.27, p[1] + 1.27), fsize=1.0, hide_value=True)      # the designator on the wire between pin and body (above a body it met the row above)
        s.wire(*p, *r.pin(1)); s.wire(*r.pin(2), r.pin(2)[0] + 7.62, p[1]); s.hlabel(r.pin(2)[0] + 7.62, p[1], nm, shape="output" if nm != "JTAG_TDO" else "input")
        hp.append((nm, "output" if nm != "JTAG_TDO" else "input"))
    label_node(ctx, u.pin("16")[0] + 2.0, u.pin("16")[1] - 5.5, "channel A: MPSSE JTAG (TCK TDI TDO TMS)", side="right", size=0.85)
    ub = [("38", "UART_RX", "output"), ("39", "UART_TX", "input"), ("40", "FTDI_RTS", "output"), ("43", "FTDI_DTR", "output")]
    s.text(u.pin("38")[0] + 5.9, u.pin("38")[1] - 2.6, "33 Ω each", size=0.85)
    for pin_, nm, shape in ub:
        p = u.pin(pin_)
        r = R(ctx, 1280, "33R", p[0] + 8.89, p[1], horiz=True, ref_at=(p[0] + 1.27, p[1] - 1.27), val_at=(p[0] + 1.27, p[1] + 1.27), fsize=1.0, hide_value=True)
        s.wire(*p, *r.pin(1)); s.wire(*r.pin(2), r.pin(2)[0] + 7.62, p[1]); s.hlabel(r.pin(2)[0] + 7.62, p[1], nm, shape=shape)
        hp.append((nm, shape))
    label_node(ctx, u.pin("38")[0] + 2.0, u.pin("38")[1] - 5.5, "channel B: serial console (TXD -> FPGA RX), RTS/DTR as FPGA inputs", side="right", size=0.85)
    for n in ("21", "22", "23", "24", "26", "27", "28", "29", "30", "32", "33", "34", "41", "44", "45", "46", "48", "52", "53", "54", "55", "57", "58", "59", "60", "36"):
        s.nc(*u.pin(n))

    # --- FPGA USB-C: D- straight, D+ on its own row below, pull-up diode underneath ------
    dp2, dm2, vb2 = usbc(ctx, "J502", 50.0, 280.0, ids, "USB-C: USER (a soft USB device on FPGA pins)", 1300)
    xv2 = vb2[0] + 25.4
    s.wire(*vb2, xv2, vb2[1])
    label_node(ctx, vb2[0] - 48.0, vb2[1] - 1.0, "VBUS not used: this port does not power the board", side="right", size=0.85)
    rv = R(ctx, 1300, "100k", xv2, vb2[1] + 6.35, side="right"); s.wire(xv2, vb2[1], *rv.pin(1)); gnd(ctx, *rv.pin(2), stub=1.27)
    f6, f4 = esd(ctx, "U504", dp2, dm2, vb2)
    xs = f6[0] + 15.24          # 27 R centres
    xpd = f6[0] + 8.89          # 15 k pull-downs
    y_dp = 302.26
    x_dn_end, x_dp_end, x_join = f6[0] + 41.91, f6[0] + 62.23, f6[0] + 57.15
    # D-
    r_n = R(ctx, 1320, "27R", xs, f6[1], horiz=True, ref_at=(xs - 2.6, f6[1] - 1.6), val_at=(xs + 4.0, f6[1] - 1.6))
    s.wire(*f6, *r_n.pin(1)); s.junction(xpd, f6[1])
    pd_n = R(ctx, 1320, "15k", xpd, f6[1] + 6.35, side="right"); s.wire(xpd, f6[1], *pd_n.pin(1)); gnd(ctx, *pd_n.pin(2), stub=1.27)
    s.wire(*r_n.pin(2), x_dn_end, f6[1]); s.hlabel(x_dn_end, f6[1], "USB_DN", shape="bidirectional")
    # D+
    xj = f4[0] + 2.54
    s.wire(*f4, xj, f4[1]); s.wire(xj, f4[1], xj, y_dp); s.wire(xj, y_dp, xpd, y_dp)
    r_p = R(ctx, 1310, "27R", xs, y_dp, horiz=True, ref_at=(xs - 2.6, y_dp - 1.6), val_at=(xs + 4.0, y_dp - 1.6))
    s.wire(xpd, y_dp, *r_p.pin(1)); s.junction(xpd, y_dp)
    pd_p = R(ctx, 1310, "15k", xpd, y_dp + 6.35, side="right"); s.wire(xpd, y_dp, *pd_p.pin(1)); gnd(ctx, *pd_p.pin(2), stub=1.27)
    s.wire(*r_p.pin(2), x_dp_end, y_dp); s.hlabel(x_dp_end, y_dp, "USB_DP", shape="bidirectional")
    hp += [("USB_DP", "bidirectional"), ("USB_DN", "bidirectional")]
    # pull-up: FPGA pin -> 1 k -> 1N4148 -> D+
    y_pu = y_dp + 10.16
    x_lab = f6[0] + 22.86
    s.hlabel(x_lab, y_pu, "USB_PULLUP", shape="input", rot=180); hp.append(("USB_PULLUP", "input"))
    rpu = R(ctx, 1310, "1k", x_lab + 6.35, y_pu, horiz=True, ref_at=(x_lab + 3.8, y_pu - 1.6), val_at=(x_lab + 10.3, y_pu - 1.6))
    s.wire(x_lab, y_pu, *rpu.pin(1))
    dpu = part(ctx, "Device:D", "D501", "1N4148W", "SOD123", rpu.pin(2)[0] + 7.62, y_pu, rot=180,
               ref_at=(rpu.pin(2)[0] + 3.8, y_pu - 2.3), val_at=(rpu.pin(2)[0] + 3.8, y_pu + 1.8), lcsc="C81598")
    s.wire(*rpu.pin(2), *dpu.pin(2)); s.wire(*dpu.pin(1), x_join, y_pu); s.wire(x_join, y_pu, x_join, y_dp); s.junction(x_join, y_dp)
    label_node(ctx, x_lab + 2.0, y_pu + 6.0, "drive high to appear as a full-speed device", side="right", size=0.85)

    # --- GPDI / mini HDMI ---------------------------------------------------------------
    xh = 440.0
    hj = part(ctx, ids["hdmi"], "J503", "mini HDMI", "HDMI_C", xh, 110.0, ref_at=(xh - 9.0, 76.0), val_at=(xh - 9.0, 146.0))
    s.text(xh - 80.0, 70.0, "GPDI (HDMI out, 22 nF coupled, ULX3S style)", size=1.6, bold=True)
    pairs = [("2", "GPDI_D2_P"), ("3", "GPDI_D2_N"), ("5", "GPDI_D1_P"), ("6", "GPDI_D1_N"), ("8", "GPDI_D0_P"), ("9", "GPDI_D0_N"), ("11", "GPDI_CK_P"), ("12", "GPDI_CK_N")]
    for pin_, nm in pairs:
        p = hj.pin(pin_)
        # fields in the half row above the wire, small, so the eight rows stay readable
        c = C(ctx, 1400, "22nF", p[0] - 10.16, p[1], horiz=True, ref_at=(p[0] - 19.5, p[1] - 0.6), val_at=(p[0] - 7.6, p[1] - 2.0), fsize=1.0)      # (designator left of the plates since build 28)
        s.wire(*c.pin(2), *p); s.wire(*c.pin(1), c.pin(1)[0] - 12.7, p[1]); s.hlabel(c.pin(1)[0] - 12.7, p[1], nm, shape="input", rot=180)
        hp.append((nm, "input"))
    # the five grounds and the shield on one bar
    gb = [hj.pin(n) for n in ("1", "4", "7", "10", "13", "20", "21", "22", "23")]
    xg = gb[0][0] - 3.81
    for p in gb:
        s.wire(*p, xg, p[1])
    s.wire(xg, gb[0][1], xg, gb[-1][1])
    for p in gb[1:-1]:
        s.junction(xg, p[1])
    gnd(ctx, xg, gb[-1][1], stub=2.54)
    p5, cec, util, scl, sda, hpd = (hj.pin(n) for n in ("18", "14", "17", "15", "16", "19"))
    # DDC level shifter: PCA9306, its SCL/SDA rows lined up with the jack's so the lines are straight
    xl = xh - 90.0
    yl = scl[1] - 2.54
    ls = part(ctx, "ours:PCA9306", "U505", "PCA9306DC1Z", "VSSOP8", xl, yl, ref_at=(xl - 6.0, yl - 11.5), val_at=(xl + 3.0, yl + 15.5))
    s1, d1, v1, s2, d2, v2, en, g1 = (ls.pin(n) for n in ("3", "4", "2", "6", "5", "7", "8", "1"))
    s.wire(*s2, *scl); s.wire(*d2, *sda)
    ladder(ctx, 1420, [(s2[0] + 19.84, s2[1]), (s2[0] + 27.46, d2[1])], "4.7k", "+5V", fsize=1.0)
    s.wire(*s1, s1[0] - 25.4, s1[1]); s.hlabel(s1[0] - 25.4, s1[1], "GPDI_SCL", shape="bidirectional", rot=180)
    s.wire(*d1, d1[0] - 25.4, d1[1]); s.hlabel(d1[0] - 25.4, d1[1], "GPDI_SDA", shape="bidirectional", rot=180)
    hp += [("GPDI_SCL", "bidirectional"), ("GPDI_SDA", "bidirectional")]
    ladder(ctx, 1430, [(s1[0] - 7.62, s1[1]), (s1[0] - 15.24, d1[1])], "3.3k", "+3V3", side="left", fsize=1.0)
    s.wire(*v1, v1[0] - 2.54, v1[1]); rail(ctx, v1[0] - 2.54, v1[1], "+3V3", stub=2.54)
    # VREF2 and EN tied, 200 k up to +5 V; the monitor's +5 V (through the polyfuse) shares that flag
    xv = v2[0] + 2.54
    s.wire(*v2, xv, v2[1]); s.wire(*en, xv, en[1]); s.wire(xv, en[1], xv, v2[1]); s.junction(xv, v2[1])
    r2 = R(ctx, 1440, "200k", xv, v2[1] - 5.08, side="right"); s.wire(xv, v2[1], *r2.pin(2))
    y5 = r2.pin(1)[1] - 2.54
    s.wire(*r2.pin(1), xv, y5); rail(ctx, xv, y5, "+5V", stub=0); s.junction(xv, y5)
    gnd(ctx, *g1, stub=2.54)
    f = part(ctx, "Device:Polyfuse", "F501", "0.5A", "F1812", p5[0] - 10.16, p5[1], rot=90, lcsc="C17313",
             ref_at=(p5[0] - 22.0, p5[1] - 0.6), val_at=(p5[0] - 12.5, p5[1] - 2.6), fsize=1.0)
    fl, fr = sorted([f.pin(1), f.pin(2)])
    x5 = xv + 10.16
    s.wire(*fr, *p5); s.wire(*fl, x5, fl[1]); s.wire(x5, fl[1], x5, y5); s.wire(x5, y5, xv, y5)
    rc = R(ctx, 1410, "470R", cec[0] - 10.16, cec[1], horiz=True, ref_at=(cec[0] - 13.5, cec[1] + 2.5), val_at=(cec[0] - 7.5, cec[1] + 1.2), fsize=1.0); s.wire(*rc.pin(2), *cec)
    s.wire(*rc.pin(1), rc.pin(1)[0] - 2.54, cec[1]); s.hlabel(rc.pin(1)[0] - 2.54, cec[1], "GPDI_CEC", shape="bidirectional", rot=180); hp.append(("GPDI_CEC", "bidirectional"))      # (a short wire: the label's name reached the DDC pull-ups)
    s.nc(*util)
    rh = R(ctx, 1410, "4.7k", hpd[0] - 10.16, hpd[1], horiz=True, ref_at=(hpd[0] - 13.5, hpd[1] + 2.5), val_at=(hpd[0] - 7.5, hpd[1] + 1.2), fsize=1.0); s.wire(*rh.pin(2), *hpd)
    s.wire(*rh.pin(1), rh.pin(1)[0] - 12.7, hpd[1]); s.hlabel(rh.pin(1)[0] - 12.7, hpd[1], "GPDI_HPD", shape="output", rot=180); hp.append(("GPDI_HPD", "output"))
    xpd_h = rh.pin(1)[0] - 6.35
    rpd = R(ctx, 1410, "10k", xpd_h, hpd[1] + 6.35, side="right"); s.junction(xpd_h, hpd[1]); s.wire(xpd_h, hpd[1], *rpd.pin(1)); gnd(ctx, *rpd.pin(2), stub=1.27)
    s.text(xl - 42.0, gb[-1][1] + 6.0, "DDC I2C level shifted: 3.3 k pull-ups on the FPGA side,\n"
                                       "4.7 k to +5 V on the cable side; EN tied to VREF2 through 200 k\n"
                                       "as the datasheet asks. +5 V to the monitor through a 500 mA polyfuse.\n"
                                       "HPD: the sink pulls it to +5 V, so 4.7 k in series and 10 k down\n"
                                       "put 3.2 V on the FPGA pin (the ECP5's limit is 3.6 V).", size=0.85, justify="left top")

    # --- microSD: pull-ups as a staircase, each line turning up at its own label ------------
    xs_ = 440.0
    sd = part(ctx, ids["usd"], "J504", "microSD", "USD", xs_, 260.0, ref_at=(xs_ - 9.0, 238.0), val_at=(xs_ - 9.0, 283.0))
    s.text(xs_ - 60.0, 232.0, "microSD, 4-bit SD bus", size=1.6, bold=True)
    for k, (pin_, nm) in enumerate((("1", "SD_D2"), ("2", "SD_D3"), ("3", "SD_CMD"), ("7", "SD_D0"), ("8", "SD_D1"))):
        p = sd.pin(pin_)
        xk = p[0] - 12.7 - k * 15.24
        s.wire(*p, xk, p[1]); s.hlabel(xk, p[1], nm, shape="bidirectional", rot=180)
        pullup(ctx, 1500, xk, p[1], "47k", "+3V3")
        hp.append((nm, "bidirectional"))
    p = sd.pin("5"); s.wire(*p, p[0] - 12.7, p[1]); s.hlabel(p[0] - 12.7, p[1], "SD_CLK", shape="bidirectional", rot=180); hp.append(("SD_CLK", "bidirectional"))
    vdd, vss = sd.pin("4"), sd.pin("6")
    s.wire(*vdd, vdd[0] - 5.08, vdd[1]); rail(ctx, vdd[0] - 5.08, vdd[1], "+3V3", stub=3.81)
    s.wire(*vss, vss[0] - 5.08, vss[1]); gnd(ctx, vss[0] - 5.08, vss[1], stub=0)
    for pin_ in ("9", "10"):
        s.nc(*sd.pin(pin_))
    sh = sd.pin("SH"); s.wire(*sh, sh[0] - 5.08, sh[1]); gnd(ctx, sh[0] - 5.08, sh[1], stub=2.54)
    decouple(ctx, 1510, 480.0, 300.0, "+3V3", ["10uF", "100nF"], label="SD card supply")
    return hp
