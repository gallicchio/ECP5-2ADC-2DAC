#!/usr/bin/env python3
"""The ECP5-2ADC-2DAC bring-up gateware (rtl/top.v) from the PC, over the FT2232H's channel B.

    from ecp5bu import Board
    with Board() as b:                       # channel B found under /dev/serial/by-id, 1 Mbaud; or Board('/dev/ttyUSB3')
        b.ident()                            # the ID and version registers, or an IOError
        b.leds(0x55)                         # LED0-7 from the register; b.leds(None) hands them back to the chaser
        b.clocks()                           # {'tcxo': 25000000, 'clk_in': ..., 'si0': ..., ...} in Hz, one second old
        b.dac(1, 'sine', freq=1e6)           # DAC 1: a full-scale 1 MHz sine; b.dac(1, 'dc', code=8192) for 0 V
        t, a, b_, otr = b.capture(4096)      # both ADC channels, 4096 samples, as numpy arrays of codes
        b.adc_stats()                        # min, max, mean of each channel over the running window
        b.si5351_set(0, 10e6)                # Si5351 CLK0 = 10 MHz (I2C bit-banged through the GPIO register)
        b.phy_id()                           # the RTL8211F's ID over MDIO: (0x001C, 0xC916)
        b.sdram_test(words=1 << 16)          # the memory tester; {'errors': 0, ...}

    python3 ecp5bu.py [/dev/...] ident | leds 0x55 | clocks | dac 1 sine 1e6 | capture 1024 | stats | sdram 65536 | phy | si 0 10e6

The protocol (rtl/regbus.v): one command byte, bit 7 = write, bits 6:0 = the register; a write carries
4 data bytes least-significant first and gets no answer; a read is answered with 4 bytes; a read of 0x7F
streams DUMP_LEN words of the capture memory.  The register map is REGS below, the same as rtl/top.v's.
Nothing here needs the PLL: the UART runs on the TCXO.
"""
import struct
import sys
import time
from fractions import Fraction

try:
    import serial
except ImportError:
    serial = None

DEFAULT_PORT = 'auto'               # the FT2232H's channel B, found by its USB name; or a /dev path


def find_port(pattern='/dev/serial/by-id/usb-FTDI_Dual_RS232-HS*-if01*'):
    """The FT2232H's channel B (interface 1) by its name under /dev/serial/by-id; a blank EEPROM enumerates as
    "Dual RS232-HS".  Never guesses a bare ttyUSBn: the bench's RS-232 adapters are ttyUSBs too, and a byte at
    1 Mbaud into a power supply is not what anyone wants."""
    import glob
    hits = sorted(glob.glob(pattern))
    if not hits:
        raise IOError('no FT2232H channel B under /dev/serial/by-id (%s): is USB PROG plugged in?  '
                      'A programmed EEPROM changes the name: pass the port explicitly' % pattern)
    return hits[0]
BAUD = 1_000_000
ID = 0xEC5BA2D2
F_TCXO = 25e6
F_S = 50e6                          # the PLL clock the converters run from

REGS = dict(
    ID=0x00, VERSION=0x01, SCRATCH=0x02, CONTROL=0x03, STATUS=0x04, LEDS=0x05, GPIO=0x06, PMOD=0x07, CLKOUT=0x08,
    F_TCXO=0x10, F_EXT=0x11, F_SI0=0x12, F_SI1=0x13, F_SI2=0x14, F_RXC=0x15, F_S=0x16, FREQSEQ=0x17,
    ADC_CTRL=0x20, ADC_DIV=0x21, ADC_DECIM=0x22, ADC_LEN=0x23, ADC_STAT=0x24, STATSEQ=0x25,
    A_MINMAX=0x26, A_SUM=0x27, B_MINMAX=0x28, B_SUM=0x29, OTR_N=0x2A,
    DAC1_CTRL=0x30, DAC1_INC=0x31, DAC1_DC=0x32, DAC2_CTRL=0x33, DAC2_INC=0x34, DAC2_DC=0x35, DAC_DIV=0x36,
    SDRAM_CTRL=0x40, SDRAM_LEN=0x41, SDRAM_STAT=0x42, SDRAM_ERR=0x43, SDRAM_ERR_ADDR=0x44, SDRAM_ERR_DATA=0x45, SDRAM_WORDS=0x46,
    DUMP_LEN=0x7E, DUMP=0x7F)
