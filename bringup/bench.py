#!/usr/bin/env python3
"""bench.py: the ECP5-2ADC-2DAC rev A bring-up from the bench PC.  The lab instruments (~/lab-instrument-control:
the E3646A supply, the Fluke 45, the SDS2104X Plus scope, the SDG1032X and 33220A generators) and the board
(gateware/bringup/host/ecp5bu.py over the FT2232H's serial channel) in one place, every reading appended to
bringup/data/board_<X>/<date>.jsonl with the time, the stage, the settings and the verdict.

The visits of ../BRINGUP.md, one command each (the person cables, types the words in the chat, the session runs
the command and reads its output; nothing here asks a question):

    python3 bringup/bench.py where                       # STATUS.md: where the bring-up stands
    python3 bringup/bench.py claim v1                    # record that the supply and the Fluke are cabled to this board
    python3 bringup/bench.py v1a                         # visit 1A: the staircase, then 5.0 V left on
    python3 bringup/bench.py rails [--seconds 180]       # visit 1A: the Fluke walk along the RAILS header
    python3 bringup/bench.py v1b [--only NAME,NAME] [--skip NAME] [--list] [--soak-minutes N]
                                                         # visit 1B: what is plugged in, then every self-test (an hour)
    python3 bringup/bench.py coldboot [--n 10]           # visit 2 step 1: power cycles with both USB cables out
    python3 bringup/bench.py claim v2                    # ... and the generators and the scope
    python3 bringup/bench.py v2 [--only ...] [--list]    # visit 2: the generators and the scope
    python3 bringup/bench.py step NAME                   # visit 3: one step (step --list names them)
    python3 bringup/bench.py report                      # the latest verdict of every test of this board, as markdown
    python3 bringup/bench.py release                     # give the instruments back

    --board A|B   which board (or $ECP5_BOARD, or bench_config.json's "board"); anywhere on the line
    --sim         no hardware at all: the board is the RTL in iverilog (gateware/bringup/host/cosim.py) and the
                  instruments are simbench.py's fakes.  Its log goes to data/sim/, never into a board's own.
    --sim-fault NAME[,NAME]   with --sim: something cabled wrong (simbench.FAULTS lists them)

The older single commands still work:

    python3 bringup/bench.py check                       # who answers: *IDN? of each instrument, the board's ID
    python3 bringup/bench.py note "boards unwrapped" --stage 0.1
    python3 bringup/bench.py psu staircase               # stage 1.2: 1, 2.5, 4, 5 V at 0.3 A, the current at each, then off
    python3 bringup/bench.py psu on [--volts 5.0 --amps 1.0]    # stage 1.3 on: 5.00 V, 1.0 A limit, OVP 5.6 V
    python3 bringup/bench.py psu read [--n 5] | log --seconds 600 | off
    python3 bringup/bench.py dmm +3V3                    # one rail on the Fluke 45 (or type the reading when asked)
    python3 bringup/bench.py scope shot NAME             # a screenshot into data/
    python3 bringup/bench.py scope meas 1 PKPK FREQ MEAN # the scope's own measurements of channel 1
    python3 bringup/bench.py gen sine 1e6 1.0 [--ch 1] [--load 50]   # the SDG; gen off
    python3 bringup/bench.py board ident | clocks | capture 4096 | dac 1 sine 1e6 | sdram | phy | si 0 10e6
    python3 bringup/bench.py run stage4.clocks           # a procedure of this file (list: run --list)
    python3 bringup/bench.py show [--n 20]

The addresses are bench_config.json's (written with defaults the first time; edit it, or run `check`).
Nothing here changes an instrument except the command that says so; `check` sends *IDN? and nothing else.
A supply or generator output is switched on only when this project holds the bench claim on it
(~/lab-instrument-control/bench_claims.py; `claim v1`, `claim v2`).

The files: bench.py (this: the Bench, the old commands, the command line), visit1.py (v1a, rails, v1b,
coldboot), visit2.py (v2), visit3.py (the steps), analysis.py (the arithmetic), report.py (rows and tables),
simbench.py (the simulated bench), test_bench.py (everything above run against the simulation).
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
LIC = os.path.expanduser(os.environ.get("LAB_INSTRUMENT_CONTROL", "~/lab-instrument-control"))
for sub in ("", "hp", "fluke", "siglent"):
    sys.path.insert(0, os.path.join(LIC, sub))
sys.path.insert(0, os.path.join(PROJECT, "gateware", "bringup", "host"))
sys.path.insert(0, HERE)

try:
    import bench_claims                  # ~/lab-instrument-control/bench_claims.py: who holds which instrument channel
except ImportError:
    bench_claims = None                  # an older checkout of the instrument library: the tool runs, no claim is checked

CONFIG = os.path.join(HERE, "bench_config.json")
DEFAULTS = {
    "board": "A",
    # the 5 V: E3646A output 1 (0-8 V, 3 A, OVP only; one switch for both outputs) on RS-232:
    # find the port with `python3 ~/lab-instrument-control/scpi_link.py identify`
    "psu": {"serial": None, "gpib": None, "out": 1},
    "dmm": {"serial": None},                                    # the Fluke 45 on RS-232; None = type the readings
    "scope": {"host": "192.168.8.203"},                         # Siglent SDS2104X Plus
    "gen": {"host": "192.168.8.246"},                           # Siglent SDG1032X
    "hpgen": {"host": "192.168.8.240", "usb": False},           # Agilent 33220A: on the LAN, or "usb": true (it was on USB on 2026-11-14)
    "board_port": "auto",                                       # the FT2232H's channel B, by its name under /dev/serial/by-id
    "pc_broadcast": "192.168.8.255",                            # where the PC broadcasts to reach the board (v1b eth_wire): the lab switch's subnet
}

SUPPLY_V = 5.00          # the board's bench input J601: 4.75-5.25 V (the LM27761's absolute maximum is 5.8 V)
SUPPLY_A = 1.0           # the board draws about 0.6-0.7 A at 5 V with the FPGA configured and both converters running
OVP_V = 5.6              # the E36xxA's OVP is a crowbar: below the LM27761's 5.8 V
STAIRCASE = [(1.0, 0.3), (2.5, 0.3), (4.0, 0.5), (5.0, 1.0)]    # stage 1.2: (volts, current limit), 2 s each
# stage 1.3's rails on the RAILS header J602 (odd pins, top to bottom as printed; even pins ground) and their limits
RAILS = {
    "+5V":      (4.60, 5.25),    # the bench input less the SS34 Schottky's 0.3-0.5 V (USB PROG's path has no diode: 4.75-5.25)
    "+3V3":     (3.23, 3.43),    # TLV62569 buck: 0.6 V x (1 + 15k/3.3k) = 3.33 V
    "+1V1":     (1.07, 1.13),    # TLV62569 buck: 0.6 V x (1 + 10k/12k) = 1.10 V
    "+2V5":     (2.45, 2.55),    # LP5907-2.5 LDO (VCCAUX)
    "+3V3_ADC": (3.25, 3.35),    # TPS7A2033 LDO, behind 2.2 ohm from +5V
    "+3V3_DAC": (3.25, 3.35),    # TPS7A2033 LDO
    "+5VA":     (4.50, 5.25),    # +5V through a ferrite bead
    "+1V0_PHY": (0.95, 1.05),    # the RTL8211F's internal switcher (0 V until the PHY runs; it needs no FPGA)
    "-4V2":     (-4.35, -3.95),  # LM27761 charge pump at -4.15 V (the op amps get it through a bead)
}
RAIL_LEDS = {"+5V": "D602", "+3V3": "D603", "+2V5": "D604", "+3V3_ADC": "D605", "+3V3_DAC": "D606", "+5VA": "D607", "-4V2": "D608", "+1V1": "D609 (via Q601)"}

CLAIM_BY = "ECP5-2ADC-2DAC"      # this project's name in the bench's claim record
# The generators' limits for this board, as open-circuit volts.  SDG CH1 feeds an ADC input (+-1 V is full scale; the
# over-range test needs 2.4 Vpp into its 50 ohm = +-2.4 V open circuit); SDG CH2 feeds CLK IN (3.3 V squares, 3 Vpp
# sines into 50 ohm = +-3.0 V open circuit).  The SDG1032X driver refuses anything beyond (its vlimit argument).
SDG_VLIMIT = {1: 2.5, 2: 3.5}
HP_PEAK_INTO_50 = 1.25           # the 33220A has no limit of its own: this tool refuses more than +-1.25 V across the ADC input's 50 ohm
SDG_MAX_HZ = 30e6                # the SDG1032X's highest sine
HP_MAX_HZ = 20e6                 # the 33220A's
STATS_LOG2 = 12                  # the ADC statistics window used here: 2^12 = 4096 samples (164 us at 25 MS/s), mean noise 1/64 code

# How big each measurement is on the bench, and in simulation (where 1 ms of board time costs 4 s): (bench, --sim)
SIZES = {
    "capture":     (8192, 512),          # samples per capture: the whole capture memory; a simulated dump of 512 takes 13 s
    "capture_fit": (2048, 128),          # samples for one sine fit of the capture-phase scan (18 captures)
    "scratch":     (50, 50),             # random words through the scratch register
    "sdram_scan":  (4096, 256),          # words per read latency (BRINGUP.md 7.1)
    "sdram_full":  (1 << 24, 256),       # the whole array: 16 M words (32 MB); not simulated
    "sdram_pol":   (65536, 256),         # words per SDRAM clock polarity
    "sdram_soak":  (4096, 256),          # words per soak sample
    "eth_min":     (1000, 20),           # minimum-size frames through the PHY's loopback
    "eth_max":     (1000, 5),            # maximum-size frames
}


class Refused(Exception):
    """The command must not, or cannot, go on, for a reason the person at the bench can act on: a claim is
    missing, an instrument is not configured, a cable is on the wrong connector.  Its text is plain language;
    main() prints it and the command ends with status 1.  Inside a visit's test it becomes that test's FAIL row."""


def now_iso():
    return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


def load_config():
    if not os.path.exists(CONFIG):
        with open(CONFIG, "w") as f:
            json.dump(DEFAULTS, f, indent=1); f.write("\n")
    with open(CONFIG) as f:
        cfg = json.load(f)
    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)
    return cfg


class Log:
    """append-only JSON lines, one file a board a day; every entry has t, board, stage, kind.
    A simulated run (--sim) logs under data/sim/ so that nothing simulated is ever read as a board's result."""
    def __init__(self, board, sim=False):
        self.board = board
        self.dir = os.path.join(HERE, "data", "sim" if sim else "", "board_%s" % board)
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, dt.date.today().isoformat() + ".jsonl")

    def add(self, kind, stage=None, quiet=False, **fields):
        """Append one entry; print it too unless quiet (the visits print their own tables)."""
        e = {"t": now_iso(), "board": self.board, "stage": stage, "kind": kind}
        e.update(fields)
        with open(self.path, "a") as f:
            f.write(json.dumps(e, default=repr) + "\n")
        if not quiet:
            print(_fmt(e))
        return e

    def tail(self, n=20):
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [json.loads(x) for x in f.readlines()[-n:]]

    def entries(self):
        """Every entry of this board, all days, oldest first."""
        out = []
        for name in sorted(os.listdir(self.dir)):
            if name.endswith(".jsonl"):
                with open(os.path.join(self.dir, name)) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                out.append(json.loads(line))
                            except ValueError:
                                pass                 # a line cut short by a crash: skip it
        return out

    def latest(self, kind, **match):
        """The newest entry of `kind` whose fields equal `match`, or None."""
        for e in reversed(self.entries()):
            if e.get("kind") == kind and all(e.get(k) == v for k, v in match.items()):
                return e
        return None


