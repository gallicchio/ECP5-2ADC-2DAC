"""The floorplan, by hand: every cluster of parts placed from its pads, not by a spiral search.

The rule (Prompt 11): design the floorplan first, then route each signal path through its chips, then
hang every passive directly off the pin it serves.  So each function here lays out one cluster --
an ADC input strip from its SMA to the converter, a DAC output strip from the converter to its SMA,
the PHY's crystal and straps at its pins, the Pmods' series resistors in line with their pins -- as
explicit coordinates computed from the footprints' pad positions, with the part's rotation chosen so
that the pad on a given net faces the right way.  The two ADC strips are the same code with a mirror
flag, the two DAC strips too, so they come out identical.

Board frame: 150 x 118 mm, origin top-left, x right, y down.  Layout:

    left edge    six right-angle SMA jacks (4 legs + pin, barrel 7 mm past the edge), 17 mm apart: CLK IN 12, CLK OUT 29, ADC A 46, ADC B 63,
                 DAC 1 80, DAC 2 97 (A above B and 1 above 2; port 2's pair crosses under port 1's columns on In2
                 to reach the lower strip)
    x 8-46       the analog strips: one per SMA, each a straight run from the SMA to its converter
    x 46-54      AD9238 (y 57) and AD9767 (y 93), both 10 mm from the FPGA's west exit line
    x 64-80      the ECP5, SDRAM above it, flash and JTAG below
    x 94-136     Ethernet (PHY, magnetics on the back) upper right, FT2232H middle right, the Pmods'
                 series resistors lower right
    right edge   RJ45, USB PROG, USB USER, mini-HDMI, Pmod B, Pmod A (0.9 inch apart); microSD on
                 the back, inboard, south-east of the FPGA
    bottom       the power section (bucks, fuse, 5 V IN, RAILS header, power-good LEDs) in the middle
"""
import math
import fplib

from place import BW, BH          # one source of truth for the board's size (pcb/place.py)
FPGA = (72.0, 58.0)
E = BW - 150.0          # the east cluster's shift: everything from the PHY to the right edge was drawn for a 150 mm board

# --- the fixed anchors: ICs and connectors ------------------------------------------------------------
SMA_Y = {"J301": 12.0, "J302": 29.0, "J101": 46.0, "J102": 63.0, "J204": 80.0, "J205": 97.0}    # CLK IN, CLK OUT, ADC A, ADC B, DAC 1, DAC 2: 17 mm apart (DAC 1 above DAC 2 since build 28)
ANCHORS = {
    "H1": (4.2, 4.2, 0), "H2": (BW - 4.2, 4.2, 0), "H3": (4.2, BH - 4.2, 0), "H4": (BW - 4.2, BH - 4.2, 0),
    "U1": (FPGA[0], FPGA[1], 0),
    "U305": (72.0, 36.5, 0),                                   # SDRAM, rows pointing at the FPGA (the river)
    "U306": (80.5, 78.0, 0), "SW303": (92.0, 79.8, 0),         # flash under the south face (east of the DAC's lanes), the PROG button beside it
    "J305": (94.0, 72.6, 90),                                  # JTAG header, pins along x
    "U103": (50.0, 54.5, 0),                                   # AD9238: inputs west (A above B), data east/north/south; its east row on bank 7's exits
    "U201": (50.0, 88.5, 0),                                   # AD9767: outputs north (port 1 west of port 2), port 2 data east (the near row), port 1 west (under the body), clocks south
    "U401": (104.0 + E, 24.0, 180),                                # PHY: MDI east, TX north, RX west, crystal/straps south
    "T401": (128.0 + E, 19.0, 270, "B.Cu"), "J401": (139.6 + E, 19.0, 90),
    "U502": (115.0 + E, 46.0, 180),                                # FT2232H: USB east, UART west, JTAG north-east, EEPROM south
    "J501": (147.68 + E, 34.5, 90), "J502": (147.68 + E, 48.0, 90), "J503": (145.93 + E, 62.0, 90),   # 13.5 mm between the USBs, 14 to the HDMI: spec-maximum plugs side by side.  Faces 1.9 (USB-C) and 0.75 mm (HDMI) past the edge (build 26): as far as their rear through-hole pads allow (0.35 mm to the edge); the end plates' cutouts admit the plugs' overmoulds
    "J304": (137.4 + E, 85.14, 180), "J303": (137.4 + E, 108.0, 180),   # Pmod B above Pmod A, 22.86 mm apart (0.9 inch)
    "J504": (106.0 + E, 84.0, 90, "B.Cu"),                          # microSD on the back, card toward the right edge
}
for _r, _y in SMA_Y.items():
    ANCHORS[_r] = (4.5, _y, 90)
ANCHORS = {k: (v if len(v) == 4 else (v[0], v[1], v[2], "F.Cu")) for k, v in ANCHORS.items()}
QUIET = set()          # parts whose placer-box overlap is known and fine (their true courtyards clear)


# --- helpers -------------------------------------------------------------------------------------------
def pads_at(pl, ref, x, y, rot, layer="F.Cu"):
    return fplib.pads_at(pl.fp[ref], x, y, rot, back=(layer == "B.Cu"))


def pad_of(pl, ref, net=None, num=None):
    """The placed pad of `ref` carrying `net` (or numbered `num`)."""
    pn = pl.nets.get(ref, {})
    if num is None:
        nums = [k for k, v in pn.items() if v == net]
        if not nums:
            raise SystemExit("floorplan: %s has no pad on %s (pads: %s)" % (ref, net, pn))
        num = nums[0]
    return pl.padpos[(ref, num)]


def net_of(pl, ref, num):
    return pl.nets.get(ref, {}).get(str(num), "")


def rot_for(pl, ref, net, side, layer="F.Cu"):
    """The rotation (0/90/180/270) that puts `ref`'s pad on `net` toward `side` ('W','E','N','S')
    of the part's centre.  Two- or three-pad parts.  On the back the footprint is mirrored first
    (fplib.pads_at), so the rotation is chosen on the mirrored pads."""
    pn = pl.nets[ref]
    nums = [k for k, v in pn.items() if v == net]
    if not nums:
        raise SystemExit("floorplan: %s has no pad on net %s" % (ref, net))
    num = nums[0]
    best = None
    for rot in (0, 90, 180, 270):
        ps = pads_at(pl, ref, 0.0, 0.0, rot, layer)
        cx = sum(p["x"] for p in ps) / len(ps); cy = sum(p["y"] for p in ps) / len(ps)
        for p in ps:
            if p["num"] != num:
                continue
            # relative to the pads' centroid: a header's pin 1 sits at the footprint origin whatever the rotation
            score = {"W": cx - p["x"], "E": p["x"] - cx, "N": cy - p["y"], "S": p["y"] - cy}[side]
            if best is None or score > best[0] + 1e-9:
                best = (score, rot)
    return best[1]


OVERLAPS = []          # (ref, other) whose true courtyards overlap: a placement mistake to fix
SECTION = [None]       # the section the clusters are placing into (the silkscreen draws a box round each)
ANCHOR_SECTION = {"U305": "SDRAM 32 MB", "U306": "FLASH + JTAG", "SW303": "FLASH + JTAG", "J305": "FLASH + JTAG",
                  "U401": "ETHERNET", "J401": "ETHERNET", "U502": "FTDI + USB", "J501": "FTDI + USB", "J502": "FTDI + USB",
                  "J503": "HDMI", "J304": "PMODS", "J303": "PMODS"}


def put(pl, ref, x, y, rot, layer="F.Cu", quiet=True):
    if ref not in pl.fp:
        raise SystemExit("floorplan: no footprint for %s" % ref)
    x, y = round(x, 3), round(y, 3)
    # the real courtyards (the placer's own boxes carry a 0.5 mm margin for its spiral search)
    x0, y0, x1, y1 = fplib.box_at(pl.fp[ref], x, y, rot, back=(layer == "B.Cu"), grow=0.0)
    if x0 < 0.3 or y0 < 0.3 or x1 > BW - 0.3 or y1 > BH - 0.3:
        if not ref.startswith(("J", "H")):
            print("  CLUSTER: %s at (%.1f, %.1f) is off the board" % (ref, x, y))
    for r2, (xx, yy, rr, ll) in pl.placed.items():
        if r2 == ref or (ll != layer and not pl.fp[r2]["th_any"] and not pl.fp[ref]["th_any"]):
            continue
        if ll != layer:
            # a through-hole part's body is on its own side; on the other side only its holes count (0.3 mm round them)
            th_ref, th_other = (r2, (ref, x, y, rot, layer)) if pl.fp[r2]["th_any"] else (ref, (r2, xx, yy, rr, ll))
            tx_, ty_, tr_, tl_ = (xx, yy, rr, ll) if th_ref == r2 else (x, y, rot, layer)
            o_ref, ox, oy, orr, oll = th_other
            c0, d0, c1, d1 = fplib.box_at(pl.fp[o_ref], ox, oy, orr, back=(oll == "B.Cu"), grow=0.0)
            hit = False
            for p in fplib.pads_at(pl.fp[th_ref], tx_, ty_, tr_, back=(tl_ == "B.Cu")):
                if not p.get("th"):
                    continue
                r_ = max(p["w"], p["h"]) / 2.0 + 0.3
                if p["x"] + r_ > c0 and p["x"] - r_ < c1 and p["y"] + r_ > d0 and p["y"] - r_ < d1:
                    hit = True
            if hit:
                OVERLAPS.append((ref, r2))
                print("  CLUSTER OVERLAP: %s (%.1f,%.1f) sits on a hole of %s" % (o_ref, ox, oy, th_ref))
            continue
        a0, b0, a1, b1 = fplib.box_at(pl.fp[r2], xx, yy, rr, back=(ll == "B.Cu"), grow=0.0)
        if x0 < a1 - 1e-6 and a0 < x1 - 1e-6 and y0 < b1 - 1e-6 and b0 < y1 - 1e-6:
            OVERLAPS.append((ref, r2))
            print("  CLUSTER OVERLAP: %s (%.1f,%.1f) and %s (%.1f,%.1f) by %.2f x %.2f mm" % (ref, x, y, r2, xx, yy, min(x1, a1) - max(x0, a0), min(y1, b1) - max(y0, b0)))
    pl.put(ref, x, y, rot, layer)
    if SECTION[0]:
        pl.section[ref] = SECTION[0]
    if quiet:
        QUIET.add(ref)


def put_facing(pl, ref, x, y, net, side, layer="F.Cu"):
    """Place a 2/3-pad part at (x, y) rotated so its pad on `net` faces `side`."""
    put(pl, ref, x, y, rot_for(pl, ref, net, side, layer), layer)


def partners(pl, ref, net):
    """The other parts' pads on `net`: [(ref, num)]."""
    return [(r, n) for (r, n) in pl.bynet.get(net, []) if r != ref]


def find(pl, value=None, nets=(), prefix="", hint_sheet=None):
    """Parts matching a value, carrying all of `nets`, with a designator prefix."""
    out = []
    for r, pn in pl.nets.items():
        if prefix and not r.startswith(prefix):
            continue
        if value is not None and pl.vals.get(r) != value:
            continue
        if any(n not in pn.values() for n in nets):
            continue
        if hint_sheet and pl.hints.get(r, ("",))[0] != hint_sheet:
            continue
        out.append(r)
    return sorted(out)


def one(pl, **kw):
    r = find(pl, **kw)
    if len(r) != 1:
        raise SystemExit("floorplan: expected one part for %s, found %s" % (kw, r))
    return r[0]


# --- the ADC input strips ------------------------------------------------------------------------------
HAND = []              # hand-laid copper: (layer, net, [(x, y), ...], width) and vias as ("via", net, x, y, size, drill)


