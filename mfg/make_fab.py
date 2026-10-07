#!/usr/bin/env python3
"""The manufacturing release: Gerbers + drill (zipped), BOM and CPL for
JLCPCB's assembly service, the hand-solder list, a cost estimate from
JLCPCB's live parts API, and FABRICATION_NOTES.txt with everything the fab
will otherwise come back to ask.

    python3 mfg/make_fab.py [--boards N] [--refresh]

Writes mfg/release/.  Reads the board (ECP5-2ADC-2DAC.kicad_pcb), the netlist
(build/netlist.net) and the LCSC codes the schematic carries (build/lcsc.json).
"""
import os, sys, csv, json, re, shutil, subprocess, zipfile, collections, datetime, math
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "tools")); sys.path.insert(0, os.path.join(ROOT, "pcb")); sys.path.insert(0, os.path.join(ROOT, "gen"))
import jlc_rotation, jlc_api, netmap, fplib

NAME = "ECP5-2ADC-2DAC"
PCB = os.path.join(ROOT, NAME + ".kicad_pcb")
OUT = os.path.join(HERE, "release")
GERBER_LAYERS = "F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"
# Through-hole parts are assembled too (Jason, 2026-10-06: "even if it costs extra"; the USB-C's soldered
# shell legs already pay JLCPCB's per-order through-hole fee).  A through-hole part without an LCSC code
# is the only thing left for the hand-solder list.
HAND = ()
THT_SETUP = 3.58          # JLCPCB's per-order through-hole labour (Icepi jlcbuild J1); the per-joint rate is
THT_PER_JOINT = 0.02      # an assumption to calibrate against the cart (CLAUDE_PCB.md: GPiBridge's estimate was $5 low per board)
sys.path.insert(0, os.path.join(ROOT, "gen"))
import parts as PARTS
import footprint_check as FC
import place as P
FPKEY = {v: k for k, v in PARTS.FP.items()}          # footprint id -> the generator's key ("H1x2", "PMOD", ...)

def cli():
    for c in (os.environ.get("KICAD_CLI"), os.environ.get("KICAD_APPIMAGE"), os.path.expanduser("~/.local/bin/kicad-10.0.6-x86_64.AppImage")):
        if c and os.path.exists(c):
            return [c, "kicad-cli"] if c.endswith("AppImage") else [c]
    return ["kicad-cli"]


def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("%s\n%s%s" % (" ".join(args[-4:]), r.stdout, r.stderr))
    return r.stdout


def components():
    fps, vals, nets, numof = netmap.load(os.path.join(ROOT, "build", "netlist.net"))
    lcsc = json.load(open(os.path.join(ROOT, "build", "lcsc.json")))
    placed = json.load(open(os.path.join(ROOT, "build", "placement.json")))
    rows = []
    for ref, fpid in sorted(fps.items(), key=lambda kv: (re.sub(r"\d+", "", kv[0]), int(re.sub(r"\D", "", kv[0]) or 0))):
        if not fpid or ref not in placed:
            continue
        x, y, rot, layer = placed[ref]
        x, y = x + P.OX, y + P.OY                            # the page frame: the CPL must agree with the gerbers (pcb/place.py)
        fp = fplib.load(fpid)
        short = fpid.split(":", 1)[1]
        # the code the schematic carries, else the parts table's footprint default (the through-hole
        # headers' codes live there since 2026-10-06; the sheets carry them from the next build on)
        code = lcsc.get(ref, "") or (PARTS.lcsc_for(vals.get(ref, ""), FPKEY.get(fpid, "")) or "")
        nth = sum(1 for q in fp["pads"] if float(q.get("drill") or 0) > 0)
        if not fp["smd"] and nth == 0:
            nth = len(fp["pads"])
        if ref.startswith("TP") or ref.startswith("H"):
            cls = "none"
        elif ref in HAND or not fp["smd"]:
            cls = "tht" if (code and ref not in HAND) else "hand"
        elif not code:
            cls = "nocode"
        else:
            cls = "smt"
        rows.append(dict(ref=ref, value=vals.get(ref, ""), fp=fpid, fpshort=short, lcsc=code, x=x, y=y, rot=rot,
                         side="bottom" if layer == "B.Cu" else "top", cls=cls, npads=len(fp["pads"]), nth=nth))
    return rows


