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

p4's coil (L401, NLV32T-101J) is not the handbook's 100 uH + 10 ohm: at 1 MHz it is 23 ohm (rising as f^2) with 1.4 pF
across it (self-resonant at 13 MHz), which puts board A's peak 1 dB under the dashed line and its curve well under it
above 3 MHz.  Fitted to board A, the same coil predicts the Icepi's peak within 0.8 dB (`compare/amodp_fit_p4.png`).