def adc_strip(pl, ch):
    """One ADC front end as a straight run east from its SMA at y_s to the AD9238's input pair.

    SMA -> [49.9 R lying above the line, its TERM jumper above that] -> 100 R in line -> BAV99 clamp
    hanging below the next node -> SRC jumper below the line (its centre pin feeds the line, the SMA
    on its west pin, the alternate source on its east pin) -> OPA1612 stage 1 (pins 1-3 west; its
    9.1 k standing above-left, the 1 k west of that, the GAIN jumper on top) -> stage 2 (pins 5-7 east;
    9.1 k on the line, out one row up, 1 k hanging below, the GAIN jumper under the chip) -> 499 R
    -> THS4521 (inputs west, outputs east, feedback resistors along its north and south sides, the
    22 pF beside those) -> 33 R on each output row -> the two lines turn south in two columns and
    enter the converter's VIN pins.  Channel B is the same strip 17 mm lower; the converter's pin
    order makes channel A's two lines swap, which one short In2 hop on its VIN+ line absorbs."""
    n = 1 if ch == "A" else 2
    base = 1100 if ch == "A" else 1200
    y_s = SMA_Y["J101" if ch == "A" else "J102"]
    R = lambda k: "R%d" % (base + k)
    C = lambda k: "C%d" % (base + k)
    JP = lambda k: "JP%d" % (100 * n + k)
    U_op, U_fda, D_cl = "U10%d" % n, "U11%d" % n, "D10%d" % n
    sma_net = pl.nets["J10%d" % n]["1"]
    # termination (below the line since build 28, so the strip's top row is the GAIN jumper's and its label's):
    # 49.9 R lying under the line (SMA pad west), its jumper lying in the strip's bottom-left corner, "50Ω IN" over it.
    # (A 2.54 mm header's anchor is its PIN 1: a 1x2 lying along x reaches 6.1 mm east of its anchor, a 1x3 8.6)
    put_facing(pl, R(1), 10.5, y_s + 1.9, sma_net, "W")
    put_facing(pl, JP(1), 10.7, y_s + 6.6, net_of(pl, JP(1), 1), "W")   # TERM jumper, its 50 R pin west
    # the 100 R in line (a 1206 since build 26: 0.25 W); the clamp below the node after it, common pin up, rail pins down
    put_facing(pl, R(2), 12.3, y_s, sma_net, "W")
    put_facing(pl, D_cl, 16.9, y_s + 2.3, net_of(pl, D_cl, 3), "N")
    # the source jumper under the line: pin 3 (from the clamp node) west, pin 1 (the alternate) east
    put_facing(pl, JP(2), 26.0, y_s + 6.5, net_of(pl, JP(2), 3), "W")   # (1.9 lower since build 28: its two choices stand between it and the op amp, each over its pin, a line from the centre pin)
    if ch == "B":
        put_facing(pl, "JP1203", 23.5, y_s + 10.3, net_of(pl, "JP1203", 1), "W")      # ALT: PHOTODIODE pin west, NOISE pin east, under the SRC jumper in the strip's notch, its choices off its ends
    # stage 1: in+ (pin 3) on the line
    x_u = 27.0
    put(pl, U_op, x_u, y_s - 0.64, 0)
    in1n, out1 = net_of(pl, U_op, 2), net_of(pl, U_op, 1)
    put_facing(pl, R(3), 22.4, y_s - 3.0, in1n, "S")               # 9.1 k standing: in- pad down, out pad up
    put_facing(pl, JP(3), 19.86, y_s - 6.5, out1, "E")             # GAIN jumper on top, out pin over the resistor's out pad; "x1 IN / x10 OUT" west of it, where the TERM jumper stood
    put_facing(pl, R(4), 18.0, y_s - 3.38, in1n, "E")              # 1 k to ground, west of the in- node
    put_facing(pl, C(2), 20.0, y_s - 1.8, "-4V2", "E")             # V- (pin 4) 100 nF lying west of the chip, above the line (build 28: under the chip it took the SRC jumper's choices' room)
    # stage 2: in- (pin 6) on the line, out (pin 7) one row up, the 9.1 k on the line, 1 k hanging below,
    # the GAIN jumper under the chip, the 499 R into the FDA on the out row
    in2n, out2 = net_of(pl, U_op, 6), net_of(pl, U_op, 7)
    put_facing(pl, R(5), 32.6, y_s, in2n, "W")
    put_facing(pl, R(6), 31.5, y_s + 2.4, in2n, "N")
    put_facing(pl, JP(4), 33.0, y_s + 5.8, in2n, "W")              # pin A (in-) west, pin B (out) east ("x1" west of it: the strip has no room for more)
    put_facing(pl, C(1), 32.0, y_s - 2.9, "+5VA", "W")             # V+ (pin 8) 100 nF
    put_facing(pl, R(7), 35.7, y_s - 1.28, out2, "W")              # 499 R: out2 west, FDA in+ east
    # the FDA
    x_f = 40.5
    fda_inp, fda_inn = net_of(pl, U_fda, 8), net_of(pl, U_fda, 1)
    put(pl, U_fda, x_f, y_s, 90)                                   # in+ NW, in- SW, OUT- NE, OUT+ SE
    put_facing(pl, R(8), 35.3, y_s + 2.3, fda_inn, "E")            # 499 R to ground on the in- row
    put_facing(pl, "D11%d" % n, 37.8, y_s, fda_inp, "N", "B.Cu")    # the BAV99 across the FDA's inputs: on the back under its input pins, common pad (IN+) north
    # the monitor tap: 49.9 R from the second stage's output into a U.FL (A: above the strip, B: in the strip's
    # notch below the SRC jumper -- above B is the converter)
    out2_ = net_of(pl, U_op, 7)
    put_facing(pl, R(13), 34.9, y_s - 3.3, out2_, "E")               # lying under the U.FL, its out2 pad east toward the 499 R
    put_facing(pl, "J10%d" % (6 + n), 32.8, y_s - 5.7, net_of(pl, "J10%d" % (6 + n), 1), "S")   # the U.FL in the strip's top row, "TAP A/B" west of it (B's sat in the strip's notch in builds 26-27; both strips are one code again since build 28)
    outn, outp = net_of(pl, U_fda, 5), net_of(pl, U_fda, 4)
    put_facing(pl, R(9), 39.4, y_s - 4.9, fda_inp, "W")            # feedback along the north side (0.5 lower since build 28: the strip's name stands over it, under the box's top edge)
    put_facing(pl, R(10), 39.4, y_s + 5.4, fda_inn, "W")           # feedback along the south side
    put_facing(pl, C(3), 38.7, y_s + 3.9, net_of(pl, U_fda, 2), "E")   # VOCM 100 nF under pin 2
    put_facing(pl, C(4), 40.9, y_s + 3.9, "+3V3_ADC", "W")         # VS+ 100 nF under pin 3
    put_facing(pl, R(11), 42.5, y_s - 5.2, outn, "W")              # 33 R on the OUT- row (0.2 lower since build 28: the strip's name over it)
    put_facing(pl, R(12), 42.5, y_s + 5.4, outp, "W")              # 33 R on the OUT+ row
    put_facing(pl, C(5), 43.1, y_s - 3.8, "GND", "W")              # 22 pF to ground off the VIN- node
    put_facing(pl, C(6), 43.0, y_s + 3.9, "GND", "W")              # 22 pF off the VIN+ node
    # the entry into the converter, by hand: VIN- down (A) / up (B) the inner column at x 44.1, VIN+ the
    # outer one at 44.7; channel A's VIN+ hops to In2 under the VIN- column
    vin_n, vin_p = net_of(pl, R(11), 2), net_of(pl, R(12), 2)
    pn = pad_of(pl, "U103", vin_n); pp = pad_of(pl, "U103", vin_p)
    xe = pn[0] - 0.75                                              # the pads' west ends
    rn2, rp2 = pad_of(pl, R(11), vin_n), pad_of(pl, R(12), vin_p)
    cn2, cp2 = pad_of(pl, C(5), vin_n), pad_of(pl, C(6), vin_p)
    w = 0.15
    HAND.append(("F.Cu", vin_n, [rn2, (44.1, rn2[1] + (0.5 if ch == "A" else -0.5)), (44.1, pn[1]), (xe, pn[1])], w))
    HAND.append(("F.Cu", vin_n, [cn2, (44.1, cn2[1])] + ([(44.1, rn2[1] - 0.5)] if ch == "B" else []), w))   # B's capacitor sits south of the column's start
    if ch == "B":
        HAND.append(("F.Cu", vin_p, [rp2, (44.7, rp2[1] - 1.0), (44.7, pp[1]), (xe, pp[1])], w))
        HAND.append(("F.Cu", vin_p, [cp2, (44.1 - 0.5, cp2[1]), (44.7, cp2[1] + 0.6)], w))
    else:
        HAND.append(("F.Cu", vin_p, [rp2, (43.5, rp2[1])], w))
        HAND.append(("via", vin_p, 43.5, rp2[1], 0.3, 0.15))
        HAND.append(("In2.Cu", vin_p, [(43.5, rp2[1]), (44.7, pp[1] - 0.6)], w))        # the second via north of the pad's row: C1311 sits south of it
        HAND.append(("via", vin_p, 44.7, pp[1] - 0.6, 0.3, 0.15))
        HAND.append(("F.Cu", vin_p, [(44.7, pp[1] - 0.6), (44.7, pp[1]), (xe, pp[1])], w))
        HAND.append(("F.Cu", vin_p, [cp2, (43.5, cp2[1]), (43.5, rp2[1])], w))


def adc_common(pl):
    p16 = pad_of(pl, "U103", num="16")                                  # GND, the west row's south end: its stitching via by hand
    HAND.append(("F.Cu", "GND", [p16, (p16[0] + 0.8, p16[1]), (p16[0] + 1.07, p16[1] + 0.05)], 0.25))
    HAND.append(("via", "GND", p16[0] + 1.07, p16[1] + 0.05, 0.3, 0.15))
    """The AD9238's own parts: clock resistors at its clock pins, the reference and supply capacitors
    on the back under the pins they serve (the 0.4 mm west row has no room in front of it: the two
    strips' input columns arrive there)."""
    ax, ay = ANCHORS["U103"][0], ANCHORS["U103"][1]
    put_facing(pl, "R1301", ax - 2.6, ay - 6.9, net_of(pl, "U103", 63), "S")      # ADC_A_CLK -> pin 63 (north row)
    put_facing(pl, "R1302", ax - 2.6, ay + 6.9, net_of(pl, "U103", 18), "N")      # ADC_B_CLK -> pin 18 (south row)
    # references on the back: REFT/REFB pairs (10 u + 100 n across, 100 n each to ground), VREF 1 u + 100 n
    back = [("C1311", ax - 5.6, ay - 1.5, 90), ("C1312", ax - 4.3, ay - 1.5, 90), ("C1313", ax - 8.0, ay - 2.2, 0), ("C1314", ax - 7.7, ay - 0.8, 0),
            ("C1321", ax - 5.6, ay + 1.5, 90), ("C1322", ax - 4.3, ay + 1.5, 90), ("C1323", ax - 7.7, ay + 0.8, 0), ("C1324", ax - 7.7, ay + 2.2, 0),
            ("C1331", ax - 10.0, ay - 0.6, 0), ("C1332", ax - 10.0, ay + 0.6, 0),
            ("C1342", ax - 4.1, ay - 3.8, 0), ("C1343", ax - 4.1, ay + 3.8, 0),                      # AVDD 100 n at pins 5 and 12
            ("C1341", ax - 6.5, ay - 5.3, 0), ("C1351", ax - 6.5, ay + 5.3, 0)]                      # the 10 u of AVDD and DRVDD
    for ref, x, y, rot in back:
        put(pl, ref, x, y, rot, "B.Cu")
    # AVDD / DRVDD on the front at the north and south rows' supply pins, east of the clock resistors
    put(pl, "C1344", ax - 2.0, ay - 8.0, 0, "B.Cu")                 # pins 61/62/64 (north row): back, beyond the side row's vias
    put(pl, "C1345", ax - 3.0, ay + 8.0, 0, "B.Cu")                 # pin 17 (south row): back
    put(pl, "C1352", ax + 3.0, ay - 8.0, 0, "B.Cu")                 # DRVDD pin 52 (north row): back
    put(pl, "C1353", ax + 2.0, ay + 8.0, 0, "B.Cu")                 # DRVDD pin 29 (south row): back
    put(pl, "C1354", ax + 6.5, ay - 0.2, 0, "B.Cu")                 # DRVDD pin 41 (east row, under the river): on the back


