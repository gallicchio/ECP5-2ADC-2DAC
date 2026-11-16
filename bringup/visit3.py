"""visit3.py: visit 3 of ../BRINGUP.md, the sit-down session: `bench.py step NAME`, one change on the board each.

The person moves one thing (a shunt, a pigtail, a probe) and says "next"; the session runs the step.  Every step
prints first ONE sentence saying what must have been moved, then measures, then says what to put back.  The
cabling is visit 2's: SDG CH1 and the 33220A on the two ADC inputs, the scope on the DAC outputs and CLK OUT.
Each generator step drives one generator at a time and looks at which ADC channel answers, so it does not
matter which generator is on which input.

    python3 bringup/bench.py step --list
    python3 bringup/bench.py step gain_x10

Under --sim the simulated bench is first changed as the step expects (simbench.SimBench.set_for_step);
`--sim-as-found` leaves it alone, so the "you did not move it" finding of each step can be seen.
"""
import analysis
import bench
import visit1
import visit2
from report import Results, row

GAIN_X10, GAIN_X100 = 10.1, 102.0        # one stage out, both stages out (BRINGUP.md 6.5)
GAIN_TOLERANCE = 0.08                    # the measured gain within 8 % of that (two 1 % resistors a stage, and the generator's 1 %)
STEP_HZ = 100e3                          # every generator step uses 100 kHz: far below any corner of the chain
CODES_PER_VOLT = 2048.0                  # ADC codes per volt at the SMA at gain x1 (+-1 V is 4096 codes)
NOISE_PKPK = 12                          # ADC codes: more than the noise's own peak to peak at x1 over 4096 samples (about 6 at 0.7 codes rms)


def seen_codes(vpp):
    """How many codes peak to peak an ADC channel must swing to count as "this generator reaches it" when the
    generator gives `vpp`: half of what `vpp` makes at gain x1, but never less than the noise.  A fixed number
    will not do: the x100 step drives 10 mVpp, which is only 20 codes if the shunts were not pulled."""
    return max(NOISE_PKPK, 0.5 * vpp * CODES_PER_VOLT)


def channel_jumpers(ch):
    """The jumper names of one ADC channel: {'term', 'src', 'gain1', 'gain2'}."""
    n = 1 if ch == "a" else 2
    return {"term": "JP%d01" % n, "src": "JP%d02" % n, "gain1": "JP%d03" % n, "gain2": "JP%d04" % n}


def each_generator(b, vpp):
    """Each of the two ADC generators alone at `vpp` (into 50 ohm), 100 kHz: yields (source, channel it reaches or
    None, that channel's statistics, the other channel's)."""
    b.analog_setup()
    for src in ("sdg1", "hp"):
        b.tone(src, STEP_HZ, vpp)
        b.sleep(0.3)
        w = b.adc_window()
        b.tone_off(src)
        best = "a" if w["a"]["pkpk"] >= w["b"]["pkpk"] else "b"
        if w[best]["pkpk"] < seen_codes(vpp):
            yield src, None, w["a"], w["b"]
        else:
            yield src, best, w[best], w["b" if best == "a" else "a"]


def gain_rows(b, test, vpp, want_gain):
    """Both channels against their generators at one gain setting."""
    rows = []
    want_setting = 10 if want_gain < 50 else 100      # the jumper setting's name: x10 (really 10.1) or x100 (102)
    for src, ch, s, other in each_generator(b, vpp):
        name = visit2.SOURCE_NAME[src]
        if ch is None:
            rows.append(row(test, "%s at %.0f mVpp" % (name, 1000 * vpp), "no ADC channel swings clearly (%d and %d codes pp)" % (s["pkpk"], other["pkpk"]), "a channel at x%g" % want_gain, "FAIL",
                            "at gain x1 this %.0f mVpp would be only %.0f codes, so first: were the GAIN shunts pulled?  If they were, this generator "
                            "reaches no ADC input: its cable, and that channel's SRC jumper on SMA" % (1000 * vpp, vpp * CODES_PER_VOLT)))
            continue
        jp = channel_jumpers(ch)
        gain = s["pkpk"] / (vpp * CODES_PER_VOLT)
        clipped = s["min"] <= 0 or s["max"] >= 4095
        ok = not clipped and abs(gain / want_gain - 1) <= GAIN_TOLERANCE
        value = "%d codes pp: gain x%.1f%s" % (s["pkpk"], gain, " (CLIPPED: the gain is higher still)" if clipped else "")
        expected = "x%g +-%.0f %% (%.0f codes pp for %.0f mVpp)" % (want_gain, 100 * GAIN_TOLERANCE, vpp * CODES_PER_VOLT * want_gain, 1000 * vpp)
        note = ""
        if not ok:
            state = analysis.jumper_state(gain)
            if clipped:
                note = "channel %s is at more gain than x%g: both %s and %s are out?" % (ch.upper(), want_gain, jp["gain1"], jp["gain2"])
            elif state is not None and state["gain"] != want_setting and state["term"]:
                note = "channel %s is at gain x%d: %s" % (ch.upper(), state["gain"], {1: "the shunt of %s was not pulled" % jp["gain1"],
                                                                                    10: "only one of %s and %s is out" % (jp["gain1"], jp["gain2"]),
                                                                                    100: "both %s and %s are out" % (jp["gain1"], jp["gain2"])}[state["gain"]])
            elif state is not None and not state["term"]:
                note = "twice what the gain alone gives: the TERM shunt %s of channel %s is out" % (jp["term"], ch.upper())
            elif gain < 0.2 * want_gain:
                # far too little, and no setting fits exactly: at 10 mVpp a channel still at x1 swings only 20 codes, and its
                # noise can push that reading outside the x1 window.  The likely cause is still the shunts.
                note = ("far below x%g (about x%.0f): were the GAIN shunts of channel %s pulled (%s%s)?"
                        % (want_gain, gain, ch.upper(), jp["gain1"], " and " + jp["gain2"] if want_setting == 100 else ""))
            else:
                note = "no jumper setting gives this: the feedback resistors of channel %s's stage (1 k and 9.1 k), or a shunt half on" % ch.upper()
        rows.append(row(test, "%s -> ADC %s at %.0f mVpp" % (name, ch.upper(), 1000 * vpp), value, expected, "pass" if ok else "FAIL", note))
    return rows


