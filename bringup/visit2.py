"""visit2.py: visit 2 of ../BRINGUP.md, `bench.py v2`: the board against the generators and the scope.

Cabled (BNC cables with SMA ends, not probes; every generator output off: the PC switches them):

    SDG1032X CH1 -> ADC A IN       scope CH1 -> DAC 1 OUT
    SDG1032X CH2 -> CLK IN         scope CH2 -> DAC 2 OUT
    33220A       -> ADC B IN       scope CH3 -> CLK OUT

`verify` first, with signals too small to hurt whatever a cable was plugged into by mistake: which generator
reaches which input, which scope channel sees which output.  A harmless swap (the two generators on each
other's ADC channel, the two scope channels on each other's DAC) is accepted and remembered; a swap that is
not (SDG CH1 on CLK IN: the two SDG channels are opened with different voltage limits) stops the command with
one sentence.  Then the tests of V2_TESTS.  At the end, whatever happened, the generators are switched off and
the scope's channels, time base and trigger are put back as they were found.
"""
import analysis
import bench
import visit1
from report import Results, hz, row

VERIFY_VPP = 0.100               # the generators' cable-check amplitude into 50 ohm: 205 ADC codes at x1, harmless anywhere on the board
VERIFY_PKPK = VERIFY_VPP * 2048  # ... in ADC codes peak to peak: 2048 codes per volt (+-1 V is the ADC's 4096 codes)
SEEN_CODES = 60                  # an ADC that swings more than this (peak to peak) while a generator is on sees that generator (its noise: under 10)
VERIFY_HZ = {"sdg1": 10e3, "hp": 15e3}   # two different low frequencies, so the log tells the generators apart
SOURCE_NAME = {"sdg1": "SDG1032X CH1", "sdg2": "SDG1032X CH2", "hp": "the 33220A"}
SOURCE_MAX_HZ = {"sdg1": bench.SDG_MAX_HZ, "sdg2": bench.SDG_MAX_HZ, "hp": bench.HP_MAX_HZ}
DAC_CHECK = {1: (12288, +1.0), 2: (4096, -1.0)}   # verify's DC codes: +0.5 V and -0.5 V into 50 ohm, so +1.0 and -1.0 V on a 1 Mohm scope
SCOPE_CHANNELS = (1, 2, 3)       # the scope channels this visit changes (CH4 is left alone: a tap, in visit 3)
SWAP_SDG = ('swap the two BNC cables at the generator, so that SDG CH1 feeds an ADC input and SDG CH2 feeds CLK IN (the tests drive the two to '
            'different voltages); then "v2 ready" again.  Nothing was tested')
HP_OFF_CLK = 'its cable belongs on ADC B IN (and SDG1032X CH2\'s on CLK IN): move it, then "v2 ready" again.  Nothing was tested'
TIMEBASES = [s * d for d in (1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3) for s in (1, 2, 5)]      # the scope's 1-2-5 steps, seconds per division


class FoundV2:
    """What v2's verify found cabled."""
    def __init__(self):
        self.board = False
        self.gen_for = {"a": None, "b": None}     # which generator ('sdg1' or 'hp') feeds each ADC channel, usable (x1, 50 ohm in)
        self.why_not = {"a": "no generator reaches ADC A IN (verify)", "b": "no generator reaches ADC B IN (verify)"}
        self.clk_gen = False                      # SDG CH2 is on CLK IN
        self.scope_for = {1: None, 2: None}       # which scope channel sees each DAC output
        self.scope_clk = False                    # scope CH3 sees CLK OUT

    @property
    def adc_gen(self):
        return any(self.gen_for.values())

    @property
    def dac_scope(self):
        return any(self.scope_for.values())

    def channels(self):
        """[('a', 'sdg1'), ('b', 'hp')]: the ADC channels a generator feeds, with it."""
        return [(ch, src) for ch, src in sorted(self.gen_for.items()) if src]

    def skipped(self, test):
        return [row(test, "ADC %s" % ch.upper(), "not run", "", "skipped", self.why_not[ch]) for ch in ("a", "b") if not self.gen_for[ch]]


# ---- the scope's settings: saved before anything is changed, put back at the end ------------------------------------
def save_scope(b, channels=SCOPE_CHANNELS):
    """The scope's settings of `channels` (as its driver's channel() returns them: probe factor included), its time
    base and its trigger, before a command changes any of them."""
    saved = {"channels": {ch: b.scope.channel(ch) for ch in channels}, "timebase": b.scope.timebase(), "trigger": b.scope.trigger()}
    b.record("scope_saved", quiet=True, channels=saved["channels"], timebase=saved["timebase"], trigger=saved["trigger"])
    return saved


def _same(a, c):
    if isinstance(a, bool) or isinstance(c, bool) or isinstance(a, str) or isinstance(c, str):
        return a == c
    return abs(a - c) <= 1e-3 * max(abs(a), abs(c), 1e-9)


