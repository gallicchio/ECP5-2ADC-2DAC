#!/usr/bin/env python3
"""Which parts can be fitted 180 degrees out without the silkscreen objecting.

    KICAD=10 ../kicad-python.sh pin1.py           # report
    KICAD=10 ../kicad-python.sh pin1.py --write OUT.kicad_pcb   # add dots

THE TEST.  A part can go in backwards if its printed silkscreen maps onto
itself under a half turn.  That is the whole criterion and it is mechanical:
take every silkscreen graphic the footprint draws, rotate the set 180 degrees
about the footprint's origin, and ask whether every piece lands on a piece
that was already there.  If it does, the printed outline is symmetric, the
board says nothing about which way round the part goes, and the only thing
standing between you and a reversed part is whoever is holding the tweezers.

Fab-layer marks do not count.  F.Fab is not printed on the board.  A pin-1
triangle that exists only on F.Fab is a pin-1 triangle that exists only in
KiCad, and an oscillator nearly went in upside down on the GPSDO board for
exactly that reason.

Two-pad passives are skipped: a resistor has no wrong way round.  Polarised
two-pad parts -- diodes and LEDs -- are NOT skipped, because they do.
"""
import math
import os
import sys

import pcbnew

TOL = 0.05                      # mm; two graphics this close are the same one
DOT_D = 0.6                     # the marker to add
DOT_GAP = 0.35                  # air between it and the courtyard

# Mechanically keyed: the plug only goes in one way, or the part only fits one
# way, so no printed mark can be the thing that saves you.
KEYED = ("USB_C_", "microSD", "A71-05H4", "PinHeader", "MountingHole",
         "TestPoint", "LOGO", "OSHW")


def pads_local(fp):
    """Pad centres in footprint-local coordinates."""
    pos = fp.GetPosition()
    ang = fp.GetOrientation().AsRadians()
    ca, sa = math.cos(-ang), math.sin(-ang)
    flip = fp.IsFlipped()
    out = []
    for p in fp.Pads():
        dx = pcbnew.ToMM(p.GetPosition().x - pos.x)
        dy = pcbnew.ToMM(p.GetPosition().y - pos.y)
        if flip:
            dx = -dx
        out.append((round(dx * ca - dy * sa, 3), round(dx * sa + dy * ca, 3)))
    return out


def pads_symmetric(fp, tol=0.06):
    """True if the PAD pattern maps onto itself under a half turn.

    This is the test that decides whether a dot is needed at all, and it is
    a much better test than anything to do with silkscreen: pads are
    unambiguous, and a package whose legs are 3-on-one-side-2-on-the-other
    cannot be fitted backwards no matter what is or is not printed.

    Jason's, from the placement preview: "The SOT-23-5 parts should not have
    dots.  The 5 legs leave the rotation unambiguous."  He is right, and the
    same argument retires the three-pad TPD2EUSB30A as well -- 13 dots become
    6, which also answers his other complaint, that with a lot of dots on the
    preview it is hard to tell which one is JLCPCB's.
    """
    pts = pads_local(fp)
    return all(any(abs(-x - u) < tol and abs(-y - v) < tol for u, v in pts)
               for x, y in pts)


def two_terminal(fp):
    """Two pads and no polarity: 180 degrees out is the same part."""
    name = str(fp.GetFPID().GetLibItemName())
    if name.startswith(("R_", "C_", "L_", "Fuse_", "switch_")):
        return True                 # a resistor with four pads is still a
                                    # resistor; the 0201 here has four
    return len(list(fp.Pads())) <= 2 and not name.startswith(("D_", "LED_"))


def keyed(fp):
    name = str(fp.GetFPID().GetLibItemName())
    return any(k.lower() in name.lower() for k in KEYED)


def classify(fp):
    """What this part needs, and why.

    A part gets a dot when its PAD PATTERN is symmetric under a half turn,
    and not otherwise.  That is the whole rule, and it is decidable: pads are
    geometry, not convention.  A SOT-23-5 has three legs one side and two the
    other and cannot go in backwards; a QFN-20 has five a side and can.

    What a dot is NOT decided by is the silkscreen, which was the first two
    attempts.  Testing the printed silk for symmetry passes parts that are
    plainly ambiguous to a human, and a blunt "everything that is not
    two-terminal" puts dots on parts that do not need them and clutters the
    placement preview you have to read them against.

    What it found instead is the argument for the blunt rule.  The
    oscillator's entire orientation cue is an L of two lines along its left
    and bottom edges -- the corner of the L is pin 1's corner, IF you know
    that is the convention, and that is precisely the part that nearly went
    in upside down on the GPSDO board.  The TPD2EUSB30A prints four little
    stubs along ONE edge, left-right symmetric, and the edge they mark is the
    one AWAY from pin 1.  Both of those pass a symmetry test and neither is
    something to bet a reflow on.

    Diodes and LEDs are left alone: a cathode bar across one end is not a
    convention you have to look up.
    """
    name = str(fp.GetFPID().GetLibItemName())
    if len(list(fp.Pads())) < 2:
        return "skip", "not a placement"
    if keyed(fp):
        return "skip", "mechanically keyed -- it cannot go in backwards"
    if two_terminal(fp):
        return "skip", "two-terminal, no wrong way round"
    if name.startswith(("D_", "LED_")):
        return "ok", "cathode bar, which needs no convention to read"
    if not pads_symmetric(fp):
        return "ok", "the pad pattern itself fixes the rotation"
    if has_mark(fp):
        return "ok", "the library footprint already prints a pin-1 mark"
    return "dot", "pad pattern is symmetric and nothing is printed"


MARK_MAX = 1.0                  # mm; a silk feature smaller than this beside
                                # pin 1 is a pin-1 mark and not an outline


