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
# JLCPCB's charges, line by line as their cart itemises them, CALIBRATED against this board's real order (Jason,
# 2026-10-08: 5 PCBs, 2 assembled, 6 layers, 158 x 119 mm, ENIG, epoxy-filled vias, Standard PCBA both sides plus
# through-hole, depanelled): PCB $47.25, PCBA $566.49, depanel $2.32, before shipping and duty.  "order" lines are
# charged once; "per_board" lines scale with the boards assembled; the rest are computed from the BOM.
FEES = {
    "engineering":          (33.00, "order",  "6-layer engineering fee"),
    "board_per_pcb":        (2.64,  "pcb",    "the bare board: $13.20 for 5 of these 158 x 119 mm 6-layer ENIG boards (scaled per PCB beyond 5: an assumption)"),
    "confirm_production":   (1.05,  "order",  "confirm production file"),
    "enig_per_5":           (18.80, "pcb",    "ENIG surface finish, $18.80 for 5 (cart of 2026-10-09; the itemised cart of 2026-10-08 was OSP, with no such line)"),
    "setup":                (51.50, "order",  "Standard PCBA setup, both sides"),
    "stencil":              (16.54, "order",  "stencils, both sides"),
    "feeder_per_extended":  (2.70,  "extended", "feeder loading: $132.33 for 49 Extended codes ($3 list less a discount, or THT parts cheaper: calibrated, not explained)"),
    "smt_per_pad":          (0.0017, "pad",   "SMT assembly per pad (JLCPCB's published rate) ..."),
    "smt_per_board":        (1.50,  "per_board", "... plus $1.50 a board: 2 x (1631 x 0.0017 + 1.50) = $8.55, the cart said $8.52"),
    "hand_solder_labour":   (3.61,  "order",  "hand-soldering labour, once an order has through-hole parts"),
    "tht_per_joint":        (0.0157, "joint", "manual assembly per through-hole joint (146 a board, the USB-Cs' shell legs included)"),
    "assembly_fixture":     (16.54, "order",  "PCB assembly fixture (double-sided board with through-hole parts)"),
    "xray_per_board":       (1.65,  "per_board", "X-ray inspection for the BGA ($3.30 for 2)"),
    "packaging":            (0.51,  "order",  "packaging"),
    "special_components":   (0.12,  "order",  "special components fee"),
    "depanel":              (2.32,  "order",  "depanel boards and edge rail before delivery (advanced option)"),
}
DUTY = 0.35              # US DDP duty JLCPCB pre-collects on PCBs and assembly (CLAUDE_PCB.md section 3): not in the cart total
SHIPPING = (31.23, "DHL Express (DDP), 2-4 business days, 0.45 kg: JLCPCB's estimate, 2026-10-09")