def restore_scope(b, saved, channels=SCOPE_CHANNELS):
    """Put the scope back as save_scope() found it and read it back.  Returns one row: pass when every setting
    reads as it did.  The driver's channel() answers 'FIFTy' / 'ONEMeg' for the impedance but takes '50' / '1M',
    its trigger() answers 'RISing' / 'AUTO' but takes 'rising' / 'auto': translated here."""
    wrong = []
    for ch in channels:
        s = saved["channels"][ch]
        probe = int(s["probe"]) if float(s["probe"]).is_integer() else s["probe"]
        try:
            b.scope.channel(ch, on=s["on"], scale=s["scale"], offset=s["offset"], coupling=s["coupling"],
                            impedance="50" if str(s["impedance"]).upper().startswith("FIF") else "1M", probe=probe, bwlimit=s["bwlimit"])
            now = b.scope.channel(ch)
            wrong += ["CH%d %s is %s, was %s" % (ch, k, now[k], s[k]) for k in s if not _same(now[k], s[k])]
        except Exception as e:                        # noqa: BLE001: the other channels must still be put back
            wrong.append("CH%d: %s: %s" % (ch, type(e).__name__, e))
    try:
        b.scope.timebase(scale=saved["timebase"][0], delay=saved["timebase"][1])
        trig = saved["trigger"]
        slope = {"RIS": "rising", "FAL": "falling", "ALT": "alternate"}.get(str(trig["slope"]).upper()[:3])
        mode = {"AUTO": "auto", "NORM": "normal", "SING": "single"}.get(str(trig["mode"]).upper()[:4])
        b.scope.trigger(source=trig["source"], level=trig["level"], slope=slope, mode=mode or "auto")
        if mode is None:
            wrong.append("the trigger mode was %s when found: the scope is left running in AUTO" % trig["mode"])
    except Exception as e:                            # noqa: BLE001
        wrong.append("time base and trigger: %s: %s" % (type(e).__name__, e))
    b.record("scope_restored", quiet=True, wrong=wrong)
    was = "; ".join("CH%d %g V/div, probe x%g, %s" % (ch, saved["channels"][ch]["scale"], saved["channels"][ch]["probe"],
                                                    "on" if saved["channels"][ch]["on"] else "off") for ch in channels)
    if not wrong:
        return row("scope", "the scope put back as found", was, "every setting reads as it did before", "pass")
    return row("scope", "the scope put back as found", "; ".join(wrong), "every setting reads as it did before", "FAIL",
               "set by hand what differs; as found it was: %s; time base %g s/div; trigger %s" % (was, saved["timebase"][0], saved["trigger"]))


def scope_setup(b, ch, scale, offset=0.0, coupling="DC", probe=1):
    """One scope channel for a BNC cable from a board output: on, 1 Mohm, the probe factor of what is plugged in."""
    b.scope.channel(ch, on=True, scale=scale, offset=offset, coupling=coupling, impedance="1M", probe=probe)


def timebase_for(freq, cycles=20):
    """The scope's time base (one of its 1-2-5 steps) that shows at least `cycles` periods of `freq` across its
    ten divisions: enough for its frequency measurement."""
    for scale in TIMEBASES:
        if 10 * scale * freq >= cycles:
            return scale
    return TIMEBASES[-1]


# ---- verify ---------------------------------------------------------------------------------------------------------
def _what_dc(volts, expect_plus):
    """What a scope reading says about a DAC output that should show +-1.0 V: 'dac' (the expected sign), 'other'
    (the other DAC's sign), 'half', 'tenth', 'nothing'."""
    if volts is None:
        return "nothing"
    size = abs(volts)
    if abs(size - 1.0) <= 0.15:
        return "dac" if (volts > 0) == expect_plus else "other"
    if abs(size - 0.5) <= 0.08:
        return "half"
    if abs(size - 0.1) <= 0.03:
        return "tenth"
    return "nothing"


