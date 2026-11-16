"""simbench.py: the bench, simulated, for `bench.py --sim`.

`bench.py --sim` runs every procedure of the bring-up with no hardware: the board is gateware/bringup's RTL in
iverilog (host/cosim.py's SimBoard, the same driver class as the real board), and the five instruments are the
fakes below.  The fakes have the real drivers' method names and arguments (test_bench.py compares them with
~/lab-instrument-control's classes) and behave plausibly: the supply's current rises with its voltage, the
multimeter plays a probe walk along the RAILS header, the scope reads what the simulated board's DAC and
CLK OUT registers say, and switching a generator's output on feeds its sine into the simulated ADC or CLK IN.

    sim = SimBench('selftest', faults=['crossed'])   # the cabling of a visit, and what is wrong with it
    sim.board                                        # cosim.SimBoard, started when first asked for (3 s)
    sim.psu, sim.dmm, sim.scope, sim.gen, sim.hpgen  # FakePSU, FakeDMM, FakeScope, FakeGen, FakeGen2

What the simulated bench holds is three dictionaries (wiring, jumpers, plugged); SimBench.apply() turns them
into the knobs of sim/tb_cosim.v through SimBoard.world().  What it cannot do is listed at the end of this
docstring, and in bringup/README.md.

PRESETS: what the person cabled before typing the words of each visit (BRINGUP.md).
FAULTS:  what `--sim-fault NAME[,NAME]` can get wrong on top of that, so the tool's findings are exercised.

Simulated time: a co-simulated board runs about 4 s of real time for 1 ms of its own, and cosim shortens every
wait a thousand times.  The fakes do not wait at all: they move SimBench.clock, a count of bench seconds that
bench.py uses in place of time.time() under --sim.

Not simulated (the simulated bench has no knob for it): a DC offset or a noise source on an ADC input (the
Johnson-noise step uses a small sine in its place and says so), any frequency response or distortion of the
analog paths, the supply actually powering the board (the simulated board runs whatever the fake supply
does), a monitor's picture, the PROG button.
"""
import math
import os
import random
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gateware", "bringup", "host"))

PRESETS = {
    "power":       "visit 1A before `v1a`: the supply's leads on J601, its output off; nothing else; a blank flash",
    "power_on":    "visit 1A after `v1a`: 5.0 V on, the FPGA unconfigured; the Fluke's probes in hand",
    "selftest":    "visit 1B: 5.0 V on, both USB cables, the three SMA cables (DAC 1 - ADC A, DAC 2 - ADC B, CLK OUT - CLK IN), "
                   "Ethernet to the switch, a microSD card; bringup.bit running",
    "coldboot":    "visit 2 step 1: as visit 1B with both USB cables pulled; bringup.bit in the flash",
    "instruments": "visit 2 and visit 3: SDG CH1 - ADC A IN, SDG CH2 - CLK IN, 33220A - ADC B IN, scope CH1 - DAC 1 OUT, "
                   "CH2 - DAC 2 OUT, CH3 - CLK OUT; USB, Ethernet and the card still in",
}
FAULTS = {
    "short":         "the supply sees a short: constant current at the first step of the staircase",
    "overcurrent":   "the board draws 0.85 A at 5 V (the pass condition is under 0.7 A)",
    "rail_low":      "the Fluke walk: +3V3_ADC reads 3.05 V (its window is 3.25-3.35 V)",
    "rail_skipped":  "the Fluke walk: the +2V5 pin is skipped (eight steady readings)",
    "rail_twice":    "the Fluke walk: the +1V1 pin is touched twice (ten steady readings)",
    "crossed":       "the two DAC cables are crossed: DAC 1 OUT - ADC B IN, DAC 2 OUT - ADC A IN",
    "no_sma_a":      "no cable on ADC A IN",
    "no_clk_cable":  "no cable from CLK OUT to CLK IN",
    "no_card":       "no microSD card",
    "no_usb":        "USB USER not cabled to a host",
    "no_link":       "no Ethernet link",
    "gain_a_x10":    "one GAIN shunt of channel A (JP103) left out: x10",
    "term_b_open":   "the TERM shunt of channel B (JP201) left out",
    "monitor":       "a monitor is plugged in (optional in visit 1B)",
    "pmod_loop":     "Pmod A is wired to Pmod B (optional in visit 1B)",
    "no_flash_boot": "the board does not configure itself from its flash at power-on",
    "gens_swapped":  "visit 2: SDG CH1 is on ADC B IN and the 33220A on ADC A IN (harmless)",
    "scope_swapped": "visit 2: scope CH1 is on DAC 2 OUT and CH2 on DAC 1 OUT (harmless)",
    "sdg_swapped":   "visit 2: SDG CH1 is on CLK IN and SDG CH2 on ADC A IN (not harmless: their voltage limits differ)",
    "no_gen_b":      "visit 2: the 33220A's cable is not on the board",
    "no_scope_clk":  "visit 2: nothing on scope CH3",
    "scope_10x":     "visit 2: a 10x probe instead of a BNC cable on scope CH1",
}

# The simulated supply's load line: the estimates of BRINGUP.md stage 1.2, (volts, amps) with the FPGA unconfigured
BOARD_LOAD = [(0.0, 0.0), (1.0, 0.02), (2.5, 0.12), (4.0, 0.30), (5.0, 0.45), (5.5, 0.47)]
RUNNING_EXTRA_A = 0.15       # more with the FPGA configured and the converters clocked (a guess: nobody has measured it)
USB_PROG_EXTRA_A = 0.02      # more again with USB PROG on a host: the FT2232H awake
SHORT_OHMS = 0.1             # what the "short" fault puts across the supply

# The nine rails as a healthy simulated board has them, in the order of the RAILS header J602
RAIL_VOLTS = [("+5V", 4.712), ("+3V3", 3.332), ("+1V1", 1.101), ("+2V5", 2.503), ("+3V3_ADC", 3.301),
              ("+3V3_DAC", 3.297), ("+5VA", 4.705), ("+1V0_PHY", 1.004), ("-4V2", -4.152)]