def _fmt(e):
    rest = {k: v for k, v in e.items() if k not in ("t", "board", "stage", "kind")}
    return "%s %s %-5s %-10s %s" % (e["t"][11:19], e["board"], e.get("stage") or "", e["kind"], json.dumps(rest, default=repr)[:300])


def verdict(value, lo, hi):
    return "pass" if lo <= value <= hi else "FAIL"


def reachable(host, port=111, timeout=2.0):
    import socket
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


class Bench:
    def __init__(self, board=None, stage=None, sim=False, sim_preset="selftest", sim_faults=()):
        self.cfg = load_config()
        self.board = board or os.environ.get("ECP5_BOARD") or self.cfg["board"]
        self.stage = stage
        self.sim = None
        if sim:
            import simbench
            self.sim = simbench.SimBench(sim_preset, sim_faults, psu_out=self.cfg["psu"]["out"])
        self.log = Log(self.board, sim=bool(sim))
        self._cache = {}
        self.adc_phase = 2               # the ADC capture phase at 25 MS/s (ecp5bu's default; v1b's `phase` test may move it)
        self.adc_negedge = False         # ... and the edge
        self.adc_negedge_50 = False      # the edge at 50 MS/s (the phase does nothing there)
        timing = self.log.latest("adc_timing")       # what v1b's `phase` test last found for this board
        if timing:
            self.adc_phase, self.adc_negedge, self.adc_negedge_50 = timing["phase"], timing["negedge"], timing["negedge_50"]
        self.found = None                # what the visit's `verify` found plugged in
        self.soak_minutes = 0.0          # v1b's soak: how long, and how often it samples (set from the command line)
        self.soak_every = 30.0
        self._no_claims_said = False

    def _get(self, name, factory):
        if name not in self._cache:
            self._cache[name] = factory()
        return self._cache[name]

    # ---- the instruments and the board: the real ones, or simbench's under --sim ------------------------
    @property
    def psu(self):
        if self.sim:
            return self.sim.psu
        def make():
            from agilent_E36xxA import AgilentE36xxA
            c = self.cfg["psu"]
            if c.get("serial"):
                return AgilentE36xxA(serial=c["serial"])
            if c.get("gpib"):
                return AgilentE36xxA(address=c["gpib"])
            raise Refused("bench_config.json: psu.serial (the /dev/serial/by-id path; `python3 %s/scpi_link.py identify`)" % LIC)
        return self._get("psu", make)

    @property
    def dmm(self):
        if self.sim:
            return self.sim.dmm
        def make():
            if not self.cfg["dmm"].get("serial"):
                return None
            from fluke_45 import Fluke45
            return Fluke45(serial=self.cfg["dmm"]["serial"])
        return self._get("dmm", make)

    @property
    def scope(self):
        if self.sim:
            return self.sim.scope
        def make():
            from siglent_SDS2104X import SDS2104X
            h = self.cfg["scope"]["host"]
            if not reachable(h):
                raise Refused("scope %s not reachable" % h)
            return SDS2104X(h)
        return self._get("scope", make)

    @property
    def gen(self):
        """The SDG1032X, opened with this board's voltage limits (SDG_VLIMIT)."""
        if self.sim:
            self.sim.gen.vlimit = dict(SDG_VLIMIT)
            return self.sim.gen
        def make():
            from siglent_SDG1032X import SDG1032X
            h = self.cfg["gen"]["host"]
            if not reachable(h):
                raise Refused("generator %s not reachable" % h)
            return SDG1032X(h, vlimit=dict(SDG_VLIMIT))
        return self._get("gen", make)

    @property
    def hpgen(self):
        if self.sim:
            return self.sim.hpgen
        def make():
            from agilent_33220A import Agilent33220A, USB_VENDOR, USB_PRODUCT
            c = self.cfg["hpgen"]
            if c.get("usb"):
                from scpi_link import usbtmc_node
                return Agilent33220A(usb=usbtmc_node(USB_VENDOR, USB_PRODUCT))
            if not reachable(c["host"]):
                raise Refused("33220A %s not reachable on the LAN (if it is on USB: \"usb\": true under hpgen in bench_config.json)" % c["host"])
            return Agilent33220A(c["host"])
        return self._get("hpgen", make)

    @property
    def bd(self):
        if self.sim:
            return self.sim.board
        def make():
            from ecp5bu import Board
            return Board(self.cfg["board_port"])
        return self._get("bd", make)

    def close(self):
        if self.sim:
            self.sim.close()
        for k, v in self._cache.items():
            try:
                v.close()
            except Exception:
                pass

    def note(self, text, **kw):
        return self.log.add("note", self.stage, text=text, **kw)

    def record(self, kind, quiet=False, **kw):
        return self.log.add(kind, self.stage, quiet=quiet, **kw)

    # ---- time: the PC's on the bench, the simulated bench's under --sim ---------------------------------
    def now(self):
        """Seconds, for measuring how long something took."""
        return self.sim.clock if self.sim else time.time()

    def sleep(self, seconds):
        """Wait `seconds` of bench time.  Under --sim the simulated bench's clock moves on at once, and the
        simulated board (if this command has started it) runs seconds / 1000 of its own time."""
        if not self.sim:
            time.sleep(seconds)
            return
        self.sim.advance(seconds)

    def size(self, what):
        """How big a measurement is: SIZES, the bench's number or the simulation's."""
        return SIZES[what][1 if self.sim else 0]

    def hardware_only(self, what):
        """Called first by everything that would touch the PC's own hardware outside the instrument and board
        objects (openFPGALoader, a serial port, a network socket): under --sim it must never get that far."""
        if self.sim:
            raise RuntimeError("%s reached under --sim: this is a bug in the tool" % what)

    # ---- the bench claims --------------------------------------------------------------------------------
    def claims_active(self):
        """False when claims are not checked: under --sim (unless $BENCH_CLAIMS_FILE names a scratch record,
        which is how test_bench.py exercises the refusals), or when bench_claims.py is not there."""
        if self.sim and not os.environ.get("BENCH_CLAIMS_FILE"):
            return False
        if bench_claims is None:
            if not self._no_claims_said:
                print("note: %s/bench_claims.py not found: no bench claim is checked" % LIC)
                self._no_claims_said = True
            return False
        return True

    def require(self, resources, what):
        """Call before switching an output on.  Raises Refused, in one sentence, unless this project holds the
        claim on every resource (e.g. ['E3646A:1'])."""
        if not self.claims_active():
            return
        try:
            bench_claims.require(resources, by=CLAIM_BY, mine=True)
        except bench_claims.BenchClaimed as e:
            raise Refused("STOPPED before switching %s on: this project does not hold the bench claim on %s.  "
                          "Once Jason has said the cables are on this board: `bench.py claim v1` (or `claim v2`).\n%s"
                          % (what, ", ".join(resources), e))

    def require_supply(self):
        """The supply's output is ours, and nobody else holds the E3646A's other output (one switch serves both)."""
        out = self.cfg["psu"]["out"]
        self.require(["E3646A:%d" % out], "the supply")
        if self.claims_active():
            try:
                bench_claims.require(["E3646A:%d" % (2 if out == 1 else 1)], by=CLAIM_BY, mine=False)
            except bench_claims.BenchClaimed as e:
                raise Refused("STOPPED before switching the supply on: the E3646A has one switch for both outputs, and its "
                              "other output is another project's.\n%s" % e)

    # ---- the supply ---------------------------------------------------------------------------
    def psu_setup(self, volts=SUPPLY_V, amps=SUPPLY_A, ovp=OVP_V):
        out = self.cfg["psu"]["out"]
        self.psu.set_range("LOW", out=out)
        self.psu.set_ovp(ovp, on=True, out=out)
        self.psu.set(volts, amps, out=out)
        if self.psu.outputs > 1:                  # the other output of an E3646A shares the switch: keep it at 0 V
            other = 2 if out == 1 else 1
            self.psu.set(0.0, 0.02, out=other)
        return self.psu.setting(out)

    def psu_read(self, label=None):
        v, i = self.psu.measure(out=self.cfg["psu"]["out"])
        return self.record("psu", label=label, volts=v, amps=i, mode=self.psu.mode(out=self.cfg["psu"]["out"]))

    def psu_output(self, on, quiet=False):
        if on:
            self.require_supply()
        self.psu.output(on)
        self.record("psu", quiet=quiet, output=bool(on), setting=self.psu.setting(self.cfg["psu"]["out"]))

    def psu_staircase(self, steps=STAIRCASE, dwell=2.0, quiet=False):
        """Stage 1.2: raise the input in steps with a low current limit, reading the current at each; off at the end."""
        out = self.cfg["psu"]["out"]
        self.require_supply()
        self.psu_setup(steps[0][0], steps[0][1])
        self.psu_output(True, quiet=quiet)
        rows = []
        try:
            for v, a in steps:
                self.psu.set(v, a, out=out)
                self.sleep(dwell)
                mv, mi = self.psu.measure(out=out)
                mode = self.psu.mode(out=out)
                rows.append({"set_v": v, "limit_a": a, "volts": mv, "amps": mi, "mode": mode})
                self.record("staircase", quiet=quiet, set_v=v, limit_a=a, volts=mv, amps=mi, mode=mode,
                            verdict="pass" if mode == "CV" else "FAIL (current limited: a short?)" if mode == "CC"
                            else "FAIL (the supply reports %s with its switch on)" % mode)
                if mode != "CV":                  # CC: a short.  OFF or UNREG with the switch on: the supply itself
                    break
        finally:
            self.psu_output(False, quiet=quiet)
        return rows

    def psu_log(self, seconds, every=1.0):
        t0 = self.now()
        while self.now() - t0 < seconds:
            self.psu_read("log")
            self.sleep(every)

    # ---- the multimeter --------------------------------------------------------------------------
    def dmm_read(self, label, settle=2, n=3):
        lo, hi = RAILS.get(label, (-99, 99))
        if self.dmm is None:
            v = float(input("Fluke on %s (pin of J602, ground spring on the pin beside it): reading in volts? " % label))
        else:
            self.dmm.function("VDC")
            vals = [self.dmm.read(settle=settle if k == 0 else 0) for k in range(n)]
            v = sum(vals) / len(vals)
        return self.record("dmm", rail=label, volts=v, lo=lo, hi=hi, verdict=verdict(v, lo, hi))

    # ---- the scope --------------------------------------------------------------------------------
    def scope_shot(self, name, quiet=False):
        path = os.path.join(self.log.dir, "%s_%s.png" % (dt.datetime.now().strftime("%Y%m%d_%H%M%S"), name))
        self.scope.screenshot(path)
        self.record("scope_shot", quiet=quiet, name=name, path=os.path.relpath(path, HERE))
        return path

    def scope_meas(self, ch, items):
        vals = {it: self.scope.pava(it, ch) for it in items}
        return self.record("scope", ch=ch, **vals)

    def scope_read(self, ch, items, settle=0.6):
        """The scope's own measurements of one channel, after the signal has changed: {item: value or None}.
        Waits `settle` first and 0.1 s between items: asked back to back, the scope keeps answering with the
        value from before the change (lab-instrument-control's siglent.md)."""
        self.sleep(settle)
        out = {}
        for item in items:
            out[item] = self.scope.pava(item, ch)
            self.sleep(0.1)
        return out

    # ---- the generators ----------------------------------------------------------------------------
    def gen_sine(self, freq, vpp, ch=1, load="HZ", offset=0.0):
        self.require(["SDG1032X:%d" % ch], "SDG1032X CH%d" % ch)
        self.gen.output(ch, on=False, load=load)
        self.gen.sine(ch, freq=freq, vpp=vpp, offset=offset)
        self.gen.output(ch, on=True)
        self.record("gen", ch=ch, wave="sine", freq=freq, vpp=vpp, offset=offset, load=load, on=True)

    def gen_off(self):
        for ch in (1, 2):
            try:
                self.gen.output(ch, on=False)
            except Exception as e:
                self.record("gen", ch=ch, error=repr(e))
        self.record("gen", on=False)

    def tone(self, source, freq, vpp):
        """A sine from 'sdg1' (SDG1032X CH1), 'sdg2' (CH2) or 'hp' (the 33220A): `vpp` volts peak to peak ACROSS
        a 50 ohm load, no offset.  The output is switched off, set, read back, and only then switched on.
        Raises Refused without the bench claim, ValueError beyond the board's limits (SDG_VLIMIT,
        HP_PEAK_INTO_50), IOError if the generator did not take the setting."""
        if source == "hp":
            if 0.5 * vpp > HP_PEAK_INTO_50:
                raise ValueError("33220A: %.2f Vpp into 50 ohm is more than the +-%.2f V this board's ADC input is given" % (vpp, HP_PEAK_INTO_50))
            self.require(["33220A"], "the 33220A")
            self.hpgen.output(on=False, load=50)
            self.hpgen.sine(freq, vpp, 0.0)          # the driver raises ValueError itself if the generator clipped the request
            self.hpgen.output(on=True)
        else:
            ch = int(source[-1])
            self.require(["SDG1032X:%d" % ch], "SDG1032X CH%d" % ch)
            self.gen.output(ch, on=False, load=50)
            w = self.gen.sine(ch, freq=freq, vpp=vpp, offset=0.0)
            if w.get("type") != "SINE" or abs(w["freq"] / freq - 1) > 1e-6 or abs(w["amp"] / vpp - 1) > 0.01:
                raise IOError("SDG1032X CH%d did not take a %g Hz, %g Vpp sine: it says %s" % (ch, freq, vpp, {k: w.get(k) for k in ("type", "freq", "amp", "offset")}))
            self.gen.output(ch, on=True)
        self.record("gen", quiet=True, source=source, wave="sine", freq=freq, vpp_into_50=vpp, on=True)

    def tone_off(self, source):
        if source == "hp":
            self.hpgen.output(on=False)
        else:
            self.gen.output(int(source[-1]), on=False)
        self.record("gen", quiet=True, source=source, on=False)

    def generators_off(self):
        """Every generator output off, each tried on its own; returns the list of what could not be switched."""
        failed = []
        for source in ("sdg1", "sdg2", "hp"):
            try:
                self.tone_off(source)
            except Exception as e:                    # noqa: BLE001: the others must still be tried
                failed.append("%s: %s" % (source, e))
        return failed

    # ---- the board ---------------------------------------------------------------------------------
    def board_call(self, name, *args, **kwargs):
        r = getattr(self.bd, name)(*args, **kwargs)
        self.record("board", call=name, args=args, kwargs=kwargs, result=_jsonable(r))
        return r

    def board_answers(self):
        """(True, {'id', 'version'}) when the board's ID register reads right over USB PROG, else (False, why).
        After a failure the port is opened afresh at the next try."""
        try:
            return True, self.bd.ident()
        except Exception as e:                        # noqa: BLE001: no port, no answer, a wrong ID: all "does not answer"
            self.board_forget()
            return False, "%s: %s" % (type(e).__name__, e)

    def board_forget(self):
        """Close the board's serial port (a bitstream is about to be loaded, or it stopped answering)."""
        if self.sim:
            return
        bd = self._cache.pop("bd", None)
        if bd is not None:
            try:
                bd.close()
            except Exception:
                pass

    def count_step_hz(self):
        """One count of the board's frequency counters in Hz: 1 on the bench (a 1 s gate), 1000 simulated (1 ms)."""
        return 1.0 / self.bd.t.gate_s

    def analog_setup(self):
        """The converters as every analog test starts: the DAC awake at 50 MS/s, both ports at mid-scale (0 V),
        the ADC at 25 MS/s."""
        self.bd.gpio(dac_sleep=0)
        self.bd.dac_config(rate=50e6)
        for port in (1, 2):
            self.bd.dac(port, "dc", code=8192)
        self.adc_setup(25e6)

    def adc_setup(self, rate, decim=0, stats_log2=STATS_LOG2):
        """The ADC's sample rate, with the capture phase and edge this board uses, and the length of the
        statistics window (2^stats_log2 samples)."""
        negedge = self.adc_negedge_50 if rate >= 50e6 else self.adc_negedge
        return self.bd.adc_config(rate=rate, phase=self.adc_phase, negedge=negedge, decim=decim, stats_log2=stats_log2)

    def adc_window(self):
        """min, max, mean and out-of-range count of both ADC channels over one whole statistics window that
        began AFTER this call (ecp5bu's adc_stats() alone returns the last finished window, which may be from
        before the signal changed).  Two windows are waited for: the first to end is the one in progress."""
        bd = self.bd
        seq0 = bd.rd("STATSEQ")
        t0 = bd.t.time()
        while (bd.rd("STATSEQ") - seq0) & 0xFFFF < 2:
            if bd.t.time() - t0 > 20.0:               # two windows are 0.3 ms at 25 MS/s (0.3 s of a simulated board's scaled time)
                raise IOError("the ADC statistics do not advance: is the ADC clocked (PLL locked)?")
            bd.wait(0.02)
        s = bd.adc_stats()
        for ch in ("a", "b"):
            s[ch]["pkpk"] = s[ch]["max"] - s[ch]["min"]
        return s

    def capture(self, n=None, rate=25e6, decim=0):
        """Capture both ADC channels: (t, a, b, otr) as ecp5bu's capture().  n defaults to the whole memory
        (512 samples simulated)."""
        self.adc_setup(rate, decim)
        self.bd.wait(0.01)
        return self.bd.capture(n or self.size("capture"))

    def save_capture(self, name, t, a, b, otr, **meta):
        import numpy as np
        path = os.path.join(self.log.dir, "%s_%s.npz" % (dt.datetime.now().strftime("%Y%m%d_%H%M%S"), name))
        np.savez_compressed(path, t=t, a=a, b=b, otr_a=otr[0], otr_b=otr[1], meta=json.dumps(meta))
        return os.path.relpath(path, HERE)

    def check(self):
        out = {}
        for name, fn in (("psu", lambda: self.psu.idn), ("dmm", lambda: self.dmm.ask("*IDN?") if self.dmm else "not configured"),
                         ("scope", lambda: self.scope.q("*IDN?")), ("gen", lambda: self.gen.idn),
                         ("board", lambda: self.bd.ident())):
            try:
                out[name] = fn()
            except (SystemExit, Refused) as e:
                out[name] = "-- %s" % e
            except Exception as e:
                out[name] = "-- %s: %s" % (type(e).__name__, e)
        self.record("check", **out)
        return out