# ---- the steps: each takes (b, a) and returns rows ------------------------------------------------------------------
def step_leds(b, a):
    """the eight white LEDs one at a time, then all, then the RGB LED red, green, blue"""
    bd = b.bd
    for k in range(8):
        bd.leds(1 << k)
        b.sleep(0.5)
    bd.leds(0xFF)
    b.sleep(1.0)
    for rgb in (1, 2, 4):
        bd.leds(0, rgb=rgb)
        b.sleep(1.0)
    bd.leds(None)
    return [row("leds", "LED0 to LED7, all eight, then red, green, blue", "driven in that order (0.5 s each, 1 s each colour); the chaser is back", "", "info",
                "needs eyes: did every LED light, one at a time and in order, and the RGB LED show three colours?")]


def step_buttons(b, a):
    """BTN0 and BTN1: both must be seen pressed"""
    seen = b.bd.wait_buttons(timeout=a.seconds)
    rows = []
    for key, name, ref in (("btn0", "BTN0", "SW301"), ("btn1", "BTN1", "SW302")):
        rows.append(row("buttons", name, "seen pressed" if seen[key] else "not seen in %.0f s" % a.seconds, "pressed", "pass" if seen[key] else "FAIL",
                        "" if seen[key] else "press %s (%s, top edge) for half a second while the step runs; pressed and still not seen: its FPGA pin and pull-up" % (name, ref)))
    return rows


PROG_MARK = 0xC0FFEE01           # a word left in the scratch register: a reconfigured FPGA has 0 there again


def step_prog(b, a):
    """SW303 PROG: the FPGA must drop its configuration and load it again from the flash"""
    if b.sim:
        return [row("prog", "SW303 PROG", "not run", "", "skipped", visit1.OUT_OF_SIM + ": the simulated board has no PROG button")]
    bd = b.bd
    bd.wr("SCRATCH", PROG_MARK)
    if bd.rd("SCRATCH") != PROG_MARK:
        return [row("prog", "SW303 PROG", "the scratch register does not hold a word", "", "FAIL", "the register bus itself: `bench.py v1b --only bus`")]
    t0 = b.now()
    silent = False
    while b.now() - t0 < a.seconds:
        try:
            if bd.rd("SCRATCH") != PROG_MARK:
                return [row("prog", "SW303 PROG", "the FPGA reconfigured %s(the scratch register is empty again)" % ("after going silent " if silent else ""),
                            "a reboot from the flash", "pass")]
        except IOError:
            silent = True                             # no answer: it is loading its bitstream
            try:
                bd.resync()
            except IOError:
                pass
        b.sleep(0.2)
    return [row("prog", "SW303 PROG", "no reboot seen in %.0f s%s" % (a.seconds, " (the board went silent and did not come back)" if silent else ""),
                "a reboot from the flash", "FAIL",
                "pressed and nothing happened: SW303 and PROGRAMN's 100 nF.  Silent and not back: the flash does not boot (`coldboot` says the same): "
                "`bench.py v1b --only load_bringup` to go on")]


def step_gain_x10(b, a):
    """both channels at gain x10: 100 mVpp from each generator must read as 1 Vpp"""
    return gain_rows(b, "gain_x10", 0.100, GAIN_X10)