CODES_PER_VOLT = 2048.0      # ADC codes per volt at the SMA at gain x1: +-1 V is the 4096 codes of full scale (BRINGUP.md stage 6)
DAC_OPEN_VOLTS_PER_CODE = 2.0 / 8192     # DAC OUT open circuit: code 8192 is 0 V, 16383 is +2 V, 0 is -2 V (BRINGUP.md stage 5)
CLK_OUT_HIGH = 3.3           # CLK OUT open circuit: a 3.3 V output behind 49.9 ohm
SOURCE_OHMS = 50.0           # every source on this bench: the generators, DAC OUT, CLK OUT
CLKIN_MIN_VPP = 0.02         # the CLK IN comparator (TLV3501, 6 mV of hysteresis) counts anything above about this
NOISE_10K_CODES_PEAK = 0.13  # 10 kohm's Johnson noise in ADC codes at x1: 12.9 nV/rtHz x sqrt(12 MHz) = 45 uV rms = 0.09 codes rms,
                             # stood in for by a sine of that rms (0.13 peak); the simulator multiplies it by the gain
NOISE_STANDIN_HZ = 1.37e6    # that sine's frequency: any that is not a simple fraction of the sample rate


def tiny_png(width=32, height=24):
    """A small valid PNG (a dark rectangle), for the fake scope's screenshot."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    line = b"\x00" + bytes([20, 24, 40]) * width
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(line * height)) + chunk(b"IEND", b""))


class SimBench:
    """The simulated board, what is plugged into it, and the fake instruments."""

    def __init__(self, preset="selftest", faults=(), psu_out=1):
        if preset not in PRESETS:
            raise ValueError("preset %r: one of %s" % (preset, sorted(PRESETS)))
        self.preset_name = preset
        self.clock = 0.0                         # bench seconds since this command began
        self.rng = random.Random(20261115)       # seeded: two runs of a command read the same numbers
        self._board = None
        self.sent = {}                           # the knob values the simulator has now
        # the board's own inputs: what each one is cabled to (None = nothing)
        #   adc_a, adc_b: 'dac1', 'dac2', 'sdg1', 'sdg2', 'hp';  clk_in: 'clk_out', 'sdg1', 'sdg2', 'hp'
        #   scope1..4: 'dac1', 'dac2', 'clk_out', 'tap_a', 'tap_b', 'tap_tia', 'tap_n4v2', 'rail_3v3', 'rail_1v1', 'dac_clk'
        self.wiring = {"adc_a": None, "adc_b": None, "clk_in": None, "scope1": None, "scope2": None, "scope3": None, "scope4": None}
        # gain: 1, 10, 100.  term: the 50 ohm shunt in.  alt: None = SRC jumper on SMA, else 'noise_0', 'noise_10k', 'photodiode'
        self.jumpers = {"gain_a": 1, "gain_b": 1, "term_a": True, "term_b": True, "alt_a": None, "alt_b": None,
                        "led": False}            # led: JP2009 on the on-board LED
        self.plugged = {"sd": 0, "usb": 0, "link": 0, "monitor": 0, "pmod_loop": 0, "btn0": 0, "btn1": 0}
        self.usb_prog = False                    # USB PROG on the PC
        self.boots_from_flash = False            # a power cycle leaves the FPGA configured
        self.fpga_configured = False
        self.psu = FakePSU(self, board_out=psu_out)
        self.dmm = FakeDMM(self)
        self.scope = FakeScope(self)
        self.gen = FakeGen(self)
        self.hpgen = FakeGen2(self)
        self._preset(preset)
        self.faults = []
        for name in faults:
            self.inject(name)

    # ---- what was cabled -------------------------------------------------------------------------------------
    def _preset(self, name):
        if name == "power":
            return
        self.psu.sim_start_on(5.0, 1.0)
        if name == "power_on":
            return
        self.plugged.update(sd=1, usb=1, link=1)
        self.usb_prog = True
        self.boots_from_flash = True
        self.fpga_configured = True
        if name in ("selftest", "coldboot"):
            self.wiring.update(adc_a="dac1", adc_b="dac2", clk_in="clk_out")
        if name == "coldboot":
            self.usb_prog = False
            self.plugged["usb"] = 0
        if name == "instruments":
            self.wiring.update(adc_a="sdg1", adc_b="hp", clk_in="sdg2", scope1="dac1", scope2="dac2", scope3="clk_out")

    def inject(self, name):
        """Make one thing wrong (a key of FAULTS)."""
        if name not in FAULTS:
            raise ValueError("--sim-fault %r: one of %s" % (name, ", ".join(sorted(FAULTS))))
        self.faults.append(name)
        w = self.wiring
        if name == "short":
            self.psu.short = True
        elif name == "overcurrent":
            self.psu.extra_amps = 0.40
        elif name in ("rail_low", "rail_skipped", "rail_twice"):
            self.dmm.script_fault = name
        elif name == "crossed":
            w["adc_a"], w["adc_b"] = w["adc_b"], w["adc_a"]
        elif name == "no_sma_a":
            w["adc_a"] = None
        elif name == "no_clk_cable":
            w["clk_in"] = None
        elif name == "no_card":
            self.plugged["sd"] = 0
        elif name == "no_usb":
            self.plugged["usb"] = 0
        elif name == "no_link":
            self.plugged["link"] = 0
        elif name == "gain_a_x10":
            self.jumpers["gain_a"] = 10
        elif name == "term_b_open":
            self.jumpers["term_b"] = False
        elif name == "monitor":
            self.plugged["monitor"] = 1
        elif name == "pmod_loop":
            self.plugged["pmod_loop"] = 1
        elif name == "no_flash_boot":
            self.boots_from_flash = False
        elif name == "gens_swapped":
            w["adc_a"], w["adc_b"] = w["adc_b"], w["adc_a"]
        elif name == "scope_swapped":
            w["scope1"], w["scope2"] = w["scope2"], w["scope1"]
        elif name == "sdg_swapped":
            w["adc_a"], w["clk_in"] = "sdg2", "sdg1"
        elif name == "no_gen_b":
            for k in ("adc_a", "adc_b"):
                if w[k] == "hp":
                    w[k] = None
        elif name == "no_scope_clk":
            w["scope3"] = None
        elif name == "scope_10x":
            self.scope.real_attenuation[1] = 10.0

    def set_for_step(self, step):
        """Move on the simulated bench what the person moves before `bench.py step NAME` (visit 3)."""
        j, w = self.jumpers, self.wiring
        if step == "buttons":
            self.plugged.update(btn0=1, btn1=1)
        elif step == "gain_x10":
            j.update(gain_a=10, gain_b=10)
        elif step == "gain_x100":
            j.update(gain_a=100, gain_b=100)
        elif step == "term_open":
            j["term_a"] = False
        elif step == "noise_0":
            j.update(gain_a=100, alt_a="noise_0")
        elif step == "noise_10k":
            j.update(gain_a=100, alt_a="noise_10k")
        elif step == "light":
            j.update(led=True, alt_b="photodiode")
        elif step in ("tap", "tap_a"):
            w["scope4"] = "tap_a"
        elif step == "tap_b":
            w["scope4"] = "tap_b"
        elif step == "tap_tia":
            w["scope4"] = "tap_tia"
            j.update(led=True, alt_b="photodiode")
        elif step == "tap_n4v2":
            w["scope4"] = "tap_n4v2"
        elif step == "poweron":
            w.update(scope1="rail_3v3", scope2="rail_1v1")
            self.scope.real_attenuation[1] = self.scope.real_attenuation[2] = 10.0      # the two 10x probes
            self.usb_prog = False
            self.plugged["usb"] = 0
        elif step == "dac_clock":
            w["scope1"] = "dac_clk"
            self.scope.real_attenuation[1] = 10.0
        elif step == "hdmi":
            self.plugged["monitor"] = 1
        elif step == "pmod":
            self.plugged["pmod_loop"] = 1
        self.apply()

    # ---- the simulated board ---------------------------------------------------------------------------------
    @property
    def board(self):
        if self._board is None:
            import cosim
            knobs = self.knobs()
            self._board = cosim.SimBoard(**knobs)
            self.sent = dict(knobs)
            self.fpga_configured = True
        return self._board

    def knobs(self):
        """The simulator's knobs (cosim.KNOBS) as wiring, jumpers, plugged and the generators stand now."""
        k = dict(self.plugged)
        for ch in ("a", "b"):
            src, hz, codes = self._adc_source(ch)
            k["src_" + ch] = src
            k["gain_" + ch] = self.jumpers["gain_" + ch]
            k["term_" + ch] = 1 if self.jumpers["term_" + ch] else 0
            k["gen_hz_" + ch] = hz
            k["gen_codes_" + ch] = codes
        k["clkin"], k["clkin_hz"] = self._clkin_source()
        return k

    def apply(self):
        """Send the simulator whatever knob has changed.  Before the board is started this does nothing: it
        starts with the knobs as they are then."""
        if self._board is None:
            return
        want = self.knobs()
        changed = {name: v for name, v in want.items() if self.sent.get(name) != v}
        if changed:
            self._board.world(**changed)
            self.sent.update(changed)

    def _adc_source(self, ch):
        """(src, gen_hz, gen_codes) for one ADC channel: src 0 nothing, 1 DAC 1, 2 DAC 2, 3 a sine of gen_codes
        peak (ADC codes at gain x1).  The simulator applies the gain; for the DACs it also applies the TERM
        shunt (out: twice), for a generator this function does."""
        hz, codes = self.sent.get("gen_hz_" + ch, 100e3), self.sent.get("gen_codes_" + ch, 0.0)
        alt = self.jumpers["alt_" + ch]
        if alt == "noise_0":
            return 0, hz, codes
        if alt == "noise_10k":
            return 3, NOISE_STANDIN_HZ, NOISE_10K_CODES_PEAK
        if alt == "photodiode":                  # the LED driven by DAC 1, seen by the photodiode: the reading follows DAC 1
            return (1 if self.jumpers["led"] else 0), hz, codes
        wired = self.wiring["adc_" + ch]
        if wired == "dac1":
            return 1, hz, codes
        if wired == "dac2":
            return 2, hz, codes
        if wired in ("sdg1", "sdg2", "hp"):
            sig = self.generator_signal(wired)
            if sig is not None and sig["kind"] == "SINE":
                at_sma = sig["open_vpp"] * (0.5 if self.jumpers["term_" + ch] else 1.0)     # 50 ohm source into the 50 ohm shunt: half
                return 3, sig["freq"], 0.5 * at_sma * CODES_PER_VOLT
        return 0, hz, codes

    def _clkin_source(self):
        """(clkin, clkin_hz): 0 nothing, 1 the cable from CLK OUT, 2 a generator at clkin_hz."""
        hz = self.sent.get("clkin_hz", 10e6)
        wired = self.wiring["clk_in"]
        if wired == "clk_out":
            return 1, hz
        if wired in ("sdg1", "sdg2", "hp"):
            sig = self.generator_signal(wired)
            if sig is not None and sig["kind"] in ("SINE", "SQUARE") and 0.5 * sig["open_vpp"] >= CLKIN_MIN_VPP:   # JP3001 in: half
                return 2, sig["freq"]
        return 0, hz

    def generator_signal(self, name):
        """What generator output 'sdg1', 'sdg2' or 'hp' puts out now: None when it is off, else
        {'kind': 'SINE'|'SQUARE'|'DC', 'freq', 'open_vpp', 'open_offset'} (open-circuit volts)."""
        if name == "hp":
            return self.hpgen.sim_signal()
        return self.gen.sim_signal(int(name[-1]))

    def adc_input(self, ch):
        """What ADC channel 'a' or 'b' has at its TAP (the preamp's output), for the scope: (vpp, freq)."""
        wired = self.wiring["adc_" + ch]
        if self.jumpers["alt_" + ch] is None and wired in ("sdg1", "sdg2", "hp"):
            sig = self.generator_signal(wired)
            if sig is not None and sig["kind"] == "SINE":
                at_sma = sig["open_vpp"] * (0.5 if self.jumpers["term_" + ch] else 1.0)
                return min(at_sma * self.jumpers["gain_" + ch], 8.0), sig["freq"]       # the OPA1612 stops at its +-4 V rails
        return 0.0, None

    def advance(self, seconds):
        """`seconds` of bench time pass: the clock moves on, and the simulated board, if it has been started,
        runs seconds / 1000 of its own time (cosim shortens every wait a thousand times)."""
        self.clock += seconds
        if self._board is not None:
            self._board.wait(seconds)

    def power_cycled(self):
        """The supply's output went from off to on."""
        self.fpga_configured = self.boots_from_flash
        self.scope.sim_event("power_on")

    def close(self):
        if self._board is not None:
            self._board.close()                      # ends the simulator; cosim removes its pipes and its log after a clean end
            self._board = None


