# Scratch tools of 2026-11-17 (board A)

Kept from the session's scratch directory, as run; each made a row of `../BRINGUP_LOG.md` on 2026-11-17.  They run
from the tutorial repository's `src/verilog` (`~/mudd/133electronics/ecp5-2adc-2dac-tutorial`), whose modules they
import.

| file | what it did |
|---|---|
| `steps.py`, `steps_t.py` | REVB 24: ADC B's two-level steps, found and timed in a long record |
| `fluke_log.py`, `rail_test.sh`, `rail*.txt` | REVB 24: a rail on the Fluke read flip by flip against ADC B's steps (-4V2, 3V3A, +5VA, +1V1) |
| `frames_rx.py`, `build_frames.patch` | a frame counter in the stream's header (hdr7): do the steps follow received frames? (no) |
| `rxcnt_rx.py`, `build_rxcnt.patch` | the Ethernet receive clock counted in each packet: the TCXO against the switch, line by line with the steps |
| `build_nodcs.patch` | the AD9238's duty-cycle stabiliser off (the step changed sign) |
| `build_frozen.patch`, `build_sleep.patch` | the DDC held still; the DAC asleep |
| `build_hat.patch` | the three-cornered hat's clock counter (also `../configs1/clocks_hat.sv`) |
| `dc_iio.py` | after the short: DAC 1 held at seven levels, ADC A or B read through IIO (the compression at the ends) |
| `scope_log.py`, `tapb.txt` | the scope on J108 TAP B at the same seven levels (straight) |
| `codedensity.py` | ADC B's code density with a 16,381-sample triangle |
| `pm_gain.txt` | the tutorial's phasemeter gain check (1.17) |

Paths inside the scripts name the session's scratch directory and the old OpticsPCBs location, as they ran.  The
`build_*.patch` files are diffs against the tutorial's `src/verilog` sources as they were that day; each build was
the tutorial's own Makefile rule run on the patched copy.
