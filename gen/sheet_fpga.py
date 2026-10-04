"""The FPGA sheet (A1): the ECP5 drawn as one unit per bank, the SDRAM, the
flash and configuration, JTAG, clocks (TCXO, Si5351, external in/out), LEDs,
buttons, the two Pmods, and the decoupling.  Buses leave to the ADC, DAC,
Ethernet and USB sheets through hierarchical labels at the sheet edges.

Layout (A1, 841 x 594):
   x  25-240   clock sources (TCXO, Si5351, CLK IN, CLK OUT) feeding bank 0
               through one vertical channel per clock; the ADC/DAC bus labels
   x 230-300   LEDs and buttons fanned out below bank 0
   x 250-300   bank 0 (top), bank 7, bank 6 (left column of units)
   x 330-470   bank 1 -> SDRAM (top right of centre); bank 8 + flash + config (middle); power unit (bottom)
   x 600-700   bank 2, bank 3 (right column) -> labels at x 760, Pmods below

The rule that keeps the clock channels from crossing each other: a channel
whose source is ABOVE the symbol belongs to a row above every channel whose
source is below, the above-group is ordered by depth with the rightmost
channel on the topmost row, and the below-group the other way round.  The
pin plan (fpga.py, CLOCKS) lists the rows in exactly that order.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from draw import *
import fpga as F


UNITS = {}          # bank -> the placed unit, filled by the sheet: a signal is drawn on the unit its ball is on
BANK_OF = {}        # signal -> bank of its ball


def unit_of(sname, u):
    return UNITS.get(BANK_OF.get(sname), u)


def unit_bus(ctx, u, sigs, bus_name, inv, x_bus, x_end, shape, elsewhere=None):
    """A bus of `sigs` from unit `u`'s pins.  A member whose ball the board put on another bank's unit is
    not wired across the sheet: `elsewhere(sname)` queues a stub and a local label at that pin (the
    label joins the bus by name), and the member is left out of the fan."""
    members = []
    for sname in sigs:
        uu = unit_of(sname, u)
        if uu is not u and elsewhere is not None:
            elsewhere(sname)
            continue
        p = uu.pin(inv[sname])
        members.append((p[0], p[1], sname))
    if not members:
        return None
    return bus_out(ctx, x_bus, 0, bus_name, members, x_end=x_end, shape=shape)


def single(ctx, u, sname, inv, x_end, shape, side="left"):
    s = ctx.s
    p = unit_of(sname, u).pin(inv[sname])
    s.wire(*p, x_end, p[1]); s.hlabel(x_end, p[1], sname, shape=shape, rot=180 if side == "left" else 0)
    return p


def gate_supply(ctx, base, g, pin_v="5", pin_g="3"):
    """+3V3 and GND on a single-gate logic part, with its 100 nF."""
    s = ctx.s
    rail(ctx, *g.pin(pin_v), "+3V3", stub=2.54); gnd(ctx, *g.pin(pin_g), stub=2.54)
    v = g.pin(pin_v)
    # the 100 nF lies along the rail stub, its ground flag pointing right, clear of the gate's output
    c = C(ctx, base, "100nF", v[0] + 6.35, v[1] - 2.54, horiz=True, ref_at=(v[0] + 3.5, v[1] - 4.5), val_at=(v[0] + 3.5, v[1] - 1.1))
    s.wire(v[0], v[1] - 2.54, *c.pin(1)); s.power("GND", *c.pin(2), down=True, rot=90); s.junction(v[0], v[1] - 2.54)


def draw(sch, ids, fpga):
    ctx = Ctx(sch, "FPGA")
    s = sch
    inv = fpga["assign"]
    units = ids["fpga_units"]
    FP_ = "BGA256"
    s.text(20, 22, "FPGA: Lattice ECP5 LFE5U-25F-6BG256C, 32 MB SDRAM, 16 MB flash, clocks, configuration", size=3.0, bold=True)
    note(ctx, 20, 26, "One box per I/O bank, in the position the bank has on the package: 7 and 6 on the west (ADC above, "
                      "DAC below), 0 and 1 on the north (clocks, I2C, LEDs, buttons; the SDRAM), 2 and 3 on the east (Ethernet and "
                      "HDMI; SD card, USB, serial, Pmods), 8 on the south (the sysCONFIG pins: SPI flash, JTAG, slow "
                      "controls). Every ball is named by its ball number; a PCLK is a primary clock input. The pin "
                      "plan is generated (gen/fpga.py) and the same table writes the .lpf and the LiteX platform file.",
         w=420, size=1.1)
    hp = []

    assigned = set(inv.values())
    _, fp_pins = kisch.SYMS.get(ids["fpga"])
    bank_of = {sname: fpga["balls"][ball]["bank"] for sname, ball in inv.items()}
    BANK_OF.clear(); BANK_OF.update(bank_of)
    # A signal drawn in one bank's section whose ball the board put on ANOTHER bank (the bus rivers of
    # pcb/river.py hand a face's balls out by position, bank or no bank) ends in a label at its source and
    # gets the same label on a stub at its pin when that bank's unit is drawn.
    import collections
    pending = collections.defaultdict(list)          # bank -> [(sname, kind, shape)]
    LEFT_SIDE = {"7", "6", "0", "8"}

    def U(bank, x, y, ref_at, val_at):
        u = part(ctx, ids["fpga"], "U1", "LFE5U-25F-6BG256C", FP_, x, y, unit=units[bank], ref_at=ref_at, val_at=val_at)
        for pp in fp_pins:
            if pp["unit"] == units[bank] and pp["num"] not in assigned and pp["num"] not in ("N9",):
                s.nc(*u.pin(pp["num"]))
        UNITS[str(bank)] = u
        return u

    def draw_pending():
        for bank, items in list(pending.items()):
            u = UNITS[bank]
            for (sname, kind, shape) in items:
                pp = u.pin(inv[sname]); left = str(bank) in LEFT_SIDE; dx = -6.35 if left else 6.35
                if kind == "label":
                    s.wire(*pp, pp[0] + dx, pp[1])
                    s.label(pp[0] + dx, pp[1], sname, size=1.0, justify="right bottom" if left else "left bottom")
                else:
                    single(ctx, u, sname, inv, pp[0] + 2 * dx, shape, side="left" if left else "right")
        pending.clear()

    def elsewhere(sname):
        """True (and the pin's label is queued) when sname's ball is not on the bank-0 unit."""
        if bank_of[sname] == "0":
            return False
        pending[bank_of[sname]].append((sname, "label", None))
        return True

    UNITS.clear()
    u0 = U(0, 280.0, 120.0, (255.0, 86.0), (266.0, 155.0))
    u7 = U(7, 280.0, 300.0, (255.0, 258.0), (255.0, 343.0))
    u6 = U(6, 280.0, 410.0, (255.0, 368.0), (255.0, 453.0))
    u1 = U(1, 420.0, 120.0, (395.0, 77.0), (395.0, 165.0))
    u2 = U(2, 640.0, 270.0, (615.0, 223.0), (615.0, 313.0))
    u3 = U(3, 640.0, 410.0, (615.0, 363.0), (615.0, 453.0))
    u8 = U(8, 420.0, 310.0, (400.0, 276.0), (400.0, 344.0))

    # ---- bank 0: clocks, I2C, LEDs, buttons, SDRAM extras ------------------------------
    s.text(255.0, 82.0, "bank 0", size=1.4, bold=True)
    # one vertical channel per clock, left of the symbol (see the module docstring)
    chan = {"I2C_SDA": 217.17, "I2C_SCL": 219.71, "CLK_EXT": 222.25, "CLK_OUT": 224.79,
            "CLK_SI2": 227.33, "CLK_SI1": 229.87, "CLK_SI0": 232.41, "CLK_TCXO": 234.95}

    def to_bank(sname, x_src, y_src):
        """Wire from a source at (x_src, y_src) to its bank-0 pin through the channel -- or, when the board
        put the signal on another bank, to a label at the mouth of its channel."""
        xk = chan[sname]
        if elsewhere(sname):
            s.wire(x_src, y_src, xk, y_src); s.label(xk, y_src, sname, size=1.0)
            return
        p = u0.pin(inv[sname])
        s.wire(x_src, y_src, xk, y_src); s.wire(xk, y_src, xk, p[1]); s.wire(xk, p[1], *p)

    # TCXO at the top left
    xe = 40.0
    yt = 62.0
    tc = part(ctx, ids["tcxo"], "X301", "FT5HNBPK25.0-T1", "TCXO5032", xe + 20.0, yt, ref_at=(xe + 8.0, yt - 9.5), val_at=(xe + 8.0, yt + 9.0))
    rail(ctx, *tc.pin("4"), "+3V3", stub=2.54); gnd(ctx, *tc.pin("2"), stub=2.54)
    s.wire(*tc.pin("1"), tc.pin("1")[0], tc.pin("2")[1] + 2.54); s.wire(tc.pin("1")[0], tc.pin("2")[1] + 2.54, tc.pin("2")[0], tc.pin("2")[1] + 2.54)
    ct = C(ctx, 2400, "100nF", tc.pin("4")[0] - 12.7, tc.pin("4")[1] - 2.54 + 3.81, side="left"); s.wire(tc.pin("4")[0], tc.pin("4")[1] - 2.54, tc.pin("4")[0] - 12.7, tc.pin("4")[1] - 2.54); s.wire(tc.pin("4")[0] - 12.7, tc.pin("4")[1] - 2.54, *ct.pin(1)); gnd(ctx, *ct.pin(2), stub=0)
    o = tc.pin("3")
    rt = R(ctx, 2400, "33R", o[0] + 8.89, o[1], horiz=True, ref_at=(o[0] + 6.3, o[1] - 1.5), val_at=(o[0] + 12.8, o[1] - 1.5)); s.wire(*o, *rt.pin(1))
    to_bank("CLK_TCXO", *rt.pin(2))
    s.text(xe - 15.0, yt - 14.0, "25 MHz TCXO ±2.5 ppm: the system clock", size=1.2, bold=True)
    # Si5351 below the TCXO: three outputs to the right, crystal and I2C on the left
    xsi, ysi = 100.0, 100.0
    s.text(xe - 15.0, ysi - 24.5, "Si5351A: three programmable clocks, 2.5 kHz to 200 MHz, from a 25 MHz crystal", size=1.2, bold=True)
    si = part(ctx, "Oscillator:Si5351A-B-GT", "U301", "Si5351A-B-GTR", "MSOP10", xsi, ysi, ref_at=(xsi + 4.0, ysi + 14.5), val_at=(xsi + 4.0, ysi + 17.5))
    for k, sname in enumerate(("CLK_SI0", "CLK_SI1", "CLK_SI2")):
        po = si.pin(("10", "9", "6")[k])
        r = R(ctx, 2410, "33R", po[0] + 8.89, po[1], horiz=True, ref_at=(po[0] + 6.3, po[1] - 1.5), val_at=(po[0] + 12.8, po[1] - 1.5))
        s.wire(*po, *r.pin(1)); to_bank(sname, *r.pin(2))
    xa, xb = si.pin("2"), si.pin("3")
    # a 3225 crystal has four pads: 1 and 3 are the crystal, 2 and 4 the grounded case (the YXC drawing;
    # the first draft used the two-pin symbol, whose pin 2 is the case pad)
    y = part(ctx, "Device:Crystal_GND24", "Y301", "25MHz", "XTAL3225", xa[0] - 10.16, (xa[1] + xb[1]) / 2, rot=270,
             ref_at=(xa[0] - 13.0, xa[1] + 0.3), val_at=(xa[0] - 13.0, xa[1] + 3.3), lcsc="C362338", justify="right")
    y1, y2 = y.pin(1), y.pin(3)
    ya, yb = (y1, y2) if y1[1] < y2[1] else (y2, y1)
    # (KiCad draws the symbol's two ground pins on one point: one stub, pointing away from the crystal, serves both)
    g2_ = y.pin(2); dx_ = 2.54 if g2_[0] > y.x else -2.54
    s.wire(*g2_, g2_[0] + dx_, g2_[1]); s.power("GND", g2_[0] + dx_, g2_[1], down=True, rot=90 if dx_ > 0 else 270)
    xj = xa[0] - 5.08
    s.wire(*xa, xj, xa[1]); s.wire(xj, xa[1], xj, ya[1]); s.wire(xj, ya[1], *ya)
    s.wire(*xb, xj, xb[1]); s.wire(xj, xb[1], xj, yb[1]); s.wire(xj, yb[1], *yb)
    p1, p7 = si.pin("1"), si.pin("7")
    xl, xr = min(p1[0], p7[0]), max(p1[0], p7[0]); yb_ = p1[1] - 2.54
    s.wire(*p1, p1[0], yb_); s.wire(*p7, p7[0], yb_); s.wire(xl, yb_, xr, yb_)
    rail(ctx, xl, yb_, "+3V3", stub=0)
    # the 100 nF lies along the supply bar to the right, clear of the crystal on the left
    cs_ = C(ctx, 2410, "100nF", xr + 6.35, yb_, horiz=True)
    s.wire(xr, yb_, *cs_.pin(1)); gnd(ctx, *cs_.pin(2), stub=0); s.junction(xr, yb_)
    gnd(ctx, *si.pin("8"), stub=2.54)
    # I2C: out to the left, under the chip, and into two channels like the clocks
    for sname, sp, dx, yy in (("I2C_SDA", si.pin("5"), 17.78, 127.0), ("I2C_SCL", si.pin("4"), 20.32, 129.54)):
        xv = xsi - dx
        s.wire(*sp, xv, sp[1]); s.wire(xv, sp[1], xv, yy); to_bank(sname, xv, yy)
    # the bus's pull-ups (4.7 k: a short bus with one slave), hanging below the two wires with their supply bar
    # underneath -- above them is the crystal
    ladder(ctx, 2415, [(xsi - 19.05, si.pin("4")[1]), (xsi - 13.97, si.pin("5")[1])], "4.7k", "+3V3", down=True, label="I2C pull-ups")
    label_node(ctx, xsi + 8.0, ysi + 21.5, "10 pF crystal, load capacitors inside; this I2C bus is the Si5351's alone (the HDMI DDC is a second bus)", side="right", size=0.85)
    # external clock in
    ye = 160.0
    s.text(xe - 15.0, ye - 20.0, "CLK IN: an external reference or sample clock", size=1.2, bold=True)
    je = part(ctx, ids["sma"], "J301", "SMA", "SMA", xe, ye, ref_at=(xe - 7.0, ye - 6.0), val_at=(xe - 7.0, ye + 4.0))
    gnd(ctx, *je.pin(2), stub=2.54)
    s.wire(*je.pin(1), xe + 12.7, ye)
    rte = R(ctx, 2420, "49.9R", xe + 12.7, ye + 6.35, side="right"); s.wire(xe + 12.7, ye, *rte.pin(1))
    jte = part(ctx, "Jumper:Jumper_2_Open", "JP3001", "TERM", "H1x2", xe + 12.7, ye + 16.51, rot=90, ref_at=(xe + 15.5, ye + 15.5), val_at=(xe + 15.5, ye + 16.0))
    ta_, tb_ = jte.pin(1), jte.pin(2)
    tt, tb2 = (ta_, tb_) if ta_[1] < tb_[1] else (tb_, ta_)
    s.wire(*rte.pin(2), *tt); gnd(ctx, *tb2, stub=2.54)
    label_node(ctx, xe + 15.5, ye + 22.0, "shunt in = 50 Ω", side="right", size=0.9)
    ce = C(ctx, 2420, "10nF", xe + 22.86, ye, horiz=True, ref_at=(xe + 20.0, ye - 1.8), val_at=(xe + 20.0, ye + 2.0))
    s.wire(xe + 12.7, ye, *ce.pin(1)); s.junction(xe + 12.7, ye)
    inv_ = part(ctx, "74xGxx:74LVC1GU04", "U302", "SN74LVC1GU04DBVR", "SOT23-5", xe + 55.88, ye, ref_at=(xe + 46.0, ye - 12.0), val_at=(xe + 46.0, ye + 12.5))
    s.wire(*ce.pin(2), *inv_.pin("2"))
    rfb = R(ctx, 2420, "1M", inv_.x, ye - 20.32, horiz=True)
    s.wire(inv_.pin("2")[0] - 2.54, ye, inv_.pin("2")[0] - 2.54, ye - 20.32); s.wire(inv_.pin("2")[0] - 2.54, ye - 20.32, *rfb.pin(1))
    s.junction(inv_.pin("2")[0] - 2.54, ye)
    s.wire(*rfb.pin(2), inv_.pin("4")[0] + 2.54, ye - 20.32); s.wire(inv_.pin("4")[0] + 2.54, ye - 20.32, inv_.pin("4")[0] + 2.54, ye); s.wire(*inv_.pin("4"), inv_.pin("4")[0] + 2.54, ye)
    s.junction(inv_.pin("4")[0] + 2.54, ye)
    s.nc(*inv_.pin("1")); gate_supply(ctx, 2420, inv_)
    sch_ = part(ctx, "74xGxx:74LVC1G17", "U303", "SN74LVC1G17DBVR", "SOT23-5", xe + 95.0, ye, ref_at=(xe + 86.0, ye - 12.0), val_at=(xe + 86.0, ye + 12.5))
    s.wire(inv_.pin("4")[0] + 2.54, ye, *sch_.pin("2"))
    s.nc(*sch_.pin("1")); gate_supply(ctx, 2420, sch_)
    re_ = R(ctx, 2420, "33R", sch_.pin("4")[0] + 8.89, ye, horiz=True, ref_at=(sch_.pin("4")[0] + 6.3, ye - 1.5), val_at=(sch_.pin("4")[0] + 12.8, ye - 1.5))
    s.wire(*sch_.pin("4"), *re_.pin(1)); to_bank("CLK_EXT", *re_.pin(2))
    note(ctx, xe - 15.0, ye + 28.0, "10 MHz sine from a GPSDO, or any 0.5 to 3.3 V square wave up to 100 MHz. 50 Ω if the shunt is in. AC coupled into an "
                                   "unbuffered inverter biased at its own threshold by the 1 MΩ, then a Schmitt buffer: the GPSDO board's front end. "
                                   "The FPGA's PLL locks to it (8 MHz minimum).", w=175, size=0.9)
    # clock out
    yo = 230.0
    s.text(xe - 15.0, yo - 25.0, "CLK OUT: sync a second board", size=1.2, bold=True)
    bo = part(ctx, "74xGxx:74LVC1G17", "U304", "SN74LVC1G17DBVR", "SOT23-5", xe + 55.88, yo, ref_at=(xe + 46.0, yo - 12.0), val_at=(xe + 46.0, yo + 12.5))
    xk = chan["CLK_OUT"]; xin = bo.pin("2")[0] - 5.08
    if elsewhere("CLK_OUT"):
        s.label(xk, yo - 20.32, "CLK_OUT", size=1.0)
    else:
        po = u0.pin(inv["CLK_OUT"])
        s.wire(*po, xk, po[1]); s.wire(xk, po[1], xk, yo - 20.32)
    s.wire(xk, yo - 20.32, xin, yo - 20.32)
    s.wire(xin, yo - 20.32, xin, yo); s.wire(xin, yo, *bo.pin("2"))
    s.nc(*bo.pin("1")); gate_supply(ctx, 2430, bo)
    ro = R(ctx, 2430, "49.9R", bo.pin("4")[0] + 8.89, yo, horiz=True, ref_at=(bo.pin("4")[0] + 6.3, yo - 1.5), val_at=(bo.pin("4")[0] + 12.8, yo - 1.5))
    s.wire(*bo.pin("4"), *ro.pin(1))
    jo = part(ctx, ids["sma_out"], "J302", "SMA", "SMA", ro.pin(2)[0] + 7.62, yo, ref_at=(ro.pin(2)[0] + 9.5, yo - 6.0), val_at=(ro.pin(2)[0] + 9.5, yo + 4.0))
    s.wire(*ro.pin(2), *jo.pin(1)); gnd(ctx, *jo.pin(2), stub=2.54)
    note(ctx, xe - 15.0, yo + 16.0, "Any FPGA clock, 50 Ω source terminated: 3.3 V open circuit, 1.65 V into 50 Ω; the other board's CLK IN squares it up.", w=110, size=0.9)
    # LEDs and buttons: the pins are on a 2.54 mm pitch, so the ten wires fan out below the symbol to a
    # row of circuits 8 mm apart.  Wire i leaves its pin to the left, drops down its own column (1.27 mm
    # apart, all left of the pin ends and right of the clock channels), turns on its own row and runs to
    # its circuit's column.  The top pin turns on the LOWEST row and the bottom pin on the highest, so no
    # wire crosses another: a wire's horizontal run lies below every wire that starts above it and above
    # every wire that starts below it.  (Eight LEDs: LiteX's boot-time chaser wants at least five.)
    order = ["LED%d" % i for i in range(8)] + ["BTN0", "BTN1"]
    here = [sname for sname in order if not elsewhere(sname)]
    pins_ = {sname: u0.pin(inv[sname]) for sname in here}
    # the circuits stand right of the pin ends (the wires come back under the symbol on their turn rows),
    # clear of the clock channels on the left and of the fan's own columns
    px0_ = (min(p[0] for p in pins_.values()) if pins_ else 261.6) + 2.54
    cols = {sname: px0_ + 8.0 * i for i, sname in enumerate(order)}
    # the turn rows start below the unit's LAST pin (a spare ball sits below the LEDs' pins)
    y_last = max([u0.pin(pp["num"])[1] for pp in fp_pins if pp["unit"] == units[0]] + [p[1] for p in pins_.values()])
    n_ = len(order)
    turn = {sname: y_last + 2.54 * (n_ - i) for i, sname in enumerate(order)}
    ytop = y_last + 2.54 * (n_ + 1)
    for i, sname in enumerate(order):
        xc = cols[sname]
        if sname not in pins_:
            s.wire(xc, ytop, xc, ytop - 5.08); s.label(xc, ytop - 5.08, sname, size=1.0, rot=90)
            continue
        p = pins_[sname]; xd = p[0] - 17.78 + 1.27 * i
        s.wire(*p, xd, p[1]); s.wire(xd, p[1], xd, turn[sname]); s.wire(xd, turn[sname], xc, turn[sname]); s.wire(xc, turn[sname], xc, ytop)
    for i in range(8):
        xc = cols["LED%d" % i]
        r = R(ctx, 2440, "1k", xc, ytop + 5.08)
        s.wire(xc, ytop, *r.pin(1))
        d = part(ctx, "Device:LED", "D%d" % (301 + i), "white", "LED0603", xc, ytop + 15.24, rot=90,
                 ref_at=(xc + 2.0, ytop + 13.9), val_at=(xc + 2.0, ytop + 16.9), lcsc="C2290", fsize=1.0)
        ka, an = d.pin(1), d.pin(2)
        s.wire(*r.pin(2), *an); gnd(ctx, *ka, stub=2.54)
    s.text(cols["LED0"] - 1.0, ytop + 30.0, "user LEDs 0-7, white, active high, ~1 mA", size=0.85)
    for i in range(2):
        xc = cols["BTN%d" % i]; yn = ytop + 7.62
        s.wire(xc, ytop, xc, yn); s.junction(xc, yn)
        s.wire(xc, yn, xc + 5.08, yn)
        r = R(ctx, 2450, "10k", xc + 5.08, yn - 5.08)
        s.wire(xc + 5.08, yn, *r.pin(2)); rail(ctx, *r.pin(1), "+3V3", stub=2.54)
        sw = part(ctx, "Switch:SW_Push", "SW%d" % (301 + i), "SW_Push", "SW_1088", xc, yn + 7.62, rot=90, ref_at=(xc + 2.5, yn + 5.5), val_at=(xc + 2.5, yn + 8.5))
        pa_, pb_ = sw.pin(1), sw.pin(2)
        t_, b_ = (pa_, pb_) if pa_[1] < pb_[1] else (pb_, pa_)
        s.wire(xc, yn, *t_); gnd(ctx, *b_, stub=2.54)
    s.text(cols["BTN0"] - 1.0, ytop + 30.0, "BTN0 = reset, BTN1 = user; active low", size=0.85)
    for sname in ("FTDI_RTS", "FTDI_DTR"):
        if bank_of[sname] == "0":
            single(ctx, u0, sname, inv, u0.pin(inv[sname])[0] - 12.7, "input")
        else:
            pending[bank_of[sname]].append((sname, "hlabel", "input"))
    hp += [("FTDI_RTS", "input"), ("FTDI_DTR", "input")]

    # ---- bank 7 (ADC) and bank 6 (DAC): pins left, buses to the west edge ---------------
    s.text(255.0, 254.0, "bank 7: ADC", size=1.4, bold=True)
    stray = lambda sname: pending[bank_of[sname]].append((sname, "label", None))
    unit_bus(ctx, u7, ["ADC_A_D%d" % i for i in range(11, -1, -1)], "ADC_A_D[11..0]", inv, 200.0, 160.0, "input", elsewhere=stray)
    unit_bus(ctx, u7, ["ADC_B_D%d" % i for i in range(11, -1, -1)], "ADC_B_D[11..0]", inv, 190.0, 160.0, "input", elsewhere=stray)
    for sname, sh in (("ADC_A_OTR", "input"), ("ADC_B_OTR", "input"), ("ADC_A_CLK", "output"), ("ADC_B_CLK", "output")):
        if unit_of(sname, u7) is u7:
            single(ctx, u7, sname, inv, 160.0, sh)
        else:
            pending[bank_of[sname]].append((sname, "hlabel", sh))
    hp += [("ADC_A_D[11..0]", "input"), ("ADC_B_D[11..0]", "input"), ("ADC_A_OTR", "input"), ("ADC_B_OTR", "input"), ("ADC_A_CLK", "output"), ("ADC_B_CLK", "output")]
    s.text(255.0, 364.0, "bank 6: DAC", size=1.4, bold=True)
    unit_bus(ctx, u6, ["DAC_P2_D%d" % i for i in range(13, -1, -1)], "DAC_P2_D[13..0]", inv, 200.0, 160.0, "output", elsewhere=stray)
    unit_bus(ctx, u6, ["DAC_P1_D%d" % i for i in range(13, -1, -1)], "DAC_P1_D[13..0]", inv, 190.0, 160.0, "output", elsewhere=stray)
    for sname in ("DAC_WRT2", "DAC_CLK2", "DAC_CLK1", "DAC_WRT1"):
        if unit_of(sname, u6) is u6:
            single(ctx, u6, sname, inv, 160.0, "output")
        else:
            pending[bank_of[sname]].append((sname, "hlabel", "output"))      # the DAC's clocks ride its river into the south face (bank 8)
    hp += [("DAC_P1_D[13..0]", "output"), ("DAC_P2_D[13..0]", "output"), ("DAC_WRT1", "output"), ("DAC_WRT2", "output"), ("DAC_CLK1", "output"), ("DAC_CLK2", "output")]

    # ---- bank 1 + bank 0 extras: SDRAM -----------------------------------------------------
    s.text(395.0, 73.0, "bank 1: SDRAM", size=1.4, bold=True)
    sd = part(ctx, ids["sdram"], "U305", "W9825G6KH-6", "TSOP54", 580.0, 120.0, ref_at=(560.0, 77.0), val_at=(560.0, 166.0))
    sd_names = {"SDRAM_A%d" % i: "A%d" % i for i in range(13)}
    sd_names.update({"SDRAM_DQ%d" % i: "DQ%d" % i for i in range(16)})
    sd_names.update({"SDRAM_BA0": "BA0", "SDRAM_BA1": "BA1", "SDRAM_CLK": "CLK", "SDRAM_CKE": "CKE", "SDRAM_CS_N": "~{CS}",
                     "SDRAM_RAS_N": "~{RAS}", "SDRAM_CAS_N": "~{CAS}", "SDRAM_WE_N": "~{WE}", "SDRAM_DQML": "DQML", "SDRAM_DQMH": "DQMH"})
    _, pins = kisch.SYMS.get(ids["sdram"])
    num_of = {p["name"]: p["num"] for p in pins}
    members_a, members_d, members_x = [], [], []
    for sname, pname in sd_names.items():
        ball = inv[sname]
        bank = fpga["balls"][ball]["bank"]
        u_ = u1 if bank == "1" else u0
        p = u_.pin(ball)
        pp = sd.pin(num_of[pname])
        is_dq = sname.startswith("SDRAM_DQ") and "DQM" not in sname
        # the SDRAM's side: data on its right bus, everything else on its left bus (by name).  The FPGA's
        # side: by the bank the board put the ball on -- bank 0's pins join the bus left of bank 0 whatever
        # they carry (the river of pcb/river.py decides, not the name), bank 1's the two columns right of it
        if is_dq:
            s.wire(*pp, pp[0] + 6.35, pp[1]); s.bus_entry(pp[0] + 6.35, pp[1], 2.54, -2.54); s.label(pp[0] + 0.5, pp[1] - 0.2, sname, size=1.0)
        else:
            s.wire(*pp, pp[0] - 6.35, pp[1]); s.bus_entry(pp[0] - 6.35, pp[1], -2.54, -2.54); s.label(pp[0] - 0.5, pp[1] - 0.2, sname, size=1.0, justify="right bottom")
        if bank != "1":
            members_x.append((p[0], p[1], sname))
        elif is_dq:
            members_d.append((p[0], p[1], sname))
        else:
            members_a.append((p[0], p[1], sname))
    # address/control bus: column right of the data column, horizontal run half a row above its first member
    xbus_d, xbus_a = 500.0, 507.62
    top_a = min(m[1] for m in members_a) - 1.27
    s.bus((xbus_a, top_a), (xbus_a, max(m[1] for m in members_a)))
    for (mx, my, nm) in members_a:
        s.wire(mx, my, xbus_a - 2.54, my); s.bus_entry(xbus_a - 2.54, my, 2.54, -2.54); s.label(mx + 0.5, my - 0.2, nm, size=1.0)
    # bank-0 SDRAM extras: bus on the left of bank 0, over the top (y 66) to the address column
    if members_x:
        xx = members_x[0][0] - 10.16
        s.bus((xx, min(m[1] for m in members_x) - 3.81), (xx, max(m[1] for m in members_x)))
        for (mx, my, nm) in members_x:
            s.wire(mx, my, xx + 2.54, my); s.bus_entry(xx + 2.54, my, -2.54, -2.54); s.label(mx - 0.5, my - 0.2, nm, size=1.0, justify="right bottom")
        top_x = 66.04
        s.bus((xx, min(m[1] for m in members_x) - 3.81), (xx, top_x), (xbus_a, top_x), (xbus_a, top_a))
        s.text(xx + 1.0, top_x - 0.5, "%d of the 39 SDRAM lines live on bank 0" % len(members_x), size=0.9)
    sd_left_x = sd.pin(num_of["A0"])[0] - 8.89
    ys = [sd.pin(num_of[pn])[1] for sn, pn in sd_names.items() if not (sn.startswith("SDRAM_DQ") and "DQM" not in sn)]
    s.bus((sd_left_x, min(ys) - 2.54), (sd_left_x, max(ys)))
    s.bus((xbus_a, top_a), (sd_left_x, top_a), (sd_left_x, min(ys) - 2.54))
    # the group label reads leftwards from the bus corner (right-justified), clear of both columns of pin labels
    group = "{SDRAM_A[12..0] SDRAM_BA[1..0] SDRAM_CLK SDRAM_CKE SDRAM_CS_N SDRAM_RAS_N SDRAM_CAS_N SDRAM_WE_N SDRAM_DQML SDRAM_DQMH%s}" % (
        " SDRAM_DQ[15..0]" if any(nm.startswith("SDRAM_DQ") and "DQM" not in nm for (_, _, nm) in members_x) else "")
    s.label(xbus_a + 1.0, top_a - 0.5, group, size=0.7, justify="right bottom")
    # data bus: left column, up and over the top (y 60) to the SDRAM's right-hand bus
    sd_right_x = sd.pin(num_of["DQ0"])[0] + 8.89
    yd = [sd.pin(num_of["DQ%d" % i])[1] for i in range(16)]
    s.bus((sd_right_x, min(yd) - 2.54), (sd_right_x, max(yd)))
    if members_d:
        bot_d = max(m[1] for m in members_d)
        s.bus((xbus_d, 60.96), (xbus_d, bot_d))
        for (mx, my, nm) in members_d:
            s.wire(mx, my, xbus_d - 2.54, my); s.bus_entry(xbus_d - 2.54, my, 2.54, -2.54); s.label(mx + 0.5, my - 0.2, nm, size=1.0)
        s.bus((xbus_d, 60.96), (sd_right_x + 7.62, 60.96), (sd_right_x + 7.62, min(yd) - 2.54), (sd_right_x, min(yd) - 2.54))
        s.label(xbus_d + 1.0, 60.96 - 0.5, "SDRAM_DQ[15..0]", size=1.0)
    else:
        s.label(sd_right_x + 1.0, min(yd) - 2.54 - 0.5, "SDRAM_DQ[15..0]", size=1.0)
    tops_ = [p for p in pins if p["name"] in ("VDD", "VDDQ")]
    bots_ = [p for p in pins if p["name"] in ("VSS", "VSSQ")]
    yv = sd.pin(tops_[0]["num"])[1] - 5.08
    for p in tops_:
        pp = sd.pin(p["num"]); s.wire(*pp, pp[0], yv)
    xs_ = [sd.pin(p["num"])[0] for p in tops_]
    s.wire(min(xs_), yv, max(xs_), yv); rail(ctx, min(xs_), yv, "+3V3", stub=5.08)
    yg = sd.pin(bots_[0]["num"])[1] + 5.08
    for p in bots_:
        pp = sd.pin(p["num"]); s.wire(*pp, pp[0], yg)
    xg_ = [sd.pin(p["num"])[0] for p in bots_]
    s.wire(min(xg_), yg, max(xg_), yg); gnd(ctx, max(xg_), yg, stub=2.54)
    s.nc(*sd.pin("40"))
    decouple(ctx, 2500, 660.0, 70.0, "+3V3", ["10uF", "100nF", "100nF", "100nF", "100nF"], label="SDRAM: 100 nF per VDD/VDDQ pair")
    note(ctx, 560.0, 180.0, "Any address or data bit can be swapped for routing: the SDRAM controller does not care which ball is A5. "
                            "Clocked by an FPGA ODDR at up to 100 MHz, no termination, 3.3 V LVCMOS.", w=150, size=0.9)

    # ---- bank 2: Ethernet and GPDI; bank 3: SD, USB, UART, Pmods ----------------------------------
    xr_ = 760.0
    s.text(615.0, 219.0, "bank 2: Ethernet, HDMI", size=1.4, bold=True)
    unit_bus(ctx, u2, ["ETH_TXD%d" % i for i in range(3, -1, -1)], "ETH_TXD[3..0]", inv, 700.0, xr_, "output", elsewhere=stray)
    unit_bus(ctx, u2, ["ETH_RXD%d" % i for i in range(3, -1, -1)], "ETH_RXD[3..0]", inv, 710.0, xr_, "input", elsewhere=stray)
    for sname, sh in (("ETH_TXC", "output"), ("ETH_TX_CTL", "output"), ("ETH_RXC", "input"), ("ETH_RX_CTL", "input"),
                      ("ETH_MDC", "output"), ("ETH_MDIO", "bidirectional"), ("ETH_RST_N", "output"), ("ETH_INT_N", "input"),
                      ("GPDI_CK_P", "output"), ("GPDI_CK_N", "output"), ("GPDI_D0_P", "output"), ("GPDI_D0_N", "output"),
                      ("GPDI_D1_P", "output"), ("GPDI_D1_N", "output"), ("GPDI_D2_P", "output"), ("GPDI_D2_N", "output"),
                      ("GPDI_HPD", "input"), ("GPDI_CEC", "bidirectional"), ("GPDI_SCL", "bidirectional"), ("GPDI_SDA", "bidirectional")):
        single(ctx, u2, sname, inv, xr_, sh, side="right")
        hp.append((sname, sh))
    hp += [("ETH_TXD[3..0]", "output"), ("ETH_RXD[3..0]", "input")]
    s.text(615.0, 357.5, "bank 3: SD card, USB, serial, Pmods", size=1.4, bold=True)
    for sname, sh in (("SD_CLK", "output"), ("SD_CMD", "bidirectional"), ("SD_D0", "bidirectional"), ("SD_D1", "bidirectional"),
                      ("SD_D2", "bidirectional"), ("SD_D3", "bidirectional"), ("USB_DP", "bidirectional"), ("USB_DN", "bidirectional"),
                      ("USB_PULLUP", "output"), ("UART_RX", "input"), ("UART_TX", "output")):
        single(ctx, u3, sname, inv, xr_, sh, side="right")
        hp.append((sname, sh))
    # Pmods: buses from bank 3 down to two sockets below it
    for pm, (jref, xpm, ypm, xb) in enumerate((("J303", 640.0, 520.0, 700.0), ("J304", 740.0, 520.0, 710.0))):
        sig = ["PMOD%s_%d" % ("AB"[pm], i) for i in range(8)]
        members = [(unit_of(sn, u3).pin(inv[sn])[0], unit_of(sn, u3).pin(inv[sn])[1], sn) for sn in sig]
        ys_ = [m[1] for m in members]
        s.bus((xb, min(ys_) - 2.54), (xb, ypm - 20.32))
        s.label(xb, ypm - 30.48, "PMOD%s_[7..0]" % "AB"[pm], rot=90, size=1.0)
        for (mx, my, nm) in members:
            s.wire(mx, my, xb - 2.54, my); s.bus_entry(xb - 2.54, my, 2.54, -2.54); s.label(mx + 0.5, my - 0.2, nm, size=1.0)
        jp = part(ctx, "Connector_Generic:Conn_02x06_Odd_Even", jref, "PMOD %s" % "AB"[pm], "PMOD", xpm, ypm, ref_at=(xpm - 6.0, ypm - 10.0), val_at=(xpm - 6.0, ypm + 9.5))
        # the socket's pads are numbered the KiCad way (odd/even: column k of the 2 x 6 holds pads 2k-1 and
        # 2k), the Pmod standard numbers its pins 1-6 along one row and 7-12 along the other, so Pmod pin k
        # is pad 2k-1 and Pmod pin k+6 is pad 2k.  IO1-4 (Pmod 1-4) = pads 1, 3, 5, 7; IO5-8 (Pmod 7-10) =
        # pads 2, 4, 6, 8; GND (Pmod 5, 11) = pads 9, 10; VCC (Pmod 6, 12) = pads 11, 12.  (Rev A's first
        # draft had GND on pads 5/11 and VCC on 6/12: a module's pin 6 would have met GND and its pin 12
        # 3.3 V, a dead short through the module.)
        pinmap = {"1": sig[0], "3": sig[1], "5": sig[2], "7": sig[3], "2": sig[4], "4": sig[5], "6": sig[6], "8": sig[7]}
        xbl, xbr = xpm - 26.0, xpm + 26.0
        s.bus((xb, ypm - 20.32), (xbl, ypm - 20.32), (xbl, ypm + 10.16))
        s.bus((xbl, ypm - 20.32), (xbr, ypm - 20.32), (xbr, ypm + 10.16))
        for pin_, sname in pinmap.items():
            pj = jp.pin(pin_)
            # fields small and in the half row above each wire (the rows are 2.54 apart)
            if pj[0] < xpm:
                xr_ = pj[0] - 8.89
                r = R(ctx, 2600 + 10 * pm, "33R", xr_, pj[1], horiz=True, ref_at=(xr_ - 3.8, pj[1] - 0.55), val_at=(xr_ + 0.9, pj[1] - 1.95), fsize=1.0)
                s.wire(*r.pin(2), *pj); s.wire(*r.pin(1), xbl + 2.54, pj[1]); s.bus_entry(xbl + 2.54, pj[1], -2.54, -2.54); s.label(r.pin(1)[0] - 0.8, pj[1] - 0.2, sname, size=0.9, justify="right bottom")
            else:
                xr_ = pj[0] + 8.89
                r = R(ctx, 2600 + 10 * pm, "33R", xr_, pj[1], horiz=True, ref_at=(xr_ - 3.8, pj[1] - 0.55), val_at=(xr_ + 0.9, pj[1] - 1.95), fsize=1.0)
                s.wire(*r.pin(1), *pj); s.wire(*r.pin(2), xbr - 2.54, pj[1]); s.bus_entry(xbr - 2.54, pj[1], 2.54, -2.54); s.label(r.pin(2)[0] + 0.8, pj[1] - 0.2, sname, size=0.9)
        # GND on pads 9 (left) and 10 (right), VCC on 11 (left) and 12 (right): one bar per side joins the
        # two rows, the flag close to the pins so "+3V3" clears the series resistors' designators
        for pin_, dx in (("9", -3.81), ("10", 3.81)):
            pj = jp.pin(pin_); s.wire(*pj, pj[0] + dx, pj[1]); gnd(ctx, pj[0] + dx, pj[1], stub=0)
        for pin_, dx in (("11", -8.89), ("12", 8.89)):
            pj = jp.pin(pin_); s.wire(*pj, pj[0] + dx, pj[1]); rail(ctx, pj[0] + dx, pj[1], "+3V3", stub=0)
    note(ctx, 600.0, 548.0, "Pmod sockets (hand soldered), 0.9 inch apart on the board edge so a double-width module spans both: 33 Ω "
                            "series, Pmod pins 1-4 = IO0-3, 7-10 = IO4-7, 5/11 ground, 6/12 3.3 V (pads 1,3,5,7 / 2,4,6,8 / 9,10 / 11,12 "
                            "in KiCad's odd/even numbering). Both buses are drawn; the labels on the socket end are the same bus members.", w=200, size=0.9)
    # the RGB LED: three bank-3 balls sink its cathodes through 330 R, the common anode on +3V3 (active low)
    rgb_sigs = ["LED_R", "LED_G", "LED_B"]
    for sn in rgb_sigs:
        p = unit_of(sn, u3).pin(inv[sn]); s.wire(*p, p[0] + 6.35, p[1]); s.label(p[0] + 6.35, p[1], sn, size=1.0)
        hp.append((sn, "output")) if False else None
    xg, yg_ = 800.0, 500.0
    led = part(ctx, ids["rgb"], "D309", "XL-1615RGBC-RF", "RGB1615", xg + 25.4, yg_, ref_at=(xg + 20.0, yg_ - 7.5), val_at=(xg + 20.0, yg_ + 7.0))
    for k_, (sn, pin_) in enumerate(zip(rgb_sigs, ("1", "4", "3"))):
        pl_ = led.pin(pin_)
        xr_ = pl_[0] - 7.62 - 10.16 * k_                 # a staircase: the three resistors clear of each other's fields
        r = R(ctx, 2460, "330R", xr_, pl_[1], horiz=True, ref_at=(xr_ - 2.6, pl_[1] - 1.6), val_at=(xr_ + 2.0, pl_[1] - 1.6))
        s.wire(*r.pin(2), *pl_); s.wire(*r.pin(1), r.pin(1)[0] - 3.81, pl_[1]); s.label(r.pin(1)[0] - 3.81, pl_[1], sn, size=1.0, justify="right bottom")
    pa_ = led.pin("2"); s.wire(*pa_, pa_[0] + 2.54, pa_[1]); rail(ctx, pa_[0] + 2.54, pa_[1], "+3V3", stub=2.54)
    s.text(xg - 10.0, yg_ - 12.0, "RGB LED (common anode): drive a cathode low to light it, ~2 mA", size=0.85)

    # ---- bank 8: flash, config, JTAG, slow controls ------------------------------------------------
    s.text(395.0, 258.0, "bank 8: sysCONFIG, flash, JTAG, slow controls", size=1.4, bold=True)
    fl = part(ctx, ids["flash"], "U306", "W25Q128JVSIQ", "SOIC8W", 330.0, 262.0, ref_at=(312.0, 240.0), val_at=(312.0, 284.0))
    # six wires, top to bottom in the same order on both sides, so the channels never cross
    fmap = {"FLASH_IO2": "3", "FLASH_IO3": "7", "FLASH_CS_N": "1", "FLASH_IO1": "2", "FLASH_IO0": "5", "FLASH_SCK": "6"}
    for k, (sname, fpin) in enumerate(fmap.items()):
        pf = u8.pin(inv[sname]); pq = fl.pin(fpin)
        xk = pq[0] + 25.4 + (len(fmap) - 1 - k) * 1.27
        s.wire(*pq, xk, pq[1]); s.wire(xk, pq[1], xk, pf[1]); s.wire(xk, pf[1], *pf)
    label_node(ctx, 300.0, 232.0, "quad SPI flash on the sysCONFIG pins: boots the FPGA and holds the bitstream", side="right", size=0.85)
    ladder(ctx, 2700, [(fl.pin("3")[0] + 5.08, fl.pin("3")[1]), (fl.pin("7")[0] + 12.7, fl.pin("7")[1]), (fl.pin("1")[0] + 20.32, fl.pin("1")[1])],
           "10k", "+3V3", side="left", label="WP, HOLD, CS: 10 k up", label_at=(fl.pin("3")[0] + 8.0, fl.pin("3")[1] - 12.4))
    rail(ctx, *fl.pin("8"), "+3V3", stub=2.54); gnd(ctx, *fl.pin("4"), stub=2.54)
    c = C(ctx, 2700, "100nF", fl.pin("8")[0] - 10.16, fl.pin("8")[1] - 2.54 + 3.81, side="left"); s.wire(fl.pin("8")[0], fl.pin("8")[1] - 2.54, fl.pin("8")[0] - 10.16, fl.pin("8")[1] - 2.54); s.wire(fl.pin("8")[0] - 10.16, fl.pin("8")[1] - 2.54, *c.pin(1)); gnd(ctx, *c.pin(2), stub=0)
    # config pins on the right of the unit: PROGRAMN to a button, all three pulled up
    p9, t9, d9 = u8.pin("R9"), u8.pin("T9"), u8.pin("P9")
    s.wire(*p9, p9[0] + 25.4, p9[1])
    s.wire(*t9, t9[0] + 12.7, t9[1]); s.wire(*d9, d9[0] + 20.32, d9[1])
    ladder(ctx, 2710, [(p9[0] + 5.08, p9[1]), (t9[0] + 12.7, t9[1], "end"), (d9[0] + 20.32, d9[1], "end")], "4.7k", "+3V3",
           label="PROGRAMN, INITN, DONE: 4.7 k to VCCIO8")
    swp = part(ctx, "Switch:SW_Push", "SW303", "SW_Push", "SW_1088", p9[0] + 30.48, p9[1], rot=0, ref_at=(p9[0] + 26.5, p9[1] - 2.6), val_at=(p9[0] + 26.5, p9[1] + 1.6))
    l_, r_ = sorted([swp.pin(1), swp.pin(2)])
    s.wire(*r_, r_[0] + 2.54, r_[1]); gnd(ctx, r_[0] + 2.54, r_[1], stub=2.54)
    label_node(ctx, r_[0] + 7.0, p9[1] + 1.0, "press: reload from the flash", side="right", size=0.85)
    cfg = {"N10": ("GND", 5.08), "P10": ("+3V3", 12.7), "R10": ("GND", 5.08)}
    for ball, (net, dx) in cfg.items():
        p = u8.pin(ball); s.wire(*p, p[0] + dx, p[1])
        if net == "GND":
            gnd(ctx, p[0] + dx, p[1], stub=2.54)
        else:
            rail(ctx, p[0] + dx, p[1], "+3V3", stub=2.54)
    label_node(ctx, u8.pin("R10")[0] + 10.0, u8.pin("R10")[1] + 1.0, "CFG[2:0] = 010: master SPI boot from the flash (as the Icepi Zero)", side="right", size=0.85)
    # JTAG: to the USB sheet (FT2232H channel A) and a header; TMS/TDI/TDO up, TCK down.
    # The four rows are 5 mm apart, so the resistors hang below the lowest one
    jtag = {"T10": ("JTAG_TCK", "input"), "T11": ("JTAG_TMS", "input"), "R11": ("JTAG_TDI", "input"), "M10": ("JTAG_TDO", "output")}
    jh = part(ctx, "Connector_Generic:Conn_01x06", "J305", "JTAG", "H1x6", 560.0, 335.0, ref_at=(565.0, 326.0), val_at=(565.0, 345.0))
    x_end = u8.pin("T10")[0] + 36.83
    for k, (ball, (nm, sh)) in enumerate(jtag.items()):
        p = u8.pin(ball); s.wire(*p, x_end, p[1]); s.hlabel(x_end, p[1], nm, shape=sh)
        hp.append((nm, sh))
        pj = jh.pin(str(k + 2)); s.wire(*pj, pj[0] - 3.81, pj[1]); s.label(pj[0] - 3.81, pj[1] - 0.2, nm, size=0.9, justify="right bottom")
    xt = u8.pin("T11")[0]; y_bar = u8.pin("M10")[1] + 8.89
    ladder(ctx, 2720, [(xt + 7.62, u8.pin("T11")[1]), (xt + 15.24, u8.pin("R11")[1]), (xt + 22.86, u8.pin("M10")[1])], "4.7k", "+3V3",
           y_bar=y_bar, down=True)
    ladder(ctx, 2720, [(x_end - 3.81, u8.pin("T10")[1])], "4.7k", "GND", y_bar=y_bar, down=True)
    s.text(xt + 1.8, y_bar + 6.0, "4.7 k: TMS, TDI, TDO up; TCK down", size=0.85)
    s.wire(*jh.pin("1"), jh.pin("1")[0] - 3.81, jh.pin("1")[1]); rail(ctx, jh.pin("1")[0] - 3.81, jh.pin("1")[1], "+3V3", stub=2.54)
    s.wire(*jh.pin("6"), jh.pin("6")[0] - 3.81, jh.pin("6")[1]); gnd(ctx, jh.pin("6")[0] - 3.81, jh.pin("6")[1], stub=2.54)
    note(ctx, 545.0, 348.0, "JTAG header (hand soldered): the same four signals the FT2232H drives through the USB sheet. "
                            "TCK pulled down, TMS/TDI/TDO pulled up (Lattice checklist). These four local labels and the SDRAM "
                            "bus members are the only labels on this sheet.", w=120, size=0.9)
    for sname, sh in (("ADC_DCS", "output"), ("ADC_DFS", "output"), ("ADC_PDWN_A", "output"), ("ADC_PDWN_B", "output"), ("DAC_MODE", "output"), ("DAC_SLEEP", "output")):
        if bank_of[sname] == "8":
            p = u8.pin(inv[sname]); s.wire(*p, 345.0, p[1]); s.hlabel(345.0, p[1], sname, shape=sh, rot=180)
        else:
            pending[bank_of[sname]].append((sname, "hlabel", sh))       # the board put it on a neighbouring bank's ball (bank 6's south-face balls)
        hp.append((sname, sh))
    draw_pending()

    # ---- power unit, bottom left, with the decoupling rows ------------------------------------------
    up = part(ctx, ids["fpga"], "U1", "LFE5U-25F-6BG256C", FP_, 110.0, 505.0, unit=ids["fpga_power_unit"], ref_at=(60.0, 497.0), val_at=(60.0, 497.5))
    _, fpins = kisch.SYMS.get(ids["fpga"])
    pu = ids["fpga_power_unit"]
    vcc = [p for p in fpins if p["unit"] == pu and p["name"] == "VCC"]
    aux = [p for p in fpins if p["unit"] == pu and p["name"] == "VCCAUX"]
    vio = [p for p in fpins if p["unit"] == pu and p["name"].startswith("VCCIO")]
    gnds = [p for p in fpins if p["unit"] == pu and p["name"] == "GND"]

    def bar(group, yoff, net, side):
        pts = [up.pin(p["num"]) for p in group]
        yb = pts[0][1] - yoff
        for pt in pts:
            s.wire(*pt, pt[0], yb)
        s.wire(min(q[0] for q in pts), yb, max(q[0] for q in pts), yb)
        x_ = min(q[0] for q in pts) if side == "l" else max(q[0] for q in pts)
        rail(ctx, x_, yb, net, stub=3.81)
    bar(vcc, 5.08, "+1V1", "l"); bar(aux, 10.16, "+2V5_AUX", "l"); bar(vio, 15.24, "+3V3", "r")
    gp = [up.pin(p["num"]) for p in gnds]
    yg = gp[0][1] + 5.08
    for pt in gp:
        s.wire(*pt, pt[0], yg)
    s.wire(min(q[0] for q in gp), yg, max(q[0] for q in gp), yg); gnd(ctx, max(q[0] for q in gp), yg, stub=2.54)
    s.text(30.0, 480.0, "FPGA power: 6 x VCC (1.1 V core), 2 x VCCAUX (2.5 V through a ferrite), 13 x VCCIO (3.3 V, all banks), 27 x GND", size=1.0, bold=True)
    decouple(ctx, 2800, 215.0, 490.0, "+1V1", ["22uF", "10uF", "10uF", "10uF", "100nF", "100nF", "100nF", "100nF", "100nF", "100nF"], label="VCC: 3 x 10 µF + 100 nF per pin (Lattice checklist)", small="C0402B")
    fb = FB(ctx, 2810, 215.0, 517.0, horiz=True); s.wire(*fb.pin(1), 215.0 - 7.62, 517.0); rail(ctx, 215.0 - 7.62, 517.0, "+2V5", stub=5.08)
    s.wire(*fb.pin(2), 235.0, 517.0); pwr_flag(ctx, 227.0, 517.0)
    decouple(ctx, 2810, 235.0, 517.0, "+2V5_AUX", ["10uF", "100nF", "100nF"], label="VCCAUX: ferrite + 10 µF + 100 nF per pin", small="C0402B")
    decouple(ctx, 2820, 320.0, 517.0, "+3V3", ["10uF", "10uF", "10uF", "10uF", "10uF", "10uF", "10uF"], label="VCCIO: 10 µF per bank")
    decouple(ctx, 2830, 215.0, 543.0, "+3V3", ["100nF"] * 13, label="VCCIO: 100 nF per pin", small="C0402B")
    decouple(ctx, 2850, 365.0, 543.0, "+3V3", ["22nF"] * 7, label="VCCIO: 22 nF per bank (as the Icepi Zero)", small="C0402B")
    draw_pending()
    return hp
