#!/usr/bin/env python3
"""The ECP5 caBGA256 ball map, and which signal lives on which ball.

Everything about the FPGA's pins comes from Lattice's own pinout CSV
(datasheets/FPGA-SC-02033-2-0-ECP5U-25-Pinout.csv), never retyped.  The
assignment is made HERE, once, by rule, and then everything else -- the
schematic, the board, the .lpf, the LiteX platform file -- reads it.

The rule is geometric, because last month's attempt proved that the ball a bus
is given matters more than anything downstream: each peripheral faces one side
of the package, its bus is assigned to the bank on that side, and the bits are
handed out in the order the balls appear along that side so that a straight
ribbon of tracks connects them without crossing.  A data bit is a data bit --
the gateware does not care which ball D5 is on -- so the physical order wins
and the logical order follows it.

Rings: ring 0 is the outermost row/column of balls, ring 1 the next, etc.  On a
16 x 16 grid the centre is ring 7.  Rings 0 and 1 escape on the top layer
(ring 1 between ring-0 pads); every deeper ball gets a via in its pad.
"""
import csv, os, re, json, collections

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "..", "datasheets", "FPGA-SC-02033-2-0-ECP5U-25-Pinout.csv")
OUT = os.path.join(HERE, "..", "build", "fpga_pins.json")

ROWS = "ABCDEFGHJKLMNPRT"          # 16 rows, no I, O, Q, S
PITCH = 0.8
PART = "LFE5U-25F-6BG256C"


def load():
    rows = list(csv.reader(open(CSV, encoding="utf-8", errors="replace")))
    hdr = next(i for i, r in enumerate(rows) if "CABGA256" in [c.strip() for c in r])
    H = [c.strip() for c in rows[hdr]]
    ci = {h: i for i, h in enumerate(H)}
    balls = {}
    for r in rows[hdr + 1:]:
        if len(r) <= ci["CABGA256"]:
            continue
        b = r[ci["CABGA256"]].strip()
        if not b or b == "-":
            continue
        func = r[ci["Pin/Ball Function"]].strip()
        bank = r[ci["Bank"]].strip()
        d = dict(ball=b, pad=r[0].strip(), func=func, bank=bank,
                 dual=r[ci["Dual Function"]].strip(),
                 diff=r[ci["Differential"]].strip(),
                 hs=r[ci["High Speed"]].strip() == "TRUE",
                 dqs=r[ci["DQS"]].strip())
        d["row"] = ROWS.index(b[0]); d["col"] = int(b[1:]) - 1
        d["ring"] = min(d["row"], d["col"], 15 - d["row"], 15 - d["col"])
        # package-relative position in mm, x right, y down, origin at the centre
        d["x"] = (d["col"] - 7.5) * PITCH
        d["y"] = (d["row"] - 7.5) * PITCH
        # A user I/O is a PL/PR/PT/PB pad; PROGRAMN also starts with P.
        d["io"] = bool(re.match(r"P[LRTB]\d", func)) and bank not in ("", "-", "40")
        d["pclk"] = "PCLK" in d["dual"]
        d["kind"] = ("io" if d["io"] else
                     "gnd" if func == "GND" else
                     "vcc" if func == "VCC" else
                     "vccaux" if func.startswith("VCCAUX") else
                     "vccio" if func.startswith("VCCIO") else "cfg")
        balls[b] = d
    return balls


BALLS = load()


def side_of(d):
    """Which package edge a ball is nearest: W, E, N or S (ties go to W/E)."""
    r, c = d["row"], d["col"]
    cand = [(c, "W"), (15 - c, "E"), (r, "N"), (15 - r, "S")]
    return min(cand)[1]