def step_gain_x100(b, a):
    """both channels at gain x100: 10 mVpp must read as 1 Vpp; then the noise with the generators off"""
    rows = gain_rows(b, "gain_x100", 0.010, GAIN_X100)       # 10 mVpp is the 33220A's smallest amplitude into 50 ohm
    _, ca, cb, _ = b.capture(rate=25e6)
    for ch, x in (("a", ca), ("b", cb)):
        rows.append(row("gain_x100", "ADC %s noise at x100, generators off" % ch.upper(), "%.2f codes rms" % float(x.std()), "", "info",
                        "BRINGUP.md 6.5: the chain's own noise at x100 is about 0.8 codes rms on top of the x1 floor"))
    return rows


def step_term_open(b, a):
    """channel A with its 50 ohm shunt out: the generator's amplitude must double"""
    rows = []
    vpp = 0.5                                         # into 50 ohm; unloaded it is 1 Vpp at the input: half of full scale
    saw_a = False
    for src, ch, s, other in each_generator(b, vpp):
        if ch is None:
            continue
        ratio = s["pkpk"] / (vpp * CODES_PER_VOLT)
        if ch == "a":
            saw_a = True
            ok = abs(ratio / 2.0 - 1) <= GAIN_TOLERANCE
            rows.append(row("term_open", "%s -> ADC A, JP101 out" % visit2.SOURCE_NAME[src], "%d codes pp: %.2f times the terminated amplitude" % (s["pkpk"], ratio),
                            "twice (%.0f codes pp for %.1f Vpp set into 50 ohm)" % (2 * vpp * CODES_PER_VOLT, vpp), "pass" if ok else "FAIL",
                            "" if ok else ("the amplitude is as with the termination in: JP101's shunt was not pulled" if abs(ratio - 1) <= 0.15 else
                                           "neither once nor twice: is a GAIN shunt of channel A still out?")))
        else:
            rows.append(row("term_open", "%s -> ADC B (its shunt JP201 in)" % visit2.SOURCE_NAME[src], "%d codes pp: %.2f times" % (s["pkpk"], ratio), "once", "info"))
    if not saw_a:
        rows.append(row("term_open", "ADC A", "no generator makes it swing", "twice the terminated amplitude", "FAIL", "the cable on ADC A IN, and JP102 on SMA"))
    return rows


NOISE_10K_CODES = 9.3            # 10 kohm at x100: 12.9 nV/rtHz x sqrt(12 MHz) x 102 = 4.6 mV rms = 9.3 codes (BRINGUP.md 6.8)
NOISIER = 1.5                    # "measurably noisier": the 10 k reading at least 1.5 times the 0 ohm reading


def _noise_now(b):
    b.analog_setup()
    _, ca, _, _ = b.capture(rate=25e6)
    return float(ca.std())


def step_noise_0(b, a):
    """channel A at x100 on the noise source's 0 ohm: the amplifiers alone"""
    std = _noise_now(b)
    b.record("noise_ref", quiet=True, resistor="0", std=std)
    return [row("noise_0", "ADC A, x100, SW101 at 0 ohm", "%.2f codes rms" % std, "about 1 code: the amplifiers and the ADC alone", "info",
                "kept in the log: `step noise_10k` compares with it")]


def step_noise_10k(b, a):
    """channel A at x100 on the noise source's 10 kohm: its Johnson noise against the 0 ohm reading"""
    std = _noise_now(b)
    b.record("noise_ref", quiet=True, resistor="10k", std=std)
    rows = [row("noise_10k", "ADC A, x100, SW101 at 10 kohm", "%.2f codes rms" % std, "about %.0f codes: 12.9 nV/rtHz over 12 MHz, times 102" % NOISE_10K_CODES, "info")]
    ref = b.log.latest("noise_ref", resistor="0")
    if ref is None:
        rows.append(row("noise_10k", "10 kohm against 0 ohm", "no 0 ohm reading in this board's log", "", "info", "run `bench.py step noise_0` first (SW101 switch 1 on)"))
        return rows
    ratio = std / ref["std"] if ref["std"] > 0 else 0.0
    ok = ratio >= NOISIER
    rows.append(row("noise_10k", "10 kohm against 0 ohm", "%.1f times the noise (%.2f against %.2f codes rms)" % (ratio, std, ref["std"]),
                    "at least %.1f times (BRINGUP.md 6.8: measurably noisier)" % NOISIER, "pass" if ok else "FAIL",
                    "" if ok else "the 10 k makes no more noise than the short: is SW101's switch 4 on and switch 1 off, JP102 on ALT, and JP103 and JP104 both out (x100)?"))
    return rows


LIGHT_CODES = ((0, "LED off"), (8192, "24 mA"), (12288, "36 mA"))      # DAC 1 codes and the LED current each makes (BRINGUP.md 5.4: 0 to 48 mA)
LIGHT_MIN_STEP = 5.0             # ADC codes: a change of the mean smaller than this is no change