# --- the DAC output strips -----------------------------------------------------------------------------
def dac_strip(pl, port):
    """One DAC output stage as a straight run west from the AD9767 to its SMA at y_s: port 1 in the UPPER strip
    (DAC 1 OUT, y 80), port 2 in the lower (DAC 2 OUT, y 97) -- DAC 1 above DAC 2 as ADC A is above ADC B
    (Jason, 2026-10-07: the other order was going to confuse every student).

    The converter sits at rot 0 with its current outputs on its north row, port 1's pair (IOUTA1 pin 46 at
    x 48.25, IOUTB1 pin 45 at 48.75) west of port 2's (IOUTA2 pin 39 at 51.75, IOUTB2 pin 40 at 51.25).
    Port 1's pair rises straight into the upper strip's in+ and in- rows; its A pad is west of its B pad while
    A's row (in+) is the upper one, so B hops under A's column on In2 for 1.5 mm.  Port 2's pair rises to two
    rows (A, the east pad, on the upper one), crosses under port 1's columns on In2, west past the chip's
    corner, and drops down two front-side columns 0.5 mm apart along the chip's west side into the lower
    strip: A on the outer column (43.5), B on the inner (44.0), so nothing crosses.  The 24.9 R loads stand
    inside the strip on the runs (builds to 27 had them beside the converter, outside the strip's box), the
    499 R are in line.  The OPA2810 faces the converter (pins 1-3 east): 2.2 k to ground above in+,
    2.2 k || 2.2 pF feedback standing east of the pins, V- capacitor above, V+ under pin 8.  The output leaves
    pin 1 south, wraps under the chip and runs west on the line through 49.9 R to the SMA.  Port 1's second
    half drives the LED (U202B, as the sheet draws it): 100 R into the NPN, 10 R sense, the LED / EXT jumper
    and the on-board LED in the strip's bottom row, the EXT header under the feedback parts."""
    y_s = SMA_Y["J204" if port == 1 else "J205"]
    base = 2400 if port == 1 else 2500
    R = lambda k: "R%d" % (base + k)
    C1 = "C%d" % (base + 1)
    U = "U202" if port == 1 else "U203"
    cv_p, cv_n = ("C2601", "C2602") if port == 1 else ("C2701", "C2702")
    x_o = 28.0
    y_o = y_s - 1.4                                                 # (0.3 mm lower than before: the strips' boundary clears its pads)
    put(pl, U, x_o, y_o, 180)                                      # pins 1-3 east: out, in-, in+ (bottom to top)
    inp, inn, out = net_of(pl, U, 3), net_of(pl, U, 2), net_of(pl, U, 1)
    ioa, iob = net_of(pl, R(3), 1), net_of(pl, R(4), 1)            # the converter's IOUTA / IOUTB
    put_facing(pl, R(3), x_o + 9.5, y_s - 2.63, inp, "W")           # 499 R into in+ (its far pad at 38.32)
    put_facing(pl, R(4), x_o + 7.0, y_s - 1.1, inn, "W")            # 499 R into in- (its far pad at 35.82), clear of the 2 k
    put_facing(pl, R(5), x_o + 4.6, y_s - 3.1, inp, "S")            # 2.2 k to ground above in+
    put_facing(pl, "C%d" % (base + 2), x_o + 5.9, y_s - 3.1, inp, "S")   # its 2.2 pF (build 26: the AC balance of the difference amplifier)
    put_facing(pl, cv_n, x_o + 8.6, y_s - 6.4, "-4V2", "S")         # V- (pin 4) capacitor above the 499 R row
    put_facing(pl, R(6), x_o + 5.5, y_s + 0.9, inn, "E")            # 2.2 k feedback: in- east, out west
    put_facing(pl, C1, x_o + 5.5, y_s + 2.2, inn, "E")              # 2.2 pF in parallel
    put_facing(pl, cv_p, x_o - 2.5, y_s + 2.9, "+5VA", "N")         # V+ (pin 8) capacitor standing under the pin
    put_facing(pl, R(7), 16.0, y_s, out, "E")                       # 49.9 R on the line to the SMA
    pa, pb = pad_of(pl, "U201", ioa), pad_of(pl, "U201", iob)     # IOUTA / IOUTB pads (north row, y 84.34)
    y_e = pa[1] - 0.75                                             # the pads' north ends
    rA, rB = pad_of(pl, R(3), ioa), pad_of(pl, R(4), iob)          # the 499 R's far pads
    w = 0.2
    if port == 1:
        # A (west pad) north and 45 degrees west into the in+ row.  B (east pad) north to y_hop, under A's column
        # on In2, back on the front and 45 degrees into the in- row (parallel to A's diagonal, 1.5 mm south of it)
        HAND.append(("F.Cu", ioa, [(pa[0], y_e), (pa[0], rA[1] + 2.03), (pa[0] - 2.03, rA[1]), rA], w))
        # the hop's vias thread the DAC's back-side bias parts (dac_common: R2301 at x 47.0 and C2342 at 48.5 reach
        # north to y 80.1, R2311 in the far row at 49.25 reaches south to 79.56): y 79.9, 1.0 mm apart, one on B's
        # own column and one a pitch west of A's (build 28's first run put them on R2301 and C2342; at 80.1 they
        # left C2342's ground pad no room for its via, which sits at (48.4, 80.4) now)
        y_hop = 79.9
        HAND.append(("F.Cu", iob, [(pb[0], y_e), (pb[0], y_hop)], w))
        HAND.append(("via", iob, pb[0], y_hop, 0.3, 0.15)); HAND.append(("In2.Cu", iob, [(pb[0], y_hop), (pb[0] - 1.0, y_hop)], w)); HAND.append(("via", iob, pb[0] - 1.0, y_hop, 0.3, 0.15))
        HAND.append(("F.Cu", iob, [(pb[0] - 1.0, y_hop), (pb[0] - 1.0 - 1.6, rB[1]), rB], w))
        put_facing(pl, R(1), 43.5, y_s - 5.0, ioa, "S")             # 24.9 R load standing over the in+ run, inside the strip
        put_facing(pl, R(2), 42.5, y_s - 0.1, iob, "N")             # 24.9 R load standing under the in- run (its ground pad 0.3 mm clear of port 2's run at 81.1)
        HAND.append(("F.Cu", ioa, [pad_of(pl, R(1), ioa), (43.5, rA[1])], w))
        HAND.append(("F.Cu", iob, [pad_of(pl, R(2), iob), (42.5, rB[1])], w))
        # the LED driver on the spare half (pins 5-7, west side): out2 -> 100 R -> base; emitter -> 10 R -> ground
        # and back to in-2; collector -> the LED/EXT jumper under the chip; the on-board LED west of it; EXT header above
        put_facing(pl, "R2508", x_o - 4.6, y_s + 0.05, net_of(pl, U, 7), "N")
        put_facing(pl, "Q201", x_o - 7.45, y_s - 1.4, net_of(pl, "Q201", 3), "W")   # collector west, base SE, emitter NE (0.95 east since build 28: the strip's name stands in the top-left corner, west of it)
        put_facing(pl, "R2509", x_o - 4.6, y_s - 3.1, net_of(pl, "Q201", 2), "S")   # 10 R sense above the emitter
        # the bottom row of the strip, west to east: the on-board LED, the LED/EXT jumper (its choices labelled above it), the EXT header
        put_facing(pl, "JP2009", x_o - 10.4, y_s + 3.6, net_of(pl, "JP2009", 1), "W")  # lying along the row: LED pin west (toward D201), EXT pin east (toward J210); its choices under the pins (the row 0.8 up: room for them over the strip's bottom edge)
        put_facing(pl, "D201", x_o - 16.75, y_s + 3.6, net_of(pl, "D201", 1), "E")   # the on-board LED west of it, cathode toward the jumper
        put_facing(pl, "J210", x_o + 5.0, y_s + 4.6, net_of(pl, "J210", 2), "E")    # EXT header under the op amp's feedback parts, its LED pin east (0.8 mm higher it meets C2401's courtyard: build 20)
    else:
        # A (east pad) north to 81.1, B (west pad) to 81.6; both cross under port 1's columns on In2 to the two
        # columns west of the chip (A outer at 43.5, B inner at 44.0: A's run passes over B's column's start,
        # B's run ends before A's column), then south on the front and 45 degrees into their rows
        # the vias a pitch outward of their pads' columns, in the gaps between the back-side bias parts (R2321
        # stands under these two pins; build 28's first run drilled it): A's east of it, B's west
        xa, xb = pa[0] + 0.5, pb[0] - 0.5
        HAND.append(("F.Cu", ioa, [(pa[0], y_e), (pa[0], 81.6), (xa, 81.1)], w)); HAND.append(("via", ioa, xa, 81.1, 0.3, 0.15))
        HAND.append(("In2.Cu", ioa, [(xa, 81.1), (43.5, 81.1)], w)); HAND.append(("via", ioa, 43.5, 81.1, 0.3, 0.15))
        HAND.append(("F.Cu", ioa, [(43.5, 81.1), (43.5, rA[1] - 2.0), (41.5, rA[1]), rA], w))
        HAND.append(("F.Cu", iob, [(pb[0], y_e), (pb[0], 82.1), (xb, 81.6)], w)); HAND.append(("via", iob, xb, 81.6, 0.3, 0.15))
        HAND.append(("In2.Cu", iob, [(xb, 81.6), (44.0, 81.6)], w)); HAND.append(("via", iob, 44.0, 81.6, 0.3, 0.15))
        HAND.append(("F.Cu", iob, [(44.0, 81.6), (44.0, rB[1] - 2.0), (42.0, rB[1]), rB], w))
        put_facing(pl, R(1), 40.5, y_s - 4.4, ioa, "S")             # 24.9 R load above the in+ run's tail
        put_facing(pl, R(2), 38.0, y_s + 0.5, iob, "N")             # 24.9 R load below the in- run's tail
        HAND.append(("F.Cu", ioa, [pad_of(pl, R(1), ioa), (40.5, rA[1])], w))
        HAND.append(("F.Cu", iob, [pad_of(pl, R(2), iob), (38.0, rB[1])], w))


def adc_control_lines(pl):
    """ADC_DCS and ADC_PDWN_A, from the AD9238's pins 19 and 60 to the FPGA's south-face exits (T6, R7), laid by hand
    on the routes build 27's fine grid found: into the chip's body on the front, down to the back, south along the
    DAC strips' east edge, round the DAC's south side and up the FPGA's west flank to the exits.  The fine grid found
    them once (build 27) and never again (five build-28 runs); the balls are bank 8's and the plan is fixed."""
    dcs, pdwn = net_of(pl, "U103", 19), net_of(pl, "U103", 60)
    w = 0.127
    HAND.append(("F.Cu", dcs, [pad_of(pl, "U103", num="19"), (47.8, 57.6)], w))
    HAND.append(("via", dcs, 47.8, 57.6, 0.3, 0.15))
    HAND.append(("B.Cu", dcs, [(47.8, 57.6), (47.8, 58.2), (45.4, 60.6), (45.4, 83.4), (52.4, 90.4), (52.4, 91.6), (54.0, 93.2)], w))
    HAND.append(("via", dcs, 54.0, 93.2, 0.3, 0.15))
    HAND.append(("F.Cu", dcs, [(54.0, 93.2), (68.0, 93.2), (70.0, 91.2), (70.0, 66.0)], w))
    HAND.append(("F.Cu", pdwn, [pad_of(pl, "U103", num="60"), (48.6, 52.2), (47.0, 53.8)], w))
    HAND.append(("via", pdwn, 47.0, 53.8, 0.3, 0.15))
    HAND.append(("B.Cu", pdwn, [(47.0, 53.8), (46.4, 54.4), (46.4, 57.0), (45.8, 57.6), (44.8, 57.6), (44.8, 58.8), (45.0, 59.0), (45.0, 85.0),
                                (46.4, 86.4), (46.4, 91.4), (48.2, 93.2), (53.2, 93.2), (53.6, 93.6)], w))
    HAND.append(("via", pdwn, 53.6, 93.6, 0.3, 0.15))
    HAND.append(("F.Cu", pdwn, [(53.6, 93.6), (60.8, 93.6), (61.2, 94.0), (69.0, 94.0), (71.2, 91.8), (71.2, 75.6), (70.4, 74.8), (70.4, 66.0)], w))


def dac_common(pl):
    """The AD9767's own parts (rot 0).  North row (pins 37-48, east to west: SLEEP, ACOM, IOUTA2, IOUTB2,
    FSADJ2, GAINCTRL, REFIO, FSADJ1, IOUTB1, IOUTA1, AVDD, MODE): the output pairs leave on the front;
    SLEEP, FSADJ2, REFIO, FSADJ1, AVDD and MODE reach their parts on the back through 0.3 mm vias at the
    pads' north ends, 0.6 mm out for the pins beside an output pair and 1.4 mm out for the pins beside
    those, so no two vias stand side by side.  The parts stand in a near row (via in the pad, or a short
    diagonal) and a far row (FSADJ1 straight north between two near-row parts, the 10 u AVDD capacitor).
    South row: the four write/clock lines' 33 R stand in two rows on the front (the river's lanes start
    at their far pads); the DVDD capacitors on the back, off the data vias' columns.  East row: the
    river.  West row: the river's vias."""
    ax, ay = ANCHORS["U201"][0], ANCHORS["U201"][1]
    front = [("R2101", 48.0, 98.5), ("R2201", 52.8, 98.5), ("R2102", 49.6, 100.1), ("R2202", 51.2, 100.1)]    # WRT1 (pin 17), WRT2 (20), CLK1 (18), CLK2 (19)
    for ref, x, y in front:
        put_facing(pl, ref, x, y, net_of(pl, ref, 2), "N")          # pad 2 (the DAC side) up
    y_near, y_far = ay - 7.1, ay - 10.25                           # the two back rows' centres
    # (part, pin, via depth, part x, far row?)
    north = [("R2301", "48", 1.4, 47.0, False), ("C2342", "47", 0.6, 48.5, False), ("R2311", "44", 0.6, 49.25, True),
             ("C2331", "43", 1.4, 50.0, False), ("R2321", "41", 0.6, 51.5, False), ("R2302", "37", 0.6, 53.0, False)]
    for ref, pin, depth, x, far in north:
        p = pad_of(pl, "U201", num=pin)
        n = net_of(pl, "U201", pin)
        y_end = p[1] - 0.75                                        # the pad's north end
        vy = y_end - depth
        put_facing(pl, ref, x, y_far if far else y_near, n, "S", "B.Cu")
        q = pad_of(pl, ref, n)                                     # the part's chip-side pad (on the back)
        HAND.append(("F.Cu", n, [(p[0], p[1]), (p[0], vy)], 0.2))   # from the pad's centre along it to the via
        HAND.append(("via", n, p[0], vy, 0.3, 0.15))
        if abs(q[0] - p[0]) > 0.05 or abs(q[1] - vy) > 0.3:
            HAND.append(("B.Cu", n, [(p[0], vy), (q[0], q[1] + 0.3 if far else q[1])], 0.2))
    put(pl, "C2341", 47.0, y_far, 90, "B.Cu")                      # AVDD 10 u beside FSADJ1 in the far row
    # C2342's ground pad gets its via by hand: a stub on the back west to x 48.25 (under DAC 1's A column on the
    # front, between the two hop vias at y 79.9) and north to a via at (48.25, 78.4), clear of R2311 (x 48.85), C2341
    # (x 47.55), the hop vias and A's diagonal.  Every nearer spot was taken: the stitcher's, north of the pad, by the
    # hop vias; west of the pad, port 2's In2 run (the 7th run's short); between the A and B columns (the 8th run's)
    q = pad_of(pl, "C2342", "GND")
    HAND.append(("via", "GND", 48.25, 78.4, 0.45, 0.25)); HAND.append(("B.Cu", "GND", [q, (48.25, q[1]), (48.25, 78.4)], 0.2))
    HAND.append(("B.Cu", "GND", [pad_of(pl, "C2341", "GND"), (48.25, 78.4)], 0.2))   # C2341's ground pad shares it (the stitcher left that pad alone once the via was near: the 9th run)
    for pin in ("38", "42"):                                       # ACOM and GAINCTRL (ground): a via half in the pad, under the body's edge
        p = pad_of(pl, "U201", num=pin)
        HAND.append(("F.Cu", "GND", [(p[0], p[1]), (p[0], p[1] + 0.7)], 0.2)); HAND.append(("via", "GND", p[0], p[1] + 0.7, 0.3, 0.15))
    back = [("C2352", ax - 3.0, ay + 8.0, 0), ("C2353", ax + 5.0, ay + 4.0, 0), ("C2351", ax + 5.8, ay + 9.5, 0)]   # DVDD (16, 22): 100 n each, 10 u -- off the back lanes (y 94-96.4, x 47-70) and their bend (x 57-58.5)
    for ref, x, y, rot in back:
        put(pl, ref, x, y, rot, "B.Cu")