def verify_v2(b):
    """Find out what is cabled where, with small signals.  Returns (FoundV2, rows, stop): `stop` is None, or the one
    sentence that ends the command (a cable on a connector where the tests' levels would not be safe)."""
    f = FoundV2()
    rows = []
    ok, ident = b.board_answers()
    if not ok:
        rows.append(row("verify", "the board on USB PROG", "no answer (%s)" % ident, "the ID register 0xEC5BA2D2", "FAIL",
                        "both USB-C cables back in after the cold boot?  It boots bringup.bit from its flash; if not: `bench.py v1b --only jtag,load_bringup`"))
        return f, rows, "The board does not answer on USB PROG: plug both USB-C cables back in, then \"v2 ready\" again."
    f.board = True
    bd = b.bd
    rows.append(row("verify", "the board on USB PROG", "answers, bitstream version %s" % ident["version"], "the ID register 0xEC5BA2D2", "pass"))
    off_failed = b.generators_off()
    if off_failed:
        rows.append(row("verify", "generators off", "; ".join(off_failed), "all three outputs off", "FAIL", "a generator does not answer: its address in bench_config.json; `bench.py check`"))
        return f, rows, "A generator could not be switched off (see the row above): nothing was tested."
    b.analog_setup()

    # the DACs on the scope: DAC 1 at +0.5 V and DAC 2 at -0.5 V into 50 ohm, +1.0 and -1.0 V into the scope's 1 Mohm
    for port, (code, _) in DAC_CHECK.items():
        bd.dac(port, "dc", code=code)
    for ch in (1, 2):
        scope_setup(b, ch, scale=0.5)
    scope_setup(b, 3, scale=1.0, offset=-1.5)         # CLK OUT: 0 to 3.3 V, drawn round the middle of the screen
    b.scope.timebase(scale=1e-3)
    b.scope.trigger(mode="auto")
    seen = {ch: b.scope_read(ch, ["MEAN"])["MEAN"] for ch in (1, 2)}
    for port in (1, 2):
        expected = "%+.1f V on scope CH%d (DAC %d at %+.1f V into 50 ohm, doubled by the scope's 1 Mohm)" % (DAC_CHECK[port][1], port, port, DAC_CHECK[port][1] / 2)
        plus = DAC_CHECK[port][1] > 0
        here, there = _what_dc(seen[port], plus), _what_dc(seen[3 - port], plus)
        value = "CH%d reads %s" % (port, "nothing" if seen[port] is None else "%+.2f V" % seen[port])
        if here == "dac":
            f.scope_for[port] = port
            rows.append(row("verify", "DAC %d OUT" % port, value, expected, "pass"))
        elif there == "dac":
            f.scope_for[port] = 3 - port
            rows.append(row("verify", "DAC %d OUT" % port, "on scope CH%d (%+.2f V)" % (3 - port, seen[3 - port]), expected, "info",
                            "the two scope cables are swapped: accepted, the tests read DAC %d on CH%d" % (port, 3 - port)))
        elif here == "half":
            rows.append(row("verify", "DAC %d OUT" % port, value, expected, "FAIL",
                            "half the level: something loads the cable with 50 ohm (a terminator, a T-piece).  Take it off; this DAC's scope tests are skipped"))
        elif here == "tenth":
            rows.append(row("verify", "DAC %d OUT" % port, value, expected, "FAIL",
                            "a tenth of the level: a 10x probe is on this channel; the plan wants a BNC cable with an SMA end.  This DAC's scope tests are skipped"))
        else:
            rows.append(row("verify", "DAC %d OUT" % port, value, expected, "FAIL",
                            "scope CH%d does not see DAC %d OUT: is the BNC cable on, at both ends?  This DAC's scope tests are skipped; "
                            "after: `bench.py v2 --only dac_dc_scope,dac_sine_scope`" % (port, port)))
    # a visit-1 SMA cable still on an ADC input shows here: that ADC's mean follows the DAC's DC level
    w_dc = b.adc_window()
    still_dac = {ch: abs(w_dc[ch]["mean"] - 2048) > 300 for ch in ("a", "b")}   # +-0.5 V is 1024 codes; an idle input sits within 100 of 2048
    for port in (1, 2):
        bd.dac(port, "dc", code=8192)

    # CLK OUT on scope CH3: held high, then low
    bd.clkout("high")
    high = b.scope_read(3, ["MEAN"])["MEAN"]
    bd.clkout("low")
    low = b.scope_read(3, ["MEAN"])["MEAN"]
    bd.clkout("tcxo")
    f.scope_clk = high is not None and low is not None and abs(high - 3.3) <= 0.3 and abs(low) <= 0.2
    rows.append(row("verify", "CLK OUT", "CH3 reads %s held high, %s held low" % tuple("nothing" if v is None else "%.2f V" % v for v in (high, low)),
                    "3.3 V and 0 V on scope CH3", "pass" if f.scope_clk else "FAIL",
                    "" if f.scope_clk else "scope CH3 does not follow CLK OUT: is its BNC cable on?  clkout_scope is skipped; after: `bench.py v2 --only clkout_scope`"))

    # the generators, one at a time, small: where does each arrive?
    arrives = {}                                      # source -> 'a', 'b', 'clk', 'both' or None
    state = {}
    for src in ("sdg1", "hp"):
        b.tone(src, VERIFY_HZ[src], VERIFY_VPP)
        b.sleep(0.3)
        w = b.adc_window()
        clk = bd.clocks(gates=2)["clk_in"]
        b.tone_off(src)
        on = [ch for ch in ("a", "b") if w[ch]["pkpk"] >= SEEN_CODES]
        if len(on) == 1:
            arrives[src] = on[0]
            clipped = w[on[0]]["min"] <= 0 or w[on[0]]["max"] >= 4095
            state[src] = {"gain": 100, "term": True} if clipped else analysis.jumper_state(w[on[0]]["pkpk"] / VERIFY_PKPK)
        elif len(on) == 2:
            arrives[src] = "both"
        elif abs(clk - VERIFY_HZ[src]) <= 0.05 * VERIFY_HZ[src] + b.count_step_hz():
            arrives[src] = "clk"
        else:
            arrives[src] = None
        b.record("verify_gen", quiet=True, source=src, pkpk_a=w["a"]["pkpk"], pkpk_b=w["b"]["pkpk"], clk_in=clk, arrives=arrives[src])
    for src, want in (("sdg1", "a"), ("hp", "b")):
        expected = "ADC %s IN: %.0f codes pp for %.0f mVpp (gain x1, TERM in)" % (want.upper(), VERIFY_PKPK, 1000 * VERIFY_VPP)
        got = arrives[src]
        name = SOURCE_NAME[src][0].upper() + SOURCE_NAME[src][1:]
        if got in ("a", "b"):
            words = "ADC %s IN, %s" % (got.upper(), analysis.jumper_words(state[src]))
            if state[src] != {"gain": 1, "term": True}:
                n = 1 if got == "a" else 2
                f.why_not[got] = "ADC %s is at %s; these tests need gain x1 with the 50 ohm in" % (got.upper(), analysis.jumper_words(state[src]))
                rows.append(row("verify", name, words, expected, "FAIL",
                                "the jumpers of channel %s are not at their bring-up positions: both GAIN shunts in (JP%d03, JP%d04), TERM in (JP%d01).  "
                                "Its tests are skipped: at these levels they would overdrive it" % (got.upper(), n, n, n)))
            elif still_dac[got]:
                f.why_not[got] = "ADC %s IN also follows a DAC: a visit-1 SMA cable is still on it" % got.upper()
                rows.append(row("verify", name, words + "; but the input also follows a DAC", expected, "FAIL", "a visit-1 SMA cable is still on: take it off.  Its tests are skipped"))
            else:
                f.gen_for[got] = src
                rows.append(row("verify", name, words, expected, "pass" if got == want else "info",
                                "" if got == want else "the two generators are on each other's ADC channel: accepted, the tests use them as they are"))
        elif got == "clk":
            rows.append(row("verify", name, "on CLK IN (it counts %.0f kHz)" % (VERIFY_HZ[src] / 1e3), expected, "FAIL", SWAP_SDG if src == "sdg1" else HP_OFF_CLK))
        elif got == "both":
            rows.append(row("verify", name, "both ADC channels swing", expected, "FAIL", "one cable cannot feed two inputs: a T-piece, or the two inputs joined"))
        else:
            rows.append(row("verify", name, "reaches neither ADC input nor CLK IN", expected, "FAIL",
                            "is its cable on the board, and is its front-panel output the one cabled?  The tests of ADC %s are skipped; "
                            "after: `bench.py v2 --only adc_abs,adc_response,overrange,xtalk_gen`" % want.upper()))
    for ch in ("a", "b"):
        if still_dac[ch] and f.gen_for[ch] is None and ch not in [arrives.get("sdg1"), arrives.get("hp")]:
            rows.append(row("verify", "ADC %s IN" % ch.upper(), "follows a DAC's DC level (mean %.0f)" % w_dc[ch]["mean"], "a generator", "FAIL",
                            "a visit-1 SMA cable from a DAC is still on this input: take it off and put the generator's cable on"))

    # SDG CH2 on CLK IN: a 1 Vpp, 10 MHz sine must be counted, and be gone when the output is off
    b.tone("sdg2", 10e6, 1.0)
    b.sleep(0.3)
    w = b.adc_window()
    clk_on = bd.clocks(gates=2)["clk_in"]
    b.tone_off("sdg2")
    clk_off = bd.clocks(gates=2)["clk_in"]
    sdg2_on_adc = [ch for ch in ("a", "b") if w[ch]["pkpk"] >= SEEN_CODES]
    f.clk_gen = abs(clk_on - 10e6) <= visit1.freq_tolerance(b, 10e6) and clk_off == 0
    value = "CLK IN counts %s with it on, %s with it off" % (hz(clk_on), hz(clk_off))
    expected = "10,000,000 Hz with it on, 0 Hz with it off"
    if f.clk_gen:
        rows.append(row("verify", "SDG1032X CH2", value, expected, "pass"))
    elif sdg2_on_adc:
        rows.append(row("verify", "SDG1032X CH2", "on ADC %s IN (it swings %d codes)" % (sdg2_on_adc[0].upper(), w[sdg2_on_adc[0]]["pkpk"]), expected, "FAIL", SWAP_SDG))
    elif clk_off != 0:
        rows.append(row("verify", "SDG1032X CH2", value, expected, "FAIL",
                        "CLK IN counts with every generator off: the visit-1 SMA cable from CLK OUT is still on it?  clkin_levels and tcxo_ppm are skipped"))
    else:
        rows.append(row("verify", "SDG1032X CH2", value, expected, "FAIL",
                        "is its cable on CLK IN, with JP3001's shunt in?  clkin_levels and tcxo_ppm are skipped; after: `bench.py v2 --only clkin_levels,tcxo_ppm`"))
    b.record("found", quiet=True, visit="v2", gen_for=f.gen_for, clk_gen=f.clk_gen, scope_for=f.scope_for, scope_clk=f.scope_clk)

    # the swaps that are not harmless: the SDG's two channels carry different limits, and the 33220A has none
    stop = None
    if arrives["sdg1"] == "clk" or sdg2_on_adc:
        stop = ("SDG1032X CH1 and CH2 are on each other's connectors (CH1 must feed an ADC input, CH2 must feed CLK IN: the tests drive them to "
                "different voltages): swap the two BNC cables at the generator, then \"v2 ready\" again.")
    elif arrives["hp"] == "clk":
        stop = "The 33220A is on CLK IN: its cable belongs on ADC B IN (and SDG1032X CH2's on CLK IN); move it, then \"v2 ready\" again."
    return f, rows, stop


