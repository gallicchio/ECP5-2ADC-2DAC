#!/usr/bin/env python3
"""The bring-up's cabling pictures: bringup/figs/visit*.png, one per physical configuration of BRINGUP.md.

    python3 bringup/make_figs.py

Each is the board's own 3D render (docs/images/render-top.png, which every build regenerates) as it lies on the
bench, SMAs to the left, with a ring round each place a cable or a probe goes and a label saying what goes there.
Positions come from build/placement.json (board millimetres), so a moved part moves its ring; the render shows the
whole board with nothing else opaque in it, so millimetres map straight to pixels (the mapping is checked below against
the picture's own opaque area).
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
BOARD_W, BOARD_H = 158.0, 119.0                      # mm (README.md)
SCALE = 1.5                                          # the render is 1376 px wide: enlarged so the labels read on a phone
MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 520, 560, 90, 120

RED, BLUE, GREEN, ORANGE, PURPLE, GREY = (220, 40, 40), (40, 90, 220), (20, 150, 60), (230, 130, 0), (150, 60, 190), (90, 90, 90)


def font(size, bold=False):
    for name in (('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'),):
        for d in ('/usr/share/fonts/truetype/dejavu/', '/usr/share/fonts/dejavu/'):
            if os.path.exists(d + name):
                return ImageFont.truetype(d + name, size)
    return ImageFont.load_default()


class Fig:
    def __init__(self, title, subtitle=''):
        src = Image.open(os.path.join(PROJECT, 'docs', 'images', 'render-top.png')).convert('RGBA')
        # the board is the dark green rectangle: its bounding box in the render, found from the pixels
        px = src.load(); w, h = src.size
        xs = [x for x in range(w) if sum(1 for y in range(0, h, 4) if _is_board(px[x, y])) > h // 16]
        ys = [y for y in range(h) if sum(1 for x in range(0, w, 4) if _is_board(px[x, y])) > w // 16]
        self.bx0, self.bx1, self.by0, self.by1 = min(xs), max(xs), min(ys), max(ys)
        assert abs((self.bx1 - self.bx0) / (self.by1 - self.by0) - BOARD_W / BOARD_H) < 0.02, 'the render is not the whole board'
        crop = src.crop((self.bx0 - 70, self.by0 - 20, self.bx1 + 20, self.by1 + 20))
        self.ox, self.oy = 70, 20                      # the board's corner inside the crop
        self.k = (self.bx1 - self.bx0) / BOARD_W * SCALE
        crop = crop.resize((int(crop.width * SCALE), int(crop.height * SCALE)), Image.LANCZOS)
        self.im = Image.new('RGB', (crop.width + MARGIN_L + MARGIN_R, crop.height + MARGIN_T + MARGIN_B), (255, 255, 255))
        self.im.paste(crop, (MARGIN_L, MARGIN_T), crop)
        self.d = ImageDraw.Draw(self.im)
        self.d.text((20, 14), title, fill=(0, 0, 0), font=font(34, True))
        if subtitle:
            self.d.text((20, 54), subtitle, fill=(60, 60, 60), font=font(22))
        self.taken = {'L': [], 'R': []}
        self.place = json.load(open(os.path.join(PROJECT, 'build', 'placement.json')))

    def xy(self, where, dx=0.0, dy=0.0):
        x, y = (self.place[where][0], self.place[where][1]) if isinstance(where, str) else where
        return (MARGIN_L + (self.ox * SCALE) + (x + dx) * self.k, MARGIN_T + (self.oy * SCALE) + (y + dy) * self.k)

    def ring(self, where, color, r=4.5, dx=0.0, dy=0.0, box=None):
        x, y = self.xy(where, dx, dy)
        if box:
            w, h = box[0] * self.k / 2, box[1] * self.k / 2
            self.d.rectangle((x - w, y - h, x + w, y + h), outline=color, width=5)
        else:
            rr = r * self.k
            self.d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=color, width=5)
        return x, y

    def label(self, where, text, color, side, r=4.5, dx=0.0, dy=0.0, box=None, y_slot=None):
        """A ring (or box) at `where` and a label in the left or right margin, joined by a line."""
        x, y = self.ring(where, color, r, dx, dy, box)
        f = font(21, True)
        lines = text.split('\n')
        h = 27 * len(lines) + 14
        w = max(self.d.textlength(s, font=f) for s in lines) + 20
        want = (y_slot if y_slot is not None else y) - h / 2
        ly = max(MARGIN_T + 4, want)
        for (a, b2) in sorted(self.taken[side]):          # move down past any label already there
            if ly < b2 + 8 and ly + h > a - 8:
                ly = b2 + 8
        self.taken[side].append((ly, ly + h))
        lx = 14 if side == 'L' else self.im.width - MARGIN_R + 14 + 0
        if side == 'L':
            lx = max(8, MARGIN_L - 30 - w)
        self.d.rectangle((lx, ly, lx + w, ly + h), outline=color, width=3, fill=(255, 255, 255))
        for i, s in enumerate(lines):
            self.d.text((lx + 10, ly + 7 + 27 * i), s, fill=color, font=f)
        edge = (lx + w, ly + h / 2) if side == 'L' else (lx, ly + h / 2)
        rim = (box[0] * self.k / 2 if box else r * self.k)
        self.d.line((edge[0], edge[1], x - rim if side == 'L' else x + rim, y), fill=color, width=4)

    def jumper(self, a, b, color, text, bulge=10.0, text_bulge=34.0):
        """An SMA cable from connector a to connector b, drawn as a loop off the left edge; its name stands left of
        every loop (text_bulge), level with the middle of its own."""
        xa, ya = self.xy(a, dx=-6.5); xb, yb = self.xy(b, dx=-6.5)
        self.ring(a, color, 4.5, dx=-3.0); self.ring(b, color, 4.5, dx=-3.0)
        x_out = xa - bulge * self.k
        self.d.line((xa, ya, x_out, ya, x_out, yb, xb, yb), fill=color, width=9, joint='curve')
        f = font(21, True)
        w = self.d.textlength(text, font=f)
        tx, ty = xa - text_bulge * self.k - w - 14, (ya + yb) / 2 - 14
        self.d.line((tx + w + 8, ty + 13, x_out, ty + 13), fill=color, width=3)
        self.d.rectangle((tx - 8, ty - 6, tx + w + 8, ty + 32), fill=(255, 255, 255), outline=color, width=3)
        self.d.text((tx, ty), text, fill=color, font=f)

    def note(self, text, color=(0, 0, 0)):
        f = font(21)
        y = self.im.height - MARGIN_B + 18
        self.d.rectangle((MARGIN_L, y - 8, self.im.width - MARGIN_R, self.im.height - 6), fill=(255, 255, 235))
        for i, s in enumerate(text.split('\n')):
            self.d.text((MARGIN_L + 10, y + 27 * i), s, fill=color, font=f)

    def save(self, name):
        os.makedirs(os.path.join(HERE, 'figs'), exist_ok=True)
        path = os.path.join(HERE, 'figs', name)
        # 128 colours: a third of the full-colour PNG's size, and the labels stay sharp (these files are in git)
        self.im.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE).save(path, optimize=True)
        print(path, self.im.size)
        return path


def _is_board(p):
    r, g, b, a = p
    return a > 128 and g > r + 8 and g > b + 4 and r < 90        # the solder mask's green


def main():
    # ---- the map: every place the plan names ------------------------------------------------------------------
    f = Fig('ECP5-2ADC-2DAC: where things are', 'the board as it lies on the bench: SMAs to the left, USB and Ethernet to the right')
    for ref, t in (('J301', 'CLK IN'), ('J302', 'CLK OUT'), ('J101', 'ADC A IN'), ('J102', 'ADC B IN'), ('J204', 'DAC 1 OUT'), ('J205', 'DAC 2 OUT')):
        f.label(ref, 'SMA  ' + t, BLUE, 'L', dx=-3.0)
    f.label('SW101', 'SW101 noise resistors\n(all OFF)', GREY, 'L', box=(10, 9))
    f.label('J401', 'RJ45  ETHERNET', GREEN, 'R', box=(17, 17))
    f.label('J501', 'USB-C  "USB PROG" (upper)\npower, JTAG, serial', RED, 'R', box=(9, 10), dx=-3)
    f.label('J502', 'USB-C  "USB USER" (lower)', ORANGE, 'R', box=(9, 10), dx=-3)
    f.label('J503', 'mini-HDMI', PURPLE, 'R', box=(9, 12), dx=-3)
    f.label('J304', 'PMOD B', GREY, 'R', box=(12, 20))
    f.label('J303', 'PMOD A', GREY, 'R', box=(12, 20))
    f.label('J601', 'J601  "5 V IN" bench header\n(2 pins: +5V and GND as printed)', RED, 'R', box=(5, 8))
    f.label('J602', 'J602  RAILS header\ntop row GND (under the printed names),\nbottom row the 9 rails', ORANGE, 'L', box=(26, 7), dx=11.5)
    f.label('SW301', 'BTN0 (upper), BTN1 (lower)', GREY, 'L', box=(8, 16), dy=4.2)
    f.note('The microSD socket (J504) is on the back, under the area between the FPGA and PMOD B; the card slides in from the right.\n'
           'Eight red POWER LEDs sit in a row just right of the RAILS header; eight white LEDs along the top edge.')
    f.save('map.png')

    # ---- Visit 0: the jumpers --------------------------------------------------------------------------------------
    f = Fig('Visit 0: the jumpers before any power', 'ten shunts; everything else stays off the board')
    f.label('JP3001', 'JP3001 TERM (CLK IN): shunt IN', BLUE, 'L', box=(6, 4))
    f.label('JP103', 'JP103 GAIN (A, stage 1): shunt IN = x1', BLUE, 'L', box=(6, 4))
    f.label('JP101', 'JP101 TERM (A): shunt IN = 50 ohm', BLUE, 'L', box=(6, 4))
    f.label('JP102', 'JP102 SRC (A): shunt on the SMA side', GREEN, 'L', box=(8, 4))
    f.label('JP203', 'JP203 GAIN (B, stage 1): shunt IN = x1', BLUE, 'L', box=(6, 4))
    f.label('JP201', 'JP201 TERM (B): shunt IN = 50 ohm', BLUE, 'L', box=(6, 4))
    f.label('JP202', 'JP202 SRC (B): shunt on the SMA side', GREEN, 'L', box=(8, 4))
    f.label('JP2009', 'JP2009 LED: NO shunt (open)', RED, 'L', box=(8, 4))
    f.label('SW101', 'SW101: all four OFF', GREY, 'L', box=(10, 9))
    f.label('JP104', 'JP104 GAIN (A, stage 2): shunt IN = x1', BLUE, 'R', box=(6, 4))
    f.label('JP204', 'JP204 GAIN (B, stage 2): shunt IN = x1', BLUE, 'R', box=(6, 4))
    f.label('JP1203', 'JP1203 ALT (B): shunt on the PD side', GREEN, 'R', box=(8, 4))
    f.label('JP501', 'JP501 FTDI OFF: NO shunt (open)', RED, 'R', box=(5, 5))
    f.note('Blue = a 2-pin jumper with its shunt IN.  Green = a 3-pin jumper: the shunt joins the middle pin to the side named.\n'
           'Red = leave OPEN.  Every jumper has its choices printed beside it on the board.')
    f.save('visit0_jumpers.png')

    # ---- Visit 1a: first power ---------------------------------------------------------------------------------------
    f = Fig('Visit 1, step A: power only', 'one lead pair from the supply; the Fluke in your hands; NO USB yet')
    f.label('J601', 'E3646A  OUTPUT 1, short thick leads\n(no BNC, no thin wire)\nred (+) -> UPPER pin (+5V)\nblack (-) -> LOWER pin (GND,\nnearer the bottom edge)', RED, 'R', box=(5, 8))
    f.label('J602', 'Fluke 45, red probe:\nthe nine BOTTOM-row pins,\nleft to right, 3 s each:\n+5V  +3V3  +1V1  +2V5  3V3A\n3V3D  +5VA  1V0  -4V2\nblack probe: any TOP-row pin\n(all GND, though the names\nare printed above it)', ORANGE, 'L', box=(26, 7), dx=11.5)
    f.label('D602', 'eight red POWER LEDs:\nall lit?', RED, 'R', box=(26, 5), dx=10.5)
    f.note('Nothing on any SMA, USB, Ethernet or Pmod.  The supply is switched on from the PC, not by hand.')
    f.save('visit1a_power.png')

    # ---- Visit 1b: USB and the self-test cables -------------------------------------------------------------------------
    f = Fig('Visit 1, step B: USB and the self-test cables', 'after this you can leave: everything here runs without instruments')
    f.jumper('J302', 'J301', BLUE, 'SMA cable 1', bulge=9)
    f.jumper('J204', 'J101', GREEN, 'SMA cable 2', bulge=20)
    f.jumper('J205', 'J102', ORANGE, 'SMA cable 3', bulge=31)
    f.label('J401', 'Ethernet cable\nto the lab switch (192.168.8.x)', GREEN, 'R', box=(17, 17))
    f.label('J501', 'USB-C cable 1 to the PC (bell)\ninto "USB PROG" (the UPPER one)', RED, 'R', box=(9, 10), dx=-3)
    f.label('J502', 'USB-C cable 2 to the PC (bell)\ninto "USB USER" (the lower one)', ORANGE, 'R', box=(9, 10), dx=-3)
    f.label((114.0, 84.0), 'microSD card: in the socket\non the BACK (any card;\nnothing is written to it)', PURPLE, 'R', box=(16, 14))
    f.label('J601', 'E3646A OUTPUT 1 stays\n(+ to +5V, - to GND)', RED, 'R', box=(5, 8))
    f.note('SMA cable 1: CLK OUT -> CLK IN.   SMA cable 2: DAC 1 OUT -> ADC A IN.   SMA cable 3: DAC 2 OUT -> ADC B IN.\n'
           'If cables 2 and 3 end up crossed, say nothing: the software finds out which is where.')
    f.save('visit1b_selftest.png')

    # ---- Visit 2: the references ---------------------------------------------------------------------------------------
    f = Fig('Visit 2: generators and scope', 'the three SMA cables come off; six instrument cables go on')
    f.label('J301', 'SDG1032X  CH2  ->  CLK IN', PURPLE, 'L', dx=-3.0)
    f.label('J302', 'SDS2104X Plus  CH3  <-  CLK OUT', BLUE, 'L', dx=-3.0)
    f.label('J101', 'SDG1032X  CH1  ->  ADC A IN', PURPLE, 'L', dx=-3.0)
    f.label('J102', '33220A  Output  ->  ADC B IN', ORANGE, 'L', dx=-3.0)
    f.label('J204', 'SDS2104X Plus  CH1  <-  DAC 1 OUT', BLUE, 'L', dx=-3.0)
    f.label('J205', 'SDS2104X Plus  CH2  <-  DAC 2 OUT', BLUE, 'L', dx=-3.0)
    f.label('J107', 'optional: U.FL pigtail  TAP A\n->  SDS2104X Plus  CH4', BLUE, 'R', r=2.5)
    f.label('J601', 'E3646A OUTPUT 1 stays', RED, 'R', box=(5, 8))
    f.label('J501', 'USB PROG, USB USER, Ethernet,\nmicroSD: all stay', GREY, 'R', box=(9, 10), dx=-3)
    f.note('Scope inputs: plain BNC cables (not the 10x probes).  Generator outputs are switched on from the PC, at low level first,\n'
           'and each cable is checked by what it does before any full-level signal is sent.')
    f.save('visit2_instruments.png')

    # ---- Visit 3: hands on -------------------------------------------------------------------------------------------------
    f = Fig('Visit 3: the places the sit-down session names', 'one change at a time; each step says which one')
    f.label('JP103', 'JP103, JP104: GAIN of channel A\n(shunt out = x10 each)', BLUE, 'L', box=(6, 4))
    f.label('JP101', 'JP101: TERM A', BLUE, 'L', box=(6, 4))
    f.label('JP102', 'JP102: SRC A  (SMA | NOISE)', GREEN, 'L', box=(8, 4))
    f.label('JP202', 'JP202: SRC B  (SMA | ALT)', GREEN, 'L', box=(8, 4))
    f.label('JP1203', 'JP1203: ALT of B  (PD | NOISE)', GREEN, 'L', box=(8, 4))
    f.label('JP2009', 'JP2009: LED  (on-board LED | EXT)', RED, 'L', box=(8, 4))
    f.label('SW101', 'SW101: noise resistor\n0 / 100 / 1k / 10k', GREY, 'L', box=(10, 9))
    f.label('J107', 'TAP A (U.FL)', BLUE, 'R', r=2.5)
    f.label('J108', 'TAP B (U.FL)', BLUE, 'R', r=2.5)
    f.label('SW303', 'SW303 PROG (reboots the FPGA)', GREY, 'R', r=3.5)
    f.label('J109', 'TAP TIA (U.FL)', BLUE, 'R', r=2.5)
    f.label('J602', 'RAILS: scope probes on\n+3V3 (2nd pin) and +1V1 (3rd pin)', ORANGE, 'R', box=(26, 7), dx=11.5)
    f.label('J603', 'TAP -4V2 (U.FL)', BLUE, 'R', r=2.5)
    f.save('visit3_places.png')


if __name__ == '__main__':
    main()
