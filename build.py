#!/usr/bin/env python3
"""Make everything from source, in one command.

    python3 build.py                 schematic, ERC, netlist, board, DRC, gateware proof, release
    python3 build.py --no-pcb        stop after the schematic checks
    python3 build.py --no-route      place the board but do not route it (fast)
    python3 build.py --boards 5      how many boards the cost estimate is for

Everything in the repository that is not under gen/, pcb/, mfg/, tools/,
datasheets/ or gateware/test/ is a product of this script.
"""
import argparse, os, re, subprocess, sys, time, json, glob

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "ECP5-2ADC-2DAC"
KICAD = os.environ.get("KICAD_APPIMAGE", os.path.expanduser("~/.local/bin/kicad-10.0.6-x86_64.AppImage"))   # or kicad-cli on PATH


def cli():
    return [KICAD, "kicad-cli"] if os.path.exists(KICAD) else ["kicad-cli"]


def run(args, env=None, ok=(0,)):
    r = subprocess.run(args, capture_output=True, text=True, cwd=ROOT, env=env)
    if r.returncode not in ok:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit("FAILED: %s" % " ".join(str(a) for a in args[:3]))
    return r.stdout + r.stderr


class Step:
    def __init__(self, n):
        self.t0 = time.time(); print("\n=== " + n, flush=True)

    def done(self, msg=""):
        print("    [%5.1fs] %s" % (time.time() - self.t0, msg), flush=True)


GENERATED = ["build", "mfg/release", "gateware/test/build", "library/ours.kicad_sym", "library/ours.pretty",
             NAME + ".kicad_sch", NAME + ".kicad_pcb", NAME + ".kicad_pro", NAME + ".kicad_prl", NAME + ".kicad_dru",
             "fpga.kicad_sch", "adc.kicad_sch", "dac.kicad_sch", "ethernet.kicad_sch", "usb.kicad_sch", "power.kicad_sch",
             "gateware/ecp5_2adc_2dac.lpf", "gateware/litex/ecp5_2adc_2dac.py", "docs/images"]


def clean():
    """Everything the build makes, so what is left is what lives in git."""
    import shutil
    n = 0
    for rel in GENERATED:
        p = os.path.join(ROOT, rel)
        if os.path.isdir(p):
            shutil.rmtree(p); n += 1
        elif os.path.exists(p):
            os.remove(p); n += 1
    for p in glob.glob(os.path.join(ROOT, "*-backups")):
        shutil.rmtree(p); n += 1
    print("removed %d generated files/directories" % n)
    return 0


def relative_netlist_source(path):
    """kicad-cli writes the schematic's absolute path into the netlist's (source ...); the netlist is
    committed, so it names the file relative to the project instead (nothing in git may name a place on
    one machine: CLAUDE_PCB.md)."""
    s = open(path, encoding="utf-8").read()
    s2 = re.sub(r'\(source "[^"]*?([^"/]+\.kicad_sch)"\)', r'(source "\1")', s, count=1)
    if s2 != s:
        open(path, "w", encoding="utf-8").write(s2)


