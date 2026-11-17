#!/usr/bin/env python3
"""Every pair and every chip-to-FPGA line of ECP5-2ADC-2DAC, from the connector or the chip to its far end, by pin
function; then the sign of each analog chain and the logic levels between chips.

    python3 tools/check_pairs.py [-v]            # exit 1 on any FAIL

The CLAUDE_PCB.md check "Pair polarity, connector to chip" (its top block; section 10, gate 2b-2c), written
2026-11-16 after board A's USB PROG turned out to have D+ and D- swapped at the FT2232H (bringup/REVB.md row 13).

1. PAIRS (tools/pin_tables.py): each line walked from its start through resistors, inductors, beads, the listed
   series capacitors and the ESD arrays' pass-through pins (PASSTHRU), stopping at rails.  FAIL unless the expected
   pin is reached and the forbidden one (the other half of the pair) is not.
2. Every IC pin that reaches an FPGA ball through at most 1 kohm: the ball's port name in the LPF
   (gateware/ecp5_2adc_2dac.lpf) against the IC pin's function (RULES: TXD2 -> eth_txd[2], DQ7 -> sdram_dq[7], ...).
   A bus bit, a TX/RX, a TDI/TDO or a MOSI/MISO crossed between the schematic and the LPF fails here.  The
   sysCONFIG and JTAG balls are also checked against Lattice's pinout CSV.
3. The analog chains' signs, from the netlist's own parts (SIGN): which pin each stage's signal enters, which
   resistors set its gain, and the sign that results.
4. Levels: each IC that drives or receives an FPGA ball, its I/O rail against the FPGA bank's (all LVCMOS33 at +3V3);
   each FPGA ball reaching a connector or a pull-up, the most that can arrive there against the ECP5's 3.63 V.
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from audit_netlist import load                     # noqa: E402
from check_power_pins import rail_of, ohms        # noqa: E402
import pin_tables as T                             # noqa: E402

FPGA = 'U1'
ECP5_ABS = 3.63          # LFE5U-25F-6BG256C_C1521614.txt:3033 "Input or I/O Transient Voltage Applied -0.5 3.63 V"


def fn_of(pins, ref, pin):
    return re.sub(r'_\d+$', '', pins[ref][pin][0]) or 'pin:' + pin


def walk(start, comps, pins, nets, max_r=None):
    """(ends, path) from start: IC/connector/transformer pins reached through series parts and pass-through pins."""
    seen, ends, path = set(), [], []
    todo = [pins[start[0]][start[1]][2]]
    while todo:
        net = todo.pop()
        if net in seen or net in T.RAILS:
            continue
        seen.add(net); path.append(net)
        for ref, pin, fn, ty in nets[net]:
            if (ref, pin) == start:
                continue
            pt = T.PASSTHRU.get(comps[ref][0])
            if pt and pin in pt:
                todo.append(pins[ref][pt[pin]][2])
            elif len(pins[ref]) == 2 and (ref.startswith(('R', 'L', 'FB')) or ref in T.SERIES_C):
                if max_r is not None and ref.startswith('R') and (ohms(comps[ref][0]) or 1e9) > max_r:
                    continue
                todo.append(pins[ref][[p for p in pins[ref] if p != pin][0]][2])
            elif not ref.startswith(('C', 'D', 'TP', 'JP', 'H')) and not (len(pins[ref]) == 2 and ref.startswith(('R', 'L', 'FB'))):
                ends.append((ref, pin, re.sub(r'_[A-Z]?\d+$', '', fn) if ref != FPGA else pin))
    return ends, path


def lpf_ports():
    site = {}
    for line in open(os.path.join(ROOT, 'gateware', 'ecp5_2adc_2dac.lpf')):
        m = re.match(r'\s*LOCATE COMP "([^"]+)" SITE "([^"]+)"', line)
        if m:
            site[m.group(2)] = m.group(1)
    return site


def lattice_csv():
    rows = list(csv.reader(open(os.path.join(ROOT, 'datasheets', 'FPGA-SC-02033-2-0-ECP5U-25-Pinout.csv'))))
    hdr = next(i for i, r in enumerate(rows) if r and r[0] == 'PAD')
    col = rows[hdr].index('CABGA256')
    return {r[col]: (r[1], r[2], r[3]) for r in rows[hdr + 1:] if len(r) > col and r[col] not in ('', '-')}


# IC pin function -> the LPF port it must land on (\1 etc. from the function's match)
RULES = {
    'RTL8211F-CG': [(r'^TXD(\d)', r'eth_txd[\1]'), (r'^RXD(\d)', r'eth_rxd[\1]'), (r'^TXCTL$', 'eth_tx_ctl'), (r'^TXC$', 'eth_txc'),
                    (r'^RXCTL', 'eth_rx_ctl'), (r'^RXC', 'eth_rxc'), (r'^MDC$', 'eth_mdc'), (r'^MDIO$', 'eth_mdio'),
                    (r'^INTB', 'eth_int_n'), (r'^PHYRSTB', 'eth_rst_n')],
    'AD9238': [(r'^D(\d+)_A$', r'adc_a_d[\1]'), (r'^D(\d+)_B$', r'adc_b_d[\1]'), (r'^OTR_A', 'adc_a_otr'), (r'^OTR_B', 'adc_b_otr'),
               (r'^CLK_A', 'adc_a_clk'), (r'^CLK_B', 'adc_b_clk'), (r'^DCS', 'adc_dcs'), (r'^DFS', 'adc_dfs'),
               (r'^PDWN_A', 'adc_pdwn_a'), (r'^PDWN_B', 'adc_pdwn_b')],
    'AD9767': [(r'^DB(\d+)P1$', r'dac_p1_d[\1]'), (r'^DB(\d+)P2$', r'dac_p2_d[\1]'), (r'^WRT1', 'dac_wrt1'), (r'^CLK1', 'dac_clk1'),
               (r'^CLK2', 'dac_clk2'), (r'^WRT2', 'dac_wrt2'), (r'^SLEEP', 'dac_sleep'), (r'^MODE', 'dac_mode')],
    'W9825G6KH-6': [(r'^DQ(\d+)$', r'sdram_dq[\1]'), (r'^A(\d+)$', r'sdram_a[\1]'), (r'^BA(\d)$', r'sdram_ba[\1]'),
                    (r'^DQML$', 'sdram_dqml'), (r'^DQMH$', 'sdram_dqmh'), (r'WE', 'sdram_we_n'), (r'CAS', 'sdram_cas_n'),
                    (r'RAS', 'sdram_ras_n'), (r'CS', 'sdram_cs_n'), (r'^CKE$', 'sdram_cke'), (r'^CLK$', 'sdram_clk')],
    'W25Q128JVSIQ': [(r'CS', 'flash_cs_n'), (r'^CLK$', 'flash_sck'), (r'^DI/IO0', 'flash_io[0]'), (r'^DO/IO1', 'flash_io[1]'),
                     (r'WP', 'flash_io[2]'), (r'HOLD', 'flash_io[3]')],
    # FT2232H MPSSE on channel A: ADBUS0 TCK out, ADBUS1 TDI out (to the target's TDI), ADBUS2 TDO in, ADBUS3 TMS out
    # (DS_FT2232H.txt MPSSE pin table); channel B UART: BDBUS0 TXD out -> FPGA rx, BDBUS1 RXD in <- FPGA tx
    'FT2232HL': [(r'^ADBUS0', 'jtag_tck'), (r'^ADBUS1', 'jtag_tdi'), (r'^ADBUS2', 'jtag_tdo'), (r'^ADBUS3', 'jtag_tms'),
                 (r'^BDBUS0', 'uart_rx'), (r'^BDBUS1', 'uart_tx'), (r'^BDBUS2', 'ftdi_rts'), (r'^BDBUS4', 'ftdi_dtr')],
    'Si5351A-B-GTR': [(r'^SCL', 'i2c_scl'), (r'^SDA', 'i2c_sda'), (r'^CLK(\d)', r'clk_si\1')],
    'PCA9306DC1Z': [(r'^SCL1', 'gpdi_scl'), (r'^SDA1', 'gpdi_sda')],
    'FT5HNBPK25.0-T1': [(r'^OUT', 'clk_tcxo')],
    'TLV3501AIDBVR': [(r'^pin:5$', 'clk_ext')],
    'SN74LVC1G17DBVR': [(r'^pin:2$', 'clk_out')],
}
# The LPF ports on dedicated balls, against Lattice's CSV (function or dual function)
DEDICATED = {'jtag_tck': 'TCK', 'jtag_tdi': 'TDI', 'jtag_tdo': 'TDO', 'jtag_tms': 'TMS', 'flash_sck': 'CCLK|SCK',
             'flash_io[0]': 'MOSI', 'flash_io[1]': 'MISO', 'flash_io[2]': 'IO2', 'flash_io[3]': 'IO3', 'flash_cs_n': 'CSSPIN',
             'done': 'DONE', 'initn': 'INITN', 'programn': 'PROGRAMN', 'cfg0': 'CFG_0', 'cfg1': 'CFG_1', 'cfg2': 'CFG_2'}
# The I/O rail of each part that drives or receives an FPGA ball, and why
IO_RAIL = {
    'AD9238': ('29', 'DRVDD drives the data (ad9238.txt:186); its inputs (CLK, DFS, DCS, PDWN) take up to AVDD + 0.3 V (:359)'),
    'AD9767': ('16', 'DVDD1 (AD9763_9765_9767.txt:255); logic 1 >= 2.1 V at 3.3 V (:348); inputs up to DVDD + 0.3 V (:406)'),
    'W9825G6KH-6': ('3', 'VDDQ (W9825G6KH-6_C62246.txt:648)'),
    'W25Q128JVSIQ': ('8', 'VCC (W25Q128JVSIQ_C97521.txt:3061)'),
    'RTL8211F-CG': ('28', 'DVDD_RG, external 3.3 V I/O (RTL8211F-CG-Datasheet.txt:618, the CFG straps)'),
    'FT2232HL': ('20', 'VCCIO (DS_FT2232H.txt:3213; its I/O are 5 V tolerant)'),
    'Si5351A-B-GTR': ('7', 'VDDO for the clocks, VDD for I2C (SI5351A-B-GTR_C504891.txt:392, :400)'),
    'PCA9306DC1Z': ('2', 'VREF1 side (MEMORY)'),
    'FT5HNBPK25.0-T1': ('4', 'VDD; VOH >= 80 % VDD (FT5HNBPK25.0-T1_C5742665.txt:25)'),
    'TLV3501AIDBVR': ('4', 'V+ (rail-to-rail output)'),
    'SN74LVC1G17DBVR': ('5', 'VCC; inputs 5.5 V tolerant (SN74LVC1G17DBVR_C7836.txt:223)'),
}
# What can arrive on a connector pin from outside (connector, pin): (most volts, why)
EXTERNAL = {
    ('J503', '19'): (5.3, 'HDMI HPD from the sink: high 2.4-5.3 V through about 1 kohm in the sink, from our own +5V pin (MEMORY: HDMI 1.4a 4.2.9)'),
    ('J503', '14'): (3.63, 'HDMI CEC: 3.3 V bus, max 3.63 V (MEMORY: HDMI 1.4a supplement 1)'),
}


def main(argv):
    verbose = '-v' in argv
    comps, pins, nets = load()
    site, latt = lpf_ports(), lattice_csv()
    rows, fails = [], 0

    def add(ok, sec, a, b, c):
        nonlocal fails
        rows.append(('pass' if ok is True else ('FAIL' if ok is False else ok), sec, a, b, c))
        fails += ok is False

    # ---- 1. pairs -------------------------------------------------------------------------------------------------
    for label, start, expect, forbid in T.PAIRS:
        ends, path = walk(start, comps, pins, nets)
        hit = [e for e in ends if e[0] == expect[0] and (re.search(expect[1], pins[e[0]][e[1]][0] or '') or re.search(expect[1], e[1]))]
        bad = [e for e in ends if forbid and e[0] == forbid[0] and (re.search(forbid[1], pins[e[0]][e[1]][0] or '') or re.search(forbid[1], e[1]))]
        add(bool(hit) and not bad, 'pair', label,
            'reaches ' + ', '.join('%s.%s(%s)' % e for e in ends),
            ('FORBIDDEN %s; ' % ['%s.%s(%s)' % e for e in bad] if bad else '') + ('' if hit else 'expected %s %s not reached; ' % expect)
            + 'path ' + ' -> '.join(path))

    # ---- 2. chip pins against the LPF port at the ball they reach ------------------------------------------------
    n_lines = 0
    for ref in sorted(comps):
        rules = RULES.get(comps[ref][0])
        if not rules:
            continue
        for pin in sorted(pins[ref], key=lambda p: (len(p), p)):
            if pins[ref][pin][2] in T.RAILS:
                continue
            ends, _ = walk((ref, pin), comps, pins, nets, max_r=1000)
            balls = [e[1] for e in ends if e[0] == FPGA]
            if not balls:
                continue
            f = fn_of(pins, ref, pin)
            want = None
            for rx, port in rules:
                m = re.search(rx, f)
                if m:
                    want = m.expand(port)
                    break
            got = [site.get(b, '(no LPF port)') for b in balls]
            n_lines += 1
            if want is None:
                add('info', 'lpf', '%s.%s %s' % (ref, pin, f), 'FPGA %s = %s' % ('/'.join(balls), '/'.join(got)), 'no rule for this pin')
            else:
                add(want in got, 'lpf', '%s.%s %s' % (ref, pin, f), 'FPGA %s = %s' % ('/'.join(balls), '/'.join(got)), 'want %s' % want)
    for port, func in DEDICATED.items():
        ball = next((b for b, p in site.items() if p == port), None)
        if ball is None:
            add('info', 'csv', port, 'not in the LPF', '')
            continue
        f, bank, dual = latt.get(ball, ('?', '?', '?'))
        add(bool(re.search(func, f + ' ' + dual)), 'csv', '%s at %s' % (port, ball), 'Lattice: %s / %s (bank %s)' % (f, dual, bank),
            'want %s' % func)

    # ---- 3. analog signs ------------------------------------------------------------------------------------------
    def net(ref, pin):
        return pins[ref][pin][2]

    def joins(r, a, b):
        """resistor/jumper r joins nets a and b"""
        ns = {v[2] for v in pins[r].values()}
        return {a, b} <= ns

    def val(r):
        return ohms(comps[r][0])

    def chain(name, facts, sign_note):
        ok = all(f[0] for f in facts)
        add(ok, 'sign', name, ('sign +, ' if ok else 'BROKEN: ') + sign_note,
            '; '.join(('' if f[0] else 'NOT ') + f[1] for f in facts))

    for ch, sma, opa, fda, adc_p, adc_n, rs in (('A', 'J101', 'U101', 'U111', '2', '3', ('R1103', 'R1104', 'R1105', 'R1106', 'R1107', 'R1108', 'R1109', 'R1110', 'R1112', 'R1111')),
                                                 ('B', 'J102', 'U102', 'U112', '15', '14', ('R1203', 'R1204', 'R1205', 'R1206', 'R1207', 'R1208', 'R1209', 'R1210', 'R1212', 'R1211'))):
        r_fb1, r_g1, r_fb2, r_g2, r_in, r_gn, r_fbp, r_fbn, r_outp, r_outn = rs
        jp = 'JP102' if ch == 'A' else 'JP202'
        _, path = walk((sma, '1'), comps, pins, nets, max_r=200)
        facts = [
            (net(jp, '3') in path and net(jp, '2') == net(opa, '3'),
             'SMA %s reaches %s pin 3 (B) through <= 200 ohm; the SRC jumper\'s SMA position joins B (3) to C (2), which is %s +INA (pin 3)'
             % (sma, jp, opa)),
            (joins(r_fb1, net(opa, '1'), net(opa, '2')) and net(r_g1, '1') in (net(opa, '2'), 'GND') and 'GND' in {v[2] for v in pins[r_g1].values()},
             '%s stage A non-inverting: %s from OUTA to -INA, %s to GND (gain 1 + %g/%g)' % (opa, r_fb1, r_g1, val(r_fb1), val(r_g1))),
            (net(opa, '1') == net(opa, '5'), '%s OUTA drives +INB (pin 5) directly' % opa),
            (joins(r_fb2, net(opa, '7'), net(opa, '6')) and 'GND' in {v[2] for v in pins[r_g2].values()},
             '%s stage B non-inverting: %s OUTB to -INB, %s to GND' % (opa, r_fb2, r_g2)),
            (joins(r_in, net(opa, '7'), net(fda, '8')), '%s OUTB -> %s -> %s VIN+ (pin 8)' % (opa, r_in, fda)),
            (joins(r_fbp, net(fda, '5'), net(fda, '8')), '%s feedback %s from VOUT- (pin 5) to VIN+ (pin 8)' % (fda, r_fbp)),
            (joins(r_fbn, net(fda, '4'), net(fda, '1')) and joins(r_gn, net(fda, '1'), 'GND'),
             '%s feedback %s from VOUT+ (pin 4) to VIN- (pin 1); %s from VIN- to GND' % (fda, r_fbn, r_gn)),
            (val(r_in) == val(r_gn) and val(r_fbp) == val(r_fbn), 'FDA balanced: Rg %s = %s, Rf %s = %s' % (r_in, r_gn, r_fbp, r_fbn)),
            (joins(r_outp, net(fda, '4'), net('U103', adc_p)) and joins(r_outn, net(fda, '5'), net('U103', adc_n)),
             '%s VOUT+ -> %s -> AD9238 VIN+_%s; VOUT- -> %s -> VIN-_%s' % (fda, r_outp, ch, r_outn, ch)),
        ]
        chain('ADC %s: SMA %s to AD9238' % (ch, sma), facts,
              'VOUT+ - VOUT- = +(Rf/Rg) x V(%s OUTB): a positive input raises VIN+_%s (THS4521IDGKR_C170157.txt:240-244)' % (opa, ch))
    for port, ioa, iob, opa, sma, ra_in, ra_g, rb_in, rb_f, rout in (('1', '46', '45', 'U202', 'J204', 'R2403', 'R2405', 'R2404', 'R2406', 'R2407'),
                                                                     ('2', '39', '40', 'U203', 'J205', 'R2503', 'R2505', 'R2504', 'R2506', 'R2507')):
        facts = [
            (joins(ra_in, net('U201', ioa), net(opa, '3')) and joins(ra_g, net(opa, '3'), 'GND'),
             'IOUTA%s -> %s -> %s +INA, %s to GND' % (port, ra_in, opa, ra_g)),
            (joins(rb_in, net('U201', iob), net(opa, '2')) and joins(rb_f, net(opa, '1'), net(opa, '2')),
             'IOUTB%s -> %s -> %s -INA, %s from OUTA' % (port, rb_in, opa, rb_f)),
            (abs(val(ra_g) / val(ra_in) - val(rb_f) / val(rb_in)) < 1e-6, 'difference amplifier balanced: %s/%s = %s/%s' % (ra_g, ra_in, rb_f, rb_in)),
            (joins(rout, net(opa, '1'), net(sma, '1')), '%s OUTA -> %s -> SMA %s' % (opa, rout, sma)),
        ]
        chain('DAC %s: AD9767 to SMA %s' % (port, sma), facts,
              'Vout = (%s/%s)(V(IOUTA) - V(IOUTB)); IOUTA rises with the code (AD9763_9765_9767.txt, IOUTA = code/16384 x IOUTFS)' % (rb_f, rb_in))
    ends, _ = walk(('J301', '1'), comps, pins, nets, max_r=1000)
    chain('CLK IN: SMA J301 to TLV3501 to the FPGA', [
        (any(e[0] == 'U302' and e[1] == '3' for e in ends), 'J301 -> C5421 -> R5427 -> TLV3501 +IN (pin 3)'),
        (joins('R5426', net('U302', '3'), net('U302', '1')) and joins('R5424', net('U302', '1'), '+3V3_ADC') and joins('R5425', net('U302', '1'), 'GND'),
         '-IN (pin 1) is the divider R5424/R5425 from +3V3_ADC (1.65 V); R5426 10k biases +IN to it'),
        (site.get(next((e[1] for e in walk(('U302', '5'), comps, pins, nets, max_r=100)[0] if e[0] == FPGA), '')) == 'clk_ext',
         'OUT (pin 5) -> R5423 -> the FPGA ball the LPF calls clk_ext')], 'non-inverting comparator')

    # ---- 4. levels ---------------------------------------------------------------------------------------------------
    fpga_rail = T.RAILS['+3V3']
    for ref in sorted(comps):
        io = IO_RAIL.get(comps[ref][0])
        if not io:
            continue
        rn, rng, _ = rail_of(pins[ref][io[0]][2], comps, pins, nets)
        reach = any(any(e[0] == FPGA for e in walk((ref, p), comps, pins, nets, max_r=1000)[0])
                    for p in pins[ref] if pins[ref][p][2] not in T.RAILS)
        if not reach:
            continue
        ok = rng is not None and 2.97 <= rng[0] and rng[1] <= 3.465
        add(ok, 'level', '%s %s I/O rail %s' % (ref, comps[ref][0], rn), '%s..%s V against FPGA LVCMOS33 %s..%s V' % (rng[0], rng[1], *fpga_rail), io[1])
    for ball in sorted(pins[FPGA]):
        n = pins[FPGA][ball][2]
        if n in T.RAILS:
            continue
        for r, p, fn, ty in nets[n]:
            if r.startswith('R') and len(pins[r]) == 2:
                other = pins[r][[q for q in pins[r] if q != p][0]][2]
                if other in T.RAILS and T.RAILS[other][1] > ECP5_ABS:
                    add(False, 'level', 'FPGA %s (%s) pulled up by %s %s' % (ball, site.get(ball), r, comps[r][0]),
                        'to %s (%s V)' % (other, T.RAILS[other][1]), 'above the ECP5 I/O maximum %.2f V' % ECP5_ABS)
        ends, path = walk((FPGA, ball), comps, pins, nets, max_r=10000)
        for e in ends:
            ext = EXTERNAL.get((e[0], e[1]))
            if ext:
                volts, why = ext
                rser, rdown = 0.0, []
                for nn in path:
                    for r, p, fn, ty in nets[nn]:
                        if r.startswith('R') and len(pins[r]) == 2:
                            other = pins[r][[q for q in pins[r] if q != p][0]][2]
                            if other == 'GND' and nn == n:
                                rdown.append(ohms(comps[r][0]))
                            elif other in path:
                                rser += ohms(comps[r][0]) / 2          # each series resistor is seen from both of its nets
                if rdown:
                    rd = 1 / sum(1 / x for x in rdown)
                    vpin = volts * rd / (rd + rser + 1000)             # + the sink's own 1 kohm
                    why += '; divider %g ohm series + 1k in the sink, %g ohm down: %.2f V at the ball' % (rser, rd, vpin)
                    volts = vpin
                rser = ['%g ohm series' % rser]
                add(volts <= ECP5_ABS or 'MEDIUM', 'level', 'FPGA %s (%s) <- %s.%s %s' % (ball, site.get(ball), e[0], e[1], e[2]),
                    'up to %.2f V at the ball (%s)' % (volts, rser[0]),
                    why + ('' if volts <= ECP5_ABS else '; the ECP5 abs max is %.2f V: the bank clamp (LFE5U-25F:3131, 18 mA at VCCIO+0.5 V) carries it' % ECP5_ABS))

    for r in rows:
        if r[0] != 'pass' or verbose:
            print('%-6s %-5s %-46s %-50s %s' % r)
    print('\n%d pair lines, %d chip-to-FPGA lines, %d sign chains, %d level rows; %d FAIL, %d other flags'
          % (len(T.PAIRS), n_lines, sum(1 for r in rows if r[1] == 'sign'), sum(1 for r in rows if r[1] == 'level'), fails,
             sum(1 for r in rows if r[0] not in ('pass', 'FAIL', 'info'))))
    print('RESULT: %s' % ('FAIL' if fails else 'PASS'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