# ---- the supply --------------------------------------------------------------------------------------------------
class FakePSU:
    """An Agilent E3646A (two outputs, one switch) as bench.py uses agilent_E36xxA.AgilentE36xxA.  The board
    hangs on output `board_out`; the other output has nothing on it."""
    idn = "Agilent Technologies,E3646A,0,1.7-5.0-1.0 (simulated)"
    model = "E3646A"
    outputs = 2
    ranges = ("P8V", "P20V")
    RANGE_MAX = {"P8V": (8.24, 3.09), "P20V": (20.6, 1.545)}     # the most each range takes (User's Guide: 3 % over the rating)

    def __init__(self, sim, board_out=1):
        self.sim = sim
        self.board_out = board_out
        self.short = False
        self.extra_amps = 0.0
        self._on = False
        self._off_at = None                      # when the output was switched off, and from what voltage
        self._off_from = 0.0
        self._s = {n: {"volts": 0.0, "amps": 3.0, "range": "P8V", "ovp": 8.8, "ovp_on": True, "ovp_tripped": False} for n in (1, 2)}

    def sim_start_on(self, volts, amps):
        """The state a visit begins in when `v1a` has run before it: 5.0 V on."""
        self._s[self.board_out].update(volts=volts, amps=amps, ovp=5.6)
        self._on = True

    def _check_out(self, out):
        if out not in (1, 2):
            raise ValueError("E3646A has output(s) 1..2, not %r" % out)

    def set_range(self, rng, out=1):
        self._check_out(out)
        name = {"LOW": "P8V", "HIGH": "P20V"}.get(rng.upper(), rng.upper())
        if name not in self.ranges:
            raise ValueError("E3646A ranges are %s (or LOW, HIGH)" % (self.ranges,))
        self._s[out]["range"] = name
        return self.setting(out)

    def set_ovp(self, volts=None, on=True, out=1):
        self._check_out(out)
        if volts is not None:
            self._s[out]["ovp"] = float(volts)
        self._s[out]["ovp_on"] = bool(on)
        return self.setting(out)

    def set(self, volts, amps, out=1):
        self._check_out(out)
        vmax, amax = self.RANGE_MAX[self._s[out]["range"]]
        if not (0 <= volts <= vmax and 0 <= amps <= amax):
            raise ValueError("E3646A: asked for %s V, %s A on output %d, outside its range %s" % (volts, amps, out, self._s[out]["range"]))
        self._s[out].update(volts=float(volts), amps=float(amps))
        if self._s[out]["ovp_on"] and volts > self._s[out]["ovp"]:
            self._s[out]["ovp_tripped"] = True
        return self.setting(out)

    def setting(self, out=1):
        self._check_out(out)
        return dict(self._s[out], output=self._on)

    def output(self, on=None):
        if on is None:
            return self._on
        was = self._on
        if was and not on:
            self._off_at = self.sim.clock
            self._off_from = self._s[self.board_out]["volts"]
        self._on = bool(on)
        self.sim.clock += 0.3
        if on and not was:
            self.sim.power_cycled()
        return self._on

    def _load_amps(self, volts):
        """What the board draws at `volts` on J601."""
        if self.short:
            return volts / SHORT_OHMS
        amps = BOARD_LOAD[-1][1]
        for (v0, i0), (v1, i1) in zip(BOARD_LOAD, BOARD_LOAD[1:]):
            if volts <= v1:
                amps = i0 + (i1 - i0) * (volts - v0) / (v1 - v0)
                break
        if volts >= 4.5:
            amps += self.extra_amps
            if self.sim.fpga_configured:
                amps += RUNNING_EXTRA_A + (USB_PROG_EXTRA_A if self.sim.usb_prog else 0.0)
        return amps

    def _operating_point(self, out):
        """(volts, amps, mode) at one output now."""
        s = self._s[out]
        if not self._on or s["ovp_tripped"]:
            volts = 0.0
            if out == self.board_out and self._off_at is not None:
                volts = self._off_from * math.exp(-(self.sim.clock - self._off_at) / 0.25)      # the board's capacitors run down in a fraction of a second
            return volts, 0.0, "OFF"
        if out != self.board_out:
            return s["volts"], 0.0, "CV"
        want = self._load_amps(s["volts"])
        if want <= s["amps"]:
            return s["volts"], want, "CV"
        volts = s["volts"]                       # current limited: the voltage sinks to where the load takes the limit
        for _ in range(40):
            volts *= 0.5 if self._load_amps(volts * 0.5) >= s["amps"] else 0.9
            if self._load_amps(volts) <= s["amps"]:
                break
        return volts, s["amps"], "CC"

    def measure(self, out=1):
        self._check_out(out)
        self.sim.clock += 0.26                   # MEASure takes about 130 ms per quantity (the driver's notes)
        volts, amps, _ = self._operating_point(out)
        return volts + self.sim.rng.gauss(0, 0.0005), max(0.0, amps + (self.sim.rng.gauss(0, 0.0005) if amps else 0.0))

    def mode(self, out=1):
        self._check_out(out)
        return self._operating_point(out)[2]

    def status(self):
        s = {"idn": self.idn}
        for n in (1, 2):
            s["out%d" % n] = self.setting(n)
            s["out%d measured" % n] = self.measure(n)
            s["out%d mode" % n] = self.mode(n)
        s["errors"] = []
        return s

    def close(self):
        pass


