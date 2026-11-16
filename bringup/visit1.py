"""visit1.py: visit 1 of ../BRINGUP.md and the cold boot that opens visit 2, as bench.py's commands.

    v1a        visit 1, step A: the staircase, then 5.0 V left on                      (the supply only)
    rails      visit 1, step A: the Fluke walk along the RAILS header                  (the Fluke only; nothing is typed)
    v1b        visit 1, step B: what is plugged in, then every test the board can do on itself (an hour, alone)
    coldboot   visit 2, step 1: ten power cycles with both USB cables out              (the supply only)

Every test is a function that takes the Bench and returns rows (report.py); v1b's are listed in V1B_TESTS at
the end of this file, in the order they run.  Every number carries a comment saying where it comes from.
"""
import datetime as dt
import os
import re
import subprocess

import analysis
import bench
import ecp5bu
from report import Results, hz, row

OUT_OF_SIM = "skipped in simulation"


# =================================================================================================================
# v1a: the staircase, then 5.0 V on
# =================================================================================================================
# BRINGUP.md stage 1.2: what the board should draw at each step of the staircase.  They are estimates made
# before any board was powered, so a current outside them with the supply in constant voltage is "info", not FAIL.
STAIRCASE_EXPECT = {1.0: (0.0, 0.03), 2.5: (0.05, 0.20), 4.0: (0.20, 0.40), 5.0: (0.30, 0.60)}
MAX_AMPS_AT_5V = 0.7             # stage 1.2's pass condition: under 0.7 A at 5 V
READINGS_AGREE = 0.05            # three readings of the current must agree within 5 % (stage 1.4: "flat to 5 %")


def v1a(b, a):
    """Visit 1, step A.  Cabled: E3646A output 1 to J601 (+ to the pin printed +5V, - to GND); nothing else on the
    board.  The staircase (1.0, 2.5, 4.0, 5.0 V with low current limits, 2 s each), then 5.0 V at a 1.0 A limit
    and three current readings.  Passes: every step in constant voltage, the power (not the current) rising with the voltage,
    under 0.7 A at 5 V.  The output is never left on after a step that went into current limit."""
    b.stage = b.stage or "1.2"
    res = Results(b, "v1a")
    out = b.cfg["psu"]["out"]
    b.require_supply()
    print("v1a: the staircase on E3646A output %d (%s), 2 s a step." % (out, ", ".join("%.1f V" % v for v, _ in bench.STAIRCASE)))
    steps = b.psu_staircase(quiet=True)
    bad = False
    for s in steps:
        lo, hi = STAIRCASE_EXPECT[s["set_v"]]
        value = "%.3f A at %.2f V, %s" % (s["amps"], s["volts"], s["mode"])
        expected = "constant voltage, about %.2f-%.2f A" % (lo, hi)
        if s["mode"] == "CC":
            bad = True
            res.add(row("staircase", "%.1f V step" % s["set_v"], value, expected, "FAIL",
                        "the supply went into current limit: a short or a reversed part.  The output is OFF.  Do not power it again: "
                        "look at D601's cathode bar and Q602's pin 1 (BRINGUP.md 0.2 a, b); then `bench.py psu on --volts 1.0 --amps 0.3` "
                        "and the IR camera finds what is warm (stage 1.2)"))
        elif s["mode"] != "CV":
            bad = True
            res.add(row("staircase", "%.1f V step" % s["set_v"], value, expected, "FAIL",
                        "the supply says %s with its switch on: that is the supply, not the board (hp.md: the first E3646A's output 1 "
                        "does this).  The output is OFF.  Use the other unit, or output 2 with \"out\": 2 in bench_config.json" % s["mode"]))
        elif s["set_v"] == 5.0 and s["amps"] >= MAX_AMPS_AT_5V:
            bad = True
            res.add(row("staircase", "5.0 V step", value, "under %.1f A" % MAX_AMPS_AT_5V, "FAIL",
                        "more than the whole board should draw running (0.6-0.7 A), and the FPGA is not even configured.  The output is "
                        "OFF.  The IR camera at 4.0 V finds what is warm"))
        elif lo <= s["amps"] <= hi:
            res.add(row("staircase", "%.1f V step" % s["set_v"], value, expected, "pass"))
        else:
            res.add(row("staircase", "%.1f V step" % s["set_v"], value, expected, "info",
                        "constant voltage, so no short; the current is outside the estimate of stage 1.2 (made before any board was powered)"))
    if not bad and len(steps) == len(bench.STAIRCASE):
        # The power, not the current: once the bucks regulate they draw about constant power, so the input current
        # falls as the voltage rises (board A, 2026-11-16: 0.388 A at 4.0 V, 0.369 A at 5.0 V, 1.55 W then 1.85 W).
        # A power that drops is something letting go (a fuse, a regulator shutting down).
        watts = [s["amps"] * s["volts"] for s in steps]
        rising = all(later >= 0.9 * earlier for earlier, later in zip(watts, watts[1:]))
        res.add(row("staircase", "the power rises with the voltage", ", ".join("%.2f W" % w for w in watts),
                    "each step at least 90 % of the last", "pass" if rising else "FAIL",
                    "" if rising else "the power drawn fell as the voltage rose: something let go (F602, a regulator in shutdown).  "
                    "Read the steps again (`bench.py psu staircase`) before going on"))
        bad = not rising
    if bad:
        res.finish()
        print("\n5.0 V was NOT switched on.  The supply's output is OFF.")
        return 0

    # 5.0 V, 1.0 A limit, left on
    b.psu_setup(bench.SUPPLY_V, bench.SUPPLY_A)
    b.psu_output(True, quiet=True)
    b.sleep(1.0)
    readings = []
    for _ in range(3):
        volts, amps = b.psu.measure(out=out)
        mode = b.psu.mode(out=out)
        readings.append((volts, amps, mode))
        b.record("psu", quiet=True, label="v1a 5V", volts=volts, amps=amps, mode=mode)
        if mode != "CV":
            break
        b.sleep(1.0)
    if any(mode != "CV" for _, _, mode in readings):
        b.psu_output(False, quiet=True)
        volts, amps, mode = readings[-1]
        res.add(row("5 V on", "the supply at 5.0 V, 1.0 A limit", "%.3f A at %.2f V, %s" % (amps, volts, mode), "constant voltage", "FAIL",
                    "not in constant voltage at 5 V with the 1.0 A limit: the output is OFF again.  The staircase passed at 5 V a moment "
                    "ago, so something changed: run `v1a` once more and watch the first step"))
        res.finish()
        print("\nThe supply's output is OFF.")
        return 0
    volts = sum(r[0] for r in readings) / 3
    amps = sum(r[1] for r in readings) / 3
    spread = (max(r[1] for r in readings) - min(r[1] for r in readings)) / amps if amps > 0 else 0.0
    res.add(row("5 V on", "the voltage at the supply", "%.3f V" % volts, "4.95-5.05 V", "pass" if 4.95 <= volts <= 5.05 else "FAIL",
                "" if 4.95 <= volts <= 5.05 else "the supply is not giving what was set: `bench.py psu status`"))
    lo, hi = STAIRCASE_EXPECT[5.0]
    if amps >= MAX_AMPS_AT_5V:
        res.add(row("5 V on", "the current, FPGA unconfigured", "%.3f A" % amps, "under %.1f A (about %.2f-%.2f)" % (MAX_AMPS_AT_5V, lo, hi), "FAIL",
                    "more than the pass condition of stage 1.2: `bench.py psu off`, then the IR camera at 4.0 V"))
    else:
        res.add(row("5 V on", "the current, FPGA unconfigured", "%.3f A" % amps, "under %.1f A (about %.2f-%.2f)" % (MAX_AMPS_AT_5V, lo, hi), "pass",
                    "" if lo <= amps <= hi else "outside the estimate of stage 1.2, inside its pass condition"))
    res.add(row("5 V on", "three readings agree", "within %.1f %%" % (100 * spread), "within %.0f %%" % (100 * READINGS_AGREE),
                "pass" if spread <= READINGS_AGREE else "FAIL",
                "" if spread <= READINGS_AGREE else "the current is moving: `bench.py psu log --seconds 60` shows whether it climbs (a part heating)"))
    # The reference the cold-boot test compares with.  Once a bitstream is in the flash the board configures itself at
    # power-on and this reading is no longer "unconfigured": it is then logged under another name.
    flashed = b.log.latest("flash", written=True) is not None
    b.record("current_ref", quiet=True, state="flash_boot_no_usb" if flashed else "unconfigured", amps=amps, volts=volts)
    res.finish()
    print("\n5.0 V is ON at J601 and stays on (limit 1.0 A, over-voltage trip %.1f V).  Next for Jason: are the eight red POWER LEDs "
          "by the RAILS header all lit?  Then \"rails go\" and the Fluke walk (`bench.py rails`)." % bench.OVP_V)
    return 0


# =================================================================================================================
# rails: the Fluke walk
# =================================================================================================================
FLUKE_RANGE_30V = 3              # Fluke 45 range number for 30 V at the medium rate (its manual's table 5-13): 1 mV steps, no autorange delays
LIFTED_END_SECONDS = 20.0        # the walk is over when the probe has been in the air this long after at least one rail
SETTLED_READINGS = 5             # a plateau this long (1 s) is not going to change: the last rail need not be lifted off
RAIL_PINS = {name: 1 + 2 * i for i, name in enumerate(bench.RAILS)}      # J602: the rails on the odd pins, in order
RAIL_HINT = {                    # where to look when a rail is wrong: BRINGUP.md 1.3's table and the power paths above it
    "+5V":      "J601 through F602 and D601 (the SS34): the supply's 5.0 V less the diode's 0.3-0.5 V",
    "+3V3":     "the buck U601 (its inductor L617 on the back, its feedback divider 15k/3.3k)",
    "+1V1":     "the buck U602 (its inductor L618 on the back, its feedback divider 10k/12k)",
    "+2V5":     "the LDO U603, fed from +3V3",
    "+3V3_ADC": "the LDO U604, fed from +5V through 2.2 ohm",
    "+3V3_DAC": "the LDO U605, fed from +5V",
    "+5VA":     "+5V through a ferrite bead",
    "+1V0_PHY": "the PHY's own switcher (L401 on the back).  The PHY makes it once out of reset: if it reads 0 V with the FPGA "
                "unconfigured, read it again after bringup.bit is loaded (`bench.py dmm +1V0_PHY`)",
    "-4V2":     "the charge pump U606 (LM27761), fed from +5V",
}