# --- clocks, LEDs, buttons: the top-left ----------------------------------------------------------------
def clocks(pl):
    """CLK IN: SMA -> 49.9 R + TERM above the line -> 10 nF in line -> unbuffered inverter (1 M feedback
    below it) -> Schmitt buffer -> 33 R -> CLK_EXT.  CLK OUT: the buffer facing the SMA, 49.9 R in line.
    The Si5351 and the TCXO sit north of the SDRAM, at the mouth of the clock corridors the SDRAM river
    leaves for bank 0's inner-layer PCLK balls; the crystal at the Si5351's XA/XB pins, its I2C pull-ups
    beside it, a 33 R on each clock output."""
    # CLK IN at y 12
    y = SMA_Y["J301"]
    n0 = pl.nets["J301"]["1"]
    put_facing(pl, "R5421", 10.5, y - 1.4, n0, "W")
    put_facing(pl, "JP3001", 11.27, y - 5.0, net_of(pl, "JP3001", 1), "W")
    put_facing(pl, "C5421", 12.8, y, n0, "W")
    # the TLV3501 (build 26) at rot 180: +IN (3) north-west on the line's row, -IN (1) north-east, V- (2) north
    # centre; V+ (4) south-west, OUT (5) south centre, SHDN (6) south-east.  Its 10 k to +IN west of it, the
    # mid-rail divider and its 100 nF north-east, the supply 100 nF south-west, the 33 R on the OUT row
    put(pl, "U302", 17.6, y + 0.5, 180)
    put_facing(pl, "R5426", 13.9, y - 1.6, net_of(pl, "U302", 3), "E")      # 10 k lying between the TERM jumper and the 10 nF: +IN pad east toward pin 3
    put_facing(pl, "R5424", 20.6, y - 3.2, "+3V3_ADC", "N")                   # 10 k from +3V3_ADC (pad north) to the mid-rail
    put_facing(pl, "R5425", 22.3, y - 3.2, "GND", "N")                        # 10 k from the mid-rail to ground
    put_facing(pl, "C5424", 24.0, y - 3.2, "GND", "N")                        # the mid-rail's 100 nF
    put_facing(pl, "C5422", 15.4, y + 3.6, "+3V3_ADC", "E")                   # the supply 100 nF at V+ (pin 4, south-west)
    put_facing(pl, "R5423", 21.6, y + 2.4, net_of(pl, "U302", 5), "W")        # 33 R on the OUT row -> CLK_EXT
    # CLK OUT at y 29: the buffer faces the SMA
    SECTION[0] = "CLK OUT"
    y = SMA_Y["J302"]
    put_facing(pl, "R5431", 10.5, y, pl.nets["J302"]["1"], "W")
    put(pl, "U304", 14.5, y + 0.95, 180)                               # out (pin 4) west top on the line, in (pin 2) east
    put_facing(pl, "C5431", 13.36, y + 4.3, "+3V3", "N")
    # the Si5351 and the TCXO north of the SDRAM, in front of the clock corridors
    SECTION[0] = "CLOCK GEN"
    xs, ys = 65.5, 14.0
    put(pl, "U301", xs, ys, 0)                                        # XA/XB/SCL/SDA west, clocks east
    put(pl, "Y301", xs - 4.5, ys - 4.4, 90)                           # pad 1 (SE) under XA's reach, pad 3 (NW) round the west
    put_facing(pl, "C5411", xs - 4.8, ys - 1.0, "+3V3", "E")          # 100 nF at pin 1
    put_facing(pl, "R5411", xs + 4.9, ys - 1.9, net_of(pl, "U301", 10), "W")   # CLK0 -> 33 R
    put_facing(pl, "R5412", xs + 8.0, ys + 0.0, net_of(pl, "U301", 9), "W")    # CLK1, further out
    put_facing(pl, "R5413", xs + 4.9, ys + 1.9, net_of(pl, "U301", 6), "W")    # CLK2
    put_facing(pl, "R5416", xs - 5.0, ys + 1.5, "+3V3", "W")          # I2C pull-ups west of SCL/SDA
    put_facing(pl, "R5417", xs - 5.0, ys + 3.1, "+3V3", "W")
    put(pl, "X301", xs + 12.0, ys + 0.5, 0)                           # TCXO: OUT (pin 3) south-east, VCC north-east
    put_facing(pl, "C5401", xs + 16.0, ys - 1.5, "+3V3", "W")         # its 100 nF at pin 4
    put_facing(pl, "R5401", xs + 16.5, ys + 2.5, net_of(pl, "X301", 3), "W")   # 33 R on OUT -> CLK_TCXO


def leds_buttons(pl):
    """Eight white user LEDs in a row at the top edge (cathode out, resistor under each), the two
    buttons beside them with their pull-ups."""
    for i in range(8):
        d, r = "D30%d" % (i + 1), "R544%d" % (i + 1)
        x = 31.5 + 3.6 * i
        put_facing(pl, d, x, 9.0, "GND", "N")                          # anode down toward its resistor; D30n beside it, LEDn between it and its resistor (build 28: the box's name has the top row)
        put_facing(pl, r, x, 14.0, net_of(pl, d, 2), "N")
    SECTION[0] = "BUTTONS"                                             # RESET and USER between the CLK IN and CLK OUT chains
    put(pl, "SW301", 23.0, 24.6, 0); put_facing(pl, "R5451", 28.5, 24.6, "+3V3", "N")
    put(pl, "SW302", 23.0, 33.0, 0); put_facing(pl, "R5452", 28.5, 33.0, "+3V3", "N")


# --- the noise source and the photodiode receiver: the bottom-left --------------------------------------
def noise_pd(pl):
    """The Johnson-noise block (four resistors into a DIP switch, the NOISE header) and the photodiode
    receiver (transimpedance OPA2810 half, the diode at its in- pin, the PD EXT header beside the diode)
    in the band under the DAC 1 strip."""
    # the DIP switch, pins along x; the four resistors standing above its top row, the header west of it
    put(pl, "SW101", 15.0, 110.2, 0)                                   # pins 1-4 at y 106.4 (x 11.2-18.8), 5-8 at 114.0 (0.7 lower since build 28: the resistors' values over the resistors)
    for i, r in enumerate(("R1401", "R1402", "R1403", "R1404")):
        put_facing(pl, r, 11.19 + 2.54 * i, 103.45, net_of(pl, "SW101", i + 1), "S")      # (0.5 lower since build 28: their values stand over them under the box's raised corner)
    put_facing(pl, "J105", 22.6, 103.9, "GND", "N")                   # NOISE header: GND pin up, R pin below (clear of the DAC 1 strip)
    # the TIA: op amp with pins 1-3 west; the diode west of its in- pin, cathode toward the pin
    xo, yo = 40.0, 108.5
    put(pl, "U105", xo, yo, 0)
    put_facing(pl, "D103", xo - 8.5, yo - 0.64, net_of(pl, "D103", 1), "E")      # pad 1 = cathode (summing node)
    put_facing(pl, "J106", xo - 15.8, yo + 1.5, net_of(pl, "J106", 1), "N")      # PD EXT: the -4.2 V (anode) pin up, K below; its name under it, "A"/"K" east of its pins (build 28)
    put_facing(pl, "R1405", xo - 1.0, yo - 4.0, net_of(pl, "U105", 2), "W")     # 10 k feedback above the chip: in- west, out east
    put_facing(pl, "C1401", xo + 2.3, yo - 4.0, net_of(pl, "U105", 2), "W")     # 2.2 pF east of it on the same row (build 28: above it, it took the box name's row)
    put_facing(pl, "J109", xo - 7.0, yo + 4.4, net_of(pl, "J109", 1), "S")      # the monitor tap (build 26): the U.FL in the box's bottom row between the PD EXT header's name and the chip (the box's name needs its top edge clear; its outline clear of the photodiode's)
    put_facing(pl, "R1406", xo - 7.0, yo + 4.4, net_of(pl, "U105", 1), "N", "B.Cu")  # its 49.9 R on the back under it
    put_facing(pl, "C1402", xo + 4.8, yo + 1.9, "+5VA", "W")                    # V+ (pin 8) capacitor
    put_facing(pl, "C1403", xo - 2.4, yo + 2.3, "-4V2", "E", "B.Cu")            # V- (pin 4) capacitor: on the back under the pin since build 26 (the tap's U.FL took its place)


# --- analog power: the two LDOs on the back under the strips, the charge pump and the +5VA ferrite ---------
def analog_power(pl):
    """+3V3_ADC and +3V3_DAC LDOs on the back, each under the middle of its converter's strips with its
    input and output capacitors beside it; the -4.4 V charge pump with its five capacitors and divider,
    and the +5VA ferrite, in the free corner south of the DAC."""
    for u, y, cin, cout in (("U604", 55.5, "C8001", "C8002"), ("U605", 89.5, "C8101", "C8102")):
        put(pl, u, 30.0, y, 0, "B.Cu")                                 # on the back (clear of the strips' headers), mirrored: IN/EN east, OUT west
        put_facing(pl, cin, 33.6, y - 0.9, "+5V", "W", "B.Cu")
        put_facing(pl, cout, 26.4, y + 0.9, net_of(pl, u, 5), "E", "B.Cu")
    put(pl, "U603", 86.0, 66.0, 0, "B.Cu")                            # +2V5 LDO on the back, south-east of the FPGA
    put_facing(pl, "C7901", 82.4, 66.0, "+3V3", "W", "B.Cu")
    put_facing(pl, "C7902", 89.6, 66.0, "+2V5", "E", "B.Cu")
    put_facing(pl, "FB5811", 92.8, 66.0, "+2V5", "W", "B.Cu")         # +2V5 -> +2V5_AUX
    put_facing(pl, "FB8201", 60.0, 50.0, "+3V3", "N", "B.Cu")         # +3V3 -> +3V3_DRV, behind the ADC's north-east corner
    put_facing(pl, "C8201", 61.8, 50.0, "+3V3_DRV", "N", "B.Cu")
    put_facing(pl, "FB8211", 59.6, 98.0, "+3V3_DAC_D", "W", "B.Cu")   # +3V3 -> +3V3_DAC_D, behind the DAC's south-east corner, south of its back lanes
    put_facing(pl, "C8211", 63.0, 98.0, "+3V3_DAC_D", "W", "B.Cu")
    SECTION[0] = "-4.2 V"
    xp, yp = 53.5, 105.3
    put(pl, "U606", xp, yp, 0)                                         # +5V/GND/CPOUT/-4V4 west (top to bottom), VFB/+5V/C-/C+ east
    put_facing(pl, "C8302", xp + 2.6, yp - 0.5, net_of(pl, "U606", 8), "N")    # flying 1 u: C+ up at pin 8's row, C- down at pin 7's
    put_facing(pl, "C8301", xp - 3.6, yp - 1.6, "+5V", "E")            # 10 u in, at pin 1
    put_facing(pl, "C8303", xp - 3.6, yp + 0.1, net_of(pl, "U606", 3), "E")    # 10 u on CPOUT (pin 3)
    put_facing(pl, "C8304", xp - 3.6, yp + 1.8, net_of(pl, "U606", 4), "E")   # 10 u out, at pin 4 (the pump's own output, before the bead)
    put_facing(pl, "R8301", xp + 3.6, yp + 2.6, net_of(pl, "U606", 4), "W")   # 1.2 M: pump output west, VFB east
    put_facing(pl, "R8302", xp + 3.6, yp + 4.1, net_of(pl, "U606", 5), "W")    # 499 k: VFB west, ground east
    put_facing(pl, "FB8301", xp - 3.6, yp + 1.8, net_of(pl, "C8304", 1), "E", "B.Cu")   # the bead (build 26) on the back under the pump's output capacitor, pump side east
    put_facing(pl, "C8305", xp - 3.6, yp + 4.0, "-4V2", "E", "B.Cu")                     # the rail's 10 u after it, on the back too
    put_facing(pl, "FB8231", xp - 3.6, yp + 4.5, "+5V", "W")           # +5V -> +5VA, under the pump's west capacitors
    put_facing(pl, "C8231", xp + 0.2, yp + 5.5, "+5VA", "W")


