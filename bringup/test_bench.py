#!/usr/bin/env python3
"""test_bench.py: the bench tool against the simulated bench, before any hardware is connected.

    python3 bringup/test_bench.py              # everything: about 25 minutes (v1b's co-simulation is the long pole)
    python3 bringup/test_bench.py --quick      # parts 1-3 only: a few seconds, no co-simulation
    python3 bringup/test_bench.py --jobs 4     # how many co-simulations run side by side (8 unless said)

It touches no instrument, no serial port and no network: every command it runs carries --sim, and the real
drivers are imported only to read their method signatures (never instantiated).  It prints one ok / FAIL line
a check and ends with PASS or FAIL (exit status 0 or 1).

  1. the fakes of simbench.py against the real drivers: every instrument attribute the tool uses exists in the
     real class and in the fake, and the fake's methods take the same arguments, with the same names and
     defaults, as the real ones;
  2. the arithmetic of analysis.py on made-up data, and the pieces that only run on the bench as far as they
     can be tried without it (reading openFPGALoader's output, the generators' voltage limits);
  3. the bench claims, on a scratch record ($BENCH_CLAIMS_FILE): refused without a claim, refused when another
     project holds an instrument;
  4. every command of bench.py under --sim, each as its own process exactly as it is typed, with injected
     faults (a shorted supply, crossed cables, a missing card, a jumper left out, ...): the right verdict in
     plain words, and never a traceback.  Their outputs are kept in data/sim/test_bench/<name>.log.
"""
import argparse
import ast
import inspect
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analysis                      # noqa: E402
import bench                         # noqa: E402  (puts ~/lab-instrument-control and gateware/bringup/host on the path)
import simbench                      # noqa: E402

OUT = os.path.join(HERE, "data", "sim", "test_bench")       # the commands' outputs, the scratch claim record
TOOL_FILES = ["bench.py", "visit1.py", "visit2.py", "visit3.py"]
results = []                         # (ok, text)


def check(ok, text, detail=""):
    results.append(bool(ok))
    print("%s  %s%s" % ("ok  " if ok else "FAIL", text, ("\n        " + detail) if (detail and not ok) else ""), flush=True)
    return bool(ok)


# =================================================================================================================
# 1. the fakes against the real drivers
# =================================================================================================================
def real_classes():
    """The real driver classes, imported but never instantiated: importing them opens nothing."""
    from agilent_E36xxA import AgilentE36xxA
    from fluke_45 import Fluke45
    from siglent_SDS2104X import SDS2104X
    from siglent_SDG1032X import SDG1032X
    from agilent_33220A import Agilent33220A
    return {"psu": AgilentE36xxA, "dmm": Fluke45, "scope": SDS2104X, "gen": SDG1032X, "hpgen": Agilent33220A}


def instrument_uses():
    """Every `<something>.psu.<name>`, `.dmm.<name>`, `.scope.<name>`, `.gen.<name>`, `.hpgen.<name>` in the tool's
    source: the set of (instrument, name), with where it was first seen."""
    uses = {}
    for name in TOOL_FILES:
        with open(os.path.join(HERE, name)) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) and node.value.attr in ("psu", "dmm", "scope", "gen", "hpgen"):
                uses.setdefault((node.value.attr, node.attr), "%s line %d" % (name, node.lineno))
    return uses


def parameters(function):
    """A function's parameters as a list of (name, kind, default), `self` left out."""
    return [(p.name, p.kind.name, None if p.default is p.empty else p.default) for p in inspect.signature(function).parameters.values() if p.name != "self"]


