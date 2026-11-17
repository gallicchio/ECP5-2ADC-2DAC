# CONFIGS 1a-1d: the scripts that ran them (board A, 2026-11-17 09:08-09:12)

Run from the tutorial repo's `src/verilog` (they import its `fast.py` and `clocks.py`) after Jason has cabled CONFIGS
section 1 and `bench.py claim v2` holds the instruments.  Each switches its generators off at the end, error or not.

* `run_1a_1c.py OUT.json [1a]`: fast.bit loaded (`make load-fast`).  1a (with the `1a` argument): SDG CH1 into J101 ADC A
  IN at 5, 10, 20 MHz, 1 Vpp and 0.632 Vpp (0 dBm), ADC A's 2nd and 3rd harmonics.  1c: the 33220A at DC 0 V, output on
  (ADC B terminated by its 50 ohm), SDG CH1 at 3, 10, 30 MHz into ADC A: what ADC B sees, in dBc.
* `run_1b.py OUT.json`: fast.bit; both DACs a tone at half of full scale; the scope's CH1 (J204 DAC 1 OUT) and CH2 (J205
  DAC 2 OUT) at 50 ohm and **probe 1x** (it was left at 10x), 10-bit, 1M points, the spectrum on the PC, at 0.2 and 0.15
  V/div (harmonics that move with the scale are the scope's).
* `run_1d.py OUT.json`: clocks.bit (`make load-clocks`); SDG CH2 into J301 CLK IN at 1, 10, 30 MHz and 1 to 0.01 Vpp: the
  count against the frequency.

The results are the `result_*.json` beside them; BRINGUP_LOG.md has the rows, REVB 21, 22 and 26 the conclusions.