# --------------------------------------------------------------------------
# What is on which bank.  Each entry: bus name -> (bank, list of signal names
# in LOGICAL order, sort key for the balls).  The bank is chosen by the side
# of the package the peripheral sits on (see pcb/floorplan.py, which places
# the peripherals to match):
#     bank 7  W upper   ADC (AD9238)            bank 6  W lower   DAC (AD9767)
#     bank 0  N left    clocks, LEDs, buttons   bank 1  N right   SDRAM
#     bank 2  E upper   RGMII, GPDI             bank 3  E lower   SD, USB, UART, PMODs
#     bank 8  S         flash (sysCONFIG), slow controls
# --------------------------------------------------------------------------
def _bus(prefix, n, rev=False):
    r = range(n - 1, -1, -1) if rev else range(n)
    return ["%s%d" % (prefix, i) for i in r]


# Signals that MUST be on a primary clock input (PCLK) ball.
NEED_PCLK = {"CLK_TCXO", "CLK_SI0", "CLK_SI1", "CLK_SI2", "CLK_EXT", "ETH_RXC"}
# Which PCLK balls a bank's clocks take first (see CLOCKS in PLAN): the ones whose escape leaves on an
# inner layer, or at the edge of a river, so the bus rivers of pcb/river.py keep the top layer.
PCLK_PREF = {0: ["C7", "D7", "E7"], 7: ["K1", "K2"]}

# Signals that must be LVDS output pairs (true/comp) -- the GPDI (HDMI) lines.
PAIRS = [("GPDI_CK_P", "GPDI_CK_N"), ("GPDI_D0_P", "GPDI_D0_N"),
         ("GPDI_D1_P", "GPDI_D1_N"), ("GPDI_D2_P", "GPDI_D2_N")]