def _jsonable(r):
    try:
        json.dumps(r)
        return r
    except TypeError:
        return repr(r)[:500]


# ---- the stages as procedures ---------------------------------------------------------------------------
def stage3_leds(b, a):
    """Stage 3.2: the LEDs and buttons through the register bus."""
    bd = b.bd
    b.record("board", ident=bd.ident(), status=bd.status())
    for v in (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0xFF, 0x00):
        bd.leds(v); b.sleep(0.3)
    for rgb in (1, 2, 4, 0):
        bd.leds(0, rgb=rgb); b.sleep(0.5)
    bd.leds(None)
    b.note("LEDs walked 0-7 then all, RGB red/green/blue; back to the chaser.  Did every LED light? (note it)")


def stage4_clocks(b, a):
    """Stage 4.1: every clock input's frequency, twice; CLK IN against the generator if cabled."""
    bd = b.bd
    for _ in range(2):
        c = bd.clocks()
        b.record("clocks", **c, verdict="pass" if c["tcxo"] == 25_000_000 and abs(c["clk_s"] - 50e6) < 100 else "FAIL")
    return c


def stage4_si5351(b, a):
    """Stage 4.2: program the Si5351's three outputs (10, 25, 100 MHz) and read them back on the counters."""
    bd = b.bd
    b.record("i2c", scan=["0x%02x" % x for x in bd.i2c_scan()])
    for clk, f in ((0, 10e6), (1, 25e6), (2, 100e6)):
        bd.si5351_set(clk, f)
    b.sleep(0.2)
    st = bd.si5351_status()
    c = bd.clocks()
    ok = abs(c["si0"] - 10e6) < 1000 and abs(c["si1"] - 25e6) < 2500 and abs(c["si2"] - 100e6) < 10000
    b.record("si5351", status=st, si0=c["si0"], si1=c["si1"], si2=c["si2"], verdict="pass" if ok else "FAIL")
    return c