# ---- the tests -------------------------------------------------------------------------------------------------------
ADC_FULL_VOLTS_PER_CODE = 2.0 / 4096     # +-1 V over 4096 codes: 488 uV per code at gain x1


def test_adc_abs(b):
    """the ADCs' scale: 1.000 Vpp at 100 kHz into each input's 50 ohm, in codes"""
    rows = b.found.skipped("adc_abs")
    for ch, src in b.found.channels():
        b.tone(src, 100e3, 1.000)
        b.sleep(0.3)
        t, ca, cb, otr = b.capture(rate=25e6)
        b.tone_off(src)
        b.record("capture", quiet=True, path=b.save_capture("v2_adc_abs_%s" % ch, t, ca, cb, otr, source=src, vpp=1.0, freq=100e3))
        x = visit1.pick(ch, ca, cb)
        amplitude, offset, _ = analysis.sine_fit(x, 25e6, 100e3)
        pkpk = 2 * amplitude
        label = "%s -> ADC %s" % (SOURCE_NAME[src], ch.upper())
        ok = abs(pkpk / 2048.0 - 1) <= 0.05
        rows.append(row("adc_abs", label + ": 1.000 Vpp reads", "%.0f codes pp (amplitude %.1f; raw max - min %d)" % (pkpk, amplitude, int(x.max() - x.min())),
                        "2048 codes pp +-5 % (amplitude 1024: 2048 codes per volt)", "pass" if ok else "FAIL",
                        "" if ok else "the input chain's gain at x1: the 49.9 ohm termination and the 100 ohm in series, the two OPA1612 stages, the THS4521 "
                        "(TAP %s on the scope, `step tap`, splits it); or the generator's amplitude" % ch.upper()))
        rows.append(row("adc_abs", label + ": offset", "%+.1f codes from mid-scale" % (offset - 2048), "within 100 codes (BRINGUP.md 6.1)",
                        "pass" if abs(offset - 2048) <= 100 else "FAIL", "" if abs(offset - 2048) <= 100 else "an offset in the preamp or the FDA: compare with v1b's dc_transfer offset"))
        rows.append(row("adc_abs", label + ": volts per code", "%.1f uV" % (1e6 * 1.000 / pkpk) if pkpk > 0 else "no signal", "%.1f uV (2 V over 4096 codes)" % (1e6 * ADC_FULL_VOLTS_PER_CODE), "info",
                        "the calibration of this channel at x1, 50 ohm in"))
    return rows


