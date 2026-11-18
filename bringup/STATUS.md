# ECP5-2ADC-2DAC rev A bring-up: where we are

**Read this first, every time.**  The session rewrites it at every hand-off and prints it at the top of its chat
messages (`python3 bringup/bench.py where`).  The procedure is [`../BRINGUP.md`](../BRINGUP.md); results are in
[`BRINGUP_LOG.md`](BRINGUP_LOG.md); problems for the next revision in [`REVB.md`](REVB.md).

Updated: **2026-11-18 11:24, by Claude (Prompt 166).  The project lives in its own repository,
`~/pcbs/ECP5-2ADC-2DAC` (github.com/gallicchio/ECP5-2ADC-2DAC); everything is recorded here.**

**Where we are: the AMOD-P march, at p11 (p0-p9 done; p10, p12, p13 wait for their own setups).**  Board A and the Icepi Zero DK0GFLAW each sweep the same
AMOD-P tile on their own AMOD-P board at the same time (`amodp/README.md`).  p0 (the through, the calibration), p1-p3
and **p4 with both switches off** are measured on both and make sense (BRINGUP_LOG).  Board A's p4 (2026-11-18 08:39,
after a fresh load of lockin2; yesterday's failure was the lock-in bitstream, not the cables): peak -1.8 dB at 1.075
MHz, Q 5.4.  It sits 1 dB under the handbook's circuit at the peak and well under it above 3 MHz because the 100 uH coil
loses more than its 10 ohm DC resistance (21-23 ohm at 1 MHz) and resonates by itself at 14 MHz.  p5 (09:26) showed
that board A's lock-in sees the DAC's staircase (DAC and ADC on one 25 MHz clock): above a few MHz a low-pass tile
reads the DAC's sinc droop that the through hides.  Modelled, board A fits p2-p5 within 0.2-0.3 dB with the handbook's
values; amodp.py's dashed lines do not have it yet (BRINGUP_LOG, p5).  Every sweep loads the lock-in first.

Earlier on 2026-11-17: gigabit works both ways; CONFIGS 1a-1e done; REVB 22's 3 MHz cross-talk is on the board, from
DAC 1 driving a load; REVB 24's steps are inside ADC B's chain after its preamp.  **Board A's ADC stage was hurt at
about 14:35** (a U.FL pigtail fitted to J108 TAP B on the powered board): both ADC channels compress held levels at
the ends of their range (1.5-3 % at +-0.75 of full scale; DNL, noise and distortion unchanged; U103 the AD9238 most
likely: REVB 27).  Rule: the board powered off for any U.FL work.  The chain's ENOB and IMD and the clocks'
three-cornered hat are in the log (15:17-15:24).

## Now

| | |
|---|---|
| **Board on the bench** | **A**, reworked: FB6241 gone, a wire from R6222's +3V3 end to its left pad (VPHY 3.3 V); USB PROG through the D+/D- swapped cable.  Board B still in the bag. |
| **Powered?** | **yes, from USB PROG** (+5V 4.975 V; -4V2 -4.150 V; +1V1 1.108 V at 16:02).  The E3646A is **not connected** to the board. |
| **Cabled to the board** | J204 (DAC 1 OUT) -> 10 cm SMA -> its AMOD-P board -> 10 cm SMA -> J101 (ADC A IN), TERM in.  On 2026-11-18 on p4 (IN, top left; OUT, bottom right); on p9 since 11:14; board A taped to the table.  J205 (DAC 2 OUT) and J102 (ADC B IN): nothing, as far as the session knows.  A U.FL pigtail from J108 (TAP B) to the scope's CH4; J401 (ETHERNET) on the gigabit path; both USB-C; the Fluke on J602 (RAILS) +1V1. |
| **Instruments claimed for this board** | the Fluke45 (on +1V1) and the scope's CH4 (TAP B), both only reading.  The E3646A released (2026-11-17 22:56:51, the claims log). |
| **What is in the board's flash** | `bringup.bit` of 2026-11-16 (version 20261116): the board boots it by itself. |
| **What the session left running** | nothing.  Board A's FPGA holds the tutorial's `lockin2.bit` (loaded 2026-11-18 11:14); the IIO bridge on bell is stopped (22:56:49, its output file).  The Icepi DK0GFLAW holds `lockin_half.bit` in SRAM (its flash still the 5.08 XY show), cabled DAC OUT -> its AMOD-P's p4 -> ADC IN. |

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

**The AMOD-P march, from p11.**  On both AMOD-P boards, move the two cables from p9 to p11 (the DAC's cable to p11 IN,
top left; **p11 OUT is at the bottom of the left cell**, not bottom right, to the ADC; the taps 100ns, 200ns, 300ns
left open) and reply "p11".  The session runs `bringup/amodp/amodp_both.sh p11` and shows the plot of both.  Board A
should be flat to about 10 MHz with a 395 ns delay.

* p10 (the clipper) and p12 (the LEDs) want an amplitude or DC sweep, not a frequency sweep (to be written), and p10
  reads OUT on high impedance (board A's JP101 TERM out).  p13 (the AM loopstick) needs a loopstick coil on the tile and
  AMOD-A's a4 in front of the ADC.
* Then the rest, one reply per setup ("p5"); the session answers each
  with the next "**go to pN on both boards**".
* If a sweep ever looks wrong again: the barrel (`ONLY=ecp5 amodp_both.sh p0chk`, it should read 0 dB), then the
  AMOD-P boards swapped between board A and the Icepi.  For a tile with a coil, `amodp/amodp_fit_p4.py` shows how to
  fit the real part before blaming the board.
* The Icepi's ADC is high impedance: a tile made for 50 ohm (p4-p9, p11) shows its handbook curve only with p1 after
  it (tile OUT -> a third short cable -> p1 IN, p1 OUT -> the Icepi's ADC IN).  amodp.py spots that and divides p1 out.
  Without it the Icepi's curves are the unterminated ones (also worth having, and computed in its dashed line).
* The crystal (p8) takes about a minute and a half (a search in 50 Hz steps, then 5 Hz steps); p10 (the clipper) and
  p12 (LEDs) want amplitude sweeps rather than frequency sweeps: to be written when we get there; p13 the loopstick.

Then, still open: test 4 (the hour-long soak, Jason sets it up); CONFIGS 3 (a microSD card), 2 (the Fluke on USB USER,
REVB 20), 5 (a monitor on mini-HDMI), 6 (board B); the cable tests 5-7 of Response 146's list; the AMOD-A board.

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