def stage4_clkin(b, a):
    """Stage 4.3: the SDG's 10 MHz sine (1 Vpp into 50 ohm, JP3001 shunt in) on CLK IN, read by the counter: the TCXO's error in ppm."""
    b.gen_sine(10e6, 1.0, ch=1, load=50)
    b.sleep(0.5)
    c = b.bd.clocks()
    ppm = (c["clk_in"] - 10e6) / 10.0
    b.record("clkin", clk_in=c["clk_in"], tcxo_error_ppm=-ppm, verdict="pass" if abs(ppm) < 10 else "FAIL (counter vs generator differ by > 10 ppm)")
    b.gen_off()
    return c


def stage5_dac_dc(b, a):
    """Stage 5.1: DAC DC codes against the scope (CH1 on DAC 1 OUT, CH2 on DAC 2 OUT, 1 Mohm): +-2 V open circuit."""
    bd = b.bd
    bd.gpio(dac_sleep=0)
    bd.dac_config(rate=25e6)
    for ch in (1, 2):
        b.scope.channel(ch, on=True, scale=0.5, offset=0, coupling="DC", impedance="1M")
    b.scope.timebase(scale=1e-3)
    rows = []
    for code, expect in ((8192, 0.0), (16383, 2.0), (0, -2.0), (12288, 1.0), (4096, -1.0)):
        for port in (1, 2):
            bd.dac(port, "dc", code=code)
        b.sleep(0.3)
        v1, v2 = b.scope.pava("MEAN", 1), b.scope.pava("MEAN", 2)
        row = {"code": code, "expect_v": expect, "dac1_v": v1, "dac2_v": v2,
               "verdict": "pass" if v1 is not None and v2 is not None and abs(v1 - expect) < 0.1 and abs(v2 - expect) < 0.1 else "FAIL"}
        rows.append(row); b.record("dac_dc", **row)
    for port in (1, 2):
        bd.dac(port, "dc", code=8192)
    return rows


