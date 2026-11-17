#!/usr/bin/env python3
"""bringup/figs/rework_ftdi.png: the two rev A reworks that make USB PROG work (REVB.md rows 12 and 13).

    python3 bringup/make_rework_fig.py

Drawn from the board file's own pads (ECP5-2ADC-2DAC.kicad_pcb), top view as the board lies on the bench (SMAs to
the left, the USB-Cs on the right edge), so every pad is where the iron goes.  Two jobs:
  1. FB6241 removed whole (hot air takes the whole part; never "lift one end": Jason, 2026-11-16) and an insulated
     wire from R6222's +3V3 end to FB6241's LEFT pad only (pad 2, toward C6241: VPHY/VPLL).  The RIGHT pad (pad 1,
     +1V8_FTDI: VREGOUT and VCORE) stays BARE: a wire on both pads puts 3.3 V on the 1.8 V core (absolute maximum
     2.0 V), which board A had for some minutes on 2026-11-16.
  2. No board work: a USB-A-to-C cable with D+ and D- swapped.  Only if that cannot be used: U501 (USBLC6-2SC6) off
     and two crossed wires on its empty pads, the USB-C's D+ to the FT2232H's DP, D- to DM.
"""
import math
import os
import re

from PIL import Image, ImageDraw

from make_figs import font, RED, BLUE, GREEN, ORANGE, GREY

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), 'ECP5-2ADC-2DAC.kicad_pcb')
X0, X1, Y0, Y1 = 141.0, 184.0, 53.0, 79.0          # board-file millimetres shown
PX = 44                                            # pixels per millimetre
TOP = 120                                          # room for the title
BOTTOM = 330                                       # room for the steps


def footprints():
    t = open(PCB).read()
    for m in re.finditer(r'\n\t\(footprint "([^"]+)"', t):
        st = m.start(); en = t.find('\n\t(footprint ', st + 5); en = en if en > 0 else len(t)
        seg = t[st:en]
        ref = re.search(r'"Reference" "([^"]+)"', seg)
        at = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', seg)
        if not ref or not at or '(layer "F.Cu")' not in seg[:400]:
            continue
        x, y, rot = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        pads = []
        for p in re.finditer(r'\(pad "([^"]*)" (\w+) (\w+)\s*\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)\s*\(size ([\d.]+) ([\d.]+)\)(.*?)\n\t\t\)', seg, re.S):
            px, py = float(p.group(4)), float(p.group(5))
            a = math.radians(-rot)
            ax, ay = x + px * math.cos(a) - py * math.sin(a), y + px * math.sin(a) + py * math.cos(a)
            w, h = float(p.group(7)), float(p.group(8))
            if round(float(p.group(6) or 0)) % 180 == 90:
                w, h = h, w
            net = re.search(r'\(net (?:\d+ )?"([^"]*)"\)', p.group(9))
            pads.append((p.group(1), ax, ay, w, h, net.group(1) if net else ''))
        yield ref.group(1), x, y, rot, pads


