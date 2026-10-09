"""Every part on the board: symbol, footprint, LCSC code, and why.

One table, read by the schematic generator (symbol + value + footprint), the
BOM (LCSC code, description), and the board builder (footprint).  A part gets
an LCSC code HERE, once, with the reason it is that one, so that the BOM
cannot disagree with the schematic.

Stock checked with tools/jlc_query.py on 2026-10-01/02 (see CLAUDE_CODE_CHAT.md
for the tables).  "Basic" parts carry no per-part setup fee at JLCPCB;
Extended ones cost about $3 per DISTINCT part per order, so passives are
pinned to Basic parts wherever one exists.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kisch
from kisch import make_box, make_opamp, make_fda, make_coax, SYMS

FP = {   # footprint shorthands
    "R0603": "Resistor_SMD:R_0603_1608Metric",
    "R0402": "Resistor_SMD:R_0402_1005Metric",
    "C0402": "Capacitor_SMD:C_0402_1005Metric",
    "C0402B": "ours:C_0402_1005Metric_BGA",        # 0402 with a trimmed courtyard: sits on two adjacent BGA ball vias
    "C0603": "Capacitor_SMD:C_0603_1608Metric",
    "C0805": "Capacitor_SMD:C_0805_2012Metric",
    "L0603": "Inductor_SMD:L_0603_1608Metric",
    "L0805": "Inductor_SMD:L_0805_2012Metric",
    "L4030": "easyeda:IND-SMD_L4.0-W4.0",
    "F1812": "Fuse:Fuse_1812_4532Metric",
    "SOT23": "Package_TO_SOT_SMD:SOT-23",
    "SOT23-5": "Package_TO_SOT_SMD:SOT-23-5",
    "SOT23-6": "Package_TO_SOT_SMD:SOT-23-6",
    "SOIC8": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "SOIC8W": "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
    "MSOP8": "Package_SO:MSOP-8_3x3mm_P0.65mm",
    "MSOP10": "Package_SO:MSOP-10_3x3mm_P0.5mm",
    "VSSOP8": "Package_SO:VSSOP-8_2.3x2mm_P0.5mm",
    "DFN8": "Package_DFN_QFN:DFN-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
    "SOD123": "Diode_SMD:D_SOD-123",
    "SOD323": "Diode_SMD:D_SOD-323",
    "SMA_D": "Diode_SMD:D_SMA",
    "LED0603": "LED_SMD:LED_0603_1608Metric",
    "LED2835": "easyeda:LED-SMD_L3.5-W2.8-RD",
    "C_1206": "Capacitor_SMD:C_1206_3216Metric",
    "C_1812": "Capacitor_SMD:C_1812_4532Metric",
    "R1206": "Resistor_SMD:R_1206_3216Metric",
    "UFL": "ours:UFL_Hirose_U.FL-R-SMT-1",       # LCSC's land pattern for C88374 (easyeda2kicad), its two ground pads both numbered 2
    "XTAL3225": "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
    "TCXO5032": "Oscillator:Oscillator_SMD_Fox_FT5H_5.0x3.2mm",
    "BGA256": "Package_BGA:BGA-256_14.0x14.0mm_Layout16x16_P0.8mm_Ball0.45mm_Pad0.32mm_NSMD",
    "LQFP64_7": "Package_QFP:LQFP-64_7x7mm_P0.4mm",
    "LQFP48": "Package_QFP:LQFP-48_7x7mm_P0.5mm",
    "LQFP64_10": "Package_QFP:LQFP-64_10x10mm_P0.5mm",
    "TSOP54": "Package_SO:TSOP-II-54_22.2x10.16mm_P0.8mm",
    "WQFN40": "Package_DFN_QFN:QFN-40-1EP_5x5mm_P0.4mm_EP3.6x3.6mm",
    "USBC": "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
    "SMA": "Connector_Coaxial:SMA_BAT_Wireless_BWSMA-KWE-Z001",
    "RJ45": "easyeda:RJ45-TH_R-RJ45R08P-C000",
    "MAG24": "easyeda:SMD-24_L15.1-W7.1-P1.00-LS10.0-BL",
    "HDMI_C": "easyeda:HDMI-SMD_A71-05H4-111N1",
    "USD": "easyeda:TF-SMD_TF-01A",
    "SW_1088": "easyeda:SW-SMD_L3.9-W3.0-P4.45",
    "DIP4": "easyeda:SW-TH_DSWB04LHGET",
    "PD": "ours:VBPW34S_K1_A2",       # LCSC's footprint renumbered: pad 1 = cathode, as KiCad's D_Photo symbol expects
    "H1x2": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    "H1x3": "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
    "H1x4": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    "H1x6": "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
    "H2x3": "Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical",
    "PMOD": "Connector_PinSocket_2.54mm:PinSocket_2x06_P2.54mm_Horizontal",
    "PMOD_V": "Connector_PinSocket_2.54mm:PinSocket_2x06_P2.54mm_Vertical",
    "H2x8": "Connector_PinHeader_2.54mm:PinHeader_2x08_P2.54mm_Vertical",
    "H2x9": "Connector_PinHeader_2.54mm:PinHeader_2x09_P2.54mm_Vertical",
    "RGB1615": "easyeda:LED-ARRAY-SMD_4P-L1.6-W1.5-BR_XL-1615RGBC-RF",   # LCSC's land pattern for C965840 (easyeda2kicad)
    "TP": "TestPoint:TestPoint_Pad_D1.5mm",
    "HOLE": "MountingHole:MountingHole_3.2mm_M3_Pad",
}

# ---------------------------------------------------------------------------
# LCSC codes.  (value, footprint shorthand) -> (code, why)
# ---------------------------------------------------------------------------
LCSC = {
    # --- the ICs -----------------------------------------------------------
    ("LFE5U-25F-6BG256C", "BGA256"): ("C1521614", "the only ECP5 JLCPCB stocks in quantity (81 on 2026-10-01); $14.25"),
    ("AD9238BSTZ-65", "LQFP64_7"): ("C514277", "dual 12-bit 65 MSPS ADC, 21 in stock, $71; two AD9226 would be $157"),
    ("AD9767ASTZRL", "LQFP48"): ("C653820", "dual 14-bit 125 MSPS DAC, 147 in stock, $14"),
    ("RTL8211F-CG", "WQFN40"): ("C187932", "gigabit RGMII PHY with internal 1.0 V switcher, 88k in stock, $1.38"),
    ("W9825G6KH-6", "TSOP54"): ("C62246", "32 MB SDRAM, the Icepi Zero's part, 8909 in stock, $5.63"),
    ("W25Q128JVSIQ", "SOIC8W"): ("C97521", "Basic. 16 MB QSPI flash, 51k in stock"),
    ("FT2232HL", "LQFP64_10"): ("C27882", "dual-channel USB: JTAG on A, serial on B at the same time; 1666 in stock, $11.74"),
    ("93LC56BT-I/OT", "SOT23-6"): ("C190271", "FTDI EEPROM (optional, blank works), 10k in stock, $0.44"),
    ("Si5351A-B-GTR", "MSOP10"): ("C504891", "three programmable clocks, 33k in stock, $1.20"),
    ("FT5HNBPK25.0-T1", "TCXO5032"): ("C5742665", "Fox 25 MHz TCXO, ±2.5 ppm, HCMOS; the GPSDO board's part, 1514 in stock"),
    ("THS4521IDGKR", "MSOP8"): ("C170157", "FDA driving the ADC: 145 MHz, 4.6 nV/rtHz, rail-to-rail, 26k in stock, $1.34"),
    ("OPA1612AIDR", "SOIC8"): ("C94590", "dual 1.1 nV/rtHz preamp, 40 MHz GBW, 29k in stock, $1.33"),
    ("OPA2810IDR", "SOIC8"): ("C1849413", "dual FET-input 140 MHz: DAC I-V stage, TIA, LED driver; 2247 in stock, $3.01"),
    ("TLV62569DBVR", "SOT23-5"): ("C141836", "2 A buck, the Icepi Zero's regulator, 243k in stock, $0.08"),
    ("LP5907MFX-2.5", "SOT23-5"): ("C165132", "250 mA LDO for VCCAUX, 30k in stock"),
    ("TPS7A2033PDBVR", "SOT23-5"): ("C2862740", "300 mA 10 uVrms LDO for the converters' analog rails, 204k in stock, $0.22"),
    ("LM27761DSGR", "DFN8"): ("C129351", "inverting charge pump + LDO for -4.5 V, 21k in stock, $1.31"),
    ("PCA9306DC1Z", "VSSOP8"): ("C5119911", "HDMI DDC level shifter, 3723 in stock, $0.74"),
    ("SN74LVC1GU04DBVR", "SOT23-5"): ("C81934", "unbuffered inverter, self-biased clock squarer (GPSDO front end), 1748 in stock"),
    ("SN74LVC1G17DBVR", "SOT23-5"): ("C7836", "Schmitt buffer, 58k in stock"),
    ("USBLC6-2SC6", "SOT23-6"): ("C2827654", "USB ESD, 90k in stock, $0.05"),
    ("SS8050", "SOT23"): ("C2150", "Basic NPN, 1.5 A, for the LED driver"),
    ("BAV99", "SOT23"): ("C2500", "Basic dual clamp diode"),
    ("B5819W", "SOD123"): ("C8598", "Basic 1 A Schottky, bench 5 V input OR-ing (builds 1-31)"),
    ("SS34", "SMA_D"): ("C8678", "Basic 3 A 40 V Schottky (SMA, 70 C/W): the bench input since build 32 -- the B5819W was 1 A / 0.5 W behind a 2 A fuse"),
    ("AO3401A", "SOT23"): ("C15127", "Basic P-FET, -30 V, 4 A, 60 mohm at -4.5 V: USB PROG's switch since build 32, off while a bench supply is on J601 (no back-feed into the laptop)"),
    ("2.2R", "R1206"): ("C2907376", "2.2 ohm 1206 0.25 W ahead of the ADC's LDO (build 32): 0.1 W of its 0.36 W at 65 MS/s"),
    ("VBPW34S", "PD"): ("C145262", "PIN photodiode 430-1100 nm, 24k in stock, $0.60"),
    ("XL-2835SURC-05", "LED2835"): ("C2843878", "red 0.4 W emitter (2835), 217k in stock, $0.06"),
    ("DSWB04LHGET", "DIP4"): ("C99418", "4-way DIP switch (noise-source resistors), 51k in stock, $0.21"),
    ("TS-1088-AR02016", "SW_1088"): ("C720477", "Basic tactile switch, the one that fits (jlcbuild README)"),
    ("USB4105-GF-A-120", "USBC"): ("C5184243", "USB-C 16P receptacle, the Icepi Zero's part, 3949 in stock"),
    ("BWSMA-KWE-Z001", "SMA"): ("C496551", "edge SMA, 158k in stock, $0.53 (hand soldered)"),
    ("R-RJ45R08P-C000", "RJ45"): ("C386757", "plain shielded RJ45, 53k in stock, $0.45 (through-hole; JLCPCB fits it)"),
    ("G2406S", "MAG24"): ("C507595", "1000BASE-T magnetics with 4 separate chip-side centre taps, 30k in stock, $0.47"),
    ("A71-05H4-111N1", "HDMI_C"): ("C2682170", "mini-HDMI, the Icepi Zero's part, 1576 in stock"),
    ("TF-01A", "USD"): ("C91145", "microSD push-push, 201k in stock, $0.19"),
    ("X322525MOB4SI", "XTAL3225"): ("C9006", "Basic 25 MHz crystal 12 pF (PHY)"),
    ("X322512MSB4SI", "XTAL3225"): ("C9002", "Basic 12 MHz crystal 20 pF (FT2232H)"),
    ("TXM25M0004322DBCDO00T", "XTAL3225"): ("C362338", "25 MHz 10 pF 30R ESR for the Si5351 (GPSDO round 24 survey)"),
    ("SWPA4030S2R2NT", "L4030"): ("C279948", "2.2 uH 2.95 A shielded inductor for the bucks, 13k in stock"),
    ("MF-MSMF200-2", "F1812"): ("C210837", "2 A resettable fuse on the USB 5 V input and (F602, build 31) on the bench 5 V header"),
    ("GZ2012D601TF", "L0805"): ("C1017", "Basic 600R@100MHz ferrite, 500 mA"),
    ("BLM18KG601SN1D", "L0603"): ("C85833", "600R@100MHz 1.3 A ferrite (rails that carry current), 941k in stock"),
    ("2.2uH", "L4030"): ("C279948", "the bucks' power inductor, also the PHY's switcher (C1043, the 0805 chip inductor builds 1-23 had there, is rated 50 mA)"),
    ("Y", "H1x2"): ("C492401", "2.54 mm 1x2 header PZ254V-11-02P (through-hole; JLCPCB fits it); builds 1-33: the 1x40 strip C2337"),
    ("1N4148W", "SOD123"): ("C81598", "Basic fast diode"),
    ("MF-MSMF050-2", "F1812"): ("C17313", "500 mA resettable fuse for the HDMI 5 V"),
    ("white", "LED0603"): ("C2290", "Basic 0603 white LED, KT-0603W (the Icepi Zero's): the user LEDs"),
    ("red", "LED0603"): ("C2286", "Basic 0603 red LED, KT-0603R, 1.8 V: the power-good LEDs, run dim"),
    ("green", "LED0603"): ("C12624", "0603 green LED, KT-0603G, 306k in stock: the Ethernet link LEDs"),
    ("XL-1615RGBC-RF", "RGB1615"): ("C965840", "common-anode RGB LED 1.6 x 1.5 mm, 617k in stock, $0.02; pads per LCSC's pattern: 1 R, 2 anode, 3 B, 4 G"),
    ("25MHz", "XTAL3225"): ("C9006", "Basic 25 MHz 12 pF crystal (PHY)"),
    ("12MHz", "XTAL3225"): ("C9002", "Basic 12 MHz 20 pF crystal (FT2232H)"),
    ("SW_Push", "SW_1088"): ("C720477", "Basic tactile switch"),
    ("1nF 2kV", "C_1206"): ("C53084552", "1 nF 2 kV X7R 1206: the Ethernet Bob Smith bridge of builds 1-25"),
    ("1nF 3kV", "C_1812"): ("C692296", "1 nF 3 kV X7R 1812 (FV43X102K302EFG): the Bob Smith bridge since build 26 -- a longer body, the reviews' point about the 1206's 1.4 mm gap"),
    ("100R", "R1206"): ("C17901", "Basic 100 R 1206, 0.25 W: the ADC input's series resistor survives a ±10 V source into the clamp (0.18 W; the 0603 was 0.1 W)"),
    ("TLV3501AIDBVR", "SOT23-6"): ("C193413", "4.5 ns rail-to-rail comparator with 6 mV hysteresis: the CLK IN squarer since build 26 (builds 1-25: a self-biased unbuffered inverter)"),
    ("U.FL-R-SMT-1(80)", "UFL"): ("C88374", "Hirose U.FL jack: the monitor taps (plug a U.FL-SMA pigtail into a scope)"),
}

# Basic/Preferred passives, 0603 resistors (0603WAF... series) and 0402/0603/0805 capacitors.
# Every code here is checked against JLCPCB's own description of it when the release is built (make_fab.code_value_check):
# builds 1-24 had seven wrong ones (27R was a 240 R, 47R a 47 k, 75R a 5.62 k, 2.49k a 270 k, 24.9R a 470 k, 499k a 536 k,
# 1.3M a 27 k), typing slips that no drawing shows and that would have made the USB, the DAC outputs, the PHY's bias
# and the -4.4 V pump all wrong on the first board.
RES = {
    "0R": "C21189", "10R": "C22859", "22R": "C23345", "27R": "C25190", "33R": "C23140",
    "47R": "C23182", "49.9R": "C23185", "75R": "C4275", "100R": "C22775", "150R": "C22808",
    "330R": "C23138", "470R": "C23179", "499R": "C137714", "1k": "C21190", "1.5k": "C22843",
    "2k": "C22975", "2.2k": "C4190", "3.3k": "C22978", "4.7k": "C23162", "5.1k": "C23186",
    "9.1k": "C23260", "10k": "C25804", "12k": "C22790", "15k": "C22809", "22k": "C31850",
    "47k": "C25819", "100k": "C25803", "200k": "C25811", "2.49k": "C22908", "24.9R": "C22916", "499k": "C26751", "1M": "C22935", "1.3M": "C13316",
    "1.2M": "C22766",
}
CAP = {
    ("100nF", "C0402"): "C1525", ("100nF", "C0402B"): "C1525", ("1uF", "C0402"): "C52923", ("22pF", "C0402"): "C1555",
    ("27pF", "C0402"): "C1557", ("18pF", "C0402"): "C1549", ("10pF", "C0402"): "C32949",
    # (2.2 pF: C1559 = 0402CG2R2C500NT.  Builds 1-24 said C1512, which is a 1206 180 k resistor: mfg/footprint_check.py found it)
    ("2.2pF", "C0402"): "C1559", ("47pF", "C0402"): "C1567", ("10nF", "C0402"): "C15195",
    ("22nF", "C0402"): "C1532", ("22nF", "C0402B"): "C1532", ("1nF", "C0402"): "C1523", ("4.7uF", "C0603"): "C19666",
    ("10uF", "C0603"): "C96446", ("22uF", "C0805"): "C45783", ("1uF", "C0603"): "C15849",
    ("100nF", "C0603"): "C14663", ("10nF", "C0603"): "C57112",
}


# The sheets name a part by what a reader knows it as ("AD9238", "mini HDMI"); the LCSC table is keyed by the
# orderable part number.  Build 20's release had no code for the two converters, the six op amps, the HDMI jack
# and the microSD socket because of exactly this gap, and nothing failed: they had silently joined the
# hand-solder list.
ALIASES = {"AD9238": "AD9238BSTZ-65", "AD9767": "AD9767ASTZRL", "OPA2810": "OPA2810IDR", "OPA1612": "OPA1612AIDR",
           "THS4521": "THS4521IDGKR", "mini HDMI": "A71-05H4-111N1", "microSD": "TF-01A", "SMA": "BWSMA-KWE-Z001",
           "RJ45": "R-RJ45R08P-C000", "USBC": "USB4105-GF-A-120", "U.FL": "U.FL-R-SMT-1(80)"}


# Through-hole parts JLCPCB fits since 2026-10-06 (Jason: "even if it costs extra"; the USB-C's shell
# legs already pay the per-order through-hole fee).  By footprint: a header is the same part whatever
# the jumper is called.  The 2.54 mm headers come as strips the assembler snaps to length, as on the
# GPSDO board JLCPCB built; the Pmod sockets are a stocked 2x6 right-angle female header (8910 in
# stock, 2026-10-06), checked against the footprint by mfg/footprint_check.py.
# Build 34 (Jason, 2026-10-08, JLCPCB's preview of build 33): every header showed as the whole 40-pin strip, a 100 mm bar
# centred on its pin 1 across the board.  JLCPCB draws (and stocks) the strip; its engineers snap it, but the preview
# cannot be checked and the drawing is not the part on the board.  Each header is now the stocked part of its own length
# (XFCN PZ254V, 2.54 mm, gold flash, all Extended -- the strips were Extended too), so JLCPCB's drawing, pins and
# origin are the footprint's and footprint_check.py fits them by pin number like any other part.
LCSC_BY_FP = {"H1x2": "C492401", "H1x3": "C2937625", "H1x4": "C2691448", "H1x6": "C492405",   # PZ254V-11-0nP, 1 row
              "H2x3": "C29952", "H2x8": "C492425", "H2x9": "C492426",                       # PZ254V-12-nnP, 2 rows (2x3 unused: no stocked black one)
              "PMOD": "C22373932"}                                                     # HC-PM254-8.5H-2x6PW, 2x6 right-angle female


def lcsc_for(value, fp_key, ref=""):
    """The LCSC code for a (value, footprint) pair, or None."""
    value = ALIASES.get(value, value)
    if (value, fp_key) in LCSC:
        return LCSC[(value, fp_key)][0]
    if fp_key == "R0603" and value in RES:
        return RES[value]
    if (value, fp_key) in CAP:
        return CAP[(value, fp_key)]
    if fp_key in LCSC_BY_FP:
        return LCSC_BY_FP[fp_key]
    return None


# ---------------------------------------------------------------------------
# Generated symbols.  Pins are (number, name, etype).
# ---------------------------------------------------------------------------
def _io(nums_names):
    return [(n, nm, "bidirectional") for n, nm in nums_names]


def make_hole(lib_id, value="M3"):
    """A mounting hole: two circles and one pin, so the pad can be tied to ground."""
    name = lib_id.split(":", 1)[1]
    out = kisch._hdr(name, "H", value, 3.0, keywords="M3 mounting hole, pad tied to ground")
    out.append('(symbol "%s_1_1"' % name)
    out.append('(circle (center 0 0) (radius 1.6) (stroke (width 0.254) (type default)) (fill (type none)))')
    out.append('(circle (center 0 0) (radius 2.54) (stroke (width 0.254) (type default)) (fill (type none)))')
    out.append(kisch._pin("1", "", 0.0, -5.08, 90, 2.54, "passive"))
    out.append(')')
    out += ['(embedded_fonts no)', ')']
    return SYMS.define(lib_id, "\n".join(out))


def make_dual_diode(lib_id, value="BAV99"):
    """A series-connected dual diode (BAV99: pin 1 anode of D1, pin 3 its cathode and D2's anode, pin 2 D2's
    cathode) drawn as TWO units, one diode each, so the two can be placed anti-parallel across a pair of nodes
    (unit 1: 1 -> 3, unit 2: 3 -> 2).  Horizontal, anode on the left."""
    name = lib_id.split(":", 1)[1]
    out = kisch._hdr(name, "D", value, 6.0, keywords="dual diode, one unit per diode")
    for u, (a, k) in enumerate((("1", "3"), ("3", "2")), 1):
        out.append('(symbol "%s_%d_1"' % (name, u))
        out.append(kisch._poly([(-1.27, 1.27), (1.27, 0.0), (-1.27, -1.27), (-1.27, 1.27)], fill="outline"))
        out.append(kisch._poly([(1.27, 1.27), (1.27, -1.27)]))
        out.append(kisch._pin(a, "A", -3.81, 0.0, 0, 2.54, "passive"))
        out.append(kisch._pin(k, "K", 3.81, 0.0, 180, 2.54, "passive"))
        out.append(')')
    out += ['(embedded_fonts no)', ')']
    return SYMS.define(lib_id, "\n".join(out))


def make_antiparallel(lib_id, value="BAV99"):
    """A BAV99 drawn as what it is used for here: two diodes anti-parallel between a node on pin 3 (top) and a
    node on pins 1 and 2 (bottom, 2.54 apart).  Pin 1 is D1's anode (D1: 1 -> 3), pin 2 is D2's cathode (D2: 3 -> 2).
    7.62 mm tall, so it stands exactly between two rows 7.62 apart."""
    name = lib_id.split(":", 1)[1]
    out = kisch._hdr(name, "D", value, 6.0, keywords="dual diode wired anti-parallel")
    out.append('(symbol "%s_1_1"' % name)
    # left diode points up (1 -> 3), right diode points down (3 -> 2)
    out.append(kisch._poly([(-2.17, -1.0), (-1.27, 0.6), (-0.37, -1.0), (-2.17, -1.0)], fill="outline"))
    out.append(kisch._poly([(-2.17, 0.6), (-0.37, 0.6)]))
    out.append(kisch._poly([(0.37, 1.0), (1.27, -0.6), (2.17, 1.0), (0.37, 1.0)], fill="outline"))
    out.append(kisch._poly([(0.37, -0.6), (2.17, -0.6)]))
    out.append(kisch._poly([(-1.27, -2.54), (-1.27, -1.0)]))
    out.append(kisch._poly([(-1.27, 0.6), (-1.27, 2.54), (1.27, 2.54), (1.27, 1.0)]))
    out.append(kisch._poly([(1.27, -0.6), (1.27, -2.54)]))
    out.append(kisch._poly([(0.0, 2.54), (0.0, 2.54)]))
    # pin names "~" print nothing: "K1A2" in the middle of the symbol read as a part name (Jason, 2026-10-07)
    out.append(kisch._pin("3", "~", 0.0, 3.81, 270, 1.27, "passive"))
    out.append(kisch._pin("1", "~", -1.27, -3.81, 90, 1.27, "passive"))
    out.append(kisch._pin("2", "~", 1.27, -3.81, 90, 1.27, "passive"))
    out.append(')')
    out += ['(embedded_fonts no)', ')']
    return SYMS.define(lib_id, "\n".join(out))


def make_comparator(lib_id, value):
    """A comparator drawn like an op amp (unit 1: + on top, - below, out right) with its supply unit (unit 2:
    V+ above, V- below, SHDN on the left).  TLV3501 in SOT-23-6: 1 -IN, 2 V-, 3 +IN, 4 V+, 5 OUT, 6 SHDN."""
    name = lib_id.split(":", 1)[1]
    out = kisch._hdr(name, "U", value, 6.0, keywords="comparator")
    out.append('(symbol "%s_1_1"' % name)
    out.append(kisch._poly([(-5.08, 5.08), (5.08, 0), (-5.08, -5.08), (-5.08, 5.08)], fill="background"))
    out.append(kisch._pin("3", "+", -7.62, 2.54, 0, 2.54, "input", 1.27))
    out.append(kisch._pin("1", "-", -7.62, -2.54, 0, 2.54, "input", 1.27))
    out.append(kisch._pin("5", "", 7.62, 0.0, 180, 2.54, "output"))
    out.append(')')
    out.append('(symbol "%s_2_1"' % name)
    out.append(kisch._rect(-5.08, 3.81, 5.08, -3.81))
    out.append(kisch._pin("4", "V+", 0.0, 7.62, 270, 3.81, "power_in"))
    out.append(kisch._pin("2", "V-", 0.0, -7.62, 90, 3.81, "power_in"))
    out.append(kisch._pin("6", "SHDN", -7.62, 0.0, 0, 2.54, "input"))
    out.append(')')
    out += ['(embedded_fonts no)', ')']
    return SYMS.define(lib_id, "\n".join(out))


def define_symbols(fpga_json):
    """Define every non-stock symbol; returns the dict of lib_ids used."""
    balls = fpga_json["balls"]
    assign = fpga_json["assign"]
    inv = {b: s for s, b in assign.items()}
    import fpga as F
    ids = {}

    # --- the FPGA, one unit per bank + one power unit ---------------------
    units = []
    order = [7, 6, 0, 1, 2, 3, 8]
    unit_of_bank = {}
    for ui, bank in enumerate(order, 1):
        bb = [d for d in balls.values() if d["io"] and d["bank"] == str(bank)]
        bb.sort(key=F._order_key(bank))
        # sort by the plan order where assigned, keeping unassigned at the end.  The order is the WHOLE
        # plan's, not the bank's: a bus signal the board moved into this bank (pcb/river.py hands a face's
        # balls out by position) still sorts with the buses at the top, above the single wires, or the
        # LEDs' and buttons' fan-out below the symbol would cross the bus members' wires
        plan_sigs = [s for name, bk, sigs in F.PLAN for s in sigs]
        pos = {s: i for i, s in enumerate(plan_sigs)}
        BUS = ("ADC_A_D", "ADC_B_D", "DAC_P1_D", "DAC_P2_D", "SDRAM_DQ", "SDRAM_A", "ETH_TXD", "ETH_RXD", "PMODA_", "PMODB_")
        def is_bus(sname):
            return any(sname.startswith(b) and sname[len(b):].isdigit() for b in BUS)
        # buses first (so a bus's horizontal run never crosses a single signal's wire), then singles, then spares
        bb.sort(key=lambda d: (0 if is_bus(inv.get(d["ball"], "")) else 1, pos.get(inv.get(d["ball"], ""), 999), d["row"], d["col"]))
        pins = []
        for d in bb:
            nm = d["ball"]
            if d["pclk"]:
                nm += " PCLK"
            pins.append((d["ball"], nm, "bidirectional"))
        if bank == 8:
            # sysCONFIG dual-purpose + the dedicated config pins on the same unit
            cfg = [("N9", "N9 CCLK/MCLK", "bidirectional"), ("R9", "R9 PROGRAMN", "input"), ("", ""),
                   ("T9", "T9 INITN", "bidirectional"), ("", ""), ("P9", "P9 DONE", "bidirectional"), ("", ""), ("", ""),
                   ("N10", "N10 CFG0", "input"), ("", ""), ("P10", "P10 CFG1", "input"), ("", ""), ("R10", "R10 CFG2", "input"),
                   ("", ""), ("", ""), ("T10", "T10 TCK", "input"), ("", ""), ("T11", "T11 TMS", "input"), ("", ""),
                   ("R11", "R11 TDI", "input"), ("", ""), ("M10", "M10 TDO", "output")]
            # flash pins first (they are in the plan as FIXED), then the rest
            flash = ["N8", "T8", "T7", "M7", "N7"]
            rest = [p for p in pins if p[0] not in flash]
            spaced = []
            for p in rest:
                spaced += [p, ("", "")]
            pins = [p for p in pins if p[0] in flash] + [cfg[0], ("", ""), ("", "")] + spaced
            units.append(dict(left=pins, right=cfg[1:], w=38.1))
        elif bank in (7, 6, 0):
            units.append(dict(left=pins, w=27.94))
        else:
            units.append(dict(right=pins, w=27.94))
        unit_of_bank[bank] = ui
    # power unit
    vcc = sorted([b for b, d in balls.items() if d["kind"] == "vcc"])
    aux = sorted([b for b, d in balls.items() if d["kind"] == "vccaux"])
    vio = sorted([b for b, d in balls.items() if d["kind"] == "vccio"], key=lambda b: (balls[b]["func"], b))
    gnd = sorted([b for b, d in balls.items() if d["kind"] == "gnd"])
    top = [(b, "VCC", "power_in") for b in vcc] + [(b, "VCCAUX", "power_in") for b in aux] + \
          [(b, balls[b]["func"], "power_in") for b in vio]
    bot = [(b, "GND", "power_in") for b in gnd]
    units.append(dict(top=top, bottom=bot, w=max(len(top), len(bot)) * 2.54 + 5.08))
    ids["fpga"] = make_box("ours:LFE5U-25F-6BG256C", units, ref="U", value="LFE5U-25F-6BG256C",
                           keywords="Lattice ECP5 FPGA, 24k LUTs, caBGA256")
    ids["fpga_units"] = unit_of_bank
    ids["fpga_power_unit"] = len(units)

    # --- AD9238 dual ADC: one trapezoid per channel (analog in on the tall
    # left side, 7.62 mm apart to match the FDA's outputs; data out on the
    # short right side) and one box for everything the two channels share:
    # references, mode pins, supplies, grounds.  Three units, one chip, and
    # the sheet draws a dashed box around the three to say so. ------------
    def adc_channel(ch, vp, vn, clk, data, otr, pdwn, oeb):
        gap = ("", "")
        left = [(vn, "VIN-_%s" % ch, "input"), gap, gap, (vp, "VIN+_%s" % ch, "input")]
        right = [(str(data[i]), "D%d_%s" % (11 - i, ch), "output") for i in range(12)]
        right += [(otr, "OTR_%s" % ch, "output"), gap, (pdwn, "PDWN_%s" % ch, "input"), gap, (oeb, "OEB_%s" % ch, "input")]
        # the sample clock enters the sloped bottom edge from below, like a flip-flop's clock (2026-10-07)
        return dict(left=left, right=right, bottom=[(clk, "CLK_%s" % ch, "input")], w=33.02, shape="trap_r")
    ca = adc_channel("A", "2", "3", "63", [57, 56, 55, 54, 51, 50, 49, 48, 47, 46, 45, 44], "58", "60", "59")
    cb = adc_channel("B", "15", "14", "18", [38, 37, 36, 35, 34, 33, 32, 31, 30, 27, 26, 25], "39", "21", "22")
    gap = ("", "")
    cm = dict(left=[("9", "SENSE", "input"), gap, ("62", "SHARED_REF", "input"), ("61", "MUX_SELECT", "input"), gap,
                    ("19", "DCS", "input"), ("20", "DFS", "input"), gap,
                    ("23", "DNC", "no_connect"), ("24", "DNC", "no_connect"), ("42", "DNC", "no_connect"), ("43", "DNC", "no_connect")],
              right=[("6", "REFT_A", "passive"), ("7", "REFB_A", "passive"), gap, gap, gap, gap,
                     ("11", "REFT_B", "passive"), ("10", "REFB_B", "passive"), gap, gap, gap, ("8", "VREF", "passive")],
              top=[("5", "AVDD", "power_in"), ("12", "AVDD", "power_in"), ("17", "AVDD", "power_in"), ("64", "AVDD", "power_in"),
                   ("29", "DRVDD", "power_in"), ("41", "DRVDD", "power_in"), ("52", "DRVDD", "power_in")],
              bottom=[("1", "AGND", "power_in"), ("4", "AGND", "power_in"), ("13", "AGND", "power_in"), ("16", "AGND", "power_in"),
                      ("28", "DRGND", "power_in"), ("40", "DRGND", "power_in"), ("53", "DRGND", "power_in")], w=33.02)
    ids["adc"] = make_box("ours:AD9238", [ca, cb, cm], value="AD9238BSTZ-65",
                          keywords="dual 12-bit 65 MSPS ADC")

    # --- AD9767 dual DAC: one trapezoid per port (14 data bits, WRT and CLK
    # on the tall left side; the complementary current outputs 7.62 mm apart
    # on the short right side) and one common box. --------------------------
    def dac_port(n, base, wrt, clk, iouta, ioutb):
        left = [(str(base + i), "DB%dP%d" % (13 - i, n), "input") for i in range(14)]      # MSB first on both ports (pin 1 / pin 23)
        # WRT and CLK enter the sloped bottom edge from below, like a flip-flop's clock (2026-10-07)
        bottom = [(wrt, "WRT%d/IQ%s" % (n, "WRT" if n == 1 else "SEL"), "input"), (clk, "CLK%d/IQ%s" % (n, "CLK" if n == 1 else "RESET"), "input")]
        right = [(iouta, "IOUTA%d" % n, "output"), gap, gap, (ioutb, "IOUTB%d" % n, "output")]
        return dict(left=left, right=right, bottom=bottom, w=30.48, shape="trap")
    p1 = dac_port(1, 1, "17", "18", "46", "45")
    p2 = dac_port(2, 23, "20", "19", "39", "40")
    cm = dict(left=[("48", "MODE", "input"), gap, ("37", "SLEEP", "input"), gap, ("42", "GAINCTRL", "input")],
              right=[("44", "FSADJ1", "passive"), ("41", "FSADJ2", "passive"), gap, ("43", "REFIO", "passive")],
              top=[("47", "AVDD", "power_in"), ("16", "DVDD1", "power_in"), ("22", "DVDD2", "power_in")],
              bottom=[("38", "ACOM", "power_in"), ("15", "DCOM1", "power_in"), ("21", "DCOM2", "power_in")], w=25.4)
    ids["dac"] = make_box("ours:AD9767", [p1, p2, cm], value="AD9767ASTZRL",
                          keywords="dual 14-bit 125 MSPS DAC")

    # --- RTL8211F PHY: RGMII unit, line unit, power/misc unit -----------------
    # Unit A: RGMII and management.  The management pins are seven rows apart
    # so that each pull-up (resistor plus flag, ~16 mm) fits above its own wire.
    G = ("", "")
    rg = dict(left=[G, ("15", "TXD3", "input"), ("16", "TXD2", "input"), ("17", "TXD1", "input"), ("18", "TXD0", "input"),
                    ("20", "TXC", "input"), ("19", "TXCTL", "input"), G, G,
                    ("22", "RXD3/PHYAD0", "output"), ("23", "RXD2/PLLOFF", "output"), ("24", "RXD1/TXDLY", "output"),
                    ("25", "RXD0/RXDLY", "output"), ("27", "RXC/PHYAD1", "output"), ("26", "RXCTL/PHYAD2", "output"),
                    G, ("13", "MDC", "input")] + [G] * 6 + [("14", "MDIO", "bidirectional")] + [G] * 6
                    + [("31", "INTB/PMEB", "open_collector")] + [G] * 6 + [("12", "PHYRSTB", "input")], w=27.94)
    # Unit B: the line side.  MDI pairs on the right, in the row pattern the
    # magnetics symbol repeats so the eight wires are straight; LEDs (seven rows
    # apart, for the same reason) and the crystal on the left.
    ln = dict(left=[("32", "LED0/CFG_EXT", "bidirectional")] + [G] * 6 + [("33", "LED1/CFG_LDO0", "bidirectional")] + [G] * 6
                   + [("34", "LED2/CFG_LDO1", "bidirectional")] + [G] * 4
                   + [("36", "XTAL_IN", "input"), ("37", "XTAL_OUT", "output"), ("35", "CLKOUT", "output")],
              right=[("1", "MDIP0", "bidirectional"), ("2", "MDIN0", "bidirectional"), G,
                     ("4", "MDIP1", "bidirectional"), ("5", "MDIN1", "bidirectional"), G,
                     ("6", "MDIP2", "bidirectional"), ("7", "MDIN2", "bidirectional"), G,
                     ("9", "MDIP3", "bidirectional"), ("10", "MDIN3", "bidirectional")], w=30.48)
    pw = dict(top=[("11", "AVDD33", "power_in"), ("40", "AVDD33", "power_in"), ("29", "DVDD33", "power_in"),
                   ("28", "DVDD_RG", "power_in"), ("3", "AVDD10", "power_in"), ("8", "AVDD10", "power_in"),
                   ("38", "AVDD10", "power_in"), ("21", "DVDD10", "power_in")],
              bottom=[("41", "GND", "power_in")],
              right=[("30", "REG_OUT", "power_out"), ("", ""), ("", ""), ("", ""), ("39", "RSET", "passive")], w=27.94)
    ids["phy"] = make_box("ours:RTL8211F-CG", [rg, ln, pw], value="RTL8211F-CG",
                          keywords="10/100/1000 Ethernet PHY, RGMII")

    # --- W9825G6KH SDRAM: a stock-looking box with the JEDEC TSOP-54 pinout ---
    ad = [("23", "A0"), ("24", "A1"), ("25", "A2"), ("26", "A3"), ("29", "A4"), ("30", "A5"), ("31", "A6"),
          ("32", "A7"), ("33", "A8"), ("34", "A9"), ("22", "A10"), ("35", "A11"), ("36", "A12"),
          ("", ""), ("20", "BA0"), ("21", "BA1"), ("", ""), ("38", "CLK"), ("37", "CKE"), ("19", "~{CS}"),
          ("18", "~{RAS}"), ("17", "~{CAS}"), ("16", "~{WE}"), ("", ""), ("15", "DQML"), ("39", "DQMH")]
    dq = [("2", "DQ0"), ("4", "DQ1"), ("5", "DQ2"), ("7", "DQ3"), ("8", "DQ4"), ("10", "DQ5"), ("11", "DQ6"),
          ("13", "DQ7"), ("42", "DQ8"), ("44", "DQ9"), ("45", "DQ10"), ("47", "DQ11"), ("48", "DQ12"),
          ("50", "DQ13"), ("51", "DQ14"), ("53", "DQ15")]
    sd = dict(left=[(n, nm, "input") if nm else (n, nm) for n, nm in ad],
              right=[(n, nm, "bidirectional") for n, nm in dq] + [("", ""), ("40", "NC", "no_connect")],
              top=[("1", "VDD", "power_in"), ("14", "VDD", "power_in"), ("27", "VDD", "power_in"),
                   ("3", "VDDQ", "power_in"), ("9", "VDDQ", "power_in"), ("43", "VDDQ", "power_in"), ("49", "VDDQ", "power_in")],
              bottom=[("28", "VSS", "power_in"), ("41", "VSS", "power_in"), ("54", "VSS", "power_in"),
                      ("6", "VSSQ", "power_in"), ("12", "VSSQ", "power_in"), ("46", "VSSQ", "power_in"), ("52", "VSSQ", "power_in")],
              w=27.94)
    ids["sdram"] = make_box("ours:W9825G6KH", [sd], value="W9825G6KH-6", keywords="32 MB SDR SDRAM 16-bit")

    # --- TCXO, 4-pin 5032: 1 = E/D (NC), 2 = GND, 3 = OUT, 4 = VCC (Fox FT5H) ---
    # FT5HN (5032, 4 pads): 1 GND, 2 GND, 3 OUT, 4 VDD -- no enable pin on this part (checked against the Fox drawing)
    ids["tcxo"] = make_box("ours:TCXO_25MHz", [dict(right=[("3", "OUT", "output")],
                                                    top=[("4", "VCC", "power_in")], bottom=[("1", "GND", "power_in"), ("2", "GND", "power_in")], w=15.24)],
                           ref="X", value="FT5HNBPK25.0-T1", keywords="25 MHz TCXO HCMOS")

    # --- Gigabit magnetics G2406S (24-pin): chip side 1-12, line side 13-24 ---
    # Pairs first (same row pattern as the PHY's line unit: +, -, gap), the
    # four centre taps grouped at the bottom where their parts hang freely.
    chip, line, ctc, ctl = [], [], [], []
    for k in range(4):
        b = 1 + 3 * k
        chip += [(str(b + 2), "TD%d-" % (k + 1), "passive"), (str(b + 1), "TD%d+" % (k + 1), "passive"), ("", "")]   # "-" above "+": the P signals land on the "-" ends (sheet_eth)
        ctc.append((str(b), "TCT%d" % (k + 1), "passive"))
        b = 24 - 3 * k
        line += [(str(b - 2), "MX%d-" % (k + 1), "passive"), (str(b - 1), "MX%d+" % (k + 1), "passive"), ("", "")]
        ctl.append((str(b), "MCT%d" % (k + 1), "passive"))
    chip, line = chip + ctc, line + ctl
    ids["mag"] = make_box("ours:G2406S", [dict(left=chip, right=line, w=22.86)], ref="T", value="G2406S",
                          keywords="1000BASE-T magnetics 1CT:1CT x4")

    # --- RJ45 jack (8 contacts + shield) -------------------------------------
    ids["rj45"] = make_box("ours:RJ45_8P8C", [dict(left=[(str(i), "P%d" % i, "passive") for i in range(1, 9)]
                                                    + [("", ""), ("13", "SHIELD", "passive"), ("14", "SHIELD", "passive")], w=15.24)],   # the footprint's two shield legs (pads 13/14; "SH" matched no pad in builds 1-16)
                           ref="J", value="R-RJ45R08P-C000", keywords="RJ45 jack shielded")

    # --- mini-HDMI type C, 19 pins + shield -----------------------------------
    # Rows grouped so each group can be wired as one: the four pairs (22 nF
    # each), then the five grounds (one bar), then the control pins.
    # Type C (mini) numbering, NOT type A: the shield comes first in each pair, DDC/CEC ground is 13,
    # CEC 14, reserved 17.  The A71-05H4-111N1 footprint's four shell tabs are pads 20-23.
    hd = [("2", "D2+"), ("3", "D2-"), ("5", "D1+"), ("6", "D1-"), ("8", "D0+"), ("9", "D0-"), ("11", "CK+"), ("12", "CK-"),
          ("", ""), ("18", "+5V"), ("14", "CEC"), ("17", "UTIL"), ("15", "SCL"), ("16", "SDA"), ("19", "HPD"),
          ("", ""), ("1", "D2_SH"), ("4", "D1_SH"), ("7", "D0_SH"), ("10", "CK_SH"), ("13", "DDC_GND"),
          ("20", "SHELL"), ("21", "SHELL"), ("22", "SHELL"), ("23", "SHELL")]
    ids["hdmi"] = make_box("ours:HDMI_C", [dict(left=[(n, nm, "passive") for n, nm in hd], w=17.78)],
                           ref="J", value="A71-05H4-111N1", keywords="mini HDMI type C receptacle")

    # --- microSD TF-01A: 8 contacts + 2 detect + shield ----------------------
    # VDD on top (its flag goes up freely), the five pulled-up lines and CLK as
    # a group (drawn as a staircase of pull-ups), then ground, detect, shield.
    sdp = [("4", "VDD"), ("", ""), ("1", "DAT2"), ("2", "DAT3/CD"), ("3", "CMD"), ("7", "DAT0"), ("8", "DAT1"), ("5", "CLK"),
           ("", ""), ("6", "VSS"), ("9", "CD1"), ("10", "CD2"), ("SH", "SHIELD")]
    ids["usd"] = make_box("ours:microSD", [dict(left=[(n, nm, "passive") for n, nm in sdp], w=17.78)],
                          ref="J", value="TF-01A", keywords="microSD push-push socket")

    # --- op-amps and FDA (stock symbols exist for THS4521/OPA1612; define OPA2810) ---
    ids["opa2810"] = make_opamp("ours:OPA2810", [("1", "2", "3"), ("7", "6", "5")], ("8", "4"),
                                value="OPA2810IDR", keywords="dual FET-input 140 MHz op amp")
    ids["opa1612"] = make_opamp("ours:OPA1612", [("1", "2", "3"), ("7", "6", "5")], ("8", "4"),
                                value="OPA1612AIDR", keywords="dual 1.1 nV/rtHz op amp")
    ids["fda"] = make_fda("ours:THS4521", dict(in_p="8", in_n="1", vocm="2", pd="7", vs_p="3", vs_n="6",
                                               out_n="5", out_p="4"), value="THS4521IDGKR",
                          keywords="fully differential ADC driver")
    # Reference pins on the top rows (their flags go up without crossing the
    # data lines); SCL/SDA on the same rows both sides.
    ids["pca9306"] = make_box("ours:PCA9306", [dict(left=[("2", "VREF1", "power_in"), ("", ""), ("", ""),
                                                          ("3", "SCL1", "bidirectional"), ("4", "SDA1", "bidirectional")],
                                                    right=[("7", "VREF2", "passive"), ("8", "EN", "input"), ("", ""),
                                                           ("6", "SCL2", "bidirectional"), ("5", "SDA2", "bidirectional")],
                                                    bottom=[("1", "GND", "power_in")], w=20.32)],
                              value="PCA9306DC1Z", keywords="I2C level shifter")
    # CS and CLK on the right (toward the FT2232H), DI and DO on the left so the
    # data net has a free side for its pull-up and the 2.2 k DO link.
    # SOT-23-6 pinout (Microchip's pin function table, SOT-23 column): 1 DO, 2 VSS, 3 DI, 4 CLK, 5 CS, 6 VCC
    ids["eeprom"] = make_box("ours:93LC56B", [dict(left=[("3", "DI", "input"), ("1", "DO", "output")],
                                                  right=[("5", "CS", "input"), ("4", "CLK", "input")],
                                                  top=[("6", "VCC", "power_in")], bottom=[("2", "VSS", "power_in")], w=17.78)],
                             value="93LC56BT-I/OT", keywords="2 kbit microwire EEPROM")
    # Row order = the order of the same six signals on bank 8's unit (M7 WP,
    # N7 HOLD, N8 CS, T7 DO, T8 DI, N9 CLK): with both sides in the same order
    # the six wires between them need no crossings.  The three pulled-up pins
    # are the top three, so one pull-up ladder sits above them all.
    ids["flash"] = make_box("ours:W25Q128JVS", [dict(right=[("3", "~{WP}/IO2", "bidirectional"), ("", ""),
                                                            ("7", "~{HOLD}/IO3", "bidirectional"), ("", ""),
                                                            ("1", "~{CS}", "input"), ("", ""), ("", ""),
                                                            ("2", "DO/IO1", "bidirectional"), ("5", "DI/IO0", "bidirectional"),
                                                            ("6", "CLK", "input")],
                                                     top=[("8", "VCC", "power_in")], bottom=[("4", "GND", "power_in")], w=22.86)],
                            value="W25Q128JVSIQ", keywords="16 MB quad SPI flash")
    ids["sma"] = make_coax("ours:SMA_in", value="SMA", side="right")
    ids["hole"] = make_hole("ours:MountingHole")
    ids["sma_out"] = make_coax("ours:SMA_out", value="SMA", side="left")
    ids["ufl"] = make_coax("ours:UFL_tap", value="U.FL", side="left")
    ids["ap_diode"] = make_antiparallel("ours:BAV99_antiparallel")           # the anti-parallel pair across each FDA's inputs
    ids["cmp"] = make_comparator("ours:TLV3501", "TLV3501AIDBVR")             # the CLK IN comparator        # the monitor taps: pin 1 signal, pin 2 the shell (both ground pads)
    # --- RGB LED, common anode.  LCSC's land pattern for the XL-1615RGBC-RF numbers the pads 1 R, 2 anode,
    # 3 B, 4 G (the datasheet numbers the same four pads 1 R, 2 anode, 3 G, 4 B going round the other way;
    # the names on the pads agree, the numbers do not): the symbol follows the pattern it is placed on.
    ids["rgb"] = make_box("ours:LED_RGB_CA", [dict(left=[("1", "R", "passive"), ("4", "G", "passive"), ("3", "B", "passive")],
                                                   right=[("2", "A", "passive")], w=12.7)],
                          ref="D", value="XL-1615RGBC-RF", keywords="RGB LED common anode 1615")
    # --- LM27761 inverting charge pump (stock symbol exists), TPS7A20 (stock) ---
    # --- photodiode and 2835 LED use stock Device symbols ---
    return ids