def rails(b, a):
    """Visit 1, step A, the Fluke walk.  The person holds the black probe on the RAILS header's top row and
    touches the red probe to each pin of the bottom row, left to right, three seconds each, lifting clear between
    pins.  This reads the Fluke the whole time and takes each steady reading as the next rail.  Passes: nine
    rails, each inside its window (bench.RAILS).  Nothing is typed and nothing is asked."""
    b.stage = b.stage or "1.3"
    res = Results(b, "rails")
    if b.dmm is None:
        raise bench.Refused("No Fluke 45 is configured: put its /dev/serial/by-id path under \"dmm\": {\"serial\": ...} in bench_config.json "
                            "(`python3 %s/scpi_link.py identify` finds it), then \"rails go\" again." % bench.LIC)
    try:
        supply_on = b.psu.output()
    except Exception:                                 # noqa: BLE001: the walk does not need the supply's port
        supply_on = None
    if supply_on is False:
        raise bench.Refused("The supply's output is off, so there are no rails to read: `bench.py v1a` first (it leaves 5.0 V on), then \"rails go\" again.")
    b.dmm.function("VDC")
    b.dmm.set_range(FLUKE_RANGE_30V)
    b.dmm.rate("M")
    print("rails: reading the Fluke for up to %.0f s; a rail is %d readings in a row that agree.  Walk now." % (a.seconds, analysis.STEADY_N), flush=True)
    finder = analysis.PlateauFinder()
    t0 = b.now()
    n_readings = 0
    ended = "the time (--seconds %.0f) ran out" % a.seconds
    while b.now() - t0 < a.seconds:
        volts = b.dmm.read()
        t = b.now() - t0
        n_readings += 1
        finder.add(t, volts)
        plateaus = finder.plateaus()
        settled = finder.open_readings() == 0 or finder.open_readings() >= SETTLED_READINGS
        # -4V2 is the last pin and the only negative rail: once it has been read after most of the others, the walk is
        # over.  Not sooner: on board A (2026-11-16) the meter read a steady -2.507 V from the start, and a rule of "two
        # steady readings, the last negative" ended the walk after 9 s with nothing read.
        if len(plateaus) >= 7 and plateaus[-1]["volts"] < -analysis.MIN_RAIL_V and settled:
            ended = "the last pin (-4V2) was read"
            break
        if plateaus and finder.open_readings() == 0 and t - finder.last_touch_t >= LIFTED_END_SECONDS:
            ended = "the probe was lifted for %.0f s" % LIFTED_END_SECONDS
            break
    plateaus = finder.plateaus()
    for k, p in enumerate(plateaus):
        b.record("plateau", quiet=True, index=k, volts=p["volts"], readings=p["n"], t0=round(p["t0"], 1), t1=round(p["t1"], 1))
    print("rails: %d readings in %.0f s, %d steady; stopped because %s." % (n_readings, b.now() - t0, len(plateaus), ended))
    if not plateaus:
        res.add(row("rails", "steady readings", "none in %.0f s" % (b.now() - t0), "nine", "FAIL",
                    "the Fluke never held a level above %.1f V for %d readings.  Is the black probe on the header's top row (ground), the "
                    "supply on (the red LEDs), the Fluke's leads in its V and COM jacks?  Then \"rails go\" again" % (analysis.MIN_RAIL_V, analysis.STEADY_N)))
        res.finish()
        return 0

    rail_list = list(bench.RAILS.items())
    volts = [p["volts"] for p in plateaus]
    taken, extras = analysis.assign_rails(volts, rail_list)
    # a walk from the right end of the header reads the rails backwards: take it if it fits better that way
    taken_back, extras_back = analysis.assign_rails(volts[::-1], rail_list)
    if _misfits(taken_back, extras_back, volts[::-1], rail_list) < _misfits(taken, extras, volts, rail_list):
        volts, taken, extras = volts[::-1], taken_back, extras_back
        print("rails: the readings fit the header from right to left (-4V2 first): taken in that order.")
    n_ok = 0
    for i, (name, (lo, hi)) in enumerate(rail_list):
        window = "%.2f to %.2f V" % (lo, hi)
        what = "%s (pin %d)" % (name, RAIL_PINS[name])
        if taken[i] is None:
            twins = analysis.could_also_be(i, taken, volts, rail_list)
            which = name if not twins else "%s or %s (they read the same: the one reading could be either)" % (name, " or ".join(twins))
            led = bench.RAIL_LEDS.get(name)
            res.add(row("rails", what, "no steady reading", window, "FAIL",
                        "probably missing: %s.  Either the probe skipped its pin or the rail is near 0 V%s.  Probe that pin alone: "
                        "`bench.py dmm %s`.  If it is dead: %s" % (which, " (is its LED %s lit?)" % led if led else " (it has no LED)", name, RAIL_HINT[name])))
        else:
            v = volts[taken[i]]
            ok = lo <= v <= hi
            n_ok += ok
            res.add(row("rails", what, "%.3f V" % v, window, "pass" if ok else "FAIL",
                        "" if ok else "outside its window.  Read it once more (`bench.py dmm %s`); if it stays: %s" % (name, RAIL_HINT[name])))
    for j in extras:
        res.add(row("rails", "an extra steady reading", "%.3f V (reading %d of %d)" % (volts[j], j + 1, len(volts)), "", "info",
                    "it fits no rail in order: a pin touched twice, or a pin that is not a rail.  The nine rows above do not use it"))
    res.finish()
    if n_ok == len(rail_list):
        print("\n9 of 9 rails in their windows%s.  Next for Jason: touch the board for anything hot, then visit 1 step B (the USB and SMA cables)."
              % ("" if not extras else " (%d extra steady reading(s), not used: a pin touched twice)" % len(extras)))
    else:
        print("\n%d of 9 rails in their windows; %d steady readings were found%s.  Fix or re-probe the FAIL rows above before step B."
              % (n_ok, len(volts), "" if len(volts) == 9 else " (nine were expected)"))
    return 0


def _misfits(taken, extras, volts, rail_list):
    """How badly a lining-up fits: rails without a reading, readings without a rail, readings outside their window."""
    outside = sum(1 for i, j in enumerate(taken) if j is not None and not rail_list[i][1][0] <= volts[j] <= rail_list[i][1][1])
    return sum(1 for j in taken if j is None) + len(extras) + outside


# =================================================================================================================
# v1b: verify (what is plugged in), then the tests
# =================================================================================================================
VERIFY_STEP = 64                 # DAC codes either side of mid-scale for the cable check: a 16 mV step open circuit, 16 ADC codes at x1
VERIFY_STEP_ADC = VERIFY_STEP / 4.0      # ... because a full-scale DAC (16384 codes, +-1 V into 50 ohm) is the ADC's full scale (4096 codes)
CONNECTED_CODES = 6.0            # an ADC mean that moves less than this for the step is not on that DAC (the mean's own noise: 1/64 code)
PPM = 100e-6                     # frequency checks: within 100 ppm (the Si5351's crystal against the TCXO: BRINGUP.md 4.2 expects under 30)
SI_PLAN = ((0, 10e6), (1, 25e6), (2, 100e6))     # the Si5351's three outputs for the bring-up (BRINGUP.md 4.2)


class Found:
    """What `verify` found plugged into the board; the tests read it to know what they can run."""
    def __init__(self):
        self.board = False               # the board answers on USB PROG
        self.adc = {"a": {"source": None, "state": None, "inverted": False}, "b": {"source": None, "state": None, "inverted": False}}
        self.paths = []                  # (DAC port, ADC channel) pairs that are cabled and at gain x1 with the 50 ohm in
        self.clk_cable = False           # CLK OUT -> CLK IN
        self.card = False                # a microSD card
        self.usb_host = False            # USB USER on a host
        self.link = False                # an Ethernet link
        self.monitor = False             # a monitor on the HDMI jack
        self.pmod_loop = False           # Pmod A wired to Pmod B
        self.sdram_latency = None        # the read latency the sdram test chose

    def channel_note(self, ch):
        """Why ADC channel `ch` has no usable DAC path, in words."""
        info = self.adc[ch]
        if info["source"] is None:
            return "no DAC reaches ADC %s IN (verify)" % ch.upper()
        if info["source"] == "both":
            return "ADC %s IN answers to both DACs (verify)" % ch.upper()
        return "ADC %s is at %s; the self-test needs gain x1 with the 50 ohm in" % (ch.upper(), analysis.jumper_words(info["state"]))


def freq_tolerance(b, nominal):
    """How far a counted frequency may be from `nominal`: 100 ppm, plus one count of the counter."""
    return nominal * PPM + b.count_step_hz()


def dac_step_response(b):
    """Step each DAC by +-VERIFY_STEP codes round mid-scale, the other held at mid-scale, and see which ADC mean
    follows.  Returns {(channel, port): ADC codes per +VERIFY_STEP, ...} and {(channel, port): True if the ADC hit
    a rail}."""
    bd = b.bd
    b.analog_setup()
    response, clipped = {}, {}
    for port in (1, 2):
        bd.dac(port, "dc", code=8192 + VERIFY_STEP)
        up = b.adc_window()
        bd.dac(port, "dc", code=8192 - VERIFY_STEP)
        down = b.adc_window()
        bd.dac(port, "dc", code=8192)
        for ch in ("a", "b"):
            response[(ch, port)] = 0.5 * (up[ch]["mean"] - down[ch]["mean"])
            clipped[(ch, port)] = up[ch]["max"] >= 4095 or down[ch]["min"] <= 0 or up[ch]["min"] <= 0 or down[ch]["max"] >= 4095
    return response, clipped