# --- Ethernet: the PHY's passives at its pins, the magnetics' parts on the back ------------------------
def phy(pl):
    """U401 (rot 180): MDI pairs east toward the magnetics, TX north and RX west into the RGMII river's
    resistor columns (pcb/river.py plan_phy, which checks their positions), crystal, straps and RSET
    south.  South row, 0.4 mm pitch, west to east: INTB, LED0, LED1, LED2, (NC), XTAL_IN, XTAL_OUT,
    AVDD10, RSET, AVDD33.  The crystal stands under XTAL_IN/OUT (its pad 3 south-west for XTAL_IN,
    pad 1 north-east for XTAL_OUT), the load capacitors beside those pads; RSET's resistor east of it;
    the four strap/LED nets fan south-west into four columns, each a pull resistor over a 330 R.
    Supply capacitors at the end pins; the 1.0 V switcher's inductor and the capacitors of the west and
    east rows on the back, reached through vias at the pad ends."""
    ax, ay = ANCHORS["U401"][0], ANCHORS["U401"][1]
    # RGMII series resistors: TX column west of the TX pads' corner, RX column west of the RX pads (as plan_phy expects)
    for ref, x, y in (("R4905", 98.5, 17.0), ("R4906", 98.5, 15.5), ("R4904", 98.5, 14.0), ("R4903", 98.5, 12.5), ("R4902", 98.5, 11.0), ("R4901", 98.5, 9.5),
                      ("R4907", 95.0, 18.0), ("R4908", 95.0, 19.5), ("R4909", 95.0, 21.0), ("R4910", 95.0, 22.5), ("R4912", 95.0, 24.0), ("R4911", 95.0, 25.5)):
        put(pl, ref, x, y, 0)
    put_facing(pl, "R4941", 97.6, 21.0, "+3V3_ETH", "E", "B.Cu")       # the TXDLY strap's 4.7 k (build 26): on the back just east of RXD1's series resistor, its RXD1 pad west (the river's layer-change via sits west of the column at x 93.6)
    # crystal and loads.  Pins 36 (XTAL_IN, x 104.2) and 37 (XTAL_OUT, x 104.6) run straight down the gap
    # between the crystal's north-row pads 4 (GND) and 3 (XTAL_OUT): the crystal is centred 0.3 mm east of
    # the PHY so that gap sits under the two pins; XTAL_IN turns west into pad 1 on the south row.  All of
    # it, with the ground vias IN the crystal's two ground pads, is laid by hand (HAND) below.
    put(pl, "Y401", ax + 0.3, ay + 7.0, 0)                             # pads: 4 GND NW (103.2, 30.15), 3 XTAL_OUT NE (105.4, 30.15), 1 XTAL_IN SW (103.2, 31.85), 2 GND SE
    put_facing(pl, "C4976", ax - 0.8, ay + 9.9, "GND", "S")            # XTAL_IN's 18 pF straight under pad 1
    put_facing(pl, "C4977", ax + 4.2, ay + 8.6, "GND", "E")            # XTAL_OUT's 18 pF south-east of pad 3, reached by a 45-degree run
    # the strap / LED / INT columns, 2.2 mm apart (room for a trace between two): pull resistor on top with
    # its signal pad up, 330 R under it.  The pulls' row stands 2.3 mm below the pin ends: the four straps
    # leave their pins as a staircase (0.4 mm apart, the westmost pin turning first) and drop into the pads.
    cols = {31: 94.5 + E, 32: 96.7 + E, 33: 98.9 + E, 34: 101.1 + E}
    pulls = {31: "R4914", 32: "R4962", 33: "R4972", 34: "R4982"}
    series = {32: "R4961", 33: "R4971", 34: "R4981"}
    for pin, x in cols.items():
        net = net_of(pl, "U401", pin)
        put_facing(pl, pulls[pin], x, ay + 6.0, net, "N")
        if pin in series:
            put_facing(pl, series[pin], x, ay + 9.3, net, "N")
    # supplies: 100 nF at the north-row and south-row supply pins on the front, the rest on the back
    put_facing(pl, "C4987", ax + 3.3, ay - 4.4, "+3V3_ETH", "W")       # AVDD33 pin 11 (north row, east end)
    put_facing(pl, "C4995", ax + 1.15, ay + 4.5, "+1V0_PHY", "N", "B.Cu")   # AVDD10 pin 38: back, its two pads on the two vias below
    put(pl, "C4993", ax + 5.3, ay + 6.5, 0, "B.Cu")                    # AVDD10 pins 3/8 (east row): back, south of the MDI fan
    put(pl, "C4994", ax - 3.5, ay - 1.8, 90, "B.Cu")                   # DVDD10 pin 21 (west row, top): back
    put(pl, "C4988", ax - 3.5, ay + 1.0, 90, "B.Cu")                   # AVDD33 / DVDD33 pins 28/29 (west row, bottom): back
    put(pl, "C4989", ax - 5.4, ay - 0.6, 90, "B.Cu")                   # DVDD_RG (pin 28) spare 100 nF: back, west of the chip
    # REG_OUT (pin 30, the west row's bottom) -> 2.2 uH power inductor -> +1V0_PHY, on the back under the RGMII
    # resistor columns: the 4 x 4 inductor's switch-node pad east toward the pin, its output pad west with the
    # 10 u and 100 n right beside it (builds 1-23: an 0805 chip inductor rated 50 mA, see sheet_eth)
    put_facing(pl, "L401", ax - 8.0, ay + 4.5, net_of(pl, "U401", 30), "E", "B.Cu")
    put_facing(pl, "C4986", ax - 8.0, ay + 0.3, "+3V3_ETH", "E", "B.Cu")      # 10 u on +3V3_ETH, 5.6 mm from DVDD33 (pin 29), beside its 100 nF (C4988)
    put_facing(pl, "C4991", ax - 13.3, ay + 4.5, "+1V0_PHY", "E", "B.Cu")    # 10 u on +1V0_PHY at the inductor's output pad
    put_facing(pl, "C4992", ax - 13.3, ay + 6.3, "+1V0_PHY", "E", "B.Cu")    # a 100 nF with it
    put_facing(pl, "C4990", ax + 5.1, ay + 4.9, "+3V3_ETH", "N")       # AVDD33 pin 40: its 100 nF east of RSET's resistor, below the MDI fan
    put_facing(pl, "R4983", ax + 3.2, ay + 5.0, net_of(pl, "U401", 39), "N")   # RSET 2.49 k: signal pad up, ground pad down (via in it)
    # --- the south-row copper, by hand: the two crystal lines, RSET, AVDD10's via, AVDD33, the straps ---
    w = 0.13
    xin, xout, avdd10, rset, avdd33 = (net_of(pl, "U401", n) for n in (36, 37, 38, 39, 40))
    y_pin = ay + 2.44
    HAND.append(("F.Cu", xin, [(104.2 + E, y_pin), (104.2 + E, 31.85), (103.2 + E, 31.85), (103.2 + E, 33.42)], w))      # pin 36 -> pad 1 -> C4976
    HAND.append(("F.Cu", xout, [(104.6 + E, y_pin), (104.6 + E, 30.15), (105.4 + E, 30.15), (105.85 + E, 30.15), (107.72 + E, 32.02), (107.72 + E, 32.6)], w))   # pin 37 -> pad 3 -> C4977
    HAND.append(("F.Cu", avdd10, [(105.0 + E, y_pin), (105.0 + E, 27.55), (105.15 + E, 27.7), (105.15 + E, 28.0)], 0.2))
    HAND.append(("via", avdd10, 105.15 + E, 28.0, 0.3, 0.15))                                                # into C4995's +1V0 pad on the back
    HAND.append(("via", "GND", 105.15 + E, 29.0, 0.3, 0.15))                                                 # C4995's ground pad
    HAND.append(("F.Cu", rset, [(105.4 + E, y_pin), (105.4 + E, 26.95), (106.63 + E, 28.18), (107.2 + E, 28.18)], w))    # pin 39 -> R4983 (45 degrees, clear of the via)
    HAND.append(("F.Cu", avdd33, [(105.8 + E, y_pin), (105.8 + E, 26.8), (106.35 + E, 27.35), (107.95 + E, 27.35), (108.6 + E, 28.0), (109.1 + E, 28.0), (109.1 + E, 28.42)], 0.2))   # pin 40 -> C4990, over RSET's resistor, under the MDI fan
    for (vx, vy) in ((103.2 + E, 30.15), (105.4 + E, 31.85), (107.2 + E, 29.83), (109.1 + E, 29.38), (103.2 + E, 34.38), (108.68 + E, 32.6)):
        HAND.append(("via", "GND", vx, vy, 0.3, 0.15))                                                   # the crystal's, RSET's, the three capacitors' ground pads
    for pin, y_turn in ((31, 27.0), (32, 27.4), (33, 27.8), (34, 28.2)):
        xp = ax + (pin - 35.5) * 0.4
        HAND.append(("F.Cu", net_of(pl, "U401", pin), [(xp, y_pin), (xp, y_turn), (cols[pin], y_turn), (cols[pin], ay + 6.0 - 0.82)], w))
    # DVDD10 (pin 21, the west row's top pin): its 100 nF is on the back under it (C4994), and the via between
    # them goes in the corner between the north and west rows by hand -- build 22's TXC and RXD3 routes left no
    # via spot on the pin's lane and the 1.0 V net was the one left unrouted.  A 0.3 mm via 0.6 mm from the pad
    # clears pin 20's pad by 0.57 mm and pin 22's by 0.6
    p21 = pl.padpos[("U401", "21")]
    HAND.append(("F.Cu", "+1V0_PHY", [p21, (ax - 2.65, ay - 2.3)], 0.13))
    HAND.append(("via", "+1V0_PHY", ax - 2.65, ay - 2.3, 0.3, 0.15))
    # reset: 330 R from the FPGA, 4.7 k up, 1 u to ground, north-east of the PHY beside PHYRSTB (pin 12)
    put_facing(pl, "R4916", ax + 6.0, ay - 6.5, "+3V3_ETH", "E")
    put_facing(pl, "C4901", ax + 6.0, ay - 8.0, "GND", "E")
    put_facing(pl, "R4915", ax + 6.0, ay - 9.5, net_of(pl, "U401", 12), "W")
    # PHYRSTB (pin 12, the north row's second pin) by hand: north past AVDD33's capacitor, then east into the
    # pull-up's pad; the three reset parts' west pads are joined by one vertical (build 16 could not get out)
    for pin, y_via in ((13, 18.2), (14, 19.2)):
        xp = ax + (pin - 15.5) * 0.4 * -1                               # the north row runs east to west: pin 11 at ax+1.8 ... pin 20 at ax-1.8
        HAND.append(("F.Cu", net_of(pl, "U401", pin), [(xp, ay - 2.44), (xp, y_via)], 0.13))
        HAND.append(("via", net_of(pl, "U401", pin), xp, y_via, 0.3, 0.15))
    rstb = net_of(pl, "U401", 12)
    HAND.append(("F.Cu", rstb, [(105.4 + E, ay - 2.44), (105.4 + E, 18.6), (106.5 + E, 17.5), (109.17 + E, 17.5)], 0.13))
    HAND.append(("F.Cu", rstb, [(109.17 + E, 17.5), (109.17 + E, 14.5)], 0.2))
    # the link LEDs by the jack, in a row above it (anode toward their resistors' side is irrelevant: the router)
    for i, d in enumerate(("D401", "D402", "D403")):
        put(pl, d, 118.0 + E + 4.0 * i, 8.0, 0)
    # magnetics (back): the four chip-side centre-tap 100 nF west of its chip-side row, the Bob Smith
    # network east of its line-side row
    tx, ty = ANCHORS["T401"][0], ANCHORS["T401"][1]
    for i, c in enumerate(("C4911", "C4921", "C4931", "C4941")):
        put_facing(pl, c, tx - 7.2, ty + 5.5 - 3.0 * i, "GND", "W", "B.Cu")      # TCT1 (y 24.5) ... TCT4 (y 15.5)
    # the Bob Smith network inside the isolation island (x > 127.3: no plane there), on the back above the jack's
    # courtyard: the four 75 R in a row, tap pads west toward the magnetics' line-side taps, their common node
    # east; the 1 nF 2 kV from that node westward to ground just outside the island
    # four 75 R standing in a row above the jack, tap pads south, the farthest tap's resistor westmost so the
    # four tap lines (columns 0.3 mm apart west of the magnetics' pads, the outermost tap in the outermost
    # column, turning east lowest) never cross; their common node runs along the top into the 2 kV capacitor's
    # hot pad, whose ground pad stands outside the island.  All laid by hand (the router does not know the
    # island rule).
    rs = ("R4951", "R4952", "R4953", "R4954")
    order = sorted(rs, key=lambda r: -pad_of(pl, "T401", net_of(pl, r, 1))[1])     # the lowest tap first: outermost column, westmost resistor
    put_facing(pl, "C4951", 128.4 + E, 5.3, "GND", "W", "B.Cu")      # 1812 (build 26): ground pad over the planes, hot pad inside the island, its body 3.7 mm from the edge
    cmt = net_of(pl, "C4951", 1)
    HAND.append(("B.Cu", cmt, [pad_of(pl, "C4951", cmt), (138.4 + E, 5.3)], 0.25))
    for k, r in enumerate(order):
        x, y_turn, x_col = 133.3 + E + 1.7 * k, 8.4 + 0.4 * k, 130.0 + E + 0.4 * k     # columns 2.6+ mm inside the island's edge (tx - 0.7), 0.3 mm off the pads' west ends (131.6); the row 0.8 east of the 1812
        put_facing(pl, r, x, 7.0, net_of(pl, r, 1), "S", "B.Cu")
        tap = net_of(pl, r, 1); tp = pad_of(pl, "T401", tap)
        HAND.append(("B.Cu", tap, [tp, (x_col, tp[1]), (x_col, y_turn), (x, y_turn), (x, 7.8)], 0.2))
        HAND.append(("B.Cu", cmt, [(x, 5.3), (x, 6.2)], 0.25))
    # the jack's shield pads (13 north, 14 south): no plane reaches them inside the island, so a track on the back
    # takes the north one into the corner hole's ring and the south one to a via just outside the island
    HAND.append(("B.Cu", "GND", [(141.9 + E, 10.9), (141.9 + E, 8.4), (144.4 + E, 5.9)], 0.3))      # into the corner hole's ring
    HAND.append(("B.Cu", "GND", [(141.9 + E, 27.1), (141.9 + E, 30.0)], 0.3))
    HAND.append(("via", "GND", 141.9 + E, 30.0, 0.45, 0.25))