def stage5_dac_sine(b, a):
    """Stage 5.2: a 1 MHz full-scale sine on both DACs; the scope's amplitude and frequency."""
    bd = b.bd
    bd.dac_config(rate=50e6)
    f = bd.dac(1, "sine", freq=1e6); bd.dac(2, "sine", freq=1e6)
    for ch in (1, 2):
        b.scope.channel(ch, on=True, scale=0.5, offset=0, coupling="DC", impedance="1M")
    b.scope.timebase(scale=5e-7)
    b.sleep(0.5)
    for ch in (1, 2):
        m = {it: b.scope.pava(it, ch) for it in ("PKPK", "FREQ", "MEAN")}
        b.record("dac_sine", port=ch, set_freq=f, **m, verdict="pass" if m["PKPK"] and 3.6 < m["PKPK"] < 4.4 and abs(m["FREQ"] - 1e6) < 1e3 else "FAIL")
    b.scope_shot("dac_sine_1MHz")


def stage6_adc_gen(b, a):
    """Stage 6.1: the SDG's sine (CH1 -> ADC A IN, 1 Vpp into 50 ohm with the TERM shunt in) captured by the board."""
    import numpy as np
    bd = b.bd
    freq = a.freq if hasattr(a, "freq") and a.freq else 100e3
    b.gen_sine(freq, 1.0, ch=1, load=50)
    bd.adc_config(rate=25e6)
    b.sleep(0.3)
    t, ca, cb, otr = bd.capture(8192)
    for name, x in (("A", ca), ("B", cb)):
        v = (x - 2048) / 2048.0                                           # volts at the ADC input (2 Vpp span)
        spec = np.abs(np.fft.rfft((v - v.mean()) * np.hanning(len(v))))
        k = spec.argmax(); fpk = k * 25e6 / len(v)
        row = {"channel": name, "mean_code": float(x.mean()), "pkpk_code": int(x.max() - x.min()), "peak_hz": fpk, "otr": int(otr[0 if name == "A" else 1].sum())}
        row["verdict"] = ("pass" if 1700 < row["pkpk_code"] < 2300 and abs(fpk - freq) < 25e6 / len(v) * 2 else "FAIL") if name == "A" else "info"
        b.record("adc_gen", gen_freq=freq, **row)
    path = b.save_capture("adc_gen_%gHz" % freq, t, ca, cb, otr, gen_freq=freq, gen_vpp=1.0)
    b.record("capture", path=path)
    b.gen_off()


