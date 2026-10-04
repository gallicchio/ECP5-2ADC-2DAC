#!/usr/bin/env python3
"""The two end plates of the Hammond 1455Q1601, with a cutout for every connector on the board's two ends.

    python3 mfg/end_panels.py            -> mfg/release/end_panel_left.{svg,dxf}, end_panel_right.{svg,dxf},
                                            end_panels.txt (every cutout's centre and size)

Reads build/placement.json (where the connectors are) and pcb/place.py (the board's size).  The drawings are
1:1 in mm, viewed FROM OUTSIDE the box, and carry the plate's outline and its four countersunk screw holes
(datasheets/Hammond_1455Q1601.pdf: plate 125.02 x 51.13 mm, holes 4 x 4.2 mm on 115.52 x 43.51 mm).  Hammond
mills end plates from a DXF ("Enclosures can be Factory Modified"); so does Front Panel Express.

ONE NUMBER TO MEASURE: PCB_TOP_ABOVE_FLOOR, the height of the board's TOP surface above the inside floor of
the extrusion, which depends on which of the extrusion's slots the board rides in (the slots are 2 mm apart,
the drawing does not number them).  The default is the lowest slot as read off the drawing; every cutout moves
up together if a higher slot is used, so measure it on the extrusion before milling.  The connectors' heights
above the board (the other number each cutout needs) come from the parts' drawings and are listed in CUTOUTS.
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "pcb"))
import place as P
import fplib
sys.path.insert(0, os.path.join(ROOT, "gen"))
import netmap

PLATE_W, PLATE_H = 125.02, 51.13                 # the end plate (Hammond drawing)
HOLE_DX, HOLE_DY, HOLE_D = 115.52, 43.51, 4.2    # its four screw holes
WALL = 2.0                                       # extrusion wall: the inside floor is 2 mm above the plate's bottom edge
PCB_TOP_ABOVE_FLOOR = 8.0                        # MEASURE THIS.  The SECOND slot from the floor: the Ethernet magnetics on the back are 4.0 +-0.4 mm tall and
                                                 # the lowest slot leaves ~4.4 mm under the board; one slot up leaves 6.4 mm
BOARD_T = 1.6

# The two USB-C jacks and the mini-HDMI stand 2.5 mm past the board edge (build 26): the plate is 1.45 mm thick and the
# board can float up to 2 mm between the plates, so their faces land within a millimetre of the plate's outer surface
# and a USB-C plug's 6.5 mm shroud always reaches.  The RJ45's and Pmods' cutouts are their whole bodies, so they may sit back.
# ref prefix -> (name, width across the panel, height, centre height above the board's top surface, shape)
# Heights above the board top are from the connectors' drawings: a plug must pass the plate into the receptacle, so
# every cutout is the receptacle's opening plus 1 mm each way (USB-C and HDMI plugs' overmoulds stay outside).
CUTOUTS = {
    "J301": ("CLK IN (SMA)", 6.5, 6.5, 3.0, "circle"),      # BWSMA-KWE-Z001: a right-angle jack, 6 x 6 mm body on the board, barrel axis 3.0 mm up, 6.2 mm thread 8.5 mm past the body
    "J302": ("CLK OUT (SMA)", 6.5, 6.5, 3.0, "circle"),
    "J101": ("ADC A IN (SMA)", 6.5, 6.5, 3.0, "circle"),
    "J102": ("ADC B IN (SMA)", 6.5, 6.5, 3.0, "circle"),
    "J205": ("DAC 2 OUT (SMA)", 6.5, 6.5, 3.0, "circle"),
    "J204": ("DAC 1 OUT (SMA)", 6.5, 6.5, 3.0, "circle"),
    "J401": ("ETHERNET (RJ45)", 16.6, 14.4, 7.0, "rect"),               # jack body 16.1 x 13.6 on the board, whole front through the plate
    "J501": ("USB PROG (USB-C)", 12.2, 6.5, 1.63, "rect"),              # receptacle opening 8.94 x 3.26 centred 1.63 above the board; the cutout takes a plug's overmould nose (the USB-C spec's maximum is 12.35 x 6.5) so the plug seats however the board sits between the plates; the webs between neighbouring cutouts are 1.1-1.4 mm
    "J502": ("USB FPGA (USB-C)", 12.2, 6.5, 1.63, "rect"),
    "J503": ("HDMI (mini)", 13.0, 7.5, 1.75, "rect"),                   # mini-HDMI opening 10.4 x 2.4; the cutout takes the plug's overmould (the jack stands only 0.75 mm past the edge)
    "J304": ("PMOD B (2x6 socket)", 17.5, 8.0, 4.6, "rect"),            # right-angle 2x6 socket, 15.2 x 8.5 body on the board
    "J303": ("PMOD A (2x6 socket)", 17.5, 8.0, 4.6, "rect"),
}


def body_centre(ref, x, y, rot, layer, fps):
    """The connector's body centre on the board (its courtyard's centre): a Pmod socket's anchor is its pin 1,
    15 mm from the body's middle."""
    x0, y0, x1, y1 = fplib.box_at(fplib.load(fps[ref]), x, y, rot, back=(layer == "B.Cu"), grow=0.0)
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def panel_coords(ref, x, y, side):
    """(u, v) of a connector's cutout centre on the plate, mm from the plate's centre, u to the viewer's right,
    v up, viewed from outside.  The board's y axis runs across the plate: looking at the RIGHT end from outside
    with the component side up, the board's +y (south in the KiCad view) is to the viewer's right; at the LEFT
    end it is to the viewer's left.  The board is centred between the slots."""
    name, w, h, zc, shape = CUTOUTS[ref]
    u = (y - P.BH / 2.0) * (1.0 if side == "right" else -1.0)
    v = (WALL + PCB_TOP_ABOVE_FLOOR + zc) - PLATE_H / 2.0
    return u, v