def main():
    fps = {r: (x, y, rot, pads) for r, x, y, rot, pads in footprints()}
    W, H = int((X1 - X0) * PX), int((Y1 - Y0) * PX)
    im = Image.new('RGB', (W, H + TOP + BOTTOM), (255, 255, 255))
    d = ImageDraw.Draw(im)
    xy = lambda x, y: ((x - X0) * PX, (y - Y0) * PX + TOP)
    d.rectangle((0, TOP, W, TOP + H), fill=(18, 70, 40))
    d.text((16, 12), 'Rev A rework: USB PROG (FT2232H)', fill=(0, 0, 0), font=font(38, True))
    d.text((16, 60), 'top view, as on the bench (SMAs to the left, USB-Cs on the right edge); pads from the board file; 1 mm = %d px' % PX,
           fill=(60, 60, 60), font=font(22))
    small, mid = font(17), font(22, True)
    for ref, (x, y, rot, pads) in fps.items():
        if not (X0 - 8 < x < X1 + 8 and Y0 - 8 < y < Y1 + 8):
            continue
        for n, px, py, w, h, net in pads:
            if not (X0 + w / 2 < px < X1 - w / 2 and Y0 + h / 2 < py < Y1 - h / 2):
                continue                          # only what lies inside the window
            a, b = xy(px - w / 2, py - h / 2), xy(px + w / 2, py + h / 2)
            colour = (200, 170, 90) if net != 'GND' else (150, 130, 80)
            d.rectangle((a[0], a[1], b[0], b[1]), fill=colour)
        if pads and len(pads) <= 8 and X0 + 2 < x < X1 - 2 and Y0 + 1 < y < Y1 - 1:
            if len(pads) == 2:                    # a two-pad part: its name to its right, clear of its pads
                right = max(p[1] + p[3] / 2 for p in pads)
                cx, cy = xy(right + 0.25, y)
                d.text((cx, cy), ref, fill=(235, 235, 235), font=small, anchor='lm')
            else:
                cx, cy = xy(x, y)
                d.text((cx, cy), ref, fill=(235, 235, 235), font=small, anchor='mm')
    # the FT2232H's body
    ux, uy = xy(fps['U502'][0], fps['U502'][1])
    d.rectangle((ux - 5 * PX, uy - 5 * PX, ux + 5 * PX, uy + 5 * PX), outline=(220, 220, 220), width=3)
    d.text((xy(146.5, 66.0)), 'U502  FT2232H', fill=(255, 255, 255), font=mid)

    def pad(ref, n):
        for p in fps[ref][3]:
            if p[0] == n:
                return p
        raise KeyError((ref, n))

    def mark(ref, n, colour, r=0.55):
        p = pad(ref, n); cx, cy = xy(p[1], p[2])
        d.ellipse((cx - r * PX, cy - r * PX, cx + r * PX, cy + r * PX), outline=colour, width=5)
        return cx, cy

    def cross(ref, colour):
        ps = fps[ref][3]
        xs = [p[1] for p in ps]; ys = [p[2] for p in ps]
        a, b = xy(min(xs) - 0.6, min(ys) - 0.6), xy(max(xs) + 0.6, max(ys) + 0.6)
        d.rectangle((a[0], a[1], b[0], b[1]), outline=colour, width=6)
        d.line((a[0], a[1], b[0], b[1]), fill=colour, width=4); d.line((a[0], b[1], b[0], a[1]), fill=colour, width=4)
        return a, b

    def callout(at, text, colour, to):
        d.line((at[0], at[1], to[0], to[1]), fill=colour, width=3)
        lines = text.split('\n'); f = font(21, True)
        wbox = max(d.textlength(s, font=f) for s in lines) + 16
        bx, by = to[0] - (wbox if to[0] > at[0] else 0) if False else to[0], to[1]
        bx = min(max(bx - wbox / 2, 4), W - wbox - 4)
        d.rectangle((bx, by, bx + wbox, by + 26 * len(lines) + 8), fill=(255, 255, 255), outline=colour, width=3)
        for i, s in enumerate(lines):
            d.text((bx + 8, by + 4 + 26 * i), s, fill=colour, font=f)

    # ---- job 1: VPHY / VPLL -----------------------------------------------------------------------------------
    bare = mark('FB6241', '1', RED, r=0.6)        # pad 1, +1V8_FTDI, farther from the chip: stays BARE
    vphy = mark('FB6241', '2', BLUE)              # pad 2, VPHY/VPLL, toward C6241: the wire goes here only
    p33 = mark('R6222', '1', BLUE)                # +3V3 end
    d.line((vphy[0], vphy[1], p33[0], p33[1]), fill=(80, 160, 255), width=7)
    d.line((bare[0] - 0.5 * PX, bare[1] - 0.5 * PX, bare[0] + 0.5 * PX, bare[1] + 0.5 * PX), fill=RED, width=5)
    d.line((bare[0] - 0.5 * PX, bare[1] + 0.5 * PX, bare[0] + 0.5 * PX, bare[1] - 0.5 * PX), fill=RED, width=5)
    mark('C6241', '2', ORANGE, r=0.45)
    callout(xy(157.1, 68.25), '1. REMOVE FB6241 (all of it).  Wire R6222\'s right end\n   (+3V3) -> FB6241\'s LEFT pad ONLY (blue: VPHY).\n   RIGHT pad (red X: +1.8 V core) stays BARE: Kapton.', BLUE, xy(150.5, 54.0))
    callout(xy(155.82, 69.6), 'PROBE: C6241 left end = VPHY\nnow 1.8 V, after rework 3.3 V', ORANGE, xy(146.0, 74.5))
    # ---- job 2: D+ / D- ---------------------------------------------------------------------------------------
    dp_c, dm_c = mark('U501', '3', BLUE), mark('U501', '1', BLUE)       # connector side (right column)
    dm_f, dp_f = mark('U501', '4', BLUE), mark('U501', '6', BLUE)       # FT2232H side (left column)
    for a_, b_ in ((dp_c, dp_f), (dm_c, dm_f)):              # dashed: only if the cable cannot be used
        n = 8
        for k in range(0, n, 2):
            d.line((a_[0] + (b_[0] - a_[0]) * k / n, a_[1] + (b_[1] - a_[1]) * k / n,
                    a_[0] + (b_[0] - a_[0]) * (k + 1) / n, a_[1] + (b_[1] - a_[1]) * (k + 1) / n), fill=(120, 200, 255), width=6)
    def tag(c, t, anchor):
        box = d.textbbox(c, t, font=mid, anchor=anchor)
        d.rectangle((box[0] - 5, box[1] - 4, box[2] + 5, box[3] + 4), fill=(0, 0, 0))
        d.text(c, t, fill=(255, 255, 255), font=mid, anchor=anchor)
    for n, t, dy in (('3', 'D+ from the USB-C', -1.0), ('1', 'D- from the USB-C', 1.0)):
        p = pad('U501', n); tag(xy(p[1] + 0.2, p[2] + dy), t, 'lm')
    for n, t, dy in (('4', 'to FT2232H pin 7 (DM)', -1.0), ('6', 'to FT2232H pin 8 (DP)', 1.0)):
        p = pad('U501', n); tag(xy(p[1] - 0.2, p[2] + dy), t, 'rm')
    callout(xy(167.6, 61.2), '2. NO BOARD WORK: a USB-A-to-C cable (USB 2.0)\n   cut, its green (D+) and white (D-) wires\n   swapped, labelled "D+/D- SWAPPED: ECP5 rev A".\n'
            '   Only if no cable will do: U501 off and the two\n   dashed wires (D+ -> DP, D- -> DM).', BLUE, xy(167.0, 66.5))
    jx, jy = xy(fps['J501'][0], fps['J501'][1])
    d.text((jx - 30, jy + 6 * PX), 'J501\nUSB PROG', fill=(255, 255, 255), font=mid, anchor='mm')
    steps = ('Why: the FT2232H data sheet wants 3.0-3.6 V on VPHY (pin 4) and VPLL (pin 9); the board feeds them VREGOUT\'s 1.8 V.\n'
             'And the board joins the USB-C\'s D+ to pin 7, which is DM.  Either one alone keeps USB PROG off the PC.\n'
             'Before power, Fluke on ohms: R6222 right end to C6241 left end ~0 ohm; R6222 right end to the bare RIGHT pad of FB6241 (+1V8) NOT ~0 ohm.\n'
             'After job 1, powered: VPHY (C6241 left end) 3.3 V; the bare right pad of FB6241 1.8 V.  With the swapped cable in USB PROG the PC lists 0403:6010.\n'
             'The swapped cable keeps U501\'s ESD and touches nothing on the board.  USB USER (J502, U504) is wired right.')
    for i, s in enumerate(steps.split('\n')):
        d.text((16, TOP + H + 20 + 30 * i), s, fill=(0, 0, 0), font=font(22))
    path = os.path.join(HERE, 'figs', 'rework_ftdi.png')
    im.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE).save(path, optimize=True)
    print(path, im.size)


if __name__ == '__main__':
    main()