def stage6_adc_noise(b, a):
    """Stage 6.2: nothing on the inputs (TERM shunts in: 50 ohm to ground): the code noise of each channel."""
    bd = b.bd
    bd.adc_config(rate=25e6)
    t, ca, cb, otr = bd.capture(8192)
    for name, x in (("A", ca), ("B", cb)):
        b.record("adc_noise", channel=name, mean=float(x.mean()), std_codes=float(x.std()), min=int(x.min()), max=int(x.max()),
                 verdict="pass" if x.std() < 3.0 and abs(x.mean() - 2048) < 100 else "FAIL (check: >3 codes rms, or the offset)")
    b.record("capture", path=b.save_capture("adc_noise", t, ca, cb, otr))


def stage6_loopback(b, a):
    """Stage 6.3: DAC 1 OUT -> ADC A IN by an SMA cable (TERM shunt in): the whole analog chain, 1 MHz at half scale
    (2048 codes peak to peak: a full-scale DAC sine is the ADC's whole 4096 and clips on a few codes of offset).
    `v1b --only sine` is the fuller test: its tones fit the capture, so its SFDR is not window leakage."""
    import numpy as np
    bd = b.bd
    bd.dac_config(rate=50e6); bd.adc_config(rate=25e6)
    f = bd.dac(1, "sine", freq=1e6, shift=1)
    b.sleep(0.2)
    t, ca, cb, otr = bd.capture(8192)
    v = (ca - 2048) / 2048.0
    spec = np.abs(np.fft.rfft((v - v.mean()) * np.hanning(len(v))))
    k = spec.argmax(); fund = spec[k]
    spec[max(0, k - 3):k + 4] = 0
    sfdr = 20 * np.log10(fund / spec[1:].max())
    b.record("loopback", dac_freq=f, pkpk_code=int(ca.max() - ca.min()), peak_hz=k * 25e6 / len(v), sfdr_db=float(sfdr),
             verdict="pass" if 1500 < ca.max() - ca.min() < 2300 else "FAIL")
    b.record("capture", path=b.save_capture("loopback_1MHz", t, ca, cb, otr, dac_freq=f))
    bd.dac(1, "dc", code=8192)