def svg(path, side, items):
    W, H = PLATE_W, PLATE_H
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%.2fmm" height="%.2fmm" viewBox="%.2f %.2f %.2f %.2f">' % (W + 20, H + 30, -W / 2 - 10, -H / 2 - 20, W + 20, H + 30),
           '<g transform="scale(1,-1)" fill="none" stroke="black" stroke-width="0.2">',
           '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="3" />' % (-W / 2, -H / 2, W, H)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            out.append('<circle cx="%.2f" cy="%.2f" r="%.2f" />' % (sx * HOLE_DX / 2, sy * HOLE_DY / 2, HOLE_D / 2))
    for (ref, name, u, v, w, h, shape) in items:
        if shape == "circle":
            out.append('<circle cx="%.2f" cy="%.2f" r="%.2f" />' % (u, v, w / 2))
        else:
            out.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="0.8" />' % (u - w / 2, v - h / 2, w, h))
        k = items.index((ref, name, u, v, w, h, shape))
        ty = v + h / 2 + 2.0 + 3.0 * (k % 2)          # labels above the cutouts, alternately 2 and 5 mm up so neighbours do not collide
        out.append('<g transform="translate(%.2f,%.2f) scale(1,-1)"><text x="0" y="0" font-size="2" text-anchor="middle" fill="black" stroke="none">%s</text></g>' % (u, ty, name))
    out.append('</g>')
    out.append('<g transform="scale(1,-1)"><g transform="translate(%.2f,%.2f) scale(1,-1)"><text font-size="2.5" fill="black">%s END PLATE, viewed from OUTSIDE, 1:1 mm. Board top %.1f mm above the inside floor (slot: measure).</text></g></g>'
               % (-W / 2, -H / 2 - 8, side.upper(), PCB_TOP_ABOVE_FLOOR))
    out.append('</svg>')
    open(path, "w").write("\n".join(out))