def step_light(b, a):
    """first light: DAC 1 drives the on-board LED, the photodiode feeds channel B; B's mean must rise with the light"""
    bd = b.bd
    b.analog_setup()
    means = []
    try:
        for code, _ in LIGHT_CODES:
            bd.dac(1, "dc", code=code)
            b.sleep(0.3)
            means.append(b.adc_window()["b"]["mean"])
    finally:
        bd.dac(1, "dc", code=0)                       # the LED off
    rows = [row("light", "DAC 1 code %d (%s)" % (code, what), "ADC B mean %.1f" % m, "", "info") for (code, what), m in zip(LIGHT_CODES, means)]
    steps = [means[1] - means[0], means[2] - means[1]]
    value = "%+.0f then %+.0f codes" % (steps[0], steps[1])
    if all(s >= LIGHT_MIN_STEP for s in steps):
        rows.append(row("light", "channel B follows the LED", value + ": it rises with the light", "rising with the code", "pass",
                        "%.1f codes per mA between 24 and 36 mA (BRINGUP.md 6.7: log it)" % (steps[1] / 12.0)))
    elif all(s <= -LIGHT_MIN_STEP for s in steps):
        rows.append(row("light", "channel B follows the LED", value + ": it FALLS with the light", "rising with the code", "info",
                        "the light is seen; the sign is the opposite of BRINGUP.md 6.7 (the receiver inverts): a matter for the document, not a fault"))
    else:
        rows.append(row("light", "channel B follows the LED", value + ": it does not follow", "rising with the code", "FAIL",
                        "is JP2009 on LED (is the red LED D201 lit at code 8192?), JP202 on ALT, JP1203 on PHOTODIODE?  All three right: the photodiode D103's "
                        "polarity and the receiver U105 (`step tap_tia` looks at its output)"))
    return rows


def _generator_for(b, ch, vpp):
    """Switch on, at `vpp` and 100 kHz, the generator that reaches ADC channel `ch`; returns its name, or None
    (then both are off)."""
    b.analog_setup()
    for src in ("sdg1", "hp"):
        b.tone(src, STEP_HZ, vpp)
        b.sleep(0.3)
        if b.adc_window()[ch]["pkpk"] >= seen_codes(vpp):
            return src
        b.tone_off(src)
    return None


def tap_rows(b, test, ch):
    """A preamp tap on scope CH4: 1 Vpp at 100 kHz on the SMA must be 1.0 Vpp at the tap (gain x1, 1 Mohm)."""
    b.require(["SDS2104X:4"], "scope CH4's settings")
    saved = visit2.save_scope(b, (4,))
    rows = []
    src = None
    try:
        visit2.scope_setup(b, 4, scale=0.2)           # 1 Vpp over 5 of the 8 divisions
        b.scope.timebase(scale=visit2.timebase_for(STEP_HZ))
        b.scope.trigger(source=4, level=0.0, slope="rising", mode="auto")
        src = _generator_for(b, ch, 1.0)
        if src is None:
            rows.append(row(test, "TAP %s" % ch.upper(), "no generator reaches ADC %s" % ch.upper(), "", "FAIL", "the generator's cable on ADC %s IN, its SRC jumper on SMA" % ch.upper()))
        else:
            m = b.scope_read(4, ["PKPK", "FREQ"])
            pkpk = m["PKPK"]
            ok = pkpk is not None and abs(pkpk - 1.0) <= 0.10
            rows.append(row(test, "TAP %s on scope CH4, 1 Vpp on the SMA" % ch.upper(),
                            "no reading" if pkpk is None else "%.2f Vpp%s" % (pkpk, "" if m["FREQ"] is None else " at %.1f kHz" % (m["FREQ"] / 1e3)),
                            "1.0 Vpp +-10 % (the preamp's output at x1, into 1 Mohm)", "pass" if ok else "FAIL",
                            "" if ok else ("nothing on CH4: is the pigtail on the U.FL of TAP %s and on scope CH4?" % ch.upper() if pkpk is None or pkpk < 0.1 else
                                           "half: something loads the tap with 50 ohm.  Otherwise: a GAIN shunt of this channel still out, or the preamp (compare `v2 --only adc_abs`)")))
    finally:
        if src is not None:
            b.tone_off(src)
        rows.append(visit2.restore_scope(b, saved, (4,)))
    return rows


def step_tap(b, a):
    """TAP A (J107) on scope CH4: the preamp's output of channel A"""
    return tap_rows(b, "tap", "a")


def step_tap_b(b, a):
    """TAP B (J108) on scope CH4: the preamp's output of channel B"""
    return tap_rows(b, "tap_b", "b")


