#!/usr/bin/env python3
"""How a KiCad placement becomes a JLCPCB CPL rotation.  THE SOURCE OF TRUTH.

Import this; do not re-derive it.  It is the accumulated result of reading
JLCPCB's "Confirm parts placement" preview on real uploads, and every number
in it cost somebody a look at a screenshot.

    from jlc_rotation import cpl_rotation
    rot = cpl_rotation(native_degrees, side, footprint_name)

TWO INDEPENDENT THINGS, APPLIED IN THIS ORDER:

  1. the bottom-side mirror, a property of how JLCPCB reads the BOARD;
  2. a per-footprint correction, a property of JLCPCB's PARTS LIBRARY.

Order matters and is not arbitrary -- see BOTTOM_FLIP.  Getting it backwards
moves parts that are known good.

WHAT THIS IS FOR NEXT.  The six-layer maximal board carries the Icepi Zero's
own parts plus the ADC, DAC, Ethernet and sample-clock PLL.  Every footprint
below appears on it, so every line here is a line that board does not have to
learn again -- and `jlcbuild/parts.py` has the LCSC part number for all 32 of
the Icepi Zero's distinct parts, which is the other half of the same saving.
"""

import sys


# ---------------------------------------------------------------------------
# JLCPCB placement rotation.  KiCad's zero for a footprint and JLCPCB's zero
# for the same part in their feeder are different things, and the offset is a
# property of THEIR library: it cannot be derived from anything here.  The
# only authority is their "Confirm parts placement" preview.
#
# So this table is SHORT on purpose.  It holds corrections that were read off
# a real preview, and nothing else.  The GPSDO board took its numbers from a
# third-party table instead and got two wrong, one of them on 59 placements.
# Everything not listed goes into PLACEMENT_CHECKS.txt to be looked at.
# Positive is counter-clockwise, which is both KiCad's sign and JLCPCB's.
# "90 clockwise" therefore lands here as 270.
#
#   footprint: (correction, confidence, who said so and what they saw)
JLC_ROTATION = {
    "SOT-23-5":
        (180, "sure", "GPSDO board's preview, where this footprint appears 59 "
              "times.  Not contradicted on this board: it was already "
              "corrected in the CPL Jason uploaded and he did not flag it"),
    # Zero, and checked.  All eight of these are on the bottom and all eight
    # were read in the preview: the vertical ones were right and the
    # horizontal ones were wrong, which is what identified BOTTOM_FLIP.  The
    # footprint itself needs no correction -- the error was the placement
    # frame, not JLCPCB's part.
    "D_SOD-523":
        (0, "read-twice", "Jason, bottom preview: \"The ones oriented "
            "vertically are correct: D10 D11 D13.  The horizontal ones are "
            "incorrect: D6 D7 D8 D9 D12\".  Fixed by BOTTOM_FLIP, not by a "
            "correction here"),
    "VSSOP-8_2.3x2mm_P0.5mm":
        (180, "sure", "Jason, JLCPCB placement preview: \"U6 needs an "
              "additional 180 degree rotation\""),
    "Texas_DRT-3":
        (270, "sure-on-top", "Jason: \"U7,U8 need 90 clockwise\".  U7 and U8 "
              "are the TOP-side pair.  U5 and U10 are the same footprint on "
              "the BOTTOM and were not in view -- see PLACEMENT_CHECKS"),
    "TSOP-II-54_22.2x10.16mm_P0.8mm":
        (270, "sure", "Jason: \"U11 needs 90 clockwise\""),
    "QFN-20-1EP_4x4mm_P0.5mm_EP2.5x2.5mm":
        # 180 on the first reading, then +90 CCW more on the second.  The
        # board wants U9's pin 1 at the SOUTH-WEST corner -- pad 1 is 1.00 mm
        # west and 1.94 mm south of centre, and the library's own triangle is
        # 2.28 west and 2.11 south, so both agree.  With 180 applied JLCPCB's
        # preview still showed their pin 1 at the north-west.  Adding to the
        # rotation walks pin 1 counter-clockwise, SE -> NE -> NW -> SW, so
        # NW needs one more quarter turn to reach SW.
        (270, "read-twice", "Jason, second preview: \"rotate U9 an additional "
              "90 degrees CCW so that the purple dot will line up with the "
              "silkscreen triangle in the SW\".  First reading was 180"),
    "SOIC-8_5.3x5.3mm_P1.27mm":
        (270, "sure", "Jason, first preview: \"U12 probably needs 90 "
              "clockwise if its pin 1 is supposed to be NE\".  Confirmed on "
              "the second: \"U12, the SOIC8, now looks right\""),
    # ZERO, and listed rather than left out.  Absent from this table means
    # nobody has looked; a zero here means somebody looked twice and it needs
    # nothing.  First reading was "seems to need 90 counter clockwise, but
    # it's hard to tell with all of the dots" -- there were thirteen dots
    # then and there is one now.  Second reading, with the correction
    # applied: "should still be rotated 90 CW more", and 90 CCW then 90 CW is
    # where it started.  It agrees with the geometry: pin 1 is Y1's
    # south-west corner, the preview showed their dot at the south-east, and
    # south-east turned a quarter clockwise is south-west.
    "Oscillator_SMD_SiT_PQFN-4Pin_2.5x2.0mm":
        (0, "read-twice", "Jason, second preview: \"Y1 seems wrong like it "
            "should still be rotated 90 CW more than it is in the corrected "
            "CPL\".  First reading was 90 CCW; the two cancel"),
}
# Per PART, read in a preview or predicted from JLCPCB's own drawing (see
# correction()).  JLCPCB draws the SN75160B lying down and the SN75161B upright
# on the same SOIC-20W (GPiBridge, 2026-10-06), so a part can need what its
# footprint does not.  Absent here and above means nobody has looked; a
# "predicted" entry is make_fab.py's own reading of the EasyEDA drawing, by pin
# number, and PLACEMENT_CHECKS.txt lists every one of them for the preview.
#   LCSC code: (correction, confidence, why)
JLC_ROTATION_BY_PART = {
    # "derived": our footprint IS JLCPCB's drawing (EasyEDA's, converted), so their zero is ours by construction
    "C88374": (0, "derived", "U.FL: our footprint is JLCPCB's own drawing with its pad 3 renamed 2 (both grounds are 2)"),
    "C145262": (0, "derived", "photodiode VBPW34S: our footprint is JLCPCB's drawing with the pads renumbered (ours: 1 = cathode); "
                              "the part sits as their library draws it, their pad 1 (anode) on the -4.2 V side"),
    # READ in JLCPCB's placement viewer (Jason, 2026-10-08, build 34): at +0 D201 showed its "-" and corner triangle on the
    # left, where our pad 1 (the cathode, the large pad) is on the right.  Their viewer draws this LED a half turn from
    # their own land drawing, so "our footprint is their drawing" did not make +0 right.
    "C2843878": (180, "read", "2835 LED XL-2835SURC-05: +0 showed the cathode on the anode's side in build 34's preview (Jason, 2026-10-08); +180"),
    # "predicted" by the POLARITY MARK in JLCPCB's drawing (the EasyEDA record's png, read 2026-10-06): the
    # cathode ("-", the bar or chamfer) on the LEFT at 0, where KiCad's pad 1 (the cathode) is.  A fit by pad
    # number would say 180 on these, since JLCPCB numbers the cathode 2 (GPiBridge's KT-0805 lesson).
    "C2290": (0, "predicted", "KT-0603W white LED, by the mark: cathode left in both drawings"),
    "C2286": (0, "predicted", "0603 red LED, by the mark: cathode left in both drawings"),
    "C12624": (0, "predicted", "0603 green LED, by the mark: cathode left in both drawings"),
    "C81598": (0, "predicted", "1N4148W SOD-123, by the mark: cathode bar left in both drawings"),
    "C8598": (0, "predicted", "B5819W SOD-123, by the mark: cathode bar left in both drawings"),
    # read from JLCPCB's land drawing and the preview of build 33 (2026-10-08): these number their pins differently from
    # KiCad, so no fit by pin number predicts them, and builds 1-33 sent them at +0 -- the preview showed every SMA lying
    # along the board edge and both Pmod sockets standing a quarter turn round.  The body is the cue, not the pins.
    "C492401": (270, "predicted", "1x2 header PZ254V-11-02P: JLCPCB's drawing lies along +x with pin 1 left, KiCad's stands along +y with pin 1 at the top (the 1x3, 1x6 and 2x9 headers predict 270 by pin number; two pads predict nothing)"),
    "C496551": (90, "predicted", "edge SMA BWSMA-KWE-Z001: JLCPCB's drawing has the barrel along +x at 0, KiCad's along -y (its courtyard runs 12 mm up); +0 put them along the edge in build 33's preview"),
    "C22373932": (270, "predicted", "2x6 right-angle Pmod socket: JLCPCB's drawing has the body below the pin rows at 0, KiCad's to the left of its pin columns; +0 stood them a quarter turn round in build 33's preview"),
    "C8678": (0, "predicted", "SS34 SMA (build 32), by the mark: the band and the '-' on the left pad at 0 deg in JLCPCB's land drawing, the bar on the left in its symbol; KiCad's D_SMA has pad 1 (cathode) on the left"),
}