def assembled(rows):
    return [r for r in rows if r["cls"] in ("smt", "tht")]


def write_bom(rows, outdir):
    """One line per LCSC code, SMT and through-hole alike; the hand-solder list only for parts without a code."""
    asm = assembled(rows)
    by = collections.defaultdict(list)
    for r in asm:
        by[r["lcsc"]].append(r)
    bom = os.path.join(outdir, "%s_bom.csv" % NAME)
    with open(bom, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for code, group in sorted(by.items(), key=lambda kv: -len(kv[1])):
            vals = sorted({g["value"] for g in group}, key=lambda v: (-len(v), v))
            fps = sorted({g["fpshort"] for g in group})
            w.writerow([vals[0], ",".join(g["ref"] for g in group), fps[0], code])
    hand = os.path.join(outdir, "hand_solder_bom.csv")
    hrows = [r for r in rows if r["cls"] == "hand"]
    # always written, and meant to hold nothing but its header: everything is assembled (Jason, 2026-10-07)
    with open(hand, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Value", "Footprint", "LCSC (to order loose)"])
        for r in hrows:
            w.writerow([r["ref"], r["value"], r["fpshort"], r["lcsc"]])
    return bom, hrows, len(asm), len(by)


def footprint_check(bom, refresh=False):
    """Every ordered code's EasyEDA land pattern laid on the board (mfg/footprint_check.py): a part wanting
    a hole the board lacks stops the release.  Returns FC.FITS, the turn and shift that laid each
    drawing on our footprint, which the CPL's predicted rotations and datum shifts come from."""
    nbad, text = FC.report(bom, refresh, False)
    open(os.path.join(OUT, "FOOTPRINT_CHECK.txt"), "w").write("\n".join(text) + "\n")
    hard = [l.strip() for l in text if l.startswith("       HOLE")]
    if hard:
        raise SystemExit("FAILED: a part wants a hole the board does not have:\n  " + "\n  ".join(hard))
    return FC.FITS


def predicted_corrections(rows, fits):
    """Per LCSC code, the correction JLCPCB's own drawing predicts, from the quarter turn that laid it on
    our footprint by pin number (GPiBridge, 2026-10-06: right on every part in its preview).  A top-side
    fit at d degrees predicts 360 - d.  A bottom-side fit is against this board's x-mirrored pads, and a
    left-right mirror is a top-bottom one turned half way round, so it predicts d + 180 (untested in a
    preview).  Two-pad parts carry no prediction: their polarity is a mark, not a pin number."""
    out = {}
    for code in sorted({r["lcsc"] for r in assembled(rows)}):
        ft, fb = fits.get((code, False)), fits.get((code, True))
        cands = []
        for fit, side in ((ft, "top"), (fb, "bottom")):
            if fit and fit.get("how") == "by name" and fit.get("n", 0) >= 3 and fit["worst"] <= FC.LAND_WARN:
                pred = (360 - fit["deg"]) % 360 if side == "top" else (fit["deg"] + 180) % 360
                cands.append((pred, side, fit))
        if not cands:
            out[code] = (None, "no prediction: " + ("two pads, polarity is a mark" if (ft or fb) and (ft or fb).get("n", 0) < 3 else
                                                      "no fit by pin number"))
        elif len(cands) == 2 and cands[0][0] != cands[1][0]:
            out[code] = (cands[0][0], "top-side fit says %d, bottom-side fit says %d: DISAGREE, the top one is used" % (cands[0][0], cands[1][0]))
        elif len(cands) == 2:
            out[code] = (cands[0][0], "from the top-side fit at %d deg (%d pads by number, worst %.2f mm); the bottom-side fit at %d deg says the same"
                         % (cands[0][2]["deg"], cands[0][2]["n"], cands[0][2]["worst"], cands[1][2]["deg"]))
        else:
            pred, side, fit = cands[0]
            out[code] = (pred, "from the %s-side fit at %d deg, %d pads by number, worst %.2f mm%s"
                         % (side, fit["deg"], fit["n"], fit["worst"], "" if side == "top" else " (the bottom rule is untested)"))
    return out


def datum_shift(r, fits):
    """How far to move one placement in the JLCPCB CPL (x right, y up, mm).  JLCPCB puts THEIR drawing's
    origin at the CPL's position; where that is not KiCad's, the part lands off its pads by the difference
    (every USB-C so far).  footprint_check.py's fit says where their origin sits in our footprint (dx, dy,
    KiCad's y-down local frame); here it is turned with the part.  Only past DATUM_OK and when the fit is good."""
    fit = fits.get((r["lcsc"], r["side"] == "bottom"))
    if r["lcsc"] in FC.STRIPS:                    # a strip snapped to length: the drawing's zero is the strip's middle
        return 0.0, 0.0
    if not fit or math.hypot(fit["dx"], fit["dy"]) <= FC.DATUM_OK or fit["worst"] > FC.LAND_OK:
        return 0.0, 0.0
    if r["side"] != "top":
        raise SystemExit("FAILED: %s has a datum offset on the bottom side, which this does not handle yet" % r["ref"])
    a = math.radians(r["rot"])                                # KiCad: counter-clockwise on screen, y down
    sx = fit["dx"] * math.cos(a) + fit["dy"] * math.sin(a)
    sy = -fit["dx"] * math.sin(a) + fit["dy"] * math.cos(a)
    return round(sx, 3), round(-sy, 3)                        # the CPL's y points up


def write_cpls(rows, fits, preds, outdir):
    """Two CPLs: the one to upload (JLCPCB's conventions: the bottom-side mirror, the per-part corrections read
    in previews or predicted from their drawings, the datum shifts) and KiCad's native numbers for reference."""
    asm = assembled(rows)
    unchecked = collections.OrderedDict()                      # code -> placements never seen right in a preview
    moved = []
    for name, corrected in (("%s_cpl.csv" % NAME, True), ("%s_cpl_native.csv" % NAME, False)):
        with open(os.path.join(outdir, name), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
            for r in asm:
                x, y = r["x"], -r["y"]
                if corrected:
                    pred = preds.get(r["lcsc"], (None, ""))[0]
                    rot = jlc_rotation.cpl_rotation(r["rot"], r["side"], r["fpshort"], r["lcsc"], pred)
                    if not jlc_rotation.checked(r["fpshort"], r["lcsc"]):
                        unchecked.setdefault(r["lcsc"], []).append(r)
                    dx, dy = datum_shift(r, fits)
                    if dx or dy:
                        moved.append((r, dx, dy)); x, y = x + dx, y + dy
                else:
                    rot = float(r["rot"]) % 360.0
                w.writerow([r["ref"], "%.3fmm" % x, "%.3fmm" % y, r["side"], "%g" % rot])
    return unchecked, moved


def placement_checks(rows, unchecked, fits, preds, moved, outdir):
    """What to look at in JLCPCB's 'Confirm parts placement' preview, part by part."""
    L = ["%s rev A: PLACEMENT CHECKS for JLCPCB's preview" % NAME, ""]
    if moved:
        L += ["MOVED in %s_cpl.csv to where JLCPCB's library puts the part's origin (their drawing's zero is not" % NAME,
              "KiCad's; FOOTPRINT_CHECK.txt's 'datum').  In the preview each should sit squarely on its pads.  If one",
              "sits off them by about the same distance the other way, their library has changed: say so.", ""]
        for r, dx, dy in moved:
            L.append("  %-6s %-10s %-44s moved (%+.3f, %+.3f) mm (x right, y up)" % (r["ref"], r["lcsc"], r["fpshort"][:44], dx, dy))
        L.append("")
    L += ["The CPL's rotations are this board's stored angles plus mfg/jlc_rotation.py: the bottom-side mirror (this",
          "board stores its back-side pads mirrored left-right, 180 from KiCad's own convention, and the rule allows",
          "for it), then the per-part correction -- read in a preview where somebody has, else PREDICTED from JLCPCB's",
          "own drawing of the part turned until its pads lie on ours by pin number.  Every predicted or unpredicted",
          "part is listed below: in the preview check its pin 1 or polarity mark (JLCPCB's dot) against the board,",
          "write down any that is wrong and by how much, and it goes into jlc_rotation.py.", ""]
    bottom = [r for r in assembled(rows) if r["side"] == "bottom" and r["fpshort"] not in jlc_rotation.ROTATION_NA]
    if bottom:
        L += ["LOOK HARDEST at the bottom side, where the mirror rule meets this board's convention for the first time:",
              "  " + " ".join(sorted({r["ref"] for r in bottom})), ""]
    L.append("Not yet seen right in a preview:")
    for code, group in unchecked.items():
        fp = group[0]["fpshort"]
        pred, why = preds.get(code, (None, ""))
        corr, conf, cwhy = jlc_rotation.correction(fp, code)
        L.append("  %-28s %-12s %s" % (", ".join(g["ref"] for g in group)[:28], code, fp))
        L.append("      value %s; %s" % ("/".join(dict.fromkeys(g["value"] for g in group)),
                                         ("correction %d (%s)" % (corr, conf)) if conf != "none" else
                                         ("predicted correction %d, %s" % (pred, why)) if pred is not None else why))
    if not unchecked:
        L.append("  (none)")
    read = sorted({r["ref"] for r in assembled(rows) if r["fpshort"] not in jlc_rotation.ROTATION_NA and jlc_rotation.checked(r["fpshort"], r["lcsc"])})
    L += ["", "Read right in a preview already (the Icepi and GPSDO boards): " + " ".join(read)]
    L.append("The method against those readings (its prediction must equal the correction somebody saw):")
    seen = set()
    for r in assembled(rows):
        corr, conf, why = jlc_rotation.correction(r["fpshort"], r["lcsc"])
        if conf in ("none", "predicted", "derived") or (r["lcsc"], r["fpshort"]) in seen:
            continue
        seen.add((r["lcsc"], r["fpshort"]))
        pred, pwhy = preds.get(r["lcsc"], (None, ""))
        L.append("  %-10s %-36s read %3d, predicted %s: %s" % (r["lcsc"], r["fpshort"][:36], corr, "%3d" % pred if pred is not None else "  -",
                                                             "AGREES" if pred == corr else ("DISAGREES -- " + pwhy if pred is not None else "no prediction")))
    L += [
          "No orientation to get wrong (two pads, or symmetric): " + ", ".join(sorted({r["fpshort"] for r in assembled(rows) if r["fpshort"] in jlc_rotation.ROTATION_NA})),
          "", "Through-hole parts JLCPCB fits: the SMA jacks' barrels must point off the LEFT edge, the Pmod sockets' openings",
          "off the RIGHT edge, the RJ45's opening off the right edge, the DIP switch's ON side at the silkscreen's ON.", ""]
    open(os.path.join(outdir, "PLACEMENT_CHECKS.txt"), "w").write("\n".join(L) + "\n")
    return L


def export_gerbers(outdir):
    gerb = os.path.join(outdir, "gerbers")
    if os.path.isdir(gerb):
        shutil.rmtree(gerb)
    os.makedirs(gerb)
    k = cli()
    run(k + ["pcb", "export", "gerbers", "-o", gerb, "--layers", GERBER_LAYERS, "--no-protel-ext", "--subtract-soldermask", PCB])
    run(k + ["pcb", "export", "drill", "-o", gerb, "--format", "excellon", "--drill-origin", "absolute", "--excellon-units", "mm",
             "--excellon-zeros-format", "decimal", "--generate-map", "--map-format", "gerberx2", PCB])
    zpath = os.path.join(outdir, "%s_gerbers.zip" % NAME)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(gerb)):
            z.write(os.path.join(gerb, fn), fn)
    for side, layers, mirror in (("top", "F.Fab,F.SilkS,Edge.Cuts", False), ("bottom", "B.Fab,B.SilkS,Edge.Cuts", True)):
        p = os.path.join(outdir, "%s_assembly_%s.pdf" % (NAME, side))
        try:
            run(k + ["pcb", "export", "pdf", "-o", p, "--layers", layers, "--mode-single", "--exclude-value"] + (["--mirror"] if mirror else []) + [PCB])
        except Exception as e:
            print("   assembly pdf:", str(e)[:120])
    return zpath


def cost(rows, boards, refresh=False):
    """Stock and price per distinct LCSC code, from JLCPCB's parts API, SMT and through-hole parts alike."""
    asm = assembled(rows)
    cnt = collections.Counter(r["lcsc"] for r in asm)
    lines, total_parts, ext = [], 0.0, 0
    thin = []
    wrong = code_value_check(asm, refresh)
    if wrong:
        # builds 1-24 ordered a 1206 resistor as the 2.2 pF capacitor, 240 R as the USB's 27 R, 470 k as the DAC's
        # 24.9 R loads, 270 k as the PHY's 2.49 k RSET and 27 k as the -4.4 V pump's 1.3 M: every one a typing slip
        # in gen/parts.py that no drawing could show.  JLCPCB's own description of the code is the check.
        raise SystemExit("FAILED: LCSC codes whose JLCPCB description does not carry the schematic value: " + "; ".join(wrong))
    for code, n in sorted(cnt.items(), key=lambda kv: -kv[1]):
        try:
            p, ts = jlc_api.by_code(code, refresh=refresh)
        except Exception as e:
            lines.append((code, n, "?", 0, 0.0, "query failed: %s" % e)); continue
        if not p:
            lines.append((code, n, "?", 0, 0.0, "not found")); continue
        need = n * boards
        lt = jlc_api.library_type(p)
        stock = int(p.get("stockCount") or 0)
        price = jlc_api.unit_price(p, max(need, 1))
        if lt not in ("Basic", "Preferred"):
            ext += 1
        total_parts += price * need
        if stock < need * 10:
            thin.append((code, p.get("componentModelEn", ""), stock, need))
        lines.append((code, n, lt, stock, price, p.get("componentModelEn", "")))
    return lines, total_parts, ext, thin


def gates():
    """What the shipped file must be before anything is written: zones filled, DRC clean, the bottom-side
    convention the CPL rule assumes (CLAUDE_PCB.md's verification gates 5 and 9)."""
    text = open(PCB, encoding="utf-8").read()
    n_fill = text.count("(filled_polygon")
    if n_fill == 0:
        raise SystemExit("FAILED: the board file has no filled zones; the gerbers would ship without the pours")
    drc = os.path.join(ROOT, "build", "drc.json")
    if os.path.exists(drc):
        d = json.load(open(drc))
        errs = [v for v in d.get("violations", []) if v.get("severity") == "error"]
        unc = d.get("unconnected_items", [])
        if errs or unc:
            raise SystemExit("FAILED: DRC has %d error(s) and %d unconnected item(s)" % (len(errs), len(unc)))
    conv, fpname = jlc_rotation.verify_bottom_convention(PCB)
    return n_fill, conv, fpname


def code_value_check(smt, refresh=False):
    """Every ordered code's JLCPCB description must carry the value the schematic gives the part (passives: the
    number and unit; parts with a part-number value: the part number) and its package.  Returns the offenders."""
    pkg = {"R_0603_1608Metric": "0603", "R_1206_3216Metric": "1206", "C_1812_4532Metric": "1812", "C_0402_1005Metric": "0402", "C_0402_1005Metric_BGA": "0402", "C_0603_1608Metric": "0603",
           "C_0805_2012Metric": "0805", "L_0603_1608Metric": "0603", "C_1206_3216Metric": "1206", "Fuse_1812_4532Metric": "1812"}
    unit = {"pf": ["pF"], "nf": ["nF"], "uf": ["uF", "\u00b5F"], "r": ["\u03a9"], "k": ["k\u03a9"], "m": ["M\u03a9"], "uh": ["uH", "\u00b5H"]}
    seen, out = {}, []
    for r in smt:
        code, value, fps = r["lcsc"], r["value"], r["fpshort"]
        if (code, value) in seen:
            continue
        seen[(code, value)] = True
        try:
            p, ts = jlc_api.by_code(code, refresh=refresh)
        except Exception:
            continue                                        # no network: the price table says "query failed" for it
        if not p:
            out.append("%s (%s): not found" % (code, value)); continue
        desc = " ".join(str(p.get(k) or "") for k in ("describe", "componentModelEn", "componentSpecificationEn")).lower()
        value = value.lower()                               # JLCPCB writes "SI5351A-B-GTR", "MicroSD", "White"
        if code in PARTS.LCSC_BY_FP.values():               # a header or socket chosen by footprint: its "value" is the jumper's name
            if "2.54" not in desc:
                out.append("%s (%s %s): JLCPCB says %s" % (code, value, fps, desc[:60]))
            continue
        want = pkg.get(fps)
        if want and want not in desc:
            out.append("%s (%s %s): JLCPCB says %s" % (code, value, want, desc[:60])); continue
        m = re.match(r"^([\d.]+)\s*(pf|nf|uf|r|k|m|uh)(\s|$)", value)
        if m:
            num, u = m.group(1), m.group(2)
            if not any(num + sep + un.lower() in desc for un in unit[u] for sep in ("", " ")):
                out.append("%s (%s): JLCPCB says %s" % (code, value, desc[:70]))
        elif len(value) > 4 and value.replace("/", "").replace("-", "").isalnum() and not any(t in desc for t in (value, value.split("-")[0])):
            out.append("%s (%s): JLCPCB says %s" % (code, value, desc[:70]))
    return out


def measure():
    """What was actually drawn: widths, vias, drills, board size."""
    from sexp import parse, kids, kid, val
    doc = parse(open(PCB, encoding="utf-8").read())[0]
    widths = [float(kid(s, "width")[1][1]) for s in kids(doc, "segment")]
    vias = [(float(kid(v, "size")[1][1]), float(kid(v, "drill")[1][1])) for v in kids(doc, "via")]
    drills = []
    for f in kids(doc, "footprint"):
        for p in kids(f, "pad"):
            d = kid(p, "drill")
            if d:
                try:
                    drills.append(float(d[1][1]))
                except Exception:
                    pass
    return dict(min_track=min(widths) if widths else None, widths=sorted(set(widths)), vias=sorted(set(vias)), n_vias=len(vias),
                n_segments=len(widths), min_drill=min([d for _, d in vias] + drills) if (vias or drills) else None)


def main(argv):
    boards = 5
    refresh = "--refresh" in argv
    if "--boards" in argv:
        boards = int(argv[argv.index("--boards") + 1])
    os.makedirs(OUT, exist_ok=True)
    n_fill, conv, convfp = gates()
    rows = components()
    nocode = [r["ref"] for r in rows if r["cls"] == "nocode"]
    if nocode:
        # build 20: the converters, op amps, HDMI jack and microSD socket had no code and had joined the
        # hand-solder list without a word.  A part JLCPCB is meant to fit must have a code, or the release lies.
        raise SystemExit("FAILED: SMD parts without an LCSC code (fix gen/parts.py, or add them to HAND): %s" % ", ".join(nocode))
    bom, hrows, n_asm, n_lines = write_bom(rows, OUT)
    fits = footprint_check(bom, refresh)
    preds = predicted_corrections(rows, fits)
    unchecked, moved = write_cpls(rows, fits, preds, OUT)
    placement_checks(rows, unchecked, fits, preds, moved, OUT)
    zpath = export_gerbers(OUT)
    import end_panels
    end_panels.main()                                   # the enclosure's two end plates, with every connector's cutout
    lines, parts_cost, ext, thin = cost(rows, boards, refresh)
    m = measure()
    import place as P
    smt = [r for r in rows if r["cls"] == "smt"]; tht = [r for r in rows if r["cls"] == "tht"]
    n_smt, n_tht = len(smt), len(tht)
    # JLCPCB's public 6-layer pricing is not a formula they publish; these are the
    # 2026 list-price neighbourhoods for a 130 x 95 mm 6-layer ENIG board with
    # via-in-pad, and are labelled as estimates in the notes
    pcb_est = 70.0 + 12.0 * boards
    asm_setup = 8.0 + 3.0 * ext            # one-off: setup plus a loading fee per Extended part
    joints = n_smt * 3
    asm_per = 0.0017 * joints + 1.5
    tht_joints = sum(r["nth"] for r in tht) + sum(r["nth"] for r in smt)       # the SMT USB-Cs' shell legs are soldered too
    tht_per = THT_PER_JOINT * tht_joints
    est_total = pcb_est + asm_setup + asm_per * boards + THT_SETUP + tht_per * boards + parts_cost
    with open(os.path.join(OUT, "cost_estimate.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["LCSC", "per board", "library", "stock", "unit price USD @ %d" % boards, "part"])
        for row in lines:
            w.writerow(row)
    notes = []
    notes.append("%s rev A -- FABRICATION NOTES (written %s)\n" % (NAME, datetime.date.today().isoformat()))
    notes.append("Board: %.0f x %.0f mm, 6 layers, 1.6 mm, JLCPCB stackup JLC06161H-7628 (1 oz outer, 0.5 oz inner, 7628 prepreg)." % (P.BW, P.BH))
    notes.append("Surface finish: ENIG (there is a 0.8 mm pitch BGA).  Solder mask green, silkscreen white.")
    notes.append("Via-in-pad under the BGA: all 0.3 mm / 0.15 mm vias must be epoxy filled and capped (JLCPCB's default for 6+ layers; tick it).")
    notes.append("The FPGA's 100 nF decoupling sits on the BACK directly under the BGA, each 0402 on two adjacent ball vias (0.8 mm pitch): those vias must be capped on the back too (the filled-and-capped option covers both sides).")
    notes.append("Enclosure: Hammond 1455Q (125 x 51.5 mm extrusion, 160 or 220 mm long); the board's long edges slide into its PCB slots, so nothing sits within 3.5 mm of them.  SMAs through the left end plate, all other connectors through the right one.")
    notes.append("Photodiode D103 uses ours:VBPW34S_K1_A2 (LCSC's footprint with pads renumbered so pad 1 is the cathode); its orientation on the board is the same as JLCPCB's library part, pad 1 of theirs (the anode) on the -5 V side.  Check it in the placement preview.")
    notes.append("The mini-HDMI jack is wired with type C pin numbering (shield first in each pair, DDC ground 13, CEC 14); its four shell tabs (pads 20-23) are grounded.")
    notes.append("Minimum track/space on the board: %.3f mm (inside the BGA fan-out; 0.127 mm elsewhere).  Via sizes: %s.  Smallest drill %.2f mm."
                 % (m["min_track"] or 0, ", ".join("%g/%g" % v for v in m["vias"]), m["min_drill"] or 0))
    notes.append("Impedance: ask for controlled impedance with the JLC06161H-7628 calculator: 50 ohm single-ended (SMA runs, 0.3 mm drawn) and 100 ohm differential (Ethernet MDI, 0.2 mm / 0.2 mm drawn), referenced to In1.")
    notes.append("The shipped board file holds %d filled zone polygons; DRC 0 errors / 0 unconnected (build/drc.json)." % n_fill)
    notes.append("")
    notes.append("Assembly (JLCPCB Standard, SMT both sides + through-hole on top): %d SMT placements and %d through-hole parts on %d BOM lines, %d of them Extended parts (each carries a one-off loading fee)."
                 % (n_smt, n_tht, n_lines, ext))
    notes.append("Through-hole, fitted by JLCPCB (Jason, 2026-10-06): the six SMA jacks, the RJ45, the DIP switch, the 2.54 mm headers (ordered as 1x40 / 2x40 strips the assembler snaps to length, as on the GPSDO board) and the two Pmod sockets.  %d through-hole joints incl. the USB-C shells." % tht_joints)
    notes.append("Upload: %s_bom.csv and %s_cpl.csv (JLCPCB's conventions: the bottom-side mirror, rotations read in previews or predicted from their drawings, the USB-C moved to their origin); %s_cpl_native.csv is KiCad's own numbers for reference."
                 % (NAME, NAME, NAME))
    notes.append("THEN READ THE PLACEMENT PREVIEW against PLACEMENT_CHECKS.txt: %d placements of %d part numbers have a predicted or unverified rotation; the bottom side's %d polarized parts hardest of all (this board stores its back-side pads mirrored left-right, %s)."
                 % (sum(len(g) for g in unchecked.values()), len(unchecked), len([r for r in tht + smt if r["side"] == "bottom" and r["fpshort"] not in jlc_rotation.ROTATION_NA]),
                    ("checked on %s" % convfp) if conv else "not checked"))
    notes.append("Hand solder (hand_solder_bom.csv): %s" % ((", ".join(r["ref"] for r in hrows) + ".") if hrows else "nothing -- every part is assembled by JLCPCB; the file is its header alone."))
    notes.append("Coordinates: the board's corner is at (%g, %g) mm on KiCad's page (pcb/place.py OX, OY); the gerbers, the drill file and the CPL all use that frame, so they agree." % (P.OX, P.OY))
    notes.append("End plates: end_panel_left/right.svg and .dxf (1:1, viewed from outside) with every connector's cutout; end_panels.txt lists them.  MEASURE which slot the board rides in and set PCB_TOP_ABOVE_FLOOR in mfg/end_panels.py before milling.")
    notes.append("")
    notes.append("COST ESTIMATE for %d boards (JLCPCB list prices, parts from their live API on %s):" % (boards, datetime.date.today().isoformat()))
    notes.append("  PCBs (6-layer, ENIG, via-in-pad)            ~$%.0f" % pcb_est)
    notes.append("  assembly setup + Extended-part loading fees  ~$%.0f" % asm_setup)
    notes.append("  SMT assembly per board x %d                  ~$%.0f" % (boards, asm_per * boards))
    notes.append("  through-hole: $%.2f per order + %d joints x $%.3f x %d boards  ~$%.0f  (per-joint rate assumed: calibrate against the cart)" % (THT_SETUP, tht_joints, THT_PER_JOINT, boards, THT_SETUP + tht_per * boards))
    notes.append("  parts for %d boards                           $%.2f" % (boards, parts_cost))
    notes.append("  TOTAL                                        ~$%.0f  (~$%.0f per board)" % (est_total, est_total / boards))
    if thin:
        notes.append("")
        notes.append("THIN STOCK (fewer than 10x what %d boards need): %s" % (boards, "; ".join("%s %s stock %d need %d" % t for t in thin)))
    open(os.path.join(OUT, "FABRICATION_NOTES.txt"), "w").write("\n".join(notes) + "\n")
    print("\n".join(notes))
    print("release in", OUT)


if __name__ == "__main__":
    main(sys.argv[1:])