PLAN = [
    # bank 7, west upper: two clocks on the bank's spare PCLK pair, then the two ADC channels.  Channel
    # A (upper) first.
    ("CLOCKS_W", 7, ["CLK_SI2", "CLK_EXT"]),
    ("ADC_A", 7, ["ADC_A_OTR"] + _bus("ADC_A_D", 12, rev=True) + ["ADC_A_CLK"]),
    ("ADC_B", 7, ["ADC_B_CLK"] + _bus("ADC_B_D", 12, rev=True) + ["ADC_B_OTR"]),
    # bank 6, west lower: the DAC, port 2 above port 1 (see the floorplan).
    ("DAC_P2", 6, _bus("DAC_P2_D", 14, rev=True)),
    ("DAC_CLK", 6, ["DAC_WRT2", "DAC_CLK2", "DAC_CLK1", "DAC_WRT1"]),
    ("DAC_P1", 6, _bus("DAC_P1_D", 14, rev=True)),
    # bank 1, north right: the SDRAM.  Two groups: the data (bottom edge of the
    # chip, nearest the FPGA) and the address/control.
    ("SDRAM_DQ", 1, _bus("SDRAM_DQ", 16) + ["SDRAM_DQML", "SDRAM_DQMH"]),
    ("SDRAM_A", 1, _bus("SDRAM_A", 11) + ["SDRAM_WE_N", "SDRAM_CAS_N"]),       # (RAS_N in bank 0: E8 is ETH_RXC's)
    # bank 0, north left: the rest of the SDRAM, then clocks, LEDs, buttons.
    ("SDRAM_X", 0, ["SDRAM_A11", "SDRAM_A12", "SDRAM_BA0", "SDRAM_BA1",
                    "SDRAM_CKE", "SDRAM_CLK", "SDRAM_CS_N", "SDRAM_RAS_N"]),
    # The row order of this group IS the schematic: every clock reaches the bank
    # through its own vertical channel left of the symbol, and this order (the
    # ones whose sources are above the symbol first, then the ones whose
    # sources are below, each group by depth) is the one where no channel
    # crosses another clock's wire.  See sheet_fpga.py.
    # Three clocks stay in bank 0 and two go to bank 7's spare PCLK pair (K1/K2, rows 9 at the south
    # edge of the ADC's ribbon): bank 0's PCLK balls sit in the middle of the north face, exactly where
    # the SDRAM's river has to pass, so the clocks that stay take the three INNER-layer PCLK balls
    # (C7 In2, D7 In3, E7 ring 4) and the river leaves one narrow corridor per inner layer for them
    # (pcb/river.py); the top layer, where the river is widest, needs no corridor at all.
    ("CLOCKS", 0, ["CLK_TCXO", "CLK_SI0", "CLK_SI1", "I2C_SDA", "I2C_SCL"]),
    ("MISC0", 0, ["CLK_OUT"] + ["LED%d" % i for i in range(8)] + ["BTN0", "BTN1"]),
    # bank 2, east upper: gigabit Ethernet (RGMII) and the GPDI/HDMI port.
    ("ETH_TX", 2, ["ETH_TXC", "ETH_TX_CTL", "ETH_TXD0", "ETH_TXD1", "ETH_TXD2", "ETH_TXD3"]),
    ("ETH_RX", 2, ["ETH_RXC", "ETH_RX_CTL", "ETH_RXD0", "ETH_RXD1", "ETH_RXD2", "ETH_RXD3"]),
    ("ETH_MGMT", 2, ["ETH_MDC", "ETH_MDIO", "ETH_RST_N", "ETH_INT_N"]),
    ("GPDI", 2, [s for p in PAIRS for s in p]),
    ("FTDI", 2, ["FTDI_RTS", "FTDI_DTR"]),
    # The HDMI pairs' lanes run from the jack to the east face on three layers (pcb/river.py): nothing
    # north of them can reach a ball south of them except on the back.  So everything on the east side is
    # split by that band: the FTDI (serial, USB, its RTS/DTR) and the FPGA's own USB-C sit north of it and
    # take bank 2; the jack's own DDC/CEC/HPD pins (below its TMDS pins), the Pmods, the microSD (on the
    # back, south of the FPGA) and the RGB LED sit south of it and take bank 3.
    ("USB", 2, ["USB_DP", "USB_DN", "USB_PULLUP"]),
    ("UART", 2, ["UART_RX", "UART_TX"]),
    # bank 3, east lower: the HDMI jack's slow pins, the SD card, two Pmods, the RGB LED.
    ("GPDI_X", 3, ["GPDI_HPD", "GPDI_CEC", "GPDI_SCL", "GPDI_SDA"]),
    ("SD", 3, ["SD_CLK", "SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3"]),
    ("PMOD_A", 3, _bus("PMODA_", 8)),
    ("PMOD_B", 3, _bus("PMODB_", 8)),
    ("RGB", 3, ["LED_R", "LED_G", "LED_B"]),
    # bank 8, south: the flash is on dedicated dual-purpose pins (fixed below);
    # the slow controls take whatever is left.
    ("CTRL", 8, ["ADC_DCS", "ADC_DFS", "ADC_PDWN_A", "ADC_PDWN_B",
                 "DAC_MODE", "DAC_SLEEP"]),
]

# Fixed by the silicon: sysCONFIG dual-purpose pins the SPI flash must use
# (the same balls the Icepi Zero uses, verified against its netlist), JTAG,
# and the configuration control pins.
FIXED = {
    "FLASH_CS_N": "N8",    # CSSPIN
    "FLASH_SCK": "N9",     # CCLK / MCLK
    "FLASH_IO0": "T8",     # D0 / MOSI
    "FLASH_IO1": "T7",     # D1 / MISO
    "FLASH_IO2": "M7",     # D2 / WP#
    "FLASH_IO3": "N7",     # D3 / HOLD#
    "JTAG_TCK": "T10", "JTAG_TMS": "T11", "JTAG_TDI": "R11", "JTAG_TDO": "M10",
    "PROGRAMN": "R9", "INITN": "T9", "DONE": "P9",
    "CFG0": "N10", "CFG1": "P10", "CFG2": "R10",
    "ETH_RXC": "E8",       # a PCLK ball of bank 1: bank 2's other PCLK balls (J14-K16) sit south of the HDMI
                           # pairs, which wall the east side on every layer; this one leaves on the back
}