def test_fakes():
    print("\n1. the fakes against the real drivers")
    real = real_classes()
    sim = simbench.SimBench("instruments")
    fake = {"psu": sim.psu, "dmm": sim.dmm, "scope": sim.scope, "gen": sim.gen, "hpgen": sim.hpgen}
    uses = instrument_uses()
    check(len(uses) >= 30, "the tool's source names %d instrument attributes (found by reading %s)" % (len(uses), ", ".join(TOOL_FILES)))
    for (inst, attr), where in sorted(uses.items()):
        r, f = real[inst], fake[inst]
        what = "%s.%s (%s)" % (inst, attr, where)
        if callable(getattr(r, attr, None)):
            if not check(callable(getattr(f, attr, None)), "%s: the fake has the method" % what):
                continue
            same = parameters(getattr(r, attr)) == parameters(getattr(type(f), attr))
            check(same, "%s%s: the fake's arguments are the real driver's" % (what, inspect.signature(getattr(r, attr))),
                  "real %s, fake %s" % (parameters(getattr(r, attr)), parameters(getattr(type(f), attr))))
        else:                                         # a plain attribute (idn, outputs, vlimit): the real class sets it in __init__
            in_real = ("self.%s" % attr) in inspect.getsource(r.__init__)
            check(in_real and hasattr(f, attr), "%s: an attribute of the real %s and of the fake" % (what, r.__name__),
                  "the real %s has no method or attribute %r: the tool calls something that does not exist" % (r.__name__, attr))
    # the other way round: a fake must not offer a method the real driver lacks (the tool could come to lean on it)
    for inst, f in sorted(fake.items()):
        for attr in sorted(dir(type(f))):
            if attr.startswith("_") or attr.startswith("sim_") or not callable(getattr(type(f), attr)):
                continue
            r = getattr(real[inst], attr, None)
            if check(callable(r), "%s.%s: the fake's method exists in the real %s" % (inst, attr, real[inst].__name__)) and (inst, attr) not in uses:
                check(parameters(r) == parameters(getattr(type(f), attr)), "%s.%s: same arguments" % (inst, attr),
                      "real %s, fake %s" % (parameters(r), parameters(getattr(type(f), attr))))