# HOW THIS BOARD STORES ITS BOTTOM-SIDE FOOTPRINTS, and why it matters here.
#
# BOTTOM_FLIP below was read off a board KiCad itself had flipped: KiCad
# mirrors a flipped footprint's pads TOP-TO-BOTTOM (y negated) and that is
# what the Icepi file holds.  pcb/board.py writes this board's back-side
# footprints mirrored LEFT-TO-RIGHT instead (x negated; U604's pad 1 is at
# +1.1375 where U601's is at -1.1375), which is equally valid to KiCad -- the
# file holds the pads where they are -- but the SAME physical placement then
# carries a stored angle 180 degrees from KiCad's own, because a left-right
# mirror is a top-bottom mirror turned half way round.  So the angle this
# board stores must be turned by 180 to be the "native" angle BOTTOM_FLIP
# expects; make_fab.py checks the file's convention (verify_bottom_convention)
# before trusting this flag.  For the stored angle s that makes the CPL
# rotation 180 - (s + 180) = -s.  Untested in a preview on this board: every
# polarized bottom part is listed in PLACEMENT_CHECKS.txt to look at hardest.
BOTTOM_STORED_X_MIRRORED = True

# BOTTOM-SIDE PLACEMENTS ARE MIRRORED: rot -> 180 - rot, and it is CONFIRMED.
#
# KiCad reports a bottom footprint's angle in the board's top-view frame.
# JLCPCB wants it the other way up.  The transform is not a negation, which
# is what I guessed first and what the diodes refuted: it is 180 - rot, whose
# fixed points are 90 and 270 rather than 0 and 180.
#
# It is the unique transform consistent with every bottom-side observation
# anybody has made on this board, and there are ten of them:
#
#   must change by 180   D6 180, D7 0, D8 0, D9 180, D12 0   Jason: the
#                        horizontal diodes are the wrong ones
#   must NOT change      D10 90, D11 90, D13 270             the vertical
#                        ones are right
#   must NOT change      U5 270, U10 90                      confirmed good
#                        earlier, and they carry a +270 footprint correction
#
# Negation fits none of it.  Adding 180 fits none of it.  180 - rot fits all
# ten, and only when it is applied to the NATIVE angle BEFORE the per-
# footprint correction -- applied afterwards it moves U5 and U10, which are
# known good.  That ordering is also the one that makes sense: the mirror is
# a property of how bottom-side geometry maps into their frame, and the
# footprint correction is a property of their parts library.  Coordinate
# first, library offset on top.
#
# My prediction was the exact opposite of what Jason saw, which is worth more
# than a confirmation would have been: a negation and a flip are
# indistinguishable on 0 and 180, and every bottom part checked before the
# diodes happened to sit there.
BOTTOM_FLIP = True