CLOCKS = ['tcxo', 'clk_in', 'si0', 'si1', 'si2', 'rxc', 'clk_s']
DAC_MODES = {'dc': 0, 'sine': 1, 'saw': 2, 'square': 3, 'triangle': 4}
CLKOUT = {'tcxo': 0, 'clk_s': 1, 'adc': 2, 'dac': 3, 'clk_in': 4, 'si0': 5, 'si1': 6, 'si2': 7, 'rxc': 8,
          '1hz': 9, 'low': 10, 'high': 11, 'tcxo/2': 12, 'pll_lock': 13}
# GPIO register bits (rtl/top.v) and the power-up value
G_ETH_RST_N, G_MDC, G_MDIO_O, G_MDIO_OE, G_SCL, G_SDA, G_PDWN_A, G_PDWN_B, G_DCS, G_DFS, G_DAC_MODE, G_DAC_SLEEP, G_USB_PULLUP = range(13)
GPIO_DEFAULT = 0b0_0101_0011_0101
S_PLL_LOCK, S_BTN0, S_BTN1, S_ETH_INT_N, S_RTS, S_DTR, S_OTR_A, S_OTR_B, S_SDA, S_SCL, S_MDIO, S_ACT = range(12)


class Transport:
    """What the Board needs from a link: write bytes, read exactly n bytes (or raise), discard what is pending."""
    def write(self, data): raise NotImplementedError
    def read(self, n): raise NotImplementedError
    def flush(self): pass
    def close(self): pass


class SerialTransport(Transport):
    def __init__(self, port=DEFAULT_PORT, baud=BAUD, timeout=1.0):
        if serial is None:
            raise ImportError('pyserial is needed: pip install pyserial (or apt install python3-serial)')
        if port in (None, 'auto'):
            port = find_port()
        self.port = port
        self.s = serial.Serial(port, baud, timeout=timeout, write_timeout=1.0)
        self.s.setDTR(False)                      # DTR/RTS are FPGA inputs (STATUS bits); leave them idle high
        self.s.setRTS(False)
        time.sleep(0.05)
        self.flush()

    def write(self, data): self.s.write(data)
    def read(self, n):
        d = self.s.read(n)
        if len(d) != n:
            raise IOError('board: wanted %d bytes, got %d (is the bringup bitstream loaded? ttyUSB1 = channel B?)' % (n, len(d)))
        return d
    def flush(self):
        self.s.reset_input_buffer()
    def close(self): self.s.close()


def _pack_w(reg, val): return bytes([0x80 | reg]) + struct.pack('<I', val & 0xFFFFFFFF)
def _pack_r(reg): return bytes([reg & 0x7F])