# Twelve logarithmic steps from 10 kHz to 30 MHz, each a little off the round number so that none is a simple
# fraction of the 50 MS/s sample rate (at exactly 30 MHz the samples would land on the same five points of the sine).
RESPONSE_HZ = [10.1e3, 20.7e3, 42.9e3, 88.8e3, 184e3, 381e3, 788e3, 1.63e6, 3.38e6, 6.99e6, 14.5e6, 29.9e6]
RESPONSE_REF_HZ = 100e3
RESPONSE_VPP = 0.5               # a quarter of full scale: room for a peak in the response
RESPONSE_STATS_LOG2 = 14         # 16384 samples: three periods of 10 kHz at 50 MS/s, so max - min is the sine's peak to peak
FLAT_TO_HZ = 1e6                 # BRINGUP.md 6.3: the amplitude within 1 dB to 1 MHz


def test_adc_response(b):
    """the ADC inputs' frequency response: 0.5 Vpp from 10 kHz to 30 MHz at 50 MS/s, against 100 kHz"""
    rows = b.found.skipped("adc_response")
    pkpk = {ch: {} for ch, _ in b.found.channels()}
    for freq in [RESPONSE_REF_HZ] + RESPONSE_HZ:
        driven = []
        for ch, src in b.found.channels():
            if freq <= SOURCE_MAX_HZ[src]:
                b.tone(src, freq, RESPONSE_VPP)
                driven.append(ch)
        b.adc_setup(50e6, stats_log2=RESPONSE_STATS_LOG2)
        b.sleep(0.2)
        w = b.adc_window()
        for ch in driven:
            pkpk[ch][freq] = w[ch]["pkpk"]
    for ch, src in b.found.channels():
        b.tone_off(src)
    b.adc_setup(25e6)
    b.record("adc_response", quiet=True, vpp=RESPONSE_VPP, pkpk={ch: {"%g" % f: v for f, v in d.items()} for ch, d in pkpk.items()})
    for ch, src in b.found.channels():
        ref = pkpk[ch][RESPONSE_REF_HZ]
        rows.append(row("adc_response", "ADC %s at 100 kHz (the reference)" % ch.upper(), "%d codes pp" % ref, "about %d (0.5 Vpp)" % (RESPONSE_VPP * 2048), "info"))
        for freq in RESPONSE_HZ:
            name = "ADC %s at %s" % (ch.upper(), ("%.3g MHz" % (freq / 1e6)) if freq >= 1e6 else ("%.3g kHz" % (freq / 1e3)))
            if freq not in pkpk[ch]:
                rows.append(row("adc_response", name, "not run", "", "skipped", "%s stops at %g MHz" % (SOURCE_NAME[src], SOURCE_MAX_HZ[src] / 1e6)))
                continue
            level = analysis.db(pkpk[ch][freq] / ref) if ref > 0 else -200.0
            if freq <= FLAT_TO_HZ:
                rows.append(row("adc_response", name, "%+.2f dB" % level, "within 1 dB of 100 kHz", "pass" if abs(level) <= 1.0 else "FAIL",
                                "" if abs(level) <= 1.0 else "not flat below 1 MHz: a coupling or filter capacitor of the wrong value in the input chain (the 22 pF at the ADC, the preamp's feedback)"))
            else:
                rows.append(row("adc_response", name, "%+.2f dB" % level, "", "info",
                                "above half the sample rate (25 MHz): it aliases, as expected" if freq > 25e6 else "the input filter's roll-off (BRINGUP.md 6.3: log it)"))
    return rows


def test_overrange(b):
    """the ADC's out-of-range flag: silent at 1.8 Vpp (90 % of full scale), counting at 2.4 Vpp (120 %)"""
    rows = b.found.skipped("overrange")
    b.adc_setup(25e6)
    for ch, src in b.found.channels():
        for vpp, must_flag in ((1.8, False), (2.4, True)):
            b.tone(src, 100e3, vpp)
            b.sleep(0.2)
            w = b.adc_window()
            b.tone_off(src)
            s = w[ch]
            value = "%d of %d samples flagged; codes %d to %d" % (s["otr"], w["n"], s["min"], s["max"])
            name = "%s -> ADC %s at %.1f Vpp" % (SOURCE_NAME[src], ch.upper(), vpp)
            if must_flag:
                rows.append(row("overrange", name, value, "the flag counts (20 % beyond full scale)", "pass" if s["otr"] > 0 else "FAIL",
                                "" if s["otr"] > 0 else "codes at 0 and 4095 with no flag: the OTR line (adc_%s_otr).  Codes short of the rails: the input "
                                "clamps before the ADC clips, see adc_abs" % ch))
            else:
                rows.append(row("overrange", name, value, "no sample flagged (90 % of full scale)", "pass" if s["otr"] == 0 else "FAIL",
                                "" if s["otr"] == 0 else "the flag counts inside full scale: the gain is high or the offset large (adc_abs has both)"))
    return rows


