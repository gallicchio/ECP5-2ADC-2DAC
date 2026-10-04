"""Drawing helpers shared by the sheets: passives with their LCSC code already
attached, decoupling rows, pull-ups, and a few geometric conveniences.
All coordinates are sheet millimetres (y down)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kisch
from kisch import snap
from parts import FP, lcsc_for

G = 1.27
S = 2.54


class Ctx:
    """Reference designator counters per sheet block, and the sheet itself."""
    OFFSET = {"ADC": 1000, "DAC": 2000, "FPGA": 3000, "ETH": 4000, "USB": 5000, "PWR": 6000}

    def __init__(self, sch, block=""):
        self.s = sch
        self.block = block
        self.off = self.OFFSET.get(block, 0)
        self.n = {}

    def ref(self, prefix, base):
        """Next designator: prefix + sheet offset + block base + running number,
        e.g. R1101 on the ADC sheet.  Unique across the whole project."""
        k = (prefix, base)
        self.n[k] = self.n.get(k, 0) + 1
        return "%s%d" % (prefix, self.off + base + self.n[k])


def part(ctx, lib, ref, value, fp_key, x, y, rot=0, mirror=None, unit=1, desc=None,
         ref_at=None, val_at=None, hide_value=False, hide_ref=False, dnp=False, fields=None, lcsc=None,
         justify="left", fsize=1.27):
    fp = FP.get(fp_key, fp_key)
    code = lcsc if lcsc is not None else lcsc_for(value, fp_key)
    return ctx.s.sym(lib, x, y, rot=rot, ref=ref, value=value, footprint=fp, unit=unit, mirror=mirror,
                     lcsc=code, desc=desc, ref_at=ref_at, val_at=val_at, hide_value=hide_value,
                     hide_ref=hide_ref, dnp=dnp, fields=fields, justify=justify, fsize=fsize)


def R(ctx, base, value, x, y, horiz=False, ref=None, ref_at=None, val_at=None, fp="R0603", side="right", fsize=1.27):
    """A resistor centred at (x, y).  Vertical by default (pin 1 up); horiz
    puts pin 1 on the LEFT.  Fields go beside it on `side`."""
    r = ref or ctx.ref("R", base)
    rot = 90 if horiz else 0
    if ref_at is None and val_at is None:
        if horiz:
            ref_at, val_at = (x - 2.6, y - 1.6), (x - 2.6, y + 1.3)
        elif side == "right":
            ref_at, val_at = (x + 1.9, y - 0.3), (x + 1.9, y + 0.3)
        else:
            ref_at, val_at = (x - 1.9, y - 0.3), (x - 1.9, y + 0.3)
    return part(ctx, "Device:R", r, value, fp, x, y, rot=rot, ref_at=ref_at, val_at=val_at,
                justify="right" if (side == "left" and not horiz) else "left", fsize=fsize)


def C(ctx, base, value, x, y, horiz=False, ref=None, ref_at=None, val_at=None, fp="C0402", side="right", fsize=1.27):
    r = ref or ctx.ref("C", base)
    rot = 90 if horiz else 0
    if ref_at is None and val_at is None:
        if horiz:
            ref_at, val_at = (x - 2.6, y - 1.9), (x - 2.6, y + 2.0)
        elif side == "right":
            ref_at, val_at = (x + 1.9, y - 0.3), (x + 1.9, y + 0.3)
        else:
            ref_at, val_at = (x - 1.9, y - 0.3), (x - 1.9, y + 0.3)
    return part(ctx, "Device:C", r, value, fp, x, y, rot=rot, ref_at=ref_at, val_at=val_at,
                justify="right" if (side == "left" and not horiz) else "left", fsize=fsize)


def FB(ctx, base, x, y, horiz=True, value="600R@100MHz", ref=None, fp="L0603"):
    r = ref or ctx.ref("FB", base)
    rot = 90 if horiz else 0
    lc = "C85833" if fp == "L0603" else "C1017"
    return part(ctx, "Device:FerriteBead", r, value, fp, x, y, rot=rot, lcsc=lc,
                ref_at=(x - 2.6, y - 1.9) if horiz else (x + 1.9, y - 0.3),
                val_at=(x - 2.6, y + 1.6) if horiz else (x + 1.9, y + 0.3))


def wire(ctx, *pts):
    ctx.s.wires(*pts)


def hjoin(ctx, a, b):
    """Wire from a to b with one bend: horizontal first, then vertical."""
    (x0, y0), (x1, y1) = a, b
    if y0 == y1 or x0 == x1:
        ctx.s.wire(x0, y0, x1, y1)
    else:
        ctx.s.wires((x0, y0), (x1, y0), (x1, y1))


def vjoin(ctx, a, b):
    """Wire from a to b with one bend: vertical first, then horizontal."""
    (x0, y0), (x1, y1) = a, b
    if y0 == y1 or x0 == x1:
        ctx.s.wire(x0, y0, x1, y1)
    else:
        ctx.s.wires((x0, y0), (x0, y1), (x1, y1))


def gnd(ctx, x, y, name="GND", stub=0, up=False):
    """A ground-style symbol below the point (x, y) with an optional stub;
    up=True hangs it above the point instead (for a negative rail feeding a
    part from above)."""
    if up:
        if stub:
            ctx.s.wire(x, y, x, y - stub)
        ctx.s.power(name, x, y - stub, down=True, rot=180)
        return
    if stub:
        ctx.s.wire(x, y, x, y + stub)
    ctx.s.power(name, x, y + stub, down=True)


def rail(ctx, x, y, name, stub=0):
    """A supply flag above the point (x, y)."""
    if stub:
        ctx.s.wire(x, y, x, y - stub)
    ctx.s.power(name, x, y - stub, down=False)


def decouple(ctx, base, x, y, railname, values, gndname="GND", pitch=10.16, label=None, small="C0402"):
    """A row of capacitors from a rail bar at y to a ground bar at y+10.16.
    Returns the x of the last one.  `label` is written above the rail bar."""
    xs = [x + i * pitch for i in range(len(values))]
    y0, y1 = y, y + 10.16
    ctx.s.wire(xs[0], y0, xs[-1], y0)
    ctx.s.wire(xs[0], y1, xs[-1], y1)
    for xi, v in zip(xs, values):
        fpk = small if v in ("100nF", "22nF", "10nF", "1uF", "1nF") else "C0603" if v in ("10uF", "4.7uF") else "C0805"
        c = C(ctx, base, v, xi, y0 + 5.08, fp=fpk)
        ctx.s.wire(xi, y0, *c.pin(1)); ctx.s.wire(*c.pin(2), xi, y1)
    rail(ctx, xs[0], y0, railname, stub=0)
    gnd(ctx, xs[-1], y1, gndname, stub=0)
    if label:
        ctx.s.text(xs[0] + 3, y0 - 1.0, label, size=1.0)
    return xs[-1]


def pullup(ctx, base, x, y, value, railname, down=False, side="right"):
    """A pull-up (or pull-down) resistor whose bottom pin is at (x, y)
    [top pin for a pull-down]."""
    ctx.s.junction(x, y)
    if not down:
        r = R(ctx, base, value, x, y - 5.08, side=side)
        ctx.s.wire(*r.pin(2), x, y)
        rail(ctx, *r.pin(1), railname, stub=2.54)
    else:
        r = R(ctx, base, value, x, y + 5.08, side=side)
        ctx.s.wire(x, y, *r.pin(1))
        gnd(ctx, *r.pin(2), stub=2.54)
    return r


def ladder(ctx, base, nodes, value, railname, y_bar=None, down=False, label=None, side="right", label_at=None):
    """Pull-ups (or pull-downs) for several parallel wires: ONE rail bar at
    y_bar and a resistor per node hanging from it, each on its own x.
    A node is (x, y) for a point inside a wire (gets a junction dot) or
    (x, y, "end") for the end of a wire (no dot).  The bar is above the
    nodes for pull-ups and below them for pull-downs, 3.5 rows away by
    default so that the bar and the resistor ends sit between rows; a
    resistor's drop wire may cross other rows (a plain crossing), its body
    never does because the bodies all sit beyond the outermost node."""
    s = ctx.s
    xs = [n[0] for n in nodes]
    if y_bar is None:
        y_bar = (min(n[1] for n in nodes) - 8.89) if not down else (max(n[1] for n in nodes) + 8.89)
    if len(xs) > 1:
        s.wire(min(xs), y_bar, max(xs), y_bar)
    for n in nodes:
        x, y = n[0], n[1]
        if len(n) < 3:
            s.junction(x, y)
        if not down:
            r = R(ctx, base, value, x, y_bar + 3.81, side=side)
            s.junction(x, y_bar) if x not in (min(xs), max(xs)) else None
            s.wire(*r.pin(2), x, y)
        else:
            r = R(ctx, base, value, x, y_bar - 3.81, side=side)
            s.junction(x, y_bar) if x not in (min(xs), max(xs)) else None
            s.wire(x, y, *r.pin(1))
    if not down:
        rail(ctx, min(xs), y_bar, railname, stub=2.54)
    elif railname.startswith("GND") or railname.startswith("-"):
        gnd(ctx, max(xs), y_bar, railname, stub=2.54)
    else:
        # a supply bar BELOW its nodes (pull-ups drawn hanging, for rows too
        # dense to put anything above): the flag still points up, past the
        # last resistor
        s.wire(max(xs), y_bar, max(xs) + 2.54, y_bar)
        rail(ctx, max(xs) + 2.54, y_bar, railname, stub=2.54)
    if label:
        lx, ly = label_at or (min(xs) + 3.0, y_bar - 3.5 if not down else y_bar + 4.5)
        ctx.s.text(lx, ly, label, size=0.85)


def note(ctx, x, y, s, cols=None, size=1.27, w=120.0):
    """A wrapped note box of width w mm (the wrap is computed from w)."""
    cols = cols or max(20, int(w / (0.78 * size)))
    return ctx.s.note(x, y, s, size=size, cols=cols, w=w)


def label_node(ctx, x, y, s, side="above", size=1.0):
    """A small annotation beside a node, AoE style ("1.65 V", "50 Ω")."""
    if side == "above":
        ctx.s.text(x, y - 0.8, s, size=size, justify="left bottom")
    elif side == "below":
        ctx.s.text(x, y + 0.8, s, size=size, justify="left top")
    elif side == "left":
        ctx.s.text(x - 0.8, y, s, size=size, justify="right bottom")
    else:
        ctx.s.text(x + 0.8, y, s, size=size, justify="left bottom")


def bus_out(ctx, x, y, name, members, dx=12.7, rot=0, shape="output", x_end=None):
    """Fan `members` (list of (x, y, netname)) into a bus running vertically at
    x, and put a hierarchical bus label at the top or at (x_end)."""
    ys = [m[1] for m in members]
    top, bot = min(ys) - 3.81, max(ys)
    ctx.s.bus((x, top), (x, bot))
    for (mx, my, nm) in members:
        # wire from the pin to the bus entry, entry rises into the bus
        ex = x - 2.54 if mx < x else x + 2.54
        ctx.s.wire(mx, my, ex, my)
        if mx < x:
            ctx.s.bus_entry(ex, my, 2.54, -2.54)
        else:
            ctx.s.bus_entry(ex, my, -2.54, -2.54)
        ctx.s.label(mx + 0.5 if mx < x else mx - 0.5, my - 0.2, nm, justify="left bottom" if mx < x else "right bottom", size=1.0)
    if x_end is None:
        ctx.s.hlabel(x, top, name, shape=shape, rot=90)
    else:
        ctx.s.bus((x, top), (x_end, top))
        ctx.s.hlabel(x_end, top, name, shape=shape, rot=0 if x_end > x else 180)
    return top


def pin_dy(lib_id, unit, pin):
    """y of `pin` relative to the symbol's placement point, for lining rows up."""
    t = kisch.Sch("t", "t.kicad_sch")
    return t.sym(lib_id, 0.0, 0.0, unit=unit, ref="X", value="").pin(pin)[1]


def pin_dx(lib_id, unit, pin):
    t = kisch.Sch("t", "t.kicad_sch")
    return t.sym(lib_id, 0.0, 0.0, unit=unit, ref="X", value="").pin(pin)[0]


def pwr_flag(ctx, x, y):
    """KiCad's PWR_FLAG: tells ERC this net is driven here."""
    ctx.n["FLG"] = ctx.n.get("FLG", 0) + 1
    ctx.s.junction(x, y)
    return ctx.s.sym("power:PWR_FLAG", x, y, rot=0, ref="#FLG%d" % (ctx.off + ctx.n["FLG"]), value="PWR_FLAG",
                     hide_ref=True, hide_value=True)
