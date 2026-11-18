# The rev A bring-up, from the bench PC

The boards arrived 2026-11-05 (JLCPCB: 5 boards, 2 assembled).  The procedure is [`../BRINGUP.md`](../BRINGUP.md);
this folder is how it is run on the bench and what it found.

| file | what |
|---|---|
| [`BRINGUP_LOG.md`](BRINGUP_LOG.md) | what was done and measured, stage by stage, board by board, against each pass condition |
| [`REVB.md`](REVB.md) | everything a rev B should change, each with the measurement that showed it |
| [`STATUS.md`](STATUS.md) | where the bring-up stands and what Jason does next (`bench.py where` prints it) |
| `bench.py` | the instruments (`~/lab-instrument-control`) and the board (`../gateware/bringup/host/ecp5bu.py`) in one place; every visit of BRINGUP.md is one of its commands; every reading appended to `data/board_<X>/<date>.jsonl` (not in git) |
| `visit1.py`, `visit2.py`, `visit3.py` | the visits' procedures: `v1a`, `rails`, `v1b`, `coldboot`; `v2`; the `step`s.  Each test is one function with a docstring saying what is cabled and what passes |
| `analysis.py`, `report.py` | the arithmetic (sine fits, spectra, the Fluke walk's plateaus and their rails); the rows, the tables and the markdown reports |
| `simbench.py`, `test_bench.py` | the bench simulated (`--sim`), and every command run against it ("Dry run" below) |
| `bench_config.json` | the instruments' addresses and serial ports (written with defaults the first time; not in git) |
| `make_figs.py`, `figs/` | the visits' pictures |

## How the pieces talk

```
 bench PC  --LAN-->        SDS2104X Plus oscilloscope (192.168.8.203), SDG1032X generator (.246), 33220A (.240)
           --USB-RS232-->  E3646A power supply (output 1 = the board's 5 V on J601); Fluke 45 (the rails)
           --USB-C-->      the board's USB PROG: FT2232H channel A = JTAG (openFPGALoader), channel B = the serial port
                           named usb-FTDI_Dual_RS232-HS-...-if01 under /dev/serial/by-id: the bring-up gateware's register bus at 1 Mbaud
```

## Setting up (once)

1. `python3 ~/lab-instrument-control/scpi_link.py identify` finds the E3646A's and the Fluke's `/dev/serial/by-id/...`
   paths (it sends `*IDN?` only); put them in `bench_config.json` (`python3 bringup/bench.py check` writes the file
   with defaults the first time and says who answers).
2. The FPGA tools: the oss-cad-suite at the path in `../gateware/bringup/build.sh` (`OSS_CAD_SUITE` to override); the
   bitstreams are committed, so only `openFPGALoader` is needed to load them.  USB permission for the FT2232H: on bell
   the `openocd` package's `/lib/udev/rules.d/60-openocd.rules` already covers 0403:6010 for `plugdev` (no rule to
   install; see BRINGUP.md 0.3 and 2.2).
3. `pip install pyserial numpy` if missing (`python3 -c "import serial, numpy"`).

## The visits as commands

Jason cables a visit and types its words in the chat; the session runs the command and reads its output.  No
command asks a question.  Every command logs what it read (`bench.py show` prints the log's tail, `bench.py report`
the latest verdict of every test); `--board A` (or `B`) and `--sim` may stand anywhere on the line.

| visit (BRINGUP.md) | cabled | Jason types | the session runs |
|---|---|---|---|
| any time | | | `bench.py where` (prints `STATUS.md`) |
| 0 | nothing: the loupe, the jumpers | "v0 done" | `bench.py note "..." --stage 0.2` for each finding |
| 1A | E3646A output 1 -> J601 (+ to +5V, - to GND); the Fluke's probes at hand | "v1a ready" | `bench.py claim v1`, then `bench.py v1a`: the staircase (1.0, 2.5, 4.0, 5.0 V), then 5.0 V left on.  A current limit at any step ends it with the output off |
| 1A | the same; the black probe on the RAILS header's top row | "rails go" | `bench.py rails`: reads the Fluke for up to 180 s and takes each steady reading as the next of the nine rails; a skipped pin is named, not guessed |
| 1B | USB PROG, USB USER, three SMA cables (CLK OUT - CLK IN, DAC 1 OUT - ADC A IN, DAC 2 OUT - ADC B IN), Ethernet, a microSD card | "v1b ready" | `bench.py v1b`: loads the FPGA and its flash, says in one table what it found plugged where, then every self-test (about an hour with the 10-minute soak).  `--list` names the tests; `--only NAME,NAME` and `--skip NAME` choose; `--soak-minutes N` |
| 2, step 1 | both USB-C cables pulled | "usb out" | `bench.py coldboot`: ten power cycles, the supply's current after each, against what `v1a` and `v1b` logged |
| 2 | SDG CH1 -> ADC A IN, SDG CH2 -> CLK IN, 33220A -> ADC B IN; scope CH1 -> DAC 1 OUT, CH2 -> DAC 2 OUT, CH3 -> CLK OUT; both USB-C back | "v2 ready" | `bench.py claim v2`, then `bench.py v2`: checks every cable with 0.1 V first, then the ADCs against the generators and the DACs and CLK OUT on the scope; the generators off and the scope's settings back as found at the end |
| 3 | one thing moved per step | "next" | `bench.py step NAME` (`step --list`): `leds`, `buttons`, `prog`, `gain_x10`, `gain_x100`, `term_open`, `noise_0`, `noise_10k`, `light`, `tap`, `tap_b`, `tap_tia`, `tap_n4v2`, `poweron`, `dac_clock`, `hdmi`, `pmod`.  Each prints first the one thing that must have been moved, and last what to put back |
| when the board leaves | | | `bench.py release` |
| 4 | board B | as visits 0, 1A, 1B | the same commands with `--board B` |