def test_xtalk_gen(b):
    """channel-to-channel leakage: 1 Vpp at 100 kHz into one ADC input, what the other channel shows"""
    rows = b.found.skipped("xtalk_gen")
    for ch, src in b.found.channels():
        other = "b" if ch == "a" else "a"
        b.tone(src, 100e3, 1.0)
        b.sleep(0.3)
        _, ca, cb, _ = b.capture(rate=25e6)
        b.tone_off(src)
        driven, _, _ = analysis.sine_fit(visit1.pick(ch, ca, cb), 25e6, 100e3)
        leaked, _, _ = analysis.sine_fit(visit1.pick(other, ca, cb), 25e6, 100e3)
        dbc = analysis.db(leaked / driven) if driven > 0 else 0.0
        rows.append(row("xtalk_gen", "%s on ADC %s: what ADC %s shows at 100 kHz" % (SOURCE_NAME[src], ch.upper(), other.upper()),
                        "%.1f dBc (%.2f codes of %.0f)" % (dbc, leaked, driven), "", "info",
                        "above -40 dBc: more than a 12-bit pair should leak; a rev B row" if dbc > -40 else ""))
    return rows


CLKIN_LEVELS = (0.1, 0.3, 1.0, 3.0)      # Vpp into CLK IN's 50 ohm (BRINGUP.md 4.3: 0.3, 1 and 3 Vpp must all count; README: 0.3 V peak or more)


def test_clkin_levels(b):
    """CLK IN's sensitivity: a 10 MHz sine at 0.1, 0.3, 1.0 and 3.0 Vpp must be counted as 10 MHz"""
    bd = b.bd
    rows = []
    try:
        for vpp in CLKIN_LEVELS:
            b.tone("sdg2", 10e6, vpp)
            b.sleep(0.3)
            got = bd.clocks(gates=2)["clk_in"]
            ok = abs(got - 10e6) <= visit1.freq_tolerance(b, 10e6)
            if vpp < 0.3:
                rows.append(row("clkin_levels", "10 MHz at %.1f Vpp" % vpp, hz(got), "", "info", "below the 0.3 V the input is specified for: %s" % ("it still counts" if ok else "it does not count")))
            else:
                rows.append(row("clkin_levels", "10 MHz at %.1f Vpp" % vpp, hz(got), "10,000,000 Hz within 100 ppm", "pass" if ok else "FAIL",
                                "" if ok else "the comparator U302 (TLV3501): its bias at mid-rail (the two 10 k), the 10 nF and the 1 k into +IN; JP3001's shunt in?"))
    finally:
        b.tone_off("sdg2")
    return rows


TCXO_PPM_MAX = 5.0               # BRINGUP.md 4.3: the TCXO and the SDG's timebase are both +-2.5 ppm parts


def test_tcxo_ppm(b):
    """the TCXO against the SDG's timebase: its 10 MHz counted over three gates"""
    bd = b.bd
    try:
        b.tone("sdg2", 10e6, 1.0)
        b.sleep(0.5)
        bd.clocks(gates=2)                            # the gate in which the generator came on is thrown away
        counts = [bd.clocks(gates=1)["clk_in"] for _ in range(3)]
    finally:
        b.tone_off("sdg2")
    mean = sum(counts) / 3.0
    ppm = (mean - 10e6) / 10e6 * 1e6 + 0.0            # the counter reads high when its own gate (the TCXO) runs slow
    tcxo_ppm = 0.0 if abs(ppm) < 0.005 else -ppm
    resolution = b.count_step_hz() / 10e6 * 1e6       # one count in ppm: 0.1 on the bench, 100 simulated
    ok = abs(ppm) <= TCXO_PPM_MAX + resolution
    return [row("tcxo_ppm", "SDG 10 MHz as the board counts it", "%s (three gates: %s): the TCXO is %+.2f ppm against the SDG" % (hz(mean), ", ".join("%d" % c for c in counts), tcxo_ppm),
                "within %.0f ppm (the counter resolves %.1f ppm)" % (TCXO_PPM_MAX, resolution), "pass" if ok else "FAIL",
                "" if ok else "more than two +-2.5 ppm parts can differ: is the SDG on its internal reference (ROSC INT)?  Against a GPSDO (BRINGUP.md 4.4) the TCXO's own error shows")]


DC_SCOPE = ((0, -2.0), (4096, -1.0), (8192, 0.0), (12288, 1.0), (16383, 2.0))    # DAC code, volts open circuit (BRINGUP.md stage 5)
DC_SCOPE_TOLERANCE = 0.1         # BRINGUP.md 5.1: within +-0.1 V
DAC_MATCH_VOLTS = 0.030          # the two channels within 30 mV of each other (one die, one reference; BRINGUP.md 5.1 says 20 mV, the scope adds its own)