# =================================================================================================================
# 2. the arithmetic, and the bench-only pieces as far as they go without a bench
# =================================================================================================================
def test_arithmetic():
    print("\n2. the arithmetic (analysis.py) and the bench-only pieces")
    import numpy as np
    rng = np.random.default_rng(7)
    n, rate = 2048, 25e6
    freq = 82 * rate / n                              # 1.001 MHz: 82 whole periods in the capture
    t = np.arange(n) / rate
    clean = 2048 + 1000 * np.sin(2 * np.pi * freq * t + 0.3) + rng.normal(0, 0.5, n)
    amplitude, offset, residuals = analysis.sine_fit(clean, rate, freq)
    check(abs(amplitude - 1000) < 0.5 and abs(offset - 2048) < 0.5 and abs(residuals).max() < 5, "sine_fit: amplitude 1000, offset 2048 from a noisy sine (%.2f, %.2f)" % (amplitude, offset))
    glitched = clean.copy()
    glitched[700] += 300
    check(abs(analysis.sine_fit(glitched, rate, freq)[2]).max() > 250, "sine_fit: one bad sample stands out in the residuals (the capture-phase test)")
    spur = clean + 1.0 * np.sin(2 * np.pi * 3 * freq * t)
    s = analysis.sfdr(spur, rate)
    check(abs(s["peak_hz"] - freq) <= s["bin_hz"] and abs(s["spur_hz"] - 3 * freq) <= s["bin_hz"] and abs(s["sfdr_db"] - 60) < 1.5,
          "sfdr: a 1 MHz tone with a third harmonic 60 dB down reads %.1f dBc at %.2f MHz" % (s["sfdr_db"], s["spur_hz"] / 1e6))
    import visit1
    tones = [visit1.test_tone(f) for f in visit1.SINE_FREQS]
    whole = all(abs(f * n_cap / fs - round(f * n_cap / fs)) < 1e-9 for f in tones for n_cap in (512, 8192) for fs in (25e6, 50e6))
    exact = all((f / 50e6 * 2 ** 32) % 2 ** 22 == 0 for f in tones)
    check(whole and exact, "the DAC-to-ADC test tones (%s Hz) fit every capture in whole periods and step the sine table exactly" % ", ".join("%.2f" % f for f in tones))
    slope, at_zero, worst = analysis.fit_line([-1024, 0, 1024], [1024.5, 2048.5, 3072.5])
    check(abs(slope - 1) < 1e-9 and abs(at_zero - 2048.5) < 1e-9 and worst < 1e-9, "fit_line: slope 1, offset +0.5")
    states = [(1.0, 1, True), (2.05, 1, False), (9.8, 10, True), (21.0, 10, False), (100.0, 100, True)]
    check(all(analysis.jumper_state(r) == {"gain": g, "term": tm} for r, g, tm in states) and analysis.jumper_state(5.0) is None,
          "jumper_state: x1, x1 unterminated, x10, x10 unterminated, x100; and 5 fits nothing")
    check(analysis.widest_run([False, True, True, False, True, True, True, False]) == (4, 6) and analysis.widest_run([False] * 4) is None, "widest_run")
    tt = np.linspace(-4e-3, 16e-3, 2000)
    ramp = 3.3 * np.clip((tt + 0.24e-3) / 0.8e-3, 0, 1)
    rise, low, high = analysis.rise_time(tt, ramp)
    check(abs(rise - 0.64e-3) < 0.03e-3 and abs(high - 3.3) < 0.01 and abs(low) < 0.01, "rise_time: a 0.8 ms ramp rises 10-90 %% in %.2f ms" % (1e3 * rise))

    # the Fluke walk
    rails = list(bench.RAILS.items())
    good = [4.71, 3.33, 1.10, 2.50, 3.30, 3.30, 4.70, 1.00, -4.15]
    taken, extras = analysis.assign_rails(good, rails)
    check(taken == list(range(9)) and not extras, "assign_rails: nine readings in order take the nine rails")
    taken, extras = analysis.assign_rails(good[:3] + good[4:], rails)
    check(taken[3] is None and taken[:3] == [0, 1, 2] and taken[4:] == [3, 4, 5, 6, 7] and not extras, "assign_rails: eight readings without the 2.5 V one leave +2V5 empty and shift nothing")
    taken, extras = analysis.assign_rails(good[:5] + good[6:], rails)
    missing = [i for i, j in enumerate(taken) if j is None]
    check(len(missing) == 1 and missing[0] in (4, 5) and analysis.could_also_be(missing[0], taken, good[:5] + good[6:], rails),
          "assign_rails: one of the two 3.3 V analog rails missing is reported as 'one of the two'")
    taken, extras = analysis.assign_rails(good[:3] + [1.10] + good[3:], rails)
    check(None not in taken and len(extras) == 1, "assign_rails: a pin touched twice is an extra reading, not a shift")
    low = list(good)
    low[4] = 3.05
    taken, extras = analysis.assign_rails(low, rails)
    check(taken == list(range(9)), "assign_rails: a rail out of its window is still that rail")
    finder = analysis.PlateauFinder()
    stream = [0.001, 0.002, 2.9, 4.71, 4.712, 4.711, 4.71, 1.5, 0.0, 0.003, 3.33, 3.331, 3.33, 3.33, 0.2, 0.0]
    for k, v in enumerate(stream):
        finder.add(0.2 * k, v)
    p = finder.plateaus()
    check(len(p) == 2 and abs(p[0]["volts"] - 4.7105) < 0.002 and abs(p[1]["volts"] - 3.33) < 0.002, "PlateauFinder: two touches in a stream of readings, the mid-touch readings left out")
    finder = analysis.PlateauFinder()
    for k, v in enumerate([0.0, 3.30, 3.30, 3.30, 2.1, 3.30, 3.30, 3.30, 0.0, 0.0, 3.30, 3.301, 3.30, 0.0]):
        finder.add(0.2 * k, v)
    slipped = [x["volts"] for x in finder.plateaus()]
    taken, extras = analysis.assign_rails([4.71, 3.33, 1.10, 2.50] + slipped + [4.70, 1.00, -4.15], rails)
    check(len(slipped) == 3 and None not in taken and len(extras) == 1,
          "PlateauFinder: a slip on a 3.3 V pin makes one plateau more, which assign_rails sets aside as an extra reading")

    # the bench-only pieces
    canned = "Jtag frequency : requested 6.00MHz -> real 6.00MHz\nindex 0:\n\tidcode 0x41111043\n\tmanufacturer lattice\n\tfamily ECP5\n\tmodel  LFE5U-25\n\tirlength 8\n"
    check(visit1.parse_idcode(canned) == visit1.IDCODE_LFE5U_25F and visit1.parse_idcode("unable to open ftdi device: -4") is None, "parse_idcode: openFPGALoader --detect's output, and its failure")
    os.makedirs(OUT, exist_ok=True)
    stand_in = os.path.join(OUT, "stand_in_loader.sh")       # a stand-in for openFPGALoader: it prints the canned answer
    with open(stand_in, "w") as f:
        f.write("#!/bin/sh\nprintf 'index 0:\\n\\tidcode 0x41111043\\n'\n")
    os.chmod(stand_in, 0o755)
    status, text = visit1.run_loader(["--detect", "-c", "ft2232"], timeout=10, loader=stand_in)
    check(status == 0 and visit1.parse_idcode(text) == 0x41111043, "run_loader: runs a program and returns its output (a stand-in script, not openFPGALoader)")
    status, text = visit1.run_loader(["--detect"], timeout=10, loader=os.path.join(OUT, "no_such_program"))
    check(status is None and "not at" in text and "OSS_CAD_SUITE" in visit1.loader_hint(text), "run_loader: a missing openFPGALoader is a sentence, not an exception")

    # the generators' limits, through Bench.tone() on the fakes (no simulated board is started for this)
    b = bench.Bench("T_LIMITS", sim=True, sim_preset="instruments")
    try:
        for source, vpp, why in (("sdg1", 3.0, "SDG CH1 beyond +-2.5 V open circuit"), ("hp", 3.0, "the 33220A beyond +-1.25 V into 50 ohm"), ("sdg2", 4.0, "SDG CH2 beyond +-3.5 V open circuit")):
            try:
                b.tone(source, 100e3, vpp)
                refused = False
            except ValueError:
                refused = True
            check(refused and b.sim.generator_signal(source) is None, "Bench.tone refuses %s, and the output stays off" % why)
        b.tone("sdg1", 100e3, 2.4)
        check(b.sim.generator_signal("sdg1")["open_vpp"] == 4.8, "Bench.tone: 2.4 Vpp into 50 ohm on SDG CH1 is allowed (the over-range test) and is 4.8 Vpp open circuit")
        try:
            b.tone("hp", 30e6, 0.5)
            refused = False
        except ValueError:
            refused = True
        check(refused, "the 33220A fake refuses 30 MHz as the real driver does (it is a 20 MHz generator)")
        check(b.generators_off() == [] and b.sim.generator_signal("sdg1") is None, "Bench.generators_off switches every output off")
    finally:
        b.close()
    with open(os.path.join(OUT, "shot.png"), "wb") as f:
        f.write(simbench.tiny_png())
    with open(os.path.join(OUT, "shot.png"), "rb") as f:
        png = f.read()
    check(png[:8] == b"\x89PNG\r\n\x1a\n" and png[-8:] == b"IEND\xaeB`\x82", "the fake scope's screenshot is a valid PNG (%d bytes)" % len(png))


