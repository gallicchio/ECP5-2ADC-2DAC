"""analysis.py: the arithmetic of the bring-up.  No instrument and no board in here: lists and arrays in, numbers
out, so every function can be tried on made-up data (test_bench.py does).

    sine_fit(codes, rate, freq)       least-squares sine at a known frequency: amplitude, offset, residuals
    spectrum(codes, rate)             Hann-windowed amplitude spectrum, in codes peak
    sfdr(codes, rate)                 the largest tone, and the largest other tone below it in dBc
    fit_line(x, y)                    slope, value at x = 0, worst deviation from the line
    jumper_state(ratio)               what an amplitude ratio says about the GAIN and TERM jumpers
    widest_run(flags)                 the longest run of True in a list: (first, last)
    PlateauFinder                     the Fluke walk: steady readings picked out of a stream of readings
    assign_rails(volts, rails)        those steady readings lined up against the nine rails in order
    rise_time(t, v), crossing(t, v, level)    for the power-on scope traces
"""
import math

import numpy as np


# ---- sines and spectra ------------------------------------------------------------------------------------
def sine_fit(codes, sample_rate, freq):
    """Fit offset + a sin(2 pi f t) + b cos(2 pi f t) to the samples by least squares, f known.
    Returns (amplitude, offset, residuals): amplitude and offset in the samples' units, residuals the array
    of sample minus fit.  A frequency above half the sample rate works too: at the sample instants the
    alias and the tone are the same numbers."""
    y = np.asarray(codes, dtype=float)
    t = np.arange(len(y)) / float(sample_rate)
    columns = np.column_stack([np.sin(2 * np.pi * freq * t), np.cos(2 * np.pi * freq * t), np.ones(len(y))])
    (a, b, offset), _, _, _ = np.linalg.lstsq(columns, y, rcond=None)
    residuals = y - columns @ np.array([a, b, offset])
    return float(math.hypot(a, b)), float(offset), residuals


def spectrum(codes, sample_rate):
    """The amplitude spectrum of the samples with their mean removed and a Hann window: (freqs, amps), amps in
    the samples' units PEAK (a sine of amplitude A that sits on a bin reads A).  Bin spacing is
    sample_rate / len(codes)."""
    y = np.asarray(codes, dtype=float)
    window = np.hanning(len(y))
    amps = np.abs(np.fft.rfft((y - y.mean()) * window)) * 2.0 / window.sum()   # 2 / sum(w): a sine's peak reads its amplitude
    freqs = np.arange(len(amps)) * float(sample_rate) / len(y)
    return freqs, amps


SKIP_ROUND_PEAK = 3      # bins either side of a tone that belong to it: the Hann window's main lobe is 2 bins each side
SKIP_DC = 1              # bin 0: what is left of the mean


def sfdr(codes, sample_rate):
    """The largest tone and the largest OTHER tone of a capture.
    Returns a dict: peak_hz, peak_amp (codes peak), spur_hz, spur_amp, sfdr_db (20 log10 of their ratio).
    The three bins either side of the peak, and DC, are left out of the search for the spur.

    This is only a spurious-free dynamic range when a whole number of the tone's periods fits the capture: a tone
    between two bins leaks into the bins around it under any window (4 bins from a Hann-windowed tone that sits
    a third of a bin off, the leakage is still 50 dB down), and that leakage would be taken for a spur.  The
    DAC-to-ADC tests choose such frequencies (visit1.TONE_STEP_HZ); a generator's tone, on its own clock, is
    measured with sine_fit() instead."""
    freqs, amps = spectrum(codes, sample_rate)
    amps = amps.copy()
    amps[:SKIP_DC] = 0.0
    k = int(amps.argmax())
    peak = float(amps[k])
    rest = amps.copy()
    rest[max(0, k - SKIP_ROUND_PEAK):k + SKIP_ROUND_PEAK + 1] = 0.0
    j = int(rest.argmax())
    spur = float(rest[j])
    return {"peak_hz": float(freqs[k]), "peak_amp": peak, "spur_hz": float(freqs[j]), "spur_amp": spur,
            "sfdr_db": 20 * math.log10(peak / spur) if spur > 0 and peak > 0 else float("inf"),
            "bin_hz": float(sample_rate) / len(codes)}


def db(ratio):
    """20 log10 of an amplitude ratio; -200 for zero, so a table never holds -inf."""
    return 20 * math.log10(ratio) if ratio > 0 else -200.0


