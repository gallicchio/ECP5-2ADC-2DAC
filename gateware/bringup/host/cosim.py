#!/usr/bin/env python3
"""The bring-up design simulated, behind the same Board class that drives the real one.

    from cosim import SimBoard
    with SimBoard(cables={'dac1': 'adc_a', 'dac2': 'adc_b', 'clk_out': 'clk_in'}, sd=1, usb=1) as b:
        print(b.ident(), b.clocks())          # ecp5bu.Board's own methods, against rtl/top.v in iverilog
        b.world(link=1)                       # change the bench: plug the Ethernet cable in

    python3 host/cosim.py                     # a self-test: a few registers, a capture, an SD card, a frame

So every procedure of bringup/bench.py is run before a board is on the bench (`bench.py --sim ...`).
sim/tb_cosim.v reads commands from one named pipe and answers on another (Icarus blocks on the read, so the
simulated time stands still while the Python thinks): S xx sends a UART byte, R n waits for n bytes back,
W n waits n nanoseconds, T asks the time, F discards what the board has sent, K id value sets a knob of the simulated bench, E ends.

Time: the simulated UART runs at 6.25 Mbaud (UART_DIV 4) and the frequency counters' gate is 1 ms, and every
wait the procedures ask for is shortened a thousand times (SimTransport.scale): a "0.5 s" settle is 0.5 ms of
simulated time, a few seconds of real time.  What cannot be shortened (16 M words of SDRAM) the caller makes smaller.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import ecp5bu                                                     # noqa: E402

OSS = os.environ.get('OSS_CAD_SUITE', '/home/jason/mudd/133electronics/icepi-zero-dac-adc/tools/oss-cad-suite')
RTL_FILES = 'top.v uart.v regbus.v cdc.v clkcount.v adc_capture.v dac_gen.v sdram_test.v pll_sys.v periph.v eth_test.v hdmi_test.v'.split()
SIM_FILES = 'tb_cosim.v ecp5_sim_models.v models.v models2.v sdram_model.v rgmii_phy_model.v'.split()
# the knobs of sim/tb_cosim.v (K id value)
KNOBS = {'clkin': 1, 'clkin_hz': 2, 'pmod_loop': 3, 'sd': 4, 'usb': 5, 'monitor': 6, 'link': 7, 'btn0': 8, 'btn1': 9,
         'src_a': 10, 'src_b': 11, 'gain_a': 12, 'gain_b': 13, 'term_a': 14, 'term_b': 15,
         'gen_hz_a': 16, 'gen_codes_a': 17, 'gen_hz_b': 18, 'gen_codes_b': 19, 'eth_inject': 20}
SRC = {None: 0, 'none': 0, 'dac1': 1, 'dac2': 2, 'gen': 3}


def build(force=False):
    """Compile the co-simulation (build/tb_cosim.vvp) if a source is newer than it."""
    vvp = os.path.join(TOP, 'build', 'tb_cosim.vvp')
    srcs = [os.path.join(TOP, 'rtl', f) for f in RTL_FILES] + [os.path.join(TOP, 'sim', f) for f in SIM_FILES]
    extra = os.path.join(TOP, 'rtl', 'tmds_enc.v')
    if os.path.exists(extra):
        srcs.append(extra)
    if force or not os.path.exists(vvp) or any(os.path.getmtime(f) > os.path.getmtime(vvp) for f in srcs):
        os.makedirs(os.path.dirname(vvp), exist_ok=True)
        subprocess.check_call([os.path.join(OSS, 'bin', 'iverilog'), '-g2012', '-o', vvp, '-s', 'tb_cosim'] + srcs)
    return vvp


class SimTransport(ecp5bu.Transport):
    scale = 1e-3                    # simulated seconds per bench second
    gate_s = 1e-3                   # tb_cosim's GATE_CYCLES is 25000

    def __init__(self, log=None):
        vvp = build()
        self.dir = tempfile.mkdtemp(prefix='ecp5cosim_')
        self.cmd_path, self.resp_path = os.path.join(self.dir, 'cmd'), os.path.join(self.dir, 'resp')
        os.mkfifo(self.cmd_path); os.mkfifo(self.resp_path)
        self.log = open(log or os.path.join(self.dir, 'vvp.log'), 'w')
        # run in rtl/: $readmemh("sine_lut.hex") is relative to the working directory
        self.proc = subprocess.Popen([os.path.join(OSS, 'bin', 'vvp'), '-n', vvp, '+cmd=' + self.cmd_path, '+resp=' + self.resp_path],
                                     cwd=os.path.join(TOP, 'rtl'), stdout=self.log, stderr=subprocess.STDOUT)
        self.cmd = open(self.cmd_path, 'w')          # blocks until the simulator has opened its end
        self.resp = open(self.resp_path, 'r')
        self.bytes_out = 0

    def _line(self):
        s = self.resp.readline()
        if not s:
            raise IOError('the simulator stopped (see %s)' % self.log.name)
        return s.strip()

    def write(self, data):
        self.cmd.write(''.join('S %02x\n' % b for b in data))
        self.bytes_out += len(data)

    def read(self, n):
        self.cmd.write('R %d\n' % n); self.cmd.flush()
        out = bytearray()
        for _ in range(n):
            s = self._line()
            if s == 'TO':
                raise IOError('board (simulated): wanted %d bytes, got %d' % (n, len(out)))
            out.append(int(s, 16))
        return bytes(out)

    def sleep(self, seconds):
        self.cmd.write('W %d\n' % max(1, int(seconds * self.scale * 1e9)))

    def time(self):
        self.cmd.write('T\n'); self.cmd.flush()
        return float(self._line()) * 1e-9 / self.scale

    def knob(self, name, value):
        self.cmd.write('K %d %g\n' % (KNOBS[name], value))

    def flush(self):
        self.cmd.write('F\n'); self.cmd.flush()

    def close(self):
        try:
            self.cmd.write('E\n'); self.cmd.flush()
            self.proc.wait(timeout=20)
        except Exception:
            self.proc.kill()
        for f in (self.cmd, self.resp, self.log):
            try: f.close()
            except Exception: pass
        if self.proc.returncode == 0:                        # a simulator that died keeps its log for whoever looks
            import shutil
            shutil.rmtree(self.dir, ignore_errors=True)      # the two pipes and the log


class SimBoard(ecp5bu.Board):
    """ecp5bu.Board on the simulated board, plus world(): the cables, cards and jumpers of the simulated bench."""
    def __init__(self, cables=None, **knobs):
        t = SimTransport()
        self.state = {}
        ecp5bu.Board.__init__(self, transport=t, check=False)
        self.world(cables=cables or {}, **knobs)
        self.wait(0.5)                               # the PLL locks, the SDRAM initialises
        self.resync()
        self.version = int(self.ident()['version'], 16)
        self._gpio = self.rd('GPIO')

    def world(self, cables=None, **knobs):
        """cables: {'dac1': 'adc_a', 'dac2': 'adc_b', 'clk_out': 'clk_in', 'gen': 'adc_a', 'gen_clk': 'clk_in'} (a
        source to the input it is plugged into).  knobs: sd, usb, monitor, link, pmod_loop, btn0, btn1 (0/1),
        gain_a, gain_b (1, 10, 100), term_a, term_b (1 = the 50 ohm shunt in), gen_hz_a, gen_codes_a, ...,
        clkin_hz."""
        if cables is not None:
            inv = {v: k for k, v in cables.items()}
            self.t.knob('src_a', SRC[inv.get('adc_a')]); self.t.knob('src_b', SRC[inv.get('adc_b')])
            self.t.knob('clkin', {None: 0, 'clk_out': 1, 'gen_clk': 2}[inv.get('clk_in')])
            self.state['cables'] = dict(cables)
        for k, v in knobs.items():
            self.t.knob(k, v); self.state[k] = v
        self.t.sleep(0.001)


def selftest():
    import numpy as np
    with SimBoard(cables={'dac1': 'adc_a', 'dac2': 'adc_b', 'clk_out': 'clk_in'}, sd=1, usb=1, monitor=1, pmod_loop=1) as b:
        print('ident', b.ident(), b.status())
        print('scratch', b.scratch_test(3))
        b.clkout('tcxo/2')
        print('clocks', b.clocks(gates=2))               # the second gate after CLK OUT was switched: the first straddles it
        b.dac_config(rate=50e6); b.adc_config(rate=25e6)
        b.gpio(dac_sleep=0)
        f = b.dac(1, 'sine', freq=1e6); b.dac(2, 'dc', code=12288)
        b.wait(0.05)
        t, a, bb, otr = b.capture(512)
        print('loopback: A pk-pk %d codes (a full-scale sine: 4095), B mean %.1f (code 12288 = +0.5 V: 3072)' % (a.max() - a.min(), bb.mean()))
        print('pmod', b.pmod_loop_test())
        print('sd', b.sd_check())
        print('usb', b.usb_attach('fs', seconds=1.0))
        print('hdmi', b.hdmi(on=True), 'edid', {k: v for k, v in (b.edid() or {}).items() if k != 'raw'})
        print('phy', ['%04x' % x for x in b.phy_id()], b.phy_straps())
        print('eth', b.eth_loopback_test(frames=20))
    return 0


if __name__ == '__main__':
    sys.exit(selftest())