# =================================================================================================================
# the commands, each as its own process
# =================================================================================================================
def command(name, args, env=None):
    """Start `python3 bench.py <args>` with its output in OUT/<name>.log.  Returns the process and its start time."""
    log = open(os.path.join(OUT, name + ".log"), "w")
    environment = dict(os.environ)
    environment.pop("BENCH_CLAIMS_FILE", None)
    environment.update(env or {})
    p = subprocess.Popen([sys.executable, "-u", os.path.join(HERE, "bench.py")] + args, stdout=log, stderr=subprocess.STDOUT, cwd=HERE, env=environment)
    p.log_file = log
    return p, time.time()


def judge(name, status, seconds, want_status, must, must_not=()):
    """Check one finished command's exit status and output."""
    with open(os.path.join(OUT, name + ".log")) as f:
        text = f.read()
    problems = []
    if status != want_status:
        problems.append("exit status %s, expected %s" % (status, want_status))
    if "Traceback" in text:
        problems.append("a traceback in its output")
    problems += ["missing: %r" % s for s in must if s not in text]
    problems += ["should not say: %r" % s for s in must_not if s in text]
    summary = [line for line in text.splitlines() if line.startswith("SUMMARY")]
    check(not problems, "%-28s %5.0f s   %s" % (name, seconds, summary[-1][9:] if summary else text.strip().splitlines()[-1][:90] if text.strip() else "(no output)"),
          "; ".join(problems) + "   (see data/sim/test_bench/%s.log)" % name)


def run_in_turn(specs, env=None):
    for name, args, want_status, must, must_not in specs:
        p, t0 = command(name, args, env)
        status = p.wait(timeout=600)
        p.log_file.close()
        judge(name, status, time.time() - t0, want_status, must, must_not)


