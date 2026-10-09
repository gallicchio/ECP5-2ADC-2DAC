#!/usr/bin/env python3
"""What JLCPCB's placement preview will show, computed: every top-side part's EasyEDA land drawing (the one JLCPCB
places) put where ECP5-2ADC-2DAC_cpl_jlcpcb_upload.csv says, at the angle it says, and compared with the board.
For each part: how far each of their pads lands from the nearest of ours (a wrong position or a quarter turn shows
here), and whether their silkscreen outline -- the body: an SMA's barrel, a socket's housing -- lies on the same side
of the part as our courtyard (a half turn of a symmetric pad pattern shows only here).

    python3 mfg/preview_check.py            # prints the parts that would look wrong, and a count of the rest
    python3 mfg/preview_check.py OTHER_CPL.csv    # the same for another CPL (an older release, to see it fail)

Written for build 34 (Jason, 2026-10-08): build 33's preview showed the headers as 40-pin strips and the SMAs and
Pmod sockets turned, none of which any check had caught, because every check compared footprints, not placements."""
import os, sys, csv, math, re, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "pcb")); sys.path.insert(0, os.path.join(ROOT, "gen"))
import footprint_check as FC, fplib, netmap, place as P

NAME = "ECP5-2ADC-2DAC"
PAD_TOL = 0.35          # mm: a pad landing further than this from all of ours is wrong
BODY_MIN = 1.0          # mm: their outline's centre must be this far from the origin to say which way the body faces


def silk_centre(code):
    """Centre of the bounding box of their top silkscreen (layer 3), footprint-local mm, y down; None if none."""
    res, ts = FC.svgs(code)
    for r in res:
        b = r.get("svg", "")
        if 'c_partid="part_pad"' not in b and 'c_partid="part_hole"' not in b:
            continue
        body = b.split("</style>", 1)[-1]
        m = re.search(r'<g [^>]*c_origin="([-\d.]+),([-\d.]+)"', body)
        ox, oy = (float(m.group(1)), float(m.group(2))) if m else FC.ORIGIN
        xs, ys = [], []
        for pl in re.finditer(r'<polyline points="([^"]+)"[^>]*layerid="3"', body):
            v = [float(t) for t in pl.group(1).split()]
            xs += v[0::2]; ys += v[1::2]
        if not xs:
            return None
        return ((min(xs) + max(xs)) / 2 - ox) * FC.UNIT, ((min(ys) + max(ys)) / 2 - oy) * FC.UNIT
    return None


def turn(x, y, deg):
    """A counter-clockwise turn as seen on the board (y down)."""
    a = math.radians(deg)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def main():
    fps, vals, nets, numof = netmap.load(os.path.join(ROOT, "build", "netlist.net"))
    placed = json.load(open(os.path.join(ROOT, "build", "placement.json")))
    lcsc = json.load(open(os.path.join(ROOT, "build", "lcsc.json")))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "mfg", "release", NAME + "_cpl_jlcpcb_upload.csv")
    cpl = {r["Designator"]: r for r in csv.DictReader(open(path))}
    bad, ok, skipped = [], 0, 0
    lp_cache, silk_cache = {}, {}
    for ref, row in sorted(cpl.items()):
        if row["Layer"] != "top" or ref not in placed:
            skipped += 1; continue
        code = lcsc.get(ref)
        if code not in lp_cache:
            lp_cache[code] = FC.land_pattern(code)[0] if code else None
            silk_cache[code] = silk_centre(code) if code else None
        lp = lp_cache[code]
        if not lp or not lp["pads"]:
            skipped += 1; continue
        x, y, rot, layer = placed[ref]
        fp = fplib.load(fps[ref])
        ours = fplib.pads_at(fp, x, y, rot, back=False)                         # board frame, y down
        cx, cy = float(row["Mid X"].rstrip("m")) - P.OX, -float(row["Mid Y"].rstrip("m")) - P.OY
        r = float(row["Rotation"])
        worst = 0.0
        for p in lp["pads"]:
            dx, dy = turn(p["x"], p["y"], r)
            px, py = cx + dx, cy + dy
            worst = max(worst, min(math.hypot(px - q["x"], py - q["y"]) for q in ours))
        msg = []
        if worst > PAD_TOL:
            msg.append("a pad lands %.2f mm from ours" % worst)
        sc = silk_cache[code]
        if sc and math.hypot(*sc) > BODY_MIN:
            jx, jy = turn(sc[0], sc[1], r)                                       # their body's side, from their origin
            bx0, by0, bx1, by1 = fplib.box_at(fp, x, y, rot, back=False, grow=0.0)
            kx, ky = (bx0 + bx1) / 2 - cx, (by0 + by1) / 2 - cy                  # our courtyard's side, from the same point
            if math.hypot(kx, ky) > BODY_MIN:
                cosang = (jx * kx + jy * ky) / (math.hypot(jx, jy) * math.hypot(kx, ky))
                if cosang < 0.7:
                    msg.append("their body faces %.0f deg away from our courtyard" % math.degrees(math.acos(max(-1, min(1, cosang)))))
        if msg:
            bad.append("%-7s %-10s %-40s rot %-5s %s" % (ref, code, fps[ref].split(":")[-1][:40], row["Rotation"], "; ".join(msg)))
        else:
            ok += 1
    for b in bad:
        print("  WRONG  " + b)
    print("%d top-side placements land on their pads with their bodies the right way; %d look wrong; %d not checked "
          "(bottom side, or no land drawing)" % (ok, len(bad), skipped))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