# Two-terminal and unpolarised: which way round is not a question.
ROTATION_NA = ("R_0402_1005Metric", "R_0201_0603Metric", "C_0402_1005Metric",
               "C_0603_1608Metric", "L_0805_2012Metric",
               # the ECP5-2ADC-2DAC board's two-terminal and electrically symmetric parts (a 3225 crystal's pads 1/3
               # are the crystal and 2/4 the case either way round; the 4030 inductor and the 1812 fuse have two)
               "R_0603_1608Metric", "C_0402_1005Metric_BGA", "C_0805_2012Metric", "C_1206_3216Metric",
               "L_0603_1608Metric", "Fuse_1812_4532Metric", "IND-SMD_L4.0-W4.0", "Crystal_SMD_3225-4Pin_3.2x2.5mm",
               "SW-SMD_L3.9-W3.0-P4.45",
               # (the 2.54 mm pin headers are NOT here since build 34: a header is the same turned half way round but
               # not a quarter -- JLCPCB draws them lying along x, KiCad standing along y -- so they need a correction)
               # two-terminal and unpolarised, build 26's parts
               "C_1812_4532Metric", "R_1206_3216Metric")

def correction(footprint, code=None):
    """(degrees, confidence, why) for one part: per part first, then per footprint, else (0, "none", "")."""
    if code in JLC_ROTATION_BY_PART:
        return JLC_ROTATION_BY_PART[code]
    return JLC_ROTATION.get(footprint, (0, "none", ""))


