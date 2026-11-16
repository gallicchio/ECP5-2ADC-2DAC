#!/usr/bin/env python3
"""host/ecp5bu.py against the RTL: the Board's own byte encoding goes to the simulated board through a file,
sim/tb_file.v runs it in iverilog, and the replies come back the same way.  Reads cannot be waited for inside
one run, so a test is a script: a list of writes, reads and waits, run once; then the replies are checked
in order.  `make test` runs it (a minute or two).  Run from gateware/bringup (or anywhere: paths are absolute).
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import ecp5bu                                                     # noqa: E402
from ecp5bu import REGS, ID                                        # noqa: E402

OSS = os.environ.get('OSS_CAD_SUITE', '/home/jason/mudd/133electronics/icepi-zero-dac-adc/tools/oss-cad-suite')
BUILD = os.path.join(TOP, 'build')
RTL = os.path.join(TOP, 'rtl')


class ScriptTransport(ecp5bu.Transport):
    """Records what the Board sends; `read` hands out a placeholder and remembers how many bytes to expect.
    Registers the script wrote are shadowed, so a method that reads back a setting it wrote (dac_rate) works."""
    def __init__(self):
        self.cmds = []          # ('S', byte) | ('W', ns)
        self.expect = []        # (name, nbytes)
        self.name = '?'
        self.shadow = {}
        self.last_read_reg = None
    def write(self, data):
        for x in data: self.cmds.append(('S', x))
        if len(data) == 5 and data[0] & 0x80:
            self.shadow[data[0] & 0x7F] = struct.unpack('<I', bytes(data[1:5]))[0]
        elif len(data) == 1 and not data[0] & 0x80:
            self.last_read_reg = data[0]
    def read(self, n):
        self.expect.append((self.name, n))
        self.cmds.append(('W', int(n * 10e3 + 30e3)))        # the PC blocks until the reply has arrived: 10 us a byte
        if n == 4 and self.last_read_reg in self.shadow:
            return struct.pack('<I', self.shadow[self.last_read_reg])
        return b'\x00' * n
    def wait(self, seconds):
        self.cmds.append(('W', int(seconds * 1e9)))
    def flush(self): pass


def run(script):
    """script(board, t): issue writes/reads through `board` (a Board on a ScriptTransport), naming each read via t.name.
    Returns the list of (name, bytes) replies in order."""
    t = ScriptTransport()
    b = ecp5bu.Board(transport=t, check=False)
    script(b, t)
    os.makedirs(BUILD, exist_ok=True)
    vvp = os.path.join(BUILD, 'tb_file.vvp')
    rtl = 'top.v uart.v regbus.v cdc.v clkcount.v adc_capture.v dac_gen.v sdram_test.v pll_sys.v periph.v eth_test.v hdmi_test.v'.split()
    if os.path.exists(os.path.join(RTL, 'tmds_enc.v')):
        rtl.append('tmds_enc.v')
    srcs = ([os.path.join(TOP, 'sim', 'tb_file.v')] + [os.path.join(RTL, f) for f in rtl] +
            [os.path.join(TOP, 'sim', f) for f in 'ecp5_sim_models.v models.v models2.v sdram_model.v rgmii_phy_model.v'.split()])
    if not os.path.exists(vvp) or any(os.path.getmtime(f) > os.path.getmtime(vvp) for f in srcs):
        subprocess.check_call([os.path.join(OSS, 'bin', 'iverilog'), '-g2012', '-o', vvp, '-s', 'tb_file'] + srcs)
    with open(os.path.join(RTL, 'cmd.txt'), 'w') as f:
        for k, v in t.cmds:
            f.write('%s %02x\n' % (k, v) if k == 'S' else '%s %d\n' % (k, v))
        f.write('E\n')
    out = subprocess.run([os.path.join(OSS, 'bin', 'vvp'), '-n', vvp], cwd=RTL, capture_output=True, text=True, timeout=1800)
    tail = [l for l in out.stdout.splitlines() if 'VCD' not in l]
    print('\n'.join(tail[-5:]))
    with open(os.path.join(RTL, 'resp.txt')) as f:
        resp = bytes(int(l, 16) for l in f if l.strip())
    replies, pos = [], 0
    for name, n in t.expect:
        replies.append((name, resp[pos:pos + n])); pos += n
    if pos != len(resp):
        print('WARNING: %d reply bytes expected, %d received' % (pos, len(resp)))
    for p in ('cmd.txt', 'resp.txt'):
        os.replace(os.path.join(RTL, p), os.path.join(BUILD, 'cosim_' + p))
    return replies


def u32(b): return struct.unpack('<I', b)[0]


def script(b, t):
    t.name = 'id'; b.rd('ID')
    t.name = 'version'; b.rd('VERSION')
    b.wr('SCRATCH', 0x12345678); t.name = 'scratch'; b.rd('SCRATCH')
    b.leds(0xA5, rgb=0b010); t.name = 'leds'; b.rd('LEDS')
    b.gpio(pdwn_a=1, dcs=0); t.name = 'gpio'; b.rd('GPIO'); b.gpio(pdwn_a=0, dcs=1)
    b.clkout('high'); t.name = 'clkout'; b.rd('CLKOUT')
    # the ADC: 25 MS/s, 32 samples, then a dump
    b.wr('ADC_DIV', 1); b.wr('ADC_DECIM', 0); b.wr('ADC_CTRL', (2 << 4) | (6 << 16)); b.wr('ADC_LEN', 32)
    b.wr('ADC_CTRL', (2 << 4) | (6 << 16) | 1); t.wait(20e-6)
    t.name = 'adc_stat'; b.rd('ADC_STAT')
    b.wr('DUMP_LEN', 32); t.name = 'dump'; b.t.write(bytes([REGS['DUMP']])); b.t.read(4 * 32)
    # the DACs through the Board's own methods
    b.dac_config(rate=25e6); b.dac(1, 'sine', freq=1.5625e6); b.dac(2, 'dc', code=1000)
    t.name = 'dac1_ctrl'; b.rd('DAC1_CTRL'); t.name = 'dac1_inc'; b.rd('DAC1_INC'); t.name = 'dac2_dc'; b.rd('DAC2_DC')
    # the frequency counters after two gates (1 ms each here)
    t.wait(2.5e-3)
    for r in ('F_TCXO', 'F_EXT', 'F_SI0', 'F_SI1', 'F_SI2', 'F_RXC', 'F_S'):
        t.name = r; b.rd(r)
    # the SDRAM tester: 128 words at latency 4
    t.wait(300e-6)
    t.name = 'sdram_stat0'; b.rd('SDRAM_STAT')
    b.wr('SDRAM_LEN', 128); b.wr('SDRAM_CTRL', (3 << 8) | 1); t.wait(120e-6)
    t.name = 'sdram_stat'; b.rd('SDRAM_STAT'); t.name = 'sdram_err'; b.rd('SDRAM_ERR'); t.name = 'sdram_words'; b.rd('SDRAM_WORDS')
    # I2C through the Board's bit-bang: write two Si5351 registers and read them back
    t.name = 'bb'                        # every STATUS read from here on is the bit-bang's
    b.i2c_write(0x60, 16, [0x4F, 0x6F])
    b.i2c_read(0x60, 16, 2)             # the Board's method does the reads; the acks and data are STATUS reads
    # MDIO: the PHY ID
    b.mdio_read(1, 2); b.mdio_read(1, 3)


def main():
    replies = run(script)
    fails = 0
    def check(what, ok):
        nonlocal fails
        print(('  ok: ' if ok else 'FAIL: ') + what)
        if not ok: fails += 1
    d = {}
    status_reads = []
    for name, data in replies:
        if name == 'bb':
            status_reads.append(data)          # the bit-bang's STATUS reads
        elif name not in d:
            d[name] = data
    check('ID', u32(d['id']) == ID)
    check('VERSION', u32(d['version']) == 0x20261105)
    check('SCRATCH', u32(d['scratch']) == 0x12345678)
    check('LEDS register as leds() wrote it', u32(d['leds']) == (0xA5 | 0x200))
    check('GPIO as gpio() wrote it', u32(d['gpio']) == (ecp5bu.GPIO_DEFAULT | 1 << ecp5bu.G_PDWN_A) & ~(1 << ecp5bu.G_DCS))
    check('CLKOUT high', u32(d['clkout']) == ecp5bu.CLKOUT['high'])
    st = u32(d['adc_stat']); check('ADC capture done, 32 samples', st & 3 == 2 and st >> 16 == 32)
    import numpy as np
    w = np.frombuffer(d['dump'], dtype='<u4'); a = w & 0xFFF; bb = (w >> 16) & 0xFFF
    check('dump: channel B ramp steps by 1', all(((bb[i + 1] - bb[i]) & 0xFFF) == 1 for i in range(31)))
    model = lambda k: int(round(2048.0 + 1800.0 * np.sin(2 * np.pi * k / 32))) & 0xFFF   # Verilog real -> reg rounds
    k0 = [k for k in range(32) if model(k) == a[0] and model(k + 1) == a[1]]
    check('dump: channel A follows the sine model', bool(k0) and all(a[i] == model(k0[0] + i) for i in range(32)))
    check('DAC1_CTRL sine', u32(d['dac1_ctrl']) == 1)
    check('DAC1_INC for 1.5625 MHz at 25 MS/s = 2^28', u32(d['dac1_inc']) == 1 << 28)
    check('DAC2_DC 1000', u32(d['dac2_dc']) == 1000)
    f = {r: u32(d[r]) for r in ('F_TCXO', 'F_EXT', 'F_SI0', 'F_SI1', 'F_SI2', 'F_RXC', 'F_S')}
    check('frequency counters (1 ms gate): %s' % f, f['F_TCXO'] == 25000 and abs(f['F_EXT'] - 10000) <= 1 and abs(f['F_SI0'] - 1000) <= 1
          and abs(f['F_SI1'] - 100) <= 1 and f['F_SI2'] == 0 and abs(f['F_RXC'] - 125000) <= 1 and abs(f['F_S'] - 50000) <= 1)
    check('SDRAM initialised', u32(d['sdram_stat0']) & 1 == 1)
    check('SDRAM test done, 0 errors, 256 words', u32(d['sdram_stat']) & 6 == 4 and u32(d['sdram_err']) == 0 and u32(d['sdram_words']) == 256)
    # the bit-bang replies: every STATUS read in order.  i2c_write: 4 acks; i2c_read: 2 acks + 1 ack + 16 data bits + ...
    # Simplest check: replay the STATUS bits against the Board's own decoding by running the methods on a replay transport.
    class Replay(ecp5bu.Transport):
        def __init__(self, reads): self.reads = list(reads)
        def write(self, data): pass
        def read(self, n): return self.reads.pop(0)
    rb = ecp5bu.Board(transport=Replay(status_reads), check=False)
    ok_w = rb.i2c_write(0x60, 16, [0x4F, 0x6F])
    got = rb.i2c_read(0x60, 16, 2)
    check('I2C write acked and the two registers read back (%s)' % got, ok_w and got == [0x4F, 0x6F])
    id1, id2 = rb.mdio_read(1, 2), rb.mdio_read(1, 3)
    check('MDIO PHY ID %04x %04x' % (id1, id2), (id1, id2) == (0x001C, 0xC916))
    print('%s: %d failures' % ('PASS' if fails == 0 else 'FAIL', fails))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
