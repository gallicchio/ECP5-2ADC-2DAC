#!/usr/bin/env python3
"""The schematic's rendered text, checked from the PDF KiCad exported: pdftotext -bbox gives every word's box,
so two words that overlap are two texts that collide on the page (words of one text never overlap each other),
and a word outside the drawing frame is text off the page.  This sees what the reader sees; the generator's
own check (kisch.Sch.overlaps) works from its estimate of the text widths and also knows about symbols and
wires.  Usage: check_sch_text.py schematic.pdf [report.txt]"""
import html, re, subprocess, sys

PT = 72 / 25.4          # points per mm
PAD = 0.25              # the invisible text's box is a little wider than the strokes
VBAND = 0.25            # ... and about twice as tall; the glyphs are the middle half of it, give or take 0.3 mm (the box
                        # sits a little differently on top- and bottom-anchored text), so a collision has to be deeper
MIN_DEPTH = 0.35        # than this in both directions to count
PAGES = {1: "root", 2: "fpga", 3: "adc", 4: "dac", 5: "ethernet", 6: "usb", 7: "power"}


def words(pdf):
    out = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True, text=True).stdout
    pages = []
    for pm in re.finditer(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', out, re.S):
        W, H = float(pm.group(1)) / PT, float(pm.group(2)) / PT
        ws = []
        for m in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', pm.group(3)):
            x0, y0, x1, y1 = (float(v) / PT for v in m.groups()[:4])
            w = html.unescape(m.group(5))
            if (y1 - y0) > 2.0 * (x1 - x0) and len(w) >= 3:    # a word standing on end (a vertical pin name): the box is its glyphs' height wide
                cx, hw = (x0 + x1) / 2, (x1 - x0) * 0.25
                ws.append((cx - hw, y0 + PAD, cx + hw, y1 - PAD, w))
            else:
                h = y1 - y0
                ws.append((x0 + PAD, y0 + VBAND * h, x1 - PAD, y1 - VBAND * h, w))
        pages.append((W, H, ws))
    return pages


def check(pdf):
    msgs = []
    for p, (W, H, ws) in enumerate(words(pdf), 1):
        name = PAGES.get(p, str(p))
        def frame(w):            # the frame's zone numbers and letters sit on the 10 mm border line
            cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            return cx < 13 or cy < 13 or cx > W - 13 or cy > H - 13
        def title(w):            # the title block (bottom right) lays its own words out
            return w[0] > W - 125 and w[1] > H - 32
        ws = [w for w in ws if not frame(w) and not title(w)]
        for i, a in enumerate(ws):
            if a[0] < 10 or a[1] < 10 or a[2] > W - 10 or a[3] > H - 10:
                msgs.append("%s: off page: %r at (%.0f,%.0f)" % (name, a[4], a[0], a[1]))
            for b in ws[i + 1:]:
                dy = min(a[3], b[3]) - max(a[1], b[1])
                if min(a[2], b[2]) - max(a[0], b[0]) > MIN_DEPTH and dy > max(MIN_DEPTH, 0.4 * min(a[3] - a[1], b[3] - b[1])):
                    # the same word twice at one place is pdftotext seeing a word and its bold twin: not an overlap
                    if a[4] == b[4] and abs(a[0] - b[0]) < 0.5 and abs(a[1] - b[1]) < 0.5:
                        continue
                    msgs.append("%s: overlap: %r / %r at (%.0f,%.0f)" % (name, a[4], b[4], a[0], a[1]))
    return msgs


if __name__ == "__main__":
    msgs = check(sys.argv[1])
    if len(sys.argv) > 2:
        open(sys.argv[2], "w").write("\n".join(msgs) + "\n")
    for m in msgs[:60]:
        print("   ", m)
    print("rendered text: %d complaints (overlapping words or words off the page)" % len(msgs))
