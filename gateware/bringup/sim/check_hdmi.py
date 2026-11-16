#!/usr/bin/env python3
"""A second receiver for rtl/hdmi_test.v: the bits tb_hdmi.v sampled from the pins, decoded here on its own.

    vvp -n build/hdmi_check/tb_hdmi.vvp          # writes build/hdmi_check/hdmi_bits.txt (from gateware/bringup)
    python3 sim/check_hdmi.py [bits.txt [frame.png]]

The dump is one hex digit {ck, d2, d1, d0} a bit, from the testbench's first lock to the end of its second frame
of pattern 0.  This script shares nothing with the testbench but that file: it finds each channel's word boundary
(the phase with the most control codes), decodes the symbols with a table built from the DVI 1.0 decoder
(figure 3-6), finds the frame (the first picture symbol after a vertical sync), checks the raster and the picture,
encodes the decoded frame again with the specification's encoder (figure 3-5) and compares it bit for bit with
what the pins carried, and saves the first frame as a PNG (and the second beside it, as ..._2.png).
"""
import sys

import numpy as np
from PIL import Image

HA, HFP, HS, HBP, HT = 640, 16, 96, 48, 800
VA, VFP, VS, VBP, VT = 480, 10, 2, 33, 525
CTL = {0b1101010100: 0, 0b0010101011: 1, 0b0101010100: 2, 0b1010101011: 3}      # the symbol -> {c1, c0}
BARS = [(255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0), (255, 0, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0)]

checks = fails = 0


def check(what, ok):
    global checks, fails
    checks += 1
    if ok:
        print("  ok: " + what)
    else:
        fails += 1
        print("FAIL: " + what)


def done():
    print("%d checks, %d failures: %s" % (checks, fails, "PASS" if fails == 0 else "FAIL"))
    sys.exit(1 if fails else 0)


def decode_symbol(s):
    """DVI 1.0 figure 3-6: bit 9 says the byte was inverted, bit 8 whether it was chained with xor (1) or xnor."""
    m = (s ^ 0xff) & 0xff if s & 0x200 else s & 0xff
    d = m & 1
    for i in range(1, 8):
        b = ((m >> i) ^ (m >> (i - 1))) & 1
        d |= (b if s & 0x100 else b ^ 1) << i
    return d


