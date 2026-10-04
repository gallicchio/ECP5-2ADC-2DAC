"""Power: 5 V from the FTDI USB-C (or a bench supply), two bucks (3.3 V, 1.1 V),
LDOs for the quiet rails, the ±4.5 V analog rails, and the ferrite-isolated
feeds.  Power flows top to bottom and left to right."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from draw import *


def buck(ctx, base, x, y, uref, vout, r1, r2, note_text):
    """TLV62569 buck at (x, y): VIN on the left, VOUT bar to the right."""
    s = ctx.s
    u = part(ctx, "Regulator_Switching:TLV62569DBV", uref, "TLV62569DBVR", "SOT23-5", x, y, ref_at=(x - 7.0, y - 7.5), val_at=(x - 7.0, y + 8.0))
    en, g, sw, vin, fb = u.pin("1"), u.pin("2"), u.pin("3"), u.pin("4"), u.pin("5")
    s.wire(*vin, vin[0] - 7.62, vin[1]); s.wire(*en, vin[0] - 5.08, en[1]); s.wire(vin[0] - 5.08, en[1], vin[0] - 5.08, vin[1])
    rail(ctx, vin[0] - 7.62, vin[1], "+5V", stub=5.08)
    ci = C(ctx, base, "10uF", vin[0] - 12.7, vin[1] + 5.08, fp="C0603", side="left"); s.wire(vin[0] - 7.62, vin[1], vin[0] - 12.7, vin[1]); s.wire(vin[0] - 12.7, vin[1], *ci.pin(1)); gnd(ctx, *ci.pin(2), stub=1.27)
    gnd(ctx, *g, stub=2.54)
    l = part(ctx, "Device:L", "L6%02d" % (base // 100), "2.2uH", "L4030", sw[0] + 8.89, sw[1], rot=90, ref_at=(sw[0] + 5.5, sw[1] - 3.5), val_at=(sw[0] + 5.5, sw[1] + 2.0), lcsc="C279948")
    la, lb = l.pin(1), l.pin(2)
    ll, lr = (la, lb) if la[0] < lb[0] else (lb, la)
    s.wire(*sw, *ll)
    xo = lr[0] + 7.62
    s.wire(*lr, xo + 25.4, lr[1])
    # feedback divider
    rt = R(ctx, base, r1, xo, lr[1] + 6.35, side="right"); rb = R(ctx, base, r2, xo, lr[1] + 16.51, side="right")
    s.wire(xo, lr[1], *rt.pin(1)); s.wire(*rt.pin(2), *rb.pin(1)); gnd(ctx, *rb.pin(2), stub=1.27)
    s.wire(*fb, fb[0] + 2.54, fb[1]); s.wire(fb[0] + 2.54, fb[1], fb[0] + 2.54, lr[1] + 11.43); s.wire(fb[0] + 2.54, lr[1] + 11.43, xo, lr[1] + 11.43)
    co1 = C(ctx, base, "22uF", xo + 12.7, lr[1] + 5.08, fp="C0805", side="right"); s.wire(xo + 12.7, lr[1], *co1.pin(1)); gnd(ctx, *co1.pin(2), stub=1.27)
    co2 = C(ctx, base, "22uF", xo + 22.86, lr[1] + 5.08, fp="C0805", side="right"); s.wire(xo + 22.86, lr[1], *co2.pin(1)); gnd(ctx, *co2.pin(2), stub=1.27)
    rail(ctx, xo + 25.4, lr[1], vout, stub=5.08); pwr_flag(ctx, xo + 17.78, lr[1])
    label_node(ctx, x - 20.0, y + 24.0, note_text, side="right", size=0.85)
    return (xo + 25.4, lr[1])


def ldo(ctx, base, x, y, uref, value, lcsc, vin, vout, note_text, cin="1uF", cout="1uF"):
    s = ctx.s
    u = part(ctx, "Regulator_Linear:TPS7A20xxxDBV" if "TPS" in value else "Regulator_Linear:LP5907MFX-2.5", uref, value, "SOT23-5", x, y,
             ref_at=(x - 7.0, y - 7.5), val_at=(x - 7.0, y + 8.0), lcsc=lcsc)
    i, g, en, o = u.pin("1"), u.pin("2"), u.pin("3"), u.pin("5")
    s.wire(*i, i[0] - 7.62, i[1]); s.wire(*en, i[0] - 5.08, en[1]); s.wire(i[0] - 5.08, en[1], i[0] - 5.08, i[1])
    rail(ctx, i[0] - 7.62, i[1], vin, stub=5.08)
    ci = C(ctx, base, cin, i[0] - 12.7, i[1] + 5.08, fp="C0603" if cin != "1uF" else "C0402", side="left"); s.wire(i[0] - 7.62, i[1], i[0] - 12.7, i[1]); s.wire(i[0] - 12.7, i[1], *ci.pin(1)); gnd(ctx, *ci.pin(2), stub=1.27)
    gnd(ctx, *g, stub=2.54)
    s.nc(*u.pin("4"))
    s.wire(*o, o[0] + 12.7, o[1])
    co = C(ctx, base, cout, o[0] + 7.62, o[1] + 5.08, fp="C0603" if cout != "1uF" else "C0402", side="right"); s.wire(o[0] + 7.62, o[1], *co.pin(1)); gnd(ctx, *co.pin(2), stub=1.27)
    rail(ctx, o[0] + 12.7, o[1], vout, stub=5.08)
    label_node(ctx, x - 20.0, y + 24.0, note_text, side="right", size=0.85)


def ferrite_feed(ctx, base, x, y, src, dst, note_text):
    s = ctx.s
    fb = FB(ctx, base, x, y, horiz=True)
    s.wire(*fb.pin(1), x - 10.16, y); rail(ctx, x - 10.16, y, src, stub=5.08)
    s.wire(*fb.pin(2), x + 15.24, y); rail(ctx, x + 15.24, y, dst, stub=5.08); pwr_flag(ctx, x + 5.08, y)
    c = C(ctx, base, "10uF", x + 10.16, y + 5.08, fp="C0603", side="right"); s.wire(x + 10.16, y, *c.pin(1)); gnd(ctx, *c.pin(2), stub=1.27)
    label_node(ctx, x - 12.0, y + 14.0, note_text, side="right", size=0.85)


def draw(sch, ids, fpga):
    ctx = Ctx(sch, "PWR")
    s = sch
    s.text(20, 22, "Power: one 5 V USB-C in; 3.3 V and 1.1 V bucks; LDOs for the quiet rails; ±4.5 V analog", size=3.0, bold=True)
    note(ctx, 20, 26, "Everything runs from the 5 V of the FTDI USB-C (or a bench 5 V on J16, diode-OR'd). The two switching "
                      "regulators make the digital 3.3 V (FPGA I/O, SDRAM, flash, PHY, FTDI) and the 1.1 V core; they are "
                      "placed in the far corner from the converters. Every analog rail is a separate LDO off the 5 V: "
                      "+3V3_ADC (AD9238 and its drivers), +3V3_DAC (AD9767); the op amps get +5VA through a ferrite and "
                      "-4.2 V from an LM27761 charge pump (then a ferrite bead). The converters' digital supplies and the PHY are fed from +3V3 "
                      "through ferrite beads so their switching noise does not ride the common rail. Budget: FPGA ~0.6 W, "
                      "ADC 0.6 W, DAC 0.4 W, PHY 0.4 W, FTDI 0.3 W, amplifiers 0.4 W, SDRAM 0.2 W: about 3 W, 0.6 A at 5 V.",
         w=340, size=1.1)
    hp = [("VBUS", "input")]
    # --- input ----------------------------------------------------------------------
    y0 = 90.0
    s.hlabel(25.0, y0, "VBUS", shape="input", rot=180)
    s.wire(25.0, y0, 35.56, y0)
    f = part(ctx, "Device:Polyfuse", "F601", "MF-MSMF200-2", "F1812", 40.64, y0, rot=90, ref_at=(37.0, y0 - 3.5), val_at=(37.0, y0 + 2.0), lcsc="C210837")
    fa, fb_ = f.pin(1), f.pin(2)
    fl, fr = (fa, fb_) if fa[0] < fb_[0] else (fb_, fa)
    s.wire(35.56, y0, *fl); s.wire(*fr, 76.2, y0)
    label_node(ctx, 30.0, y0 + 8.0, "from the FTDI USB-C; 2 A resettable fuse", side="right", size=0.85)
    # header pins point right (rot 180), the Schottky's anode faces the header (rot 180)
    jb = part(ctx, "Connector_Generic:Conn_01x02", "J601", "5V IN", "H1x2", 25.4, y0 + 25.4, rot=180, ref_at=(20.0, y0 + 19.5), val_at=(20.0, y0 + 29.0))
    b1, b2 = jb.pin(1), jb.pin(2)
    bh, bl = (b1, b2) if b1[1] < b2[1] else (b2, b1)
    gnd(ctx, *bl, stub=2.54)
    d = part(ctx, "Device:D_Schottky", "D601", "B5819W", "SOD123", bh[0] + 10.16, bh[1], rot=180, ref_at=(bh[0] + 6.5, bh[1] - 2.5), val_at=(bh[0] + 6.5, bh[1] + 1.5))
    s.wire(*bh, *d.pin(2)); s.wire(*d.pin(1), 60.96, bh[1]); s.wire(60.96, bh[1], 60.96, y0)
    label_node(ctx, 28.0, y0 + 36.0, "bench 5 V (5.0 to 5.5 V): a Schottky keeps it off the USB port", side="right", size=0.85)
    rail(ctx, 76.2, y0, "+5V", stub=5.08); pwr_flag(ctx, 68.58, y0)
    gp = (76.2, y0 + 45.0); s.wire(*gp, gp[0], gp[1] + 2.54); gnd(ctx, gp[0], gp[1] + 2.54, stub=0); pwr_flag(ctx, *gp)
    s.text(gp[0] + 2.0, gp[1] + 0.5, "ground reference", size=0.85)
    decouple(ctx, 1600, 90.0, y0 - 5.08, "+5V", ["22uF", "22uF", "100nF"], label="bulk on 5 V")
    # (the power LED is one of the power-good LEDs at the bottom of the sheet)
    # --- bucks ---------------------------------------------------------------------------
    buck(ctx, 1700, 60.0, 180.0, "U601", "+3V3", "15k", "3.3k", "+3V3 = 0.6 V x (1 + 15k/3.3k) = 3.33 V; 2 A, 1.5 MHz. Digital only.")
    buck(ctx, 1800, 60.0, 250.0, "U602", "+1V1", "10k", "12k", "+1V1 = 0.6 V x (1 + 10k/12k) = 1.10 V; FPGA core, up to 1 A.")
    # --- LDOs -----------------------------------------------------------------------------
    ldo(ctx, 1900, 230.0, 180.0, "U603", "LP5907MFX-2.5", "C165132", "+3V3", "+2V5", "VCCAUX 2.5 V for the FPGA's PLLs and I/O pre-drivers, 250 mA LDO")
    ldo(ctx, 2000, 230.0, 250.0, "U604", "TPS7A2033PDBVR", "C2862740", "+5V", "+3V3_ADC", "ADC analog supply and its drivers: 10 µVrms, 65 dB PSRR at 100 kHz", cin="10uF", cout="10uF")
    ldo(ctx, 2100, 230.0, 320.0, "U605", "TPS7A2033PDBVR", "C2862740", "+5V", "+3V3_DAC", "DAC analog supply", cin="10uF", cout="10uF")
    # --- ferrite-isolated digital feeds -------------------------------------------------------
    ferrite_feed(ctx, 2200, 400.0, 180.0, "+3V3", "+3V3_DRV", "ADC output drivers (DRVDD)")
    ferrite_feed(ctx, 2210, 400.0, 215.0, "+3V3", "+3V3_DAC_D", "DAC digital (DVDD1, DVDD2)")
    ferrite_feed(ctx, 2220, 400.0, 250.0, "+3V3", "+3V3_ETH", "Ethernet PHY 3.3 V (switcher inside it)")
    ferrite_feed(ctx, 2230, 400.0, 285.0, "+5V", "+5VA", "op-amp positive rail")
    # --- negative rail: LM27761 --------------------------------------------------------------
    x, y = 470.0, 345.0
    u = part(ctx, "Regulator_SwitchedCapacitor:LM27761", "U606", "LM27761DSGR", "DFN8", x, y, ref_at=(x - 11.0, y - 16.0), val_at=(x - 11.0, y + 17.0))
    vin, g, cpo, vo, vfb, en, cm, cp, pad = (u.pin(n) for n in ("1", "2", "3", "4", "5", "6", "7", "8", "9"))
    s.wire(*vin, vin[0] - 5.08, vin[1]); s.wire(*en, vin[0] - 2.54, en[1]); s.wire(vin[0] - 2.54, en[1], vin[0] - 2.54, vin[1]); s.wire(vin[0] - 5.08, vin[1], vin[0] - 10.16, vin[1])
    rail(ctx, vin[0] - 10.16, vin[1], "+5V", stub=5.08)
    ci = C(ctx, 2300, "10uF", vin[0] - 15.24, vin[1] + 5.08, fp="C0603", side="left"); s.wire(vin[0] - 10.16, vin[1], vin[0] - 15.24, vin[1]); s.wire(vin[0] - 15.24, vin[1], *ci.pin(1)); gnd(ctx, *ci.pin(2), stub=1.27)
    cf = C(ctx, 2300, "1uF", cp[0] - 7.62, (cp[1] + cm[1]) / 2, side="left"); s.wire(*cp, cp[0] - 7.62, cp[1]); s.wire(cp[0] - 7.62, cp[1], *cf.pin(1)); s.wire(*cf.pin(2), cp[0] - 7.62, cm[1]); s.wire(cp[0] - 7.62, cm[1], *cm)
    s.wire(*pad, pad[0], pad[1] + 2.54); s.wire(pad[0], pad[1] + 2.54, g[0], g[1] + 2.54); gnd(ctx, *g, stub=2.54)
    cc = C(ctx, 2300, "10uF", cpo[0] + 3.81, cpo[1] + 5.08, fp="C0603", side="right"); s.wire(*cpo, cpo[0] + 3.81, cpo[1]); s.wire(cpo[0] + 3.81, cpo[1], *cc.pin(1)); gnd(ctx, *cc.pin(2), stub=1.27)
    s.wire(*vo, vo[0] + 33.02, vo[1])
    r1 = R(ctx, 2300, "1.2M", vo[0] + 15.24, vo[1] + 6.35 - 1.27, side="right"); s.wire(vo[0] + 15.24, vo[1], *r1.pin(1))
    r2 = R(ctx, 2300, "499k", vo[0] + 15.24, vo[1] + 16.51 - 1.27, side="right"); s.wire(*r1.pin(2), *r2.pin(1)); gnd(ctx, *r2.pin(2), stub=1.27)
    s.wire(*vfb, vfb[0] + 10.16, vfb[1]); s.wire(vfb[0] + 10.16, vfb[1], vfb[0] + 10.16, vo[1] + 10.16); s.wire(vfb[0] + 10.16, vo[1] + 10.16, vo[0] + 15.24, vo[1] + 10.16)
    co = C(ctx, 2300, "10uF", vo[0] + 33.02, vo[1] + 5.08, fp="C0603", side="left")
    s.wire(vo[0] + 33.02, vo[1], *co.pin(1)); gnd(ctx, *co.pin(2), stub=1.27); s.junction(vo[0] + 33.02, vo[1])
    # build 26: a ferrite bead and 10 uF between the pump and the op amps (the 2 MHz ripple was common to both
    # noise channels: reviews, R3); the divider senses the pump's own output, before the bead
    fbn = FB(ctx, 2300, vo[0] + 41.91, vo[1], horiz=True)
    s.wire(vo[0] + 33.02, vo[1], *fbn.pin(1)); s.wire(*fbn.pin(2), vo[0] + 80.0, vo[1])
    cfl = C(ctx, 2300, "10uF", vo[0] + 56.0, vo[1] + 5.08, fp="C0603", side="right")
    s.wire(vo[0] + 56.0, vo[1], *cfl.pin(1)); gnd(ctx, *cfl.pin(2), stub=1.27); s.junction(vo[0] + 56.0, vo[1])
    gnd(ctx, vo[0] + 80.0, vo[1], "-4V2", stub=5.08); pwr_flag(ctx, vo[0] + 52.07, vo[1]); s.junction(vo[0] + 52.07, vo[1])   # driven through a bead: ERC wants the flag
    # and a monitor tap on the rail: 49.9 R into a U.FL (a 1 MR scope input sees the rail; a 50 R one, half of it)
    rtn = R(ctx, 2300, "49.9R", vo[0] + 66.0, vo[1] + 7.62, side="right"); s.wire(vo[0] + 66.0, vo[1], *rtn.pin(1)); s.junction(vo[0] + 66.0, vo[1])
    jtn = part(ctx, ids["ufl"], "J603", "U.FL", "UFL", vo[0] + 74.1, vo[1] + 15.24, ref_at=(vo[0] + 76.5, vo[1] + 13.5), val_at=(vo[0] + 76.5, vo[1] + 15.5),
               desc="monitor tap: the -4.2 V rail, through 49.9 R")
    s.wire(*rtn.pin(2), vo[0] + 66.0, vo[1] + 15.24); s.wire(vo[0] + 66.0, vo[1] + 15.24, *jtn.pin(1)); gnd(ctx, *jtn.pin(2), stub=2.54)
    label_node(ctx, vo[0] + 58.0, vo[1] + 29.5, "TAP -4V2 (50 Ω scope: x1/2)", side="right", size=0.85)      # (below the jack's ground since build 27: on the jack's row it crossed pin 2's wire)
    label_node(ctx, x - 20.0, y + 28.0, "-4V2 = -1.22 V x (1.2M + 499k) / 499k = -4.15 V: 0.45 V of LDO headroom from a 4.75 V USB supply", side="right", size=0.85)
    label_node(ctx, x - 20.0, y + 31.0, "(builds 1-25 aimed at -4.4 V, in dropout below 4.6 V in); 2 MHz, 250 mA. The bead and 10 µF keep the 2 MHz out of the op-amp rail", side="right", size=0.85)
    # --- the rails header: every rail beside a ground pin, for a scope probe and its ground spring -----
    RAILS = ["+5V", "+3V3", "+1V1", "+2V5", "+3V3_ADC", "+3V3_DAC", "+5VA", "+1V0_PHY", "-4V2"]      # +1V0_PHY since build 26 (reviews: no pin for it); the negative rail last: its flag hangs down
    xt, yt = 100.0, 352.0
    jr = part(ctx, "Connector_Generic:Conn_02x09_Odd_Even", "J602", "RAILS", "H2x9", xt, yt, ref_at=(xt + 0.5, yt - 16.7), val_at=(xt + 0.5, yt - 14.5), lcsc=None)      # (above the body: the 18-pin symbol is 23 mm tall, centred on its anchor)
    for i, nm in enumerate(RAILS):
        po = jr.pin(str(2 * i + 1)); pe = jr.pin(str(2 * i + 2))
        # the rails step out to the left (the lowest row furthest), each flag clear of the rows above it
        xo = po[0] - 5.08 - 7.62 * i
        s.wire(*po, xo, po[1])
        if nm.startswith("-"):
            gnd(ctx, xo, po[1], nm, stub=2.54)
        else:
            rail(ctx, xo, po[1], nm, stub=2.54)
        s.wire(*pe, pe[0] + 2.54, pe[1])
    g0, g1 = jr.pin("2"), jr.pin("18")
    s.wire(g0[0] + 2.54, g0[1], g1[0] + 2.54, g1[1]); gnd(ctx, g1[0] + 2.54, g1[1], stub=2.54)
    for i in range(1, 8):
        s.junction(jr.pin(str(2 * i + 2))[0] + 2.54, jr.pin(str(2 * i + 2))[1])
    s.text(xt - 62.0, yt - 19.0, "RAILS header: odd pins the rails, even pins ground (probe with a ground spring)", size=1.2, bold=True)
    # --- power-good LEDs: a dim red LED on every rail --------------------------------------------------
    def pg_led(base, x, y, railname, rval, dref):
        """A red LED and its resistor from the rail to ground; a negative rail hangs from ground instead."""
        neg = railname.startswith("-")
        d = part(ctx, "Device:LED", dref, "red", "LED0603", x, y + 7.62, rot=90, ref_at=(x + 2.0, y + 6.0), val_at=(x + 2.0, y + 9.0), lcsc="C2286")
        ka, aa = d.pin(1), d.pin(2)
        kk, an = (ka, aa) if ka[1] > aa[1] else (aa, ka)
        r = R(ctx, base, rval, x, y + 17.78, side="right")
        s.wire(*an, x, y); s.wire(*kk, *r.pin(1))
        if neg:
            gnd(ctx, x, y, stub=0, up=True); gnd(ctx, *r.pin(2), railname, stub=1.27)
        else:
            rail(ctx, x, y, railname, stub=0); gnd(ctx, *r.pin(2), stub=1.27)
        return r
    xp0, yp0 = 230.0, 352.0
    for i, (nm, rv, dref) in enumerate((("+5V", "10k", "D602"), ("+3V3", "4.7k", "D603"), ("+2V5", "2.2k", "D604"), ("+3V3_ADC", "4.7k", "D605"),
                                        ("+3V3_DAC", "4.7k", "D606"), ("+5VA", "10k", "D607"), ("-4V2", "10k", "D608"))):
        pg_led(1650 + 10 * i, xp0 + 17.78 * i, yp0, nm, rv, dref)
    # the 1.1 V rail cannot light a diode itself: it turns on an NPN whose collector takes a LED from 3.3 V
    xq = xp0 + 17.78 * 7 + 12.7
    q = part(ctx, "Transistor_BJT:SS8050", "Q601", "SS8050", "SOT23", xq, yp0 + 20.32, rot=0, ref_at=(xq + 3.5, yp0 + 18.5), val_at=(xq + 3.5, yp0 + 21.0))
    bq, eq, cq = q.pin(1), q.pin(2), q.pin(3)
    rb = R(ctx, 1720, "4.7k", bq[0] - 7.62, bq[1], horiz=True, ref_at=(bq[0] - 10.2, bq[1] - 1.6), val_at=(bq[0] - 10.2, bq[1] + 1.3))
    s.wire(*rb.pin(2), *bq); s.wire(*rb.pin(1), rb.pin(1)[0] - 2.54, bq[1]); rail(ctx, rb.pin(1)[0] - 2.54, bq[1], "+1V1", stub=2.54)
    gnd(ctx, *eq, stub=1.27)
    dq = part(ctx, "Device:LED", "D609", "red", "LED0603", cq[0], cq[1] - 7.62, rot=90, ref_at=(cq[0] + 2.0, cq[1] - 9.5), val_at=(cq[0] + 2.0, cq[1] - 6.5), lcsc="C2286")
    ka, aa = dq.pin(1), dq.pin(2)
    kk, an = (ka, aa) if ka[1] > aa[1] else (aa, ka)
    s.wire(*kk, *cq)
    rq = R(ctx, 1720, "2.2k", cq[0], cq[1] - 17.78, side="right")
    s.wire(*an, *rq.pin(2)); rail(ctx, *rq.pin(1), "+3V3", stub=2.54)
    s.text(xp0 - 8.0, yp0 - 10.0, "POWER GOOD: a dim red LED on every rail (0.3 mA); the 1.1 V core rail switches an NPN", size=1.2, bold=True)
    # --- mounting holes: M3 in the four corners, pads tied to ground --------------------------
    xh = 60.0
    for i in range(4):
        h = part(ctx, ids["hole"], "H%d" % (i + 1), "M3", "HOLE", xh + i * 12.7, 395.0, ref_at=(xh + i * 12.7 - 2.0, 390.3), val_at=(xh + i * 12.7 - 2.0, 390.8), lcsc=None)
        gnd(ctx, *h.pin(1), stub=1.27)
    s.text(xh - 3.0, 388.0, "M3 mounting holes, four corners, grounded", size=1.2, bold=True)
    # power flags for ERC: the rails are driven here
    for i, nm in enumerate(("+5V", "+3V3", "+1V1", "+2V5", "+3V3_ADC", "+3V3_DAC", "+3V3_DRV", "+3V3_DAC_D", "+3V3_ETH", "+5VA", "-4V2", "+1V0_PHY", "+1V8_FTDI", "GND")):
        pass
    note(ctx, 20.0, 318.0, "Sequencing (FPGA-DS-02012 §3.5, Master SPI): VCCIO8 must be above the flash's VIH before the FIRST of VCC "
                           "and VCCAUX reaches its POR threshold, or PROGRAMN/INITN must be held low until it is. Here VCCAUX is an LDO "
                           "off +3V3 (= VCCIO8), so it cannot lead it; VCC is the other buck, enabled by the same 5 V with the same "
                           "soft-start, and the 100 nF on PROGRAMN (FPGA sheet) holds configuration off for ~0.5 ms after +3V3 is up "
                           "in any case. Scope +3V3 against +1V1 on the first board. The PHY, converters and amplifiers tolerate any order.", w=180, size=0.95)
    return hp