def run_side_by_side(specs, jobs):
    """Run the commands `jobs` at a time (each is one co-simulation on one core) and judge each as it ends."""
    waiting = list(specs)
    running = []
    while waiting or running:
        while waiting and len(running) < jobs:
            spec = waiting.pop(0)
            p, t0 = command(spec[0], spec[1])
            running.append((p, t0, spec))
        time.sleep(1.0)
        for item in list(running):
            p, t0, (name, args, want_status, must, must_not) = item
            status = p.poll()
            if status is None and time.time() - t0 > 3600:        # an hour: something hangs
                p.kill()
                status = p.wait()
            if status is not None:
                running.remove(item)
                p.log_file.close()
                judge(name, status, time.time() - t0, want_status, must, must_not)


SIM = ["--sim"]


def test_claims():
    print("\n3. the bench claims, on a scratch record")
    if bench.bench_claims is None:
        check(False, "bench_claims.py can be imported from %s" % bench.LIC)
        return
    record = os.path.join(OUT, "claims.json")
    for path in (record, record + ".lock", record + ".tmp"):
        if os.path.exists(path):
            os.remove(path)
    env = {"BENCH_CLAIMS_FILE": record}
    board = ["--board", "T_CLAIMS"]
    run_in_turn([
        ("claims_v1a_without", SIM + board + ["v1a"], 1, ["STOPPED before switching the supply on", "does not hold the bench claim"], ["staircase"]),
        ("claims_claim_v1", SIM + board + ["claim", "v1"], 0, ["claimed for ECP5-2ADC-2DAC: E3646A:1, Fluke45"], []),
        ("claims_v1a_with", SIM + board + ["v1a"], 0, ["5.0 V is ON"], ["STOPPED"]),
        ("claims_v2_without", SIM + board + ["v2", "--only", "adc_abs"], 1, ["STOPPED before switching the generators and the scope on"], ["verify"]),
    ], env)
    os.environ["BENCH_CLAIMS_FILE"] = record              # another project takes a generator channel, in the scratch record
    try:
        bench.bench_claims.claim(["SDG1032X:1"], by="another-project", to="its own board", limit="+-10 V")
    finally:
        del os.environ["BENCH_CLAIMS_FILE"]
    run_in_turn([
        ("claims_claim_v2_taken", SIM + board + ["claim", "v2"], 1, ["NOT CLAIMED", "another-project"], ["claimed for"]),
        ("claims_release", SIM + board + ["release"], 0, ["released: E3646A:1, Fluke45"], []),
        ("claims_coldboot_without", SIM + board + ["coldboot", "--n", "2"], 1, ["STOPPED before switching the supply on"], ["cycle 1"]),
    ], env)


