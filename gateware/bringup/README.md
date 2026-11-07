# Bring-up gateware for ECP5-2ADC-2DAC rev A

Two bitstreams and a Python driver, so the first board can be exercised block by block from the PC over the
FT2232H's serial channel, with no SoC, no LiteX and no Ethernet needed.  Written 2026-11-05, the day before the
boards were unwrapped, and debugged against the RTL in iverilog (`make sim`, `make test`); nothing here has yet
run on a board.  The procedure that uses it is [`../../BRINGUP.md`](../../BRINGUP.md).

| file | what |
|---|---|
| `rtl/blink.v` | **The first bitstream** (`build/blink.bit`, 100 kB): no PLL, no bus.  LED0-7 chase (one step per 0.67 s), BTN1 lights all eight, BTN0 reverses, the RGB LED cycles, CLK OUT carries the 25 MHz TCXO, the serial channel prints `ECP5-2ADC-2DAC blink <n>` once a second at **115200** baud.  ADC powered down, DAC asleep, PHY out of reset. |
| `rtl/top.v` | **The bring-up design** (`build/bringup.bit`, 200 kB): a register bus over the UART at **1 Mbaud**, clocked by the TCXO alone; a PLL to 50 MHz for the converters and the SDRAM.  The register map is at the top of the file and in `host/ecp5bu.py`. |
| `rtl/uart.v`, `rtl/regbus.v` | 8N1 UART; the protocol: command byte (bit 7 write, 6:0 register), 4 data bytes LSB first; a read answers 4 bytes; a read of 0x7F streams the capture memory.  A half-sent write times out after 40 ms; five 0x00 bytes resynchronise.  A 64-byte FIFO takes bytes that arrive while a reply is going out. |
| `rtl/clkcount.v` | A frequency counter per clock input (CLK IN, the three Si5351 outputs, the PHY's RXC, the PLL, the TCXO itself): edges per 1 s gate, read in Hz; a dead clock reads 0 and its sequence number stops. |
| `rtl/adc_capture.v` | The AD9238: the sample clock (clk_s itself = 50 MS/s, or a toggle every `div` cycles: 25 MS/s at 1), the data latched `phase` cycles after our rising edge (2 nominal; scan it), 8192 samples of both channels into memory, decimation, running min/max/mean/out-of-range per window. |
| `rtl/dac_gen.v` | One AD9767 port: its clock (WRT and CLK tied, as the datasheet allows), data updated at the clock's falling edge, an NCO (sine from `sine_lut.hex`, sawtooth, square, triangle) or a DC code, amplitude shift and offset. |
| `rtl/sdram_test.v` | The W9825G6KH: JEDEC init, CL 2, one word per access with auto-precharge, a refresh every 6 us; writes `pattern(addr)` to N words then reads them back, counting mismatches; the read latency is a register (3 in simulation: scan 1..7 on the board). |
| `rtl/pll_sys.v` | `ecppll -i 25 -o 50`. |
| `sim/` | `tb_top.v`: 60 self-checking checks of everything above through the UART, with models of the ADC (sine and ramp), the DAC (a monitor that checks setup), the SDRAM, an I2C slave (the Si5351) and an MDIO slave (the PHY ID).  `tb_file.v` is the same board driven by a command file.  `tb_sdram.v`, `tb_blink.v`, `tb_uart.v`: unit tests. |
| `host/ecp5bu.py` | The driver: `Board('/dev/ttyUSB1')`, `ident()`, `leds()`, `clocks()`, `capture()`, `adc_stats()`, `dac()`, `si5351_set()`, `phy_id()`, `sdram_test()`, `sdram_scan()`, and a command line.  I2C and MDIO are bit-banged through the GPIO register (about 50 us a bit over the UART: a Si5351 image takes a second). |
| `host/si5351.py` | The Si5351 arithmetic (from the GPSDO board's driver, which ran on real parts). |
| `host/test_sim.py` | `make test`: the Python driver's own bytes through `tb_file.v`, replies checked (17 checks, PASS). |
| `build.sh`, `Makefile` | `./build.sh blink|bringup`; `make sim`, `make test`, `make sim-blink`.  Tools: the oss-cad-suite (`OSS_CAD_SUITE`). |

## Loading

```sh
openFPGALoader --detect -c ft2232                # the ECP5's IDCODE (0x41111043 for the LFE5U-25F)
openFPGALoader -c ft2232 build/blink.bit         # into the FPGA (SRAM): until the next power cycle
openFPGALoader -c ft2232 build/bringup.bit
openFPGALoader -c ft2232 -f build/bringup.bit    # into the flash: the board boots it by itself (CFG = master SPI)
python3 host/ecp5bu.py ident                     # the serial channel is the second ttyUSB the FT2232H makes
```

The FT2232H enumerates as 0403:6010 with two interfaces: A is the JTAG (openFPGALoader takes it from the
`ftdi_sio` driver while it runs), B the serial channel (`/dev/ttyUSB1` when nothing else is plugged in; check with
`ls /dev/serial/by-id/`).  openFPGALoader needs USB permission on 0403:6010: a udev rule giving it to
the user's group (on bell the `openocd` package's `60-openocd.rules` does; the oss-cad-suite ships none), or run it as root.

## What the simulation says about timing

* The DAC data change at the falling edge of WRT/CLK; the monitor saw 20 ns of setup and hold at 25 MS/s and 10 ns
  at 50 MS/s, which is what the AD9767 wants (2 / 1.5 ns).
* The ADC capture is right at `phase` 1 or 2 with the model's tPD of 3.5 ns; the real tPD is 2-6 ns plus the
  clock's trip out and the data's trip back (about 2 ns each way): phase 2 nominal at 25 MS/s.
* The SDRAM reads back with a read latency of **3** cycles in simulation (CL 2 plus the input register);
  on the board the latency scan (`host/ecp5bu.py sdram scan`) settles it, and `pol` inverts the SDRAM clock if
  the write side turns out marginal.
* DAC 2's clock pins (M9, P8) are in bank 8, whose I/O cells have no DDR register (ecppack refused the ODDRX1F
  there), so that clock goes out through the fabric with one register of delay to match the others.
* nextpnr: every clock meets timing (clk_s 70 MHz against 50; the TCXO domain 100 MHz against 25).