def step_tap_tia(b, a):
    """TAP TIA (J109) on scope CH4: the photodiode receiver's output, LED off and LED on"""
    b.require(["SDS2104X:4"], "scope CH4's settings")
    bd = b.bd
    saved = visit2.save_scope(b, (4,))
    rows = []
    try:
        visit2.scope_setup(b, 4, scale=0.5)
        b.scope.timebase(scale=1e-3)
        b.scope.trigger(mode="auto")
        b.analog_setup()
        levels = []
        for code, what in ((0, "LED off"), (12288, "LED at 36 mA")):
            bd.dac(1, "dc", code=code)
            v = b.scope_read(4, ["MEAN"])["MEAN"]
            levels.append(v)
            rows.append(row("tap_tia", "TAP TIA, %s" % what, "no reading" if v is None else "%+.3f V" % v, "", "info"))
        if None not in levels:
            moved = levels[1] - levels[0]
            rows.append(row("tap_tia", "the receiver follows the LED", "%+.0f mV from dark to 36 mA" % (1000 * moved), "a clear change (over 50 mV)", "pass" if abs(moved) >= 0.05 else "FAIL",
                            "" if abs(moved) >= 0.05 else "the receiver's output does not move with the light: JP2009 on LED?  the pigtail on J109?  then D103's polarity and U105"))
    finally:
        bd.dac(1, "dc", code=0)                       # the LED off
        rows.append(visit2.restore_scope(b, saved, (4,)))
    return rows


def step_tap_n4v2(b, a):
    """TAP -4V2 (J603) on scope CH4, AC coupled: the charge pump's 2 MHz residue"""
    b.require(["SDS2104X:4"], "scope CH4's settings")
    saved = visit2.save_scope(b, (4,))
    rows = []
    try:
        visit2.scope_setup(b, 4, scale=0.02, coupling="AC")   # 20 mV/div, AC (BRINGUP.md 1.6)
        b.scope.timebase(scale=1e-6)                           # 1 us/div: two periods of 2 MHz a division
        b.scope.trigger(source=4, level=0.0, slope="rising", mode="auto")
        m = b.scope_read(4, ["PKPK", "FREQ"])
        rows.append(row("tap_n4v2", "-4V2's ripple on scope CH4", "no reading" if m["PKPK"] is None else "%.1f mVpp%s" % (1000 * m["PKPK"], "" if m["FREQ"] is None else " at %.2f MHz" % (m["FREQ"] / 1e6)),
                        "a few millivolts at 2 MHz (BRINGUP.md 1.6)", "info", "the number goes in the log; tens of millivolts would be a row for REVB.md"))
        shot = b.scope_shot("tap_n4v2", quiet=True)
        rows.append(row("tap_n4v2", "screenshot", shot.replace(bench.HERE + "/", ""), "", "info"))
    finally:
        rows.append(visit2.restore_scope(b, saved, (4,)))
    return rows


RAIL_3V3_READY = 3.0             # +3V3 "up": above the flash's and the FPGA's I/O thresholds (BRINGUP.md 1.5)
RAIL_1V1_READY = 1.0             # +1V1 "up": the core past its power-on reset
REALTEK_MIN_RISE = 0.5e-3        # review R2-12: the PHY asks for a 3.3 V rise slower than 0.5 ms
SAME_TIME = 0.1e-3               # "before or with": within 0.1 ms
MAX_WAVEFORM_POINTS = 2_000_000  # a longer record than this takes too long to fetch twice a cycle: then only the scope's own numbers are used