def test_quick_commands():
    print("\n4a. the commands that need no simulated board (seconds each)")
    board = ["--board", "T"]
    run_in_turn([
        ("where", SIM + ["where"], 0, ["where we are"], []),
        ("v1a", SIM + board + ["v1a"], 0, ["8 pass, 0 FAIL", "5.0 V is ON at J601"], []),
        ("v1a_short", SIM + ["--board", "T_F1", "--sim-fault", "short", "v1a"], 0,
         ["FAIL", "current limit: a short or a reversed part", "5.0 V was NOT switched on", "output is OFF"], ["5.0 V is ON"]),
        ("v1a_overcurrent", SIM + ["--board", "T_F1", "--sim-fault", "overcurrent", "v1a"], 0, ["FAIL", "under 0.7 A", "5.0 V was NOT switched on"], ["5.0 V is ON"]),
        ("rails", SIM + board + ["rails"], 0, ["9 pass, 0 FAIL", "9 of 9 rails in their windows"], []),
        ("rails_low", SIM + ["--board", "T_F1", "--sim-fault", "rail_low", "rails"], 0, ["8 pass, 1 FAIL", "+3V3_ADC (pin 9)", "3.050 V", "outside its window"], []),
        ("rails_skipped", SIM + ["--board", "T_F1", "--sim-fault", "rail_skipped", "rails"], 0,
         ["8 pass, 1 FAIL", "+2V5 (pin 7)", "no steady reading", "probably missing: +2V5", "D604"], []),
        ("rails_twice", SIM + ["--board", "T_F1", "--sim-fault", "rail_twice", "rails"], 0, ["9 pass, 0 FAIL, 1 info", "an extra steady reading", "9 of 9 rails"], []),
        ("psu_staircase_old", SIM + board + ["psu", "staircase"], 0, ["staircase", '"mode": "CV"'], ["FAIL"]),
        ("dmm_old", SIM + board + ["dmm", "+3V3"], 0, ['"rail": "+3V3"'], []),
        ("check_old", SIM + board + ["check"], 0, ["psu    Agilent Technologies,E3646A", "gen    Siglent Technologies,SDG1032X"], ["AttributeError"]),
        ("step_list", SIM + ["step", "--list"], 0, ["gain_x10", "poweron", "noise_10k"], []),
        ("v1b_list", SIM + ["v1b", "--list"], 0, ["dc_transfer", "usb_power", "eth_wire"], []),
        ("unknown_test", SIM + board + ["v1b", "--only", "nosuch"], 1, ["No test named nosuch"], []),
        ("unknown_fault", SIM + board + ["--sim-fault", "nosuch", "v1a"], 2, ["one of"], []),
        ("step_noise_alias", SIM + board + ["step", "noise"], 1, ["two commands", "noise_0", "noise_10k"], []),
        ("step_poweron", SIM + board + ["step", "poweron", "--n", "3"], 0, ["+3V3 rise, 10-90 %, 3 cycles", "the scope put back as found", "0 FAIL"], []),
    ])