def encode_stream(data, c, de):
    """DVI 1.0 figure 3-5, one channel: the ten-bit symbols for bytes `data`, control pairs `c`, enable `de`."""
    qm_of, n1_of = [], []                           # per byte: the transition-minimised word, the ones in its low eight bits
    for d in range(256):
        n1 = bin(d).count("1")
        xnor = n1 > 4 or (n1 == 4 and not d & 1)
        qm = d & 1
        for k in range(1, 8):
            b = ((qm >> (k - 1)) ^ (d >> k)) & 1
            qm |= (b ^ 1 if xnor else b) << k
        qm_of.append(qm | (0 if xnor else 0x100))
        n1_of.append(bin(qm).count("1"))
    code = {v: k for k, v in CTL.items()}
    out = np.zeros(len(data), np.int32)
    cnt = 0
    for i, (d, ci, e) in enumerate(zip(data.tolist(), c.tolist(), de.tolist())):
        if not e:
            out[i] = code[ci]
            cnt = 0
            continue
        qm, n1 = qm_of[d], n1_of[d]
        n0 = 8 - n1
        b8 = qm >> 8
        if cnt == 0 or n1 == n0:
            out[i] = ((b8 ^ 1) << 9) | (b8 << 8) | ((qm & 0xff) if b8 else (~qm & 0xff))
            cnt += (n1 - n0) if b8 else (n0 - n1)
        elif (cnt > 0 and n1 > n0) or (cnt < 0 and n0 > n1):
            out[i] = 0x200 | (b8 << 8) | (~qm & 0xff)
            cnt += 2 * b8 + (n0 - n1)
        else:
            out[i] = (b8 << 8) | (qm & 0xff)
            cnt += -2 * (b8 ^ 1) + (n1 - n0)
    return out


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "build/hdmi_check/hdmi_bits.txt"
    png = sys.argv[2] if len(sys.argv) > 2 else "build/hdmi_check/frame.png"
    raw = np.fromfile(src, dtype=np.uint8)
    hexval = np.full(256, 255, np.uint8)
    for ch in "0123456789abcdef":
        hexval[ord(ch)] = int(ch, 16)
    nib = hexval[raw]
    check("%s: %d bits, every one 0 or 1" % (src, len(nib)), len(nib) > 20 * HT * VT and int(nib.max()) < 16)
    if fails:
        done()

    # ---- words: per channel, the boundary with the most control codes ----
    is_ctl = np.zeros(1024, bool)
    is_ctl[list(CTL)] = True
    weights = 1 << np.arange(10)                    # the first bit sent is bit 0
    sym, phase = [], []
    for chn in range(3):
        bits = ((nib >> chn) & 1).astype(np.int32)
        best = None
        for ph in range(10):
            n = (len(bits) - ph) // 10
            s = bits[ph:ph + 10 * n].reshape(n, 10) @ weights
            score = int(is_ctl[s].sum())
            if best is None or score > best[0]:
                best = (score, ph, s)
        phase.append(best[1])
        sym.append(best[2])
    check("word boundary: the same on d0, d1 and d2 (bit %d of the dump)" % phase[0], phase[0] == phase[1] == phase[2])
    if fails:
        done()
    n = min(len(s) for s in sym)
    sym = np.array([s[:n] for s in sym])            # [channel, pixel]
    ctl = is_ctl[sym]
    val = np.array([CTL.get(s, 0) if s in CTL else decode_symbol(s) for s in range(1024)], np.uint8)[sym]
    # the clock pair: one rising edge every ten bits
    ck = ((nib >> 3) & 1).astype(np.int8)
    rises = np.flatnonzero(np.diff(ck) == 1) + 1
    check("clock pair: a rising edge every 10 bits, high for 5 (%d edges), at the word boundary" % len(rises),
          len(rises) > 1000 and bool(np.all(np.diff(rises) == 10)) and bool(np.all(ck[rises[:-1, None] + np.arange(10)] == [1] * 5 + [0] * 5))
          and rises[0] % 10 == phase[0])

    # ---- the frame: the first picture symbol after a vertical sync ----
    vs_low = np.flatnonzero(ctl[0] & ((val[0] & 2) == 0))
    pic = np.flatnonzero(~ctl[0])
    start = int(pic[pic > vs_low[0]][0]) if len(vs_low) and np.any(pic > vs_low[0]) else -1
    check("frame start found, and two whole frames after it", start >= 0 and start + 2 * HT * VT <= n)
    if fails:
        done()
    fr_sym = sym[:, start:start + 2 * HT * VT].reshape(3, 2, VT, HT)
    fr_ctl = ctl[:, start:start + 2 * HT * VT].reshape(3, 2, VT, HT)
    fr_val = val[:, start:start + 2 * HT * VT].reshape(3, 2, VT, HT)

    # ---- the raster ----
    xx, yy = np.meshgrid(np.arange(HT), np.arange(VT))
    in_pic = (xx < HA) & (yy < VA)
    hs = ~((xx >= HA + HFP) & (xx < HA + HFP + HS))
    vline = yy + (xx >= HA + HFP)                   # lines counted from hsync's leading edge
    vs = ~((vline >= VA + VFP) & (vline < VA + VFP + VS))
    check("data enable: picture symbols on 640 x 480 of 800 x 525, control codes everywhere else, on all three channels, both frames",
          bool(np.all(fr_ctl == ~in_pic)))
    blank = ~in_pic
    check("d1 and d2: control code 00 through the blanking", bool(np.all(fr_val[1:, :, blank] == 0)))
    got_hs = (fr_val[0] & 1).astype(bool)
    got_vs = (fr_val[0] & 2).astype(bool)
    check("hsync: low for 96 pixels from column 656 of every line (front porch 16, back porch 48), high otherwise",
          bool(np.all(got_hs[:, blank] == hs[blank])))
    check("vsync: low for 2 lines from column 656 of line 489 (front porch 10 lines, back porch 33), on hsync's leading edge",
          bool(np.all(got_vs[:, blank] == vs[blank])))
    line0 = np.flatnonzero(~got_hs[0, 0, HA:]) + HA
    flat_vs = np.flatnonzero(~np.where(blank, got_vs[0], True).reshape(-1))
    print("        measured: hsync columns %d-%d of %d; vsync from line %d column %d for %d pixels (%.3f lines) of %d lines"
          % (line0[0], line0[-1], HT, flat_vs[0] // HT, flat_vs[0] % HT, len(flat_vs), len(flat_vs) / HT, VT))

    # ---- the picture ----
    img = np.stack([fr_val[2], fr_val[1], fr_val[0]], axis=-1)[:, :VA, :HA]     # [frame, y, x, rgb]
    Image.fromarray(img[0], "RGB").save(png)
    Image.fromarray(img[1], "RGB").save(png[:-4] + "_2.png")
    a = img[0].astype(int)
    white = np.array([255, 255, 255])
    check("border: columns 0 and 639 and lines 0 and 479 white, both frames",
          all(bool(np.all(f[0] == 255) and np.all(f[VA - 1] == 255) and np.all(f[:, 0] == 255) and np.all(f[:, HA - 1] == 255)) for f in img))
    check("inside the border it is not white where the picture is not: (120,1), (638,160), (1,400), (120,478)",
          all(not np.array_equal(a[y, x], white) for x, y in ((120, 1), (638, 160), (1, 400), (120, 478))))
    got = [tuple(a[160, 40 + 80 * k]) for k in range(8)]
    check("bars at their centres: " + " ".join("%02x%02x%02x" % g for g in got), got == BARS)
    check("bars fill lines 1-319, 80 columns each",
          all(bool(np.all(a[1:320, max(80 * k, 1):min(80 * k + 80, HA - 1)] == BARS[k])) for k in range(8)))
    ok = True
    for y in (320, 330, 391, 408, 470, 478):
        row = a[y, 1:HA - 1]
        ok = ok and bool(np.all(row[:, 0] == row[:, 1]) and np.all(row[:, 0] == row[:, 2]))
        step = np.diff(row[:, 0])
        ok = ok and bool(np.all((step == 0) | (step == 1))) and row[0, 0] == 0 and row[-1, 0] == 255
    check("ramp: grey, 0 at column 1 to 255 at column 638, steps of 0 or 1 (six lines of it)", ok)
    pos = []
    for f in img:
        red = (f[320:VA - 1, :, 0] == 255) & (f[320:VA - 1, :, 1] == 0) & (f[320:VA - 1, :, 2] == 0)
        ys, xs = np.nonzero(red)
        pos.append((int(xs.min()), int(ys.min()) + 320, int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1), int(red.sum())))
    check("moving block: red 16 x 16 at column %d, line %d in frame 1 and column %d in frame 2" % (pos[0][0], pos[0][1], pos[1][0]),
          pos[0][2:] == (16, 16, 256) and pos[1][2:] == (16, 16, 256) and pos[0][1] == pos[1][1] == 392 and pos[1][0] == pos[0][0] + 1)
    same = np.all(img[0] == img[1], axis=-1)
    check("the two frames differ in the block's two edge columns only (%d pixels)" % int((~same).sum()), int((~same).sum()) == 32)

    # ---- the symbols themselves: what the specification's encoder makes of this frame ----
    de = in_pic.reshape(-1)
    zeros = np.zeros(HT * VT, np.uint8)
    for f in range(2):
        want = [encode_stream(fr_val[0, f].reshape(-1), (got_vs[f].reshape(-1) * 2 + got_hs[f].reshape(-1)), de),
                encode_stream(fr_val[1, f].reshape(-1), zeros, de),
                encode_stream(fr_val[2, f].reshape(-1), zeros, de)]
        bad = [int((want[chn] != fr_sym[chn, f].reshape(-1)).sum()) for chn in range(3)]
        check("frame %d: all 3 x %d symbols are the ones the DVI 1.0 encoder gives for this picture (%d, %d, %d differ)"
              % (f + 1, HT * VT, bad[0], bad[1], bad[2]), bad == [0, 0, 0])
    # the line's running disparity (ones minus zeros of the picture symbols since the blanking), and the whole frame's
    ones = np.array([bin(s).count("1") for s in range(1024)])
    disp = 2 * ones[fr_sym] - 10
    run = np.cumsum(disp[:, :, :VA, :HA], axis=-1)
    check("running disparity along a line, from 0 at the blanking: at most %d, %d, %d on d0, d1, d2 (limit 10)"
          % tuple(int(np.abs(run[chn]).max()) for chn in range(3)), int(np.abs(run).max()) <= 10)
    print("        ones minus zeros over frame 1's %d bits a channel: d0 %+d (the sync codes are not balanced), d1 %+d, d2 %+d"
          % (10 * HT * VT, disp[0, 0].sum(), disp[1, 0].sum(), disp[2, 0].sum()))
    print("        wrote %s and %s" % (png, png[:-4] + "_2.png"))
    done()


if __name__ == "__main__":
    main()
