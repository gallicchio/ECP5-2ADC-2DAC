#!/usr/bin/env python3
"""bench.py: the ECP5-2ADC-2DAC rev A bring-up from the bench PC.  The lab instruments (~/lab-instrument-control:
the E3646A supply, the Fluke 45, the SDS2104X Plus scope, the SDG1032X and 33220A generators) and the board
(gateware/bringup/host/ecp5bu.py over the FT2232H's serial channel) in one place, every reading appended to
bringup/data/board_<X>/<date>.jsonl with the time, the stage, the settings and the verdict.

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

The board is `--board A` (or $ECP5_BOARD, or bench_config.json's "board"): mark the two assembled boards A and
B.  The addresses are bench_config.json's (written with defaults the first time; edit it, or run `check`).
Nothing here changes an instrument except the command that says so; `check` sends *IDN? and nothing else.
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

CONFIG = os.path.join(HERE, "bench_config.json")
DEFAULTS = {
    "board": "A",
    # the 5 V: E3646A output 1 (0-8 V, 3 A, OVP only; one switch for both outputs) on RS-232:
    # find the port with `python3 ~/lab-instrument-control/scpi_link.py identify`
    "psu": {"serial": None, "gpib": None, "out": 1},
    "dmm": {"serial": None},                                    # the Fluke 45 on RS-232; None = type the readings
    "scope": {"host": "192.168.8.203"},                         # Siglent SDS2104X Plus
    "gen": {"host": "192.168.8.246"},                           # Siglent SDG1032X
    "hpgen": {"host": "192.168.8.240"},                         # Agilent 33220A (LAN), when it is plugged in
    "board_port": "auto",                                       # the FT2232H's channel B, by its name under /dev/serial/by-id
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
    """append-only JSON lines, one file a board a day; every entry has t, board, stage, kind"""
    def __init__(self, board):
        self.board = board
        self.dir = os.path.join(HERE, "data", "board_%s" % board)
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, dt.date.today().isoformat() + ".jsonl")

    def add(self, kind, stage=None, **fields):
        e = {"t": now_iso(), "board": self.board, "stage": stage, "kind": kind}
        e.update(fields)
        with open(self.path, "a") as f:
            f.write(json.dumps(e, default=repr) + "\n")
        print(_fmt(e))
        return e

    def tail(self, n=20):
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [json.loads(x) for x in f.readlines()[-n:]]


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
    def __init__(self, board=None, stage=None):
        self.cfg = load_config()
        self.board = board or os.environ.get("ECP5_BOARD") or self.cfg["board"]
        self.stage = stage
        self.log = Log(self.board)
        self._cache = {}

    def _get(self, name, factory):
        if name not in self._cache:
            self._cache[name] = factory()
        return self._cache[name]

    @property
    def psu(self):
        def make():
            from agilent_E36xxA import AgilentE36xxA
            c = self.cfg["psu"]
            if c.get("serial"):
                return AgilentE36xxA(serial=c["serial"])
            if c.get("gpib"):
                return AgilentE36xxA(address=c["gpib"])
            raise SystemExit("bench_config.json: psu.serial (the /dev/serial/by-id path; `python3 %s/scpi_link.py identify`)" % LIC)
        return self._get("psu", make)

    @property
    def dmm(self):
        def make():
            if not self.cfg["dmm"].get("serial"):
                return None
            from fluke_45 import Fluke45
            return Fluke45(serial=self.cfg["dmm"]["serial"])
        return self._get("dmm", make)

    @property
    def scope(self):
        def make():
            from siglent_SDS2104X import SDS2104X
            h = self.cfg["scope"]["host"]
            if not reachable(h):
                raise SystemExit("scope %s not reachable" % h)
            return SDS2104X(h)
        return self._get("scope", make)

    @property
    def gen(self):
        def make():
            from siglent_SDG1032X import SDG1032X
            h = self.cfg["gen"]["host"]
            if not reachable(h):
                raise SystemExit("generator %s not reachable" % h)
            return SDG1032X(h)
        return self._get("gen", make)

    @property
    def hpgen(self):
        def make():
            from agilent_33220A import Agilent33220A
            return Agilent33220A(self.cfg["hpgen"]["host"])
        return self._get("hpgen", make)

    @property
    def bd(self):
        def make():
            from ecp5bu import Board
            return Board(self.cfg["board_port"])
        return self._get("bd", make)

    def close(self):
        for k, v in self._cache.items():
            try:
                v.close()
            except Exception:
                pass

    def note(self, text, **kw):
        return self.log.add("note", self.stage, text=text, **kw)

    def record(self, kind, **kw):
        return self.log.add(kind, self.stage, **kw)

    # ---- the supply ---------------------------------------------------------------------------
    def psu_setup(self, volts=SUPPLY_V, amps=SUPPLY_A, ovp=OVP_V):
        ps, out = self.psu, self.cfg["psu"]["out"]
        ps.set_range("LOW", out=out)
        ps.set_ovp(ovp, on=True, out=out)
        ps.set(volts, amps, out=out)
        if ps.outputs > 1:                        # the other output of an E3646A shares the switch: keep it at 0 V
            other = 2 if out == 1 else 1
            ps.set(0.0, 0.02, out=other)
        return ps.setting(out)

    def psu_read(self, label=None):
        v, i = self.psu.measure(out=self.cfg["psu"]["out"])
        return self.record("psu", label=label, volts=v, amps=i, mode=self.psu.mode(out=self.cfg["psu"]["out"]))

    def psu_output(self, on):
        self.psu.output(on)
        self.record("psu", output=bool(on), setting=self.psu.setting(self.cfg["psu"]["out"]))

    def psu_staircase(self, steps=STAIRCASE, dwell=2.0):
        """Stage 1.2: raise the input in steps with a low current limit, reading the current at each; off at the end."""
        out = self.cfg["psu"]["out"]
        self.psu_setup(steps[0][0], steps[0][1])
        self.psu_output(True)
        rows = []
        try:
            for v, a in steps:
                self.psu.set(v, a, out=out)
                time.sleep(dwell)
                mv, mi = self.psu.measure(out=out)
                mode = self.psu.mode(out=out)
                rows.append({"set_v": v, "limit_a": a, "volts": mv, "amps": mi, "mode": mode})
                self.record("staircase", set_v=v, limit_a=a, volts=mv, amps=mi, mode=mode,
                            verdict="FAIL (current limited: a short?)" if mode == "CC" else "pass")
                if mode == "CC":
                    break
        finally:
            self.psu_output(False)
        return rows

    def psu_log(self, seconds, every=1.0):
        t0 = time.time()
        while time.time() - t0 < seconds:
            self.psu_read("log")
            time.sleep(every)

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
    def scope_shot(self, name):
        path = os.path.join(self.log.dir, "%s_%s.png" % (dt.datetime.now().strftime("%Y%m%d_%H%M%S"), name))
        self.scope.screenshot(path)
        self.record("scope_shot", name=name, path=os.path.relpath(path, HERE))
        return path

    def scope_meas(self, ch, items):
        vals = {it: self.scope.pava(it, ch) for it in items}
        return self.record("scope", ch=ch, **vals)

    # ---- the generator ----------------------------------------------------------------------------
    def gen_sine(self, freq, vpp, ch=1, load="HZ", offset=0.0):
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

    # ---- the board ---------------------------------------------------------------------------------
    def board_call(self, name, *args, **kwargs):
        r = getattr(self.bd, name)(*args, **kwargs)
        self.record("board", call=name, args=args, kwargs=kwargs, result=_jsonable(r))
        return r

    def save_capture(self, name, t, a, b, otr, **meta):
        import numpy as np
        path = os.path.join(self.log.dir, "%s_%s.npz" % (dt.datetime.now().strftime("%Y%m%d_%H%M%S"), name))
        np.savez_compressed(path, t=t, a=a, b=b, otr_a=otr[0], otr_b=otr[1], meta=json.dumps(meta))
        return os.path.relpath(path, HERE)

    def check(self):
        out = {}
        for name, fn in (("psu", lambda: self.psu.idn), ("dmm", lambda: self.dmm.ask("*IDN?") if self.dmm else "not configured"),
                         ("scope", lambda: self.scope.q("*IDN?")), ("gen", lambda: self.gen.q("*IDN?")),
                         ("board", lambda: self.bd.ident())):
            try:
                out[name] = fn()
            except SystemExit as e:
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
        bd.leds(v); time.sleep(0.3)
    for rgb in (1, 2, 4, 0):
        bd.leds(0, rgb=rgb); time.sleep(0.5)
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
    time.sleep(0.2)
    st = bd.si5351_status()
    c = bd.clocks()
    ok = abs(c["si0"] - 10e6) < 1000 and abs(c["si1"] - 25e6) < 2500 and abs(c["si2"] - 100e6) < 10000
    b.record("si5351", status=st, si0=c["si0"], si1=c["si1"], si2=c["si2"], verdict="pass" if ok else "FAIL")
    return c


def stage4_clkin(b, a):
    """Stage 4.3: the SDG's 10 MHz sine (1 Vpp into 50 ohm, JP3001 shunt in) on CLK IN, read by the counter: the TCXO's error in ppm."""
    b.gen_sine(10e6, 1.0, ch=1, load=50)
    time.sleep(0.5)
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
    sc = b.scope
    for ch in (1, 2):
        sc.channel(ch, on=True, scale=0.5, offset=0, coupling="DC", impedance="1M")
    sc.timebase(scale=1e-3)
    rows = []
    for code, expect in ((8192, 0.0), (16383, 2.0), (0, -2.0), (12288, 1.0), (4096, -1.0)):
        for port in (1, 2):
            bd.dac(port, "dc", code=code)
        time.sleep(0.3)
        v1, v2 = sc.pava("MEAN", 1), sc.pava("MEAN", 2)
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
    sc = b.scope
    for ch in (1, 2):
        sc.channel(ch, on=True, scale=0.5, offset=0, coupling="DC", impedance="1M")
    sc.timebase(scale=5e-7)
    time.sleep(0.5)
    for ch in (1, 2):
        m = {it: sc.pava(it, ch) for it in ("PKPK", "FREQ", "MEAN")}
        b.record("dac_sine", port=ch, set_freq=f, **m, verdict="pass" if m["PKPK"] and 3.6 < m["PKPK"] < 4.4 and abs(m["FREQ"] - 1e6) < 1e3 else "FAIL")
    b.scope_shot("dac_sine_1MHz")


def stage6_adc_gen(b, a):
    """Stage 6.1: the SDG's sine (CH1 -> ADC A IN, 1 Vpp into 50 ohm with the TERM shunt in) captured by the board."""
    import numpy as np
    bd = b.bd
    freq = a.freq if hasattr(a, "freq") and a.freq else 100e3
    b.gen_sine(freq, 1.0, ch=1, load=50)
    bd.adc_config(rate=25e6)
    time.sleep(0.3)
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
    """Stage 6.3: DAC 1 OUT -> ADC A IN by an SMA cable (TERM shunt in): the whole analog chain, 1 MHz."""
    import numpy as np
    bd = b.bd
    bd.dac_config(rate=50e6); bd.adc_config(rate=25e6)
    f = bd.dac(1, "sine", freq=1e6)
    time.sleep(0.2)
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


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", default=None)
    p.add_argument("--stage", default=None)
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
    a = p.parse_args()
    if not a.cmd:
        p.print_help(); return 2
    b = Bench(a.board, a.stage)
    try:
        if a.cmd == "check":
            for k, v in b.check().items(): print("%-6s %s" % (k, v))
        elif a.cmd == "note":
            b.note(a.text)
        elif a.cmd == "psu":
            if a.what == "staircase": b.psu_staircase()
            elif a.what == "on": b.psu_setup(a.volts, a.amps); b.psu_output(True); time.sleep(1.0); b.psu_read("on")
            elif a.what == "off": b.psu_output(False)
            elif a.what == "read":
                for _ in range(a.n): b.psu_read(); time.sleep(0.5)
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
    finally:
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