# ---- the multimeter ------------------------------------------------------------------------------------------------
class FakeDMM:
    """A Fluke 45 as bench.py uses fluke_45.Fluke45.  read() plays a person walking the red probe along the
    RAILS header: lifted (millivolts), a reading or two caught mid-touch, eight steady readings on the rail,
    lifted again; nine rails in the header's order, then lifted for good.  With the supply off every reading
    is "lifted"."""
    idn = "FLUKE, 45, 9166018, 1.7 D3.0 (simulated)"
    READ_SECONDS = 0.2                           # one reading at the medium rate: 5 a second

    def __init__(self, sim):
        self.sim = sim
        self.script_fault = None                 # 'rail_low', 'rail_skipped', 'rail_twice'
        self._script = None
        self._settings = {"function": "VDC", "auto": True, "range": 3, "rate": "M"}

    def _lifted(self):
        return round(self.sim.rng.gauss(0.0, 0.003), 3)

    def _make_script(self):
        rng = self.sim.rng
        readings = [self._lifted() for _ in range(12)]                    # 2.4 s before the first touch
        for name, volts in RAIL_VOLTS:
            if self.script_fault == "rail_skipped" and name == "+2V5":
                continue
            if self.script_fault == "rail_low" and name == "+3V3_ADC":
                volts = 3.05
            for _ in range(2 if (self.script_fault == "rail_twice" and name == "+1V1") else 1):
                readings += [round(volts * rng.uniform(0.2, 0.9), 3) for _ in range(rng.choice([1, 2]))]     # caught mid-touch
                readings += [round(volts + rng.gauss(0, 0.0006), 3) for _ in range(8)]                     # 1 mV steps on the 30 V range
                readings += [round(volts * rng.uniform(0.05, 0.6), 3) for _ in range(rng.choice([0, 1]))]    # caught lifting
                readings += [self._lifted() for _ in range(rng.randint(3, 5))]
        return readings

    def function(self, name, auto=True):
        self._settings.update(function=name.upper(), auto=bool(auto))
        return dict(self._settings)

    def set_range(self, n):
        auto = str(n).upper() == "AUTO"
        self._settings.update(auto=auto)
        if not auto:
            self._settings["range"] = int(n)
        return dict(self._settings)

    def rate(self, speed):
        self._settings["rate"] = speed.upper()
        return dict(self._settings)

    def read(self, settle=0):
        value = 0.0
        for _ in range(settle + 1):
            self.sim.clock += self.READ_SECONDS
            if self._script is None:
                self._script = self._make_script()
            if not self.sim.psu.output() or not self._script:
                value = self._lifted()
            else:
                value = self._script.pop(0)
        return value

    def ask(self, cmd):
        return self.idn if cmd.strip().upper() == "*IDN?" else ""

    def close(self):
        pass