def stage7_sdram(b, a):
    """Stage 7.1: the read-latency scan on 4096 words, then the whole 32 MB at the latency that passed."""
    bd = b.bd
    scan = bd.sdram_scan(4096)
    good = [lat for lat, e in scan.items() if e == 0]
    b.record("sdram_scan", errors_by_latency=scan, good=good, verdict="pass" if good else "FAIL")
    if good:
        lat = good[len(good) // 2]
        for pat in (0, 1, 6):
            r = bd.sdram_test(1 << 24, pattern=pat, rdlat=lat)
            b.record("sdram_full", **r, verdict="pass" if r["errors"] == 0 else "FAIL")


def stage7_phy(b, a):
    """Stage 7.2: the PHY's ID over MDIO, its link status, RXC's frequency (125 MHz with a gigabit link up)."""
    bd = b.bd
    ids = bd.phy_id()
    st = bd.phy_status()
    c = bd.clocks()
    b.record("phy", id=["0x%04x" % x for x in ids], **st, rxc_hz=c["rxc"], verdict="pass" if ids == (0x001C, 0xC916) else "FAIL")


STAGES = {"stage3.leds": stage3_leds, "stage4.clocks": stage4_clocks, "stage4.si5351": stage4_si5351, "stage4.clkin": stage4_clkin,
          "stage5.dac_dc": stage5_dac_dc, "stage5.dac_sine": stage5_dac_sine, "stage6.adc_gen": stage6_adc_gen,
          "stage6.adc_noise": stage6_adc_noise, "stage6.loopback": stage6_loopback, "stage7.sdram": stage7_sdram, "stage7.phy": stage7_phy}


# ---- the small commands -------------------------------------------------------------------------------------
# What each visit claims on the bench (bench_claims.py's resource names), what it says they are cabled to, and
# the most this tool puts on them.  The supply's output number is bench_config.json's psu.out.
def claim_plan(visit, board, psu_out):
    v1 = ["E3646A:%d" % psu_out, "Fluke45"]
    v2 = ["SDG1032X:1", "SDG1032X:2", "33220A", "SDS2104X:1", "SDS2104X:2", "SDS2104X:3", "SDS2104X:4"]
    if visit == "v1":
        return (v1, "ECP5-2ADC-2DAC board %s: E3646A output %d -> J601 5 V IN; Fluke 45 probes -> the RAILS header J602" % (board, psu_out),
                "supply 5.0 V, 1.0 A limit, OVP 5.6 V; the Fluke only reads")
    return (v1 + v2, "ECP5-2ADC-2DAC board %s: E3646A output %d -> J601; SDG CH1 -> ADC A IN, SDG CH2 -> CLK IN, 33220A -> ADC B IN; "
            "scope CH1 -> DAC 1 OUT, CH2 -> DAC 2 OUT, CH3 -> CLK OUT, CH4 -> a tap or nothing" % (board, psu_out),
            "supply 5.0 V 1.0 A; ADC inputs +-1.25 V into their 50 ohm; CLK IN 3 Vpp into 50 ohm; the scope only reads")


def cmd_claim(b, visit):
    """`claim v1` / `claim v2`: record in the bench's claim file that the instruments are cabled to this board.
    Only after Jason has said so in this visit: a claim is his word, not a measurement."""
    if not b.claims_active():
        print("simulation: no claim is made or checked." if b.sim else "bench_claims.py is not available: nothing recorded.")
        return 0
    resources, to, limit = claim_plan(visit, b.board, b.cfg["psu"]["out"])
    try:
        bench_claims.claim(resources, by=CLAIM_BY, to=to, limit=limit)
    except bench_claims.BenchClaimed as e:
        print("NOT CLAIMED: another project holds one of these instruments, and nothing was changed.  Ask Jason which board the "
              "cables are on; only on his word: `python3 %s/bench_claims.py claim ... --by %s --force`.\n%s" % (LIC, CLAIM_BY, e))
        return 1
    b.record("claim", quiet=True, visit=visit, resources=resources, to=to, limit=limit)
    print("claimed for %s: %s" % (CLAIM_BY, ", ".join(resources)))
    print(bench_claims.table())
    return 0


def cmd_release(b):
    """`release`: give back everything this project holds (when the board leaves the bench)."""
    if not b.claims_active():
        print("simulation: no claim is made or checked." if b.sim else "bench_claims.py is not available: nothing recorded.")
        return 0
    gone = bench_claims.release(None, by=CLAIM_BY)
    b.record("release", quiet=True, resources=gone)
    print("released: " + (", ".join(gone) if gone else "nothing (this project held no claim)"))
    return 0


def cmd_where():
    """`where`: print STATUS.md."""
    with open(os.path.join(HERE, "STATUS.md")) as f:
        print(f.read())
    return 0


def cmd_report(b):
    """`report`: the latest verdict of every test of this board, from all its logs, as one markdown table."""
    import report
    rows = report.latest_rows(b.log.entries())
    print("# Board %s: the latest result of every test%s" % (b.board, " (SIMULATED)" if b.sim else ""))
    print()
    if not rows:
        print("No results in %s yet." % os.path.relpath(b.log.dir, HERE))
        return 0
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in report.VERDICTS}
    print("%d pass, %d FAIL, %d info, %d skipped; from %s" % (counts["pass"], counts["FAIL"], counts["info"], counts["skipped"], os.path.relpath(b.log.dir, HERE)))
    print()
    for r in rows:
        r["note"] = (r.get("note") or "") + ("" if not r.get("t") else (" " if r.get("note") else "") + "[%s]" % r["t"][:16].replace("T", " "))
    print("\n".join(report.markdown_table(rows, with_visit=True)))
    return 0


# Which simulated bench each command starts from under --sim (simbench.PRESETS says what each is)
SIM_PRESET = {"v1a": "power", "rails": "power_on", "coldboot": "coldboot", "v1b": "selftest", "v2": "instruments", "step": "instruments",
              "psu": "power", "dmm": "power_on"}
GLOBAL_OPTIONS = ("--board", "--stage", "--sim-fault")      # options with a value that may stand anywhere on the line