def step_poweron(b, a):
    """the power-on sequence on the scope: +3V3 (CH1) against +1V1 (CH2) while the supply switches on"""
    out = b.cfg["psu"]["out"]
    b.require_supply()
    b.require(["SDS2104X:1", "SDS2104X:2"], "scope CH1 and CH2's settings")
    saved = visit2.save_scope(b, (1, 2))
    rows = []
    rise_3v3, rise_1v1, lead = [], [], []
    try:
        visit2.scope_setup(b, 1, scale=1.0, offset=-2.0, probe=10)    # +3V3: 0 to 3.3 V, two divisions below the middle to 1.3 above
        visit2.scope_setup(b, 2, scale=0.5, offset=-1.0, probe=10)    # +1V1: 0 to 1.1 V
        b.scope.timebase(scale=2e-3, delay=3 * 2e-3)                  # 2 ms/div (BRINGUP.md 1.5), the trigger two divisions from the left edge
        b.scope.trigger(source=1, level=1.0, slope="rising", mode="normal")
        fetch = b.scope.acquire()["points"] <= MAX_WAVEFORM_POINTS
        for cycle in range(1, a.n + 1):
            b.psu_output(False, quiet=True)
            t0 = b.now()
            while b.now() - t0 < visit1.OFF_WAIT_SECONDS:
                if b.psu.measure(out=out)[0] < visit1.OFF_BELOW_VOLTS:
                    break
                b.sleep(0.1)
            b.sleep(1.0)                              # the rails all the way down
            b.scope.arm()
            b.psu_output(True, quiet=True)
            try:
                b.scope.wait_stop(timeout=5.0)
            except TimeoutError:
                rows.append(row("poweron", "cycle %d" % cycle, "the scope did not trigger", "a trigger on +3V3 rising through 1 V", "FAIL",
                                "is the CH1 probe hooked on RAILS pin 3 (+3V3), its ground on pin 4, and its switch at 10x?  The supply is ON"))
                break
            if fetch:
                t1, v1, _ = b.scope.waveform(1)
                t2, v2, _ = b.scope.waveform(2)
                r1, low1, high1 = analysis.rise_time(t1, v1)
                r2, low2, high2 = analysis.rise_time(t2, v2)
                if not (abs(low1) < 0.3 and 2.8 < high1 < 3.8 and abs(low2) < 0.3 and 0.9 < high2 < 1.3):
                    rows.append(row("poweron", "cycle %d" % cycle, "CH1 went from %.2f to %.2f V, CH2 from %.2f to %.2f V" % (low1 + 0.0, high1 + 0.0, low2 + 0.0, high2 + 0.0),
                                    "CH1 from 0 to 3.3 V (+3V3), CH2 from 0 to 1.1 V (+1V1)", "FAIL",
                                    "these are not the two rails: are the 10x probes hooked on RAILS pins 3 and 5 (grounds on 4 and 6), and both USB-C cables out "
                                    "(with USB PROG in, the rails never fall)?  The supply is ON"))
                    break
                rise_3v3.append(r1)
                rise_1v1.append(r2)
                up_3v3, up_1v1 = analysis.crossing(t1, v1, RAIL_3V3_READY), analysis.crossing(t2, v2, RAIL_1V1_READY)
                lead.append(None if up_3v3 is None or up_1v1 is None else up_1v1 - up_3v3)
            b.record("poweron", quiet=True, cycle=cycle, rise_3v3=rise_3v3[-1] if rise_3v3 else None, rise_1v1=rise_1v1[-1] if rise_1v1 else None,
                     lead=lead[-1] if lead else None)
        shot = b.scope_shot("poweron", quiet=True)
        rows.append(row("poweron", "screenshot of the last cycle", shot.replace(bench.HERE + "/", ""), "", "info", "CH1 and CH2 at 2 ms/div, the trigger two divisions from the left"))
        good_3v3 = [r for r in rise_3v3 if r is not None]
        good_1v1 = [r for r in rise_1v1 if r is not None]
        good_lead = [x for x in lead if x is not None]
        if not fetch:
            rows.append(row("poweron", "rise times", "not computed", "", "info",
                            "the scope's record is over %d points: read the two rise times and the order off the screenshot" % MAX_WAVEFORM_POINTS))
        if good_3v3:
            slow_enough = min(good_3v3) >= REALTEK_MIN_RISE
            rows.append(row("poweron", "+3V3 rise, 10-90 %%, %d cycles" % len(good_3v3), "%.2f to %.2f ms" % (1e3 * min(good_3v3), 1e3 * max(good_3v3)),
                            "slower than %.1f ms (the PHY's wish, review R2-12); the bucks' soft start is about 0.8 ms" % (1e3 * REALTEK_MIN_RISE), "pass" if slow_enough else "info",
                            "" if slow_enough else "faster than Realtek asks: a row for REVB.md (BRINGUP.md 1.5)"))
        if good_1v1:
            rows.append(row("poweron", "+1V1 rise, 10-90 %%, %d cycles" % len(good_1v1), "%.2f to %.2f ms" % (1e3 * min(good_1v1), 1e3 * max(good_1v1)), "", "info"))
        if good_lead:
            in_order = min(good_lead) >= -SAME_TIME
            rows.append(row("poweron", "the order, %d cycles" % len(good_lead),
                            "+3V3 passes %.1f V between %.2f and %.2f ms before +1V1 passes %.1f V" % (RAIL_3V3_READY, 1e3 * min(good_lead), 1e3 * max(good_lead), RAIL_1V1_READY),
                            "+3V3 first, or together within %.1f ms (review R8)" % (1e3 * SAME_TIME), "pass" if in_order else "FAIL",
                            "" if in_order else "the core is up before the 3.3 V of the configuration bank: the sysCONFIG rule of review R8 is broken on some cycles; "
                            "did every cycle still boot (`coldboot`)?  A row for REVB.md with the screenshot"))
        elif fetch and rise_3v3:
            rows.append(row("poweron", "the order", "one of the rails never passed its level on the scope", "+3V3 first", "FAIL",
                            "is the CH2 probe on RAILS pin 5 (+1V1)?  The screenshot shows what each channel saw"))
    finally:
        try:
            if not b.psu.output():
                b.psu_output(True, quiet=True)        # the supply is never left off
        finally:
            rows.append(visit2.restore_scope(b, saved, (1, 2)))
    return rows