# ---- the oscilloscope ------------------------------------------------------------------------------------------------
class FakeScope:
    """A Siglent SDS2104X Plus as bench.py uses siglent_SDS2104X.SDS2104X.  What a channel shows is worked
    out from the simulated board's registers (the DAC modes and codes, the CLK OUT selection) and from what
    SimBench.wiring says that channel is cabled to.  It starts as the shared bench leaves it: 10x probes set
    on all four channels, 2 V/div; a tool that forgets to set the probe factor for a BNC cable reads ten
    times too much here, as it would on the bench."""
    idn = "Siglent Technologies,SDS2104X Plus,SIMULATED,5.0.1.3.9R12"
    SCREEN_HALF_DIVS = 4.2                       # the converter clips 4.2 divisions either side of the centre (the driver's notes)

    def __init__(self, sim):
        self.sim = sim
        self.ch = {n: {"on": n != 4, "scale": 2.0, "offset": 0.0, "coupling": "DC", "impedance": "ONEMeg", "probe": 10.0,
                       "bwlimit": "FULL"} for n in (1, 2, 3, 4)}
        self.real_attenuation = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}         # what is really on the BNC: a cable (1) or a 10x probe
        self._tb = {"scale": 1e-3, "delay": 0.0}
        self._trig = {"source": "C1", "level": 0.0, "slope": "RISing", "mode": "AUTO", "coupling": "DC"}
        self._status = "Auto"
        self._armed = False
        self.shots = []

    # -- settings: the same arguments, and the same answers, as the real driver --
    def channel(self, ch, on=None, scale=None, offset=None, coupling=None, impedance=None, probe=None, bwlimit=None):
        c = self.ch[ch]
        if probe is not None:
            c["scale"] *= float(probe) / c["probe"]          # the scope keeps the volts per division at its BNC
            c["probe"] = float(probe)
        if on is not None:
            c["on"] = bool(on)
        if impedance is not None:
            c["impedance"] = "FIFTy" if str(impedance) == "50" else "ONEMeg"     # the driver's own rule: anything but '50' is 1 Mohm
        if coupling is not None:
            c["coupling"] = str(coupling)
        if bwlimit is not None:
            c["bwlimit"] = str(bwlimit)
        if scale is not None:
            c["scale"] = float(scale)
        if offset is not None:
            c["offset"] = float(offset)
        self.sim.clock += 0.05
        return dict(c)

    def timebase(self, scale=None, delay=None):
        if scale is not None:
            self._tb["scale"] = float(scale)
        if delay is not None:
            self._tb["delay"] = float(delay)
        self.sim.clock += 0.1
        return self._tb["scale"], self._tb["delay"]

    def trigger(self, source=None, level=None, slope=None, mode=None, coupling=None):
        if source is not None:
            self._trig["source"] = "C%d" % source if isinstance(source, int) else source
        if slope is not None:
            self._trig["slope"] = {"rising": "RISing", "falling": "FALLing", "alternate": "ALTernate"}[slope]
        if level is not None:
            self._trig["level"] = float(level)
        if coupling is not None:
            self._trig["coupling"] = coupling
        if mode is not None:
            self._trig["mode"] = {"auto": "AUTO", "normal": "NORMal", "single": "SINGle"}[mode]
            self._status = {"AUTO": "Auto", "NORMal": "Ready", "SINGle": "Ready"}[self._trig["mode"]]
        return {"source": self._trig["source"], "level": self._trig["level"], "slope": self._trig["slope"],
                "mode": self._trig["mode"], "status": self._status}

    def acquire(self, mdepth=None, mode=None, average=None, eres=None, resolution=None):
        if mdepth is not None:
            self._mdepth = str(mdepth)
        return {"mdepth": getattr(self, "_mdepth", "10k"), "type": "NORMal", "resolution": "8Bits",
                "sample_rate": 1000 / (10 * self._tb["scale"]), "points": 1000.0}     # waveform() below gives 1000 points

    def acquire_now(self, timeout=10.0):
        self._trig["mode"] = "FTRIG"
        self._status = "FStop"
        self.sim.clock += 0.1

    def arm(self):
        self._trig["mode"] = "SINGle"
        self._status = "Ready"
        self._armed = True
        self.sim.clock += 0.08
        source = int(self._trig["source"][1]) if self._trig["source"][1:].isdigit() else 1
        sig = self._signal(source)
        if sig["freq"] and abs(self._trig["level"] - sig["mean"]) < 0.5 * sig["pkpk"]:     # a running signal crosses the level by itself
            self.sim_event("signal")

    def sim_event(self, what):
        """Something happened on the bench that a waiting trigger sees (the supply switching on)."""
        if self._armed:
            self._armed = False
            self._status = "Stop"

    def wait_stop(self, timeout=10.0):
        if self._status.endswith("Stop"):
            return self._status
        self.sim.clock += timeout
        raise TimeoutError("no trigger within %s s (status %r)" % (timeout, self._status))

    def single(self, timeout=10.0):
        self.arm()
        return self.wait_stop(timeout)

    # -- what is on each BNC --
    def _signal(self, ch):
        """What channel `ch`'s BNC carries, in true volts into 1 Mohm: {'mean', 'pkpk', 'freq' (None = DC),
        'ohms' (the source's resistance: a 50 ohm input halves a 50 ohm source), 'kind'}."""
        flat = {"mean": 0.0, "pkpk": 0.0, "freq": None, "ohms": None, "kind": "nothing"}
        wired = self.sim.wiring.get("scope%d" % ch)
        if wired is None:
            return flat
        if wired in ("dac1", "dac2"):
            return self._dac_signal(1 if wired == "dac1" else 2)
        if wired == "clk_out":
            return self._clkout_signal()
        if wired in ("tap_a", "tap_b"):
            vpp, freq = self.sim.adc_input(wired[-1])
            return {"mean": 0.0, "pkpk": vpp, "freq": freq, "ohms": SOURCE_OHMS, "kind": "tap"}
        if wired == "tap_tia":                   # the photodiode receiver: it follows DAC 1 when the LED jumper is on
            dac = self._dac_signal(1)
            lit = self.sim.jumpers["led"]
            return {"mean": (0.2 + 0.4 * (dac["mean"] + 2.0)) if lit else 0.2, "pkpk": 0.0, "freq": None, "ohms": SOURCE_OHMS, "kind": "tap"}
        if wired == "tap_n4v2":                  # the LM27761's 2 MHz residue on -4.15 V: a few millivolts (BRINGUP.md 1.6)
            return {"mean": -4.15, "pkpk": 0.004, "freq": 2.0e6, "ohms": None, "kind": "tap"}
        if wired == "dac_clk":                   # the DAC clock at the DAC: a 3.3 V edge with 6 % of overshoot
            rate = self.sim.board.dac_rate()
            return {"mean": 1.65, "pkpk": 3.7, "freq": rate, "ohms": None, "kind": "clock", "max": 3.5, "min": -0.2}
        if wired in ("rail_3v3", "rail_1v1"):
            level = (3.33 if wired == "rail_3v3" else 1.10) if self.sim.psu.output() else 0.0
            return {"mean": level, "pkpk": 0.0, "freq": None, "ohms": None, "kind": "rail"}
        return flat

    def _dac_signal(self, port):
        import ecp5bu
        bd = self.sim.board
        base = ecp5bu.REGS["DAC1_CTRL" if port == 1 else "DAC2_CTRL"]
        ctrl, inc, dc = bd.rd(base), bd.rd(base + 1), bd.rd(base + 2) & 0xFFFF
        asleep = bool(bd.rd("GPIO") >> ecp5bu.G_DAC_SLEEP & 1)
        mode, shift = ctrl & 7, ctrl >> 4 & 15
        if asleep:
            return {"mean": 0.0, "pkpk": 0.0, "freq": None, "ohms": SOURCE_OHMS, "kind": "dac asleep"}
        if mode == 0:
            code = min(max(dc, 0), 16383)
            return {"mean": (code - 8192) * DAC_OPEN_VOLTS_PER_CODE, "pkpk": 0.0, "freq": None, "ohms": SOURCE_OHMS, "kind": "dc"}
        offset = dc - 0x10000 if dc >= 0x8000 else dc                     # signed codes added to the waveform
        amplitude = (8191 >> shift) if mode in (1, 3) else 8192           # sine and square scale with shift; sawtooth and triangle are full scale
        return {"mean": offset * DAC_OPEN_VOLTS_PER_CODE, "pkpk": 2 * amplitude * DAC_OPEN_VOLTS_PER_CODE,
                "freq": inc / 2.0 ** 32 * bd.dac_rate(), "ohms": SOURCE_OHMS, "kind": "wave"}

    def _clkout_signal(self):
        import ecp5bu
        bd = self.sim.board
        sel = bd.rd("CLKOUT") & 15
        enabled = bool(bd.rd("CONTROL") & 2)
        dc = {"pkpk": 0.0, "freq": None, "ohms": SOURCE_OHMS, "kind": "dc"}
        if not enabled or sel == ecp5bu.CLKOUT["low"]:
            return dict(dc, mean=0.0)
        if sel in (ecp5bu.CLKOUT["high"], ecp5bu.CLKOUT["pll_lock"], ecp5bu.CLKOUT["1hz"]):
            return dict(dc, mean=CLK_OUT_HIGH)
        freq = {0: 25e6, 1: 50e6, 2: bd.adc_rate(), 3: bd.dac_rate(), 4: self.sim.sent.get("clkin_hz", 0.0) if self.sim.sent.get("clkin") == 2 else 0.0,
                5: 10e6, 6: 25e6, 7: 100e6, 8: 125e6, 12: 12.5e6}.get(sel, 0.0)
        if sel in (5, 6, 7) and bd.rd(ecp5bu.REGS["F_SI0"] + sel - 5) == 0:       # that Si5351 output is not running
            freq = 0.0
        if not freq:
            return dict(dc, mean=0.0)
        return {"mean": 0.5 * CLK_OUT_HIGH, "pkpk": CLK_OUT_HIGH, "freq": freq, "ohms": SOURCE_OHMS, "kind": "clock"}

    def _shown(self, ch):
        """What the screen shows of channel `ch`: (mean, top, bottom, freq), or None with the channel off."""
        c = self.ch[ch]
        if not c["on"]:
            return None
        sig = self._signal(ch)
        k = c["probe"] / self.real_attenuation[ch]                       # the scope multiplies what its BNC sees by the probe setting
        if c["impedance"] == "FIFTy" and sig["ohms"] == SOURCE_OHMS:
            k *= 0.5
        mean = sig["mean"] * k
        top = sig.get("max", sig["mean"] + 0.5 * sig["pkpk"]) * k
        bottom = sig.get("min", sig["mean"] - 0.5 * sig["pkpk"]) * k
        if c["coupling"] == "AC":
            mean, top, bottom = 0.0, top - mean, bottom - mean
        elif c["coupling"] == "GND":
            mean = top = bottom = 0.0
        centre, half = -c["offset"], self.SCREEN_HALF_DIVS * c["scale"]
        clip = lambda v: min(max(v, centre - half), centre + half)       # noqa: E731
        return clip(mean), clip(top), clip(bottom), sig["freq"]

    def pava(self, item, ch):
        shown = self._shown(ch)
        self.sim.clock += 0.02
        if shown is None:
            return None
        mean, top, bottom, freq = shown
        c = self.ch[ch]
        noise = 0.02 * c["scale"]                                        # an 8-bit converter: about half a code of 30 per division
        g = self.sim.rng.gauss
        item = item.upper()
        if item == "MEAN":
            return mean + g(0, noise / 5)
        if item == "MAX":
            return top + abs(g(0, noise))
        if item == "MIN":
            return bottom - abs(g(0, noise))
        if item == "PKPK":
            return (top - bottom) + 2 * abs(g(0, noise))
        if item == "FREQ":
            cycles_on_screen = (freq or 0.0) * 10 * self._tb["scale"]
            if not freq or (top - bottom) < 0.3 * c["scale"] or not 1.5 <= cycles_on_screen <= 5000:
                return None                                              # the scope answers '****'
            return freq * (1 + g(0, 2e-5))
        return None

    def measure(self, item, ch):
        self.sim.clock += 0.3
        return self.pava(item, ch)

    def waveform(self, ch, points=None, start=0, preamble=True):
        """The record on the screen as (t, volts, info), 1000 points across the ten divisions.  A rail (the
        power-on step) is drawn as the bucks' soft start, 0.8 ms from 0 V to its level, crossing the trigger
        level at t = 0; anything else as its mean plus a sine."""
        import numpy as np
        n = 1000
        tdiv, delay = self._tb["scale"], self._tb["delay"]
        t = delay - 5 * tdiv + np.arange(n) * (10 * tdiv / n)
        c = self.ch[ch]
        sig = self._signal(ch)
        k = c["probe"] / self.real_attenuation[ch]
        if sig["kind"] == "rail":
            soft_start = 0.8e-3                                          # the TLV62569's soft start (BRINGUP.md 1.5)
            begins = -soft_start * 1.0 / 3.33                            # +3V3 crosses the 1 V trigger level at t = 0
            volts = sig["mean"] * np.clip((t - begins) / soft_start, 0.0, 1.0) * k
        else:
            volts = (sig["mean"] + 0.5 * sig["pkpk"] * np.sin(2 * np.pi * (sig["freq"] or 0.0) * t)) * k
        volts = volts + np.array([self.sim.rng.gauss(0, 0.01 * c["scale"]) for _ in range(n)])
        volts = volts[start:start + points] if points is not None else volts[start:]
        t = t[start:start + len(volts)]
        info = {"points": len(volts), "total_points": n, "vdiv": c["scale"], "voffset": c["offset"], "bits": 8, "dt": 10 * tdiv / n,
                "sample_rate": n / (10 * tdiv), "delay": -delay, "tdiv": tdiv, "probe": c["probe"]}
        self.sim.clock += 0.3
        return t, volts, info

    def screenshot(self, path):
        png = tiny_png()
        with open(path, "wb") as f:
            f.write(png)
        self.shots.append(path)
        self.sim.clock += 0.5
        return len(png)

    def q(self, cmd):
        return self.idn if cmd.strip().upper() == "*IDN?" else ""

    def close(self):
        pass


