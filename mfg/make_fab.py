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
HAND = ("J301", "J302", "J101", "J102", "J204", "J205",      # right-angle SMA jacks at the left edge
        "J303", "J304", "J305", "J601", "J105", "J106", "J210",  # headers and sockets
        "JP101", "JP102", "JP103", "JP104", "JP201", "JP202", "JP203", "JP204", "JP1203", "JP2009", "JP3001",
        "SW101", "J401")                                      # DIP switch, RJ45


def cli():
    for c in (os.environ.get("KICAD_CLI"), os.path.expanduser("~/.local/bin/kicad-10.0.6-x86_64.AppImage")):
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
        fp = fplib.load(fpid)
        short = fpid.split(":", 1)[1]
        code = lcsc.get(ref, "")
        if ref.startswith("TP") or ref.startswith("H"):
            cls = "none"
        elif ref in HAND or not fp["smd"]:
            cls = "tht"
        elif not code:
            cls = "nocode"
        else:
            cls = "smt"
        rows.append(dict(ref=ref, value=vals.get(ref, ""), fp=fpid, fpshort=short, lcsc=code, x=x, y=y, rot=rot,
                         side="bottom" if layer == "B.Cu" else "top", cls=cls))
    return rows


def write_bom_cpl(rows, outdir):
    smt = [r for r in rows if r["cls"] == "smt"]
    by = collections.defaultdict(list)
    for r in smt:
        by[r["lcsc"]].append(r)
    bom = os.path.join(outdir, "%s_bom.csv" % NAME)
    with open(bom, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for code, group in sorted(by.items(), key=lambda kv: -len(kv[1])):
            vals = sorted({g["value"] for g in group}, key=lambda v: (-len(v), v))
            fps = sorted({g["fpshort"] for g in group})
            w.writerow([vals[0], ",".join(g["ref"] for g in group), fps[0], code])
    cpl = os.path.join(outdir, "%s_cpl.csv" % NAME)
    unchecked = collections.Counter()
    with open(cpl, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in smt:
            rot = jlc_rotation.cpl_rotation(r["rot"], r["side"], r["fpshort"])
            if not jlc_rotation.checked(r["fpshort"]):
                unchecked[r["fpshort"]] += 1
            w.writerow([r["ref"], "%.3fmm" % r["x"], "%.3fmm" % (-r["y"]), r["side"], "%g" % rot])
    hand = os.path.join(outdir, "hand_solder_bom.csv")
    with open(hand, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Value", "Footprint", "LCSC (to order loose)"])
        for r in rows:
            if r["cls"] in ("tht", "nocode"):
                w.writerow([r["ref"], r["value"], r["fpshort"], r["lcsc"]])
    return bom, cpl, hand, unchecked, len(smt), len(by)


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
    """Stock and price per distinct LCSC code, from JLCPCB's parts API."""
    smt = [r for r in rows if r["cls"] == "smt"]
    cnt = collections.Counter(r["lcsc"] for r in smt)
    lines, total_parts, ext = [], 0.0, 0
    thin = []
    wrong = code_value_check(smt + [r for r in rows if r["cls"] == "tht" and r["lcsc"]], refresh)   # the loose-ordered parts too
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


def code_value_check(smt, refresh=False):
    """Every ordered code's JLCPCB description must carry the value the schematic gives the part (passives: the
    number and unit; parts with a part-number value: the part number) and its package.  Returns the offenders."""
    pkg = {"R_0603_1608Metric": "0603", "C_0402_1005Metric": "0402", "C_0402_1005Metric_BGA": "0402", "C_0603_1608Metric": "0603",
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
    rows = components()
    nocode = [r["ref"] for r in rows if r["cls"] == "nocode"]
    if nocode:
        # build 20: the converters, op amps, HDMI jack and microSD socket had no code and had joined the
        # hand-solder list without a word.  A part JLCPCB is meant to fit must have a code, or the release lies.
        raise SystemExit("FAILED: SMD parts without an LCSC code (fix gen/parts.py, or add them to HAND): %s" % ", ".join(nocode))
    bom, cpl, hand, unchecked, n_smt, n_lines = write_bom_cpl(rows, OUT)
    zpath = export_gerbers(OUT)
    import end_panels
    end_panels.main()                                   # the enclosure's two end plates, with every connector's cutout
    lines, parts_cost, ext, thin = cost(rows, boards, refresh)
    m = measure()
    import place as P
    area_dm2 = P.BW * P.BH / 10000.0
    # JLCPCB's public 6-layer pricing is not a formula they publish; these are the
    # 2026 list-price neighbourhoods for a 130 x 95 mm 6-layer ENIG board with
    # via-in-pad, and are labelled as estimates in the notes
    pcb_est = 70.0 + 12.0 * boards
    asm_setup = 8.0 + 3.0 * ext            # one-off: setup plus a loading fee per Extended part
    joints = sum(1 for r in rows if r["cls"] == "smt") * 3
    asm_per = 0.0017 * joints + 1.5
    est_total = pcb_est + asm_setup + asm_per * boards + parts_cost
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
    notes.append("")
    notes.append("Assembly (JLCPCB SMT, both sides): %d placements on %d BOM lines, %d of them Extended parts (each carries a one-off loading fee)." % (n_smt, n_lines, ext))
    notes.append("Upload: %s_bom.csv and %s_cpl.csv.  The CPL rotations are KiCad native with the corrections in mfg/jlc_rotation.py applied;" % (NAME, NAME))
    notes.append("CHECK THESE PACKAGES IN THE PLACEMENT PREVIEW (no verified correction yet): %s" % (", ".join("%s x%d" % kv for kv in sorted(unchecked.items())) or "none"))
    notes.append("Hand solder (hand_solder_bom.csv): the right-angle SMA jacks, the headers, the Pmod sockets, the DIP switch, the RJ45 jack.")
    notes.append("End plates: end_panel_left/right.svg and .dxf (1:1, viewed from outside) with every connector's cutout; end_panels.txt lists them.  MEASURE which slot the board rides in and set PCB_TOP_ABOVE_FLOOR in mfg/end_panels.py before milling (all cutouts move together).")
    notes.append("")
    notes.append("COST ESTIMATE for %d boards (JLCPCB list prices, parts from their live API on %s):" % (boards, datetime.date.today().isoformat()))
    notes.append("  PCBs (6-layer, ENIG, via-in-pad)            ~$%.0f" % pcb_est)
    notes.append("  assembly setup + Extended-part loading fees  ~$%.0f" % asm_setup)
    notes.append("  assembly per board x %d                      ~$%.0f" % (boards, asm_per * boards))
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