**The claims.**  A supply or generator output is switched on only while this project (`ECP5-2ADC-2DAC`) holds the
bench claim on that channel (`~/lab-instrument-control/bench_claims.py`): `claim v1` records the supply and the
Fluke, `claim v2` adds the generators and the scope, each with what it is cabled to and the most it will be driven
to.  A command that finds the claim missing, or another project's, stops with one sentence before it touches
anything.  A claim is Jason's word that the cables are on this board: make it only after he has said so.

**The results.**  Every test prints rows: `pass`, `FAIL` (with what to do next on the line under it), `info` (a
number kept, with no pass condition) or `skipped` (with why: its cable was not found, or it cannot run in
simulation).  `v1b` and `v2` end with a summary and write the same as `data/board_<X>/report_<visit>_<time>.md`;
their exit status is 0 even with FAIL rows (the report is the result), 1 when the command could not start (a
claim, a cable that must be moved first).

The older single-instrument commands still work (`psu staircase | on | off | read | log`, `dmm RAIL`, `scope shot |
meas`, `gen sine | off`, `board ...`, `run stageN.x`, `show`, `check`): `bench.py --help` lists them.

## Dry run

Nothing here has run on hardware yet; everything has run against a simulation.  `--sim` on any command replaces
the board by its RTL in iverilog (`../gateware/bringup/host/cosim.py`: the same driver class as the real board)
and the five instruments by the fakes of `simbench.py`, whose methods take the same arguments as the real drivers'
and which follow the simulated board (the fake scope reads the DAC registers; a fake generator's output feeds
the simulated ADC).  A simulated run logs under `data/sim/`, never into a board's own log.

```sh
python3 bringup/bench.py --sim v1a                           # seconds: the fake supply only
python3 bringup/bench.py --sim v1b                           # 21 minutes: the co-simulated board is slow (1 ms of its time costs 4 s)
python3 bringup/bench.py --sim --sim-fault crossed,no_card v1b --only sd,dc_transfer    # something cabled wrong
python3 bringup/bench.py --sim step gain_x10 --sim-as-found  # visit 3: the jumper was NOT moved
python3 bringup/test_bench.py                                # everything: 22 minutes with 8 side by side, PASS or FAIL at the end
python3 bringup/test_bench.py --quick                        # 6 s: no co-simulation
```

`--sim-fault` takes names from `simbench.FAULTS` (`short`, `overcurrent`, `rail_low`, `rail_skipped`, `rail_twice`,
`crossed`, `no_sma_a`, `no_clk_cable`, `no_card`, `no_usb`, `no_link`, `gain_a_x10`, `term_b_open`, `monitor`,
`pmod_loop`, `no_flash_boot`, `gens_swapped`, `scope_swapped`, `sdg_swapped`, `no_gen_b`, `no_scope_clk`,
`scope_10x`).

`test_bench.py` checks four things: (1) every instrument method the tool's source uses exists in the real driver
class and takes the arguments the fake takes (the real classes are imported to read their signatures, never
opened); (2) the arithmetic on made-up data; (3) the claim refusals, on a scratch claim record; (4) every command,
each as its own process as it would be typed, with the faults above: the right finding in plain words, never a
traceback.  The outputs stay in `data/sim/test_bench/<name>.log`.

In simulation the sizes are small (`bench.SIZES`: 512-sample captures, 256 SDRAM words, 20 + 5 Ethernet frames, no
soak) and four things are skipped because they are the PC's own hardware: openFPGALoader (`jtag`, `load_blink`,
`load_bringup`, `flash`), real frames on the wire (`eth_wire`), running from USB power (`usb_power`), and the PROG
button (`step prog`).  The simulated bench has no frequency response, no distortion and no noise source of its
own (the Johnson-noise step uses a small sine in its place), and the fake instruments answer at once.

### What the dry run does not prove

A PASS from `test_bench.py` says the tool runs to its end and words its findings rightly on an ideal board.  It
says nothing about these, which are first exercised on hardware:

* **Code that never runs under `--sim`:** opening the real instruments and the board's serial port (the
  constructors in `Bench`, the SDG's `vlimit`, the 33220A over USB); the four openFPGALoader tests and the 115200
  baud greeting; `eth_wire` (its sockets, `pc_broadcast`, the PC's firewall); the kernel-log lines of `usb`;
  `usb_power`; `step prog`; the bench branch of the HDMI frame rate (the simulation times frames another way).
* **The instruments' real behaviour:** how fast the Fluke reads and what it shows with the probe in the air; the
  scope's measurements (how long they take to follow a change, whether its frequency reading is good to 0.1 %),
  putting its settings back, how long a waveform takes to fetch in `step poweron`; the E3646A's mode reports.
* **Every analog threshold:** the simulated chain is ideal (quantisation and one code of noise), so no pass window
  for noise, SFDR, flatness, cross-talk, offsets, capture phase or SDRAM latency has been stressed.  The supply
  currents, the rails, the power-on ramps, the DAC clock's overshoot, the LED-to-photodiode path and the taps are
  made-up numbers in `simbench.py`.
* **The cold boot's levels:** "booted" is "at least 5 % more current than unconfigured", a guess until measured.