class Board:
    def __init__(self, port=DEFAULT_PORT, transport=None, check=True):
        self.t = transport or SerialTransport(port)
        self._gpio = GPIO_DEFAULT
        if check:
            self.resync()
            self.ident()
            self._gpio = self.rd('GPIO')

    def close(self): self.t.close()
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

    # -- the bus ---------------------------------------------------------------------------------
    def wr(self, reg, val):
        self.t.write(_pack_w(REGS[reg] if isinstance(reg, str) else reg, val))

    def rd(self, reg):
        self.t.write(_pack_r(REGS[reg] if isinstance(reg, str) else reg))
        return struct.unpack('<I', self.t.read(4))[0]

    def resync(self):
        """Five 0x00 bytes complete any half-sent write and read the ID up to five times; drop the replies."""
        self.t.write(b'\x00' * 5)
        time.sleep(0.05)
        self.t.flush()

    def ident(self):
        i = self.rd('ID')
        if i != ID:
            raise IOError('board: ID register reads %08x, not %08x' % (i, ID))
        return {'id': i, 'version': '%08x' % self.rd('VERSION')}

    def status(self):
        s = self.rd('STATUS')
        names = ['pll_lock', 'btn0', 'btn1', 'eth_int_n', 'ftdi_rts', 'ftdi_dtr', 'otr_a', 'otr_b', 'sda', 'scl', 'mdio', 'bus_active']
        return {n: bool(s >> i & 1) for i, n in enumerate(names)}

    def scratch_test(self, n=20):
        """Write random words and read them back: the bus itself."""
        import random
        for _ in range(n):
            v = random.getrandbits(32)
            self.wr('SCRATCH', v)
            got = self.rd('SCRATCH')
            if got != v:
                raise IOError('scratch: wrote %08x read %08x' % (v, got))
        return n

    # -- LEDs, GPIO, Pmods, CLK OUT -------------------------------------------------------------------
    def leds(self, value=None, rgb=0):
        """LED0-7 from `value` (bits), RGB from `rgb` (bit 0 red, 1 green, 2 blue); None gives them back to the chaser."""
        ctl = self.rd('CONTROL')
        if value is None:
            self.wr('CONTROL', ctl & ~1)
        else:
            self.wr('LEDS', (value & 0xFF) | ((rgb & 7) << 8))
            self.wr('CONTROL', ctl | 1)

    def gpio(self, **bits):
        """Set GPIO bits by name: eth_rst_n, mdc, mdio_o, mdio_oe, scl, sda, pdwn_a, pdwn_b, dcs, dfs, dac_mode, dac_sleep, usb_pullup."""
        names = ['eth_rst_n', 'mdc', 'mdio_o', 'mdio_oe', 'scl', 'sda', 'pdwn_a', 'pdwn_b', 'dcs', 'dfs', 'dac_mode', 'dac_sleep', 'usb_pullup']
        g = self._gpio
        for k, v in bits.items():
            i = names.index(k)
            g = (g | (1 << i)) if v else (g & ~(1 << i))
        if g != self._gpio or not bits:
            self._gpio = g
            self.wr('GPIO', g)
        return {n: bool(g >> i & 1) for i, n in enumerate(names)}

    def pmod(self, a=None, b=None, mode_a=None, mode_b=None):
        """Pmod pins: a/b = 8-bit output values; mode 0 inputs, 1 register, 2 counter.  Returns the pins read."""
        cur = self.rd('PMOD')
        va = cur & 0xFF if a is None else a & 0xFF
        vb = (cur >> 8) & 0xFF if b is None else b & 0xFF
        ma = (cur >> 16) & 3 if mode_a is None else mode_a
        mb = (cur >> 18) & 3 if mode_b is None else mode_b
        self.wr('PMOD', va | (vb << 8) | (ma << 16) | (mb << 18))
        r = self.rd('PMOD')
        return {'a': r & 0xFF, 'b': (r >> 8) & 0xFF}

    def clkout(self, what='tcxo'):
        """What the CLK OUT SMA carries: a key of CLKOUT."""
        self.wr('CLKOUT', CLKOUT[what] if isinstance(what, str) else what)

    # -- the frequency counters -------------------------------------------------------------------------
    def clocks(self, wait=True):
        """Every clock input's frequency in Hz (a 1 s gate; 'tcxo' reads 25000000 by construction).
        wait=True blocks until a fresh gate has passed (up to 2.2 s), so the numbers are current."""
        seq0 = self.rd('FREQSEQ')
        if wait:
            t0 = time.time()
            while self.rd('FREQSEQ') & 0xF == seq0 & 0xF and time.time() - t0 < 2.5:
                time.sleep(0.05)
        while True:
            s1 = self.rd('FREQSEQ')
            vals = [self.rd(0x10 + i) for i in range(7)]
            s2 = self.rd('FREQSEQ')
            if s1 == s2:
                break
        out = dict(zip(CLOCKS, vals))
        alive = [(s1 >> (4 * i)) & 0xF != (seq0 >> (4 * i)) & 0xF for i in range(7)]
        for i, n in enumerate(CLOCKS):
            if not alive[i] and wait:
                out[n] = 0            # no gate was acknowledged: that clock is not running
        return out

    # -- the ADC --------------------------------------------------------------------------------------
    def adc_config(self, rate=None, div=None, phase=2, negedge=False, decim=0, stats_log2=16):
        """The ADC clock: `rate` in S/s (50e6 direct, else F_S / (2 div)), or `div` directly.  Returns the rate."""
        if div is None:
            div = 0 if rate is None or rate >= F_S else max(1, round(F_S / (2 * rate)))
        self.wr('ADC_DIV', div)
        self.wr('ADC_DECIM', decim)
        self.wr('ADC_CTRL', ((phase & 7) << 4) | (int(negedge) << 8) | ((stats_log2 & 31) << 16))
        self.gpio(dcs=(div == 0 or F_S / (2 * div) >= 20e6))   # the duty-cycle stabiliser only above 20 MS/s
        return F_S if div == 0 else F_S / (2 * div)

    def adc_rate(self):
        div = self.rd('ADC_DIV')
        return F_S if div == 0 else F_S / (2 * div)

    def capture(self, n=4096, timeout=5.0):
        """Capture n samples (<= 8192) of both channels.  Returns (t, a, b, otr): seconds, codes 0..4095
        (offset binary; 2048 is 0 V in), out-of-range flags as (a, b) bit arrays."""
        import numpy as np
        n = min(max(1, n), 8192)
        decim = self.rd('ADC_DECIM')
        ctl = self.rd('ADC_CTRL') & ~1
        self.wr('ADC_LEN', n)
        self.wr('ADC_CTRL', ctl | 1)
        time.sleep(0.002)                        # `done` is the last capture's until the arm has crossed into clk_s
        t0 = time.time()
        while True:
            s = self.rd('ADC_STAT')
            if s & 2 and not s & 1:
                break
            if time.time() - t0 > timeout:
                raise IOError('capture: not done after %.1f s (ADC_STAT %08x): is the PLL locked?' % (timeout, s))
        self.wr('DUMP_LEN', n)
        self.t.write(_pack_r(REGS['DUMP']))
        raw = self.t.read(4 * n)
        w = np.frombuffer(raw, dtype='<u4')
        a = (w & 0xFFF).astype(np.int32); b = ((w >> 16) & 0xFFF).astype(np.int32)
        otr = (((w >> 12) & 1).astype(np.uint8), ((w >> 28) & 1).astype(np.uint8))
        fs = self.adc_rate() / (decim + 1)
        return np.arange(n) / fs, a, b, otr

    def adc_stats(self):
        """min, max, mean (codes) and out-of-range count of each channel over the last statistics window."""
        while True:
            s1 = self.rd('STATSEQ')
            am, asum, bm, bsum, otr = (self.rd(r) for r in ('A_MINMAX', 'A_SUM', 'B_MINMAX', 'B_SUM', 'OTR_N'))
            s2 = self.rd('STATSEQ')
            if s1 == s2:
                break
        n = 1 << ((self.rd('ADC_CTRL') >> 16) & 31)
        return {'a': {'min': am & 0xFFF, 'max': am >> 16, 'mean': asum / n, 'otr': otr & 0xFFFF},
                'b': {'min': bm & 0xFFF, 'max': bm >> 16, 'mean': bsum / n, 'otr': otr >> 16}, 'n': n, 'seq': s1}

    # -- the DACs ---------------------------------------------------------------------------------------
    def dac_config(self, rate=None, div=None, pol=1):
        """Both DACs' clock: `rate` in S/s (50e6 direct, else F_S / (2 div)).  Returns the rate."""
        if div is None:
            div = 0 if rate is None or rate >= F_S else max(1, round(F_S / (2 * rate)))
        self.wr('DAC_DIV', div | (int(pol) << 16))
        return F_S if div == 0 else F_S / (2 * div)

    def dac_rate(self):
        div = self.rd('DAC_DIV') & 0xFFFF
        return F_S if div == 0 else F_S / (2 * div)

    def dac(self, port, mode='sine', freq=1e6, shift=0, code=None, offset=0):
        """One DAC port (1 or 2).  mode: dc (code 0..16383; 8192 is 0 V, 16383 is +2 V open / +1 V into 50 ohm),
        sine, saw, square, triangle at `freq` Hz, amplitude / 2^shift, plus `offset` codes.  Returns the exact frequency."""
        base = {1: 'DAC1_CTRL', 2: 'DAC2_CTRL'}[port]
        r = REGS[base]
        fs = self.dac_rate()
        inc = int(round(freq / fs * 2 ** 32)) & 0xFFFFFFFF
        m = DAC_MODES[mode]
        self.wr(r + 1, inc)
        self.wr(r + 2, (code if m == 0 and code is not None else offset) & 0xFFFF)
        self.wr(r, m | ((shift & 15) << 4))
        return inc / 2 ** 32 * fs

    def dac_sleep(self, asleep=True): self.gpio(dac_sleep=asleep)

    # -- bit-banged buses: I2C to the Si5351, MDIO to the PHY -----------------------------------------------
    def _scl(self, v): self.gpio(scl=v)
    def _sda(self, v): self.gpio(sda=v)
    def _sda_in(self): return bool(self.rd('STATUS') >> S_SDA & 1)

    def i2c_start(self): self._sda(1); self._scl(1); self._sda(0); self._scl(0)
    def i2c_stop(self): self._sda(0); self._scl(1); self._sda(1)
    def i2c_write_byte(self, b):
        for i in range(7, -1, -1):
            self._sda(b >> i & 1); self._scl(1); self._scl(0)
        self._sda(1); self._scl(1); ack = not self._sda_in(); self._scl(0)
        return ack
    def i2c_read_byte(self, last):
        self._sda(1); b = 0
        for i in range(7, -1, -1):
            self._scl(1); b |= int(self._sda_in()) << i; self._scl(0)
        self._sda(1 if last else 0); self._scl(1); self._scl(0); self._sda(1)
        return b
    def i2c_write(self, addr, reg, data):
        """Write bytes `data` to register `reg` (auto-incrementing) of 7-bit address `addr`.  False if NACKed."""
        self.i2c_start()
        ok = self.i2c_write_byte(addr << 1) and self.i2c_write_byte(reg)
        for d in (data if ok else []):
            ok = self.i2c_write_byte(d) and ok
        self.i2c_stop()
        return ok
    def i2c_read(self, addr, reg, n=1):
        self.i2c_start()
        ok = self.i2c_write_byte(addr << 1) and self.i2c_write_byte(reg)
        if not ok:
            self.i2c_stop(); return None
        self.i2c_start()
        if not self.i2c_write_byte(addr << 1 | 1):
            self.i2c_stop(); return None
        out = [self.i2c_read_byte(i == n - 1) for i in range(n)]
        self.i2c_stop()
        return out
    def i2c_scan(self):
        found = []
        for a in range(0x08, 0x78):
            self.i2c_start(); ok = self.i2c_write_byte(a << 1); self.i2c_stop()
            if ok: found.append(a)
        return found

    def si5351_set(self, clk, freq, drive_ma=2):
        """Program Si5351 output `clk` (0-2) to `freq` Hz from its 25 MHz crystal: PLLA for CLK0/1, PLLB for CLK2.
        Even integer output dividers 6..900 with an integer-mode PLL where it can; a fractional PLL otherwise.
        Returns the frequency actually set."""
        from si5351 import plan, registers
        p = plan(25e6, freq)
        regs = registers(clk, p, drive_ma=drive_ma)
        if self.i2c_read(0x60, 0, 1) is None:
            raise IOError('Si5351 at 0x60 does not answer')
        self.i2c_write(0x60, 3, [0xFF])                         # all outputs off while reprogramming
        for r, v in sorted(regs.items()):
            self.i2c_write(0x60, r, [v])
        self.i2c_write(0x60, 177, [0xA0])                       # reset both PLLs
        oeb = self.i2c_read(0x60, 3, 1)[0]
        self.i2c_write(0x60, 3, [oeb & ~(1 << clk) & 0xFF])     # this output on
        return p['f_out']

    def si5351_status(self):
        s = self.i2c_read(0x60, 0, 1)
        if s is None: return None
        s = s[0]
        return {'sys_init': bool(s & 0x80), 'lol_b': bool(s & 0x40), 'lol_a': bool(s & 0x20), 'los_xtal': bool(s & 0x08), 'raw': s}

    def _mdio_bit(self, v):
        self.gpio(mdio_o=v, mdio_oe=1, mdc=0); self.gpio(mdc=1)
    def _mdio_clock(self):
        self.gpio(mdc=0); self.gpio(mdc=1)
    def mdio_read(self, phy, reg):
        for _ in range(32): self._mdio_bit(1)
        for b in (0, 1, 1, 0): self._mdio_bit(b)
        for i in range(4, -1, -1): self._mdio_bit(phy >> i & 1)
        for i in range(4, -1, -1): self._mdio_bit(reg >> i & 1)
        self.gpio(mdio_oe=0, mdc=0); self.gpio(mdc=1)             # turnaround: released, two clocks
        self._mdio_clock()
        d = 0
        for i in range(15, -1, -1):
            self.gpio(mdc=0)
            d |= int(self.rd('STATUS') >> S_MDIO & 1) << i
            self.gpio(mdc=1)
        self.gpio(mdc=0)
        return d
    def mdio_write(self, phy, reg, value):
        for _ in range(32): self._mdio_bit(1)
        for b in (0, 1, 0, 1): self._mdio_bit(b)
        for i in range(4, -1, -1): self._mdio_bit(phy >> i & 1)
        for i in range(4, -1, -1): self._mdio_bit(reg >> i & 1)
        self._mdio_bit(1); self._mdio_bit(0)
        for i in range(15, -1, -1): self._mdio_bit(value >> i & 1)
        self.gpio(mdio_oe=0, mdc=0)
    def phy_id(self, phy=1):
        """(PHYID1, PHYID2): the RTL8211F answers (0x001C, 0xC916).  The board straps PHYAD = 1."""
        return self.mdio_read(phy, 2), self.mdio_read(phy, 3)
    def phy_status(self, phy=1):
        s = self.mdio_read(phy, 1); r = self.mdio_read(phy, 26)   # BMSR; RTL8211F PHYSR (page 0xa43 reg 26 on some; here reg 26 = PHYSR of page 0)
        return {'link': bool(s & 4), 'autoneg_done': bool(s & 0x20), 'bmsr': s, 'physr': r}

    # -- the SDRAM ----------------------------------------------------------------------------------------
    def sdram_test(self, words=1 << 16, pattern=0, rdlat=3, pol=0, timeout=60.0):
        """Write `words` 16-bit words (<= 2^24 = all 32 MB), read them back, count the mismatches.
        rdlat is the read latency in 50 MHz cycles (3 in simulation; sdram_scan finds the board's); the whole array takes about 5 s."""
        if not self.rd('SDRAM_STAT') & 1:
            raise IOError('SDRAM not initialised (no PLL?)')
        self.wr('SDRAM_LEN', words)
        self.wr('SDRAM_CTRL', (pattern << 4) | (rdlat << 8) | (pol << 12) | 1)
        time.sleep(0.002)                        # `done` is the last test's until the start has crossed into clk_s
        t0 = time.time()
        while True:
            s = self.rd('SDRAM_STAT')
            if s & 4 and not s & 2:
                break
            if time.time() - t0 > timeout:
                self.wr('SDRAM_CTRL', (pattern << 4) | (rdlat << 8) | (pol << 12) | 2)
                raise IOError('SDRAM test not done after %.0f s' % timeout)
            time.sleep(0.05)
        r = {'words': words, 'pattern': pattern, 'rdlat': rdlat, 'errors': self.rd('SDRAM_ERR'),
             'words_done': self.rd('SDRAM_WORDS'), 'seconds': time.time() - t0}
        if r['errors']:
            d = self.rd('SDRAM_ERR_DATA')
            r.update(first_addr=self.rd('SDRAM_ERR_ADDR'), first_expected=d >> 16, first_got=d & 0xFFFF)
        return r

    def sdram_scan(self, words=4096):
        """Every read latency 1..7: the one(s) with 0 errors are the data-valid window."""
        return {lat: self.sdram_test(words, rdlat=lat)['errors'] for lat in range(1, 8)}