# ---- the generators ------------------------------------------------------------------------------------------------
def open_circuit(volts, load):
    """A generator's number for its load setting, as open-circuit volts (its output is a source behind 50 ohm)."""
    if load in ("HZ", "INF") or (isinstance(load, (int, float)) and load > 1e30):
        return volts
    return volts * (float(load) + SOURCE_OHMS) / float(load)


class FakeGen:
    """A Siglent SDG1032X as bench.py uses siglent_SDG1032X.SDG1032X, the vlimit check included (the same
    rule as the driver's: a number is a peak either side of 0 V, open circuit; a dict gives each channel its
    own).  Switching an output on or off, or changing a wave that is on, moves the simulated bench.  It
    starts as the shared bench may leave it: channel 1 holding 3.3 V DC, off."""
    idn = "Siglent Technologies,SDG1032X,SIMULATED,1.01.01.30R1B2"
    MAX_SINE_HZ = 30e6                           # the SDG1032X's top frequency

    def __init__(self, sim, vlimit=None):
        self.sim = sim
        self.vlimit = vlimit
        self._wave = {1: {"type": "DC", "freq": 1000.0, "amp": 0.0, "offset": 3.3, "phase": 0.0},
                      2: {"type": "SINE", "freq": 1000.0, "amp": 4.0, "offset": 0.0, "phase": 0.0}}
        self._out = {1: {"on": False, "load": "HZ", "polarity": "NOR"}, 2: {"on": False, "load": "HZ", "polarity": "NOR"}}

    def wave(self, ch):
        return dict(self._wave[ch], raw={})

    def output_state(self, ch):
        return dict(self._out[ch])

    def status(self):
        out = {"idn": self.idn, "phase_mode": "MODE INDEPENDENT", "reference": "ROSC INT"}
        for ch in (1, 2):
            out["C%d" % ch] = dict(self._wave[ch], **self._out[ch])
        return out

    def output(self, ch, on=None, load=None):
        if load is not None:
            new = "HZ" if str(load).upper() == "HZ" else float(load)
            old = self._out[ch]["load"]
            w = self._wave[ch]                   # changing the load keeps the volts and restates the numbers (the driver's notes)
            w["amp"] = open_circuit(w["amp"], old) / open_circuit(1.0, new)
            w["offset"] = open_circuit(w["offset"], old) / open_circuit(1.0, new)
            self._out[ch]["load"] = new
        if on:
            self._check_limit(ch, {})
        if on is not None:
            self._out[ch]["on"] = bool(on)
        self.sim.clock += 0.15
        self.sim.apply()
        return self.output_state(ch)

    def _set(self, ch, kind, freq=None, amp=None, offset=None, phase=None):
        params = {"WVTP": kind}
        if amp is not None:
            params["AMP"] = amp
        if offset is not None:
            params["OFST"] = offset
        self._check_limit(ch, params)
        w = self._wave[ch]
        w["type"] = kind
        if freq is not None:
            w["freq"] = min(float(freq), self.MAX_SINE_HZ)       # the generator clips, and says nothing
        if amp is not None:
            w["amp"] = float(amp)
        if offset is not None:
            w["offset"] = float(offset)
        if phase is not None:
            w["phase"] = float(phase)
        self.sim.clock += 0.15
        self.sim.apply()
        return self.wave(ch)

    def sine(self, ch, freq, vpp, offset=0.0, phase=0.0):
        return self._set(ch, "SINE", freq, vpp, offset, phase)

    def square(self, ch, freq, vpp, offset=0.0, duty=50.0, phase=0.0):
        return self._set(ch, "SQUARE", freq, vpp, offset, phase)

    def dc(self, ch, volts):
        return self._set(ch, "DC", offset=volts)

    def _check_limit(self, ch, params):
        limit = self.vlimit
        if isinstance(limit, dict):
            if ch not in limit:
                raise ValueError("C%d: vlimit names channels %s only" % (ch, sorted(limit)))
            limit = limit[ch]
        if limit is None:
            return
        try:
            v_min, v_max = limit
        except TypeError:
            v_min, v_max = -limit, limit
        cur = self._wave[ch]
        load = self._out[ch]["load"]
        kind = params.get("WVTP", cur["type"])
        if kind != cur["type"] and kind != "DC" and "AMP" not in params:
            raise ValueError("C%d: give AMP with a new waveform type while vlimit is set" % ch)
        amp = float(params.get("AMP", cur.get("amp") or 0.0))
        off = float(params.get("OFST", cur.get("offset") or 0.0))
        if kind == "DC":
            amp = 0.0
        low, high = open_circuit(off - amp / 2, load), open_circuit(off + amp / 2, load)
        if low < v_min - 1e-9 or high > v_max + 1e-9:
            raise ValueError("C%d: %.2f V to %.2f V open circuit is outside vlimit (%g V to %g V)" % (ch, low, high, v_min, v_max))

    def sim_signal(self, ch):
        """For SimBench: what this output puts out now (None when off)."""
        if not self._out[ch]["on"]:
            return None
        w, load = self._wave[ch], self._out[ch]["load"]
        return {"kind": w["type"], "freq": w["freq"], "open_vpp": 0.0 if w["type"] == "DC" else open_circuit(w["amp"], load),
                "open_offset": open_circuit(w["offset"], load)}

    def close(self):
        pass