OVERSHOOT_GOOD = 0.10            # BRINGUP.md 5.3: ringing under 10 % is what is expected
OVERSHOOT_BAD = 0.20             # over 20 %: a stitching capacitor goes on the rev B list
LOGIC_HIGH = 3.3


def step_dac_clock(b, a):
    """the DAC clock at the DAC (review R2-11), on a held 10x probe: its overshoot, and a screenshot of an edge"""
    bd = b.bd
    ch = a.ch
    b.require(["SDS2104X:%d" % ch], "scope CH%d's settings" % ch)
    saved = visit2.save_scope(b, (ch,))
    rows = []
    try:
        bd.gpio(dac_sleep=0)
        bd.dac_config(rate=50e6)
        visit2.scope_setup(b, ch, scale=1.0, offset=-1.5, probe=10)
        b.scope.timebase(scale=5e-9)                  # 5 ns/div: two and a half periods of 50 MHz
        b.scope.trigger(source=ch, level=1.65, slope="rising", mode="auto")
        m = b.scope_read(ch, ["MAX", "MIN", "FREQ"], settle=2.0)
        is_clock = (None not in (m["MAX"], m["MIN"], m["FREQ"]) and abs(m["FREQ"] / 50e6 - 1) < 0.01          # the DAC runs at 50 MS/s
                    and 2.5 < m["MAX"] < 4.6 and -1.3 < m["MIN"] < 0.8)                                       # a 3.3 V logic level, 40 % of ringing allowed for
        if not is_clock:
            rows.append(row("dac_clock", "the DAC clock on scope CH%d" % ch,
                            "not a 3.3 V, 50 MHz clock: %s" % ", ".join("%s %s" % (k, "none" if v is None else "%.3g" % v) for k, v in m.items()), "a 3.3 V, 50 MHz clock", "FAIL",
                            "the probe's tip on the DAC end of the 33 ohm by U201 pin 18, its switch at 10x; run the step again while it is held"))
        else:
            over, under = (m["MAX"] - LOGIC_HIGH) / LOGIC_HIGH, -m["MIN"] / LOGIC_HIGH
            worst = max(over, under)
            verdict = "pass" if worst < OVERSHOOT_GOOD else ("info" if worst <= OVERSHOOT_BAD else "FAIL")
            rows.append(row("dac_clock", "the DAC clock on scope CH%d" % ch, "%.2f V to %.2f V: %.0f %% over, %.0f %% under" % (m["MIN"], m["MAX"], 100 * over, 100 * under),
                            "ringing under %.0f %% of 3.3 V (over %.0f %% fails)" % (100 * OVERSHOOT_GOOD, 100 * OVERSHOOT_BAD), verdict,
                            "" if verdict == "pass" else "a stitching capacitor by the In4 corridor goes on the rev B list (REVB.md); until then 25 MS/s has the same edge (BRINGUP.md 5.3)"))
        b.scope.timebase(scale=1e-9)                  # 1 ns/div: one edge (BRINGUP.md 5.3)
        shot = b.scope_shot("dac_clock", quiet=True)
        rows.append(row("dac_clock", "screenshot of an edge", shot.replace(bench.HERE + "/", ""), "", "info"))
    finally:
        rows.append(visit2.restore_scope(b, saved, (ch,)))
    return rows


def step_hdmi(b, a):
    """HDMI: the monitor's hot-plug pin, its EDID, the test picture"""
    if not b.bd.hdmi()["hpd"]:
        return [row("hdmi", "a monitor on the mini-HDMI jack", "none seen (the hot-plug pin is low)", "a monitor", "FAIL",
                    "is the cable in the mini-HDMI jack (J503) and the monitor on, set to that input?  A monitor that is there and not seen: the HPD line")]
    return [row("hdmi", "a monitor on the mini-HDMI jack", "seen (the hot-plug pin is high)", "a monitor", "pass")] + visit1.test_hdmi(b)


def step_pmod(b, a):
    """the Pmod loop: every pin of Pmod A driven and read on Pmod B, and back"""
    r = b.bd.pmod_loop_test()
    if len(r["a_to_b"]) == 8 and len(r["b_to_a"]) == 8:
        return [row("pmod", "Pmod A - Pmod B", "no pin of one reaches the other", "eight wires, pin for pin", "FAIL",
                    "no loop found: eight jumper wires from Pmod A's eight signal pins to the same pins of Pmod B (not the 3.3 V and ground pins)")]
    return visit1.test_pmod(b)


