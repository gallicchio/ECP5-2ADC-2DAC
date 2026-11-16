# ECP5-2ADC-2DAC rev A bring-up: where we are

**Read this first, every time.**  The session rewrites it at every hand-off and prints it at the top of its chat
messages (`python3 bringup/bench.py where`).  The procedure is [`../BRINGUP.md`](../BRINGUP.md); results are in
[`BRINGUP_LOG.md`](BRINGUP_LOG.md); problems for the next revision in [`REVB.md`](REVB.md).

Updated: **2026-11-16 10:50, by Claude (Prompt 101): board A powered; visit 1A done except +5V; supply OFF.**

## Now

| | |
|---|---|
| **Board on the bench** | **A** (marked), shunts set per visit 0, JP501 open (it never had a shunt: the session misread the photo).  Board B still in the bag. |
| **Powered?** | **OFF since 10:43** (Jason's request).  The E3646A output 1 is set 5.0 V, 1.0 A limit, OVP 5.6 V, output off. |
| **Cabled to the board** | **E3646A output 1 on J601** (red on the upper pin +5V, black on the lower pin GND), **through a BNC cable and thin wire**.  The microSD card.  Nothing else: no USB, no SMA, no Ethernet. |
| **Instruments claimed for this board** | E3646A:1 and Fluke45 (`claim v1`, 10:34).  Held while the leads stay on J601. |
| **Adapters** | E3646A on FTDI `A9PUYBUD`, Fluke 45 on FTDI `A95AME9U` (`identify`, 10:30; in `bench_config.json`). |
| **What is in the board's flash** | blank (nothing loaded yet). |
| **What the session is doing alone** | nothing. |

## The next thing Jason does

**Finish visit 1A** (5 min):
1. **Replace the supply leads**: short, thick leads from E3646A output 1 straight to J601, with no BNC cable or thin wire.
   Red on the upper pin (+5V), black on the lower pin (GND).  The old ones lost 0.47 V at 0.385 A, and the configured
   board draws nearly twice that.
2. Type **"v1a ready"**: the staircase again, and 5.0 V left on.
3. Fluke: **black on J602's top row** (ground, although the names are printed above it), **red on J602 bottom-row pin 1
   (+5V)**, then the same red on the bottom row's 7th pin (+5VA).  5 s each; the session reads them.  Want 4.6 V or more.

Then **visit 1B** (supply stays on): USB-C PC to USB PROG (upper), USB-C PC to USB USER (lower), SMA CLK OUT to CLK IN,
DAC 1 OUT to ADC A IN, DAC 2 OUT to ADC B IN, Ethernet to the lab switch; "v1b ready"; leave for an hour.

## The visits

| visit | what | Jason's time | state |
|---|---|---|---|
| 0 | unwrap, mark A/B, photos, jumpers | 15 min | board A done 2026-11-16 |
| 1A | board A: the supply on J601; the staircase; the eight LEDs; the Fluke along the RAILS header | 5 min | 2026-11-16: staircase pass, LEDs pass, 7 of 9 rails pass; +5V/+5VA 4.22 V from the leads: **re-read with thick leads next** |
| 1B | board A: USB PROG, USB USER, three SMA cables, Ethernet, microSD; then the session alone (an hour or more) | 5 min | |
| 2 | board A: both USB out for the cold-boot test; then the two generators and the scope on the six SMAs; then the session alone | 10 min | |
| 3 | board A: the sit-down session: LEDs, buttons, gain and source jumpers, the LED and photodiode, the taps, the power-on scope shot, HDMI | 30-40 min | |
| 4 | board B: visits 0 and 1 again | 10 min | |

## What is known so far

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
