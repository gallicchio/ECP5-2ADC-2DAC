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

    python3 ecp5bu.py [/dev/...] ident | leds 0x55 | clocks | dac 1 sine 1e6 | capture 1024 | stats | sdram 65536 | phy | si 0 10e6 | gpio usb_pullup=1

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
    USB=0x09, USB_EDGES=0x0A, USB_TIME=0x0B, SD=0x0C, HDMI=0x0E,
    ETH_CTRL=0x50, ETH_TXLEN=0x51, ETH_TXCNT=0x52, ETH_TXDATA=0x53, ETH_RXADDR=0x54, ETH_RXDATA=0x55,
    ETH_TXN=0x56, ETH_RXN=0x57, ETH_RXGOOD=0x58, ETH_RXBAD=0x59,
    DUMP_LEN=0x7E, DUMP=0x7F)
V2 = 0x20261115                     # the first version with the USB, SD, HDMI and ETH registers
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
    # Time as the board lives it.  On the bench these are the PC's clock; a simulated board (sim/cosim.py)
    # advances its own time instead, so the same procedures run against the RTL.
    # (its sleep() shortens every wait by one factor and its time() runs that much faster, so timeouts keep
    # their meaning).
    def sleep(self, seconds): time.sleep(seconds)
    def time(self): return time.time()
    gate_s = 1.0                    # the frequency counters' gate in the board's own seconds (a simulation's is 1 ms)


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
        try:                                      # the FTDI's latency timer to 1 ms instead of 16 (no root needed)
            self.s.set_low_latency_mode(True)
        except Exception:
            pass
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
        self.version = None
        if check:
            self.resync()
            self.version = int(self.ident()['version'], 16)
            self._gpio = self.rd('GPIO')

    def wait(self, seconds):
        """Wait `seconds` of bench time (a simulated board shortens it: Transport.sleep)."""
        self.t.sleep(seconds)

    def need_v2(self):
        if self.version is None:
            self.version = self.rd('VERSION')
        if self.version < V2:
            raise IOError('this needs the bring-up bitstream of 2026-11-15 or later (the board runs %08x): load build/bringup.bit' % self.version)

    def close(self): self.t.close()
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

    # -- the bus ---------------------------------------------------------------------------------
    def wr(self, reg, val):
        self.t.write(_pack_w(REGS[reg] if isinstance(reg, str) else reg, val))

    def rd(self, reg):
        self.t.write(_pack_r(REGS[reg] if isinstance(reg, str) else reg))
        return struct.unpack('<I', self.t.read(4))[0]

    def rd_many(self, regs):
        """Several registers in one round trip: every read command goes out in one write (the bus queues up to 64
        bytes), then all the replies come back together.  The board answers them back to back, 40 us apart at 1 Mbaud."""
        codes = [REGS[r] if isinstance(r, str) else r for r in regs]
        self.t.write(bytes(c & 0x7F for c in codes))
        raw = self.t.read(4 * len(codes))
        return list(struct.unpack('<%dI' % len(codes), raw))

    def resync(self):
        """Five 0x00 bytes complete any half-sent write and read the ID up to five times; drop the replies."""
        self.t.write(b'\x00' * 5)
        self.t.sleep(0.05)
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
        # Read-modify-write from the register itself, not from a copy: on board A (2026-11-16) a stale copy wrote
        # 0x03d2, which powered both ADCs down and held the PHY in reset (the register reads back what was written).
        self._gpio = self.rd('GPIO') & 0x1FFF
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
    def clocks(self, wait=True, gates=1):
        """Every clock input's frequency in Hz (a 1 s gate; 'tcxo' reads 25000000 by construction).
        wait=True blocks until `gates` fresh gates have passed (1.1 s each), so the numbers are current.  After a
        clock has been switched or started, ask for gates=2: the first gate after the change straddles it."""
        seq0 = self.rd('FREQSEQ')
        if wait:
            t0 = self.t.time()
            while (self.rd('FREQSEQ') - seq0) & 0xF < gates and self.t.time() - t0 < 1.3 * gates + 1.2:
                self.t.sleep(0.05)
        while True:
            s1 = self.rd('FREQSEQ')
            vals = [self.rd(0x10 + i) for i in range(7)]
            s2 = self.rd('FREQSEQ')
            if s1 == s2:
                break
        out = dict(zip(CLOCKS, [int(round(v / self.t.gate_s)) for v in vals]))
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
        self.t.sleep(0.002)                        # `done` is the last capture's until the arm has crossed into clk_s
        t0 = self.t.time()
        while True:
            s = self.rd('ADC_STAT')
            if s & 2 and not s & 1:
                break
            if self.t.time() - t0 > timeout:
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
        # One window, all from the same one: the sequence number before and after must agree.  The reads go out in one
        # write (rd_many), because one USB round trip per register (1-16 ms) is far longer than a short window; on
        # board A (2026-11-16) the old one-read-at-a-time loop never saw two equal numbers with a 164 us window and hung.
        for _ in range(200):
            s1, am, asum, bm, bsum, otr, s2, ctl = self.rd_many(('STATSEQ', 'A_MINMAX', 'A_SUM', 'B_MINMAX', 'B_SUM', 'OTR_N', 'STATSEQ', 'ADC_CTRL'))
            if s1 == s2:
                break
        else:
            raise IOError('adc_stats: the statistics window changed during every read: make the window longer (stats_log2)')
        n = 1 << ((ctl >> 16) & 31)
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
    # Two buses share these routines: 'si' (the Si5351's, through the GPIO register) and 'ddc' (the HDMI jack's,
    # through the HDMI register's bits 4 and 5; a monitor's EDID is at address 0x50 on it).
    _bus = 'si'
    _ddc = 0x30
    def _use_bus(self, bus):
        self._bus = bus
        if bus == 'ddc':
            self._ddc = self.rd('HDMI') & 0x3F | 0x30
    def _scl(self, v):
        if self._bus == 'ddc':
            self._ddc = (self._ddc & ~0x10) | (0x10 if v else 0); self.wr('HDMI', self._ddc)
        else: self.gpio(scl=v)
    def _sda(self, v):
        if self._bus == 'ddc':
            self._ddc = (self._ddc & ~0x20) | (0x20 if v else 0); self.wr('HDMI', self._ddc)
        else: self.gpio(sda=v)
    def _sda_in(self):
        if self._bus == 'ddc': return bool(self.rd('HDMI') >> 10 & 1)
        return bool(self.rd('STATUS') >> S_SDA & 1)

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
    def i2c_write(self, addr, reg, data, bus='si'):
        """Write bytes `data` to register `reg` (auto-incrementing) of 7-bit address `addr`.  False if NACKed."""
        self._use_bus(bus)
        self.i2c_start()
        ok = self.i2c_write_byte(addr << 1) and self.i2c_write_byte(reg)
        for d in (data if ok else []):
            ok = self.i2c_write_byte(d) and ok
        self.i2c_stop()
        return ok
    def i2c_read(self, addr, reg, n=1, bus='si'):
        self._use_bus(bus)
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
    def i2c_scan(self, bus='si'):
        self._use_bus(bus)
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
        oeb = self.i2c_read(0x60, 3, 1)[0]                      # which outputs are on now (a 1 is "off"): read BEFORE switching all off
        self.i2c_write(0x60, 3, [0xFF])                         # all outputs off while reprogramming
        for r, v in sorted(regs.items()):
            self.i2c_write(0x60, r, [v])
        self.i2c_write(0x60, 177, [0xA0])                       # reset both PLLs
        self.i2c_write(0x60, 3, [oeb & ~(1 << clk) & 0xFF])     # the other outputs as they were, this output on
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
    def mdio_page(self, phy, page, reg):
        """An RTL8211F register on another page: register 31 selects the page (0xa42 is the default one)."""
        self.mdio_write(phy, 31, page)
        v = self.mdio_read(phy, reg)
        self.mdio_write(phy, 31, 0xa42)
        return v
    def phy_status(self, phy=1):
        """Link, speed and duplex as the PHY has them now (BMSR's link bit latches low: read twice; PHYSR is
        page 0xa43 register 26: bits 5:4 speed, 3 duplex, 2 link in real time)."""
        self.mdio_read(phy, 1); s = self.mdio_read(phy, 1)
        r = self.mdio_page(phy, 0xa43, 26)
        return {'link': bool(s & 4), 'autoneg_done': bool(s & 0x20), 'bmsr': s, 'physr': r,
                'speed': {0: 10, 1: 100, 2: 1000}.get(r >> 4 & 3), 'full_duplex': bool(r & 8), 'link_now': bool(r & 4)}
    def phy_straps(self, phy=1):
        """The RGMII delays the PHY took from its straps at reset (page 0xd08: register 0x11 bit 8 is the transmit
        delay, register 0x15 bit 3 the receive delay).  The board straps both on."""
        return {'txdly': bool(self.mdio_page(phy, 0xd08, 0x11) & 0x100), 'rxdly': bool(self.mdio_page(phy, 0xd08, 0x15) & 0x008)}
    def phy_loopback(self, on=True, phy=1):
        """The PHY's PCS loopback at 1000 Mb/s (BMCR 0x4140: loopback, gigabit, full duplex, no auto-negotiation):
        what the FPGA sends on TXD comes back on RXD, with no cable.  on=False restores auto-negotiation (0x1340)."""
        self.mdio_write(phy, 0, 0x4140 if on else 0x1340)
        return self.mdio_read(phy, 0)

    # -- the SDRAM ----------------------------------------------------------------------------------------
    def sdram_test(self, words=1 << 16, pattern=0, rdlat=3, pol=1, timeout=60.0):
        """Write `words` 16-bit words (<= 2^24 = all 32 MB), read them back, count the mismatches.
        rdlat is the read latency in 50 MHz cycles (3 in simulation; sdram_scan finds the board's); the whole array takes about 5 s."""
        if not self.rd('SDRAM_STAT') & 1:
            raise IOError('SDRAM not initialised (no PLL?)')
        self.wr('SDRAM_LEN', words)
        self.wr('SDRAM_CTRL', (pattern << 4) | (rdlat << 8) | (pol << 12) | 1)
        self.t.sleep(0.002)                        # `done` is the last test's until the start has crossed into clk_s
        t0 = self.t.time()
        while True:
            s = self.rd('SDRAM_STAT')
            if s & 4 and not s & 2:
                break
            if self.t.time() - t0 > timeout:
                self.wr('SDRAM_CTRL', (pattern << 4) | (rdlat << 8) | (pol << 12) | 2)
                raise IOError('SDRAM test not done after %.0f s' % timeout)
            self.t.sleep(0.05)
        r = {'words': words, 'pattern': pattern, 'rdlat': rdlat, 'errors': self.rd('SDRAM_ERR'),
             'words_done': self.rd('SDRAM_WORDS'), 'seconds': self.t.time() - t0}
        if r['errors']:
            d = self.rd('SDRAM_ERR_DATA')
            r.update(first_addr=self.rd('SDRAM_ERR_ADDR'), first_expected=d >> 16, first_got=d & 0xFFFF)
        return r

    def sdram_scan(self, words=4096, pol=1):
        """Every read latency 1..7: the one(s) with 0 errors are the data-valid window.
        pol=1 (the SDRAM clock inverted) is board A's setting: with pol=0 its rising edge meets the command lines as
        they change, and whole-array tests failed part way through (2026-11-16, ECP5 REVB 19)."""
        return {lat: self.sdram_test(words, rdlat=lat, pol=pol)['errors'] for lat in range(1, 8)}


    # -- 2026-11-15: USB USER, microSD, HDMI, the RGMII data path, the Pmod loop, the buttons ------------------
    def usb_lines(self):
        """The USB USER lines as the FPGA sees them, what it drives, and the counters since the last clear."""
        self.need_v2()
        r, e, t = self.rd('USB'), self.rd('USB_EDGES'), self.rd('USB_TIME')
        return {'dp': bool(r >> 16 & 1), 'dn': bool(r >> 17 & 1), 'drive_dp': bool(r & 1), 'drive_dn': bool(r & 4),
                'pullup': bool(self._gpio >> G_USB_PULLUP & 1),
                'dp_edges': e & 0xFFFF, 'dn_edges': e >> 16, 'se0_ms': t & 0xFFFF, 'j_ms': t >> 16}

    def usb_drive(self, dp=None, dn=None, clear=False):
        """Drive D+ and/or D- to a level (0 or 1), or release them (None).  clear=True zeroes the counters."""
        self.need_v2()
        v = (0 if dp is None else 1 | (int(bool(dp)) << 1)) | (0 if dn is None else 4 | (int(bool(dn)) << 3))
        self.wr('USB', v | (0x100 if clear else 0))

    def usb_attach(self, how='fs', seconds=1.5):
        """Look like a device to whatever host the USB USER cable goes to, for `seconds`, and say what the lines
        did.  how: 'fs' = the board's 1.5 k pull-up on D+ (a full-speed device); 'ls' = D- driven high (what a
        low-speed device looks like: tests that output); 'dp' = D+ driven high by the FPGA pin itself.
        A host answers an attach with a bus reset (both lines low, 10 ms or more) and then packets, which nothing
        here answers: so se0_ms > 0 and edges on both lines mean both inputs, the pull-up or the output, the
        connector and the cable are right.  With no host both lines just follow what is driven."""
        self.need_v2()
        self.gpio(usb_pullup=0); self.usb_drive(clear=True)
        self.wait(0.05)
        before = self.usb_lines()
        if how == 'fs': self.gpio(usb_pullup=1)
        elif how == 'ls': self.usb_drive(dn=1)
        elif how == 'dp': self.usb_drive(dp=1)
        else: raise ValueError(how)
        self.wait(0.002)
        self.wr('USB', (self.rd('USB') & 0xF) | 0x100)       # zero the counters with the line held: a detached port
        held = self.usb_lines()                              # with a host's pull-downs is SE0 too, and must not count
        self.wait(seconds)
        after = self.usb_lines()
        self.gpio(usb_pullup=0); self.usb_drive()
        self.wait(0.05)
        idle = self.usb_lines()
        line = 'dn' if how == 'ls' else 'dp'
        return {'how': how, 'before': before, 'held': held, 'after': after, 'released': idle,
                'line_went_high': held[line], 'line_fell_when_released': not idle[line],
                'host_reset_seen': after['se0_ms'] > 0, 'host_packets_seen': after['dp_edges'] > 2 and after['dn_edges'] > 2}

    def spi_xfer(self, byte=0xFF, cs=0, div=32):
        """One byte to the microSD socket in SPI mode and the byte that came back.  cs is the chip select's level
        (DAT3); div the SCK half period in 40 ns steps (32 = 390 kHz for the card's initialisation; 4 = 3.1 MHz)."""
        self.wr('SD', (byte & 0xFF) | 0x100 | (int(bool(cs)) << 9) | ((div & 0xFF) << 16))
        for _ in range(50):
            r = self.rd('SD')
            if not r & 0x100:
                return r & 0xFF
        raise IOError('SD: the SPI byte engine stays busy')

    def sd_pins(self):
        """The socket's pins as levels: DAT0-3 and CMD (with no card and the pull-ups, all high)."""
        self.need_v2()
        r = self.rd('SD')
        return {'dat0': r >> 16 & 1, 'dat1': r >> 17 & 1, 'dat2': r >> 18 & 1, 'dat3': r >> 19 & 1, 'cmd': r >> 20 & 1}

    @staticmethod
    def _crc7(data):
        c = 0
        for b in data:
            for i in range(7, -1, -1):
                bit = (b >> i & 1) ^ (c >> 6 & 1)
                c = (c << 1) & 0x7F
                if bit: c ^= 0x09
        return c

    @staticmethod
    def _crc16(data):
        c = 0
        for b in data:
            c ^= b << 8
            for _ in range(8):
                c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        return c

    def sd_command(self, cmd, arg=0, extra=0, div=32, hold=False):
        """One SPI-mode command: returns (R1, the `extra` bytes after it).  R1 is None if the card never answered.
        hold=True leaves the card selected (for the data block that follows)."""
        frame = bytes([0x40 | cmd, arg >> 24 & 0xFF, arg >> 16 & 0xFF, arg >> 8 & 0xFF, arg & 0xFF])
        frame += bytes([self._crc7(frame) << 1 | 1])
        self.spi_xfer(0xFF, cs=0, div=div)                   # a byte of clocks with the card selected
        for b in frame:
            self.spi_xfer(b, cs=0, div=div)
        r1 = None
        for _ in range(10):
            r = self.spi_xfer(0xFF, cs=0, div=div)
            if not r & 0x80:
                r1 = r; break
        rest = bytes(self.spi_xfer(0xFF, cs=0, div=div) for _ in range(extra)) if r1 is not None else b''
        if not hold:
            self.spi_xfer(0xFF, cs=1, div=div)               # deselect, and the eight clocks the card wants after it
        return r1, rest

    def sd_data(self, n, div=32):
        """The data block after a read command: waits for the start token 0xFE, reads n bytes and the CRC-16.
        Returns (data, crc_ok); then deselects the card."""
        tok = None
        for _ in range(2000):
            tok = self.spi_xfer(0xFF, cs=0, div=div)
            if tok != 0xFF:
                break
        if tok != 0xFE:
            self.spi_xfer(0xFF, cs=1, div=div)
            raise IOError('SD: no data token (got %s)' % ('nothing' if tok == 0xFF else '0x%02x' % tok))
        data = bytes(self.spi_xfer(0xFF, cs=0, div=div) for _ in range(n))
        crc = self.spi_xfer(0xFF, cs=0, div=div) << 8 | self.spi_xfer(0xFF, cs=0, div=div)
        self.spi_xfer(0xFF, cs=1, div=div)
        return data, crc == self._crc16(data)

    def sd_check(self, read_block=True):
        """Bring a microSD card up in SPI mode and read its identity and block 0.  Nothing is written to the card.
        Returns a dict; 'ok' is True when the card initialised, its CID read with a right CRC, and block 0 did too.
        With no card the first command gets no answer ('card': False)."""
        self.need_v2()
        out = {'pins_idle': self.sd_pins()}
        for _ in range(10):                                  # 80 clocks with the card deselected: it enters SPI mode
            self.spi_xfer(0xFF, cs=1)
        r1, _ = self.sd_command(0)
        out['cmd0'] = r1
        if r1 is None:
            out.update(card=False, ok=False)
            return out
        out['card'] = True
        r1, r7 = self.sd_command(8, 0x1AA, extra=4)
        out['cmd8'] = (r1, r7.hex())
        v2 = r1 == 0x01 and r7[2:] == b'\x01\xaa'
        ready = False
        for n in range(200):                                 # ACMD41 until the card leaves idle (a second at most)
            self.sd_command(55)
            r1, _ = self.sd_command(41, 0x40000000 if v2 else 0)
            if r1 == 0x00:
                ready = True; break
            self.wait(0.01)
        out.update(acmd41_tries=n + 1, ready=ready)
        if not ready:
            out['ok'] = False
            return out
        r1, ocr = self.sd_command(58, extra=4)
        out['ocr'] = ocr.hex(); out['high_capacity'] = bool(ocr and ocr[0] & 0x40)
        fast = 4                                             # 3.1 MHz from here on
        r1, _ = self.sd_command(10, div=fast, hold=True)
        cid, ok_cid = self.sd_data(16, div=fast) if r1 == 0 else (b'', False)
        out.update(cid=cid.hex(), cid_crc_ok=ok_cid, manufacturer=cid[0] if cid else None,
                   name=cid[3:8].decode('ascii', 'replace') if cid else None)
        ok_blk = True
        if read_block:
            r1, _ = self.sd_command(17, 0, div=fast, hold=True)
            blk, ok_blk = self.sd_data(512, div=fast) if r1 == 0 else (b'', False)
            out.update(block0_crc_ok=ok_blk, block0_signature=blk[510:512].hex() if blk else None, block0_head=blk[:16].hex())
        out['ok'] = bool(ready and ok_cid and ok_blk)
        return out

    def hdmi(self, on=None, pattern=None):
        """The HDMI test picture (640 x 480, 60 Hz): on/off and the pattern (0 colour bars with a white border, a grey
        ramp and a moving block; 1 white; 2 black; 3 a one-pixel checkerboard).  Returns the state: the hot-plug
        pin, the DDC pins, the frames sent."""
        self.need_v2()
        r = self.rd('HDMI')
        v = r & 0x3F
        if on is not None: v = (v & ~1) | int(bool(on))
        if pattern is not None: v = (v & ~6) | ((pattern & 3) << 1)
        if on is not None or pattern is not None:
            self.wr('HDMI', v | 0x30)                        # DDC released
            r = self.rd('HDMI')
        return {'on': bool(r & 1), 'pattern': r >> 1 & 3, 'hpd': bool(r >> 8 & 1), 'scl': bool(r >> 9 & 1), 'sda': bool(r >> 10 & 1),
                'cec': bool(r >> 11 & 1), 'frames': r >> 16}

    def hdmi_frame_rate(self, seconds=1.0):
        """Frames per second from the frame counter: 59.5 (25 MHz / (800 x 525)).  The counter runs whether or not the
        picture is switched on: it shows that the PLL's pixel clock and the picture's timing are alive, not that
        a monitor shows anything."""
        a = self.hdmi()['frames']; t0 = self.t.time()
        self.wait(seconds)
        b = self.hdmi()['frames']; t1 = self.t.time()
        return ((b - a) & 0xFFFF) / (t1 - t0)

    def edid(self):
        """The monitor's EDID (128 bytes from DDC address 0x50) through the bit-banged I2C, or None when nothing
        answers.  Returns {'raw', 'header_ok', 'checksum_ok', 'maker', 'name'}."""
        self.need_v2()
        raw = self.i2c_read(0x50, 0, 128, bus='ddc')
        if raw is None:
            return None
        raw = bytes(raw)
        m = raw[8] << 8 | raw[9]
        maker = ''.join(chr(64 + (m >> s & 31)) for s in (10, 5, 0))
        name = None
        for o in (54, 72, 90, 108):                          # the four descriptors; tag 0xFC is the monitor's name
            if raw[o:o + 3] == b'\x00\x00\x00' and raw[o + 3] == 0xFC:
                name = raw[o + 5:o + 18].split(b'\n')[0].decode('ascii', 'replace').strip()
        return {'raw': raw.hex(), 'header_ok': raw[:8] == b'\x00\xff\xff\xff\xff\xff\xff\x00', 'checksum_ok': sum(raw) & 0xFF == 0,
                'maker': maker, 'name': name}

    @staticmethod
    def eth_frame(payload_len=18, seq=0, src_mac=b'\x02\xec\x5b\xa2\xd2\x01', src_ip=(192, 168, 8, 250), port=50007):
        """A complete Ethernet frame, destination address through FCS: a UDP datagram to the broadcast address,
        which any PC on the same switch receives on an ordinary socket bound to `port` (no root).  The payload
        is 'ECP5' + a 4-byte sequence number + counting bytes.  payload_len 18 gives the minimum frame (64 bytes)."""
        import zlib
        payload = (b'ECP5' + struct.pack('>I', seq) + bytes(i & 0xFF for i in range(max(0, payload_len - 8))))[:payload_len]
        udp = struct.pack('>HHHH', port, port, 8 + len(payload), 0) + payload
        ip = struct.pack('>BBHHHBBH4B4B', 0x45, 0, 20 + len(udp), seq & 0xFFFF, 0, 64, 17, 0, *src_ip, 255, 255, 255, 255)
        csum = sum(struct.unpack('>10H', ip)); csum = (csum & 0xFFFF) + (csum >> 16); csum = ~((csum & 0xFFFF) + (csum >> 16)) & 0xFFFF
        ip = ip[:10] + struct.pack('>H', csum) + ip[12:]
        f = b'\xff' * 6 + src_mac + b'\x08\x00' + ip + udp
        f += b'\x00' * max(0, 60 - len(f))
        return f + struct.pack('<I', zlib.crc32(f) & 0xFFFFFFFF)

    def eth_load(self, frame):
        """Put a frame (with its FCS) into the transmit buffer."""
        self.need_v2()
        if not 64 <= len(frame) <= 1522:
            raise ValueError('a frame is 64..1522 bytes with its FCS, not %d' % len(frame))
        for i, b in enumerate(frame):
            self.wr('ETH_TXDATA', b | (i << 8))
        self.wr('ETH_TXLEN', len(frame))

    def eth_counts(self):
        s = self.rd('ETH_CTRL')
        return {'tx_busy': bool(s & 1), 'captured': bool(s & 2), 'rx_len': s >> 16 & 0x7FF, 'tx': self.rd('ETH_TXN'),
                'rx': self.rd('ETH_RXN'), 'rx_good': self.rd('ETH_RXGOOD'), 'rx_bad': self.rd('ETH_RXBAD')}

    def eth_clear(self):
        self.wr('ETH_CTRL', 2)

    def eth_send(self, count=1, gap=12, timeout=30.0):
        """Send the loaded frame `count` times (<= 65535) with `gap` idle bytes between; waits until they are out."""
        self.wr('ETH_TXCNT', (count & 0xFFFF) | ((gap & 0xFFF) << 16))
        self.wr('ETH_CTRL', 1)
        self.t.sleep(0.001)
        t0 = self.t.time()
        while self.rd('ETH_CTRL') & 1:
            if self.t.time() - t0 > timeout:
                raise IOError('ETH: still sending after %.0f s (no 125 MHz clock? PLL lock?)' % timeout)
            self.t.sleep(0.005)

    def eth_capture(self):
        """The first frame received since eth_clear(), as bytes (through its FCS), or None."""
        s = self.rd('ETH_CTRL')
        if not s & 2:
            return None
        n = s >> 16 & 0x7FF
        out = bytearray()
        for i in range(n):
            self.wr('ETH_RXADDR', i)
            out.append(self.rd('ETH_RXDATA') & 0xFF)
        return bytes(out)

    def eth_loopback_test(self, frames=1000, payload_len=18, gap=12, phy=1):
        """The RGMII data path with no cable: the PHY in its own loopback, `frames` frames out, every one counted
        and CRC-checked on the way back, and the first compared byte for byte.  Restores auto-negotiation after."""
        import zlib
        self.need_v2()
        f = self.eth_frame(payload_len)
        self.phy_loopback(True, phy)
        self.wait(0.5)                                       # the PHY's receive clock settles
        self.eth_load(f); self.eth_clear()
        self.eth_send(1, gap); self.wait(0.05)               # the counters the bus reads are snapshots, up to 10 us old
        first = self.eth_counts(); cap = self.eth_capture()
        self.eth_clear()
        self.eth_send(frames, gap); self.wait(0.05)
        c = self.eth_counts()
        self.phy_loopback(False, phy)
        return {'frame_len': len(f), 'frames': frames, 'first': first, 'capture_equal': cap == f,
                'capture_crc_ok': cap is not None and len(cap) >= 4 and zlib.crc32(cap[:-4]) & 0xFFFFFFFF == struct.unpack('<I', cap[-4:])[0],
                'rx': c['rx'], 'rx_good': c['rx_good'], 'rx_bad': c['rx_bad'], 'tx': c['tx'],
                'ok': cap == f and c['rx_good'] == frames and c['rx_bad'] == 0}

    def pmod_loop_test(self):
        """With Pmod A's eight signal pins wired to Pmod B's (pin for pin): each pin driven alone high, then alone low,
        from A and then from B, and the other side read.  Returns {'ok', 'a_to_b': [bad bits], 'b_to_a': [...], 'detail'}.
        Leaves both Pmods as inputs."""
        bad = {'a_to_b': [], 'b_to_a': []}
        detail = []
        for name, kw_drive, read in (('a_to_b', 'a', 'b'), ('b_to_a', 'b', 'a')):
            for i in range(8):
                for pat in (1 << i, ~(1 << i) & 0xFF):
                    args = {'mode_a': 1 if kw_drive == 'a' else 0, 'mode_b': 1 if kw_drive == 'b' else 0, kw_drive: pat}
                    got = self.pmod(**args)[read]
                    if got != pat:
                        if i not in bad[name]: bad[name].append(i)
                        detail.append('%s bit %d: drove %02x, read %02x' % (name, i, pat, got))
        self.pmod(mode_a=0, mode_b=0)
        return {'ok': not bad['a_to_b'] and not bad['b_to_a'], 'detail': detail[:16], **bad}

    def wait_buttons(self, timeout=30.0):
        """Watch BTN0 and BTN1 for `timeout` seconds; returns which were seen pressed."""
        seen = {'btn0': False, 'btn1': False}
        t0 = self.t.time()
        while self.t.time() - t0 < timeout and not all(seen.values()):
            st = self.status()
            seen['btn0'] |= st['btn0']; seen['btn1'] |= st['btn1']
            self.t.sleep(0.02)
        return seen


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
        elif cmd == 'gpio':                      # gpio usb_pullup=1 pdwn_a=0 ...: set bits, print them all (they stay set)
            print(b.gpio(**{k: int(v, 0) for k, v in (a.split('=') for a in args)}))
        else:
            print(__doc__); return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