def long_commands():
    """The commands that run the co-simulated board: (name, arguments, exit status, must say, must not say)."""
    board, fault = ["--board", "T"], lambda n, names: ["--board", "T_F%d" % n, "--sim-fault", names]
    return [
        # visit 1B, whole, as the plan cables it
        ("v1b", SIM + board + ["v1b"], 0,
         ["ADC A IN", "DAC 1 OUT, gain x1, TERM in", "skipped in simulation", "0 FAIL", "report: "], []),
        # ... the two DAC cables crossed: found, accepted, used
        ("v1b_crossed", SIM + fault(2, "crossed") + ["v1b", "--only", "dc_transfer,xtalk"], 0,
         ["the two DAC cables are crossed: accepted", "DAC 2 -> ADC A: slope", "DAC 1 -> ADC B: slope", "0 FAIL"], []),
        # ... no cable on ADC A IN, no card, no CLK cable: said in words, their tests skipped, the rest run
        ("v1b_missing", SIM + fault(3, "no_sma_a,no_card,no_clk_cable") + ["v1b", "--only", "sd,clkloop,dc_transfer,fullscale"], 0,
         ["no DAC reaches ADC A IN: is the SMA cable from DAC 1 OUT on", "push a microSD card into the socket", "is the SMA cable from CLK OUT to CLK IN on",
          "no microSD card (verify)", "no cable from CLK OUT to CLK IN (verify)", "DAC 2 -> ADC B: slope", "3 FAIL"], []),
        # ... a GAIN shunt left out on A, the TERM shunt out on B: neither channel is tested at the wrong level
        ("v1b_jumpers", SIM + fault(4, "gain_a_x10,term_b_open,no_usb,no_link") + ["v1b", "--only", "dc_transfer,usb,eth_wire"], 0,
         ["gain x10, TERM in", "one GAIN shunt is out (JP103 or JP104)", "gain x1, TERM OUT", "the TERM shunt JP201 is out",
          "no DAC reaches an ADC at gain x1", "USB USER is not on a host (verify)", "no Ethernet link"], []),
        # ... the optional monitor and Pmod loop, and the soak
        ("v1b_optional", SIM + fault(5, "monitor,pmod_loop") + ["v1b", "--only", "hdmi,pmod,soak", "--soak-minutes", "0.05", "--soak-every", "1"], 0,
         ["a monitor (hot-plug high)", "all eight pins looped", "maker HMC", "frames a second", "Pmod A drives, Pmod B reads", "supply current over", "0 FAIL"], []),
        # visit 2, whole
        ("v2", SIM + board + ["v2"], 0,
         ["SDG CH1, SDG CH2 and the 33220A are off", "the scope put back as found", "probe x10", "0 FAIL", "report: "], []),
        # ... harmless swaps: accepted and used
        ("v2_swapped", SIM + fault(6, "gens_swapped,scope_swapped") + ["v2", "--only", "adc_abs,dac_dc_scope"], 0,
         ["the two generators are on each other's ADC channel: accepted", "the two scope cables are swapped: accepted", "the 33220A -> ADC A: 1.000 Vpp reads", "0 FAIL"], []),
        # ... a swap that is not harmless: one sentence, nothing tested, the bench put back
        ("v2_sdg_swapped", SIM + fault(7, "sdg_swapped") + ["v2"], 1,
         ["STOPPED after verify", "-> swap the two BNC cables at the generator", "the scope put back as found", "are off"], ["adc_abs", "see the last line"]),
        # ... a missing generator cable, a 10x probe, nothing on CH3
        ("v2_missing", SIM + fault(8, "no_gen_b,scope_10x,no_scope_clk") + ["v2", "--only", "adc_abs,dac_dc_scope,clkout_scope"], 0,
         ["reaches neither ADC input nor CLK IN", "a 10x probe is on this channel", "scope CH3 does not follow CLK OUT", "no generator reaches ADC B IN (verify)",
          "scope CH3 does not see CLK OUT (verify)", "SDG1032X CH1 -> ADC A: 1.000 Vpp reads"], []),
        # visit 3: every step with the bench as the step expects ...
        ("step_leds", SIM + board + ["step", "leds"], 0, ["needs eyes"], []),
        ("step_buttons", SIM + board + ["step", "buttons", "--seconds", "3"], 0, ["2 pass, 0 FAIL"], []),
        ("step_prog", SIM + board + ["step", "prog"], 0, ["skipped in simulation"], []),
        ("step_gain_x10", SIM + board + ["step", "gain_x10"], 0, ["gain x10.0", "2 pass, 0 FAIL"], []),
        ("step_gain_x100", SIM + board + ["step", "gain_x100"], 0, ["gain x100", "2 pass, 0 FAIL", "put all four GAIN shunts back"], []),
        ("step_term_open", SIM + board + ["step", "term_open"], 0, ["2.00 times the terminated amplitude", "1 pass, 0 FAIL"], []),
        ("step_noise_0", SIM + board + ["step", "noise_0"], 0, ["SW101 at 0 ohm"], []),
        ("step_light", SIM + board + ["step", "light"], 0, ["it rises with the light", "1 pass, 0 FAIL"], []),
        ("step_tap", SIM + board + ["step", "tap"], 0, ["TAP A on scope CH4", "2 pass, 0 FAIL"], []),
        ("step_tap_b", SIM + board + ["step", "tap_b"], 0, ["TAP B on scope CH4", "2 pass, 0 FAIL"], []),
        ("step_tap_tia", SIM + board + ["step", "tap_tia"], 0, ["the receiver follows the LED", "2 pass, 0 FAIL"], []),
        ("step_tap_n4v2", SIM + board + ["step", "tap_n4v2"], 0, ["mVpp", "1 pass, 0 FAIL"], []),
        ("step_dac_clock", SIM + board + ["step", "dac_clock"], 0, ["% over", "2 pass, 0 FAIL"], []),
        ("step_hdmi", SIM + board + ["step", "hdmi"], 0, ["seen (the hot-plug pin is high)", "maker HMC", "0 FAIL"], []),
        ("step_pmod", SIM + board + ["step", "pmod"], 0, ["2 pass, 0 FAIL"], []),
        # ... and with the bench as it was found: "you did not move it"
        ("asfound_buttons", SIM + board + ["step", "buttons", "--seconds", "2", "--sim-as-found"], 0, ["not seen in 2 s", "0 pass, 2 FAIL"], []),
        ("asfound_gain_x10", SIM + board + ["step", "gain_x10", "--sim-as-found"], 0, ["is at gain x1: the shunt of JP103 was not pulled", "the shunt of JP203 was not pulled", "0 pass, 2 FAIL"], []),
        # 10 mVpp at gain x1 is only 20 codes: the step must still say "the shunt was not pulled", not "no cable"
        ("asfound_gain_x100", SIM + board + ["step", "gain_x100", "--sim-as-found"], 0,
         ["channel A is at gain x1: the shunt of JP103 was not pulled", "channel B is at gain x1: the shunt of JP203 was not pulled", "0 pass, 2 FAIL"],
         ["reaches no ADC input"]),
        ("asfound_term_open", SIM + board + ["step", "term_open", "--sim-as-found"], 0, ["JP101's shunt was not pulled", "1 FAIL"], []),
        ("asfound_light", SIM + board + ["step", "light", "--sim-as-found"], 0, ["it does not follow", "is JP2009 on LED", "1 FAIL"], []),
        ("asfound_tap", SIM + board + ["step", "tap", "--sim-as-found"], 0, ["is the pigtail on the U.FL of TAP A", "1 FAIL"], []),
        ("asfound_poweron", SIM + board + ["step", "poweron", "--n", "2", "--sim-as-found"], 0, ["FAIL", "the scope put back as found"], []),
        ("asfound_dac_clock", SIM + board + ["step", "dac_clock", "--sim-as-found"], 0, ["not a 3.3 V, 50 MHz clock", "1 FAIL"], []),
        ("asfound_hdmi", SIM + board + ["step", "hdmi", "--sim-as-found"], 0, ["none seen (the hot-plug pin is low)", "1 FAIL"], []),
        ("asfound_pmod", SIM + board + ["step", "pmod", "--sim-as-found"], 0, ["no loop found", "1 FAIL"], []),
        # The older procedures still run.  stage6.adc_noise assumes nothing on the ADC inputs; here visit 1B's cables are on
        # them and the DACs power up as full-scale sines, so its verdict is rightly FAIL (over 1000 codes rms).  What is
        # checked is that it runs to its end; `v1b --only noise` is the test that parks the DACs first.
        ("run_stage6_noise_old", SIM + board + ["run", "stage6.adc_noise"], 0, ['"channel": "A"', '"channel": "B"', "adc_noise.npz"], []),
    ]