def verify_v1b(b):
    """Find out what is actually plugged in, by what each cable does.  Returns (Found, rows): one row per thing,
    "found" against "expected"."""
    f = Found()
    rows = []
    bd_ok, ident = b.board_answers()
    if not bd_ok:
        rows.append(row("verify", "the board on USB PROG", "no answer (%s)" % ident, "the ID register 0xEC5BA2D2", "FAIL",
                        "is USB PROG (the upper USB-C) on the PC, and bringup.bit loaded?  `bench.py v1b --only jtag,load_bringup` loads it"))
        return f, rows
    f.board = True
    bd = b.bd
    rows.append(row("verify", "the board on USB PROG", "answers, bitstream version %s" % ident["version"], "the ID register 0xEC5BA2D2", "pass"))

    # (1) which DAC reaches which ADC, and through which jumpers
    response, clipped = dac_step_response(b)
    for ch, expected_port in (("a", 1), ("b", 2)):
        name = "ADC %s IN" % ch.upper()
        expected = "DAC %d OUT, gain x1, TERM in (%d ADC codes for the %d-code DAC step)" % (expected_port, VERIFY_STEP_ADC, VERIFY_STEP)
        ports = [port for port in (1, 2) if abs(response[(ch, port)]) >= CONNECTED_CODES]
        info = f.adc[ch]
        if not ports:
            rows.append(row("verify", name, "nothing (it moved %.1f and %.1f codes)" % (abs(response[(ch, 1)]), abs(response[(ch, 2)])), expected, "FAIL",
                            "no DAC reaches %s: is the SMA cable from DAC %d OUT on, finger tight at both ends?  This channel's analog "
                            "tests are skipped; after fixing: `bench.py v1b --only phase,dc_transfer,noise,sine,fullscale,xtalk,waves`" % (name, expected_port)))
            continue
        if len(ports) == 2:
            info["source"] = "both"
            rows.append(row("verify", name, "follows BOTH DACs (%.1f and %.1f codes)" % (response[(ch, 1)], response[(ch, 2)]), expected, "FAIL",
                            "one input cannot be cabled to two outputs: a short between the two DAC outputs, or heavy cross-talk.  "
                            "This channel's analog tests are skipped"))
            continue
        port = ports[0]
        step = response[(ch, port)]
        info["source"] = port
        info["inverted"] = step < 0
        if clipped[(ch, port)]:
            info["state"] = {"gain": 100, "term": False}
        else:
            info["state"] = analysis.jumper_state(abs(step) / VERIFY_STEP_ADC)
        words = "DAC %d OUT, %s (%+.1f codes)" % (port, analysis.jumper_words(info["state"]), step)
        nominal = info["state"] == {"gain": 1, "term": True}
        if not nominal:
            ch_n = 1 if ch == "a" else 2
            out = []                                  # which shunts the amplitude says are out
            if info["state"] is None:
                out.append("no jumper setting gives this amplitude: look at all of JP%d01, JP%d03, JP%d04" % (ch_n, ch_n, ch_n))
            else:
                if info["state"]["gain"] == 10:
                    out.append("one GAIN shunt is out (JP%d03 or JP%d04)" % (ch_n, ch_n))
                if info["state"]["gain"] == 100:
                    out.append("both GAIN shunts are out (JP%d03 and JP%d04)" % (ch_n, ch_n))
                if not info["state"]["term"]:
                    out.append("the TERM shunt JP%d01 is out" % ch_n)
            rows.append(row("verify", name, words, expected, "FAIL",
                            "%s; visit 0 sets all three in.  This channel's analog tests are skipped until they are" % "; ".join(out)))
            continue
        f.paths.append((port, ch))
        if info["inverted"]:
            rows.append(row("verify", name, words + ", INVERTED", expected, "info", "the ADC falls when the DAC rises: dc_transfer says so in words"))
        elif port != expected_port:
            rows.append(row("verify", name, words, expected, "info", "the two DAC cables are crossed: accepted, the tests use them as they are"))
        else:
            rows.append(row("verify", name, words, expected, "pass"))

    # (2) CLK OUT -> CLK IN
    bd.clkout("tcxo/2")
    f_half = bd.clocks(gates=2)["clk_in"]
    bd.clkout("low")
    f_low = bd.clocks(gates=2)["clk_in"]
    bd.clkout("tcxo")
    expected = "12,500,000 Hz with CLK OUT at TCXO/2, 0 Hz with CLK OUT held low"
    value = "%s at TCXO/2, %s held low" % (hz(f_half), hz(f_low))
    if abs(f_half - 12.5e6) <= freq_tolerance(b, 12.5e6) and f_low == 0:
        f.clk_cable = True
        rows.append(row("verify", "CLK IN", "the cable from CLK OUT: " + value, expected, "pass"))
    elif f_half == 0 and f_low == 0:
        rows.append(row("verify", "CLK IN", "nothing: " + value, expected, "FAIL",
                        "is the SMA cable from CLK OUT to CLK IN on?  The clkloop test is skipped; after fixing: `bench.py v1b --only clkloop`"))
    else:
        rows.append(row("verify", "CLK IN", value, expected, "FAIL",
                        "CLK IN counts something that does not follow CLK OUT: what is on its SMA?  The clkloop test is skipped"))

    # (3) a card
    sd = bd.sd_check(read_block=False)
    f.card = bool(sd.get("card"))
    rows.append(row("verify", "microSD socket", "a card answers" if f.card else "no card answers (CMD0 got no reply)", "a card", "pass" if f.card else "FAIL",
                    "" if f.card else "push a microSD card into the socket on the back until it clicks.  The sd test is skipped; after: `bench.py v1b --only sd`"))

    # (4) USB USER on a host
    usb = bd.usb_attach("fs", seconds=1.5)
    f.usb_host = bool(usb["host_reset_seen"])
    if f.usb_host:
        rows.append(row("verify", "USB USER", "a host: it reset the bus (%d ms with both lines low)" % usb["after"]["se0_ms"], "a host's bus reset", "pass"))
    elif not usb["line_went_high"]:
        rows.append(row("verify", "USB USER", "D+ did not go high with the board's pull-up on", "a host's bus reset", "FAIL",
                        "that is the board, not the cable: the 1.5 k on USB_PULLUP (H13), or D+ (G14) held low.  The usb test will say more"))
    else:
        rows.append(row("verify", "USB USER", "no host: D+ went high and nothing answered in 1.5 s", "a host's bus reset", "FAIL",
                        "is the second USB-C cable in USB USER (the lower USB-C) and in the PC, and is it a data cable?  The usb test is "
                        "skipped; after: `bench.py v1b --only usb`"))

    # (5) the Ethernet link
    phy = bd.phy_status()
    f.link = bool(phy["link"])
    rows.append(row("verify", "Ethernet", ("link up, %s Mb/s %s duplex" % (phy["speed"], "full" if phy["full_duplex"] else "half")) if f.link else "no link",
                    "a link to the lab switch", "pass" if f.link else "FAIL",
                    "" if f.link else "is the cable in the RJ45 and in the switch (the jack's LEDs)?  eth_loop still runs (it needs no cable); "
                    "eth_wire is skipped; after: `bench.py v1b --only phy,eth_wire`"))

    # (6) a monitor, (7) the Pmod loop: both optional until visit 3
    f.monitor = bool(bd.hdmi()["hpd"])
    rows.append(row("verify", "mini-HDMI", "a monitor (hot-plug high)" if f.monitor else "no monitor", "optional (visit 3)", "info",
                    "" if f.monitor else "the hdmi test is skipped"))
    pmod = bd.pmod_loop_test()
    bad = sorted(set(pmod["a_to_b"]) | set(pmod["b_to_a"]))
    f.pmod_loop = len(bad) < 8
    if pmod["ok"]:
        rows.append(row("verify", "Pmod A - Pmod B", "all eight pins looped", "optional (visit 3)", "info"))
    elif f.pmod_loop:
        rows.append(row("verify", "Pmod A - Pmod B", "looped, but not bit(s) %s" % ", ".join(str(i) for i in bad), "optional (visit 3)", "info",
                        "some wires are on: the pmod test runs and names the bad ones"))
    else:
        rows.append(row("verify", "Pmod A - Pmod B", "no loop", "optional (visit 3)", "info", "the pmod test is skipped"))
    b.record("found", quiet=True, paths=f.paths, adc=f.adc, clk_cable=f.clk_cable, card=f.card, usb_host=f.usb_host, link=f.link,
             monitor=f.monitor, pmod_loop=f.pmod_loop)
    return f, rows


# ---- loading the FPGA: on the bench only -----------------------------------------------------------------------
OSS = os.environ.get("OSS_CAD_SUITE", "/home/jason/mudd/133electronics/icepi-zero-dac-adc/tools/oss-cad-suite")   # as gateware/bringup/build.sh
LOADER = os.path.join(OSS, "bin", "openFPGALoader")
BITSTREAMS = os.path.join(bench.PROJECT, "gateware", "bringup", "build")
IDCODE_LFE5U_25F = 0x41111043    # BRINGUP.md 2.2
BLINK_GREETING = b"ECP5-2ADC-2DAC blink"     # what blink.bit prints once a second at 115200 baud (gateware/bringup/README.md)