def dxf(path, items):
    """A minimal R12 DXF: the plate outline, the holes, the cutouts (circles and closed polylines), in mm."""
    e = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "4", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    def line(x0, y0, x1, y1, layer="OUTLINE"):
        e.extend(["0", "LINE", "8", layer, "10", "%.3f" % x0, "20", "%.3f" % y0, "11", "%.3f" % x1, "21", "%.3f" % y1])
    def circle(x, y, r, layer):
        e.extend(["0", "CIRCLE", "8", layer, "10", "%.3f" % x, "20", "%.3f" % y, "40", "%.3f" % r])
    W, H = PLATE_W, PLATE_H
    for (x0, y0, x1, y1) in ((-W / 2, -H / 2, W / 2, -H / 2), (W / 2, -H / 2, W / 2, H / 2), (W / 2, H / 2, -W / 2, H / 2), (-W / 2, H / 2, -W / 2, -H / 2)):
        line(x0, y0, x1, y1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            circle(sx * HOLE_DX / 2, sy * HOLE_DY / 2, HOLE_D / 2, "HOLES")
    for (ref, name, u, v, w, h, shape) in items:
        if shape == "circle":
            circle(u, v, w / 2, "CUTOUTS")
        else:
            x0, y0, x1, y1 = u - w / 2, v - h / 2, u + w / 2, v + h / 2
            for (a, b, c, d) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
                line(a, b, c, d, "CUTOUTS")
    e.extend(["0", "ENDSEC", "0", "EOF"])
    open(path, "w").write("\n".join(e) + "\n")


def main():
    placed = json.load(open(os.path.join(ROOT, "build", "placement.json")))
    fps, vals, nets, numof = netmap.load(os.path.join(ROOT, "build", "netlist.net"))
    out = os.path.join(HERE, "release")
    os.makedirs(out, exist_ok=True)
    report = ["End plates for the Hammond 1455Q1601 (plate %.2f x %.2f mm, holes %.1f mm on %.2f x %.2f).  Viewed from outside; u right, v up, from the plate's centre."
              % (PLATE_W, PLATE_H, HOLE_D, HOLE_DX, HOLE_DY),
              "Board %.0f x %.0f mm, top surface %.1f mm above the inside floor (PCB_TOP_ABOVE_FLOOR: measure the slot before milling)." % (P.BW, P.BH, PCB_TOP_ABOVE_FLOOR), ""]
    for side in ("left", "right"):
        items = []
        for ref, (name, w, h, zc, shape) in CUTOUTS.items():
            if ref not in placed:
                continue
            x, y, rot, layer = placed[ref]
            xc, yc = body_centre(ref, x, y, rot, layer, fps)
            at_left = x < P.BW / 2.0
            y = yc
            if (side == "left") != at_left:
                continue
            u, v = panel_coords(ref, x, y, side)
            items.append((ref, name, u, v, w, h, shape))
            report.append("%-5s %-22s %-6s u %+7.2f  v %+7.2f  %s %.1f x %.1f" % (ref, name, side, u, v, shape, w, h))
        items.sort(key=lambda it: it[2])
        svg(os.path.join(out, "end_panel_%s.svg" % side), side, items)
        dxf(os.path.join(out, "end_panel_%s.dxf" % side), items)
        # a sanity check: no two cutouts overlap, none leaves the plate
        for i, a in enumerate(items):
            if abs(a[2]) + a[4] / 2 > PLATE_W / 2 - 1.0 or abs(a[3]) + a[5] / 2 > PLATE_H / 2 - 1.0:
                report.append("  WARNING: %s runs off the plate" % a[0])
            for b in items[i + 1:]:
                if abs(a[2] - b[2]) < (a[4] + b[4]) / 2 + 1.0 and abs(a[3] - b[3]) < (a[5] + b[5]) / 2 + 1.0:
                    report.append("  WARNING: %s and %s cutouts are within 1 mm of each other" % (a[0], b[0]))
    open(os.path.join(out, "end_panels.txt"), "w").write("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()
