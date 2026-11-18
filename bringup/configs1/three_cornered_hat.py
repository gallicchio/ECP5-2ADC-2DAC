"""Test 3 (2026-11-17): the board's three clocks against each other.  Load a build of configs1/clocks_hat.sv (the
tutorial's clocks.sv with the Ethernet receive clock, the switch's 125 MHz, counted in place of the Si5351's CLK2, and
the PHY out of reset): yosys/nextpnr/ecppack as the tutorial's Makefile does, then openFPGALoader -c ft2232.  Run from the
tutorial's src/verilog: python3 three_cornered_hat.py [seconds].  The Si5351's CLK0 at 100 MHz and the switch's clock,
each counted against the TCXO's second; the Allan deviation of each pair, and the three-cornered hat's split."""
import sys, time, numpy as np
import clocks
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
c = clocks.Clocks(clocks.find_port())
c.si5351(0, 100e6, enabled=(0,), drive=1)
time.sleep(4)
c.s.reset_input_buffer()
rows = []
while len(rows) < N + 5:
    f = c.s.readline().split()
    if len(f) == 4:
        rows.append([int(x, 16) for x in f])
c.write(clocks.REG_OEB, 0xFF)
r = np.array(rows[5:], float)
ys, yr = r[:, 1] / 100e6 - 1, r[:, 3] / 125e6 - 1
def adev(y, m):
    yb = np.convolve(y, np.ones(m) / m, "valid"); d = yb[m:] - yb[:-m]
    return np.sqrt(0.5 * np.mean(d ** 2))
print("Si5351 %+.3f ppm, switch %+.3f ppm against the TCXO" % (1e6 * ys.mean(), 1e6 * yr.mean()))
for m in (1, 2, 4, 8, 16, 32, 64):
    st, rt, sr = adev(ys, m), adev(yr, m), adev(ys - yr, m)
    v = (0.5 * (st**2 + rt**2 - sr**2), 0.5 * (st**2 + sr**2 - rt**2), 0.5 * (rt**2 + sr**2 - st**2))
    print("%4d s: pairs %.2e %.2e %.2e; TCXO, Si5351, switch: %s" % (m, st, rt, sr, ", ".join("%.2e" % np.sqrt(x) if x > 0 else "(<0)" for x in v)))