def test_long_commands(jobs):
    print("\n4b. the commands that run the co-simulated board, %d side by side (v1b is the longest: about 20 minutes)" % jobs)
    import cosim
    cosim.build()                                     # compile the simulation once, before several processes want it at the same moment
    run_side_by_side(long_commands(), jobs)
    print("\n4c. the commands that read what the others logged")
    board = ["--board", "T"]
    run_in_turn([
        # the 10 kohm step compares with the 0 ohm step's log entry
        ("step_noise_10k", SIM + board + ["step", "noise_10k"], 0, ["times the noise", "1 pass, 0 FAIL"], []),
        # the cold boot compares with the currents v1a and v1b logged
        ("coldboot", SIM + board + ["coldboot"], 0, ["the 10 cycles agree", "it configured itself from its flash", "against bringup.bit with USB plugged", "2 pass, 0 FAIL"], []),
        # the report before the next fault run, which logs to this same board (it needs the currents logged above)
        ("report", SIM + board + ["report"], 0,
         ["| visit | test | what |", "| v1b | dc_transfer |", "| v2 | adc_abs |", "| rails | rails |", "| coldboot | coldboot | the 10 cycles agree |"], []),
        ("coldboot_no_boot", SIM + board + ["--sim-fault", "no_flash_boot", "coldboot", "--n", "3"], 0, ["it did not boot from its flash", "1 FAIL"], []),
    ])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="parts 1 to 3 and the commands that need no simulated board")
    ap.add_argument("--jobs", type=int, default=8, help="how many co-simulations run side by side")
    a = ap.parse_args()
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    sim_dir = os.path.join(HERE, "data", "sim")
    if not a.quick:                                   # a full run starts from empty logs: its last commands read what its first ones logged.
        for name in os.listdir(sim_dir):              # (--quick leaves them: it would wipe a full run's logs and reports and rebuild only a few)
            if name.startswith("board_T"):
                shutil.rmtree(os.path.join(sim_dir, name))
    test_fakes()
    test_arithmetic()
    test_claims()
    test_quick_commands()
    if not a.quick:
        test_long_commands(a.jobs)
    failed = results.count(False)
    print("\n%d checks, %d failed, %.0f s%s" % (len(results), failed, time.time() - t0, " (--quick: the co-simulated commands were not run)" if a.quick else ""))
    print("PASS" if failed == 0 else "FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
