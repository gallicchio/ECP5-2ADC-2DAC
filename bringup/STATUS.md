# ECP5-2ADC-2DAC rev A bring-up: where we are

**Read this first, every time.**  The session rewrites it at every hand-off and prints it at the top of its chat
messages (`python3 bringup/bench.py where`).  The procedure is [`../BRINGUP.md`](../BRINGUP.md); results are in
[`BRINGUP_LOG.md`](BRINGUP_LOG.md); problems for the next revision in [`REVB.md`](REVB.md).

Updated: **2026-11-17 09:15, by Claude (Prompt 128): CONFIGS 1a-1d done with the generators and the scope.  The ADC front end
makes REVB 21's distortion (a generator straight into ADC A: -28 dBc at 10 MHz, -17 dBc at 20 MHz, slew-limited at the
OPA1612's 27 V/us; the DACs alone only a 3rd harmonic of -35 to -50 dBc).  REVB 22's cross-talk is neither the ADC side
(-85 dB at 3 MHz) nor the DAC side (-62 dB): the cables' ground loops, probably.  CLK IN counts a sine exactly at 1-30 MHz
from 0.3 Vpp (REVB 26: a slow small sine double-counts).  -4V2 is steady at -4.150 V under every bitstream; +5V 4.975 V.
New: REVB 25 (the RAILS header's labels sit over its ground row).  Next for you: 1e and 1f in
[`CONFIGS.md`](CONFIGS.md).**

## Now

| | |
|---|---|
| **Board on the bench** | **A**, reworked: FB6241 gone, a wire from R6222's +3V3 end to its left pad (VPHY 3.3 V); USB PROG through the D+/D- swapped cable.  Board B still in the bag. |
| **Powered?** | **yes, from USB PROG** (+5V 4.975 V, -4V2 -4.150 V on the Fluke; the E3646A's output is OFF). |
| **Cabled to the board** | **CONFIGS 1**: the SDG1032X CH1 -> J101 (ADC A IN), CH2 -> J301 (CLK IN); the 33220A -> J102 (ADC B IN); the scope CH1 -> J204 (DAC 1 OUT), CH2 -> J205 (DAC 2 OUT), CH3 -> J302 (CLK OUT), all BNC-SMA, no external terminators (the scope's inputs set to 50 ohm, probe 1x); the Fluke on J602 (RAILS), red on the bottom-row pin under -4V2, black on the top row; Ethernet; both USB-C.  Two Icepi Zeros, cross-connected, on the bench too (the Icepi tutorial's tests). |
| **Instruments claimed for this board** | all of `bench.py claim v2` (E3646A:1, Fluke45, SDG1032X CH1 and CH2, 33220A, SDS2104X CH1-4) since 09:07; every generator output off. |
| **What is in the board's flash** | `bringup.bit` of 2026-11-16 (version 20261116): the board boots it by itself. |
| **What the session is doing alone** | the FPGA holds the tutorial's `fast.bit` (the flash still bringup.bit); the tutorial's IIO bridge runs on bell; an agent tests the Icepi tutorial on the two Icepi Zeros (their own USB ports, SRAM only). |

## Visit 1B on board A (2026-11-16 17:00-18:00)

* **Passed:** JTAG, both bitstreams and the flash, the register bus, every clock, the PLL, the Si5351 (-25.7 ppm),
  CLK OUT -> CLK IN, the PHY, Ethernet through the PHY's loopback and on the wire both ways at gigabit, both analog
  loops (slope 1.026, offsets +8 and +3 codes, noise 0.7 codes rms, SFDR 67-81 dBc to 1 MHz, cross-talk -80 dBc),
  every ADC capture phase, the SDRAM's whole array (with the clock inverted).
* **Fixed on the way** (REVB 16-19): nine global clocks killed the TCXO domain (gateware); the ADC statistics read
  hung over USB (host); a stale GPIO copy powered the ADCs down (host); the SDRAM clock as designed is marginal (use
  polarity 1).
* **Open:** REVB 20, USB USER's full-speed pull-up does not lift D+; no microSD card answered.
* Figures: `figs/board_A/2026-11-16/` (`python3 bringup/plot_v1b.py`).

## The next thing Jason does

**[`CONFIGS.md`](CONFIGS.md)** lists them, each with every cable named (instrument channel to board connector), the
jumpers, what the PC runs and what a pass looks like.  In order of time:

0. **Put the bring-up design back first**: the FPGA holds whichever tutorial design ran last.  Either unplug and replug
   USB PROG (the board boots `bringup.bit` from its flash), or `openFPGALoader -c ft2232 gateware/bringup/build/bringup.bit`.
1. **CONFIGS 3, a microSD card** (2 min): into J504 on the back, then `bench.py v1b --only sd`.
2. **CONFIGS 2, the Fluke on USB USER** (10 min, REVB 20): D501's anode and cathode with the pull-up on, D- at rest.
3. **CONFIGS 1, visit 2 plus tonight's questions** (30 min): the generators and the scope on the six SMAs; REVB 21
   (which stage distorts), REVB 22 (where the cross-talk is), 1e (the ADC channels' skew, a tee), **1f (REVB 24: ADC B's
   1.9 s steps, with ddc_awg.bit: cables crossed, B terminated, USB PROG unplugged, a warm finger)**.
4. CONFIGS 5 (a monitor on mini-HDMI), 4 (gigabit all the way to the PC), 6 (board B), when convenient.

## The visits

| visit | what | Jason's time | state |
|---|---|---|---|
| 0 | unwrap, mark A/B, photos, jumpers | 15 min | board A done 2026-11-16 |
| 1A | board A: the supply on J601; the staircase; the eight LEDs; the Fluke along the RAILS header | 5 min | 2026-11-16: staircase pass, LEDs pass, 7 of 9 rails pass; +5V/+5VA 4.22 V from the leads: **re-read with thick leads next** |
| 1B | board A: USB PROG, USB USER, three SMA cables, Ethernet, microSD; then the session alone (an hour or more) | 5 min | ran 2026-11-16 17:00-18:00 after the USB PROG rework: 66 pass; open: REVB 20 (USB USER), the microSD (CONFIGS 3) |
| 2 | board A: both USB out for the cold-boot test; then the two generators and the scope on the six SMAs; then the session alone | 10 min | |
| 3 | board A: the sit-down session: LEDs, buttons, gain and source jumpers, the LED and photodiode, the taps, the power-on scope shot, HDMI | 30-40 min | |
| 4 | board B: visits 0 and 1 again | 10 min | |

## What is known so far

**The pin audit (2026-11-16, `PIN_AUDIT.md`).**  Every IC's supply pins, 39 pairs and 145 FPGA lines were checked by
script.  It found nothing new beyond REVB 12 and 13.  One finding from the IcepiZero audit applies here: **the Pmod
sockets are mirrored against the Pmod spec (REVB 14)**, so no third-party Pmod goes in the usual way.  Jason
(2026-11-16): rev B follows the standard, and rev A boards are marked non-standard; they mate only with the AMOD/RF-MOD
rev A plugs (some of those came in, untested).

**Board A, visit 1A (2026-11-16).**
* Staircase all in constant voltage: 1.0 V 0.000 A, 2.5 V 0.090 A, 4.0 V 0.386 A, 5.0 V 0.388 A.  No short.
* At 5.0 V: **0.385 A** with the FPGA unconfigured, steady within 1.1 %.  The eight POWER LEDs are lit.
* Rails: +3V3 3.331, +1V1 1.106, +2V5 2.508, +3V3_ADC 3.296, +3V3_DAC 3.293, +1V0_PHY 1.011, -4V2 -4.115 V, all pass.
  +5V 4.220 and +5VA 4.226 V are low: the supply gave 5.00 V, J601 saw 4.51-4.54 V (the BNC cable and thin wire), and
  D601 with F602 took another 0.30 V (normal for the SS34).  REVB rows 10 (J602's labels, accepted) and 11 (the input's
  losses, candidate).
* Two bench-tool rules were wrong on the real board and were fixed in `visit1.py`; both dry runs pass again:
  * "the current rises with the voltage" (the bucks draw constant power) is now a check on power;
  * "any negative reading is -4V2, so the walk is over" now needs seven rails first.

**The photos (2026-11-16).**  Every part position populated; pin 1 and polarity as drawn wherever readable.  JP501 has
no shunt: the session's "shunt on JP501" was a misread of a slanted photo.

Before the board, what was written and dry-run (2026-11-15/16):

* `gateware/bringup/build/bringup.bit` (version 20261115): every clock meets timing; `make sim` 60 checks, `make test`,
  `make sim-eth` 61 checks, `make sim-hdmi` 28 checks and the co-simulation (`make cosim`) all pass.  It now tests every
  connector: the RGMII data path, the microSD socket, USB USER's lines and HDMI were added on 2026-11-15.
* `bringup/bench.py`: every visit is a command (`v1a`, `rails`, `v1b`, `coldboot`, `v2`, `step NAME`, `report`,
  `where`).  `python3 bringup/test_bench.py` runs all of them against the simulated board and simulated instruments:
  206 checks pass, among them 22 injected faults (a shorted supply, crossed or missing cables, a missing card, jumpers
  not moved) that each give a worded finding.
* **What the dry run does not prove** is listed in `bringup/README.md` under that heading and in
  `gateware/bringup/README.md` ("What only the board can settle").  In short: the E3646A and Fluke 45 paths have now run on the
  real bench (visit 1A); nothing that opens the board's serial port has run; openFPGALoader has not been run; the Ethernet-on-the-wire test, the kernel-log
  reading and the USB-power test are written and untested; every analog pass window is a design number on an ideal
  simulated chain; the staircase's expected currents and the cold-boot current rule are estimates.  Expect the first
  minutes of each visit to find some of these.

## For lab-instrument-control, when its instruments are on this board's bench

This session changed nothing there.  Noted while writing the tool, to be fixed with the instrument in hand (the
library's rule is to measure before changing a driver):

* `SDS2104X.channel()` returns `'ONEMeg'`/`'FIFTy'` and `trigger()` returns `'RISing'`/`'AUTO'`, but they take `'1M'`/`'50'`
  and `'rising'`/`'auto'`: settings read back cannot be handed straight back to restore them (bench.py translates).
* `SDS2104X.waveform()` cannot bound the record length; `SDG1032X` has no `q()`; the 33220A has no voltage limit of
  its own (bench.py enforces +-1.25 V into 50 ohm).
* `Fluke45`'s default port named the adapter that now carries the BK 9130; another session was already editing
  `fluke/fluke_45.py` for that on 2026-11-16.  bench.py always passes the port from `bench_config.json`.

## Rules the session keeps on this bench

* Nothing is switched on (supply, generator) unless this project holds the claim on that channel
  (`bench_claims.py`), and every cable is checked by a harmless signal before a full-level one.
* The supply's switch is the PC's; outputs are left off, and instruments put back as found, when the board leaves.
* Root commands are Jason's, given in the chat as a block to paste.  None is needed for anything here.
