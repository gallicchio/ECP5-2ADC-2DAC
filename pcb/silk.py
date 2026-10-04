"""Silkscreen placement: a label goes where it covers nothing -- not a part,
not another label, not the board edge.  An occupancy grid per side (0.5 mm)
holds every courtyard; labels claim their box as they are placed; a spot
search finds the free box nearest where a label would like to be, and the
largest empty rectangle is where the title block goes."""
import math
import numpy as np
import place as P

RES = 0.25


def text_w(s, size, bold=False):
    """Width of a one-line KiCad stroke text, roughly (it is a monospace-ish font)."""
    return len(s) * size * (1.08 if bold else 1.0) + 0.3


def text_h(size):
    """KiCad's bounding box of a one-line stroke text is about 2.0 x the size (1.38 mm for 0.7 mm text)."""
    return size * 2.0


class Occ:
    """Occupancy of one side at RES mm: a cell is taken when the majority of
    it lies under a courtyard (grown 0.45 mm), a placed label or the edge
    margin.  A summed-area table makes the free test O(1)."""
    def __init__(self, pl, layer):
        self.nx, self.ny = int(round(P.BW / RES)), int(round(P.BH / RES))
        self.a = np.zeros((self.ny, self.nx), dtype=np.int32)
        self._sat = None
        m = 1.2
        self.mark(0, 0, P.BW, m); self.mark(0, P.BH - m, P.BW, P.BH)
        self.mark(0, 0, m, P.BH); self.mark(P.BW - m, 0, P.BW, P.BH)
        import fplib
        for ref, (x, y, rot, lay) in pl.placed.items():
            if lay == layer or pl.fp[ref]["th_any"] or ref == "U1":     # the BGA's escape vias: both sides
                # the true courtyard (the placer's boxes carry its own margin)
                x0, y0, x1, y1 = fplib.box_at(pl.fp[ref], x, y, rot, back=(lay == "B.Cu"), grow=0.0)
                self.mark(x0 - 0.15, y0 - 0.15, x1 + 0.15, y1 + 0.15)
        self.boxes = []          # labels placed, (x0, y0, x1, y1)

    def _cells(self, x0, y0, x1, y1):
        i0 = max(0, int(round(x0 / RES))); i1 = min(self.nx, int(round(x1 / RES)))
        j0 = max(0, int(round(y0 / RES))); j1 = min(self.ny, int(round(y1 / RES)))
        return i0, j0, max(i1, i0 + 1), max(j1, j0 + 1)

    def mark(self, x0, y0, x1, y1):
        i0, j0, i1, j1 = self._cells(x0, y0, x1, y1)
        if i1 > i0 and j1 > j0 and i0 < self.nx and j0 < self.ny:
            self.a[j0:j1, i0:i1] = 1
            self._sat = None

    def sat(self):
        if self._sat is None:
            s = np.zeros((self.ny + 1, self.nx + 1), dtype=np.int32)
            s[1:, 1:] = self.a.cumsum(0).cumsum(1)
            self._sat = s
        return self._sat

    def free(self, x0, y0, x1, y1):
        if x0 < 0 or y0 < 0 or x1 > P.BW or y1 > P.BH:
            return False
        i0, j0, i1, j1 = self._cells(x0, y0, x1, y1)
        if i1 > self.nx or j1 > self.ny:
            return False
        s = self.sat()
        return int(s[j1, i1] - s[j0, i1] - s[j1, i0] + s[j0, i0]) == 0

    def claim(self, x0, y0, x1, y1, margin=0.15):
        """A label's box, plus a margin so two labels never touch after the 0.25 mm cell rounding."""
        self.mark(x0 - margin, y0 - margin, x1 + margin, y1 + margin)
        self.boxes.append((x0, y0, x1, y1))

    def spot(self, w, h, prefer, maxd=12.0, step=0.5, rot_ok=False, region=None, rot=None):
        """Top-left (x, y, rot) of a free w x h box with its centre nearest
        `prefer`, or None.  rot_ok also tries the box standing up (rot 90);
        rot=90 tries only that, rot=0 only flat."""
        if rot == 90:
            rot_ok = True
        px, py = prefer
        n = int(maxd / step)
        cands = []
        for dj in range(-n, n + 1):
            for di in range(-n, n + 1):
                d = math.hypot(di * step, dj * step)
                if d <= maxd:
                    cands.append((d, px + di * step, py + dj * step))
        cands.sort()
        for d, cx, cy in cands:
            if region and not (region[0] <= cx <= region[2] and region[1] <= cy <= region[3]):
                continue
            x0, y0 = cx - w / 2.0, cy - h / 2.0
            if rot != 90 and self.free(x0, y0, x0 + w, y0 + h):
                return (x0, y0, 0)
            if rot_ok and self.free(cx - h / 2.0, cy - w / 2.0, cx + h / 2.0, cy + w / 2.0):
                return (cx - h / 2.0, cy - w / 2.0, 90)
        return None

    def largest(self):
        """The largest empty rectangle (x0, y0, x1, y1) in mm."""
        nx, ny = self.nx, self.ny
        h = [0] * nx
        best = (0, None)
        for j in range(ny):
            row = self.a[j]
            for i in range(nx):
                h[i] = 0 if row[i] else h[i] + 1
            stack = []
            for i in range(nx + 1):
                cur = h[i] if i < nx else 0
                start = i
                while stack and stack[-1][1] >= cur:
                    si, sh = stack.pop()
                    area = sh * (i - si)
                    if area > best[0]:
                        best = (area, (si, j - sh + 1, i, j + 1))
                    start = si
                stack.append((start, cur))
        if best[1] is None:
            return None
        i0, j0, i1, j1 = best[1]
        return (i0 * RES, j0 * RES, i1 * RES, j1 * RES)