# JLCPCB's order form, field by field IN THE FORM'S OWN ORDER (Jason, 2026-10-09: the notes he uploads from must read down
# the form, so nothing is missed or mis-set on the many re-uploads).  A value in <angle brackets> is computed in jlc_form().
# (section, field, value, why)
JLC_PCB_FORM = [
    ("", "Base Material", "FR-4", ""),
    ("", "Layers", "<layers>", "High Precision PCB row"),
    ("", "Dimensions", "<dims>", "the board outline"),
    ("", "PCB Qty", "<pcbs>", "JLCPCB's minimum; <boards> of them assembled"),
    ("", "Product Type", "Industrial/Consumer electronics", "the only true one of the three (Aerospace, Medical); duty is 35% whatever is chosen"),
    ("PCB Specifications", "Different Design", "1", ""),
    ("PCB Specifications", "Delivery Format", "Single PCB", "JLCPCB adds and removes the assembly rails (see Depanel below)"),
    ("PCB Specifications", "PCB Thickness", "<thickness>", "the stack-up's total"),
    ("PCB Specifications", "PCB Color", "Green", ""),
    ("PCB Specifications", "Silkscreen", "White", ""),
    ("PCB Specifications", "Material Type", "FR4 TG155", "a 0.8 mm BGA reflowed twice (both sides) plus through-hole: TG155 rather than the TG135 default.  If Specify Stackup sets the material, take what it sets"),
    ("PCB Specifications", "Surface Finish", "ENIG", "not OSP: flat for the 0.8 mm BGA and 0.4 mm QFP/QFN, survives the second side's reflow and the through-hole soldering, keeps for rework and probing"),
    ("PCB Specifications", "Gold Thickness", "1 U\"", "appears under ENIG; 2 U\" is for gold fingers and wearing contacts, and the board has none"),
    ("High-spec Options", "Outer Copper Weight", "1 oz", "the stack-up's"),
    ("High-spec Options", "Inner Copper Weight", "0.5 oz", "the stack-up's"),
    ("High-spec Options", "Specify Layer Sequence", "No", "the Gerber names and the job file give the order"),
    ("High-spec Options", "Specify Stackup", "Yes: <stackup>", "the 50 ohm SMA feeds (<rfw> mm) and the 100 ohm MDI pairs are drawn for it.  If it is not offered, STOP and ask"),
    ("High-spec Options", "Via Covering", "Epoxy Filled & Capped", "via-in-pad under the BGA and the back-side decoupling on ball vias"),
    ("High-spec Options", "Min via hole size/diameter", "<minvia>", "the board's smallest via is <smallvia>"),
    ("High-spec Options", "Board Outline Tolerance", "+-0.2mm (Regular)", "the extrusion's slots take it"),
    ("High-spec Options", "Confirm Production file", "Yes", "about $1: JLCPCB's production Gerbers come back to check before they make it"),
    ("High-spec Options", "Mark on PCB", "Remove Mark", "no order number printed (the back silk's JLCJLCJLCJLC, in the slot band, then prints as plain text)"),
    ("High-spec Options", "Electrical Test", "Flying Probe Fully Test", ""),
    ("High-spec Options", "Gold Fingers", "No", ""),
    ("High-spec Options", "Castellated Holes", "No", ""),
    ("High-spec Options", "Press-Fit Hole", "No", ""),
    ("High-spec Options", "Edge Plating", "No", ""),
    ("High-spec Options", "Blind Slots", "No", ""),
    ("High-spec Options", "UL Marking", "No", ""),
    ("High-spec Options", "Backdrill", "No", ""),
    ("High-spec Options", "Humidity Indicator Card", "No", ""),
]
JLC_PCBA_FORM = [
    ("PCB Assembly", "PCB Assembly", "On", ""),
    ("PCB Assembly", "PCBA Type", "Standard", "Economic cannot assemble both sides"),
    ("PCB Assembly", "Assembly Side", "<sides>", "<sides_why>"),
    ("PCB Assembly", "PCBA Qty", "<boards>", ""),
    ("PCB Assembly", "Tooling holes", "Added by JLCPCB", ""),
    ("PCB Assembly", "Confirm Parts Placement", "Yes", "free: the placement preview, read against PLACEMENT_CHECKS.txt -- BOTH sides"),
    ("PCB Assembly", "Stencil Storage", "No", ""),
    ("PCB Assembly", "Fixture Storage", "No", ""),
    ("PCB Assembly", "Parts Selection", "By Customer (Self-Service)", "the BOM carries every LCSC code"),
    ("Advanced Options", "Bake Components", "No", ""),
    ("Advanced Options", "Photo Confirmation", "No", ""),
    ("Advanced Options", "Board Cleaning", "No", ""),
    ("Advanced Options", "Conformal Coating", "No", ""),
    ("Advanced Options", "Special stencil", "No", ""),
    ("Advanced Options", "Packaging", "Antistatic bubble film", "the default"),
    ("Advanced Options", "Depanel boards & edge rail before delivery", "Yes", "about $2: the boards come without JLCPCB's rails"),
    ("Advanced Options", "Solder Paste", "High temp.", "the default, lead-free"),
    ("Advanced Options", "Flying Probe Test", "No", "the bare boards are already flying-probe tested"),
    ("Advanced Options", "Nitrogen reflow soldering", "(leave as offered)", ""),
    ("Advanced Options", "Function test", "No", ""),
    ("Advanced Options", "Assembly remark", "No", ""),
    ("Stencil", "Stencil", "Off", "the assembly makes its own"),
    ("Files", "BOM", "<name>_bom.csv", ""),
    ("Files", "CPL", "<name>_cpl_jlcpcb_upload.csv", "not the _kicad_native one"),
]
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
    for name, corrected in (("%s_cpl_jlcpcb_upload.csv" % NAME, True), ("%s_cpl_kicad_native.csv" % NAME, False)):
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
                    if r["lcsc"] in jlc_rotation.VIEWER_HALF_TURN:
                        # JLCPCB's viewer turns this part's drawing a half turn about its body's centre B; every pad then
                        # lands 2B (turned with the part) away, so the CPL point goes back by that (x right, y up)
                        if r["side"] != "top":
                            raise SystemExit("FAILED: %s: a viewer half turn on the bottom side is not handled" % r["ref"])
                        bc = FC.body_centre(r["lcsc"])
                        if bc is None:
                            raise SystemExit("FAILED: %s: no body outline in JLCPCB's drawing of %s" % (r["ref"], r["lcsc"]))
                        a = math.radians(rot)
                        tx = 2 * bc[0] * math.cos(a) + 2 * bc[1] * math.sin(a)          # 2B turned with the part, y down
                        ty = -2 * bc[0] * math.sin(a) + 2 * bc[1] * math.cos(a)
                        dx, dy = round(dx - tx, 3), round(dy + ty, 3)
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
        L += ["MOVED in %s_cpl_jlcpcb_upload.csv to where JLCPCB's library puts the part's origin (their drawing's zero is not" % NAME,
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
    L += ["", "Read right in a preview already (this board's, or the Icepi and GPSDO boards'): " + " ".join(read)]
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
        # what JLCPCB buys and charges (calibrated 2026-10-08, the ECP5 cart: $326.72 against their $328.93): the parts
        # needed plus the attrition they add per line (lossNumber: 10 extra 0402s), and at least a feeder's minimum
        # (leastPatchNumber), at the price break of that quantity
        bought = max(need + int(p.get("lossNumber") or 0), int(p.get("leastPatchNumber") or 0), 1)
        price = jlc_api.unit_price(p, bought)
        if lt not in ("Basic", "Preferred"):
            ext += 1
        total_parts += price * bought
        if stock < need * 10:
            thin.append((code, p.get("componentModelEn", ""), stock, need))
        lines.append((code, n, lt, stock, price, p.get("componentModelEn", "")))
    return lines, total_parts, ext, thin


# JLCPCB's defaults as the form opens (screenshots of 2026-10-09).  A field whose value here differs is marked ">>" in the
# notes, with the default to avoid: a late-night upload must not keep a default by mistake (Jason, 2026-10-09).
JLC_DEFAULTS = {
    "Layers": "2", "PCB Qty": "5", "Product Type": "Industrial/Consumer electronics", "Different Design": "1",
    "Delivery Format": "Single PCB", "PCB Thickness": "1.6mm", "PCB Color": "Green", "Silkscreen": "White",
    "Material Type": "FR4 TG135", "Surface Finish": "OSP", "Gold Thickness": "1 U\"", "Outer Copper Weight": "1 oz",
    "Inner Copper Weight": "0.5 oz", "Specify Layer Sequence": "No", "Specify Stackup": "No",
    "Via Covering": "Epoxy Filled & Capped", "Min via hole size/diameter": "0.3mm/(0.4/0.45mm)",
    "Board Outline Tolerance": "+-0.2mm (Regular)", "Confirm Production file": "No", "Mark on PCB": "Remove Mark",
    "Electrical Test": "Flying Probe Fully Test", "Gold Fingers": "No", "Castellated Holes": "No", "Press-Fit Hole": "No",
    "Edge Plating": "No", "Blind Slots": "No", "UL Marking": "No", "Backdrill": "No", "Humidity Indicator Card": "No",
    "PCB Assembly": "Off", "PCBA Type": "Economic", "Assembly Side": "Top Side", "PCBA Qty": "5",
    "Tooling holes": "Added by JLCPCB", "Confirm Parts Placement": "No", "Stencil Storage": "No", "Fixture Storage": "No",
    "Parts Selection": "By Customer (Self-Service)", "Bake Components": "No", "Photo Confirmation": "No",
    "Board Cleaning": "No", "Conformal Coating": "No", "Special stencil": "No", "Packaging": "Antistatic bubble film",
    "Depanel boards & edge rail before delivery": "No", "Solder Paste": "High temp.", "Flying Probe Test": "No",
    "Function test": "No", "Assembly remark": "No", "Stencil": "Off",
}


def jlc_form(m, boards, rows, rf_w):
    """The order form as text, in JLCPCB's order: section headings, then 'field ...... value   (why)'."""
    import place as P
    pcbs = max(5, boards)
    layers = sum(1 for l in ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"))
    vias = m["vias"]                                          # (diameter, drill)
    d_min = min(d for _, d in vias); s_at = min(s for s, d in vias if d == d_min)
    options = [(0.3, (0.4, 0.45)), (0.25, (0.35, 0.4)), (0.2, (0.3, 0.35)), (0.15, (0.25, 0.3)), (0.1, (0.2, 0.25))]
    hole, dias = next((h, ds) for h, ds in options if h <= d_min + 1e-6)
    sides = sorted({r["side"] for r in rows if r["cls"] in ("smt", "tht")})
    subs = {"<layers>": "%d (High Precision PCB)" % layers, "<dims>": "%g x %g mm" % (P.BW, P.BH), "<pcbs>": str(pcbs),
            "<boards>": str(boards), "<thickness>": "1.6mm", "<stackup>": "JLC06161H-7628", "<rfw>": "%.2f" % rf_w,
            "<minvia>": "%gmm/(%g/%gmm)" % (hole, dias[0], dias[1]), "<smallvia>": "%g mm across, %g mm drill" % (s_at, d_min),
            "<sides>": "Both Sides" if len(sides) == 2 else ("Top Side" if sides == ["top"] else "Bottom Side"),
            "<sides_why>": "parts on both sides (the BGA's decoupling, the regulators, the magnetics and the microSD on the back)" if len(sides) == 2 else "",
            "<name>": NAME}
    def fill(s):
        for k, v in subs.items():
            s = s.replace(k, v)
        return s
    out = ["JLCPCB ORDER FORM -- set it top to bottom; the fields are in the form's own order (as of 2026-10-09).",
           "A line marked >> is NOT JLCPCB's default: change it, and do not leave the default named on its right.", ""]
    n_change = 0
    for title, form in (("PCB", JLC_PCB_FORM), ("PCBA", JLC_PCBA_FORM)):
        last = None
        for sec, field, value, why in form:
            head = sec or title
            if head != last:
                out.append("  %s" % head); last = head
            v = fill(value)
            d = JLC_DEFAULTS.get(field)
            change = d is not None and not v.startswith(d) and not v.startswith("(")
            n_change += change
            mark = ">> " if change else "   "
            tail = ("NOT the default %s.  " % d if change else "") + (("(" + fill(why) + ")") if why else "")
            out.append("  %s %-44s %-30s %s" % (mark, field + " " + "." * max(2, 42 - len(field)), v, tail))
        out.append("")
    out.insert(2, "%d fields differ from JLCPCB's defaults." % n_change)
    return out


def calibration_total(rows, lines, ext, smt_pads, tht_joints, n_tht):
    """The model's total for the order it was calibrated on (5 PCBs, 2 assembled), whatever --boards says: a check that
    the fees and the parts model still add up to JLCPCB's $616.06 when prices move."""
    f = {k: v[0] for k, v in FEES.items()}
    parts = 0.0
    asm = assembled(rows)
    cnt = collections.Counter(r["lcsc"] for r in asm)
    for code, n in cnt.items():
        p, ts = jlc_api.by_code(code)
        if not p:
            continue
        bought = max(n * 2 + int(p.get("lossNumber") or 0), int(p.get("leastPatchNumber") or 0), 1)
        parts += jlc_api.unit_price(p, bought) * bought
    return (f["engineering"] + f["board_per_pcb"] * 5 + f["confirm_production"] + f["setup"] + f["stencil"] + parts
            + f["feeder_per_extended"] * ext + (f["smt_per_pad"] * smt_pads + f["smt_per_board"]) * 2 + (f["hand_solder_labour"] if n_tht else 0)
            + f["tht_per_joint"] * tht_joints * 2 + f["assembly_fixture"] + f["xray_per_board"] * 2 + f["packaging"]
            + f["special_components"] + f["depanel"])


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
    boards = 2
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
    # build 34 (JLCPCB's preview of build 33): a part of three or more pads that numbers its pins differently from KiCad
    # gets no prediction, and builds 1-33 then sent it at KiCad's angle -- the SMAs lay along the edge and the Pmod sockets
    # stood a quarter turn round.  Every such part must be read from JLCPCB's drawing and put in jlc_rotation's table
    # (or have its footprint read in a preview) before a release is written.
    unread = sorted({r["lcsc"] for r in assembled(rows) if preds.get(r["lcsc"], (None, ""))[0] is None
                     and "no fit by pin number" in preds.get(r["lcsc"], (None, ""))[1]
                     and r["lcsc"] not in jlc_rotation.JLC_ROTATION_BY_PART and not jlc_rotation.checked(r["fpshort"], r["lcsc"])})
    if unread:
        raise SystemExit("FAILED: no rotation for %s: their pins are numbered unlike KiCad's, so nothing predicts how JLCPCB's "
                         "drawing sits; read the body's direction off its land drawing and add it to mfg/jlc_rotation.JLC_ROTATION_BY_PART" % unread)
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
    smt_pads = sum(r["npads"] - r["nth"] for r in smt)                        # every SMT pad is a joint (the BGA's 256 included)
    tht_joints = sum(r["nth"] for r in tht) + sum(r["nth"] for r in smt)       # the SMT USB-Cs' shell legs are soldered too
    pcbs = max(5, boards)
    f = {k: v[0] for k, v in FEES.items()}
    cart = [("PCB", "engineering fee", f["engineering"]),
            ("PCB", "board (%d PCBs)" % pcbs, f["board_per_pcb"] * pcbs),
            ("PCB", "confirm production file", f["confirm_production"]),
            ("PCB", "surface finish, ENIG (%d PCBs)" % pcbs, f["enig_per_5"] * pcbs / 5.0),
            ("PCBA", "setup fee", f["setup"]),
            ("PCBA", "stencil", f["stencil"]),
            ("PCBA", "components (%d lines, with JLCPCB's attrition)" % len(lines), parts_cost),
            ("PCBA", "feeders loading fee (%d Extended codes x $%.2f)" % (ext, f["feeder_per_extended"]), f["feeder_per_extended"] * ext),
            ("PCBA", "SMT assembly (%d pads x $%.4f + $%.2f, x %d)" % (smt_pads, f["smt_per_pad"], f["smt_per_board"], boards), (f["smt_per_pad"] * smt_pads + f["smt_per_board"]) * boards),
            ("PCBA", "hand-soldering labour fee", f["hand_solder_labour"] if n_tht else 0.0),
            ("PCBA", "manual assembly (%d through-hole joints x $%.4f x %d)" % (tht_joints, f["tht_per_joint"], boards), f["tht_per_joint"] * tht_joints * boards),
            ("PCBA", "PCB assembly fixture", f["assembly_fixture"]),
            ("PCBA", "X-ray inspection (%d x $%.2f)" % (boards, f["xray_per_board"]), f["xray_per_board"] * boards),
            ("PCBA", "packaging fee", f["packaging"]),
            ("PCBA", "special components fee", f["special_components"]),
            ("option", "depanel boards and edge rail", f["depanel"])]
    est_total = sum(c[2] for c in cart)
    with open(os.path.join(OUT, "cost_estimate.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["LCSC", "per board", "library", "stock", "unit price USD @ %d" % boards, "part"])
        for row in lines:
            w.writerow(row)
    notes = []
    notes.append("%s rev A -- FABRICATION NOTES (written %s)\n" % (NAME, datetime.date.today().isoformat()))
    rf_w = float(re.search(r"^RF_W = ([\d.]+)", open(os.path.join(ROOT, "pcb", "build_pcb.py")).read(), re.M).group(1))   # the 50 ohm width, from its one source
    notes += jlc_form(m, boards, rows, rf_w)
    notes.append("NOTES")
    notes.append("Board: %.0f x %.0f mm, 6 layers, 1.6 mm, JLCPCB stackup JLC06161H-7628 (1 oz outer, 0.5 oz inner, 7628 prepreg)." % (P.BW, P.BH))
    notes.append("Surface finish: ENIG (there is a 0.8 mm pitch BGA).  Solder mask green, silkscreen white.")
    notes.append("Via-in-pad under the BGA: all 0.3 mm / 0.15 mm vias must be epoxy filled and capped (JLCPCB's default for 6+ layers; tick it).")
    notes.append("The FPGA's 100 nF decoupling sits on the BACK directly under the BGA, each 0402 on two adjacent ball vias (0.8 mm pitch): those vias must be capped on the back too (the filled-and-capped option covers both sides).")
    notes.append("Enclosure: Hammond 1455Q (125 x 51.5 mm extrusion, 160 or 220 mm long); the board's long edges slide into its PCB slots, so nothing sits within 3.5 mm of them.  SMAs through the left end plate, all other connectors through the right one.")
    notes.append("Photodiode D103 uses ours:VBPW34S_K1_A2 (LCSC's footprint with pads renumbered so pad 1 is the cathode); its orientation on the board is the same as JLCPCB's library part, pad 1 of theirs (the anode) on the -5 V side.  Check it in the placement preview.")
    notes.append("The mini-HDMI jack is wired with type C pin numbering (shield first in each pair, DDC ground 13, CEC 14); its four shell tabs (pads 20-23) are grounded.")
    notes.append("Minimum track/space on the board: %.3f mm (inside the BGA fan-out; 0.127 mm elsewhere).  Via sizes: %s.  Smallest drill %.2f mm."
                 % (m["min_track"] or 0, ", ".join("%g/%g" % v for v in m["vias"]), m["min_drill"] or 0))
    notes.append("Fiducials: three 1 mm copper dots in 2 mm mask openings, front and back, at %s mm from the board's top-left corner (x right, y down); JLCPCB adds its own on the panel rails as well." % ", ".join("(%.1f, %.1f)" % f for f in P.FIDUCIALS))
    notes.append("Layer markers: the copper layer numbers 1-6, each in copper on its own layer, in a row at the top edge (x %.0f-%.0f, y %.1f mm, inside the extrusion's slot band): hold the bare board against the light to check the layer order." % (P.LAYER_MARK[0], P.LAYER_MARK[0] + 5 * P.LAYER_MARK[2], P.LAYER_MARK[1]))
    notes.append("Order number: the back silkscreen carries JLCJLCJLCJLC at the top edge (x %.0f, y %.1f mm, in the slot band).  On the order form choose 'Remove order number: Specify a location'; JLCPCB prints its number there, hidden by the extrusion." % P.ORDER_MARK)
    notes.append("Impedance: ask for controlled impedance with the JLC06161H-7628 calculator: 50 ohm single-ended (SMA runs, 0.35 mm drawn) and 100 ohm differential (Ethernet MDI, 0.2 mm / 0.2 mm drawn), referenced to In1.")
    notes.append("The shipped board file holds %d filled zone polygons; DRC 0 errors / 0 unconnected (build/drc.json)." % n_fill)
    notes.append("")
    notes.append("Assembly (JLCPCB Standard, SMT both sides + through-hole on top): %d SMT placements and %d through-hole parts on %d BOM lines, %d of them Extended parts (each carries a one-off loading fee)."
                 % (n_smt, n_tht, n_lines, ext))
    notes.append("Through-hole, fitted by JLCPCB (Jason, 2026-10-06): the six SMA jacks, the RJ45, the DIP switch, the 2.54 mm headers (ordered as 1x40 / 2x40 strips the assembler snaps to length, as on the GPSDO board) and the two Pmod sockets.  %d through-hole joints incl. the USB-C shells." % tht_joints)
    notes.append("Upload: %s_bom.csv and %s_cpl_jlcpcb_upload.csv (JLCPCB's conventions: the bottom-side mirror, rotations read in previews or predicted from their drawings, the USB-C moved to their origin); %s_cpl_kicad_native.csv is KiCad's own numbers for reference."
                 % (NAME, NAME, NAME))
    notes.append("THEN READ THE PLACEMENT PREVIEW against PLACEMENT_CHECKS.txt: %d placements of %d part numbers have a predicted or unverified rotation; the bottom side's %d polarized parts hardest of all (this board stores its back-side pads mirrored left-right, %s)."
                 % (sum(len(g) for g in unchecked.values()), len(unchecked), len([r for r in tht + smt if r["side"] == "bottom" and r["fpshort"] not in jlc_rotation.ROTATION_NA]),
                    ("checked on %s" % convfp) if conv else "not checked"))
    notes.append("Hand solder (hand_solder_bom.csv): %s" % ((", ".join(r["ref"] for r in hrows) + ".") if hrows else "nothing -- every part is assembled by JLCPCB; the file is its header alone."))
    notes.append("Coordinates: the board's corner is at (%g, %g) mm on KiCad's page (pcb/place.py OX, OY); the gerbers, the drill file and the CPL all use that frame, so they agree." % (P.OX, P.OY))
    notes.append("End plates: end_panel_left/right.svg and .dxf (1:1, viewed from outside) with every connector's cutout; end_panels.txt lists them.  MEASURE which slot the board rides in and set PCB_TOP_ABOVE_FLOOR in mfg/end_panels.py before milling.")
    notes.append("")
    notes.append("COST ESTIMATE: %d PCBs, %d assembled, itemised as JLCPCB's cart is (fees calibrated against this board's real order on"
                 " 2026-10-08; parts from their live API on %s):" % (pcbs, boards, datetime.date.today().isoformat()))
    for group, what, usd in cart:
        notes.append("  %-6s %-62s $%8.2f" % (group, what, usd))
    notes.append("  %-6s %-62s $%8.2f  ($%.0f per assembled board)" % ("TOTAL", "before shipping and duty", est_total, est_total / boards))
    notes.append("  US duty, DDP, about %.0f%% of that: ~$%.0f more.  Shipping: $%.2f, %s." % (100 * DUTY, DUTY * est_total, SHIPPING[0], SHIPPING[1]))
    notes.append("  (The order of 2026-10-08, 5 PCBs and 2 assembled with OSP, came to $616.06 in JLCPCB's cart; this model gives $%.2f for it.)" % calibration_total(rows, lines, ext, smt_pads, tht_joints, n_tht))
    if thin:
        notes.append("")
        notes.append("THIN STOCK (fewer than 10x what %d boards need): %s" % (boards, "; ".join("%s %s stock %d need %d" % t for t in thin)))
    open(os.path.join(OUT, "FABRICATION_NOTES.txt"), "w").write("\n".join(notes) + "\n")
    print("\n".join(notes))
    print("release in", OUT)


if __name__ == "__main__":
    main(sys.argv[1:])
