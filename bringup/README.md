# The rev A bring-up, from the bench PC

The boards arrived 2026-11-05 (JLCPCB: 5 boards, 2 assembled).  The procedure is [`../BRINGUP.md`](../BRINGUP.md);
this folder is how it is run on the bench and what it found.

| file | what |
|---|---|
| [`BRINGUP_LOG.md`](BRINGUP_LOG.md) | what was done and measured, stage by stage, board by board, against each pass condition |
| [`REVB.md`](REVB.md) | everything a rev B should change, each with the measurement that showed it |
| `bench.py` | the instruments (`~/lab-instrument-control`) and the board (`../gateware/bringup/host/ecp5bu.py`) in one place; every reading appended to `data/board_<X>/<date>.jsonl` (not in git) |
| `bench_config.json` | the instruments' addresses and serial ports (written with defaults the first time; not in git) |

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

## The stages as commands

Every command logs what it read; `python3 bringup/bench.py show` prints the log's tail; `--board A` (or B) on every one.

| BRINGUP | cabled | command |
|---|---|---|
| 0 | the loupe | `bench.py note "..." --stage 0.2` for each finding |
| 1.2 | E3646A output 1 -> J601 (+ to +5V, - to GND) | `bench.py psu staircase` |
| 1.3 | the same; the Fluke on J602 | `bench.py psu on`, then `bench.py dmm +5V`, `dmm +3V3`, ... (the RAILS table in bench.py) |
| 1.4 | the IR camera | `bench.py psu log --seconds 300` in the background; the camera's readings as notes |
| 2 | USB PROG to the PC | `lsusb`, `openFPGALoader --detect -c ft2232` |
| 3 | | `openFPGALoader -c ft2232 gateware/bringup/build/blink.bit`; then `bringup.bit`; `bench.py board ident`; `bench.py run stage3.leds` |
| 4 | SDG CH1 -> CLK IN (JP3001 shunt in) | `run stage4.clocks`, `run stage4.si5351`, `run stage4.clkin` |
| 5 | scope CH1 -> DAC 1 OUT, CH2 -> DAC 2 OUT | `run stage5.dac_dc`, `run stage5.dac_sine` |
| 6 | SDG CH1 -> ADC A IN (JP101 shunt in) / nothing / DAC 1 OUT -> ADC A IN | `run stage6.adc_gen`, `run stage6.adc_noise`, `run stage6.loopback` |
| 7 | an Ethernet cable to the switch | `run stage7.sdram`, `run stage7.phy` |
