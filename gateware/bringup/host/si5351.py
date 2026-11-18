"""Si5351A register planning (AN619), the little that the bring-up needs: one output at a time from the
25 MHz crystal.  The multiplier and divider arithmetic is the GPSDO board's (GPSDO-PYNQ-Z2/gateware/driver/
i2c_devices.py: ms_params, ms_registers, plan_pll), which ran on real Si5351As there.

    plan(25e6, 10e6)   -> {'a','b','c' (the PLL ratio), 'div' (even integer output divider), 'f_vco', 'f_out', 'integer'}
    registers(clk, plan, drive_ma=2) -> {register: byte} for the PLL (A for CLK0/1, B for CLK2) and the MultiSynth

CLK0 and CLK1 share PLLA here, so setting one reprograms the PLL the other depends on: set CLK2 (PLLB) when
two independent frequencies are wanted at once.
"""
from fractions import Fraction

REG_OEB, REG_CLK_CTRL, REG_MSNA, REG_MSNB, REG_MS0, REG_PLL_RESET, REG_XTAL_CL = 3, 16, 26, 34, 42, 177, 183
CLK_INT, CLK_PLLB, CLK_SRC_MS = 0x40, 0x20, 0x0C
IDRV = {2: 0, 4: 1, 6: 2, 8: 3}
XTAL_CL_10PF = 0xC0 | 0x12          # AN619 reg 183: 10 pF load, reserved bits 010010b


def ms_params(a, b, c):
    """(P1, P2, P3) for the ratio a + b/c (AN619 3.2 / 4.1.2)."""
    f = (128 * b) // c
    p1 = 128 * a + f - 512
    p2 = 128 * b - c * f
    return p1, p2, c


def ms_registers(base, p1, p2, p3, rdiv=0):
    return {base + 0: (p3 >> 8) & 0xFF, base + 1: p3 & 0xFF, base + 2: ((rdiv & 7) << 4) | ((p1 >> 16) & 3),
            base + 3: (p1 >> 8) & 0xFF, base + 4: p1 & 0xFF, base + 5: ((p3 >> 12) & 0xF0) | ((p2 >> 16) & 0x0F),
            base + 6: (p2 >> 8) & 0xFF, base + 7: p2 & 0xFF}


def plan(f_xtal, f_out):
    """An even integer output divider 6..900 and the PLL ratio (integer where one exists) for f_out, VCO in 600-900 MHz.
    Below 500 kHz the R divider (powers of two) stretches the range to 2.5 kHz."""
    f_out = Fraction(f_out).limit_denominator(10 ** 6)
    best = None
    rdiv = 0
    while f_out * (1 << rdiv) < 500_000 and rdiv < 7:
        rdiv += 1
    f_ms = f_out * (1 << rdiv)
    for div in range(6, 902, 2):
        f_vco = f_ms * div
        if f_vco < 600e6 or f_vco > 900e6:
            continue
        ratio = Fraction(f_vco) / Fraction(f_xtal)
        if ratio.denominator == 1 and 15 <= ratio <= 90:
            best = (div, ratio, True); break
        if best is None and 15 <= ratio <= 90:
            best = (div, ratio.limit_denominator(1048575), False)
    if best is None:
        raise ValueError('no Si5351 plan for %.1f Hz' % float(f_out))
    div, ratio, integer = best
    a = ratio.numerator // ratio.denominator
    b = ratio.numerator - a * ratio.denominator
    c = ratio.denominator
    f_vco = f_xtal * float(ratio)
    return {'a': a, 'b': b, 'c': c, 'div': div, 'rdiv': rdiv, 'f_vco': f_vco, 'f_out': f_vco / div / (1 << rdiv), 'integer': integer}


def registers(clk, p, drive_ma=2):
    pll_b = clk == 2
    regs = {REG_XTAL_CL: XTAL_CL_10PF}
    regs.update(ms_registers(REG_MSNB if pll_b else REG_MSNA, *ms_params(p['a'], p['b'], p['c'])))
    regs.update(ms_registers(REG_MS0 + 8 * clk, *ms_params(p['div'], 0, 1), rdiv=p['rdiv']))
    regs[REG_CLK_CTRL + clk] = (CLK_INT if p['integer'] else 0) | (CLK_PLLB if pll_b else 0) | CLK_SRC_MS | IDRV[drive_ma]
    return regs


if __name__ == '__main__':
    import sys
    for f in (sys.argv[1:] or ['10e6', '25e6', '100e6', '1e6', '12.345e6']):
        p = plan(25e6, float(f))
        print('%12.3f Hz: VCO %.3f MHz = 25 x (%d + %d/%d), /%d, R/%d -> %.6f Hz %s'
              % (float(f), p['f_vco'] / 1e6, p['a'], p['b'], p['c'], p['div'], 1 << p['rdiv'], p['f_out'], 'integer' if p['integer'] else 'fractional'))
