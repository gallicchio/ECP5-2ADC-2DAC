"""The pin tables for ECP5-2ADC-2DAC rev A: what every IC's supply, reference, ground and strap pins want, transcribed
from the data sheets, and every rail's real voltage.  Read by tools/check_power_pins.py and tools/check_pairs.py, and
by the shared engine's config ~/OpticsPCBs/tools/pin_audit/boards/ECP5-2ADC-2DAC.py.

Written 2026-11-16, after board A's USB PROG turned out dead (bringup/REVB.md rows 12-13).  The format is the shared
engine's (pin_audit.py's docstring):

    RAILS  {net: (vmin, vmax)}                              RAIL_SOURCE {net: how the voltage was derived}
    PARTS  {netlist value: {pin: (name, vmin, vmax, 'file:line "quote"')}}   vmin == vmax == 0: a ground pin
    PASSTHRU, SERIES_C, PAIRS                               (check_pairs.py; pin_audit.py)

Ranges are the recommended operating conditions, not the absolute maximum, unless the entry says otherwise.  'file'
is under docs/datasheets/txt/ unless it names another place.  An entry marked MEMORY was not checked against a data
sheet on disk (there is none for the PCA9306).
"""
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _m(v, pct=1.0):
    """A measured rail: the reading +-pct % (the Fluke 45's 0.025 % plus drift and load; board A, 2026-11-16)."""
    return (round(v * (1 - pct / 100), 3), round(v * (1 + pct / 100), 3)) if v > 0 else (round(v * (1 + pct / 100), 3), round(v * (1 - pct / 100), 3))


# ---- the rails ---------------------------------------------------------------------------------------------------
RAILS = {
    'GND': (0.0, 0.0),
    '+5V': (4.20, 5.25),
    '+5VA': (4.20, 5.25),
    '+3V3': _m(3.331), '+3V3_DRV': _m(3.331), '+3V3_DAC_D': _m(3.331), '+3V3_ETH': _m(3.331),
    '+1V1': _m(1.106),
    '+2V5': _m(2.508), '+2V5_AUX': _m(2.508),
    '+3V3_ADC': _m(3.296),
    '+3V3_DAC': _m(3.293),
    '+1V0_PHY': _m(1.011),
    '-4V2': _m(-4.115),
    '+1V8_FTDI': (1.71, 1.89),
    '/Power/VBUS': (4.40, 5.25),
    'Net-(U504-VBUS)': (4.40, 5.25),
    'Net-(U505-EN)': (3.90, 5.25),
    'Net-(U601-SW)': (0.0, 5.25),
    'Net-(U602-SW)': (0.0, 5.25),
    'Net-(U606-CPOUT)': (-5.25, -4.20),
    'Net-(U103C-VREF)': (0.98, 1.02),
}
RAIL_SOURCE = {
    'GND': 'ground',
    '+5V': 'J601 (bench, through D601 SS34 and F602) or USB PROG VBUS through Q602.  Measured on board A, 2026-11-16: '
           '4.220 V (bench, thin leads), 5.047 V (USB).  Upper limit: USB 2.0 VBUS 5.25 V',
    '+5VA': '+5V through FB8231 (measured 4.226 V)',
    '+3V3': 'U601 TLV62569 buck, FB 15k/3.3k: 0.6 V x (1 + 15/3.3) = 3.33 V (TLV62569 VFB 0.6 V); measured 3.331 V',
    '+3V3_DRV': '+3V3 through FB8201', '+3V3_DAC_D': '+3V3 through FB8211', '+3V3_ETH': '+3V3 through FB8221',
    '+1V1': 'U602 TLV62569 buck, FB 10k/12k: 0.6 V x (1 + 10/12) = 1.10 V; measured 1.106 V',
    '+2V5': 'U603 LP5907MFX-2.5 (fixed 2.5 V) from +3V3; measured 2.508 V', '+2V5_AUX': '+2V5 through FB5811',
    '+3V3_ADC': 'U604 TPS7A2033 (fixed 3.3 V) from +5V through R8001 2.2 ohm; measured 3.296 V',
    '+3V3_DAC': 'U605 TPS7A2033 (fixed 3.3 V) from +5V; measured 3.293 V',
    '+1V0_PHY': 'U401 RTL8211F REG_OUT switcher through L401; measured 1.011 V',
    '-4V2': 'U606 LM27761 through FB8301, VFB divider 1.2M/499k; measured -4.115 V',
    '+1V8_FTDI': 'U502 FT2232H VREGOUT (DS_FT2232H.txt:3217 "VREGOUT Voltage regulator Output 1.71 1.80 1.89 V"); '
                 'VPHY read 1.78 V on board A behind FB6241 (Jason, 2026-11-16)',
    '/Power/VBUS': 'USB PROG J501 VBUS: USB 2.0 4.40-5.25 V at the device (MEMORY)',
    'Net-(U504-VBUS)': 'USB USER J502 VBUS: USB 2.0 4.40-5.25 V (MEMORY)',
    'Net-(U505-EN)': 'PCA9306 VREF2 = EN, 200k to +5V: the pass gate holds it near VREF1 + Vth (MEMORY: TI PCA9306 '
                     'application); at most +5V',
    'Net-(U601-SW)': 'TLV62569 switch node: GND to VIN', 'Net-(U602-SW)': 'TLV62569 switch node: GND to VIN',
    'Net-(U606-CPOUT)': 'LM27761 charge-pump output, unregulated, about -VIN',
    'Net-(U103C-VREF)': 'AD9238 internal reference with SENSE grounded: 1.0 V (ad9238.txt:1525 "If SENSE is grounded, '
                        'the reference amplifier ... 1.0 V"); a decoupling capacitor only',
}