def usbc_stubs(pl, ref):
    """The receptacle's duplicated pads, joined by hand: D+ (A6, B6) through a U west of the pad column
    between the D- pads' ends, D- (A7, B7) through a U east of the column under the housing, VBUS (the
    two twin pads) through a U east of the column too.  D- then leaves the lower D- pad west, D+ the
    lower leg of its U: a pair 0.5 mm apart heading for the ESD array."""
    pad = lambda num: pad_of(pl, ref, num=num)
    x_w, x_e = pad("A6")[0] - 0.95, pad("A6")[0] + 1.1          # the Us' legs: 0.95 mm west / 1.1 mm east of the pad centres
    w = 0.2
    dp, dm, vb = net_of(pl, ref, "A6"), net_of(pl, ref, "A7"), net_of(pl, ref, "A4")
    b6, a6, a7, b7 = pad("B6"), pad("A6"), pad("A7"), pad("B7")
    HAND.append(("F.Cu", dp, [(b6[0] - 0.4, b6[1]), (x_w, b6[1]), (x_w, a6[1]), (a6[0] - 0.4, a6[1])], w))
    HAND.append(("F.Cu", dm, [(a7[0] + 0.4, a7[1]), (x_e, a7[1]), (x_e, b7[1]), (b7[0] + 0.4, b7[1])], w))
    # (VBUS's twin pads are left to the router: a U east of the column ran over the housing's locating pegs)


# --- the FTDI, the two USB-C ports, the HDMI jack's slow side -------------------------------------------
def ftdi_usb(pl):
    """U502 (rot 180): USB D+/D- on the east side facing the PROG port, UART on the west side facing the
    FPGA, JTAG at the north-east corner, EEPROM pins on the south row.  Crystal at OSCI/OSCO (east side,
    bottom), its loads beside it; REF resistor at pin 6; the EEPROM under the south row.
    Each USB-C: the two CC resistors in line with their pads (ground pads west), the ESD array right
    behind the D pads with its connector pins east, VBUS passing round the resistor pair."""
    fx, fy = ANCHORS["U502"][0], ANCHORS["U502"][1]
    put(pl, "Y501", fx + 8.8, fy + 5.0, 0)                             # pads 1 (OSCI, SW) and 3 (OSCO, NE) toward pins 2/3
    put_facing(pl, "C6211", fx + 7.6, fy + 7.4, "GND", "W")            # OSCI 27 pF
    put_facing(pl, "C6216", fx + 12.0, fy + 4.3, "GND", "E")           # OSCO 27 pF
    put_facing(pl, "R6221", fx + 8.3, fy + 1.6, net_of(pl, "U502", 6), "W")   # 12 k REF at pin 6
    put_facing(pl, "R6222", fx + 8.3, fy - 2.75, "+3V3", "E")          # RESET pull-up at pin 14
    put_facing(pl, "JP501", fx + 12.5, fy - 3.0, net_of(pl, "JP501", 1), "W")   # FTDI OFF (build 28): a shunt grounds RESET#; lying east of the pull-up, its RESET# pin west
    put_facing(pl, "C6241", fx + 8.3, fy - 1.4, "GND", "E")
    put_facing(pl, "FB6241", fx + 8.3, fy + 0.0, "+1V8_FTDI", "E")     # 1.8 V -> VPHY/VPLL ferrite at pins 4/9
    put(pl, "U503", fx + 3.7, fy + 9.2, 0)                             # EEPROM under pins 61-63
    put_facing(pl, "R6231", fx + 7.3, fy + 9.2, "+3V3", "E")           # EEDATA pull-up
    put_facing(pl, "R6232", fx - 0.1, fy + 9.6, net_of(pl, "U503", 1), "W")   # 2.2 k DO link
    # 1.8 V: 4.7 u at pin 49 (south row), 100 n at pins 12 (east), 37 (west, on the back), 64 (south, on the back)
    put_facing(pl, "C6251", fx - 5.0, fy + 8.8, "+1V8_FTDI", "N")
    put_facing(pl, "C6252", fx + 8.3, fy - 4.7, "+1V8_FTDI", "W")
    put(pl, "C6254", fx - 8.5, fy - 1.75, 90, "B.Cu"); put(pl, "C6253", fx + 4.5, fy + 7.3, 0, "B.Cu")
    # 3.3 V: at pins 20 and 31 (north row), 42 (west, back), 50/56 (south)
    for ref, x, y, lay in (("C6262", fx + 2.25, fy - 7.9, "F.Cu"), ("C6264", fx - 3.25, fy - 7.9, "F.Cu"), ("C6263", fx - 2.8, fy + 8.8, "F.Cu"),
                           ("C6261", fx - 8.5, fy + 1.3, "B.Cu"), ("C6265", fx - 0.3, fy + 7.3, "B.Cu")):
        if ref in pl.fp:
            put_facing(pl, ref, x, y, "+3V3", "S" if y < fy else "N", lay)
    # JTAG series resistors standing in a row at the north-east corner, UART ones lying in a column off the west side
    for i, r in enumerate(("R6271", "R6272", "R6273", "R6274")):
        put_facing(pl, r, fx + 8.2 + 1.6 * i, fy - 7.5, net_of(pl, r, 1), "S")
    for i, r in enumerate(("R6281", "R6282", "R6283", "R6284")):
        put_facing(pl, r, fx - 9.5, fy - 2.4 + 1.6 * i, net_of(pl, r, 1), "E")
    # USB PROG (J501 at y 36): CC2 pad at 34.25, CC1 at 37.25, D+ 35.25/36.25, D- 35.75/36.75, VBUS 33.6/38.4
    jx, jy = ANCHORS["J501"][0], ANCHORS["J501"][1]
    xp = jx - 3.68                                                     # the pad column (x 141.82)
    usbc_stubs(pl, "J501")
    # (everything 3.5 mm west of where build 15 had it: the strip x 136.5-140.5 beside each jack holds its name, standing)
    put_facing(pl, "R6202", 131.0 + E, jy - 1.2, net_of(pl, "J501", "B5"), "E")   # CC2 (pad row y-1.75): 5.1 k, ground pad west
    put_facing(pl, "R6201", 131.0 + E, jy + 2.9, net_of(pl, "J501", "A5"), "E")   # CC1 (pad row y+1.25)
    put(pl, "U501", 134.6 + E, jy, 180)                                    # behind the D pads: pins 1-3 (D-, GND, D+) east
    put_facing(pl, "F601", 129.5 + E, jy - 3.9, "/Power/VBUS", "E")        # the 2 A fuse above the CC2 resistor, VBUS pad east
    put_facing(pl, "C7603", 123.8 + E, jy - 3.5, "+5V", "E")               # 100 nF on the fused 5 V
    # USB USER (J502 at y 48): the FPGA's own port
    jx, jy = ANCHORS["J502"][0], ANCHORS["J502"][1]
    usbc_stubs(pl, "J502")
    put_facing(pl, "R6302", 131.0 + E, jy - 2.4, net_of(pl, "J502", "B5"), "E")
    put_facing(pl, "R6301", 131.0 + E, jy + 4.0, net_of(pl, "J502", "A5"), "E")
    put(pl, "U504", 134.6 + E, jy, 180)
    put_facing(pl, "R6303", 134.8 + E, jy + 3.6, net_of(pl, "J502", "A4"), "E")   # 100 k VBUS to ground under the ESD array
    put_facing(pl, "R6311", 130.0 + E, jy - 0.4, net_of(pl, "U504", 4), "E")      # 27 R on D- (ESD pin 4), between the CC resistors
    put_facing(pl, "R6321", 130.0 + E, jy + 1.4, net_of(pl, "U504", 6), "E")      # 27 R on D+ (ESD pin 6)
    put(pl, "R6312", 130.0 + E, jy - 0.4, 0, "B.Cu"); put(pl, "R6322", 130.0 + E, jy + 1.4, 0, "B.Cu")   # 15 k pull-downs on the back under them
    put_facing(pl, "D501", 129.7 + E, jy + 7.7, net_of(pl, "D501", 1), "E")      # 1N4148: cathode to D+, below the FTDI's crystal
    put_facing(pl, "R6313", 125.5 + E, jy + 7.7, net_of(pl, "D501", 2), "E")     # 1 k from USB_PULLUP
    # the HDMI jack's slow pins (south end of its column): DDC level shifter facing the jack, its parts beside it
    SECTION[0] = "HDMI"
    hx, hy = ANCHORS["J503"][0], ANCHORS["J503"][1]
    put(pl, "U505", hx - 8.0, hy + 3.3, 0)                             # SCL2/SDA2 (pins 6/5) east toward pads 15/16
    put_facing(pl, "R6421", hx - 6.0, hy + 6.5, "+5V", "N")            # 4.7 k to +5 V on the jack side, standing
    put_facing(pl, "R6422", hx - 7.6, hy + 6.5, "+5V", "N")
    put_facing(pl, "R6441", hx - 9.4, hy + 6.5, "+5V", "N")            # 200 k EN/VREF2
    put(pl, "F501", hx - 2.2, hy, 0, "B.Cu")                           # 0.5 A polyfuse to the jack's +5 V: on the back under the jack (the jack stands past the edge since build 26)
    put_facing(pl, "R6431", hx - 12.5, hy + 1.3, "+3V3", "W")          # 3.3 k pull-ups on the FPGA side, a column
    put_facing(pl, "R6432", hx - 12.5, hy + 2.8, "+3V3", "W")
    put_facing(pl, "R6411", hx - 12.5, hy + 4.3, net_of(pl, "J503", 14), "E")   # 470 R CEC
    put_facing(pl, "R6412", hx - 12.5, hy + 5.8, net_of(pl, "J503", 19), "E")   # 470 R HPD
    put_facing(pl, "R6413", hx - 12.5, hy + 7.35, "GND", "W")          # 10 k HPD pull-down
    for jnum, unum in (("15", "6"), ("16", "5")):
        jp_ = pad_of(pl, "J503", num=jnum); up_ = pad_of(pl, "U505", num=unum)
        net = net_of(pl, "J503", int(jnum))
        d_ = up_[1] - jp_[1]                                            # the drop (1.55 and 1.65 mm) is taken at 45 degrees
        HAND.append(("F.Cu", net, [jp_, (jp_[0] - 1.0, jp_[1]), (jp_[0] - 1.0 - d_, up_[1]), (up_[0] + 0.6, up_[1])], 0.13))


# --- the Pmods' series resistors, the RGB LED, the microSD's parts --------------------------------------
def pmods_sd(pl):
    """Each socket's eight series resistors stand in two columns west of its pins, in line with them:
    the inboard row's four straight west (x 134.1), the outboard row's four at the half-pitch rows
    (x 131.0) where their traces come through between the inboard pins.  The FPGA-side pads of all
    sixteen (x 133.28 and 130.18) are where the Pmod river (pcb/river.py plan_pmod) starts.  The RGB LED
    below Pmod A; the microSD's pull-ups and capacitors on the back beside its contacts."""
    for jref, rs in (("J304", ["R5611", "R5612", "R5613", "R5614", "R5615", "R5616", "R5617", "R5618"]),
                     ("J303", ["R5601", "R5602", "R5603", "R5604", "R5605", "R5606", "R5607", "R5608"])):
        x0, y0 = ANCHORS[jref][0], ANCHORS[jref][1]
        for i in range(4):
            y = y0 - 2.54 * i                                          # pads 1/3/5/7 (inboard row, x0) and 2/4/6/8 (x0 + 2.54)
            put_facing(pl, rs[i], x0 - 3.3, y, net_of(pl, jref, 2 * i + 1), "E")
            put_facing(pl, rs[4 + i], x0 - 6.4, y - 1.27, net_of(pl, jref, 2 * i + 2), "E")
    SECTION[0] = "RGB LED"
    put(pl, "D309", 126.5 + E, 112.0, 0)                                   # RGB LED west of Pmod A's socket, its three resistors in a column beside it
    for r, x, y in (("R5461", 121.4 + E, 110.7), ("R5462", 121.4 + E, 112.2), ("R5463", 121.4 + E, 113.7)):
        put_facing(pl, r, x, y, net_of(pl, r, 2), "E")
    SECTION[0] = "PMODS"
    sx, sy = ANCHORS["J504"][0], ANCHORS["J504"][1]
    for i, r in enumerate(("R6501", "R6502", "R6503", "R6504", "R6505")):
        put_facing(pl, r, sx - 8.5, sy - 5.5 + 2.0 * i, "+3V3", "W", "B.Cu")   # lying in a column beside the contacts
    for ref, x, y in (("C6511", sx - 4.0, sy + 10.3), ("C6512", sx - 7.5, sy + 10.3)):
        if ref in pl.fp:
            put_facing(pl, ref, x, y, "+3V3", "E", "B.Cu")


