"""Gigabit Ethernet: RTL8211F-CG (RGMII at 3.3 V), G2406S magnetics with four
separate chip-side centre taps, a plain shielded RJ45, the straps, the LEDs.

The PHY is drawn as three units.  Unit A (RGMII and management) on the left;
unit B (the line side: MDI pairs out of its right edge, LEDs and crystal on
its left) beside it; the magnetics and the jack to the right, placed so that
the MDI rows line up and the eight pair wires are straight lines; unit C
(power) along the bottom."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from draw import *


def pin_dy(lib_id, unit, pin):
    """y of `pin` relative to the symbol's placement point, for lining rows up."""
    t = kisch.Sch("t", "t.kicad_sch")
    return t.sym(lib_id, 0.0, 0.0, unit=unit, ref="X", value="").pin(pin)[1]


def draw(sch, ids, fpga):
    ctx = Ctx(sch, "ETH")
    s = sch
    s.text(20, 22, "Gigabit Ethernet: RTL8211F-CG, RGMII, discrete magnetics", size=3.0, bold=True)
    note(ctx, 20, 26, "The FPGA talks RGMII (4-bit DDR at 125 MHz) at 3.3 V to the PHY; 22 Ω series resistors damp the "
                      "lines. The PHY makes its own 1.0 V core with an internal switcher (REG_OUT, 2.2 µH). Straps on the "
                      "LED pins are sampled at reset: CFG_EXT = 1 (external 3.3 V on DVDD_RG) and CFG_LDO[1:0] = 00 "
                      "(3.3 V I/O pads), PHY address 1, TX delay off, RX delay on (the gateware's RGMII PHY expects "
                      "the 2 ns receive delay in the PHY and adds its own transmit delay). The magnetics are a G2406S "
                      "module: each chip-side centre tap gets its own 100 nF to ground, as a voltage-mode driver wants; "
                      "the line-side taps go to a Bob Smith termination (75 Ω each, 1 nF / 2 kV to ground).",
         w=340, size=1.1)
    hp = []
    # ---- unit A: RGMII and management ------------------------------------------------
    xp = 150.0
    ph = part(ctx, ids["phy"], "U401", "RTL8211F-CG", "WQFN40", xp, 120.0, unit=1, ref_at=(xp - 13.0, 68.0), val_at=(xp - 13.0, 172.0))
    tx = [("15", "ETH_TXD3"), ("16", "ETH_TXD2"), ("17", "ETH_TXD1"), ("18", "ETH_TXD0"), ("20", "ETH_TXC"), ("19", "ETH_TX_CTL")]
    rx = [("22", "ETH_RXD3"), ("23", "ETH_RXD2"), ("24", "ETH_RXD1"), ("25", "ETH_RXD0"), ("27", "ETH_RXC"), ("26", "ETH_RX_CTL")]
    for group, shape in ((tx, "input"), (rx, "output")):
        members = []
        for pin_, nm in group:
            p = ph.pin(pin_)
            r = R(ctx, 900, "22R", p[0] - 8.89, p[1], horiz=True, ref_at=(p[0] - 11.5, p[1] - 1.5), val_at=(p[0] - 5.0, p[1] - 1.5))
            s.wire(*r.pin(2), *p)
            if "TXD" in nm or "RXD" in nm:
                members.append((r.pin(1)[0], p[1], nm))
            else:
                s.wire(*r.pin(1), r.pin(1)[0] - 10.16, p[1]); s.hlabel(r.pin(1)[0] - 10.16, p[1], nm, shape=shape, rot=180)
                hp.append((nm, shape))
        bus = "ETH_TXD[3..0]" if group is tx else "ETH_RXD[3..0]"
        bus_out(ctx, members[0][0] - 10.16, 0, bus, members, x_end=members[0][0] - 25.4, shape=shape)
        hp.append((bus, shape))
    s.text(xp - 70.0, ph.pin("15")[1] - 6.0, "RGMII, 3.3 V, 125 MHz DDR", size=1.0, bold=True)
    # management: hierarchical labels at one x, pull-ups above each wire
    mdc, mdio, intb, rst = ph.pin("13"), ph.pin("14"), ph.pin("31"), ph.pin("12")
    xh = mdc[0] - 27.94
    s.wire(*mdc, xh, mdc[1]); s.hlabel(xh, mdc[1], "ETH_MDC", shape="input", rot=180)
    s.wire(*mdio, xh, mdio[1]); s.hlabel(xh, mdio[1], "ETH_MDIO", shape="bidirectional", rot=180)
    pullup(ctx, 900, mdio[0] - 7.62, mdio[1], "4.7k", "+3V3_ETH")
    s.wire(*intb, xh, intb[1]); s.hlabel(xh, intb[1], "ETH_INT_N", shape="output", rot=180)
    pullup(ctx, 900, intb[0] - 7.62, intb[1], "4.7k", "+3V3_ETH")
    rr = R(ctx, 900, "330R", rst[0] - 19.05, rst[1], horiz=True, ref_at=(rst[0] - 21.6, rst[1] - 1.6), val_at=(rst[0] - 21.6, rst[1] + 1.3))
    s.wire(*rr.pin(2), *rst); s.wire(*rr.pin(1), xh, rst[1]); s.hlabel(xh, rst[1], "ETH_RST_N", shape="input", rot=180)
    pullup(ctx, 900, rst[0] - 10.16, rst[1], "4.7k", "+3V3_ETH")
    cr = C(ctx, 900, "1uF", rst[0] - 3.81, rst[1] + 6.35, side="right"); s.junction(rst[0] - 3.81, rst[1])
    s.wire(rst[0] - 3.81, rst[1], *cr.pin(1)); gnd(ctx, *cr.pin(2), stub=1.27)
    label_node(ctx, 62.0, mdc[1] + 9.0, "MDIO, INTB, RST: 4.7 k up\n(MDIO's 1.5 k is for a long bus)\nRST: 330 Ω + 1 µF, ~10 ms after power", side="right", size=0.85)
    hp += [("ETH_MDC", "input"), ("ETH_MDIO", "bidirectional"), ("ETH_RST_N", "input"), ("ETH_INT_N", "output")]

    # ---- unit B: line side; LEDs and crystal on its left --------------------------------
    xl, yl = 150.0, 232.0
    ln = part(ctx, ids["phy"], "U401", "RTL8211F-CG", "WQFN40", xl, yl, unit=2, ref_at=(xl - 13.0, yl - 32.0), val_at=(xl - 13.0, yl + 32.0))
    l0, l1, l2 = ln.pin("32"), ln.pin("33"), ln.pin("34")
    # LED0 / CFG_EXT = 1: LED to +3V3_ETH (active low) plus a 4.7 k pull-up, all on one row
    xn = l0[0] - 7.62
    r0 = R(ctx, 960, "330R", xn - 6.35, l0[1], horiz=True)
    s.wire(*l0, *r0.pin(2)); pullup(ctx, 960, xn, l0[1], "4.7k", "+3V3_ETH")
    d0 = part(ctx, "Device:LED", "D401", "green", "LED0603", xn - 17.78, l0[1], rot=180,
              ref_at=(xn - 20.5, l0[1] + 3.5), val_at=(xn - 20.5, l0[1] + 3.8), lcsc="C12624")
    k0, a0 = d0.pin(1), d0.pin(2)
    s.wire(*r0.pin(1), *k0); s.wire(*a0, a0[0] - 2.54, a0[1]); rail(ctx, a0[0] - 2.54, a0[1], "+3V3_ETH", stub=2.54)
    label_node(ctx, xl - 60.0, l0[1] + 10.5, "LED0: 10M link (active low); strap CFG_EXT = 1, 3.3 V I/O", side="right", size=0.85)
    # LED1, LED2 / CFG_LDO = 00: LED to ground (active high) plus a 4.7 k pull-down, hanging in columns
    for lp, nm, dref, xc, base in ((l1, "LED1: 100M link; strap CFG_LDO0 = 0", "D402", xl - 92.28, 970),
                                   (l2, "LED2: 1000M link; strap CFG_LDO1 = 0", "D403", xl - 69.42, 980)):
        xr = xc + 10.16
        s.wire(*lp, xc, lp[1]); s.junction(xr, lp[1])
        r1 = R(ctx, base, "330R", xc, lp[1] + 5.08, side="right")
        s.wire(xc, lp[1], *r1.pin(1))
        d1 = part(ctx, "Device:LED", dref, "green", "LED0603", xc, lp[1] + 15.24, rot=90,
                  ref_at=(xc + 2.0, lp[1] + 13.5), val_at=(xc + 2.0, lp[1] + 16.5), lcsc="C12624")
        k1, a1 = d1.pin(1), d1.pin(2)
        s.wire(*r1.pin(2), *a1); gnd(ctx, *k1, stub=2.54)
        rp = R(ctx, base, "4.7k", xr, lp[1] + 5.08, side="right"); s.wire(xr, lp[1], *rp.pin(1)); gnd(ctx, *rp.pin(2), stub=2.54)
    label_node(ctx, xl - 79.0, l1[1] + 9.5, "LED1: 100M link (active high); strap CFG_LDO0 = 0", side="right", size=0.85)
    label_node(ctx, xl - 95.0, l2[1] + 23.0, "LED2: 1000M link (active high); strap CFG_LDO1 = 0", side="right", size=0.85)
    # crystal on XTAL_IN/OUT: jogs of 2.54 to the crystal's 7.62 mm pin pitch
    xi, xo, clko = ln.pin("36"), ln.pin("37"), ln.pin("35")
    # four pads: 1 and 3 are the crystal, 2 and 4 the grounded case (the YXC drawing)
    y = part(ctx, "Device:Crystal_GND24", "Y401", "25MHz", "XTAL3225", xi[0] - 15.24, (xi[1] + xo[1]) / 2, rot=270,
             ref_at=(xi[0] - 12.5, xi[1] - 1.3), val_at=(xi[0] - 12.5, xi[1] + 4.3), lcsc="C9006")
    ya, yb = sorted([y.pin(1), y.pin(3)], key=lambda q: q[1])
    # (KiCad draws the symbol's two ground pins on one point: one stub, pointing away from the crystal, serves both)
    g2_ = y.pin(2); dx_ = 2.54 if g2_[0] > y.x else -2.54
    s.wire(*g2_, g2_[0] + dx_, g2_[1]); s.power("GND", g2_[0] + dx_, g2_[1], down=True, rot=90 if dx_ > 0 else 270)
    xj = xi[0] - 6.35
    s.wire(*xi, xj, xi[1]); s.wire(xj, xi[1], xj, ya[1]); s.wire(xj, ya[1], *ya)
    s.wire(*xo, xj, xo[1]); s.wire(xj, xo[1], xj, yb[1]); s.wire(xj, yb[1], *yb)
    for pp, base in ((ya, 975), (yb, 976)):
        c = C(ctx, base, "18pF", pp[0] - 10.16, pp[1], horiz=True); s.wire(*pp, *c.pin(2)); s.wire(*c.pin(1), c.pin(1)[0] - 2.54, pp[1]); gnd(ctx, c.pin(1)[0] - 2.54, pp[1], stub=0)
    s.nc(*clko)
    label_node(ctx, xl - 62.0, yb[1] + 9.0, "25 MHz, 12 pF crystal, 18 pF loads", side="right", size=0.85)

    # ---- magnetics, placed so its TD rows are unit B's MDI rows ------------------------
    xm = xl + 100.0
    ym = ln.pin("1")[1] - pin_dy(ids["mag"], 1, "3")
    mag = part(ctx, ids["mag"], "T401", "G2406S", "MAG24", xm, ym, ref_at=(xm - 11.0, ym - 25.0), val_at=(xm - 11.0, ym + 24.0))
    # Every pair's P goes to the transformer's "-" end and N to its "+" end, on BOTH sides (so the polarity
    # through the transformer is unchanged -- an end is only a name).  Why: the PHY's pads run N-above-P and
    # the jack's pins P-above-N, so one side of the transformer has to cross each pair; the layout puts that
    # crossing at the PHY, where every line changes layer anyway (pcb/floorplan.py ethernet_lines).
    pairs = [("1", "2", "3", "2"), ("4", "5", "6", "5"), ("6", "7", "9", "8"), ("9", "10", "12", "11")]
    for k, (pp, pn, tp, tn) in enumerate(pairs):
        a, b = ln.pin(pp), ln.pin(pn)
        ta, tb = mag.pin(tp), mag.pin(tn)
        assert abs(a[1] - ta[1]) < 0.01 and abs(b[1] - tb[1]) < 0.01, "MDI rows not aligned"
        s.wire(*a, *ta); s.wire(*b, *tb)
        s.label(a[0] + 2.0, a[1] - 0.3, "ETH_MDI%d_P" % k, size=0.9); s.label(b[0] + 2.0, b[1] - 0.3, "ETH_MDI%d_N" % k, size=0.9)
    label_node(ctx, ln.pin("1")[0] + 20.0, ln.pin("1")[1] - 4.0, "100 Ω differential pairs; P on the transformer's - ends, N on its + ends, both sides (see the layout)", side="right", size=0.85)
    # chip-side centre taps: one 100 nF each, staggered so no cap sits under another tap's wire
    for k, tct in enumerate(("1", "4", "7", "10")):
        ct = mag.pin(tct)
        xc = ct[0] - 40.64 + k * 10.16
        c = C(ctx, 910 + 10 * k, "100nF", xc, ct[1] + 5.08, side="left")
        s.wire(*ct, xc, ct[1]); s.wire(xc, ct[1], *c.pin(1)); gnd(ctx, *c.pin(2), stub=0)
    label_node(ctx, mag.pin("10")[0] - 42.0, mag.pin("10")[1] + 18.0, "four SEPARATE centre taps, 100 nF each", side="right", size=0.85)
    # line side to the jack, pin 1 on the MX1+ row: A -> 1,2  B -> 3,6  C -> 4,5  D -> 7,8
    xjk = xm + 135.0
    yj = mag.pin("22")[1] - pin_dy(ids["rj45"], 1, "1")
    j = part(ctx, ids["rj45"], "J401", "RJ45", "RJ45", xjk, yj, ref_at=(xjk - 8.0, yj - 16.0), val_at=(xjk - 8.0, yj + 18.0))
    # jack pin -> (magnetics pin, pair, jog channel).  Channels are ordered so
    # that where one wire's magnetics row is another's jack row, the first
    # finishes before the second starts (no two horizontals on one row touch).
    jack = {1: ("22", 0, None), 2: ("23", 0, None), 3: ("19", 1, 0), 6: ("20", 1, 1), 4: ("16", 2, 2), 5: ("17", 2, 3), 7: ("13", 3, 4), 8: ("14", 3, 5)}
    for pin_j, (pin_t, k, chan) in jack.items():
        a = mag.pin(pin_t); b = j.pin(str(pin_j))
        if chan is None:
            s.wire(*a, *b)
        else:
            xk = a[0] + 10.16 + chan * 1.27
            s.wire(*a, xk, a[1]); s.wire(xk, a[1], xk, b[1]); s.wire(xk, b[1], *b)
        s.label(a[0] + 1.0, a[1] - 0.3, "ETH_LAN%d_%s" % (k, "P" if pin_j in (1, 3, 4, 7) else "N"), size=0.85)
    s13, s14 = j.pin("13"), j.pin("14")                                   # the shield's two legs, both to ground
    xs_ = s13[0] - 3.81
    s.wire(*s13, xs_, s13[1]); s.wire(*s14, xs_, s14[1]); s.wire(xs_, min(s13[1], s14[1]), xs_, max(s13[1], s14[1]))
    gnd(ctx, xs_, max(s13[1], s14[1]), stub=2.54)
    # Bob Smith: line-side centre taps -> 75R each -> node -> 1nF 2kV -> ground
    xbs = mag.pin("24")[0] + 20.32
    ybs = mag.pin("15")[1] + 17.78
    for i, pin_t in enumerate(("24", "21", "18", "15")):
        ct = mag.pin(pin_t)
        xr = xbs + (3 - i) * 7.62
        r = R(ctx, 950, "75R", xr, ybs - 6.35, side="right")
        s.wire(*ct, xr, ct[1]); s.wire(xr, ct[1], *r.pin(1)); s.wire(*r.pin(2), xr, ybs)
    s.wire(xbs, ybs, xbs + 3 * 7.62 + 10.16, ybs)
    for i in range(1, 4):
        s.junction(xbs + i * 7.62, ybs)
    cbs = C(ctx, 950, "1nF 2kV", xbs + 3 * 7.62 + 10.16, ybs + 5.08, fp="C_1206", side="right")
    s.wire(xbs + 3 * 7.62 + 10.16, ybs, *cbs.pin(1)); gnd(ctx, *cbs.pin(2), stub=1.27)
    label_node(ctx, xbs, ybs + 12.0, "Bob Smith termination; the jack's shield goes to the same ground", side="right", size=0.85)

    # ---- unit C: power, regulator, RSET --------------------------------------------------
    pw = part(ctx, ids["phy"], "U401", "RTL8211F-CG", "WQFN40", 150.0, 300.0, unit=3, ref_at=(125.0, 298.0), val_at=(125.0, 301.0))
    # the dashed box: three units, one chip
    gx0, gx1 = xp - 25.4, xp + 25.4
    s.rect(gx0, 64.0, gx1 - gx0, 258.0, style="dash", width=0.25)
    s.text(gx0 + 2.0, 62.5, "U401 RTL8211F-CG: one chip, drawn as RGMII side (A), line side (B) and power (C)", size=1.0, bold=True)
    a33 = [pw.pin(n) for n in ("11", "40", "29", "28")]
    v10 = [pw.pin(n) for n in ("3", "8", "38", "21")]
    yb = a33[0][1] - 5.08
    for p in a33:
        s.wire(*p, p[0], yb)
    s.wire(a33[0][0], yb, a33[-1][0], yb); rail(ctx, a33[0][0], yb, "+3V3_ETH", stub=7.62)
    yb1 = v10[0][1] - 5.08
    for p in v10:
        s.wire(*p, p[0], yb1)
    s.wire(v10[0][0], yb1, v10[-1][0], yb1); rail(ctx, v10[-1][0], yb1, "+1V0_PHY", stub=7.62)
    g = pw.pin("41"); gnd(ctx, *g, stub=2.54)
    ro, rs = pw.pin("30"), pw.pin("39")
    # a POWER inductor: Realtek asks for one that withstands 600 mA with ESR under 0.8 ohm (Table 50, note 4: a
    # lesser one "may damage the switching regulator").  Builds 1-23 had an 0805 multilayer chip inductor rated
    # 50 mA / 0.6 ohm (CMI201209U2R2KT) here.  The bucks' 4 x 4 mm SWPA4030S2R2NT (2.2 uH, 2.95 A, 40 mohm) now.
    l = part(ctx, "Device:L", "L401", "2.2uH", "L4030", ro[0] + 10.16, ro[1], rot=90, ref_at=(ro[0] + 7.5, ro[1] - 3.0), val_at=(ro[0] + 7.5, ro[1] + 2.0), lcsc="C279948")
    la, lb = sorted([l.pin(1), l.pin(2)])
    s.wire(*ro, *la); s.wire(*lb, lb[0] + 5.08, lb[1]); rail(ctx, lb[0] + 5.08, lb[1], "+1V0_PHY", stub=3.81); pwr_flag(ctx, lb[0] + 2.54, lb[1])
    label_node(ctx, lb[0] + 8.0, lb[1] + 0.5, "internal 1.0 V switcher output: feeds only this chip; the inductor must take 600 mA (a power inductor, not a chip one)", side="right", size=0.85)
    rr_ = R(ctx, 980, "2.49k", rs[0] + 7.62, rs[1] + 5.08, side="right"); s.wire(*rs, rs[0] + 7.62, rs[1]); s.wire(rs[0] + 7.62, rs[1], *rr_.pin(1)); gnd(ctx, *rr_.pin(2), stub=1.27)
    label_node(ctx, rs[0] + 12.0, rs[1] + 0.5, "line driver current reference, 1 %", side="right", size=0.85)
    decouple(ctx, 985, 230.0, 335.0, "+3V3_ETH", ["10uF", "100nF", "100nF", "100nF", "100nF"], label="AVDD33 x2, DVDD33, DVDD_RG: 100 nF each at the pin")
    decouple(ctx, 990, 230.0, 362.0, "+1V0_PHY", ["10uF", "100nF", "100nF", "100nF", "100nF"], label="switcher output 10 µF X5R, 100 nF per 1.0 V pin")
    note(ctx, 330.0, 335.0, "+3V3_ETH is +3V3 through a ferrite bead (power sheet). The PHY address strap is the default "
                            "(RXD3 pulled up internally): PHYAD = 1. No strap resistors on RXD0/RXD1: TXDLY = 0, RXDLY = 1.",
         w=120, size=0.95)
    return hp
