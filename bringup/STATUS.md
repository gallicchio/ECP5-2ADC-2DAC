# ECP5-2ADC-2DAC rev A bring-up: where we are

**Read this first, every time.**  The session rewrites it at every hand-off and prints it at the top of its chat
messages (`python3 bringup/bench.py where`).  The procedure is [`../BRINGUP.md`](../BRINGUP.md); results are in
[`BRINGUP_LOG.md`](BRINGUP_LOG.md); problems for the next revision in [`REVB.md`](REVB.md).

Updated: **2026-11-17 01:36, by Claude (Prompts 116-127, "keep going all night"): board A's USB PROG works (rework done,
swapped cable); visit 1B ran (66 pass, every failure explained).  Overnight, with this cabling only, the tutorial's
designs pushed every interface board A can test alone (serial 12 Mbaud, Ethernet at line rate, DACs 187.5 MS/s, ADCs
87.5 MS/s, Si5351 225 MHz, CLK IN 300 MHz); **the board is an IIO device two ways** (gigabit UDP from the FPGA through
`iiod_bridge.py`, and its own Linux with a kernel driver and libiio's iiod), in GNU Radio unmodified; the DACs stream
too (never dry); an SDR receiver, a lock box, a phasemeter (1.6 urad/rtHz), a 21 ps carry-chain TDC, a TRNG.  The
network caps board A at 96 Mbit/s somewhere on its branch (CONFIGS 4).  New problems: REVB 21 (large-signal distortion
from the ADC front end slewing), 22 (cross-talk), 23 (USB USER dual-role), **24 (ADC B steps 0.1-0.4 codes on a ~1.9 s
grid with the ddc_awg bitstreams: source unknown)**.  What's left needs your hands: [`CONFIGS.md`](CONFIGS.md).**

## Now

| | |
|---|---|
| **Board on the bench** | **A**, reworked: FB6241 gone, a wire from R6222's +3V3 end to its left pad (VPHY 3.3 V); USB PROG through the D+/D- swapped cable.  Board B still in the bag. |
| **Powered?** | **yes, from USB PROG** (the E3646A's output is OFF). |
| **Cabled to the board** | the swapped USB-A-to-C cable in USB PROG; USB-C to USB USER; SMA CLK OUT to CLK IN, DAC 1 OUT to ADC A IN, DAC 2 OUT to ADC B IN; Ethernet to the lab switch (gigabit link); E3646A output 1 on J601 (off); no microSD card answers; no monitor; nothing on the Pmods. |
| **Instruments claimed for this board** | none (E3646A:1 and Fluke45 released 2026-11-16 20:14, unused since 10:34); visit 2's `bench.py` claims what it needs. |
| **What is in the board's flash** | `bringup.bit` of 2026-11-16 (version 20261116): the board boots it by itself. |
| **What the session is doing alone** | the ECP5 version of the tutorial (`~/mudd/133electronics/ecp5-2adc-2dac-tutorial`, 30 pages), on board A over USB PROG and Ethernet.  The FPGA's SRAM holds the tutorial's `udp_awg.bit`; the flash still holds bringup.bit (unplugging USB PROG puts it back).  The tutorial's IIO bridge runs on bell (`iiod_bridge.py`, port 30431).  The Si5351's outputs are off.  The session goes on with this cabling; the AMOD session waits for "port free". |

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