D = 'docs/datasheets/txt/'


def _pins(names, entry):
    return {p: entry for p in names.split()}


# ---- ECP5: every CABGA256 ball's function from Lattice's own pinout CSV -------------------------------------------
def _ecp5():
    src_vcc = 'LFE5U-25F-6BG256C_C1521614.txt:3049 "VCC Core Supply Voltage ECP5 1.045 1.155 V"'
    src_aux = 'LFE5U-25F-6BG256C_C1521614.txt:3052 "VCCAUX Auxiliary Supply Voltage 2.375 2.625 V"'
    src_io = ('LFE5U-25F-6BG256C_C1521614.txt:3376 "LVCMOS33 3.135 3.3 3.465" (every bank\'s I/O in the LPF is LVCMOS33; '
              ':3053 VCCIO 1.14..3.465)')
    src_vih = 'LFE5U-25F-6BG256C_C1521614.txt:3430 "LVCMOS33 -0.3 0.8 2.0 3.465" (VIL max 0.8, VIH min 2.0)'
    t = {}
    rows = list(csv.reader(open(os.path.join(ROOT, 'datasheets', 'FPGA-SC-02033-2-0-ECP5U-25-Pinout.csv'))))
    hdr = next(i for i, r in enumerate(rows) if r and r[0] == 'PAD')
    col = rows[hdr].index('CABGA256')
    for r in rows[hdr + 1:]:
        if len(r) <= col or r[col] in ('', '-'):
            continue
        ball, fn = r[col], r[1]
        if fn == 'VCC':
            t[ball] = ('VCC', 1.045, 1.155, src_vcc)
        elif fn == 'VCCAUX':
            t[ball] = ('VCCAUX', 2.375, 2.625, src_aux)
        elif fn.startswith('VCCIO'):
            t[ball] = (fn, 3.135, 3.465, src_io)
        elif fn == 'GND':
            t[ball] = ('GND', 0, 0, 'FPGA-SC-02033 pinout CSV: GND')
        elif fn in ('CFG_0', 'CFG_2'):        # Master SPI is CFG[2:0] = 010 (DESIGN_REVIEW_RESPONSE.md, the Versa table)
            t[ball] = (fn + ' (low for Master SPI)', -0.3, 0.8, src_vih)
        elif fn == 'CFG_1':
            t[ball] = (fn + ' (high for Master SPI)', 2.0, 3.465, src_vih)
    return t


