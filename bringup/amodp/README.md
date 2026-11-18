# AMOD-P tiles on board A and an Icepi Zero, at the same time

Each board has its own AMOD-P board and two 10 cm SMA cables: the ECP5's J204 DAC 1 OUT -> the tile's IN, its OUT ->
J101 ADC A IN (TERM in, 50 ohm); the Icepi Zero DK0GFLAW's DAC OUT -> IN, OUT -> ADC IN (high impedance).

    ./amodp_both.sh p4          # both boards sweep tile p4 (each lock-in loaded first), one plot of both in compare/
    ONLY=ecp5 ./amodp_both.sh p0chk     # one board: the through again, as a check

The sweep is the tutorials' `src/verilog/amodp.py` (the same file in both); it saves each board's data and plot into
its own tutorial (`dev/data/amodp/`) and the runner commits them there.  p0 is the through (a barrel), the
calibration every tile is divided by; do not sweep p0 again unless the cables change (p0chk is the check).  Tiles:
p1 ... p13, and p4-1, p4-2, p4-12 for p4's DIP switches.  The dashed lines in the plots are the handbook's circuits
(`~/pcbs/AMOD-and-RFMOD/docs/HANDBOOK_amod_p.md`) with each board's own source and load.  Logs go to `logs/` (not
kept).

    python3 amodp_fit_p4.py p4 compare  # fit the real coil to board A's p4, then check it on the Icepi's sweep

p4's coil (L401, NLV32T-101J) is not the handbook's 100 uH + 10 ohm: at 1 MHz it is 21-23 ohm, which puts board A's
peak 1 dB under the dashed line (`compare/amodp_fit_p4.png`).  Its tail above 3 MHz and the phase turning back towards
0 are the staircase (below), not the coil's own capacitance as first thought.

**Board A's lock-in sees the DAC's staircase** (found on p5, 2026-11-18): the DAC and the ADC run on one 25 MHz clock,
so the through reads flat (the ADC samples the held value back), but a tile that cuts the DAC's images leaves the
hold's sinc droop (-2.4 dB at 10 MHz) and its half-sample delay in the ratio.  `sampled_model_scratch.py` folds a
tile's response at 25 MS/s; with the ADC sampling 2.35 ns after the DAC's update and two 20.6 MHz poles in the chain,
board A fits p2-p5 within 0.2-0.4 dB rms on the handbook's values.  **amodp.py's dashed line is now this** (its
SAMPLING table; the plain circuit dotted; `python3 amodp.py all --replot` redraws the saved figures).  amodp_fit_p4.py
predates it: its f^2 loss, its 1.4 pF and its Icepi prediction are the staircase's, not the coil's.  The Icepi (DAC
50 MS/s, ADC 25) fits no better folded, so its curve stays the plain one; its own input is lossier at MHz than its
model (p4's peak, p5's ring), not yet explained.