def test_dac_dc_scope(b):
    """the DACs' DC levels on the scope: codes 0, 4096, 8192, 12288, 16383 against -2, -1, 0, +1, +2 V"""
    bd = b.bd
    rows = []
    ports = [port for port in (1, 2) if b.found.scope_for[port]]
    for port in (1, 2):
        if port not in ports:
            rows.append(row("dac_dc_scope", "DAC %d" % port, "not run", "", "skipped", "no scope channel sees DAC %d OUT (verify)" % port))
    b.analog_setup()
    for port in ports:
        scope_setup(b, b.found.scope_for[port], scale=1.0)        # 1 V/div: +-2 V is +-2 of the 4 divisions either side
    b.scope.timebase(scale=1e-3)
    b.scope.trigger(mode="auto")
    for code, volts in DC_SCOPE:
        for port in ports:
            bd.dac(port, "dc", code=code)
        seen = {port: b.scope_read(b.found.scope_for[port], ["MEAN"])["MEAN"] for port in ports}
        for port in ports:
            v = seen[port]
            ok = v is not None and abs(v - volts) <= DC_SCOPE_TOLERANCE
            rows.append(row("dac_dc_scope", "DAC %d at code %d" % (port, code), "no reading" if v is None else "%+.3f V" % v, "%+.1f V +-%.1f" % (volts, DC_SCOPE_TOLERANCE),
                            "pass" if ok else "FAIL",
                            "" if ok else "stuck near 0 V with the other DAC right: this channel's OPA2810 rails (+5VA, -4V2 at the chip) or its 24.9 ohm pair; "
                            "both stuck: DAC_SLEEP high, MODE low, or no WRT/CLK (BRINGUP.md 5.1)"))
        if len(ports) == 2 and None not in seen.values():
            diff = seen[1] - seen[2]
            ok = abs(diff) <= DAC_MATCH_VOLTS
            rows.append(row("dac_dc_scope", "DAC 1 - DAC 2 at code %d" % code, "%+.0f mV" % (1000 * diff), "within %.0f mV" % (1000 * DAC_MATCH_VOLTS), "pass" if ok else "FAIL",
                            "" if ok else "two scope channels differ by a per cent or two by themselves: swap the two BNC cables at the scope and run "
                            "`bench.py v2 --only dac_dc_scope`; a difference that stays with the scope channel is the scope's"))
    for port in ports:
        bd.dac(port, "dc", code=8192)
    return rows


SINE_SCOPE_HZ = (1e6, 5e6, 10e6)
FULL_SCALE_VPP = 4.0             # a full-scale DAC sine, open circuit (BRINGUP.md 5.2: 4.0 Vpp +-0.4)
SCOPE_FREQ_TOLERANCE = 1e-3      # the scope's frequency measurement must agree within 0.1 %


def test_dac_sine_scope(b):
    """full-scale DAC sines at 1, 5 and 10 MHz on the scope: amplitude, frequency, a screenshot of each"""
    bd = b.bd
    rows = []
    ports = [port for port in (1, 2) if b.found.scope_for[port]]
    for port in (1, 2):
        if port not in ports:
            rows.append(row("dac_sine_scope", "DAC %d" % port, "not run", "", "skipped", "no scope channel sees DAC %d OUT (verify)" % port))
    b.analog_setup()
    for port in ports:
        scope_setup(b, b.found.scope_for[port], scale=1.0)
    b.scope.trigger(source=b.found.scope_for[ports[0]], level=0.0, slope="rising", mode="auto")
    at_1mhz = {}
    for freq in SINE_SCOPE_HZ:
        actual = {port: bd.dac(port, "sine", freq=freq, shift=0) for port in ports}
        b.scope.timebase(scale=timebase_for(freq))
        for port in ports:
            m = b.scope_read(b.found.scope_for[port], ["PKPK", "FREQ"])
            pkpk, f_scope = m["PKPK"], m["FREQ"]
            name = "DAC %d at %g MHz" % (port, freq / 1e6)
            if pkpk is None:
                rows.append(row("dac_sine_scope", name + ": amplitude", "no reading", "", "FAIL", "the scope gave no value: is the trace on its screen?  The screenshot shows"))
            elif freq == 1e6:
                at_1mhz[port] = pkpk
                ok = abs(pkpk / FULL_SCALE_VPP - 1) <= 0.10
                rows.append(row("dac_sine_scope", name + ": amplitude", "%.2f Vpp" % pkpk, "%.1f Vpp +-10 %%" % FULL_SCALE_VPP, "pass" if ok else "FAIL",
                                "" if ok else "dac_dc_scope's +-2 V rows say whether the DC gain is off too; only the sine: the output stage's bandwidth"))
            else:
                rel = analysis.db(pkpk / at_1mhz[port]) if at_1mhz.get(port) else None
                rows.append(row("dac_sine_scope", name + ": amplitude", "%.2f Vpp%s" % (pkpk, "" if rel is None else " (%+.1f dB against 1 MHz)" % rel), "", "info",
                                "the output stage is -3 dB at 12.3 MHz, and the DAC's sin(x)/x adds -0.6 dB at 10 MHz"))
            ok = f_scope is not None and abs(f_scope / actual[port] - 1) <= SCOPE_FREQ_TOLERANCE
            rows.append(row("dac_sine_scope", name + ": frequency", "no reading" if f_scope is None else hz(f_scope), "%s within 0.1 %%" % hz(actual[port]), "pass" if ok else "FAIL",
                            "" if ok else "the DAC's clock is not the 50 MS/s it is set to (the clocks test), or the scope could not measure: the screenshot shows"))
        shot = b.scope_shot("v2_dac_sine_%gMHz" % (freq / 1e6), quiet=True)
        rows.append(row("dac_sine_scope", "screenshot at %g MHz" % (freq / 1e6), shot.replace(bench.HERE + "/", ""), "", "info"))
    for port in ports:
        bd.dac(port, "dc", code=8192)
    return rows


CLKOUT_SCOPE = (("tcxo", 25e6), ("clk_s", 50e6), ("si0", 10e6))