def _order_key(bank):
    """Sort balls of a bank in the order a ribbon arriving from that side
    meets them: along the side first, then depth into the package."""
    if bank in (7, 6):                 # west: top to bottom, outer first
        return lambda d: (d["row"], d["col"])
    if bank in (2, 3):                 # east: top to bottom, outer first
        return lambda d: (d["row"], -d["col"])
    if bank in (0, 1):                 # north: left to right, outer first
        return lambda d: (d["col"], d["row"])
    return lambda d: (d["col"], -d["row"])   # south


def assign():
    """Return {signal: ball} for every signal in PLAN and FIXED."""
    out = dict(FIXED)
    used = set(FIXED.values())
    pool = collections.defaultdict(list)
    for b, d in BALLS.items():
        if d["io"] and b not in used:
            pool[int(d["bank"])].append(d)
    for bank in pool:
        pool[bank].sort(key=_order_key(bank))
    for name, bank, sigs in PLAN:
        avail = [d for d in pool[bank] if d["ball"] not in used]
        if name == "GPDI":
            # The four TMDS pairs on bank 2's four SOUTHERN LVDS pairs (rows J and K), true pin = P.  Their
            # exits lie at y 58.0-59.6 on the east face, on the top layer (two pairs: J16/J15 own row and
            # inner midline, K16/K15 likewise), In2 (J14/K14) and In3 (J13/J12) -- none on the back, so the
            # pairs' run to the jack walls the east side on three layers only, and everything north of
            # bank 2's rows G/H stays free for the FTDI, the USB port and the PHY's management lines.
            # (pcb/river.ESCAPE_LAYERS / ESCAPE_MID_IN steer the escape to exactly those rows.)
            want = {"GPDI_D0": ("J16", "J15"), "GPDI_CK": ("K16", "K15"), "GPDI_D1": ("J14", "K14"), "GPDI_D2": ("J13", "J12")}
            by_ball = {d["ball"]: d for d in avail}
            for (sp, sn) in PAIRS:
                p, n = want[sp[:-2]]
                if p not in by_ball or n not in by_ball or not by_ball[p]["diff"].startswith("True_OF_") or not by_ball[n]["diff"].startswith("Comp_OF_"):
                    raise SystemExit("GPDI: %s/%s are not a free true/comp pair in bank %d" % (p, n, bank))
                out[sp] = p; out[sn] = n; used.update((p, n))
            continue
        for s in sigs:
            if s in out:
                continue                    # pinned by FIXED (ETH_RXC on E8): the plan does not hand it a second ball
            if s in NEED_PCLK:
                # A dedicated primary-clock input, and the TRUE half of a pair
                # before the COMPLEMENT half before a general-routing one.
                free = [d for d in avail if d["pclk"] and d["ball"] not in used]
                pref = [d for b in PCLK_PREF.get(bank, []) for d in free if d["ball"] == b]
                cands = (pref +
                         [d for d in free if "PCLKT" in d["dual"] and d not in pref] +
                         [d for d in free if "PCLKC" in d["dual"] and d not in pref] +
                         [d for d in free if "GR_PCLK" in d["dual"] and d not in pref])
            else:
                cands = [d for d in avail if d["ball"] not in used]
            if not cands:
                raise SystemExit("bank %d ran out of balls at %s (%s)" % (bank, s, name))
            d = cands[0]
            out[s] = d["ball"]; used.add(d["ball"])
    return out


def _lvds_pairs(avail):
    """(true, comp) ball pairs among `avail`, from the CSV's Differential column
    (True_OF_PR47B pairs with Comp_OF_PR47A: same pad name, A/B suffix)."""
    by_pad = {d["pad"]: d for d in avail}
    pairs = []
    for d in avail:
        if d["diff"].startswith("True_OF_"):
            padname = d["diff"][len("True_OF_"):]          # e.g. PR47B or PR47D
            comp = padname[:-1] + {"B": "A", "D": "C"}[padname[-1]]
            for e in avail:
                if e["diff"] == "Comp_OF_" + comp:
                    pairs.append((d, e))
    pairs.sort(key=lambda t: (t[0]["row"], -t[0]["col"]))
    return pairs