OPA_SPAN = {}           # part -> (V+ pin, V- pin, span min, span max, source): check_power_pins.py checks V+ - V-

PARTS = {
    'LFE5U-25F-6BG256C': _ecp5(),

    'FT2232HL': {
        **_pins('4', ('VPHY', 3.0, 3.6, 'DS_FT2232H.txt:3319 "VPHY, VPLL PHY Operating Supply Voltage 3.0 3.3 3.6 V"; :679 "VPHY +3.3V Input"')),
        **_pins('9', ('VPLL', 3.0, 3.6, 'DS_FT2232H.txt:3319 "VPHY, VPLL PHY Operating Supply Voltage 3.0 3.3 3.6 V"; :675 "VPLL +3.3V input"')),
        **_pins('12 37 64', ('VCORE', 1.62, 1.98, 'DS_FT2232H.txt:3211 "VCORE VCC Core Operating Supply Voltage 1.62 1.80 1.98 V"')),
        **_pins('20 31 42 56', ('VCCIO', 2.97, 3.63, 'DS_FT2232H.txt:3213 "VCCIO Operating Supply Voltage 2.97 3.30 3.63 V"')),
        **_pins('50', ('VREGIN', 3.0, 3.6, 'DS_FT2232H.txt:3215 "VREGIN Voltage regulator Input 3.00 3.30 3.60 V"')),
        **_pins('49', ('VREGOUT', 1.71, 1.89, 'DS_FT2232H.txt:3217 "VREGOUT Voltage regulator Output 1.71 1.80 1.89 V"')),
        **_pins('1 5 11 15 25 35 47 51', ('GND', 0, 0, 'DS_FT2232H.txt pin table: GND')),
        **_pins('10', ('AGND', 0, 0, 'DS_FT2232H.txt:700 "AGND 0V Analog ground"')),
        **_pins('13', ('TEST', 0, 0, 'DS_FT2232H.txt:706 "TEST ... for normal operation should be connected to GND"')),
    },
    'AD9238': {
        **_pins('5 12 17 64', ('AVDD', 2.7, 3.6, 'ad9238.txt:185 "AVDD Full IV 2.7 3.0 3.6 V"')),
        **_pins('29 41 52', ('DRVDD', 2.25, 3.6, 'ad9238.txt:186 "DRVDD Full IV 2.25 3.0 3.6 V"')),
        **_pins('1 4 13 16', ('AGND', 0, 0, 'ad9238.txt pin table: AGND')),
        **_pins('28 40 53', ('DRGND', 0, 0, 'ad9238.txt pin table: DRGND')),
        **_pins('8', ('VREF (output)', 0.95, 1.05, 'ad9238.txt:1525 "If SENSE is grounded ... 1.0 V" (an output; checked only for its rail)')),
        **_pins('9', ('SENSE (grounded: 1 V internal reference)', 0, 0, 'ad9238.txt:580 "SENSE Reference Mode Selection"; :1525')),
        **_pins('22 59', ('OEB (low = outputs on)', -0.3, 0.8, 'ad9238.txt:279 "Low Level Input Voltage 0.8 V"')),
        **_pins('61 62', ('MUX_SELECT / SHARED_REF (high)', 2.0, 3.6, 'ad9238.txt:278 "High Level Input Voltage 2.0 V"; :359 abs max AVDD + 0.3')),
    },
    'AD9767': {
        **_pins('47', ('AVDD', 3.0, 5.5, 'AD9763_9765_9767.txt:254 "AVDD 3 5 5.5 V"')),
        **_pins('16 22', ('DVDD1/DVDD2', 2.7, 5.5, 'AD9763_9765_9767.txt:255 "DVDD1, DVDD2 2.7 5 5.5 V"')),
        **_pins('15 21', ('DCOM1/DCOM2', 0, 0, 'AD9763_9765_9767.txt:692 "DCOM1, DCOM2 Digital Common"')),
        **_pins('38', ('ACOM', 0, 0, 'AD9763_9765_9767.txt:700 "ACOM Analog Common"')),
        **_pins('42', ('GAINCTRL (low)', -0.3, 0.9, 'AD9763_9765_9767.txt:350 "Logic 0 Voltage @ DVDD = 3.3 V 0 0.9 V"; :412 abs')),
    },
    'RTL8211F-CG': {
        **_pins('3 8 38', ('AVDD10', 0.95, 1.05, 'RTL8211F-CG-Datasheet.txt:2515 "AVDD10, DVDD10 0.95 1.0 1.05 V"')),
        **_pins('21', ('DVDD10', 0.95, 1.05, 'RTL8211F-CG-Datasheet.txt:2515 "AVDD10, DVDD10 0.95 1.0 1.05 V"')),
        **_pins('11 40', ('AVDD33', 2.97, 3.63, 'RTL8211F-CG-Datasheet.txt:2514 "DVDD33, AVDD33 2.97 3.3 3.63 V"')),
        **_pins('29', ('DVDD33', 2.97, 3.63, 'RTL8211F-CG-Datasheet.txt:2514 "DVDD33, AVDD33 2.97 3.3 3.63 V"')),
        **_pins('28', ('DVDD_RG (external 3.3 V mode)', 2.97, 3.63,
                       'RTL8211F-CG-Datasheet.txt:618 "DVDD_RG ... External Power mode ... 3.3/2.5/1.8/1.5V"; :574 "CFG_EXT pulled up: '
                       '2\'b00: 3.3V" (straps: R4962 4.7k up, R4972/R4982 4.7k down; check_power_pins.py checks them)')),
        **_pins('30', ('REG_OUT (switch node, to L401)', -0.3, 3.63, 'RTL8211F-CG-Datasheet.txt:2204 "REG_OUT ... connected only to DVDD10 and AVDD10"; :2494 abs 3.6')),
        **_pins('41', ('GND (exposed pad)', 0, 0, 'RTL8211F-CG-Datasheet.txt:624 "41 GND"')),
    },
    'W9825G6KH-6': {
        **_pins('1 14 27', ('VDD', 3.0, 3.6, 'W9825G6KH-6_C62246.txt:647 "Power Supply Voltage VDD 3.0 3.3 3.6 V"')),
        **_pins('3 9 43 49', ('VDDQ', 3.0, 3.6, 'W9825G6KH-6_C62246.txt:648 "I/O Buffer Supply Voltage VDDQ 3.0 3.3 3.6 V"')),
        **_pins('28 41 54', ('VSS', 0, 0, 'W9825G6KH pinout: VSS')),
        **_pins('6 12 46 52', ('VSSQ', 0, 0, 'W9825G6KH pinout: VSSQ')),
        **_pins('40', ('NC', None, None, 'W9825G6KH pinout: NC')),
    },
    'W25Q128JVSIQ': {
        **_pins('8', ('VCC', 2.7, 3.6, 'W25Q128JVSIQ_C97521.txt:3061 "Supply Voltage VCC 2.7 3.0 (104 MHz) / 3.0 3.6 (133 MHz)"')),
        **_pins('4', ('GND', 0, 0, 'W25Q128JV pinout: GND')),
    },
    'Si5351A-B-GTR': {
        **_pins('1', ('VDD (3.3 V option)', 3.0, 3.6, 'SI5351A-B-GTR_C504891.txt:392 "Core Supply Voltage VDD 3.0 3.3 3.60 V"')),
        **_pins('7', ('VDDO (3.3 V option)', 3.0, 3.6, 'SI5351A-B-GTR_C504891.txt:400 "Output Buffer Voltage VDDOx 3.0 3.3 3.60 V"')),
        **_pins('8', ('GND', 0, 0, 'SI5351A-B-GTR_C504891.txt:1498 pin table')),
    },
    'FT5HNBPK25.0-T1': {
        **_pins('4', ('VDD', 3.135, 3.465, 'FT5HNBPK25.0-T1_C5742665.txt:13 "Supply Voltage (VDD) 3.3 VDC+-5%"; drawings/tcxo_p1-1.png "#4 VDD"')),
        **_pins('1 2', ('GND', 0, 0, 'drawings/tcxo_p1-1.png "#1 GND #2 GND"')),
    },
    '93LC56BT-I/OT': {
        **_pins('6', ('VCC', 2.5, 5.5, '93LC56BT-I_OT_C190271.txt:8 "93LC56B 2.5-5.5"')),
        **_pins('2', ('VSS', 0, 0, '93LC56BT-I_OT_C190271.txt:63 SOT-23 "VSS 2"')),
    },
    'PCA9306DC1Z': {
        **_pins('1', ('GND', 0, 0, 'MEMORY (no PCA9306 data sheet on disk): pin 1 GND')),
        **_pins('2', ('VREF1', 0.0, 5.5, 'MEMORY: TI PCA9306 VREF1 0..5.5 V, VREF1 + 0.6 V <= VREF2')),
        **_pins('7', ('VREF2', 0.0, 5.5, 'MEMORY: TI PCA9306 VREF2 0..5.5 V')),
        **_pins('8', ('EN', 0.0, 5.5, 'MEMORY: TI PCA9306 EN = VREF2 through 200k')),
    },
    'USBLC6-2SC6': {
        **_pins('2', ('GND', 0, 0, 'datasheets/USBLC6-2SC6_C2827654.pdf p.1 (image; the txt is empty): "GND 2"')),
        **_pins('5', ('VBUS', 0.0, 5.5, 'datasheets/USBLC6-2SC6_C2827654.pdf p.1 (image): "Operating voltage: 5V"; 5.5 is MEMORY (ST VRWM)')),
    },
    'TLV62569DBVR': {
        **_pins('4', ('VIN', 2.5, 5.5, 'TLV62569DBVR_C141836.txt:244 "VIN Input voltage 2.5 5.5 V"')),
        **_pins('1', ('EN (high)', 1.2, 6.0, 'TLV62569DBVR_C141836.txt:278 "VIH High-level threshold at EN pin ... 1.2 V"; :209 abs 6')),
        **_pins('3', ('SW', -0.3, 5.55, 'TLV62569DBVR_C141836.txt:210 "SW (DC) -0.3 VIN+0.3" (VIN max 5.25)')),
        **_pins('2', ('GND', 0, 0, 'TLV62569DBVR_C141836.txt:189 "GND 2"')),
    },
    'TPS7A2033PDBVR': {
        **_pins('1', ('IN', 1.6, 6.0, 'TPS7A2033PDBVR_C2862740.txt:237 "VIN Input supply voltage 1.6 6.0 V"')),
        **_pins('3', ('EN (high)', 0.9, 6.0, 'TPS7A2033PDBVR_C2862740.txt:383 "VEN(HI) High input threshold 0.9 V"; :238 "VEN 0 6.0 V"')),
        **_pins('5', ('OUT (3.3 V +-1.5 %)', 3.25, 3.35, 'TPS7A2033PDBVR_C2862740.txt:16 "1.5% max accuracy"; :288')),
        **_pins('2', ('GND', 0, 0, 'TPS7A20 DBV pinout: GND 2')),
        **_pins('4', ('NC', None, None, 'TPS7A20 DBV pinout: NC 4')),
    },
    'LP5907MFX-2.5': {
        **_pins('1', ('IN', 2.2, 5.5, 'LP5907MFX-2.5_NOPB_C165132.txt:265 "VIN Input supply voltage 2.2 5.5"')),
        **_pins('3', ('EN (high)', 1.2, 5.5, 'LP5907MFX-2.5_NOPB_C165132.txt:382 "VIH High input threshold 1.2 V"; :267 "VEN 0 5.5"')),
        **_pins('5', ('OUT (2.5 V +-2 %)', 2.45, 2.55, 'LP5907MFX-2.5_NOPB_C165132.txt:313 "Output voltage tolerance -2 2 %VOUT"')),
        **_pins('2', ('GND', 0, 0, 'LP5907 SOT-23-5: GND 2')),
        **_pins('4', ('NC', None, None, 'LP5907 SOT-23-5: NC 4')),
    },
    'LM27761DSGR': {
        **_pins('1', ('VIN', 2.7, 5.5, 'LM27761DSGR_C129351.txt:227 "Operating input voltage, VIN 2.7 5.5 V"; :198 abs 5.8')),
        **_pins('6', ('EN (high)', 1.2, 5.5, 'LM27761DSGR_C129351.txt:269 "VIH Enable pin input voltage high 1.2 V"; :199 abs VIN + 0.3')),
        **_pins('3', ('CPOUT', -5.8, 0.0, 'LM27761DSGR_C129351.txt:173 "CPOUT Negative unregulated output"; :198 "GND to VOUT 5.8 V"')),
        **_pins('4', ('VOUT', -5.0, -1.5, 'LM27761DSGR_C129351.txt:18 "adjustable between -1.5 V and -5 V"')),
        **_pins('2 9', ('GND / thermal pad', 0, 0, 'LM27761DSGR_C129351.txt:172, :181')),
    },
    'SN74LVC1G17DBVR': {
        **_pins('5', ('VCC', 1.65, 5.5, 'SN74LVC1G17DBVR_C7836.txt:220 "VCC Supply voltage Operating 1.65 5.5 V"')),
        **_pins('3', ('GND', 0, 0, 'SN74LVC1G17 DBV pinout: GND 3')),
        **_pins('1', ('NC', None, None, 'SN74LVC1G17 DBV pinout: NC 1')),
    },
    'TLV3501AIDBVR': {
        **_pins('4', ('V+', 2.2, 5.5, 'TLV3501AIDBVR_C193413.txt:222 "VS Supply voltage 2.2 2.7 5.5 V"; :149 "V+ 4"')),
        **_pins('2', ('V- (on GND here)', 0, 0, 'TLV3501AIDBVR_C193413.txt:148 "V- 2"; single supply on this board')),
        **_pins('6', ('SHDN (low = on)', -0.3, 1.53, 'TLV3501AIDBVR_C193413.txt:223 "VIL SHDN (enabled) (V+) - 1.7" (V+ min 3.23)')),
    },
    # Op-amps: the data sheets give a span (V+ - V-); the per-pin ranges here take the other rail at its worst case on
    # this board (+5VA 4.20..5.25, -4V2 -4.16..-4.07) and say so.  check_power_pins.py also checks the span itself.
    'OPA1612': {
        **_pins('8', ("V+", 0.43, 31.8, 'OPA1612IDR_C_TI.txt:260 "Supply voltage (V+ - V-) 4.5 (+-2.25) 36 (+-18) V"; with V- = -4V2')),
        **_pins('4', ('V-', -30.8, -0.3, 'OPA1612IDR_C_TI.txt:260 "(V+ - V-) 4.5 36"; with V+ = +5VA')),
    },
    'OPA2810': {
        **_pins('8', ('V+', 0.69, 22.8, 'OPA2810IDR_C1849413.txt:205 "VS total supply 4.75 27 V"; with V- = -4V2')),
        **_pins('4', ('V-', -21.7, -0.55, 'OPA2810IDR_C1849413.txt:205 "VS 4.75 27 V"; with V+ = +5VA')),
        # inputs tied to ground (U105 both halves, U203B): inside the common-mode range.  'if-tied:' entries are checked
        # only where the pin sits on a rail.
        **_pins('3 5', ('if-tied: +IN', -4.0, 4.0, 'OPA2810IDR_C1849413.txt:16 "rail-to-rail input"; GND is inside V-..V+')),
    },
    'THS4521': {
        **_pins('3', ('VS+', 2.7, 5.4, 'THS4521IDGKR_C170157.txt:372 "VS+ single-supply voltage 2.7 5.0 5.4 V"')),
        **_pins('6', ('VS- (on GND here)', 0, 0, 'THS4521IDGKR_C170157.txt:242 pin table "VS-"; single supply')),
        **_pins('7', ('PD (high = on)', 2.1, 3.6, 'THS4521IDGKR_C170157.txt:505 "Enable voltage threshold Assured on above 2.1 V"')),
    },
}
OPA_SPAN = {
    'OPA1612': ('8', '4', 4.5, 36.0, 'OPA1612IDR_C_TI.txt:260 "Supply voltage (V+ - V-) 4.5 (+-2.25) 36 (+-18) V"'),
    'OPA2810': ('8', '4', 4.75, 27.0, 'OPA2810IDR_C1849413.txt:205 "VS total supply voltage 4.75 27 V"'),
    'THS4521': ('3', '6', 2.7, 5.4, 'THS4521IDGKR_C170157.txt:372 "VS+ single-supply voltage 2.7 5.4 V"'),
    'TLV3501AIDBVR': ('4', '2', 2.2, 5.5, 'TLV3501AIDBVR_C193413.txt:222 "VS Supply voltage 2.2 5.5 V"'),
}