class FakeGen2:
    """An Agilent 33220A as bench.py uses agilent_33220A.Agilent33220A: one output, 20 MHz, no voltage limit of
    its own.  Like the real driver it raises ValueError for a setting the generator cannot make."""
    idn = "Agilent Technologies,33220A,SIMULATED,2.07-2.06-22-2"
    MAX_SINE_HZ = 20e6                           # a 20 MHz generator
    MIN_VPP_50, MAX_VPP_50 = 0.010, 10.0         # 10 mVpp to 10 Vpp into 50 ohm (User's Guide)

    def __init__(self, sim):
        self.sim = sim
        self._w = {"function": "SIN", "freq": 1000.0, "vpp": 0.1, "offset": 0.0, "output": False, "load": 50.0}

    def wave(self):
        return dict(self._w)

    def _set(self, function, freq, vpp, offset):
        if freq is not None and not 1e-6 <= freq <= self.MAX_SINE_HZ:
            raise ValueError("33220A: asked for %s %s Hz, got %s; errors ['-222,\"Data out of range\"']" % (function, freq, self.MAX_SINE_HZ))
        factor = 2.0 / open_circuit(1.0, self._w["load"])                 # the limits are for 50 ohm (factor 1); at high Z the numbers double
        if vpp is not None and not self.MIN_VPP_50 * factor - 1e-12 <= vpp <= self.MAX_VPP_50 * factor:
            raise ValueError("33220A: asked for %s Vpp, outside %g..%g; errors ['-222,\"Data out of range\"']"
                             % (vpp, self.MIN_VPP_50 * factor, self.MAX_VPP_50 * factor))
        self._w["function"] = function
        if freq is not None:
            self._w["freq"] = float(freq)
        if vpp is not None:
            self._w["vpp"] = float(vpp)
        self._w["offset"] = float(offset)
        self.sim.clock += 0.2
        self.sim.apply()
        return self.wave()

    def sine(self, freq, vpp, offset=0.0):
        return self._set("SIN", freq, vpp, offset)

    def square(self, freq, vpp, offset=0.0, duty=50.0):
        return dict(self._set("SQU", freq, vpp, offset), duty=float(duty))

    def dc(self, volts):
        return self._set("DC", None, None, volts)

    def output(self, on=None, load=None, sync=None):
        if load is not None:
            self._w["load"] = "INF" if str(load).upper().startswith("INF") else float(load)
        if on is not None:
            self._w["output"] = bool(on)
        self.sim.clock += 0.1
        self.sim.apply()
        return self.wave()

    def sim_signal(self):
        """For SimBench: what the output puts out now (None when off)."""
        if not self._w["output"]:
            return None
        w = self._w
        kind = {"SIN": "SINE", "SQU": "SQUARE", "DC": "DC"}.get(w["function"], w["function"])
        return {"kind": kind, "freq": w["freq"], "open_vpp": 0.0 if kind == "DC" else open_circuit(w["vpp"], w["load"]),
                "open_offset": open_circuit(w["offset"], w["load"])}

    def close(self):
        pass