# --- power: the bucks, the 5 V input, the rails header, the power-good LEDs --------------------------------
def power(pl):
    """Both bucks the same way round (EN/GND/SW west, VIN/FB east): inductor west of SW, the two output
    capacitors standing at the inductor's far pad, the feedback divider on the row above, the input
    capacitor at VIN.  1.1 V nearest the FPGA, 3.3 V east of it.  Then the bench input (Schottky over
    its header), the bulk capacitors, the RAILS header along the bottom, the power-good LEDs in a row
    with their resistors under them."""
    for u, x, l, cos, (rt, rb), ci, vout in (("U602", 84.0, "L618", ("C7802", "C7803"), ("R7801", "R7802"), "C7801", "+1V1"),
                                           ("U601", 102.0, "L617", ("C7702", "C7703"), ("R7701", "R7702"), "C7701", "+3V3")):
        y = 100.0
        put(pl, u, x, y, 0)
        put_facing(pl, l, x - 6.0, y + 0.65, net_of(pl, u, 3), "E")          # the 4 x 4 inductor west, SW pad east
        put_facing(pl, cos[0], x - 6.0, y - 2.7, vout, "E")                  # output 22 u: one over the inductor
        put_facing(pl, cos[1], x - 10.6, y + 0.65, vout, "N")                # one standing at its far pad (0.3 mm up: the rails' names stand under them)
        put_facing(pl, rt, x - 1.2, y - 2.6, vout, "W")                      # the divider's top beside the chip: Vout west, FB east
        put_facing(pl, rb, x + 3.0, y - 2.6, "GND", "E")                     # bottom: FB west, ground east
        put_facing(pl, ci, x + 3.7, y + 0.95, "+5V", "W")                    # input 10 u at VIN
    put_facing(pl, "D601", 111.8, 101.0, net_of(pl, "D601", 2), "S")         # Schottky: anode down to the header
    put_facing(pl, "F602", 118.5, 98.4, net_of(pl, "D601", 1), "S")          # (build 31) the bench input's 2 A fuse, standing: Schottky side south, +5V pad north (its own via into the +5V plane), between the bulk capacitors and the box's east edge (the Fuse_1812 courtyard is 8.2 x 3.9 mm: lying, it reached the capacitor and the edge)
    put_facing(pl, "J601", 111.8, 108.0, "GND", "S")                         # 5 V IN: +5V pin up, ground pin down
    put_facing(pl, "C7601", 109.7, 96.5, "+5V", "W"); put_facing(pl, "C7602", 113.7, 96.5, "+5V", "W")   # the bulk 22 u lying along the box's top edge (build 28: east of the Schottky they took "5 V IN"'s room)
    put(pl, "J602", 61.0, 110.5, 90)                                         # RAILS (2x9 since build 26: +1V0_PHY): odd pins (the rails) in the bottom row, even (ground) in the top; the names stand over it
    put_facing(pl, "J603", 118.5, 105.9, net_of(pl, "J603", 1), "S")       # the -4V2 monitor tap (build 26): a U.FL at the section's east end, its 49.9 R lying under it
    put_facing(pl, "R8303", 118.5, 110.0, "-4V2", "W")                     # (build 28: 1.2 mm further east; the U.FL's courtyard is 5.6 x 3.9 mm, the cable's room included)
    for i, (d, r) in enumerate((("D602", "R7651"), ("D603", "R7661"), ("D604", "R7671"), ("D605", "R7681"), ("D606", "R7691"), ("D607", "R7703"), ("D608", "R7711"), ("D609", "R7722"))):
        x = 84.1 + 3.0 * i                                                   # (2.1 mm east of builds 1-25: the header is a column longer)
        put_facing(pl, d, x, 107.8, net_of(pl, d, 1), "S")                   # cathode down to its resistor
        put_facing(pl, r, x, 111.1, net_of(pl, d, 1) if d != "D609" else net_of(pl, d, 2), "N")
    put(pl, "Q601", 107.95, 111.1, 0); put_facing(pl, "R7721", 107.95, 114.2, "+1V1", "W")   # (build 28: under Q601, not above it: J601's pin names go on its west, the U.FL's 5.6 mm courtyard fills its east)


# --- flash, configuration, JTAG, the SDRAM's decoupling --------------------------------------------------
def memory(pl):
    fx, fy = ANCHORS["U306"][0], ANCHORS["U306"][1]
    put_facing(pl, "R5703", fx - 6.4, fy - 2.5, "+3V3", "W")                 # CS pull-up (pin 1, west top)
    put_facing(pl, "R5701", fx - 6.4, fy + 0.0, "+3V3", "W")                 # WP (pin 3)
    put_facing(pl, "R5702", fx + 6.4, fy + 0.0, "+3V3", "E")                 # HOLD (pin 7, east)
    put_facing(pl, "C5701", fx + 6.4, fy - 2.5, "+3V3", "W")                 # VCC (pin 8, east top)
    sx, sy = ANCHORS["SW303"][0], ANCHORS["SW303"][1]
    put_facing(pl, "R5711", sx - 2.0, sy - 3.6, "+3V3", "N")                 # PROGRAMN  (J305 sits at y 72.6 above these, its pull-ups east of them)
    put_facing(pl, "C5711", sx - 3.5, sy - 3.6, "GND", "N")                  # its 100 nF (build 26): ground pad north, PROGRAMN pad south
    put_facing(pl, "R5712", sx + 0.0, sy - 3.6, "+3V3", "N")                 # INITN
    put_facing(pl, "R5713", sx + 2.0, sy - 3.6, "+3V3", "N")                 # DONE
    jx, jy = ANCHORS["J305"][0], ANCHORS["J305"][1]
    for i, r in enumerate(("R5724", "R5721", "R5722", "R5723")):             # under pins 2-5: TCK down, TMS/TDI/TDO up
        put_facing(pl, r, jx + 2.54 * (i + 1), jy + 3.6, net_of(pl, "J305", i + 2), "N")
    SECTION[0] = "SDRAM 32 MB"              # the size in the box's name: a label beside the chip has no room inside the box
    mx, my = ANCHORS["U305"][0], ANCHORS["U305"][1]
    for ref, x, y in (("C5502", mx - 8.0, my - 10.2), ("C5503", mx - 8.0, my - 4.2), ("C5501", mx - 8.5, my + 0.1), ("C5504", mx + 8.0, my - 6.6), ("C5505", mx + 8.0, my - 1.8)):
        put_facing(pl, ref, x, y, "+3V3", "E" if x < mx else "W")


# --- the Ethernet lines: PHY -> magnetics -> jack, by hand --------------------------------------------------
def ethernet_lines(pl):
    """The eight MDI lines and the eight LAN lines (floorplan.HAND).

    MDI (PHY pads at x 106.44, 0.4 mm pitch, N above P): a 45-degree fan on the top layer doubles the pitch
    (the outer lines start their diagonals first, so the parallel diagonals stay 0.57 mm apart), then every
    line runs east on its own row to a via: P's at x 109.6, N's at x 111.2, the two AVDDL pins between the
    pairs at 110.4.  On the back each line runs 45 degrees north-east to its transformer row and straight
    into the pad.  N's via stands 1.6 mm east of P's: that is the crossing -- the transformer wants P above N
    (sheet_eth puts P on its "-" ends) and the PHY has N above P.

    LAN (transformer pads on the back at x 132.7, P above N, pair A at the bottom; the jack's pins at x 141.1
    and 142.9, pair A at the top): the pairs' order reverses, so each pair rides its own layer -- A on the
    back straight from the pads, B on In3 and C on In2 through vias 2.8 mm east of the pads, D on the top
    layer around the north of the jack's LED pins.  A's P passes north of pin 2 to reach pin 1 (the
    pads' east column is reached straight through the 0.52 mm gaps of the west column, with 0.2 mm tracks)."""
    # ---- MDI
    def ppad(ref, net):
        return pad_of(pl, ref, net)
    mdi = []                                                     # (net, pad y, fan row, via x)
    for i in range(4):
        n_p, n_n = "/Gigabit Ethernet/ETH_MDI%d_P" % i, "/Gigabit Ethernet/ETH_MDI%d_N" % i
        mdi.append((n_p, ppad("U401", n_p), 109.6 + E)); mdi.append((n_n, ppad("U401", n_n), 111.2 + E))
    for n_a in ("+1V0_PHY",):
        for num in ("3", "8"):
            mdi.append((n_a, pl.padpos[("U401", num)], 110.4 + E))
    yc = 24.0
    for net, (px, py), vx in mdi:
        yf = yc + 2.0 * (py - yc)                                # the fan doubles the pitch about the middle
        rank = int(round(abs(py - yc) / 0.4 + 0.5 + 1e-6))       # 1 (innermost) .. 5 (outermost)
        x0 = 107.2 + E + 0.4 * (5 - rank)                            # outer lines turn first; every diagonal ends at x 109.0
        pts = [(px, py), (x0, py), (x0 + abs(yf - py), yf), (vx, yf)]
        HAND.append(("F.Cu", net, pts, 0.2))
        HAND.append(("via", net, vx, yf, 0.45, 0.25))
        if net.endswith(("_P", "_N")):
            i = int(net[-3]); tp = pad_of(pl, "T401", net)       # the transformer pad on this net
            dy = yf - tp[1]
            HAND.append(("B.Cu", net, [(vx, yf), (vx + dy, tp[1]), tp], 0.25))
    # ---- LAN
    T = lambda n: pad_of(pl, "T401", "/Gigabit Ethernet/ETH_LAN" + n)
    J = lambda n: pad_of(pl, "J401", "/Gigabit Ethernet/ETH_LAN" + n)
    w, wg = 0.25, 0.2
    # pair A (LAN0) on the back: P north of pin 2 into pin 1, N into pin 2
    p, n = T("0_P"), T("0_N"); jp, jn = J("0_P"), J("0_N")
    HAND.append(("B.Cu", "/Gigabit Ethernet/ETH_LAN0_P", [p, (134.4 + E, p[1]), (138.9 + E, p[1] - 4.5), (138.9 + E, jp[1] - 0.13), (jp[0], jp[1] - 0.13)], w))
    HAND.append(("B.Cu", "/Gigabit Ethernet/ETH_LAN0_N", [n, (134.5 + E, n[1]), (jn[0] - 0.06, jn[1] + 0.5)], w))
    # pairs B (In3) and C (In2): a via 2.8 mm east of the pad, then east, a short diagonal, east into the pin
    for k, lay, vx in (("1", "In3.Cu", 135.5 + E), ("2", "In2.Cu", 135.5 + E)):
        for pol, x_turn in (("P", 136.0 + E), ("N", 136.3 + E)):
            net = "/Gigabit Ethernet/ETH_LAN%s_%s" % (k, pol)
            tp, jp = T(k + "_" + pol), J(k + "_" + pol)
            HAND.append(("B.Cu", net, [tp, (vx, tp[1])], w))
            HAND.append(("via", net, vx, tp[1], 0.45, 0.25))
            d = jp[1] - tp[1]
            if abs(d) < 0.1:
                HAND.append((lay, net, [(vx, tp[1]), jp], w))
            else:
                HAND.append((lay, net, [(vx, tp[1]), (x_turn, tp[1]), (x_turn + abs(d), jp[1]), (139.5 + E, jp[1])], w))
                HAND.append((lay, net, [(139.5 + E, jp[1]), jp], wg))
    # pair D (LAN3) on the top layer, round the north of the jack's LED pins.  Its pins are the jack's
    # southmost, its pads the transformer's northmost, and pin 7 (P) stands in the east column: N goes
    # round the inside (west column, pin 8 from the west), P round the outside -- along the top of the
    # jack, down between its east pins and the board edge, and into pin 7 from the east.
    p, n = T("3_P"), T("3_N"); jp, jn = J("3_P"), J("3_N")
    HAND.append(("B.Cu", "/Gigabit Ethernet/ETH_LAN3_P", [p, (134.3 + E, p[1])], w)); HAND.append(("via", "/Gigabit Ethernet/ETH_LAN3_P", 134.3 + E, p[1], 0.45, 0.25))
    HAND.append(("B.Cu", "/Gigabit Ethernet/ETH_LAN3_N", [n, (134.9 + E, n[1])], w)); HAND.append(("via", "/Gigabit Ethernet/ETH_LAN3_N", 134.9 + E, n[1], 0.45, 0.25))
    # (the pair used to go round the jack's north side, between the corner hole's ring and the shield leg's 3.2 mm
    #  pad -- two chassis-potential conductors 1.9 mm apart: no room for the 1.5 mm isolation gap.  Now both lines
    #  run down between the magnetics and the jack on the top layer, where the other pairs ride inner layers, P
    #  entering pin 7 through the west column's 0.5 mm gap on its row, N straight into pin 8.)
    # (the jack's unused LED pins 11/12 stand at (136.3, 14.4) and (136.3, 12.1): P passes between them at y 13.25,
    #  N below pin 11 at y 15.6)
    HAND.append(("F.Cu", "/Gigabit Ethernet/ETH_LAN3_P", [(134.3 + E, p[1]), (134.55 + E, 13.25), (139.4 + E, 13.25), (139.4 + E, jp[1])], w))
    HAND.append(("F.Cu", "/Gigabit Ethernet/ETH_LAN3_P", [(139.4 + E, jp[1]), jp], 0.2))
    HAND.append(("F.Cu", "/Gigabit Ethernet/ETH_LAN3_N", [(134.9 + E, n[1]), (134.9 + E, 15.6), (138.9 + E, 15.6), (138.9 + E, jn[1]), jn], w))
    # the parts that stood in the fan's and the vias' way
    # (R4983 and C4990 now stand where phy() puts them: their copper is laid by hand there)
    # (R4983 and C4990 now stand where phy() puts them: their copper is laid by hand there)
    # (C4986, the 10 u on +3V3_ETH, stands on the back beside DVDD33's 100 nF: Realtek wants the bulk input
    #  capacitors within 5 mm of DVDD33 (pin 29); it used to stand on the front north of the fan, 9 mm away)
    put_facing(pl, "R4913", 113.3 + E, 15.6, "+3V3_ETH", "W")                 # MDIO pull-up, off the back lanes' band
    put_facing(pl, "FB8221", 114.3 + E, 14.0, "+3V3", "E")                    # +3V3 -> +3V3_ETH, north of the back lanes
    put_facing(pl, "C8221", 117.6 + E, 14.0, "+3V3_ETH", "W")


# --- the HDMI coupling capacitors ------------------------------------------------------------------------------
HDMI_CAP_X = (140.2 + E, 138.1 + E)                  # the two columns (0402 courtyards are 2.08 wide): east (straight on to its jack pad), west (on the rows between)
HDMI_ROW = 0.6                               # the rows: 0402 pads 0.62 tall, a 0.2 track between two of them needs 0.6