# An internal regulator's output may feed only the pins its data sheet names.
REG_CONSUMERS = {
    ('U502', '49'): ({'VCORE'}, 'DS_FT2232H.txt:669 "VCORE +1.8V input"; :1907 "connect VREGOUT to the pins that require the +1.8V"; '
                                 'VPHY and VPLL are "+3.3V input" (:675, :679)'),
    ('U401', '30'): ({'AVDD10', 'DVDD10'}, 'RTL8211F-CG-Datasheet.txt:2204 "REG_OUT should be connected only to DVDD10 and AVDD10"'),
}

# Straps that decide what a supply pin wants (check_power_pins.py): (ref, pin, want 'high'/'low', why)
STRAPS = [
    ('U401', '32', 'high', 'CFG_EXT: external I/O power on DVDD_RG (RTL8211F-CG-Datasheet.txt:563)'),
    ('U401', '33', 'low', 'CFG_LDO0 = 0: external I/O power is 3.3 V (RTL8211F-CG-Datasheet.txt:574-577 "2\'b00: 3.3V")'),
    ('U401', '34', 'low', 'CFG_LDO1 = 0: external I/O power is 3.3 V'),
]

# ---- pairs ---------------------------------------------------------------------------------------------------------
PASSTHRU = {'USBLC6-2SC6': {'1': '6', '6': '1', '3': '4', '4': '3'}}     # USBLC6-2SC6_C2827654.pdf p.1: I/O1 1-6, I/O2 3-4
SERIES_C = {'C6401', 'C6402', 'C6403', 'C6404', 'C6405', 'C6406', 'C6407', 'C6408', 'C5421'}   # HDMI TMDS 22 nF; CLK IN 10 nF