def summary(a):
    inv = collections.defaultdict(list)
    for s, b in a.items():
        inv[int(BALLS[b]["bank"]) if BALLS[b]["bank"].isdigit() else -1].append(s)
    lines = []
    for bank in sorted(inv):
        n_io = sum(1 for d in BALLS.values() if d["io"] and d["bank"] == str(bank))
        lines.append("bank %s: %d of %d I/O used" % (bank, len(inv[bank]), n_io))
    return "\n".join(lines)


def grid(a):
    """A 16x16 text picture of what is on each ball."""
    inv = {b: s for s, b in a.items()}
    short = {"ADC": "A", "DAC": "D", "SDRAM": "M", "ETH": "E", "GPDI": "H", "SD": "S",
             "USB": "U", "UART": "u", "PMOD": "P", "CLK": "c", "LED": "l", "BTN": "b",
             "FTDI": "f", "FLASH": "F", "JTAG": "J", "I2C": "i"}
    out = ["     " + " ".join("%2d" % (c + 1) for c in range(16))]
    for r in range(16):
        cells = []
        for c in range(16):
            b = "%s%d" % (ROWS[r], c + 1)
            d = BALLS.get(b)
            if d is None:
                cells.append(" ."); continue
            if b in inv:
                s = inv[b]
                k = next((v for k, v in short.items() if s.startswith(k)), "?")
                cells.append(" " + k)
            elif d["kind"] == "io":
                cells.append(" -")
            elif d["kind"] == "gnd":
                cells.append(" G")
            else:
                cells.append(" V" if d["kind"] != "cfg" else " x")
        out.append("%2s   " % ROWS[r] + " ".join(cells))
    return "\n".join(out)


SWAPS = os.path.join(HERE, "..", "build", "pin_swaps.json")


def apply_swaps(a):
    """pcb/pinswap.py, run on the placed board, says which ball each free
    signal should really be on (a permutation inside each bank).  Apply it if
    it is there and still describes this plan; a stale file is an error, not
    a silent misroute."""
    if not os.path.exists(SWAPS):
        return a
    sw = json.load(open(SWAPS))["swaps"]
    inv = {b: s for s, b in a.items()}
    fixed = set(FIXED) | NEED_PCLK | {s for pr in PAIRS for s in pr}
    for s, b in sw.items():
        if s not in a or b not in BALLS or not BALLS[b]["io"]:
            raise SystemExit("build/pin_swaps.json is stale (%s -> %s is not in the plan); delete it and rebuild" % (s, b))
        if s in fixed and b != a[s]:
            raise SystemExit("build/pin_swaps.json moves the fixed signal %s; delete it and rebuild" % s)
        # a plain I/O may move to any bank: every bank's VCCIO is +3V3 on this board (the bus rivers of
        # pcb/river.py hand the balls of a face out in the order the river arrives, bank or no bank)
        if s in NEED_PCLK and not BALLS[b]["pclk"]:
            raise SystemExit("build/pin_swaps.json puts clock %s on a non-PCLK ball" % s)
    new = dict(a)
    new.update(sw)
    if len(set(new.values())) != len(new):
        raise SystemExit("build/pin_swaps.json is not a permutation; delete it and rebuild")
    moved = sum(1 for s in sw if a[s] != sw[s])
    print("pin swaps applied from build/pin_swaps.json: %d signals moved" % moved)
    return new


if __name__ == "__main__":
    a = apply_swaps(assign())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"part": PART, "assign": a,
               "balls": {b: {k: v for k, v in d.items()} for b, d in BALLS.items()}},
              open(OUT, "w"), indent=1, sort_keys=True)
    print(summary(a))
    print(grid(a))
    print("%d signals assigned -> %s" % (len(a), OUT))
    rings = collections.Counter(BALLS[b]["ring"] for b in a.values())
    print("by ring:", dict(sorted(rings.items())))