def cpl_rotation(native_deg, side, footprint, code=None, predicted=None, stored_x_mirrored=None):
    """The number that goes in JLCPCB's CPL for one placement.

    `native_deg` is the footprint orientation this board's file stores, `side`
    is "top" or "bottom", `footprint` the footprint's short name, `code` its
    LCSC code.  `predicted` is a correction read off JLCPCB's drawing by
    make_fab.py; it is used only where nobody has read the part in a preview.
    """
    rot = float(native_deg) % 360.0
    if stored_x_mirrored is None:
        stored_x_mirrored = BOTTOM_STORED_X_MIRRORED
    if side == "bottom":
        if stored_x_mirrored:
            rot = (rot + 180.0) % 360.0          # to KiCad's own (top-bottom mirrored) convention first
        if BOTTOM_FLIP:
            rot = (180.0 - rot) % 360.0
    corr, conf, why = correction(footprint, code)
    if conf == "none" and predicted is not None:
        corr = predicted
    return round((rot + corr) % 360.0, 4)


def checked(footprint, code=None):
    """Has anybody looked at this part in a placement preview?"""
    if code in JLC_ROTATION_BY_PART:
        return JLC_ROTATION_BY_PART[code][1] not in ("predicted", "none")
    return footprint in JLC_ROTATION or footprint in ROTATION_NA


def verify_bottom_convention(pcb_path):
    """Read the board file: do its back-side footprints hold their pads
    mirrored left-right (x negated, this board's writer) or top-bottom (y
    negated, KiCad's own flip)?  Compared on a footprint that appears on both
    sides.  Raises if the file disagrees with BOTTOM_STORED_X_MIRRORED, since
    every bottom-side CPL rotation would then be 180 degrees out."""
    import re as _re
    s = open(pcb_path, encoding="utf-8").read()
    inst = {}
    for blk in s.split("(footprint ")[1:]:
        name = _re.match(r'"([^"]+)"', blk)
        lay = _re.search(r'\(layer "([^"]+)"\)', blk)
        pad = _re.search(r'\(pad "1"[^\n]*\n\s*\(at ([-\d.]+) ([-\d.]+)', blk)
        if name and lay and pad:
            inst.setdefault(name.group(1), {}).setdefault(lay.group(1), (float(pad.group(1)), float(pad.group(2))))
    for name, sides in inst.items():
        if "F.Cu" in sides and "B.Cu" in sides:
            (tx, ty), (bx, by) = sides["F.Cu"], sides["B.Cu"]
            if abs(tx) < 0.05 and abs(ty) < 0.05:
                continue                                     # pad 1 on the origin says nothing
            x_mirrored = abs(bx + tx) < 0.01 and abs(by - ty) < 0.01
            y_mirrored = abs(bx - tx) < 0.01 and abs(by + ty) < 0.01
            if x_mirrored or y_mirrored:
                if x_mirrored != BOTTOM_STORED_X_MIRRORED:
                    raise SystemExit("FAILED: the board stores back-side footprints mirrored %s (%s), but "
                                     "jlc_rotation.BOTTOM_STORED_X_MIRRORED is %s: every bottom CPL rotation would be 180 out"
                                     % ("left-right" if x_mirrored else "top-bottom", name, BOTTOM_STORED_X_MIRRORED))
                return "left-right" if x_mirrored else "top-bottom", name
    return None, None


# The ten bottom-side readings BOTTOM_FLIP was derived from, kept so the rule
# can be re-checked rather than re-believed.  (ref, native, side, must_move)
EVIDENCE = [
    ("D6", 180, "bottom", True), ("D7", 0, "bottom", True),
    ("D8", 0, "bottom", True), ("D9", 180, "bottom", True),
    ("D12", 0, "bottom", True), ("D10", 90, "bottom", False),
    ("D11", 90, "bottom", False), ("D13", 270, "bottom", False),
    ("U5", 270, "bottom", False), ("U10", 90, "bottom", False),
]
EVIDENCE_FP = {"D6": "D_SOD-523", "D7": "D_SOD-523", "D8": "D_SOD-523",
               "D9": "D_SOD-523", "D12": "D_SOD-523", "D10": "D_SOD-523",
               "D11": "D_SOD-523", "D13": "D_SOD-523",
               "U5": "Texas_DRT-3", "U10": "Texas_DRT-3"}


def self_test():
    """Re-check the rule against every reading it was derived from."""
    bad = 0
    for ref, native, side, must_move in EVIDENCE:
        fp = EVIDENCE_FP[ref]
        before = (float(native) + (JLC_ROTATION.get(fp, (0,))[0])) % 360.0
        after = cpl_rotation(native, side, fp, stored_x_mirrored=False)      # the Icepi file: KiCad's own convention
        moved = round((after - before) % 360.0) == 180
        if moved != must_move:
            print("  %-5s expected %s, got %s" %
                  (ref, "a 180 flip" if must_move else "no change",
                   "a 180 flip" if moved else "no change"))
            bad += 1
    print("%d of %d bottom-side readings still satisfied"
          % (len(EVIDENCE) - bad, len(EVIDENCE)))
    return bad


if __name__ == "__main__":
    sys.exit(1 if self_test() else 0)