def pin_one(fp):
    """The pad that is pin 1, by name.

    "1" for anything numbered, "A1" for a BGA.  The first version of this
    took the lowest pad number and fell back to (1, 0) for anything
    non-numeric -- which makes every ball of a BGA tie, so `min` returned
    whichever the iterator happened to yield first.  It was A1, and it was
    luck.  A pin-1 dot in the wrong corner of a 256-ball package is the exact
    failure this file exists to prevent.
    """
    for name in ("1", "A1"):
        p = fp.FindPadByNumber(name)
        if p is not None:
            return p
    numbered = [p for p in fp.Pads() if p.GetNumber().isdigit()]
    if numbered:
        return min(numbered, key=lambda p: int(p.GetNumber()))
    return None


def pad1(fp):
    """Where pin 1 is, in board coordinates."""
    p = pin_one(fp)
    return p.GetPosition() if p is not None else fp.GetPosition()


def has_mark(fp):
    """Does the footprint already print a pin-1 mark of its own?

    A small polygon or circle on a silkscreen layer is a mark; the outline is
    lines.  KiCad's SOT-23-5, the three-pad Texas_DRT-3 and the QFN-20 all
    print a little triangle beside pin 1, and where the library already does
    the job there is nothing to add -- a second mark beside the first is one
    more dot to tell apart from JLCPCB's on the placement preview.

    Library marks are never removed, only counted.  They are the footprint
    author's statement about their own footprint and they are correct.
    """
    for it in fp.GraphicalItems():
        if not it.GetLayerName().endswith("Silkscreen"):
            continue
        if it.GetShape() not in (pcbnew.SHAPE_T_POLY, pcbnew.SHAPE_T_CIRCLE):
            continue
        bb = it.GetBoundingBox()
        if max(pcbnew.ToMM(bb.GetWidth()),
               pcbnew.ToMM(bb.GetHeight())) <= MARK_MAX:
            return True
    return False


def add_dot(board, fp):
    """A filled dot on the printed layer, just outside the courtyard, by pad 1.

    Outside, because inside is under the part.  On the footprint's own side,
    because a mark on the other face is a mark you cannot see while placing.
    """
    p1 = pad1(fp)
    c = fp.GetPosition()
    box = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped()
                          else pcbnew.F_CrtYd).BBox()
    if box.GetWidth() == 0:
        box = fp.GetBoundingBox(False, False)
    vx, vy = p1.x - c.x, p1.y - c.y
    n = math.hypot(vx, vy) or 1.0
    half = pcbnew.FromMM(DOT_D / 2.0 + DOT_GAP)
    # push out along the pad-1 direction until clear of the courtyard
    step = pcbnew.FromMM(0.05)
    x, y = float(p1.x), float(p1.y)
    for _ in range(400):
        if not box.Contains(pcbnew.VECTOR2I(int(x), int(y))):
            break
        x += vx / n * step
        y += vy / n * step
    x += vx / n * half
    y += vy / n * half
    # A child of the footprint, not a loose drawing on the board.  It belongs
    # to the part, it moves with the part, and "which part is this dot for"
    # stops being a question you answer by measuring distances.
    sh = pcbnew.PCB_SHAPE(fp)
    sh.SetShape(pcbnew.SHAPE_T_CIRCLE)
    sh.SetCenter(pcbnew.VECTOR2I(int(x), int(y)))
    sh.SetEnd(pcbnew.VECTOR2I(int(x + pcbnew.FromMM(DOT_D / 2.0)), int(y)))
    sh.SetFilled(True)
    sh.SetLayer(pcbnew.B_SilkS if fp.IsFlipped() else pcbnew.F_SilkS)
    sh.SetWidth(pcbnew.FromMM(0.12))
    fp.Add(sh)
    return pcbnew.ToMM(x), pcbnew.ToMM(y)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, "..", "common", "base", "icepi-zero.kicad_pcb")
    board = pcbnew.LoadBoard(src)
    write = None
    if "--write" in sys.argv:
        write = sys.argv[sys.argv.index("--write") + 1]

    need, ok, skip = [], [], []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        what, why = classify(fp)
        row = (fp.GetReference(), fp.GetValue(),
               str(fp.GetFPID().GetLibItemName()), why, fp)
        {"dot": need, "ok": ok, "skip": skip}[what].append(row)

    print("%-6s %-24s %-42s %s" % ("ref", "value", "footprint", "side"))
    for ref, val, fpn, why, fp in need:
        print("%-6s %-24s %-42s %s"
              % (ref, val[:24], fpn[:42], "bottom" if fp.IsFlipped() else "top"))
    print("\n%d get a pin-1 dot, %d already unmistakable, %d need none"
          % (len(need), len(ok), len(skip)))

    if write:
        def compass(dx, dy):                # board coords: +x east, +y SOUTH
            v = ("N" if dy < -0.2 else "S" if dy > 0.2 else "")
            return (v + ("W" if dx < -0.2 else "E" if dx > 0.2 else "")) or "centre"
        print("\ndots added:")
        for ref, val, fpn, why, fp in need:
            x, y = add_dot(board, fp)
            c = fp.GetPosition()
            p1 = pad1(fp)
            print("  %-4s dot %-6s of centre;  pin 1 (%s) is %s of centre"
                  % (ref,
                     compass(x - pcbnew.ToMM(c.x), y - pcbnew.ToMM(c.y)),
                     pin_one(fp).GetNumber() if pin_one(fp) else "?",
                     compass(pcbnew.ToMM(p1.x - c.x), pcbnew.ToMM(p1.y - c.y))))
        board.Save(write)
        print("wrote %s" % write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