def main(argv):
    args = list(argv)
    port = DEFAULT_PORT
    if args and args[0].startswith('/dev/'):
        port = args.pop(0)
    if not args:
        print(__doc__); return 2
    cmd = args.pop(0)
    with Board(port) as b:
        if cmd == 'ident':
            print(b.ident()); print(b.status())
        elif cmd == 'leds':
            b.leds(None if not args or args[0] == 'chaser' else int(args[0], 0))
        elif cmd == 'clocks':
            for k, v in b.clocks().items(): print('%-7s %12.0f Hz' % (k, v))
        elif cmd == 'dac':
            port_, mode = int(args[0]), args[1]
            if mode == 'dc': print(b.dac(port_, 'dc', code=int(args[2], 0)))
            else: print('%.3f Hz' % b.dac(port_, mode, float(args[2]) if len(args) > 2 else 1e6))
        elif cmd == 'capture':
            n = int(args[0]) if args else 1024
            t, a, bb, otr = b.capture(n)
            print('rate %.0f S/s; A mean %.1f std %.2f min %d max %d; B mean %.1f std %.2f min %d max %d; OTR %d %d'
                  % (b.adc_rate(), a.mean(), a.std(), a.min(), a.max(), bb.mean(), bb.std(), bb.min(), bb.max(), otr[0].sum(), otr[1].sum()))
        elif cmd == 'stats':
            print(b.adc_stats())
        elif cmd == 'sdram':
            print(b.sdram_scan() if args and args[0] == 'scan' else b.sdram_test(int(args[0]) if args else 1 << 16))
        elif cmd == 'phy':
            print('PHY ID %04x %04x' % b.phy_id()); print(b.phy_status())
        elif cmd == 'si':
            print('%.3f Hz' % b.si5351_set(int(args[0]), float(args[1]))); print(b.si5351_status())
        elif cmd == 'i2cscan':
            print(['0x%02x' % a for a in b.i2c_scan()])
        elif cmd == 'clkout':
            b.clkout(args[0])
        else:
            print(__doc__); return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
