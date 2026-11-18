# Bring-up gateware for ECP5-2ADC-2DAC rev A

Two bitstreams and a Python driver, so the first board can be exercised block by block from the PC over the
FT2232H's serial channel, with no SoC, no LiteX and no Ethernet stack needed.  Written 2026-11-05, the day before the
boards were unwrapped, and debugged against the RTL in iverilog (`make sim`, `make test`); extended 2026-11-15 so that
every connector has a test (the RGMII data path, the microSD socket, USB USER's lines, HDMI) and so that the bench
procedures themselves run against the simulated board (`make cosim`, `bringup/bench.py --sim`).  Nothing here has yet
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
| `rtl/pll_sys.v` | The one PLL: 25 MHz to 125 MHz (RGMII transmit, the HDMI serialiser), 50 MHz (converters, SDRAM) and 25 MHz (HDMI pixels), phase-aligned, from a 500 MHz VCO.  Written by hand: `ecppll` fits only its first output exactly (it gave 52.08 or 150 MHz for the others). |
| `rtl/eth_test.v` | **The RGMII data path** at gigabit: a frame the PC writes into a 2048-byte buffer (destination address through FCS) is sent N times with preamble and SFD; the receiver counts frames, checks each one's CRC-32 in hardware and keeps the first for the PC to read back.  With the PHY in its own loopback (BMCR bit 14) it needs no cable.  `sim/tb_eth.v`, `sim/rgmii_phy_model.v`. |
| `rtl/hdmi_test.v` | **An HDMI test picture**, 640 x 480 at 59.5 Hz from the 25 MHz pixel clock: a one-pixel white border, eight colour bars, a grey ramp, a moving block (or all white, all black, a checkerboard).  `sim/tb_hdmi.v` decodes the TMDS bits back into the picture. |
| `rtl/periph.v` | `spi_byte`: one SPI byte to the microSD socket (the card in SPI mode: CLK, CMD = data in, DAT0 = data out, DAT3 = chip select).  `usb_mon`: USB USER's D+ and D- as plain pins: edges counted, the time spent in a bus reset. |
| `bringup_extra.lpf` | Pin pulls of this design only, appended to the generated LPF by `build.sh`: no pull on USB USER's lines (the generated file pulls them up: rev B list row 7), pull-ups on the card's data lines and the DDC lines, pull-downs on hot-plug detect and the Pmods. |
| `sim/tb_cosim.v`, `host/cosim.py` | **The co-simulation**: the board and a bench around it (the three self-test SMA cables or a generator, the SDRAM, the Si5351, the PHY, a microSD card, a USB host, a monitor's EDID, a Pmod loop), driven live by `host/ecp5bu.py` through two named pipes.  `SimBoard` is `Board` on it; `world()` moves the simulated cables and jumpers.  The simulated UART runs at 6.25 Mbaud, the counters' gate is 1 ms, and waits are shortened a thousand times. |
| `sim/` | `tb_top.v`: 60 self-checking checks of everything above through the UART, with models of the ADC (sine and ramp), the DAC (a monitor that checks setup), the SDRAM, an I2C slave (the Si5351) and an MDIO slave (the PHY ID).  `tb_file.v` is the same board driven by a command file.  `tb_sdram.v`, `tb_blink.v`, `tb_uart.v`: unit tests. |
| `host/ecp5bu.py` | The driver: `Board('/dev/ttyUSB1')`, `ident()`, `leds()`, `clocks()`, `capture()`, `adc_stats()`, `dac()`, `si5351_set()`, `phy_id()`, `sdram_test()`, `sdram_scan()`, and a command line.  I2C and MDIO are bit-banged through the GPIO register (about 50 us a bit over the UART: a Si5351 image takes a second). |
| `host/si5351.py` | The Si5351 arithmetic (from the GPSDO board's driver, which ran on real parts). |
| `host/test_sim.py` | `make test`: the Python driver's own bytes through `tb_file.v`, replies checked (17 checks, PASS). |
| `build.sh`, `Makefile` | `./build.sh blink|bringup` (tries placer seeds until every clock meets its constraint); `make sim`, `make test`, `make sim-blink`, `make sim-eth`, `make sim-hdmi`, `make cosim`.  Tools: the oss-cad-suite (`OSS_CAD_SUITE`). |

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
* nextpnr (the build of 2026-11-15, seed 1): every clock meets timing: the RGMII transmit clock 198 MHz and the
  PHY's receive clock 234 MHz against 125, clk_s 69 MHz against 50, the TCXO domain 104 MHz against 25, the pixel
  clock 119 MHz against 25.  nextpnr does not check the one synchronous crossing, the HDMI words from the pixel clock
  into the 125 MHz serialiser, which needs under 8 ns: its "Max delay posedge hdmi.clk_pix -> posedge eth.clk125" line
  reads 2.03 ns.  `build.sh` tries seeds until every clock passes.
* The RGMII engine alone reaches 224-261 MHz in both domains over four seeds (`build/eth_check/`).  Its first form met 125 MHz alone and
  98-117 MHz inside this design (an arithmetic compare into a clock enable, and an inferred block RAM whose output
  register yosys does not use: the transmit buffer is now a hand-instantiated DP16KD with `REGMODE_B = "OUTREG"`).

## What only the board can settle

| what | where it shows | the knob |
|---|---|---|
| the SDRAM's read latency (3 in simulation) and clock polarity | `sdram scan` | registers (`rdlat`, `pol`) |
| the ADC's capture phase (2 in simulation) | `bench.py v1b`, `phase` | a register (`adc_config(phase=, negedge=)`) |
| the RGMII receive sampling: each input goes through a DELAYG (`SCLK_CENTERED`, about 1 ns) before its IDDRX1F, because the PHY's RXDLY leaves 1.2-2.0 ns of hold and a plain input register on this FPGA needs 3.3 ns (data sheet table 3.22) | `eth_loop`: bad frames | `eth_test`'s parameter `RX_DELAY` ("NONE", or "USER_DEFINED" with `RX_DELAY_TAPS` 0-127 of 25 ps): one build per setting |
| which IDDRX1F output is the first nibble of a byte (written from memory of LiteEth's ECP5 PHY, not checked against silicon) | `eth_loop`: every frame bad; the raw capture shows the nibbles shifted | one register in `eth_test.v` |
| the transmit buffer's registered output (checked against a simulation model and the bitstream's configuration only) | frames arrive shifted by one byte | `TX_RAM_OUTREG = 0` |
| the RGMII transmit pins' slew (FAST here; the generated LPF leaves the default, SLOW) | `eth_loop`: bad frames | six lines of `bringup_extra.lpf` |
| the HDMI pins' drive (4 mA, as the LiteX platform file says) and the order of the DDR bits (D0 first, as the demo design and the simulation model have it) | no picture, or a monitor that will not lock | `bringup_extra.lpf`; `hdmi_test.v` |
| whether a DDR output register on the SDRAM clock, the converter clocks and DAC 2's fabric-routed clock behave as simulated | stages 5-7 | `dac_config(pol=)`, `sdram_test(pol=)` |