def hdmi_caps(pl):
    """The eight TMDS coupling capacitors in the jack's order, one row each 0.6 mm apart from the first
    TMDS pad's row, alternating between the east column (its jack pad straight east) and the west column
    (0.3 mm south of its pad: the stub jogs that much); FPGA-side pad west.  pcb/river.plan_hdmi lays
    the stubs and the lanes from exactly these pads."""
    import re
    jack = sorted((pl.padpos[("J503", n)][1], net) for n, net in pl.nets["J503"].items() if re.match(r"Net-\(J503-(D[012]|CK)[+-]\)$", net))
    if len(jack) != 8:
        raise SystemExit("floorplan: %d TMDS pads on the HDMI jack, not 8" % len(jack))
    y0 = jack[0][0]
    for i, (yj, jnet) in enumerate(jack):
        ref = one(pl, nets=(jnet,), prefix="C")
        fnet = [n for n in pl.nets[ref].values() if n != jnet][0]
        put_facing(pl, ref, HDMI_CAP_X[i % 2], y0 + HDMI_ROW * i, fnet, "W")


# --- the microSD card (J504 on the back, contacts west, the card enters from the east): the board under the
# card's travel stays blank -- 16 mm beyond the socket's mouth, the card's width plus a margin
SD_CARD_PATH = (115.6 + E, 76.5, 133.0 + E, 91.8)


def sd_card_path_check(pl, fp_box):
    """Nothing on the back within the card's path, nothing through-hole anywhere in it.  Returns the offenders."""
    x0, y0, x1, y1 = SD_CARD_PATH
    bad = []
    for ref, (x, y, rot, layer) in pl.placed.items():
        if ref == "J504" or ref.startswith("H"):
            continue
        bx0, by0, bx1, by1 = fp_box(ref)
        if bx0 < x1 and x0 < bx1 and by0 < y1 and y0 < by1 and (layer == "B.Cu" or pl.fp[ref]["th_any"]):
            bad.append(ref)
    return bad


# --- the VCCAUX (+2V5_AUX) feed, by hand.  Its two balls, G11 (74.0, 56.8) and L7 (70.8, 60.0), stand in the
# core's via field, where every neighbour is a via: the only way out is the 0.5 mm channels between via
# rows, which the router's 0.16 mm clearance cannot use.  G11 steps to the channel x 73.6, down it to the
# channel y 60.4, west to x 71.2 (where L7 joins), down the channel x 71.2 out of the package (the ring-4
# escapes use x 69.6 and 70.4), then east along y 66.8 under the south face's exits to the ferrite behind
# the 2.5 V LDO.  AUX_KEEP keeps the ball-pair capacitors' pads out of those channels (build_pcb.bga_caps).
AUX_KEEP = [(73.3, 56.6, 73.9, 60.7), (71.0, 60.1, 73.9, 60.7), (70.9, 60.1, 71.5, 66.9)]


def aux_feed(pl):
    aux = "+2V5_AUX"
    HAND.append(("B.Cu", aux, [(74.0, 56.8), (73.6, 57.2), (73.6, 60.4), (71.2, 60.4), (71.2, 66.6)], 0.127))
    HAND.append(("B.Cu", aux, [(70.8, 60.0), (71.2, 60.4)], 0.127))
    HAND.append(("B.Cu", aux, [(71.2, 66.6), (71.2, 66.8), (83.6, 66.8), (83.6, 68.6), (93.59, 68.6), (93.59, 66.3)], 0.25))   # round the 2.5 V LDO's south pads
    # its capacitors stand on that run, east of the south face's exits, ground pads south
    put_facing(pl, "C5812", 78.3, 67.5, aux, "N", "B.Cu")
    put_facing(pl, "C5811", 80.3, 68.1, aux, "N", "B.Cu")
    put_facing(pl, "C5813", 82.4, 67.7, aux, "N", "B.Cu")
    # the 3.3 V island under the core (In3) is fed from the 3.3 V plane on In4 through vias in the gaps between
    # four balls at the core's edge, where the 1.1 V patch (build_pcb.RAIL_ZONES) ends and no escape runs
    for (vx, vy) in ((74.4, 56.4), (74.4, 58.8), (74.4, 60.4)):                      # (the core's west edge is too close to the patch: a via there stands on the seam)
        HAND.append(("via", "+3V3", vx, vy, 0.3, 0.15))


# --- the silkscreen boxes: a polygon per section where the parts' bounding box would not do (clockwise from
# the top-left, so the first edge is the top edge the name goes into); every other section gets its bounding box
SECTION_BOX = {
    "CLK IN": [(8.8, 3.6), (28.6, 3.6), (28.6, 20.4), (8.8, 20.4)],
    "CLK OUT": [(8.8, 20.6), (19.0, 20.6), (19.0, 37.4), (8.8, 37.4)],
    "BUTTONS": [(19.6, 20.6), (32.5, 20.6), (32.5, 37.4), (19.6, 37.4)],
    "ADC A IN": [(8.8, 37.6), (44.7, 37.6), (44.7, 54.5), (8.8, 54.5)],
    "ADC B IN": [(8.8, 54.7), (44.7, 54.7), (44.7, 71.5), (35.6, 71.5), (35.6, 75.1), (8.8, 75.1)],
    "DAC 1 OUT": [(8.8, 75.3), (35.8, 75.3), (35.8, 71.7), (44.6, 71.7), (44.6, 88.1), (8.8, 88.1)],      # (the upper strip is DAC 1's since build 28)
    # (a notch at the bottom left: the noise resistors' values stand over them, inside the NOISE box's raised corner)
    "DAC 2 OUT": [(8.8, 88.6), (44.6, 88.6), (44.6, 101.1), (20.7, 101.1), (20.7, 99.15), (8.8, 99.15)],
    "NOISE + PHOTODIODE": [(8.6, 99.4), (20.7, 99.4), (20.7, 101.35), (46.9, 101.35), (46.9, 116.3), (8.6, 116.3)],
    "-4.2 V": [(47.2, 101.8), (58.7, 101.8), (58.7, 116.3), (47.2, 116.3)],
    "POWER": [(58.9, 94.0), (121.6, 94.0), (121.6, 116.3), (58.9, 116.3)],
    "ETHERNET": [(85.0 + E, 4.2), (134.8 + E, 4.2), (134.8 + E, 28.0), (114.5 + E, 28.0), (114.5 + E, 36.0), (103.3 + E, 36.0), (103.3 + E, 38.5), (85.0 + E, 38.5)],   # (west to the RX resistors' far side, south under the strap columns since build 28)
    "FTDI + USB": [(112.5 + E, 28.6), (140.9 + E, 28.6), (140.9 + E, 54.4), (136.6 + E, 54.4), (136.6 + E, 57.4), (131.5 + E, 57.4), (131.5 + E, 60.9), (103.6 + E, 60.9), (103.6 + E, 36.5), (112.5 + E, 36.5)],   # (down to 60.9 west of the HDMI box since build 28: the EEPROM's name under it)
    "HDMI": [(133.5 + E, 57.6), (142.2 + E, 57.6), (142.2 + E, 70.3), (130.6 + E, 70.3), (130.6 + E, 61.2), (133.5 + E, 61.2)],
    "PMODS": [(128.0 + E, 70.6), (143.5 + E, 70.6), (143.5 + E, 109.4), (142.2 + E, 109.4), (142.2 + E, 116.0), (133.6 + E, 116.0), (133.6 + E, 109.6), (128.0 + E, 109.6)],
    "RGB LED": [(119.0 + E, 107.5), (129.6 + E, 107.5), (129.6 + E, 116.3), (119.0 + E, 116.3)],
    "LEDS": [(29.3, 4.0), (58.3, 4.0), (58.3, 16.6), (29.3, 16.6)],
    "CLOCK GEN": [(58.6, 4.0), (85.2, 4.0), (85.2, 20.0), (58.6, 20.0)],
    "FLASH + JTAG": [(72.5, 69.0), (109.0, 69.0), (109.0, 83.5), (72.5, 83.5)],      # (top at 69.0 since build 28: the JTAG header's pin names stand over its pins)
}


# --- everything, in order; the keep-outs for what the rivers and the labels need ------------------------------
def layout(pl):
    """Place the anchors, then every hand-laid cluster.  Returns nothing; the placer's spiral search
    handles what is left (the FPGA's decoupling band, stray parts)."""
    pl.section = {}
    for ref, (x, y, rot, layer) in ANCHORS.items():
        if ref in pl.fp:
            put(pl, ref, x, y, rot, layer, quiet=False)
            pl.section[ref] = ANCHOR_SECTION.get(ref)
    for sec, fn in (("ADC A IN", lambda: adc_strip(pl, "A")), ("ADC B IN", lambda: adc_strip(pl, "B")), (None, lambda: adc_common(pl)),
                    ("DAC 2 OUT", lambda: dac_strip(pl, 2)), ("DAC 1 OUT", lambda: dac_strip(pl, 1)), (None, lambda: dac_common(pl)), (None, lambda: adc_control_lines(pl)),
                    ("CLK IN", lambda: clocks(pl)), ("LEDS", lambda: leds_buttons(pl)), ("NOISE + PHOTODIODE", lambda: noise_pd(pl)),
                    (None, lambda: analog_power(pl)), ("ETHERNET", lambda: phy(pl)), ("ETHERNET", lambda: ethernet_lines(pl)),
                    ("FTDI + USB", lambda: ftdi_usb(pl)), ("HDMI", lambda: hdmi_caps(pl)), ("PMODS", lambda: pmods_sd(pl)),
                    ("POWER", lambda: power(pl)), ("FLASH + JTAG", lambda: memory(pl)), (None, lambda: aux_feed(pl))):
        SECTION[0] = sec
        fn()
        SECTION[0] = None


def keepouts():
    """(layer or None, x0, y0, x1, y1): where the spiral search may not put anything."""
    fx, fy = FPGA
    K = []
    K.append(("F.Cu", fx - 10.5, fy - 10.5, fx + 10.5, fy + 10.5))          # the escape band
    K.append(("B.Cu", fx - 9.0, fy - 9.0, fx + 9.0, fy + 9.0))
    K.append(("B.Cu", fx - 40.0, fy - 40.0, fx + 40.0, fy - 7.0))            # the back around the FPGA: north, west, east
    K.append(("B.Cu", fx - 40.0, fy - 40.0, fx - 7.0, fy + 22.0))
    K.append(("B.Cu", fx + 7.0, fy - 40.0, fx + 40.0, fy + 18.0))
    K.append(("F.Cu", 46.9, 44.0, 64.0, 103.0))                             # the converters' rivers and the DAC's bundles north
    K.append(("F.Cu", 64.0, 66.0, 76.0, 103.0)); K.append(("B.Cu", 64.0, 66.0, 76.0, 103.0))   # the DAC's lanes into the south face
    K.append(("B.Cu", 66.3, 66.5, 78.0, 76.0))                              # the south face's other exits: no decoupling capacitor (and its vias) in front of them
    for box in ((101.4 + E, 8.5, 105.2 + E, 21.5), (88.5 + E, 8.5, 100.6 + E, 17.6), (88.5 + E, 17.4, 101.6 + E, 26.5), (83.0, 12.0, 90.6 + E, 57.0), (80.0, 51.5, 90.6 + E, 56.5)):
        K.append(("F.Cu",) + box)                                           # the Ethernet river
    K.append(("F.Cu", 80.0, 57.6, 131.0 + E, 60.0))                             # the HDMI lanes (rows J/K: no pair on the back)
    K.append(("F.Cu", 131.0 + E, 54.8, 141.6 + E, 65.0))                            # their jog and capacitor block (the jack at y 62)
    K.append(("B.Cu", 56.5, 59.0, 59.0, 97.0))                              # the DAC's back-layer lanes bending north
    K.append(("F.Cu", 80.0, 58.4, 129.0 + E, 64.0))                             # the Pmod lanes along the east face's lower rows
    K.append(("F.Cu", 113.5 + E, 64.0, 131.0 + E, 109.0))                           # ... and their bend south to the resistor columns (turn_x 124)
    K.append(("B.Cu",) + SD_CARD_PATH)                                       # the microSD card slides in and out over blank board (checked in build_pcb.place)
    K.append(("B.Cu", 45.5, 83.0, 56.5, 87.0))                              # the DAC's north-row vias (HAND): no stray capacitor on them
    K.append(("F.Cu", 101.0 + E, 26.9, 107.5 + E, 30.0)); K.append(("F.Cu", 106.5 + E, 19.5, 112.0 + E, 28.5))   # the PHY's south side; the MDI fan and its vias
    K.append(("B.Cu", 106.5 + E, 12.5, 123.0 + E, 28.5))                            # the MDI lines on the back
    K.append(("F.Cu", 133.0 + E, 9.5, 143.5 + E, 25.0)); K.append(("B.Cu", 133.0 + E, 9.5, 143.5 + E, 25.0))   # the LAN lines
    sx, sy = ANCHORS["U305"][0], ANCHORS["U305"][1]
    K.append(("F.Cu", sx - 7.0, sy + 10.5, sx + 7.0, fy - 7.0))              # the SDRAM river's straight run
    for lay in ("F.Cu", "B.Cu"):
        K.append((lay, 0.0, 0.0, BW, 3.5)); K.append((lay, 0.0, BH - 3.5, BW, BH))
    for r, y in SMA_Y.items():
        K.append(("F.Cu", 0.0, y + 4.8, 17.5, y + 9.2))                      # the SMA labels' strips
    return K