FPGA = 'U1'
PAIRS = [
    # (label, start (ref, pin), expect (ref, function regex), forbid (ref, function regex))
    ('USB PROG D+ -> FT2232H DP', ('J501', 'A6'), ('U502', r'^DP'), ('U502', r'^DM')),
    ('USB PROG D- -> FT2232H DM', ('J501', 'A7'), ('U502', r'^DM'), ('U502', r'^DP')),
    ('USB PROG D+ (B6) -> FT2232H DP', ('J501', 'B6'), ('U502', r'^DP'), ('U502', r'^DM')),
    ('USB PROG D- (B7) -> FT2232H DM', ('J501', 'B7'), ('U502', r'^DM'), ('U502', r'^DP')),
    ('USB USER D+ -> FPGA G14 (LPF usb_dp)', ('J502', 'A6'), (FPGA, r'G14'), (FPGA, r'G13')),
    ('USB USER D- -> FPGA G13 (LPF usb_dn)', ('J502', 'A7'), (FPGA, r'G13'), (FPGA, r'G14')),
    ('HDMI D0+ -> FPGA J16 (LPF gpdi_d0_p)', ('J503', '8'), (FPGA, r'J16'), (FPGA, r'J15')),
    ('HDMI D0- -> FPGA J15 (LPF gpdi_d0_n)', ('J503', '9'), (FPGA, r'J15'), (FPGA, r'J16')),
    ('HDMI D1+ -> FPGA J14 (LPF gpdi_d1_p)', ('J503', '5'), (FPGA, r'J14'), (FPGA, r'K14')),
    ('HDMI D1- -> FPGA K14 (LPF gpdi_d1_n)', ('J503', '6'), (FPGA, r'K14'), (FPGA, r'J14')),
    ('HDMI D2+ -> FPGA J13 (LPF gpdi_d2_p)', ('J503', '2'), (FPGA, r'J13'), (FPGA, r'J12')),
    ('HDMI D2- -> FPGA J12 (LPF gpdi_d2_n)', ('J503', '3'), (FPGA, r'J12'), (FPGA, r'J13')),
    ('HDMI CK+ -> FPGA K16 (LPF gpdi_ck_p)', ('J503', '11'), (FPGA, r'K16'), (FPGA, r'K15')),
    ('HDMI CK- -> FPGA K15 (LPF gpdi_ck_n)', ('J503', '12'), (FPGA, r'K15'), (FPGA, r'K16')),
    ('ADC A VIN+ <- THS4521 U111 VOUT+ (pin 4)', ('U103', '2'), ('U111', r'^4$'), ('U111', r'^5$')),
    ('ADC A VIN- <- THS4521 U111 VOUT- (pin 5)', ('U103', '3'), ('U111', r'^5$'), ('U111', r'^4$')),
    ('ADC B VIN+ <- THS4521 U112 VOUT+ (pin 4)', ('U103', '15'), ('U112', r'^4$'), ('U112', r'^5$')),
    ('ADC B VIN- <- THS4521 U112 VOUT- (pin 5)', ('U103', '14'), ('U112', r'^5$'), ('U112', r'^4$')),
    ('DAC IOUTA1 -> OPA2810 U202A +IN', ('U201', '46'), ('U202', r'^\+_3'), ('U202', r'^-_2')),
    ('DAC IOUTB1 -> OPA2810 U202A -IN', ('U201', '45'), ('U202', r'^-_2'), ('U202', r'^\+_3')),
    ('DAC IOUTA2 -> OPA2810 U203A +IN', ('U201', '39'), ('U203', r'^\+_3'), ('U203', r'^-_2')),
    ('DAC IOUTB2 -> OPA2810 U203A -IN', ('U201', '40'), ('U203', r'^-_2'), ('U203', r'^\+_3')),
    ('CLK IN SMA -> TLV3501 +IN', ('J301', '1'), ('U302', r'^\+'), None),
]
# Ethernet: the board crosses each pair on both sides of the G2406S (PHY P to TDk-, RJ45 + to MXk-), and the
# transformer's in-phase ends are TDk+ / MXk+ (drawings/g2406-1.png: "Polarity: 2-23, 5-20, 8-17, 11-14 In-Phase"),
# so the PHY's P still reaches the RJ45's + pin.  (1000BASE-T and the RTL8211F also correct pair polarity.)
for _k, (_p, _n, _jp, _jn) in enumerate((('1', '2', '1', '2'), ('4', '5', '3', '6'), ('6', '7', '4', '5'), ('9', '10', '7', '8'))):
    PAIRS += [
        ('Ethernet MDI%d P (U401.%s) -> T401 TD%d-' % (_k, _p, _k + 1), ('U401', _p), ('T401', r'^TD%d-' % (_k + 1)), ('T401', r'^TD%d\+' % (_k + 1))),
        ('Ethernet MDI%d N (U401.%s) -> T401 TD%d+' % (_k, _n, _k + 1), ('U401', _n), ('T401', r'^TD%d\+' % (_k + 1)), ('T401', r'^TD%d-' % (_k + 1))),
        ('Ethernet RJ45 %s (+) -> T401 MX%d-' % (_jp, _k + 1), ('J401', _jp), ('T401', r'^MX%d-' % (_k + 1)), ('T401', r'^MX%d\+' % (_k + 1))),
        ('Ethernet RJ45 %s (-) -> T401 MX%d+' % (_jn, _k + 1), ('J401', _jn), ('T401', r'^MX%d\+' % (_k + 1)), ('T401', r'^MX%d-' % (_k + 1))),
    ]