def take_global_options(argv):
    """`--sim`, `--board X`, `--stage X` and `--sim-fault X` may be typed before or after the command
    (`bench.py v1b --sim --board B`): move them to the front, where argparse wants its global options."""
    front, rest = [], []
    i = 0
    while i < len(argv):
        word = argv[i]
        if word == "--sim":
            front.append(word)
        elif word in GLOBAL_OPTIONS and i + 1 < len(argv):
            front += [word, argv[i + 1]]
            i += 1
        elif word.split("=")[0] in GLOBAL_OPTIONS and "=" in word:
            front.append(word)
        else:
            rest.append(word)
        i += 1
    return front + rest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", default=None)
    p.add_argument("--stage", default=None)
    p.add_argument("--sim", action="store_true", help="the simulated board and instruments: no hardware is touched")
    p.add_argument("--sim-fault", default="", help="with --sim: comma-separated names from simbench.FAULTS")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("check")
    n = sub.add_parser("note"); n.add_argument("text")
    ps = sub.add_parser("psu"); ps.add_argument("what", choices=["staircase", "on", "off", "read", "log", "status"])
    ps.add_argument("--volts", type=float, default=SUPPLY_V); ps.add_argument("--amps", type=float, default=SUPPLY_A)
    ps.add_argument("--n", type=int, default=1); ps.add_argument("--seconds", type=float, default=60)
    d = sub.add_parser("dmm"); d.add_argument("rail")
    sc = sub.add_parser("scope"); sc.add_argument("what", choices=["shot", "meas"]); sc.add_argument("args", nargs="*")
    g = sub.add_parser("gen"); g.add_argument("what", choices=["sine", "off"]); g.add_argument("args", nargs="*")
    g.add_argument("--ch", type=int, default=1); g.add_argument("--load", default="50")
    bd = sub.add_parser("board"); bd.add_argument("args", nargs="+")
    r = sub.add_parser("run"); r.add_argument("stage_name", nargs="?"); r.add_argument("--list", action="store_true"); r.add_argument("--freq", type=float, default=None)
    s = sub.add_parser("show"); s.add_argument("--n", type=int, default=20)
    # the visits
    sub.add_parser("where")
    c = sub.add_parser("claim"); c.add_argument("visit", choices=["v1", "v2"])
    sub.add_parser("release")
    sub.add_parser("v1a")
    ra = sub.add_parser("rails"); ra.add_argument("--seconds", type=float, default=180.0)
    for name in ("v1b", "v2"):
        v = sub.add_parser(name)
        v.add_argument("--only", default="", help="run only these tests: NAME[,NAME]")
        v.add_argument("--skip", default="", help="leave these tests out: NAME[,NAME]")
        v.add_argument("--list", action="store_true", help="name the tests and stop")
        if name == "v1b":
            v.add_argument("--soak-minutes", type=float, default=None, help="how long the soak runs (10 on the bench, 0 simulated)")
            v.add_argument("--soak-every", type=float, default=30.0, help="seconds between the soak's samples")
    cb = sub.add_parser("coldboot"); cb.add_argument("--n", type=int, default=10)
    st = sub.add_parser("step"); st.add_argument("name", nargs="?"); st.add_argument("--list", action="store_true")
    st.add_argument("--seconds", type=float, default=30.0, help="buttons, prog: how long to wait for the press")
    st.add_argument("--n", type=int, default=10, help="poweron: how many power cycles")
    st.add_argument("--ch", type=int, default=1, help="dac_clock: the scope channel the held probe is on")
    st.add_argument("--sim-as-found", action="store_true", help="with --sim: leave the simulated bench as it was (the jumper was NOT moved)")
    sub.add_parser("report")
    a = p.parse_args(take_global_options(list(sys.argv[1:] if argv is None else argv)))
    if not a.cmd:
        p.print_help(); return 2
    if a.cmd == "where":
        return cmd_where()
    faults = [x for x in a.sim_fault.split(",") if x]
    if faults and not a.sim:
        print("--sim-fault only means something with --sim"); return 2
    if a.cmd == "board" and a.sim:
        print("`board ...` is ecp5bu's own command line and opens the real serial port: it has no --sim.  Use `run`, `v1b --only ...` or `step`.")
        return 2
    try:
        b = Bench(a.board, a.stage, sim=a.sim, sim_preset=SIM_PRESET.get(a.cmd, "selftest"), sim_faults=faults)
    except ValueError as e:                       # an unknown --sim-fault
        print(e); return 2
    try:
        if a.cmd == "check":
            for k, v in b.check().items(): print("%-6s %s" % (k, v))
        elif a.cmd == "note":
            b.note(a.text)
        elif a.cmd == "psu":
            if a.what == "staircase": b.psu_staircase()
            elif a.what == "on": b.psu_setup(a.volts, a.amps); b.psu_output(True); b.sleep(1.0); b.psu_read("on")
            elif a.what == "off": b.psu_output(False)
            elif a.what == "read":
                for _ in range(a.n): b.psu_read(); b.sleep(0.5)
            elif a.what == "log": b.psu_log(a.seconds)
            elif a.what == "status": print(json.dumps(b.psu.status(), indent=1, default=repr))
        elif a.cmd == "dmm":
            b.dmm_read(a.rail)
        elif a.cmd == "scope":
            if a.what == "shot": b.scope_shot(a.args[0] if a.args else "shot")
            else: b.scope_meas(int(a.args[0]), a.args[1:] or ["PKPK", "FREQ", "MEAN"])
        elif a.cmd == "gen":
            if a.what == "sine": b.gen_sine(float(a.args[0]), float(a.args[1]), ch=a.ch, load=a.load)
            else: b.gen_off()
        elif a.cmd == "board":
            import ecp5bu
            sys.argv = ["ecp5bu", b.cfg["board_port"]] + a.args
            b.record("board", cli=a.args)
            return ecp5bu.main(sys.argv[1:])
        elif a.cmd == "run":
            if a.list or not a.stage_name:
                for k, f in STAGES.items(): print("%-18s %s" % (k, f.__doc__))
            else:
                b.stage = b.stage or a.stage_name.split(".")[0].replace("stage", "")
                STAGES[a.stage_name](b, a)
        elif a.cmd == "show":
            for e in b.log.tail(a.n): print(_fmt(e))
        elif a.cmd == "claim":
            return cmd_claim(b, a.visit)
        elif a.cmd == "release":
            return cmd_release(b)
        elif a.cmd == "report":
            return cmd_report(b)
        elif a.cmd in ("v1a", "rails", "v1b", "coldboot"):
            import visit1
            return {"v1a": visit1.v1a, "rails": visit1.rails, "v1b": visit1.v1b, "coldboot": visit1.coldboot}[a.cmd](b, a)
        elif a.cmd == "v2":
            import visit2
            return visit2.v2(b, a)
        elif a.cmd == "step":
            import visit3
            return visit3.step(b, a)
    except Refused as e:
        print("\n" + str(e))
        return 1
    finally:
        b.close()
    return 0


if __name__ == "__main__":
    import bench                 # run the copy of this module that visit1.py, visit2.py and visit3.py import,
    sys.exit(bench.main())       # so there is one Bench class, one Refused and one RAILS table in the program