def run_loader(args, timeout, loader=LOADER):
    """Run openFPGALoader with `args`.  Returns (exit status or None, its output as text); never raises."""
    try:
        p = subprocess.run([loader] + list(args), capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return None, "openFPGALoader is not at %s (set OSS_CAD_SUITE)" % loader
    except subprocess.TimeoutExpired:
        return None, "openFPGALoader %s did not finish in %d s" % (" ".join(args), timeout)
    except OSError as e:
        return None, "openFPGALoader could not be run: %s" % e


def parse_idcode(text):
    """The first 'idcode 0x...' of openFPGALoader --detect's output as an integer, or None."""
    m = re.search(r"idcode\s+0x([0-9a-fA-F]+)", text)
    return int(m.group(1), 16) if m else None


def loader_hint(text):
    """What to do about an openFPGALoader failure, from its own words."""
    low = text.lower()
    if "not at" in low or "could not be run" in low:
        return "the oss-cad-suite's path: OSS_CAD_SUITE, as gateware/bringup/build.sh"
    if "permission" in low or "access" in low or "unable to open ftdi" in low or "-4" in low:
        return ("USB permission for the FT2232H (0403:6010), or no FT2232H at all: `lsusb | grep 0403:6010`; if it is there, the udev rule is "
                "Jason's (BRINGUP.md 2.2: the block with `sudo cp /lib/udev/rules.d/60-openocd.rules ...`)")
    return ("no answer on JTAG: USB PROG plugged?  JP501 (FTDI OFF) must be open; then the JTAG pins (TCK T10, TMS T11, TDI R11, TDO M10) "
            "and the BGA itself (BRINGUP.md 2.2)")


def test_jtag(b):
    """the FPGA on JTAG: openFPGALoader --detect must read IDCODE 0x41111043"""
    if b.sim:
        return [row("jtag", "IDCODE over JTAG", "not run", "0x%08X" % IDCODE_LFE5U_25F, "skipped", OUT_OF_SIM)]
    b.hardware_only("openFPGALoader")
    b.board_forget()
    status, text = run_loader(["--detect", "-c", "ft2232"], timeout=30)
    idcode = parse_idcode(text)
    b.record("loader", quiet=True, args="--detect", status=status, output=text[-600:])
    if idcode == IDCODE_LFE5U_25F:
        return [row("jtag", "IDCODE over JTAG", "0x%08X" % idcode, "0x%08X (LFE5U-25F)" % IDCODE_LFE5U_25F, "pass")]
    value = ("0x%08X" % idcode) if idcode is not None else "none (%s)" % (text.strip().splitlines()[-1][:80] if text.strip() else "no output")
    return [row("jtag", "IDCODE over JTAG", value, "0x%08X (LFE5U-25F)" % IDCODE_LFE5U_25F, "FAIL", loader_hint(text))]


def test_load_blink(b):
    """blink.bit into the FPGA, then its greeting on the serial channel at 115200 baud"""
    if b.sim:
        return [row("load_blink", "blink.bit and its greeting", "not run", "", "skipped", OUT_OF_SIM)]
    b.hardware_only("openFPGALoader")
    b.board_forget()
    status, text = run_loader(["-c", "ft2232", os.path.join(BITSTREAMS, "blink.bit")], timeout=60)
    b.record("loader", quiet=True, args="blink.bit", status=status, output=text[-600:])
    if status != 0:
        return [row("load_blink", "blink.bit into the FPGA", "openFPGALoader failed: %s" % text.strip().splitlines()[-1][:80], "loaded", "FAIL", loader_hint(text))]
    rows = [row("load_blink", "blink.bit into the FPGA", "loaded", "loaded", "pass")]
    import serial
    port = b.cfg["board_port"]
    if port in (None, "auto"):
        port = ecp5bu.find_port()
    heard = b""
    with serial.Serial(port, 115200, timeout=0.5) as s:      # blink.bit talks at 115200; bringup.bit at 1 Mbaud
        t0 = b.now()
        while b.now() - t0 < 3.5 and BLINK_GREETING not in heard:      # it prints once a second
            heard += s.read(200)
    ok = BLINK_GREETING in heard
    rows.append(row("load_blink", "the greeting at 115200 baud", repr(heard[-40:].decode("ascii", "replace")) if heard else "nothing in 3.5 s",
                    "'%s <n>' once a second" % BLINK_GREETING.decode(), "pass" if ok else "FAIL",
                    "" if ok else "the LEDs chasing means the design runs: then it is uart_tx (H14) or the FT2232H's channel B; no chase: "
                    "the TCXO (BRINGUP.md 3.1)"))
    rows.append(row("load_blink", "the LEDs", "the eight white LEDs should chase, the RGB LED cycle", "", "info", "needs eyes"))
    return rows


def test_load_bringup(b):
    """bringup.bit into the FPGA; the board must then answer on the register bus"""
    if b.sim:
        return [row("load_bringup", "bringup.bit and the ID register", "not run", "", "skipped", OUT_OF_SIM)]
    b.hardware_only("openFPGALoader")
    b.board_forget()
    status, text = run_loader(["-c", "ft2232", os.path.join(BITSTREAMS, "bringup.bit")], timeout=60)
    b.record("loader", quiet=True, args="bringup.bit", status=status, output=text[-600:])
    if status != 0:
        return [row("load_bringup", "bringup.bit into the FPGA", "openFPGALoader failed: %s" % text.strip().splitlines()[-1][:80], "loaded", "FAIL", loader_hint(text))]
    b.sleep(0.5)
    ok, ident = b.board_answers()
    return [row("load_bringup", "bringup.bit into the FPGA", "loaded", "loaded", "pass"),
            row("load_bringup", "the board answers", ("ID right, version %s" % ident["version"]) if ok else "no (%s)" % ident, "the ID register 0xEC5BA2D2",
                "pass" if ok else "FAIL", "" if ok else "the LEDs chasing means the design is in: then the serial channel (uart_tx H14, uart_rx H15, "
                "1 Mbaud from the 25.000 MHz TCXO); `ls /dev/serial/by-id/` must show ...-if01 (BRINGUP.md 3.2)")]


def test_flash(b):
    """bringup.bit into the flash (a minute); the board must answer again afterwards"""
    if b.sim:
        return [row("flash", "bringup.bit into the W25Q128", "not run", "", "skipped", OUT_OF_SIM)]
    b.hardware_only("openFPGALoader")
    b.board_forget()
    status, text = run_loader(["-c", "ft2232", "-f", os.path.join(BITSTREAMS, "bringup.bit")], timeout=300)
    b.record("loader", quiet=True, args="-f bringup.bit", status=status, output=text[-600:])
    if status != 0:
        return [row("flash", "bringup.bit into the W25Q128", "openFPGALoader failed: %s" % text.strip().splitlines()[-1][:80], "written and verified", "FAIL",
                    loader_hint(text) + "; the flash's pins are on the sysCONFIG bank")]
    b.record("flash", quiet=True, written=True, bitstream="bringup.bit")
    b.sleep(3.0)                                      # openFPGALoader reloads the FPGA from the flash when it is done
    ok, ident = b.board_answers()
    return [row("flash", "bringup.bit into the W25Q128", "written", "written and verified", "pass"),
            row("flash", "the board answers again", ("ID right, version %s" % ident["version"]) if ok else "no (%s)" % ident, "the ID register 0xEC5BA2D2",
                "pass" if ok else "FAIL", "" if ok else "written, but the FPGA did not come back from its flash: `bench.py v1b --only load_bringup` "
                "to go on from RAM; the cold boot test (`coldboot`) will say whether the flash boots at power-on")]


# ---- the digital tests ---------------------------------------------------------------------------------------------
def test_bus(b):
    """the register bus: the ID, the version, random words through the scratch register"""
    bd = b.bd
    ident = bd.ident()
    rows = [row("bus", "ID register", "0x%08X" % ident["id"], "0xEC5BA2D2", "pass")]
    new_enough = int(ident["version"], 16) >= ecp5bu.V2
    rows.append(row("bus", "bitstream version", ident["version"], "20261115 or later", "pass" if new_enough else "FAIL",
                    "" if new_enough else "an older bring-up bitstream is running: the USB, SD, HDMI and Ethernet tests need 20261115; "
                    "`bench.py v1b --only load_bringup,flash`"))
    try:
        n = bd.scratch_test(b.size("scratch"))
        rows.append(row("bus", "scratch register", "%d random words written and read back" % n, "every one the same", "pass"))
    except IOError as e:
        rows.append(row("bus", "scratch register", str(e), "every word read back as written", "FAIL",
                        "the serial link drops or flips bytes: the USB cable, a hub; `journalctl -k | tail` for USB errors"))
    return rows


def test_current(b):
    """the supply's current with bringup.bit running as it starts: the reference for the cold-boot test"""
    bd = b.bd
    out = b.cfg["psu"]["out"]
    bd.gpio(dac_sleep=0)
    bd.dac_config(rate=50e6)
    bd.dac(1, "sine", freq=1e6)                       # the design's power-up state: full-scale sines of 1 and 2 MHz (rtl/top.v)
    bd.dac(2, "sine", freq=2e6)
    b.adc_setup(25e6)
    b.sleep(1.0)
    readings = []
    for _ in range(3):
        readings.append(b.psu.measure(out=out))
        b.sleep(0.5)
    mode = b.psu.mode(out=out)
    for port in (1, 2):
        bd.dac(port, "dc", code=8192)
    volts = sum(r[0] for r in readings) / 3
    amps = sum(r[1] for r in readings) / 3
    b.record("current_ref", quiet=True, state="bringup", amps=amps, volts=volts)
    ok = mode == "CV" and amps < bench.SUPPLY_A
    return [row("current", "supply current, bringup.bit running", "%.3f A at %.2f V, %s" % (amps, volts, mode), "constant voltage; about 0.6-0.7 A (BRINGUP.md: about 3 W)",
                "pass" if ok else "FAIL", "" if ok else "the supply is at its 1.0 A limit with the design running: what is warm?")]


def test_clocks(b):
    """the board's own counters: the TCXO, the PLL's 50 MHz, the PHY's receive clock"""
    bd = b.bd
    c = bd.clocks(gates=2)
    status = bd.status()
    step = b.count_step_hz()
    rows = [row("clocks", "tcxo (counts its own gate)", hz(c["tcxo"]), "25,000,000 Hz exactly", "pass" if c["tcxo"] == 25_000_000 else "FAIL",
                "" if c["tcxo"] == 25_000_000 else "this counter counts the clock that makes its own gate: anything else is the gateware, not the board"),
            row("clocks", "clk_s (the PLL)", hz(c["clk_s"]), "50,000,000 Hz within one count (%s)" % hz(step),
                "pass" if abs(c["clk_s"] - 50e6) <= step else "FAIL", "" if abs(c["clk_s"] - 50e6) <= step else "the PLL (VCCAUX = +2V5 from U603): see pll_lock"),
            row("clocks", "PLL locked", "yes" if status["pll_lock"] else "NO", "yes", "pass" if status["pll_lock"] else "FAIL",
                "" if status["pll_lock"] else "the RGB LED is red: +2V5 (VCCAUX) at the RAILS header; without the PLL no converter, SDRAM or Ethernet test means anything"),
            row("clocks", "rxc (the PHY's receive clock)", hz(c["rxc"]), "", "info", "125 MHz with a gigabit link; 25 MHz at 100 Mb/s; 2.5 MHz at 10 Mb/s or with no link")]
    return rows


def ensure_si5351(b, outputs=(0, 1, 2)):
    """Program whichever of the Si5351's `outputs` the counters do not see running (after a power cycle none
    runs).  Returns None when all of them run afterwards, else a sentence saying why not."""
    bd = b.bd
    c = bd.clocks(gates=2)
    missing = [(clk, freq) for clk, freq in SI_PLAN if clk in outputs and c["si%d" % clk] == 0]
    if not missing:
        return None
    try:
        for clk, freq in missing:
            bd.si5351_set(clk, freq)
    except IOError as e:
        return str(e)
    b.sleep(0.2)
    return None


def test_si5351(b):
    """the Si5351 on I2C: it answers at 0x60, and its outputs count 10, 25 and 100 MHz"""
    bd = b.bd
    found = bd.i2c_scan()
    answers = 0x60 in found
    rows = [row("si5351", "I2C scan", ", ".join("0x%02x" % x for x in found) or "nothing answers", "0x60", "pass" if answers else "FAIL",
                "" if answers else "no ACK from the Si5351: its pull-ups (4.7 k), SDA A15 / SCL E13, its 3.3 V (BRINGUP.md 4.2)")]
    if not answers:
        return rows
    bd.i2c_write(0x60, 3, [0xFF])                     # register 3, output enable: every output off, so that what runs below is what was set here
    for clk, freq in SI_PLAN:
        bd.si5351_set(clk, freq)
    b.sleep(0.2)
    status = bd.si5351_status()
    c = bd.clocks(gates=2)
    for clk, freq in SI_PLAN:
        got = c["si%d" % clk]
        ok = abs(got - freq) <= freq_tolerance(b, freq)
        rows.append(row("si5351", "CLK%d" % clk, "%s (%+.1f ppm)" % (hz(got), (got - freq) / freq * 1e6), "%s within 100 ppm" % hz(freq), "pass" if ok else "FAIL",
                        "" if ok else ("the output does not run: its crystal Y301, the status row below" if got == 0 else
                                       "the wrong frequency: the Si5351's crystal Y301 is 25 MHz? (the counter's own reference is the TCXO)")))
    healthy = status is not None and not (status["sys_init"] or status["lol_a"] or status["lol_b"] or status["los_xtal"])
    rows.append(row("si5351", "status register", "0x%02x" % status["raw"] if status else "no answer", "no SYS_INIT, LOL or LOS bit", "pass" if healthy else "FAIL",
                    "" if healthy else "LOS: the crystal Y301 does not oscillate; LOL: a PLL has not locked (read it again in a second)"))
    return rows


# CLK OUT's sources for the loop test: (CLK OUT's name, the counter that reads the same clock inside, its factor, why "info")
CLKLOOP = [("tcxo", "tcxo", 1.0, ""), ("tcxo/2", "tcxo", 0.5, ""), ("clk_s", "clk_s", 1.0, ""),
           ("si0", "si0", 1.0, ""), ("si1", "si1", 1.0, ""),
           ("si2", "si2", 1.0, "100 MHz is above the CLK IN comparator's 80 MHz (the TLV3501's part of README.md): reported, not judged")]


def test_clkloop(b):
    """CLK OUT -> CLK IN: every source of CLK OUT, counted again on CLK IN"""
    bd = b.bd
    rows = []
    why_not = ensure_si5351(b)
    if why_not:
        rows.append(row("clkloop", "the Si5351", why_not, "", "info", "its three sources are left out; `bench.py v1b --only si5351` says why"))
    try:
        for name, counter, factor, why_info in CLKLOOP:
            bd.clkout(name)
            c = bd.clocks(gates=2)
            source = c[counter] * factor
            got = c["clk_in"]
            if source == 0:
                rows.append(row("clkloop", "CLK OUT = %s" % name, "the source itself is not running", "", "skipped", "the si5351 test says why"))
                continue
            ok = abs(got - source) <= freq_tolerance(b, source)
            if why_info:
                rows.append(row("clkloop", "CLK OUT = %s" % name, "%s on CLK IN (the source: %s)" % (hz(got), hz(source)), "", "info", why_info))
            else:
                rows.append(row("clkloop", "CLK OUT = %s" % name, "%s on CLK IN (the source: %s)" % (hz(got), hz(source)), "the same within 100 ppm",
                                "pass" if ok else "FAIL", "" if ok else "CLK OUT's driver or CLK IN's comparator at this frequency: the scope on CLK OUT in visit 2 "
                                "(`v2 --only clkout_scope`) says which"))
    finally:
        bd.clkout("tcxo")
    return rows


def test_sdram(b):
    """the SDRAM: the read-latency scan, the whole array with three patterns, both clock polarities"""
    bd = b.bd
    rows = []
    words = b.size("sdram_scan")
    scan = bd.sdram_scan(words)
    good = [lat for lat, errors in scan.items() if errors == 0]
    rows.append(row("sdram", "read-latency scan, %d words" % words, "errors at latency 1..7: " + " ".join(str(scan[lat]) for lat in sorted(scan)),
                    "0 errors at one latency at least (3 in simulation; 3 or 4 on the board)", "pass" if good else "FAIL",
                    "" if good else "errors at every latency.  In one data bit: that DQ line; in one bank: its BA; everywhere: the SDRAM's clock (BRINGUP.md 7.1)"))
    if not good:
        return rows
    latency = good[len(good) // 2]
    b.found.sdram_latency = latency
    words = b.size("sdram_full")
    whole = "the whole array (16 M words)" if not b.sim else "%d words (the whole array is not simulated)" % words
    for pattern in (0, 1, 6):
        r = bd.sdram_test(words, pattern=pattern, rdlat=latency, timeout=120.0)
        value = "%d errors in %d words written and read back" % (r["errors"], r["words"])
        if r["errors"]:
            value += "; first at word 0x%06x: wrote %04x, read %04x" % (r["first_addr"], r["first_expected"], r["first_got"])
        rows.append(row("sdram", "pattern %d at latency %d, %s" % (pattern, latency, whole), value, "0 errors", "pass" if r["errors"] == 0 else "FAIL",
                        "" if r["errors"] == 0 else "the bits that differ between 'wrote' and 'read' name the DQ line; an address pattern names an address line"))
    words = b.size("sdram_pol")
    for pol in (0, 1):
        r = bd.sdram_test(words, pattern=0, rdlat=latency, pol=pol)
        if pol == 0:
            rows.append(row("sdram", "clock polarity 0 (as designed), %d words" % words, "%d errors" % r["errors"], "0 errors", "pass" if r["errors"] == 0 else "FAIL"))
        else:
            rows.append(row("sdram", "clock polarity 1 (inverted), %d words" % words, "%d errors" % r["errors"], "", "info",
                            "the margin: 0 errors both ways means the SDRAM clock's phase is not critical"))
    return rows


def test_phy(b):
    """the Ethernet PHY on MDIO: its ID, the RGMII delays it took from its straps, the link"""
    bd = b.bd
    ids = bd.phy_id()
    rows = [row("phy", "ID over MDIO", "%04X %04X" % ids, "001C C916 (RTL8211F)", "pass" if ids == (0x001C, 0xC916) else "FAIL",
                "" if ids == (0x001C, 0xC916) else "FFFF FFFF is no answer: the PHY's address strap (PHYAD = 1), its 3.3 V, its 1.0 V switcher (L401; `bench.py dmm +1V0_PHY`)")]
    if ids != (0x001C, 0xC916):
        return rows
    straps = bd.phy_straps()
    both = straps["txdly"] and straps["rxdly"]
    rows.append(row("phy", "RGMII delay straps", "TXDLY %s, RXDLY %s" % ("on" if straps["txdly"] else "OFF", "on" if straps["rxdly"] else "OFF"), "both on",
                    "pass" if both else "FAIL", "" if both else "the board straps both delays on; without them eth_loop shows CRC errors: the strap resistors at the PHY"))
    st = bd.phy_status()
    rows.append(row("phy", "link", ("up, %s Mb/s, %s duplex" % (st["speed"], "full" if st["full_duplex"] else "half")) if st["link"] else "down", "", "info"))
    return rows


# The largest standard frame: 1500 bytes after the Ethernet header.  ecp5bu.eth_frame builds a UDP datagram, whose
# IP and UDP headers take 28 of them, so its payload_len is 1472 (and 18 gives the 64-byte minimum frame).
ETH_MAX_PAYLOAD = 1472


def test_eth_loop(b):
    """the RGMII data path with no cable: frames out and back through the PHY's own loopback"""
    bd = b.bd
    rows = []
    for label, frames, payload in (("minimum frames (64 bytes)", b.size("eth_min"), 18),
                                   ("maximum frames (1518 bytes)", b.size("eth_max"), ETH_MAX_PAYLOAD)):
        r = bd.eth_loopback_test(frames=frames, payload_len=payload)
        value = "%d sent, %d back with a right CRC, %d bad; the first one %s" % (frames, r["rx_good"], r["rx_bad"],
                                                                                  "equal byte for byte" if r["capture_equal"] else "DIFFERENT")
        rows.append(row("eth_loop", label, value, "all back, none bad, the first equal", "pass" if r["ok"] else "FAIL",
                        "" if r["ok"] else "lost or damaged inside the PHY's loopback, so nothing outside the board is involved: the RGMII pins, "
                        "or their timing (the delay straps: the phy test); 0 back at all: the 125 MHz clocks (clocks' rxc row)"))
    return rows


def test_eth_wire(b):
    """real frames on the wire: the board's broadcasts reach a socket on this PC, and the PC's reach the board"""
    if b.sim:
        return [row("eth_wire", "frames to and from the PC", "not run", "", "skipped", OUT_OF_SIM + ": the simulated bench has no PC on its wire")]
    b.hardware_only("a UDP socket")
    import socket
    bd = b.bd
    rows = []
    port = 50007                                      # ecp5bu.eth_frame's UDP port: its frames are broadcasts to this port
    for _ in range(12):                               # eth_loop has just restarted auto-negotiation: up to 6 s for the link
        if bd.phy_status()["link"]:
            break
        b.sleep(0.5)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", port))
        sock.settimeout(0.3)
        # the board sends 10 broadcasts; this PC must receive them
        bd.eth_load(bd.eth_frame(payload_len=64, seq=1))
        bd.eth_clear()
        bd.eth_send(10, gap=1200)
        heard = 0
        t0 = b.now()
        while b.now() - t0 < 2.0 and heard < 10:
            try:
                data, _ = sock.recvfrom(2048)
            except socket.timeout:
                continue
            if data[:4] == b"ECP5":
                heard += 1
        rows.append(row("eth_wire", "board -> PC", "%d of 10 broadcast frames received on UDP port %d" % (heard, port), "10", "pass" if heard == 10 else "FAIL",
                        "" if heard == 10 else "eth_loop passing means the board's side is right: then the magnetics and the RJ45, the switch port, "
                        "or this PC's firewall dropping UDP %d (`sudo ufw status` is Jason's)" % port))
        # the PC sends 20 broadcasts; the board's good-frame count must rise by as many (other traffic on the LAN adds to it)
        bd.eth_clear()
        before = bd.eth_counts()
        for k in range(20):
            sock.sendto(b"ECP5 from the PC %02d" % k + bytes(40), (b.cfg["pc_broadcast"], port))
            b.sleep(0.01)
        b.sleep(0.2)
        after = bd.eth_counts()
        got = after["rx_good"] - before["rx_good"]
        rows.append(row("eth_wire", "PC -> board", "%d good frames counted while the PC sent 20 (%d bad)" % (got, after["rx_bad"] - before["rx_bad"]),
                        "20 or more good, none bad", "pass" if got >= 20 and after["rx_bad"] == before["rx_bad"] else "FAIL",
                        "" if got >= 20 else "the PC broadcasts to %s (bench_config.json's pc_broadcast): is that the subnet the lab switch is on?" % b.cfg["pc_broadcast"]))
    finally:
        sock.close()
    return rows


def test_sd(b):
    """the microSD socket: the card initialised in SPI mode, its identity and block 0 read with their CRCs"""
    r = b.bd.sd_check()
    if not r.get("card"):
        return [row("sd", "the card", "no answer to CMD0 (the pins idle at %s)" % r["pins_idle"], "a card that answers", "FAIL",
                    "push the card in until it clicks; with a card in: CLK, CMD, DAT0 and DAT3 at the socket")]
    rows = [row("sd", "initialisation", ("ready after %d ACMD41" % r["acmd41_tries"]) if r.get("ready") else "never left idle", "ready", "pass" if r.get("ready") else "FAIL",
                "" if r.get("ready") else "the card answers but does not initialise: another card first")]
    if not r.get("ready"):
        return rows
    rows.append(row("sd", "identity (CID)", "maker 0x%02x, name %r, CRC %s" % (r["manufacturer"] or 0, r["name"], "right" if r["cid_crc_ok"] else "WRONG"),
                    "read with a right CRC-16", "pass" if r["cid_crc_ok"] else "FAIL", "" if r["cid_crc_ok"] else "bytes damaged at 3 MHz: DAT0's trace or the socket"))
    rows.append(row("sd", "block 0 (512 bytes)", "CRC %s, ends %s" % ("right" if r["block0_crc_ok"] else "WRONG", r.get("block0_signature")),
                    "read with a right CRC-16", "pass" if r["block0_crc_ok"] else "FAIL", "" if r["block0_crc_ok"] else "as the CID row"))
    return rows


def kernel_usb_lines(since):
    """The kernel log's lines about USB since `since` (a datetime): what the PC made of the board's attach."""
    try:
        p = subprocess.run(["journalctl", "-k", "--no-pager", "-o", "short", "--since", since.strftime("%Y-%m-%d %H:%M:%S")],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        return ["(journalctl could not be read: %s)" % e]
    return [line.split("kernel: ", 1)[-1] for line in p.stdout.splitlines() if "usb" in line.lower()][-8:]


def test_usb(b):
    """USB USER's lines: the board shows itself as a full-speed, then a low-speed device; the host must react"""
    bd = b.bd
    rows = []
    began = dt.datetime.now()
    # full speed: the board's 1.5 k pulls D+ up; the host answers with a bus reset (both lines low) and packets on both lines
    r = bd.usb_attach("fs", seconds=1.5)
    value = "D+ high: %s; bus reset: %s (%d ms); packets: %s (%d edges on D+, %d on D-)" % (
        "yes" if r["line_went_high"] else "NO", "yes" if r["host_reset_seen"] else "NO", r["after"]["se0_ms"],
        "yes" if r["host_packets_seen"] else "no", r["after"]["dp_edges"], r["after"]["dn_edges"])
    ok = r["line_went_high"] and r["host_reset_seen"] and r["host_packets_seen"] and r["line_fell_when_released"]
    rows.append(row("usb", "full speed (the 1.5 k pull-up on D+)", value, "D+ goes high, the host resets the bus and sends packets, D+ falls when released",
                    "pass" if ok else "FAIL",
                    "" if ok else "the line that does not move is the suspect: D+ is G14, D- is G13, the pull-up H13; verify saw a host, so the cable is right"))
    b.sleep(0.5)                                      # the host notices the detach before the next attach
    # low speed: the FPGA drives D- high itself (the board has no pull-up there).  The host's reset cannot be seen on a
    # line the FPGA holds high, so the witness is D+: the host's packets after it has taken the board for a low-speed device.
    # 0.8 s only: while the FPGA holds D- high the host's bus reset pulls against it (a few tens of mA for the
    # 10-60 ms of each reset); a host answers an attach within about 0.25 s, so there is no reason to hold longer
    r = bd.usb_attach("ls", seconds=0.8)
    host_reacted = r["after"]["dp_edges"] > 2
    value = "D- high: %s; the host's packets on D+: %s (%d edges)" % ("yes" if r["line_went_high"] else "NO", "yes" if host_reacted else "NO", r["after"]["dp_edges"])
    ok = r["line_went_high"] and host_reacted and r["line_fell_when_released"]
    rows.append(row("usb", "low speed (D- driven high by the FPGA)", value, "D- goes high, the host answers on D+, D- falls when released", "pass" if ok else "FAIL",
                    "" if ok else "with full speed passing, this is D-'s output path alone: the FPGA pin G13 and its series resistor"))
    b.sleep(0.5)
    if not b.sim:
        b.hardware_only("journalctl")
        lines = kernel_usb_lines(began)
        rows.append(row("usb", "the PC's kernel log", "%d line(s) about USB since the test began" % len(lines), "", "info",
                        " // ".join(lines) if lines else "nothing logged: the PC did not notice a device (is USB USER on this PC?)"))
    return rows


HDMI_FPS = 59.5                  # 25 MHz pixels / (800 x 525): the test picture's frame rate (ecp5bu.hdmi_frame_rate)


def hdmi_frame_rate(b):
    """Frames per second of the test picture, from the board's frame counter."""
    bd = b.bd
    if not b.sim:
        return bd.hdmi_frame_rate(seconds=4.0)        # 238 frames +-1: good to 0.25 frames a second
    # A simulated board's waits are a thousand times shorter than they say (cosim.SimTransport.scale), its pixel clock
    # is not: time two changes of the frame counter instead, in the board's own time.
    scale = bd.t.scale
    def next_change():
        last = bd.hdmi()["frames"]
        for _ in range(600):
            bd.wait(0.1)
            if bd.hdmi()["frames"] != last:
                return bd.t.time()
        raise IOError("the HDMI frame counter does not advance")
    first = next_change()
    second = next_change()
    return 1.0 / ((second - first) * scale)


def test_hdmi(b):
    """HDMI: the monitor's EDID over DDC, the test picture on, its frame rate"""
    bd = b.bd
    rows = []
    edid = bd.edid()
    if edid is None:
        rows.append(row("hdmi", "the monitor's EDID", "nothing answers at DDC address 0x50", "128 bytes with a right header and checksum", "FAIL",
                        "the monitor shows hot-plug but not its EDID: the DDC lines (their pull-ups and level shifting at J503), or a monitor in standby"))
    else:
        ok = edid["header_ok"] and edid["checksum_ok"]
        rows.append(row("hdmi", "the monitor's EDID", "maker %s, name %r, header %s, checksum %s" % (edid["maker"], edid["name"], "right" if edid["header_ok"] else "WRONG",
                        "right" if edid["checksum_ok"] else "WRONG"), "a right header and checksum", "pass" if ok else "FAIL",
                        "" if ok else "bytes damaged on DDC: read it again (`bench.py step hdmi`); it is a slow bit-banged bus, so wiring, not timing"))
    bd.hdmi(on=True, pattern=0)
    fps = hdmi_frame_rate(b)
    tolerance = 0.5 if not b.sim else 1.0             # simulated: two frames are timed in 0.1 ms steps, good to 0.4 frames a second
    rows.append(row("hdmi", "frame rate", "%.2f frames a second" % fps, "%.1f +-%.1f" % (HDMI_FPS, tolerance), "pass" if abs(fps - HDMI_FPS) <= tolerance else "FAIL",
                    "" if abs(fps - HDMI_FPS) <= tolerance else "the pixel clock is the PLL's 25 MHz: the clocks test"))
    rows.append(row("hdmi", "the picture", "on: colour bars in a white border, a grey ramp, a moving block (640 x 480, 60 Hz)", "", "info", "needs eyes: does the monitor show it?"))
    return rows


def test_pmod(b):
    """the Pmod loop: every pin of Pmod A driven and read on Pmod B, and back"""
    r = b.bd.pmod_loop_test()
    rows = []
    for key, label in (("a_to_b", "Pmod A drives, Pmod B reads"), ("b_to_a", "Pmod B drives, Pmod A reads")):
        bad = r[key]
        rows.append(row("pmod", label, "all eight pins" if not bad else "bad bit(s): %s" % ", ".join(str(i) for i in bad), "all eight", "pass" if not bad else "FAIL",
                        "" if not bad else "bit n is the socket's n-th signal pin (0-3 the top row, 4-7 the bottom): that wire, then that FPGA pin.  " + "; ".join(r["detail"][:4])))
    return rows


# ---- the analog self-test, through the cables verify found -----------------------------------------------------------
HALF_SCALE_PKPK = 2048           # ADC codes peak to peak of a half-scale DAC sine (amplitude shift 1): +-0.5 V into 50 ohm, half of 4096
CLEAN_RESIDUAL = 20              # a capture phase is clean if no sample is further than this from the fitted sine (a bit error is hundreds)
SFDR_MIN_DB = 60.0               # BRINGUP.md 6.6: over 60 dB at 1 MHz is the chain working as designed
NOISE_MAX_STD = 3.0              # BRINGUP.md 6.1: under 3 codes rms with nothing coming in
SPUR_MAX_CODES = 10.0            # BRINGUP.md 6.1: no tone above 10 codes peak
TONE_ABOVE_FLOOR = 6.0           # a spectrum's largest bin is a tone, not noise, when it is 6 times the median bin (noise alone reaches 3 to 4 times)
# The DAC's sine table has 1024 steps a period and the DAC runs at 50 MS/s (rtl/dac_gen.v): a tone that is a multiple of
# 50 MS/s / 1024 = 48.828 kHz walks the table in whole steps (the generator adds no spurs of its own), and an EVEN multiple
# fits a whole number of periods into every capture taken here (512 samples or more, at 25 or 50 MS/s), so the spectrum
# shows the tone as three clean bins and anything else is the analog chain's.  The test tones are the nearest such.
TONE_STEP_HZ = 2 * 50e6 / 1024


def test_tone(nominal):
    """The test tone nearest to `nominal` Hz: 100 kHz -> 97,656.25; 1 MHz -> 976,562.5; 5 MHz -> 4,980,468.75; 10 MHz -> 9,960,937.5."""
    return max(1, round(nominal / TONE_STEP_HZ)) * TONE_STEP_HZ


SINE_FREQS = (100e3, 1e6, 5e6, 10e6)     # nominal; test_tone() of each is what the DAC makes
ONE_MHZ = test_tone(1e6)                 # the "1 MHz" of the phase scan, the cross-talk test and the soak
SPUR_NAMES = [(1.0e6, "the +1V1 buck (1 MHz)"), (1.5e6, "the +3V3 buck (1.5 MHz)"), (2.0e6, "the -4V2 charge pump (2 MHz)"),
              (12.5e6, "a clock (12.5 MHz)"), (25e6, "a clock (25 MHz)")]         # BRINGUP.md 6.1: who makes which tone


def skipped_channels(b, test):
    """A 'skipped' row for each ADC channel that has no usable DAC path, saying why."""
    used = [ch for _, ch in b.found.paths]
    return [row(test, "ADC %s" % ch.upper(), "not run", "", "skipped", b.found.channel_note(ch)) for ch in ("a", "b") if ch not in used]


def pick(ch, ca, cb):
    return ca if ch == "a" else cb


def name_spur(freq, bin_hz):
    """Who makes a tone at `freq`, if it is near one of the board's own frequencies."""
    for f, name in SPUR_NAMES:
        if abs(freq - f) <= max(2 * bin_hz, 0.03 * f):
            return name
    return "none of the board's own frequencies"


def alias(freq, rate):
    """Where a tone of `freq` shows in a capture at `rate`: itself below half the rate, folded above."""
    f = freq % rate
    return f if f <= rate / 2 else rate - f


def test_phase(b):
    """the ADC capture timing: every capture phase and both edges on a 1 MHz sine; which are clean"""
    bd = b.bd
    rows = skipped_channels(b, "phase")
    b.analog_setup()
    freq = {}
    for port, ch in b.found.paths:
        freq[ch] = bd.dac(port, "sine", freq=ONE_MHZ, shift=1)
    n = b.size("capture_fit")
    worst = {}                                        # (rate, falling edge?, phase) -> the largest residual of any channel, in codes
    for rate, phases in ((25e6, range(8)), (50e6, [0])):      # at 50 MS/s the gateware latches every cycle: the phase does nothing (rtl/adc_capture.v)
        for negedge in (False, True):
            for phase in phases:
                bd.adc_config(rate=rate, phase=phase, negedge=negedge, stats_log2=bench.STATS_LOG2)
                bd.wait(0.01)
                _, ca, cb, _ = bd.capture(n)
                worst[(rate, negedge, phase)] = max(float(abs(analysis.sine_fit(pick(ch, ca, cb), rate, freq[ch])[2]).max()) for _, ch in b.found.paths)
    for port, _ in b.found.paths:
        bd.dac(port, "dc", code=8192)
    b.record("phase_scan", quiet=True, residuals={"%g/%s/%d" % (r / 1e6, "fall" if e else "rise", p): round(v, 1) for (r, e, p), v in worst.items()})

    # 25 MS/s: eight phases on each edge
    best = None                                       # (run length, falling edge?, first, last)
    for negedge in (False, True):
        clean = [worst[(25e6, negedge, p)] < CLEAN_RESIDUAL for p in range(8)]
        run = analysis.widest_run(clean)
        rows.append(row("phase", "25 MS/s, %s edge" % ("falling" if negedge else "rising"),
                        "clean phases: %s (largest residuals %s codes)" % (" ".join(str(p) for p in range(8) if clean[p]) or "none",
                                                                          " ".join("%.0f" % worst[(25e6, negedge, p)] for p in range(8))), "", "info"))
        if run is not None and (best is None or run[1] - run[0] + 1 > best[0]):
            best = (run[1] - run[0] + 1, negedge, run[0], run[1])
    if best is None:
        rows.append(row("phase", "25 MS/s: a clean setting", "none of the 16", "at least one (BRINGUP.md 6.2)", "FAIL",
                        "every setting has samples far off the sine: the ADC's clock (E4 / R2 through their 33 ohm) or a data line; the analog "
                        "tests that follow cannot be trusted"))
    else:
        middle = (best[2] + best[3]) // 2
        rows.append(row("phase", "25 MS/s: recommended", "phase %d, %s edge (the middle of clean phases %d-%d)" % (middle, "falling" if best[1] else "rising", best[2], best[3]),
                        "at least one clean setting (BRINGUP.md 6.2)", "pass"))
        if worst[(25e6, b.adc_negedge, b.adc_phase)] >= CLEAN_RESIDUAL:
            b.adc_phase, b.adc_negedge = middle, best[1]
            rows.append(row("phase", "25 MS/s: used from here on", "phase %d, %s edge" % (middle, "falling" if best[1] else "rising"), "", "info",
                            "the driver's default (phase 2, rising) is not clean on this board: the tests that follow use the recommended one; "
                            "change ecp5bu.adc_config's default"))
    # 50 MS/s: the two edges
    clean_50 = {negedge: worst[(50e6, negedge, 0)] < CLEAN_RESIDUAL for negedge in (False, True)}
    value = "rising %s (%.0f codes), falling %s (%.0f codes)" % ("clean" if clean_50[False] else "NOT clean", worst[(50e6, False, 0)],
                                                                 "clean" if clean_50[True] else "NOT clean", worst[(50e6, True, 0)])
    if clean_50[False] or clean_50[True]:
        rows.append(row("phase", "50 MS/s: the two edges", value, "one clean at least", "pass"))
        if not clean_50[False]:
            b.adc_negedge_50 = True
            rows.append(row("phase", "50 MS/s: used from here on", "the falling edge", "", "info", "the rising edge (the default) is not clean at 50 MS/s on this board"))
    else:
        rows.append(row("phase", "50 MS/s: the two edges", value, "one clean at least", "FAIL",
                        "neither edge gives a clean sine at 50 MS/s: the rows at 50 MS/s that follow cannot be trusted; 25 MS/s is the working rate"))
    b.record("adc_timing", quiet=True, phase=b.adc_phase, negedge=b.adc_negedge, negedge_50=b.adc_negedge_50)     # every later command starts from this
    return rows


DC_CODES = list(range(2048, 14337, 2048))            # 2048 ... 14336: seven DAC codes that keep the ADC well inside its range (512 ... 3584)


def test_dc_transfer(b):
    """the DC path DAC -> cable -> ADC: seven codes, the ADC's mean against the ideal line"""
    bd = b.bd
    rows = skipped_channels(b, "dc_transfer")
    b.analog_setup()
    means = {ch: [] for _, ch in b.found.paths}
    for code in DC_CODES:
        for port, _ in b.found.paths:
            bd.dac(port, "dc", code=code)
        w = b.adc_window()
        for _, ch in b.found.paths:
            means[ch].append(w[ch]["mean"])
    for port, _ in b.found.paths:
        bd.dac(port, "dc", code=8192)
    ideal_from_mid = [(code - 8192) / 4.0 for code in DC_CODES]       # the ideal ADC code is 2048 + (DAC code - 8192) / 4
    for port, ch in b.found.paths:
        slope, at_mid, worst = analysis.fit_line(ideal_from_mid, means[ch])
        offset = at_mid - 2048.0
        name = "DAC %d -> ADC %s" % (port, ch.upper())
        b.record("dc_transfer", quiet=True, port=port, channel=ch, codes=DC_CODES, means=[round(m, 2) for m in means[ch]], slope=slope, offset=offset, worst=worst)
        if slope < 0:
            rows.append(row("dc_transfer", name + ": slope", "%.4f: the path INVERTS (the ADC falls when the DAC rises)" % slope, "+1.00 +-5 %", "FAIL",
                            "one stage has its two outputs swapped: the DAC's IOUTA/IOUTB into the OPA2810, or the THS4521's outputs into the ADC "
                            "(BRINGUP.md's dead-on-arrival list); visit 2's scope on DAC %d OUT says which side" % port))
        else:
            rows.append(row("dc_transfer", name + ": slope", "%.4f" % slope, "1.00 +-5 %", "pass" if abs(slope - 1) <= 0.05 else "FAIL",
                            "" if abs(slope - 1) <= 0.05 else "a gain error: the DAC's FSADJ 2 k and the 24.9 ohm pairs, the 49.9 ohm source and "
                            "termination; visit 2 measures each half against the instruments"))
        rows.append(row("dc_transfer", name + ": offset", "%+.1f ADC codes" % offset, "within 100 codes of mid-scale (BRINGUP.md 6.1)", "pass" if abs(offset) <= 100 else "FAIL",
                        "" if abs(offset) <= 100 else "an offset of %.0f mV at the ADC: an op amp's rails (+5VA, -4V2 at the chip) or a clamp diode conducting" % (offset / 2.048)))
        rows.append(row("dc_transfer", name + ": worst deviation from a line", "%.2f codes" % worst, "under 8", "pass" if worst < 8 else "FAIL",
                        "" if worst < 8 else "the path bends: something clips or a clamp (BAV99) starts to conduct inside +-0.75 V; the log's dc_transfer entry has the seven means"))
    return rows


def test_noise(b):
    """the noise with both DACs at mid-scale: the standard deviation, and the largest tone of the spectrum"""
    rows = []
    b.analog_setup()
    quiet = [ch for ch in ("a", "b") if b.found.adc[ch]["source"] is None or ch in [c for _, c in b.found.paths]]
    for ch in ("a", "b"):
        if ch not in quiet:
            rows.append(row("noise", "ADC %s" % ch.upper(), "not run", "", "skipped", b.found.channel_note(ch)))
    for rate in (25e6, 50e6):
        t, ca, cb, otr = b.capture(rate=rate)
        if rate == 25e6:
            b.record("capture", quiet=True, path=b.save_capture("v1b_noise", t, ca, cb, otr))
        for ch in quiet:
            x = pick(ch, ca, cb)
            label = "ADC %s at %d MS/s" % (ch.upper(), rate / 1e6)
            std = float(x.std())
            rows.append(row("noise", label + ": noise", "%.2f codes rms (mean %.1f)" % (std, float(x.mean())), "under %.0f codes rms" % NOISE_MAX_STD,
                            "pass" if std < NOISE_MAX_STD else "FAIL",
                            "" if std < NOISE_MAX_STD else "the next row names the largest tone; no tone: the ADC's reference or its 3.3 V (U604), or the capture phase"))
            s = analysis.sfdr(x, rate)
            _, amps = analysis.spectrum(x, rate)
            floor = float(sorted(amps)[len(amps) // 2])            # the median bin: the noise floor of this spectrum
            stands_out = s["peak_amp"] >= TONE_ABOVE_FLOOR * floor
            loud = s["peak_amp"] >= SPUR_MAX_CODES
            what = name_spur(s["peak_hz"], s["bin_hz"]) if stands_out else "no tone: it is one of the noise's own bins (their median is %.2f)" % floor
            rows.append(row("noise", label + ": largest bin", "%.2f codes peak at %.3f MHz: %s" % (s["peak_amp"], s["peak_hz"] / 1e6, what),
                            "under %.0f codes peak (BRINGUP.md 6.1)" % SPUR_MAX_CODES, "FAIL" if loud else "info",
                            "the tone's source is named in the value: its inductor, its bead, its return path (a row for REVB.md)" if loud else ""))
    return rows


def test_sine(b):
    """half-scale sines DAC -> ADC at 100 kHz, 1, 5 and 10 MHz, captured at 25 and 50 MS/s: frequency, amplitude, SFDR"""
    bd = b.bd
    rows = skipped_channels(b, "sine")
    b.analog_setup()
    for freq in SINE_FREQS:
        actual = {}
        for port, ch in b.found.paths:
            actual[ch] = bd.dac(port, "sine", freq=test_tone(freq), shift=1)
        for rate in (25e6, 50e6):
            t, ca, cb, otr = b.capture(rate=rate)
            if freq == 1e6 and rate == 25e6:
                b.record("capture", quiet=True, path=b.save_capture("v1b_sine_1MHz", t, ca, cb, otr, dac_freq=actual))
            for port, ch in b.found.paths:
                x = pick(ch, ca, cb)
                s = analysis.sfdr(x, rate)
                pkpk = 2 * analysis.sine_fit(x, rate, actual[ch])[0]     # from the fit: with five samples a period, max - min misses the peaks
                expect_hz = alias(actual[ch], rate)
                problems = []
                if abs(s["peak_hz"] - expect_hz) > s["bin_hz"]:
                    problems.append("the largest tone is not the DAC's frequency: a wrong DAC or ADC clock rate (the clocks test), or the sine is buried")
                if freq <= 1e6 and abs(pkpk / HALF_SCALE_PKPK - 1) > 0.10:
                    problems.append("the amplitude is off: dc_transfer's slope says whether the DC gain is; if only the sine is, a capacitor in the path")
                if freq == 1e6 and s["sfdr_db"] <= SFDR_MIN_DB:
                    problems.append("a spur at %.3f MHz, %.1f codes peak: at 2 or 3 times the tone it is distortion in an output stage or the preamp; "
                                    "at another frequency: %s" % (s["spur_hz"] / 1e6, s["spur_amp"], name_spur(s["spur_hz"], s["bin_hz"])))
                expected = "%.3f MHz +-1 bin" % (expect_hz / 1e6)
                if freq <= 1e6:
                    expected += "; %d codes pp +-10 %%" % HALF_SCALE_PKPK
                if freq == 1e6:
                    expected += "; SFDR over %.0f dBc" % SFDR_MIN_DB
                rows.append(row("sine", "DAC %d -> ADC %s, %g MHz at %d MS/s" % (port, ch.upper(), freq / 1e6, rate / 1e6),
                                "peak %.3f MHz, %.0f codes pp, SFDR %.1f dBc" % (s["peak_hz"] / 1e6, pkpk, s["sfdr_db"]), expected,
                                "FAIL" if problems else "pass", "; ".join(problems)))
    for port, _ in b.found.paths:
        bd.dac(port, "dc", code=8192)
    return rows


def test_fullscale(b):
    """a full-scale DAC sine into the ADC: does it clip, and does the out-of-range flag count when it does"""
    bd = b.bd
    rows = skipped_channels(b, "fullscale")
    b.analog_setup()
    for port, _ in b.found.paths:
        bd.dac(port, "sine", freq=ONE_MHZ, shift=0)
    w = b.adc_window()
    for port, _ in b.found.paths:
        bd.dac(port, "dc", code=8192)
    for port, ch in b.found.paths:
        s = w[ch]
        clips_both_ways = s["min"] <= 0 and s["max"] >= 4095
        value = "codes %d to %d; %d of %d samples flagged out of range" % (s["min"], s["max"], s["otr"], w["n"])
        if clips_both_ways and s["otr"] == 0:
            rows.append(row("fullscale", "DAC %d -> ADC %s, full scale" % (port, ch.upper()), value, "the flag counts when the sine clips", "FAIL",
                            "the sine reaches both rails and the flag never rose: the OTR line of channel %s (adc_%s_otr)" % (ch.upper(), ch)))
        else:
            rows.append(row("fullscale", "DAC %d -> ADC %s, full scale" % (port, ch.upper()), value, "", "info",
                            "a full-scale DAC is exactly the ADC's full scale: a few codes of gain or offset decide whether it clips"))
    return rows


def test_xtalk(b):
    """cross-talk: a sine on one DAC, the other at mid-scale; how much of it the other ADC channel shows"""
    bd = b.bd
    rows = skipped_channels(b, "xtalk")
    for port, ch in b.found.paths:
        other = "b" if ch == "a" else "a"
        b.analog_setup()
        freq = bd.dac(port, "sine", freq=ONE_MHZ, shift=1)
        _, ca, cb, _ = b.capture(rate=25e6)
        driven, _, _ = analysis.sine_fit(pick(ch, ca, cb), 25e6, freq)
        leaked, _, _ = analysis.sine_fit(pick(other, ca, cb), 25e6, freq)
        dbc = analysis.db(leaked / driven) if driven > 0 else 0.0
        rows.append(row("xtalk", "DAC %d on ADC %s: what ADC %s shows at 1 MHz" % (port, ch.upper(), other.upper()),
                        "%.1f dBc (%.2f codes of %.0f)" % (dbc, leaked, driven), "", "info",
                        "above -40 dBc: more than a 12-bit converter pair should leak; a rev B row" if dbc > -40 else ""))
    b.analog_setup()
    return rows


# The DAC's other waveforms at 100 kHz and the ADC codes peak to peak each should give: the sawtooth and the triangle
# are always full scale (rtl/dac_gen.v), the square follows the amplitude shift (1: half scale).
WAVES = [("saw", 0, 4095), ("square", 1, 2047), ("triangle", 0, 4095)]


def test_waves(b):
    """the DAC's sawtooth, square and triangle at 100 kHz: the captured peak to peak"""
    bd = b.bd
    rows = skipped_channels(b, "waves")
    b.analog_setup()
    for mode, shift, expect in WAVES:
        for port, _ in b.found.paths:
            bd.dac(port, mode, freq=100e3, shift=shift)
        _, ca, cb, _ = b.capture(rate=25e6)
        for port, ch in b.found.paths:
            x = pick(ch, ca, cb)
            rows.append(row("waves", "DAC %d %s -> ADC %s" % (port, mode, ch.upper()), "%d codes pp" % int(x.max() - x.min()), "about %d" % expect, "info"))
    b.analog_setup()
    return rows


# ---- last: USB power alone, and the soak --------------------------------------------------------------------------------
USB_POWER_SECONDS = 20.0         # how long the bench supply stays off (BRINGUP.md 2.3)


def test_usb_power(b):
    """the bench supply off for 20 s: USB PROG's 5 V must carry the board (it must keep answering)"""
    if b.sim:
        return [row("usb_power", "running from USB PROG alone", "not run", "", "skipped", OUT_OF_SIM + ": the simulated board is not powered by the fake supply")]
    out = b.cfg["psu"]["out"]
    b.require_supply()
    rows = []
    asked = answered = 0
    try:
        b.psu_output(False, quiet=True)
        t0 = b.now()
        while b.now() - t0 < USB_POWER_SECONDS:
            ok, _ = b.board_answers()
            asked += 1
            answered += ok
            b.sleep(2.0)
    finally:
        b.psu_output(True, quiet=True)                # the supply is never left off
    b.sleep(1.0)
    rows.append(row("usb_power", "with the supply's output off", "answered %d of %d times in %.0f s" % (answered, asked, USB_POWER_SECONDS), "every time",
                    "pass" if answered == asked else "FAIL",
                    "" if answered == asked else "the board dropped out on USB power: F601 or Q602 (the P-FET), or the PC's port limiting below the "
                    "board's 0.6-0.7 A.  If it does not answer below: `bench.py v1b --only load_bringup`"))
    ok, ident = b.board_answers()
    volts, amps = b.psu.measure(out=out)
    rows.append(row("usb_power", "with the supply back on", ("answers; %.3f A at %.2f V" % (amps, volts)) if ok else "does not answer (%s)" % ident, "answers",
                    "pass" if ok else "FAIL", "" if ok else "the supply is ON again; reload: `bench.py v1b --only load_bringup`"))
    return rows


SOAK_CURRENT_DRIFT = 0.05        # BRINGUP.md 1.4: the current flat to 5 %


def test_soak(b):
    """the soak: every 30 s the supply's current, an SDRAM test and the 1 MHz loopback amplitude; what drifted"""
    bd = b.bd
    minutes, every = b.soak_minutes, b.soak_every
    if minutes <= 0:
        return [row("soak", "the soak", "not run", "", "skipped", "0 minutes asked (`--soak-minutes N`; 10 is the bench's default)")]
    out = b.cfg["psu"]["out"]
    latency = b.found.sdram_latency
    if latency is None:
        scan = bd.sdram_scan(b.size("sdram_scan"))
        good = [lat for lat, errors in scan.items() if errors == 0]
        latency = good[len(good) // 2] if good else 3
    b.analog_setup()
    for port, _ in b.found.paths:
        bd.dac(port, "sine", freq=ONE_MHZ, shift=1)
    samples = []
    t_end = b.now() + 60.0 * minutes
    while True:
        volts, amps = b.psu.measure(out=out)
        memory = bd.sdram_test(b.size("sdram_soak"), pattern=len(samples) % 7, rdlat=latency)
        w = b.adc_window()
        s = {"t": round(b.now(), 1), "amps": amps, "volts": volts, "sdram_errors": memory["errors"], "pkpk_a": w["a"]["pkpk"], "pkpk_b": w["b"]["pkpk"]}
        samples.append(s)
        b.record("soak", quiet=True, **s)
        if b.now() >= t_end:
            break
        b.sleep(every)
    for port, _ in b.found.paths:
        bd.dac(port, "dc", code=8192)
    amps = [s["amps"] for s in samples]
    drift = (max(amps) - min(amps)) / amps[0] if amps[0] > 0 else 0.0
    errors = sum(s["sdram_errors"] for s in samples)
    rows = [row("soak", "supply current over %g min, %d samples" % (minutes, len(samples)), "%.3f A at first, %.3f at last (%.3f to %.3f: %.1f %%)" % (amps[0], amps[-1], min(amps), max(amps), 100 * drift),
                "flat to %.0f %% (BRINGUP.md 1.4)" % (100 * SOAK_CURRENT_DRIFT), "pass" if drift <= SOAK_CURRENT_DRIFT else "FAIL",
                "" if drift <= SOAK_CURRENT_DRIFT else "a slow rise is a part heating: the IR camera now (U604 and the PHY are allowed warm)"),
            row("soak", "SDRAM, %d tests of %d words" % (len(samples), b.size("sdram_soak")), "%d errors" % errors, "0", "pass" if errors == 0 else "FAIL",
                "" if errors == 0 else "errors that come with time are heat or refresh: the log's soak entries say when they began")]
    for port, ch in b.found.paths:
        pkpk = [s["pkpk_" + ch] for s in samples]
        rows.append(row("soak", "1 MHz loopback DAC %d -> ADC %s" % (port, ch.upper()), "%d codes pp at first, %d at last (%d to %d)" % (pkpk[0], pkpk[-1], min(pkpk), max(pkpk)),
                        "", "info", "the drift of the analog path's gain while the board warms"))
    return rows


# ---- the list, and the run -----------------------------------------------------------------------------------------------
# (name, function, what it needs).  The needs: "hardware" = not in simulation; "board" = the board answers;
# "analog" = a DAC reaches an ADC at x1; the rest are Found's attributes.  The first four load the FPGA and run
# BEFORE verify (verify needs bringup.bit running); the others after it, in this order.
LOADING = ("jtag", "load_blink", "load_bringup", "flash")
V1B_TESTS = [
    ("jtag",         test_jtag,         ()),
    ("load_blink",   test_load_blink,   ()),
    ("load_bringup", test_load_bringup, ()),
    ("flash",        test_flash,        ()),
    ("bus",          test_bus,          ("board",)),
    ("current",      test_current,      ("board",)),
    ("clocks",       test_clocks,       ("board",)),
    ("si5351",       test_si5351,       ("board",)),
    ("clkloop",      test_clkloop,      ("board", "clk_cable")),
    ("sdram",        test_sdram,        ("board",)),
    ("phy",          test_phy,          ("board",)),
    ("eth_loop",     test_eth_loop,     ("board",)),
    ("eth_wire",     test_eth_wire,     ("board", "link")),
    ("sd",           test_sd,           ("board", "card")),
    ("usb",          test_usb,          ("board", "usb_host")),
    ("hdmi",         test_hdmi,         ("board", "monitor")),
    ("pmod",         test_pmod,         ("board", "pmod_loop")),
    ("phase",        test_phase,        ("board", "analog")),
    ("dc_transfer",  test_dc_transfer,  ("board", "analog")),
    ("noise",        test_noise,        ("board",)),
    ("sine",         test_sine,         ("board", "analog")),
    ("fullscale",    test_fullscale,    ("board", "analog")),
    ("xtalk",        test_xtalk,        ("board", "analog")),
    ("waves",        test_waves,        ("board", "analog")),
    ("usb_power",    test_usb_power,    ("board",)),
    ("soak",         test_soak,         ("board",)),
]
NEED_WORDS = {"board": "the board does not answer (verify)", "clk_cable": "no cable from CLK OUT to CLK IN (verify)", "card": "no microSD card (verify)",
              "usb_host": "USB USER is not on a host (verify)", "link": "no Ethernet link (verify)", "monitor": "no monitor (verify)",
              "pmod_loop": "no Pmod loop (verify)", "analog": "no DAC reaches an ADC at gain x1 with the 50 ohm in (verify)"}


def choose_tests(tests, only, skip):
    """The tests to run, from --only and --skip (comma-separated names).  An unknown name stops the command."""
    names = [name for name, _, _ in tests]
    only = [x for x in only.split(",") if x]
    skip = [x for x in skip.split(",") if x]
    unknown = [x for x in only + skip if x not in names]
    if unknown:
        raise bench.Refused("No test named %s.  The tests: %s." % (", ".join(unknown), ", ".join(names)))
    return [t for t in tests if (not only or t[0] in only) and t[0] not in skip]


def missing_need(found, needs):
    """The first thing a test needs that verify did not find, in words; None when it can run."""
    for need in needs:
        have = bool(found.paths) if need == "analog" else getattr(found, need)
        if not have:
            return NEED_WORDS[need]
    return None


def print_test_list(tests):
    for name, function, needs in tests:
        print("  %-13s %s%s" % (name, function.__doc__.strip().split("\n")[0], ("   [needs: %s]" % ", ".join(needs)) if needs else ""))


def v1b(b, a):
    """Visit 1, step B.  Cabled: the supply still on; USB PROG and USB USER to the PC; three SMA cables (CLK OUT to
    CLK IN, DAC 1 OUT to ADC A IN, DAC 2 OUT to ADC B IN; crossed is accepted); Ethernet to the lab switch; a
    microSD card.  Loads the FPGA and its flash, finds out what is plugged in (one table), then runs every test in
    V1B_TESTS; a test whose cable is absent is skipped with a line saying so.  The result is the table and the
    report file: the exit status is 0 even with FAIL rows."""
    if a.list:
        print("v1b's tests, in the order they run (the first four load the FPGA, then verify, then the rest):")
        print_test_list(V1B_TESTS)
        return 0
    tests = choose_tests(V1B_TESTS, a.only, a.skip)
    b.stage = b.stage or "v1b"
    b.soak_minutes = a.soak_minutes if a.soak_minutes is not None else (0.0 if b.sim else 10.0)     # 10 minutes on the bench, none simulated
    b.soak_every = a.soak_every
    res = Results(b, "v1b")
    print("v1b board %s%s: %d tests%s." % (b.board, " (SIMULATED)" if b.sim else "", len(tests), "" if not (a.only or a.skip) else " (" + ", ".join(t[0] for t in tests) + ")"))
    try:
        for name, function, _ in tests:
            if name in LOADING:
                res.run(name, function, b)
        print("\n== verify: what is plugged in", flush=True)
        try:
            b.found, rows = verify_v1b(b)
        except Exception as e:                        # noqa: BLE001: verify failing must not cost the report
            import traceback
            b.record("exception", quiet=True, test="verify", traceback=traceback.format_exc())
            b.found, rows = Found(), [row("verify", "verify itself", "%s: %s" % (type(e).__name__, e), "to run to its end", "FAIL",
                                          "nothing is known about the cabling, so every test that needs a cable is skipped; the traceback is in the log")]
            b.found.board = b.board_answers()[0]
        res.add(rows)
        for name, function, needs in tests:
            if name in LOADING:
                continue
            why_not = missing_need(b.found, needs)
            if why_not:
                res.skip(name, why_not)
            else:
                res.run(name, function, b)
    except KeyboardInterrupt:
        print("\ninterrupted: the report holds what was done so far")
    finally:
        try:
            if b.found is not None and b.found.board:
                b.analog_setup()                      # both DACs back at 0 V, whatever stopped the run
                b.bd.clkout("tcxo")
        except Exception:                             # noqa: BLE001
            pass
    res.finish()
    return 0


# =================================================================================================================
# coldboot: power cycles with both USB cables out
# =================================================================================================================
OFF_BELOW_VOLTS = 0.3            # the output counts as off when the supply measures less than this ...
OFF_WAIT_SECONDS = 3.0           # ... or after this long (the board's capacitors run down in a fraction of a second)
BOOT_SECONDS = 2.0               # after power-on: the FPGA configures from its flash within a second (BRINGUP.md 3.3)
CYCLES_AGREE = 0.05              # the cycles' currents must agree within 5 %
SAME_AS = 0.03                   # two currents within 3 % are "the same"
BOOTED_ABOVE = 0.05              # a board that configured itself draws at least 5 % more than it did unconfigured (a guess until measured)


def coldboot(b, a):
    """Visit 2, step 1.  Cabled: the supply on J601; BOTH USB-C cables pulled (with USB PROG in, the PC's port keeps
    the board alive through the power cycle); the rest as visit 1B left it.  Switches the supply off and on `--n`
    times and reads the current 2 s after each power-on.  The board cannot be reached, so the current is the only
    witness: the cycles must agree within 5 %, and the level is compared with what this board drew unconfigured
    (v1a) and running bringup.bit (v1b), if its log has them."""
    b.stage = b.stage or "3.3"
    res = Results(b, "coldboot")
    out = b.cfg["psu"]["out"]
    b.require_supply()
    b.psu_setup(bench.SUPPLY_V, bench.SUPPLY_A)
    print("coldboot: %d power cycles on E3646A output %d; the white LEDs should restart their chase each time." % (a.n, out))
    currents = []
    stopped = False
    for k in range(1, a.n + 1):
        b.psu_output(False, quiet=True)
        t0 = b.now()
        while b.now() - t0 < OFF_WAIT_SECONDS:
            volts, _ = b.psu.measure(out=out)
            if volts < OFF_BELOW_VOLTS:
                break
            b.sleep(0.1)
        b.psu_output(True, quiet=True)
        b.sleep(BOOT_SECONDS)
        volts, amps = b.psu.measure(out=out)
        mode = b.psu.mode(out=out)
        b.record("coldboot", quiet=True, cycle=k, volts=volts, amps=amps, mode=mode)
        if mode != "CV":
            b.psu_output(False, quiet=True)
            stopped = True
            res.add(row("coldboot", "cycle %d" % k, "%.3f A at %.2f V, %s" % (amps, volts, mode), "constant voltage", "FAIL",
                        "the supply is not in constant voltage 2 s after power-on: its output is OFF.  It ran before this cycle, so look for "
                        "what a power cycle can latch (the -4V2 pump, a regulator's start into a charged rail); `bench.py v1a` starts over gently"))
            break
        currents.append(amps)
        res.add(row("coldboot", "cycle %d" % k, "%.3f A at %.2f V" % (amps, volts), "", "info"))
    if currents:
        mean = sum(currents) / len(currents)
        spread = (max(currents) - min(currents)) / mean if mean > 0 else 0.0
        res.add(row("coldboot", "the %d cycles agree" % len(currents), "%.3f to %.3f A (%.1f %%)" % (min(currents), max(currents), 100 * spread),
                    "within %.0f %%" % (100 * CYCLES_AGREE), "pass" if spread <= CYCLES_AGREE else "FAIL",
                    "" if spread <= CYCLES_AGREE else "some cycles drew less: the board did not configure itself every time.  Did the LEDs chase "
                    "after every power-on?  The low cycles are the ones that failed (the 100 nF on PROGRAMN, the flash's power-up time: review R8)"))
        unconfigured = b.log.latest("current_ref", state="unconfigured")
        running = b.log.latest("current_ref", state="bringup")
        if unconfigured is None:
            res.add(row("coldboot", "against the unconfigured board", "no such current in this board's log", "", "info",
                        "`v1a` logs it the first time the board is powered; without it the LEDs are the only witness that it booted"))
        else:
            ratio = mean / unconfigured["amps"] if unconfigured["amps"] > 0 else 0.0
            value = "%.3f A now, %.3f A unconfigured (%s): %+.1f %%" % (mean, unconfigured["amps"], unconfigured["t"][:10], 100 * (ratio - 1))
            if abs(ratio - 1) <= SAME_AS:
                res.add(row("coldboot", "against the unconfigured board", value, "at least %.0f %% more" % (100 * BOOTED_ABOVE), "FAIL",
                            "the board draws what it drew with the FPGA unconfigured: it did not boot from its flash.  Plug USB PROG back in and "
                            "`bench.py v1b --only jtag,flash,bus`; if the flash verifies and it still does not boot: the CFG pins (010), PROGRAMN's 100 nF"))
            elif ratio - 1 >= BOOTED_ABOVE:
                res.add(row("coldboot", "against the unconfigured board", value, "at least %.0f %% more" % (100 * BOOTED_ABOVE), "pass",
                            "it draws more than an unconfigured board: it configured itself from its flash"))
            else:
                res.add(row("coldboot", "against the unconfigured board", value, "at least %.0f %% more" % (100 * BOOTED_ABOVE), "info",
                            "between the two: the current alone cannot say.  Did the LEDs chase?"))
        if running is not None:
            res.add(row("coldboot", "against bringup.bit with USB plugged", "%.3f A now, %.3f A then (%+.0f %%)" % (mean, running["amps"], 100 * (mean / running["amps"] - 1)),
                        "", "info", "a little less is expected: without a host the FT2232H sleeps"))
    res.finish()
    if stopped:
        print("\nThe supply's output is OFF.")
    elif res.failures():
        print("\nThe supply is ON at 5.0 V.  Next for Jason: plug both USB-C cables back in; the FAIL above comes before the visit-2 cabling.")
    else:
        print("\nThe supply is ON at 5.0 V.  Next for Jason: plug both USB-C cables back in, then the visit-2 cabling.")
    return 0