def test_clkout_scope(b):
    """CLK OUT on scope CH3 from the TCXO, the PLL and the Si5351: frequency, amplitude, a screenshot of each"""
    bd = b.bd
    rows = []
    why_not = visit1.ensure_si5351(b, outputs=(0,))   # si0 is not running after the cold boot's power cycles
    if why_not:
        rows.append(row("clkout_scope", "the Si5351", why_not, "", "info", "the si0 rows below will fail for this reason: `bench.py v1b --only si5351`"))
    scope_setup(b, 3, scale=1.0, offset=-1.5)
    b.scope.trigger(source=3, level=1.65, slope="rising", mode="auto")
    try:
        for name, nominal in CLKOUT_SCOPE:
            bd.clkout(name)
            b.scope.timebase(scale=timebase_for(nominal))
            m = b.scope_read(3, ["FREQ", "PKPK"])
            ok = m["FREQ"] is not None and abs(m["FREQ"] / nominal - 1) <= SCOPE_FREQ_TOLERANCE
            rows.append(row("clkout_scope", "CLK OUT = %s: frequency" % name, "no reading" if m["FREQ"] is None else hz(m["FREQ"]), "%s within 0.1 %%" % hz(nominal),
                            "pass" if ok else "FAIL", "" if ok else "no clock on CLK OUT from this source: `bench.py v1b --only clocks,si5351` says whether the source runs"))
            rows.append(row("clkout_scope", "CLK OUT = %s: amplitude" % name, "no reading" if m["PKPK"] is None else "%.2f Vpp" % m["PKPK"], "about 3.3 V open circuit", "info",
                            "an unterminated cable rings: more than 3.3 V here is the cable, not the board"))
            shot = b.scope_shot("v2_clkout_%s" % name, quiet=True)
            rows.append(row("clkout_scope", "screenshot, CLK OUT = %s" % name, shot.replace(bench.HERE + "/", ""), "", "info"))
    finally:
        bd.clkout("tcxo")
    return rows


# (name, function, what it needs of FoundV2)
V2_TESTS = [
    ("adc_abs",        test_adc_abs,        ("adc_gen",)),
    ("adc_response",   test_adc_response,   ("adc_gen",)),
    ("overrange",      test_overrange,      ("adc_gen",)),
    ("xtalk_gen",      test_xtalk_gen,      ("adc_gen",)),
    ("clkin_levels",   test_clkin_levels,   ("clk_gen",)),
    ("tcxo_ppm",       test_tcxo_ppm,       ("clk_gen",)),
    ("dac_dc_scope",   test_dac_dc_scope,   ("dac_scope",)),
    ("dac_sine_scope", test_dac_sine_scope, ("dac_scope",)),
    ("clkout_scope",   test_clkout_scope,   ("scope_clk",)),
]
NEED_WORDS = {"adc_gen": "no generator reaches an ADC input at gain x1 with the 50 ohm in (verify)", "clk_gen": "SDG1032X CH2 does not reach CLK IN (verify)",
              "dac_scope": "no scope channel sees a DAC output (verify)", "scope_clk": "scope CH3 does not see CLK OUT (verify)"}
V2_CLAIMS = ["SDG1032X:1", "SDG1032X:2", "33220A", "SDS2104X:1", "SDS2104X:2", "SDS2104X:3"]


def v2(b, a):
    """Visit 2 (after `coldboot`).  Cabled as the table at the top of this file.  verify, then the tests of
    V2_TESTS; the generators off and the scope put back as found at the end, whatever happened.  The result is
    the table and the report file: exit status 0 even with FAIL rows, 1 when a cable has to be moved first."""
    if a.list:
        print("v2's tests, in the order they run (after verify):")
        visit1.print_test_list(V2_TESTS)
        return 0
    tests = visit1.choose_tests(V2_TESTS, a.only, a.skip)
    b.stage = b.stage or "v2"
    b.require(V2_CLAIMS, "the generators and the scope")
    res = Results(b, "v2")
    print("v2 board %s%s: %d tests%s." % (b.board, " (SIMULATED)" if b.sim else "", len(tests), "" if not (a.only or a.skip) else " (" + ", ".join(t[0] for t in tests) + ")"))
    saved = None
    stop = None
    try:
        saved = save_scope(b)
        print("\n== verify: what is cabled where, with small signals", flush=True)
        try:
            b.found, rows, stop = verify_v2(b)
        except bench.Refused:
            raise
        except Exception as e:                        # noqa: BLE001: verify failing must not cost the report, nor the clean-up below
            import traceback
            b.record("exception", quiet=True, test="verify", traceback=traceback.format_exc())
            b.found, rows = FoundV2(), [row("verify", "verify itself", "%s: %s" % (type(e).__name__, e), "to run to its end", "FAIL",
                                            "nothing is known about the cabling, so no test was run; the traceback is in the log")]
            stop = "verify could not finish (the row above says why): nothing was tested."
        res.add(rows)
        if stop is None:
            for name, function, needs in tests:
                missing = [NEED_WORDS[need] for need in needs if not getattr(b.found, need)]
                if missing:
                    res.skip(name, missing[0])
                else:
                    res.run(name, function, b)
    except KeyboardInterrupt:
        print("\ninterrupted: the report holds what was done so far")
    finally:
        print("\n== the bench put back", flush=True)
        failed = b.generators_off()
        res.add(row("generators", "every generator output off", "; ".join(failed) if failed else "SDG CH1, SDG CH2 and the 33220A are off", "all off",
                    "FAIL" if failed else "pass", "switch it off at its front panel NOW: its output may be live on the board" if failed else ""))
        if saved is not None:
            res.add(restore_scope(b, saved))
        try:
            if b.found is not None and b.found.board:
                b.analog_setup()
                b.bd.clkout("tcxo")
        except Exception:                             # noqa: BLE001
            pass
    res.finish()
    if stop:
        print("\nSTOPPED after verify: " + stop)
        return 1
    return 0