def render_docs():
    """Pictures of what was made, for the log and the README: one PDF of the
    schematic, a PNG per sheet (inkscape, if present), the board front and
    back from pcb/plot.py, and KiCad's own 3D renders."""
    import shutil
    out = os.path.join(ROOT, "docs", "images")
    os.makedirs(out, exist_ok=True)
    made = []
    subprocess.run(cli() + ["sch", "export", "pdf", "-o", os.path.join(out, NAME + "_schematic.pdf"), NAME + ".kicad_sch"], capture_output=True, cwd=ROOT)
    made.append("schematic.pdf")
    # what KiCad actually drew: every word's box from the PDF, overlapping pairs and words off the page
    # (gen/check_sch_text.py; the generator's own check works from its estimate of the text sizes)
    r = subprocess.run([sys.executable, "gen/check_sch_text.py", os.path.join(out, NAME + "_schematic.pdf"),
                        os.path.join(ROOT, "build", "sch_text_overlaps.txt")], capture_output=True, text=True, cwd=ROOT)
    print("    " + (r.stdout.strip().splitlines() or ["(text check: no output)"])[-1])
    if shutil.which("inkscape"):
        for sheet in ("ECP5-2ADC-2DAC", "fpga", "adc", "dac", "ethernet", "usb", "power"):
            d = os.path.join(ROOT, "build", "svg_" + sheet)
            subprocess.run(cli() + ["sch", "export", "svg", "-o", d, sheet + ".kicad_sch"], capture_output=True, cwd=ROOT)
            svgs = sorted(glob.glob(os.path.join(d, "*.svg")))
            if svgs:
                # no display and no session bus: with them inkscape 1.x can block forever waiting for a desktop that is not there
                env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
                env["DBUS_SESSION_BUS_ADDRESS"] = "/dev/null"
                try:
                    subprocess.run(["inkscape", svgs[0], "--export-type=png", "--export-width=3000",
                                    "--export-filename=" + os.path.join(out, "sch_%s.png" % ("root" if sheet == NAME else sheet))],
                                   capture_output=True, env=env, timeout=600)
                except subprocess.TimeoutExpired:
                    print("    inkscape timed out on", sheet)
                made.append("sch_%s.png" % ("root" if sheet == NAME else sheet))
    subprocess.run([sys.executable, "pcb/plot.py", os.path.join(out, "board_front.png")], capture_output=True, cwd=ROOT)
    subprocess.run([sys.executable, "pcb/plot.py", os.path.join(out, "board_back.png"), "--back"], capture_output=True, cwd=ROOT)
    made += ["board_front.png", "board_back.png"]
    for side in ("top", "bottom"):
        r = subprocess.run(cli() + ["pcb", "render", "--side", side, "--width", "2400", "--height", "1900", "--quality", "high",
                                    "-o", os.path.join(out, "board_3d_%s.png" % side), NAME + ".kicad_pcb"], capture_output=True, text=True, cwd=ROOT)
        if r.returncode == 0:
            made.append("board_3d_%s.png" % side)
    return ", ".join(made)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-pcb", action="store_true")
    ap.add_argument("--no-route", action="store_true")
    ap.add_argument("--no-release", action="store_true")
    ap.add_argument("--boards", type=int, default=5)
    ap.add_argument("--route-budget", type=int, default=3600)
    ap.add_argument("--clean", action="store_true", help="remove everything this script generates, then stop")
    a = ap.parse_args()
    if a.clean:
        return clean()
    t0 = time.time()
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)

    def generate(tag=""):
        s = Step("1/9  pin plan  <- gen/fpga.py" + tag)
        s.done(run([sys.executable, "gen/fpga.py"]).strip().splitlines()[-1])
        s = Step("2/9  constraints and LiteX platform  <- gen/lpf.py")
        s.done(run([sys.executable, "gen/lpf.py"]).strip().splitlines()[-1])
        s = Step("3/9  schematic  <- gen/gen.py  (its own accidental-connection and layout checks)")
        out = run([sys.executable, "gen/gen.py"])
        first = out.strip().splitlines()[0]
        if "0 accidental touches" not in first:
            print(out)
            raise SystemExit("FAILED: the schematic has accidental connections")
        s.done(first)
        # KiCad 10's own file format, so opening the project never asks to upgrade
        for f in [NAME + ".kicad_sch"] + glob.glob(os.path.join(ROOT, "*.kicad_sch")):
            run(cli() + ["sch", "upgrade", "--force", f])
        s = Step("4/9  ERC and netlist  <- kicad-cli")
        run(cli() + ["sch", "erc", "--severity-all", "--format", "json", "-o", "build/erc.json", NAME + ".kicad_sch"])
        n = sum(len(sh["violations"]) for sh in json.load(open(os.path.join(ROOT, "build", "erc.json")))["sheets"])
        run(cli() + ["sch", "export", "netlist", "-o", "build/netlist.net", NAME + ".kicad_sch"])
        relative_netlist_source(os.path.join(ROOT, "build", "netlist.net"))
        s.done("ERC: %d violations; netlist written" % n)
        if n:
            raise SystemExit("FAILED: ERC is not clean")
        # every signal path, walked through the netlist, for review (docs/SIGNAL_PATHS.md)
        open(os.path.join(ROOT, "docs", "SIGNAL_PATHS.md"), "w").write(run([sys.executable, "tools/trace_paths.py"]))

    generate()
    if not a.no_pcb:
        # the board decides which ball carries which signal: place it, match
        # exits to destinations, and if that moved anything regenerate once
        s = Step("5/9  pin swaps  <- pcb/pinswap.py  (match BGA exits to destinations, per exit pool)")
        r = subprocess.run([sys.executable, "pcb/pinswap.py"], capture_output=True, text=True, cwd=ROOT)
        s.done("\n    ".join(l for l in r.stdout.strip().splitlines()
                              if l.startswith(("river", "pool", "pinswap", "wrote")) or "CLEARANCE" in l))
        if r.returncode == 1:
            generate("  (again, with the swaps)")
            r = subprocess.run([sys.executable, "pcb/pinswap.py"], capture_output=True, text=True, cwd=ROOT)
            if r.returncode == 1:
                print("    NOTE: the swap pass did not reach a fixed point in one iteration; using the second assignment")
                generate("  (third pass)")
        elif r.returncode not in (0, 1):
            sys.stderr.write(r.stdout + r.stderr)
            raise SystemExit("FAILED: pcb/pinswap.py")
    s = Step("6/9  gateware pin proof  <- gateware/test/build.sh  (yosys + nextpnr-ecp5)")
    env = dict(os.environ, PATH=os.path.expanduser("~/openfpga/oss-cad-suite/bin") + ":" + os.environ["PATH"])
    out = run(["sh", "gateware/test/build.sh"], env=env)
    s.done("; ".join(l.strip() for l in out.splitlines() if "Max frequency" in l)[:300] or out.strip()[-200:])
    if a.no_pcb:
        print("\nstopped before the board.  %.0f s" % (time.time() - t0)); return 0
    s = Step("7/9  board  <- pcb/build_pcb.py  (placement, BGA escape, routing)")
    env = dict(os.environ, ROUTE_BUDGET=str(a.route_budget))
    out = run([sys.executable, "pcb/build_pcb.py"] + (["--place"] if a.no_route else []), env=env)
    s.done("; ".join(l.strip() for l in out.splitlines() if l.strip())[:400])
    run(cli() + ["pcb", "upgrade", "--force", NAME + ".kicad_pcb"])
    # KiCad's own pcbnew must agree with our placer about where every pad is (rotations, back side)
    out = run([sys.executable, "tools/check_pads_kicad.py"])
    print("    " + out.strip().splitlines()[0]); print("    " + out.strip().splitlines()[-1])
    if "every pad is where KiCad puts it" not in out:
        raise SystemExit("FAILED: pad positions disagree with KiCad (tools/check_pads_kicad.py)")
    out = run([sys.executable, "pcb/rotscan.py"])
    print("    rotations of the bus chips (total signal distance per rotation, lower is better):\n    " + "\n    ".join(out.strip().splitlines()))
    s = Step("8/9  DRC  <- kicad-cli pcb drc, all severities, with our rules (zones filled and SAVED: the gerbers plot what the file holds)")
    run(cli() + ["pcb", "drc", "--severity-all", "--refill-zones", "--save-board", "--format", "json", "-o", "build/drc.json", NAME + ".kicad_pcb"])
    d = json.load(open(os.path.join(ROOT, "build", "drc.json")))
    import collections
    c = collections.Counter((v["severity"], v["type"]) for v in d["violations"])
    s.done("%d violations, %d unconnected: %s" % (len(d["violations"]), len(d.get("unconnected_items", [])),
                                                   ", ".join("%s %s x%d" % (k[0], k[1], n) for k, n in sorted(c.items(), key=lambda kv: -kv[1]))[:400]))
    if a.no_release:
        return 0
    n_err = sum(1 for v in d["violations"] if v["severity"] == "error")
    n_unc = len(d.get("unconnected_items", []))
    s = Step("9/9  release  <- mfg/make_fab.py")
    out = run([sys.executable, "mfg/make_fab.py", "--boards", str(a.boards)])
    s.done("\n    ".join(out.strip().splitlines()[-8:]))
    # build 34 (JLCPCB's preview of build 33 showed 40-pin strips and turned SMAs): JLCPCB's own drawings placed where the
    # upload CPL says, against the board -- the preview, computed.  A placement that would look wrong stops the build.
    s = Step("9b   preview check  <- mfg/preview_check.py  (JLCPCB's drawings at the CPL's positions and angles)")
    out = run([sys.executable, "mfg/preview_check.py"])
    s.done("\n    ".join(out.strip().splitlines()[-6:]))
    s = Step("10   renders  -> docs/images  (schematic PDF and PNGs, board PNGs, 3D views)")
    s.done(render_docs())
    if n_err or n_unc:
        with open(os.path.join(ROOT, "mfg", "release", "FABRICATION_NOTES.txt"), "a") as f:
            f.write("\n*** DRC: %d errors, %d unconnected items (build/drc.json).  DO NOT ORDER THIS RELEASE. ***\n" % (n_err, n_unc))
        print("\nBUILT in %.0f s, BUT the board has %d DRC errors and %d unconnected items: not orderable" % (time.time() - t0, n_err, n_unc))
        return 1
    print("\nBUILT in %.0f s; DRC clean, release in mfg/release/" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