def fit_line(x, y):
    """The straight line through the points by least squares.  Returns (slope, value at x = 0, worst deviation
    of a point from the line)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    slope, at_zero = np.polyfit(x, y, 1)
    worst = float(np.abs(y - (slope * x + at_zero)).max())
    return float(slope), float(at_zero), worst


# ---- the jumpers, from an amplitude ---------------------------------------------------------------------------
# What a signal measures, divided by what it would measure with both GAIN shunts in (x1) and the TERM shunt in
# (50 ohm).  Each preamp stage is x1 with its shunt in and x10.1 with it out (BRINGUP.md 6.5: x10.1 and x102);
# with the TERM shunt out a 50 ohm source is not loaded and the input sees twice the voltage.
JUMPER_STATES = [
    (1.0,   {"gain": 1,   "term": True}),
    (2.0,   {"gain": 1,   "term": False}),
    (10.1,  {"gain": 10,  "term": True}),
    (20.2,  {"gain": 10,  "term": False}),
    (102.0, {"gain": 100, "term": True}),
    (204.0, {"gain": 100, "term": False}),
]
JUMPER_TOLERANCE = 0.25      # a ratio within 25 % of a row is that row: the rows are a factor 2 or more apart


def jumper_state(ratio):
    """The row of JUMPER_STATES an amplitude ratio fits, as {'gain': 1|10|100, 'term': True|False}, or None
    when it fits none (a broken path, or a ratio no jumper setting makes)."""
    for nominal, state in JUMPER_STATES:
        if abs(ratio / nominal - 1.0) <= JUMPER_TOLERANCE:
            return dict(state)
    return None


def jumper_words(state):
    """{'gain': 10, 'term': False} -> 'gain x10, TERM out'"""
    if state is None:
        return "no jumper setting fits"
    return "gain x%d, TERM %s" % (state["gain"], "in (50 ohm)" if state["term"] else "OUT (high-Z)")


def widest_run(flags):
    """The longest run of True in a list of booleans: (first index, last index), or None when none is True.
    The first of two equally long runs wins."""
    best = None
    start = None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        if not f and start is not None:
            if best is None or (i - 1 - start) > (best[1] - best[0]):
                best = (start, i - 1)
            start = None
    return best


# ---- the Fluke walk --------------------------------------------------------------------------------------------
STEADY_N = 3             # this many consecutive readings that agree make a plateau (0.6 s at the Fluke's medium rate)
STEADY_REL = 0.01        # "agree": within 1 % ...
STEADY_ABS = 0.010       # ... or 10 mV, whichever is larger (10 counts on the 30 V range)
MIN_RAIL_V = 0.5         # a plateau is a rail only above this: the lowest rail is +1V0_PHY at 1.0 V
LIFTED_V = 0.3           # below this the probe is in the air (a 10 Mohm input left open reads millivolts)


def same_level(a, b):
    """True when two readings agree within 1 % or 10 mV."""
    return abs(a - b) <= max(STEADY_REL * abs(b), STEADY_ABS)


def _median(values):
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


class PlateauFinder:
    """Feed it the meter's readings one by one with add(t, volts); it keeps the list of plateaus: a plateau is
    STEADY_N consecutive readings that agree with each other and are above MIN_RAIL_V in size, and it lasts
    until a reading is below LIFTED_V (the probe was lifted) or moves away.  A probe that slips on a pin and
    settles again makes two plateaus of that pin; assign_rails() below takes the second as an extra reading,
    which costs nothing.  (Joining them would also join +3V3_ADC and +3V3_DAC, two pins that read the same,
    when the probe moves quickly from one to the other.)

        finder.plateaus()      -> [{'volts': median, 'n': readings, 't0': ..., 't1': ...}, ...] so far, the
                                  one still being held included
    """

    def __init__(self):
        self.done = []           # finished plateaus, each a dict with its list of readings under 'values'
        self.open = None         # the plateau the probe is on now
        self.recent = []         # the last readings that are not part of a plateau
        self.last_touch_t = None # when the probe last rested on a rail

    def add(self, t, volts):
        if self.open is not None:
            if abs(volts) >= LIFTED_V and same_level(volts, _median(self.open["values"])):
                self.open["values"].append(volts)
                self.open["t1"] = t
                self.last_touch_t = t
                return
            self.done.append(self.open)              # it ends: the probe was lifted, or the level moved away
            self.open = None
        self.recent = (self.recent + [(t, volts)])[-STEADY_N:]
        values = [v for _, v in self.recent]
        if (len(values) == STEADY_N and all(abs(v) > MIN_RAIL_V for v in values)
                and all(same_level(v, _median(values)) for v in values)):
            self.open = {"values": values, "t0": self.recent[0][0], "t1": t}
            self.recent = []
            self.last_touch_t = t

    def plateaus(self):
        """Every plateau so far, in order; the one still held is included."""
        every = self.done + ([self.open] if self.open is not None else [])
        return [{"volts": _median(p["values"]), "n": len(p["values"]), "t0": p["t0"], "t1": p["t1"]} for p in every]

    def open_readings(self):
        """How many readings the plateau now being held has (0 when the probe is in the air)."""
        return len(self.open["values"]) if self.open is not None else 0


# What lining a reading up against a rail costs.  The lining-up with the smallest total wins.
COST_IN_WINDOW = 0       # the reading is inside the rail's window
COST_NEAR = 1            # outside the window, but within 20 % of the rail: that rail, out of tolerance
COST_WRONG = 3           # nothing like the rail: still cheaper than "one rail skipped and one stray reading" (2 + 2)
COST_SKIPPED_RAIL = 2    # a rail with no reading: the probe skipped its pin, or the rail is dead (0 V makes no plateau)
COST_EXTRA_READING = 2   # a reading that belongs to no rail: a pin touched twice
NEAR_FRACTION = 0.20


def _fit_cost(volts, window):
    lo, hi = window
    if lo <= volts <= hi:
        return COST_IN_WINDOW
    nominal = 0.5 * (lo + hi)
    if abs(volts - nominal) <= NEAR_FRACTION * abs(nominal):
        return COST_NEAR
    return COST_WRONG


def assign_rails(volts, rails):
    """Line the steady readings (in the order they were taken) up against the rails (in the order of the
    header).  `rails` is a list of (name, (lo, hi)).  A rail may get no reading and a reading may get no
    rail; among all ways of lining them up in order, the one with the fewest misfits is taken.  So eight
    readings with the 2.5 V one absent come out as "+2V5 has no reading", not as seven rails shifted by one.

    Returns (taken, extras): taken[i] is the index into `volts` of the reading for rail i, or None; extras
    is the list of reading indexes that were given to no rail."""
    n, m = len(rails), len(volts)
    # best[i][j]: the smallest cost of lining up the first i rails with the first j readings
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    how = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        best[i][0] = best[i - 1][0] + COST_SKIPPED_RAIL
        how[i][0] = "skip"
    for j in range(1, m + 1):
        best[0][j] = best[0][j - 1] + COST_EXTRA_READING
        how[0][j] = "extra"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            choices = [(best[i - 1][j - 1] + _fit_cost(volts[j - 1], rails[i - 1][1]), "take"),
                       (best[i - 1][j] + COST_SKIPPED_RAIL, "skip"),
                       (best[i][j - 1] + COST_EXTRA_READING, "extra")]
            best[i][j], how[i][j] = min(choices, key=lambda c: c[0])     # on a tie the first wins: "take"
    taken = [None] * n
    extras = []
    i, j = n, m
    while i > 0 or j > 0:
        step = how[i][j]
        if step == "take":
            taken[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif step == "skip":
            i -= 1
        else:
            extras.append(j - 1)
            j -= 1
    return taken, sorted(extras)


def could_also_be(i, taken, volts, rails):
    """For a rail i that got no reading: the neighbouring rails whose reading would have fitted rail i just as
    well (+3V3_ADC and +3V3_DAC read the same), so the report can say "one of these two" instead of guessing."""
    names = []
    for k in (i - 1, i + 1):
        if 0 <= k < len(rails) and taken[k] is not None and _fit_cost(volts[taken[k]], rails[i][1]) == COST_IN_WINDOW:
            names.append(rails[k][0])
    return names


# ---- scope traces ---------------------------------------------------------------------------------------------
def crossing(t, v, level):
    """The time at which the trace first rises through `level` (linear between the two samples), or None."""
    t = np.asarray(t, dtype=float)
    v = np.asarray(v, dtype=float)
    above = np.nonzero((v[1:] >= level) & (v[:-1] < level))[0]
    if len(above) == 0:
        return None
    k = int(above[0])
    return float(t[k] + (level - v[k]) / (v[k + 1] - v[k]) * (t[k + 1] - t[k]))


def rise_time(t, v):
    """The 10 % to 90 % rise time of a trace that starts low and ends high: the levels are taken from the mean
    of the first and of the last twentieth of the record.  Returns (seconds, low level, high level), seconds
    None if the trace does not rise."""
    v = np.asarray(v, dtype=float)
    n = max(1, len(v) // 20)
    low, high = float(v[:n].mean()), float(v[-n:].mean())
    if high - low <= 0:
        return None, low, high
    t10 = crossing(t, v, low + 0.1 * (high - low))
    t90 = crossing(t, v, low + 0.9 * (high - low))
    if t10 is None or t90 is None:
        return None, low, high
    return t90 - t10, low, high