# name -> (the ONE sentence saying what must have been moved, the function, what to put back afterwards)
STEPS = {
    "leds":      ("Nothing to move: watch the eight white LEDs along the top edge, then the RGB LED by Pmod A.", step_leds, ""),
    "buttons":   ("Nothing to move: press BTN0 (SW301), then BTN1 (SW302), half a second each, while this runs.", step_buttons, ""),
    "prog":      ("Nothing to move: press SW303 PROG once while this runs.", step_prog, ""),
    "gain_x10":  ("The shunts of JP103 (channel A) and JP203 (channel B) must be pulled: gain x10 on both.", step_gain_x10, ""),
    "gain_x100": ("The shunts of JP104 and JP204 must be pulled as well (JP103 and JP203 still out): gain x100 on both.", step_gain_x100,
                  "Now put all four GAIN shunts back in (JP103, JP104, JP203, JP204)."),
    "term_open": ("All four GAIN shunts must be back in and the shunt of JP101 (channel A's TERM) pulled.", step_term_open, "Now put JP101's shunt back in."),
    "noise_0":   ("JP102 (channel A's SRC) must be on ALT, JP103 and JP104 pulled (x100), and SW101's switch 1 on (0 ohm) with the other three off.", step_noise_0, ""),
    "noise_10k": ("On SW101, switch 1 must be off and switch 4 on (10 kohm); everything else as for noise_0.", step_noise_10k,
                  "Now: SW101 all off, JP102 back on SMA, JP103 and JP104 back in."),
    "light":     ("JP2009 must be on LED (the on-board LED) and JP202 (channel B's SRC) on ALT, with JP1203 on PHOTODIODE.", step_light,
                  "Now: JP2009 open again, JP202 back on SMA.  (DAC 1 is left at code 0: the LED is off.)"),
    "tap":       ("A U.FL pigtail must go from TAP A (J107) to scope CH4.", step_tap, ""),
    "tap_b":     ("The pigtail must be moved to TAP B (J108).", step_tap_b, ""),
    "tap_tia":   ("The pigtail must be moved to TAP TIA (J109), and JP2009 put on LED.", step_tap_tia, "Now: JP2009 open again."),
    "tap_n4v2":  ("The pigtail must be moved to TAP -4V2 (J603).", step_tap_n4v2, "Now: the pigtail off."),
    "poweron":   ("Both USB-C cables must be pulled, and two 10x probes hooked on the RAILS header: scope CH1 on +3V3 (pin 3), CH2 on +1V1 (pin 5), "
                  "their grounds on pins 4 and 6.", step_poweron, "Now: the probes off, both USB-C cables back in.  The supply is ON."),
    "dac_clock": ("A 10x probe on the scope (CH1 unless --ch says another) must be HELD on the DAC end of the 33 ohm by U201 pin 18, its ground spring on "
                  "U201's nearest ground, until this has answered.", step_dac_clock, "Now: the probe away."),
    "hdmi":      ("A monitor must be plugged into the mini-HDMI jack and switched on.", step_hdmi, ""),
    "pmod":      ("Eight wires must join Pmod A's signal pins to Pmod B's, pin for pin.", step_pmod, "Now: the eight wires off."),
}
ALIASES = {"tap_a": "tap"}
GENERATOR_STEPS = ("gain_x10", "gain_x100", "term_open", "tap", "tap_b")     # the steps that switch a generator on


def step(b, a):
    """`bench.py step NAME`: one step of visit 3.  Prints what must have been moved, measures, prints the rows and
    what to put back."""
    if a.list or not a.name:
        print("visit 3's steps, in BRINGUP.md's order (each: what must have been moved; what it measures):")
        for name, (sentence, function, _) in STEPS.items():
            print("  %-10s %s\n  %-10s -> %s" % (name, sentence, "", function.__doc__.strip().split("\n")[0]))
        return 0
    name = ALIASES.get(a.name, a.name)
    if name == "noise":
        raise bench.Refused("The noise step is two commands, with SW101 changed between them: `bench.py step noise_0` (switch 1 on: 0 ohm), then "
                            "`bench.py step noise_10k` (switch 4 on: 10 kohm).")
    if name not in STEPS:
        raise bench.Refused("No step named %s.  The steps: %s." % (a.name, ", ".join(STEPS)))
    sentence, function, after = STEPS[name]
    b.stage = b.stage or "v3"
    print("step %s%s.  %s" % (name, " (SIMULATED)" if b.sim else "", sentence), flush=True)
    if b.sim and not a.sim_as_found:
        b.sim.set_for_step(name)
    res = Results(b, "step")
    try:
        res.run(name, function, b, a)
    finally:
        if name in GENERATOR_STEPS:                   # whatever happened inside, no generator is left on
            failed = b.generators_off()
            if failed:
                res.add(row(name, "every generator output off", "; ".join(failed), "all off", "FAIL", "switch it off at its front panel NOW"))
    res.finish(write=False)
    if after:
        print("\n" + after)
    return 0
