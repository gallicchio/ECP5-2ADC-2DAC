# ECP5-2ADC-2DAC rev A: the bring-up

Written 2026-11-05, the evening the boards arrived (JLCPCB: 5 PCBs, 2 assembled, build 34 of 2026-10-09), for the
bring-up of 2026-11-06 in Jason's office, run over chat: Jason plugs in cables and moves jumpers, the session drives the
bench supply, the scope, the generators and the board, and logs every reading.  The rule of the bench (CLAUDE_PCB.md
section 9): **plug in; do not solder or hold a probe.**  Every node worth a look has a U.FL tap or a header pin, and
every stage below says which one to plug into.  The stages are in order; each has a *pass* condition; the
dead-on-arrival table at the end says which stage retires which risk.

What goes where:

| thing | where |
|---|---|
| this procedure | `BRINGUP.md` (this file) |
| running it: the bench tool, the log, the rev B list | [`bringup/`](bringup/README.md): `bench.py`, `BRINGUP_LOG.md`, `REVB.md`; raw data in `bringup/data/` (not in git) |
| the gateware it uses | [`gateware/bringup/`](gateware/bringup/README.md): `build/blink.bit`, `build/bringup.bit`, `host/ecp5bu.py`; simulated end to end in iverilog (`make sim`, `make test`), not yet run on silicon |
| the instruments | `~/lab-instrument-control` (E3646A, Fluke 45, SDS2104X Plus, SDG1032X, 33220A); `bench_config.json` holds the addresses |
| what the board is | [`README.md`](README.md); the reviews' open questions for the first board: `DESIGN_REVIEW_RESPONSE.md` section 6 (R2-11, R2-12), stage 8 below |

## What to have on the bench

| thing | why | have |
|---|---|---|
| **E3646A** bench supply, output 1, into **J601 "5V IN"** (2-pin header: + and GND as printed) through a 2-pin lead with 2.54 mm female ends; 5.00 V, 1.0 A limit, OVP 5.6 V | stage 1: a bench input that reads its own current; J601 also turns the USB power path off (Q602), so the PC's port is never asked for the board's 0.7 A.  4.75-5.25 V at the header (the LM27761's absolute maximum is 5.8 V); the SS34 (D601) drops 0.3-0.5 V on the way to +5V | have; the lead: make |
| a **USB-C cable** to the PC, into **J501 "USB PROG"** (the upper of the two USB-Cs, below the RJ45) | stage 2 on: JTAG and the serial channel.  The board can also run from this alone (0.6-0.7 A: a USB 3 or USB-C port, not a 2.0 one) | have |
| **Fluke 45** (or any DMM) with a probe and a **ground spring** or clip | stage 1: the nine rails on J602 | have |
| **SDS2104X Plus** scope, BNC leads, two SMA-to-BNC adapters | stages 1, 4-6: the DAC outputs, CLK OUT, the taps | have |
| **SDG1032X** generator, an SMA-to-BNC lead | stages 4 and 6: CLK IN, the ADC inputs | have |
| **U.FL-to-SMA pigtails**, 2 or more (Hirose U.FL-LP-088, 100-200 mm; 30 matings each) | the four taps J107 TAP A, J108 TAP B, J109 TAP TIA, J603 TAP -4V2 (49.9 ohm in series: a 50 ohm input sees half) | buy if none |
| **SMA male-male lead**, 1, and a 50 ohm SMA termination | stage 6: DAC 1 OUT to ADC A IN | have |
| 2.54 mm **jumper shunts**, 10 | JP101-104, JP201-204, JP1203, JP2009, JP3001, JP501 (table below) | have |
| an **Ethernet cable** to the lab switch | stage 7 | have |
| a loupe or the USB microscope; `mfg/release/ECP5-2ADC-2DAC_assembly_top.pdf` and `_bottom.pdf` and `PLACEMENT_CHECKS.txt`, open on a screen | stage 0 | have |
| the IR camera or thermometer | stage 1.4 | have |
| the oss-cad-suite's `openFPGALoader` (any machine with the USB cable; the bench PC has it at the path in `gateware/bringup/build.sh`); USB permission for 0403:6010 (on bell the `openocd` package's `/lib/udev/rules.d/60-openocd.rules` already gives it to `plugdev`, checked 2026-11-06) | stages 2-3 | have |

## The board, as the bench sees it

Left end, top to bottom, 17 mm apart: J301 **CLK IN**, J302 **CLK OUT**, J101 **ADC A IN**, J102 **ADC B IN**, J204 **DAC 1 OUT**, J205
**DAC 2 OUT** (each name and its limit printed under its SMA; ±1 V MAX IN on the ADCs, ±1 V MAX OUT on the DACs).  Right
end, top to bottom: J401 **RJ45**, J501 **USB PROG**, J502 **USB USER**, J503 **mini-HDMI**, J304 **Pmod B**, J303 **Pmod A**; J504 microSD on
the back.  Top edge: the TCXO X301, the Si5351 U301, the eight white LEDs LED0-7 (D301-D308) and the buttons SW301 **BTN0**
(reset in the LiteX plan) and SW302 **BTN1**.  Bottom edge, left to right: SW101 (the noise resistors), J105 **NOISE**, D103
the photodiode, J106 **PD EXT**, J109 **TAP TIA**, U606 (the -4.2 V pump), J602 **RAILS**, U601/U602 (the bucks), J601 **5V IN**,
J603 **TAP -4V2**.  Middle: U1 the FPGA, U305 the SDRAM above it, U306 the flash and J305 **JTAG** and SW303 **PROGRAMN** below
it; U103 the AD9238 and U201 the AD9767 to its left; U401 the PHY and U502 the FT2232H to its right; D309 the RGB LED by
Pmod A.

**The RAILS header J602** (2 x 9, by U601/U602): the odd pins are the rails, the even pins ground, so a probe with a ground
spring reaches every rail without a clip.  In order as printed: +5V, +3V3, +1V1, +2V5, +3V3_ADC, +3V3_DAC, +5VA, +1V0_PHY,
-4V2.

**The POWER GOOD LEDs** (dim red, 0.3 mA, in a row by the header): D602 +5V, D603 +3V3, D604 +2V5, D605 +3V3_ADC, D606
+3V3_DAC, D607 +5VA, D608 -4V2, D609 +1V1 (through Q601: the core rail cannot light a diode itself).  Eight LEDs; +1V0_PHY
has a header pin but no LED.

**Jumpers, as they stand for the bring-up** (every 3-pin jumper has its two choices printed beside its outer pins, every
2-pin jumper what a shunt does):

| jumper | what | bring-up position |
|---|---|---|
| JP101, JP201 **TERM** (ADC A, B) | shunt in = 50 ohm input; open = high-Z | **shunt in** (the generator and the DAC are 50 ohm sources) |
| JP102, JP202 **SRC** | SMA / ALT: what the preamp sees | **SMA**; ALT only for the noise source (A, B) or the photodiode (B, through JP1203) |
| JP103, JP104 (A), JP203, JP204 (B) **GAIN** | per stage: shunt = x1, open = x10 (x1, x10, x100 in all) | **both shunts in** (x1): ±1 V full scale |
| JP1203 **ALT** (channel B) | NOISE / PHOTODIODE | PHOTODIODE (unused until stage 6.6) |
| JP2009 **LED** (the LED driver's current) | on-board LED D201 / J210 LED EXT | **open** until the DAC checks out (the driver would put up to 48 mA through D201 at full scale) |
| JP3001 **TERM** (CLK IN) | shunt in = 50 ohm | **shunt in** for the generator; open for a 3.3 V square wave from another board's CLK OUT |
| JP501 **FTDI OFF** | shunt holds the FT2232H in reset so J305 takes an external JTAG programmer | **open** |
| SW101 (the noise resistors 0 / 100 / 1 k / 10 k) | | **all off** |

**Power paths.**  USB PROG's 5 V comes through F601 (a 2 A resettable fuse) and Q602 (a P-FET) to +5V; the bench header
J601 comes through F602 and D601 (SS34) and lifts Q602's gate, so with a bench supply on J601 the USB cable carries data
only.  +5V feeds U601 (+3V3 buck), U602 (+1V1 buck), U604 (+3V3_ADC, behind 2.2 ohm), U605 (+3V3_DAC), U606 (the -4.15 V
charge pump, "-4V2") and the +5VA bead; +3V3 feeds U603 (+2V5 = VCCAUX) and the +3V3_DRV / +3V3_DAC_D / +3V3_ETH beads.
About 3 W, 0.6-0.7 A at 5 V with everything running.

## Stage 0: before power (the evening before, or the first half hour)

0.1 **Unwrap** and photograph both assembled boards, both sides.  Mark them **A** and **B** with a pen on the back by the
    RAILS header.  Count the bare boards (3).  Note the bag's contents and any damage.  `bench.py note "..." --stage 0.1`.

0.2 **Look**, with the loupe, against the assembly drawings and `PLACEMENT_CHECKS.txt` (the parts JLCPCB rotated by rule
    rather than by a preview reading are the ones to check).  In order of what a mistake would cost at first power:
    (a) D601 (SS34, by J601): its cathode bar toward +5V (the side away from the header).  Backwards, the bench supply
        sees a diode across its output and the staircase of stage 1.2 finds it at 1 V.
    (b) Q602 (AO3401A, SOT-23 by F601) and Q601 (SS8050 by D609): pin 1 by the dot.
    (c) The eight power LEDs D602-D609 and the eight white LEDs: cathode marks all the same way along each row (backwards
        they stay dark; no harm).  D309's reading was confirmed by JLCPCB's e-mail of 2026-10-22.
    (d) The BAV99s D101, D102 (SOT-23 after the 100 ohm 1206s) and D111, D112 (on the back under the THS4521s): pin 1 by the
        bevel.  D103, the photodiode: its anode toward -4V2 as `FABRICATION_NOTES.txt` says.
    (e) Pin 1 of the LQFP-64s U103 (AD9238) and U401 (RTL8211F), the LQFP-48 U201 (AD9767), the LQFP-64 U502 (FT2232H), the
        MSOP-10 U301 (Si5351), the DFN-8 U606 (LM27761): the chamfer or dot at the silkscreen's dot.  The BGA cannot be read;
        stage 2's IDCODE reads it.
    (f) The six SMAs' barrels straight out past the left edge; the two Pmod sockets' openings facing the right edge; the
        USB-Cs and the HDMI jack 1-2 mm past the edge with their shells soldered; J504's card slot facing east.
    (g) Nothing missing: every IC's position populated; the three crystals (Y301, 25 MHz, by the Si5351; Y401, 25 MHz, by the PHY; Y501, 12 MHz, by the
        FTDI) and the TCXO X301 present; both 4030 inductors (L617, L618, the bucks') on the back.
    A part that differs from the preview is JLCPCB's placement, not the CPL: a photo to their support, and no power to that
    board until the part is turned.  Normal and wanting nothing: the vias are filled and capped; through-hole pins have
    no inner-layer rings.

0.3 **The bench PC**: `python3 ~/lab-instrument-control/scpi_link.py identify` for the supply's and the Fluke's ports;
    `python3 bringup/bench.py check` (writes `bringup/bench_config.json`, says who answers); the scope and the generator
    on the LAN.  `openFPGALoader --Version` runs.  USB permission for the FT2232H (0403:6010): on bell the `openocd`
    package's `/lib/udev/rules.d/60-openocd.rules` already gives it `MODE 660, GROUP plugdev` and Jason is in `plugdev`
    (checked 2026-11-06 with the two FT232 adapters, which the same file covers); no rule to install.  Nothing from this
    folder needs `sudo`; what does is Jason's, as a copy-paste block in the chat.

0.4 **Jumpers** as the table says; nothing on any SMA or header yet; JP2009 open.

*Pass:* both boards photographed and inspected, every polarity in (a)-(e) as drawn, the bench answers.

## Stage 1: first power from the bench supply, no USB (board A, then B)

1.1 **The supply alone**: output 1 to the lead, nothing on the board; `bench.py psu on` sets 5.00 V, 1.0 A, OVP 5.6 V, the
    E3646A's other output at 0 V (one switch serves both); read 5.00 V, 0.00 A; `psu off`.  Then the lead into J601, + to
    the pin marked +5V.  **Check the polarity twice**: the SS34 protects against a reversed supply, but only up to its
    3 A and the fuse's trip, and a reversed 5 V at 1 A for the seconds it takes to notice is a hot diode.

1.2 **The staircase**: `bench.py psu staircase` puts 1.0 V (0.3 A limit) for 2 s and reads the current, then 2.5 V (0.3 A),
    4.0 V (0.5 A), 5.0 V (1.0 A), and switches off.  Expected: at 1.0 V under 30 mA (below every regulator's start-up
    threshold: the LEDs' resistors and leakage); at 2.5 V the bucks starting, 50-200 mA; at 4.0 V 0.2-0.4 A; at 5.0 V
    0.3-0.6 A with the FPGA unconfigured (the ADC is on with no clock, the DAC on, the PHY running, the FTDI enumerating
    nothing).  The supply in CC at any step (`mode` = CC in the log) is a short or a reversed part: off, and the IR camera
    at 1.0 V, 0.3 A finds what is warm.  *Pass:* every step in CV, the current rising with the voltage, under 0.7 A at 5 V.

1.3 **The rails**: `bench.py psu on`, then the Fluke on each odd pin of J602 with the ground spring on the pin beside it:
    `bench.py dmm +5V`, `dmm +3V3`, `dmm +1V1`, `dmm +2V5`, `dmm +3V3_ADC`, `dmm +3V3_DAC`, `dmm +5VA`, `dmm +1V0_PHY`,
    `dmm -4V2` (with no Fluke configured it asks for the reading).  The limits (`RAILS` in bench.py):

    | rail | pin | expect | source |
    |---|---|---|---|
    | +5V | 1 | 4.60-5.25 V (the bench input less D601's drop) | J601 through F602, D601 |
    | +3V3 | 3 | 3.23-3.43 V | U601 buck, 0.6 V x (1 + 15k/3.3k) = 3.33 V |
    | +1V1 | 5 | 1.07-1.13 V | U602 buck, 1.10 V |
    | +2V5 | 7 | 2.45-2.55 V | U603 LDO (VCCAUX) |
    | +3V3_ADC | 9 | 3.25-3.35 V | U604 LDO behind 2.2 ohm |
    | +3V3_DAC | 11 | 3.25-3.35 V | U605 LDO |
    | +5VA | 13 | 4.50-5.25 V | +5V through a bead |
    | +1V0_PHY | 15 | 0.95-1.05 V | the PHY's own switcher (L401 on the back) |
    | -4V2 | 17 | -4.35 to -3.95 V | U606 LM27761 at -4.15 V |

    And the eight LEDs all lit (D609 is the 1.1 V rail's: it goes through Q601, so it is the one most likely to be dark
    for a reason).  *Pass:* nine rails in their windows, eight LEDs on.  A rail low with its LED dark: its regulator's
    input first (the Fluke on the regulator's input capacitor), then its enable (tied to its input on every one).

1.4 **Heat**, after five minutes at 5.0 V: the IR camera over both sides.  Expected warm: U604 (the ADC's LDO: it takes
    (5 - 3.3) V x 0.2 A less the resistor's share once the ADC is clocked; unclocked less), U401 (the PHY, 0.3 A inside),
    the two bucks a little.  Nothing over 60 C on a 25 C bench; nothing warm that has no reason to be (an op amp, a
    BAV99, the photodiode, a passive).  `bench.py psu log --seconds 300` in another terminal logs the current meanwhile;
    a slow rise is a part heating.  *Pass:* the current flat to 5 %, nothing unexpected warm.

1.5 **The power-on sequence on the scope** (the review's R8): the scope's two probes on J602 pins 3 (+3V3) and 5 (+1V1),
    ground springs on pins 4 and 6; single trigger on +3V3 rising through 1 V, 2 ms/div; `psu off` then `psu on`.  What
    is expected: both bucks start together off the same 5 V (soft start about 0.8 ms); +3V3 reaches 3 V before or with
    +1V1 reaching 1 V, and the sysCONFIG rule (VCCIO8 above the flash's VIH before VCC and VCCAUX pass their POR) holds
    with the 100 nF on PROGRAMN adding 0.5 ms.  Save the screenshot (`bench.py scope shot power_on`).  Then the same on
    pin 15 (+1V0_PHY) against pin 3: Realtek asks for a 3.3 V rise slower than 0.5 ms (R2-12); read the rise time off
    the shot.  *Pass:* the traces saved and the order as expected; a +3V3 rise faster than 0.5 ms goes in `REVB.md`.

1.6 **The -4.2 V pump's noise**: a pigtail from J603 (TAP -4V2) to the scope at 1 MOhm, AC coupled, 20 mV/div, 1 us/div:
    the LM27761's 2 MHz residue after the bead.  Expected: a few millivolts; log the peak-to-peak.

*Stage 1 pass:* board A and board B both through 1.2-1.4; 1.5-1.6 on board A (once is enough unless B differs).

## Stage 2: USB PROG, JTAG (board A; B the same at the end)

2.1 **Enumerate**: with the bench supply on (Q602 keeps the PC's 5 V out), the USB-C cable into J501.  On the PC:
    `lsusb` shows `0403:6010 Future Technology Devices International, Ltd FT2232C/D/H Dual UART/FIFO IC` (a blank
    EEPROM: the default name), and `ls /dev/serial/by-id/` two new `usb-FTDI_Dual_RS232-HS-if00` / `-if01` entries
    (`/dev/ttyUSB0` and `1` if nothing else is plugged).  Channel A (if00) is the JTAG, channel B (if01) the serial.
    `dmesg -w` in another terminal while plugging: no "device descriptor read" errors.  *Pass:* 0403:6010 and two ports.

2.2 **The FPGA answers**: `openFPGALoader --detect -c ft2232` prints the IDCODE **0x41111043** (LFE5U-25F).  It
    detaches ftdi_sio from channel A while it runs; channel B stays a tty.  A permission error (`ls -l /dev/bus/usb/<bus>/<dev>` not `root plugdev`) means
    the openocd rule did not apply; the fix is Jason's: `sudo cp /lib/udev/rules.d/60-openocd.rules /etc/udev/rules.d/ &&
    sudo udevadm control --reload && sudo udevadm trigger`, then re-plug (the oss-cad-suite ships no rule file of its own).
    No IDCODE at all is the JTAG wiring (TCK T10, TMS T11, TDI R11, TDO
    M10, pulled as the sheet says) or JP501 fitted.  *Pass:* the IDCODE.

2.3 **USB power alone**: `psu off`, the board now powered by the PC's port through F601/Q602: the LEDs stay on, `--detect`
    still answers, the port's current if the PC reports it.  Then `psu on` again for the rest of the day (the P-FET hands
    over without a glitch: the LEDs do not blink).  *Pass:* runs from USB alone.

## Stage 3: the first bitstreams (board A)

3.1 **blink**: `openFPGALoader -c ft2232 gateware/bringup/build/blink.bit` (into the FPGA's SRAM, 2 s).  Expected: the
    eight white LEDs chase, one step every 0.67 s; the RGB LED cycles red, green, blue, off; BTN1 held lights all eight;
    BTN0 held reverses the chase; CLK OUT (J302, SMA-to-BNC to the scope at 50 ohm) shows the 25 MHz TCXO at 1.65 V
    amplitude (3.3 V open circuit through the 49.9 ohm); and `python3 -m serial.tools.miniterm /dev/ttyUSB1 115200`
    prints `ECP5-2ADC-2DAC blink 0`, `... 1`, once a second.  The scope's frequency counter on CLK OUT reads the TCXO
    against the scope's timebase (good to about 25 ppm; stage 4 does better).  *Pass:* all five; the current now (log it).

3.2 **bringup**: `openFPGALoader -c ft2232 gateware/bringup/build/bringup.bit`.  The chaser runs again (from the register
    design now, with the RGB LED green blinking once a second when the PLL is locked, red steady if it is not, blue on
    bus activity).  Then `python3 bringup/bench.py board ident`: the ID register 0xEC5BA2D2, the version 20261105, and
    STATUS with `pll_lock` true.  `bench.py run stage3.leds` walks every LED and colour from the register.  `bench.py
    board clkout tcxo|clk_s|low|high` moves CLK OUT between the TCXO, the 50 MHz PLL output, 0 and 3.3 V (the scope
    sees each).  *Pass:* the ID, the PLL locked, every LED, CLK OUT obeying.
    If `ident` fails: `ls /dev/serial/by-id/` (channel B is if01); the LEDs chasing means the design is in; a wrong byte
    back means a baud mismatch (the design expects 1 Mbaud from a 25.000 MHz TCXO: a dead TCXO would also stop the
    chaser); nothing back means uart_tx (H14) / uart_rx (H15) or the FTDI's channel B.

3.3 **The flash**: `openFPGALoader -c ft2232 -f gateware/bringup/build/bringup.bit` writes the W25Q128 through the
    FPGA (a minute).  Power-cycle (`psu off`, `psu on`, USB unplugged so nothing else powers it): the chaser starts by
    itself within a second (CFG = 010, master SPI, the 100 nF on PROGRAMN).  SW303 (PROGRAMN) pressed: the LEDs go out
    and the chaser restarts.  *Pass:* boots from the flash with no PC.  From here the board comes up ready for `bench.py`
    at every power-up.

3.4 **Board B** through 2.1-3.3 (the flash too), then back to A for the rest.

## Stage 4: the clocks (board A)

4.1 `bench.py run stage4.clocks`: every clock input's frequency from the board's own counters (1 s gate from the TCXO):
    `tcxo` 25,000,000 by construction (it counts its own gate: a check of the method), `clk_s` 50,000,000 ±1 (the PLL),
    `clk_in` 0 (nothing on the SMA), `si0`-`si2` 0 (the Si5351 unprogrammed; its outputs power up off), `rxc` 0 or 25 MHz
    (the PHY's RXC with no link: the RTL8211F idles it at 2.5 or 25 MHz depending on the mode; note what it is).
    *Pass:* 25,000,000 and 50,000,000 ±1.

4.2 `bench.py run stage4.si5351`: the I2C scan finds 0x60; the three outputs are set to 10, 25 and 100 MHz (CLK0 and
    CLK1 from PLLA, CLK2 from PLLB, 2 mA drive); the counters read them ±1 Hz (they are integer-mode from the same
    25 MHz crystal, so their ratio to the TCXO is exact to the crystal's offset: the counts read the Si5351 crystal's
    ppm against the TCXO; expect under ±30 ppm).  `bench.py board clkout si2` puts the 100 MHz on CLK OUT for the scope.
    *Pass:* 0x60 answers, three frequencies as set.  No ACK: the pull-ups (4.7 k), SDA A15 / SCL E13.

4.3 `bench.py run stage4.clkin`: the SDG's channel 1, 10 MHz sine, 1 Vpp into 50 ohm (JP3001 shunt in), SMA-to-BNC to
    J301.  The TLV3501 squares it and the counter reads it: the difference from 10,000,000 Hz is the TCXO's error
    against the SDG's timebase (both ±2.5 ppm class: expect under ±5 ppm, i.e. ±50 Hz).  Then the SDG at 0.3 Vpp and
    at 3 Vpp: the count must not change (the comparator's threshold is at mid-rail, 6 mV of hysteresis).  Then a 1 MHz
    square wave, 3.3 Vpp, offset 1.65 V, JP3001 open: 1,000,000.  *Pass:* ±50 Hz at 10 MHz, level-independent.

4.4 The TCXO against the house 10 MHz, if a GPSDO or the OCXO distribution amplifier is at hand: the same measurement
    with a reference on CLK IN gives the TCXO's absolute error; log it in `BRINGUP_LOG.md` (the ±2.5 ppm spec).

## Stage 5: the DACs (board A)

Scope CH1 on J204 DAC 1 OUT and CH2 on J205 DAC 2 OUT through SMA-to-BNC adapters, both 1 MOhm, DC: the open-circuit
numbers (±2 V).  The output stage is an OPA2810 at gain 4.4 from the two 24.9 ohm current-to-voltage nodes, 50 ohm source
termination, DC coupled, centred on 0 V; code 8192 is 0 V, 16383 is +2 V (+1 V into 50 ohm), 0 is -2 V.

5.1 `bench.py run stage5.dac_dc`: both DACs out of sleep, 25 MS/s, codes 8192, 16383, 0, 12288, 4096; the scope's mean
    of each channel against 0, +2, -2, +1, -1 V (±0.1 V: the OPA2810's offset and the 24.9 ohm's 1 % are tens of mV).
    Then the scope at 50 ohm for one code: half.  *Pass:* within ±0.1 V on both; the two channels within 20 mV of each
    other (one die, one reference).  A channel stuck at 0 V with the other right: its OPA2810's rails (+5VA, -4V2 at the
    chip) or its 24.9 ohms; both stuck: DAC_SLEEP (R5) high, or MODE (R8) low, or no WRT/CLK.

5.2 `bench.py run stage5.dac_sine`: 50 MS/s, a 1 MHz full-scale sine on both: 4.0 Vpp ±0.4 open circuit, 1.000 MHz
    (the NCO's frequency is exact to the TCXO), the scope's FFT with the fundamental and nothing within 50 dB (the
    scope's 8 bits limit this; the ADC loopback of stage 6 measures it properly).  Then 10 MHz: the amplitude within
    1 dB (the stage is -3 dB at 12.3 MHz; the full-scale slew limit is at 10 MHz).  Then `bench.py board dac 1 saw 100e3`,
    `dac 2 triangle 100e3`, `square`: the shapes.  *Pass:* amplitude, frequency, shapes.

5.3 **The DAC clock at the DAC** (the reviews' R2-11: DAC_CLK1 rides the +1V1 corridor on In4 for 49 mm with the nearest
    ground via 5-6 mm away): this one is a probe, held by Jason, on the DAC end of the 33 ohm in the DAC_CLK1 line (the
    0603 nearest U201's pin 18, CLK1), ground spring on U201's nearest ground; 50 MS/s, the scope at 1 ns/div on a
    single edge.  Expected: a 3.3 V edge with ringing under 10 % and no glitch.  Save the shot.  Ringing over 20 %: a
    stitching capacitor on the rev B list (`REVB.md`), and for now the lower rate (25 MS/s) which has the same edge.

5.4 **The LED driver**: JP2009 to the on-board LED; `bench.py board dac 1 dc 8192`: the DAC 1 IOUTA node at 0.24 V makes
    24 mA through D201 (10 ohm sense: I = VA1 / 10 ohm, 0 to 48 mA): the red LED lit; `dac 1 dc 0` off; `dac 1 dc 16383`
    bright (48 mA; the XL-2835SURC is rated 60).  A 1 kHz sine on DAC 1 (`dac 1 sine 1e3`) flickers it.  Back to code 0
    and JP2009 open after.  *Pass:* the LED follows the code.

## Stage 6: the ADCs (board A)

Each channel: SMA, 49.9 ohm termination by JP, 100 ohm 1206 in series, a BAV99 clamp to the rails, the SRC jumper, two
OPA1612 stages (x1 or x10 each by jumper), a 49.9 ohm into the U.FL tap, then the THS4521 fully differential driver at
gain 1 into the AD9238 through 33 ohm and 22 pF.  ±1 V at the SMA is full scale at x1; offset binary, 2048 is 0 V.  The
capture is 8192 samples of both channels at once, 25 MS/s (or 50 MS/s direct), read back over the serial channel in a
second; the running statistics (min, max, mean over 65536 samples) read in milliseconds.

6.1 `bench.py run stage6.adc_noise`, nothing on either SMA, TERM shunts in (50 ohm to ground), SRC = SMA, GAIN x1: the
    mean of each channel 2048 ±100 codes (the offset of the chain: the OPA1612s' tens of uV and the THS4521's mV are
    codes at 0.5 mV/code; log it, it is calibration), and the standard deviation **under 3 codes** (the AD9238's own
    is about 0.6 codes rms at 65 MS/s; the chain's 50 ohm-source noise at x1 is 1.1 nV/rtHz x sqrt(12 MHz) x 4 = 15 uV
    rms = 0.03 codes: the digital noise is what this measures).  A tone in the FFT of the capture: note its frequency
    (2 MHz is the pump, 1.5 MHz the +3V3 buck, 1 MHz the +1V1 buck, 25 MHz / 50 MHz the clocks).  *Pass:* std < 3 codes,
    no tone above 10 codes peak.

6.2 **The capture phase**: `bench.py board capture 1024` at phase 2 (the default), then `python3
    gateware/bringup/host/ecp5bu.py` from Python with `adc_config(phase=1)`, `phase=3`, `negedge=True`: on a clean
    50 kHz sine (6.3 below) a wrong phase shows as isolated samples far off the sine (bit errors at the transition);
    the phases that give a clean sine are the window; choose the middle.  At 50 MS/s (`adc_config(rate=50e6)`) the same.
    *Pass:* at least one clean phase at 25 MS/s; note the window.  Nothing clean: the clock to the ADC (E4 / R2 through
    its 33 ohm; the scope on the 33 ohm at the ADC's pin 63 CLK_A / pin 18 CLK_B) or the data lines.

6.3 `bench.py run stage6.adc_gen`: the SDG channel 1, 100 kHz sine, 1 Vpp into 50 ohm (the generator told load = 50),
    into J101 ADC A IN: a 100 kHz sine of **1024 codes peak-to-peak** ±5 % (±0.5 V of ±1 V full scale) centred on
    2048; channel B at its noise floor (the cross-talk, in dB: the ratio of B's component at 100 kHz to A's).  Then the
    same lead on J102 for channel B.  Then 1.8 Vpp (90 % of full scale), then 2.4 Vpp: the out-of-range flag (`otr` in the
    capture) counts the clipped samples, and the clamp holds the preamp input to the rails.  Then 1 MHz and 10 MHz at
    1 Vpp: the amplitude within 1 dB at 1 MHz; at 10 MHz the input filter's roll-off (log it).  *Pass:* 1024 ±50 codes
    on both channels, OTR on the overdrive, the amplitude flat to 1 MHz.

6.4 **The taps**: a pigtail from J107 TAP A to the scope at 1 MOhm with the 100 kHz 1 Vpp on the SMA: the preamp chain's
    output, 1 Vpp (x1) in phase with the input, DC coupled.  At 50 ohm, half.  The same on J108 for B.  *Pass:* 1 Vpp
    at 1 MOhm.

6.5 **Gain x10 and x100**: JP103 open (stage 1 of channel A at x10.1): 0.1 Vpp in reads 1024 codes ±5 %; both open
    (x102): 10 mVpp.  The noise floor at x100 with the SMA terminated: the chain's 1.1 nV/rtHz x 100 over 12 MHz is 0.4 mV
    rms = 0.8 codes rms above the floor; log it.  Back to x1.  *Pass:* the gains within 5 % of 10.1 and 102.

6.6 `bench.py run stage6.loopback`: an SMA lead from J204 DAC 1 OUT to J101 ADC A IN (TERM in: the DAC drives 50 ohm,
    ±1 V, exactly the ADC's full scale): a 1 MHz full-scale sine captured at 25 MS/s; 2048 codes peak-to-peak ±10 %,
    and the SFDR from the FFT of the capture (the DAC's images are above Nyquist of the capture; the harmonics of the
    two output stages and the ADC chain are what shows): **over 60 dB** is the chain working as designed (the AD9238's
    80 dB and the OPA2810's distortion say 70 is possible).  Then 100 kHz and 10 MHz.  Save the captures (`bringup/data`).
    *Pass:* amplitude and SFDR > 60 dB at 1 MHz.

6.7 **First light**: the optical path.  JP2009 to the on-board LED, JP1203 to PHOTODIODE, JP202 (channel B's SRC) to ALT:
    the photodiode receiver (U105, the transimpedance stage, TAP TIA on J109) feeds channel B.  `bench.py board dac 1
    dc 12288` (36 mA in D201): channel B's mean rises from the dark level; `dac 1 sine 1e3` with offset 8192 (a 1 kHz
    modulated LED): a 1 kHz sine on channel B's capture (decimate: `adc_config(decim=99)` gives 250 kS/s for 32 ms of
    record).  The photodiode sees the LED at 60 % of its peak sensitivity across the board; the TIA's gain is the
    sheet's.  Log the codes per mA.  Everything back after (JP2009 open, JP202 SMA).  *Pass:* the light is seen; the
    ratio logged.

6.8 **The noise source**: JP102 (A's SRC) to ALT, JP1203 unchanged (B's ALT is the photodiode; the noise reaches B
    through JP1203's NOISE position: do B later), SW101 switch 4 on (10 k: 12.9 nV/rtHz), gain x100 on A: the capture's
    std against the 0 ohm switch (switch 1 on: the amplifiers alone); the difference squared is 4kTR x B.  A one-line
    Johnson-noise check of the whole chain.  *Pass:* 10 k measurably noisier than 0 ohm at x100.

## Stage 7: the memory, the Ethernet PHY, the rest (board A)

7.1 `bench.py run stage7.sdram`: the read-latency scan on 4096 words (latencies 1-7: in simulation 3 passes and its
    neighbours fail in every word; on the board the clock's and the command's trips to the chip decide, so 3 or 4), then
    the whole 32 MB (16 M words) written and read back with three patterns at the latency that passed: **0 errors**,
    about 5 s each (retention over the write phase proves the refresh).  Both SDRAM clock polarities (`pol`) if the
    scan's window is one wide.  *Pass:* a latency with 0 errors over the whole array, all patterns.  Errors in one
    data bit at every address: that DQ line; in one bank: its BA; everywhere: the clock or the latency.

7.2 `bench.py run stage7.phy`: the PHY's ID over MDIO (bit-banged: a second): **0x001C, 0xC916** at address 1 (PHYAD0
    strapped high); then an Ethernet cable from J401 to the switch: the RJ45's link LED, the PHY's status register says
    link up and the negotiated speed, and RXC counts **125,000,000** (gigabit) on `bench.py board clocks`.  *Pass:* the
    ID, the link, 125 MHz.  Traffic through the RGMII (ping) is LiteX's liteeth job, after the bring-up.

7.3 **The Pmods**: `bench.py board` with `pmod(mode_a=2, mode_b=2)` (from Python: counters on every pin, 12.5 MHz
    down to 98 kHz): the scope on each of the 16 pins (a probe, Jason, or a Pmod breakout).  `pmod(mode_a=1, a=0x55)`:
    static levels.  *Pass:* every pin toggles.

7.4 **Buttons, RGB, user LEDs, the FTDI's modem lines**: covered by stage 3; `bench.py board ident` shows RTS/DTR as the
    PC sets them (`python3 -c` with pyserial `setRTS`): a reset line for the LiteX design later.

7.5 **Not this day** (they need gateware that does not exist yet, and nothing on the board for them can be hurt by
    waiting): USB USER (J502: a soft USB device; D+/D- at G14/G13, the pull-up at H13), HDMI (J503), microSD (J504).
    The ECP5 LiteX platform file is generated (`gateware/litex/ecp5_2adc_2dac.py`); a VexRiscv SoC with liteeth and
    litesdcard is the next gateware.

## Stage 8: the reviews' open questions, and what goes on the rev B list

| from | what to measure | where | done in |
|---|---|---|---|
| R8 (round 1) | +3V3 against +1V1 at power-on: the Master-SPI sequencing rule | J602 pins 3 and 5 | 1.5 |
| R2-12 | DVDD33's rise (Realtek wants slower than 0.5 ms) and REG_OUT (+1V0_PHY) clean | J602 pins 3 and 15; the ripple on 15 | 1.5 |
| R2-11 | DAC_CLK1 at the DAC end: ringing from the In4 corridor | the 33 ohm by U201 pin 18 (a held probe) | 5.3 |
| round 2 (both) | the ADC's LDO U604 temperature at 65 MS/s (0.26 W after the 2.2 ohm) | the IR camera, the ADC clocked at 50 MS/s | 1.4 again after 6 |
| round 2 (CopilotSDK) | +5V's ring on a hot plug toward 5.8 V with 94 uF behind the fuse | the scope on J602 pin 1, single trigger, while the USB-C is plugged with J601 off | after 2.3 |
| R10 | the ADC's SFDR at 1 and 10 MHz (the input trace asymmetry) | the loopback and the generator | 6.3, 6.6 |
| Response 26 | the taps' loading: the OPA1612 driving 100 ohm | TAP A at 50 ohm with a full-scale input: no distortion | 6.4 |
| build 31 | the ADC's analog LDO's dissipation | as above | 1.4 |

Everything that fails a pass condition, every number outside its window, every "works but" goes to `bringup/REVB.md` with
the reading that showed it, the day it is seen.

## The dead-on-arrival list against the stages

| risk | what would show | retired by |
|---|---|---|
| a reversed SS34 or P-FET, a short under the BGA or a 0402 bridge | current limit at 1-2.5 V | 1.2 |
| a buck not starting (L617/L618, the feedback divider), an LDO dead | a rail out of its window, its LED dark | 1.3 |
| the -4.15 V pump dead or at the wrong voltage (the 1.3 M mistake of build 24 is fixed, but) | -4V2 out of window, the op amps at 0 V | 1.3, 5.1 |
| the BGA not soldered, or the configuration pins (CFG, PROGRAMN, DONE, INITN) wrong | no IDCODE | 2.2 |
| the FT2232H dead, its crystal Y501 not oscillating, the USB-C's CC resistors | no 0403:6010 | 2.1 |
| the TCXO dead (its two grounds, found on the first sheet) | no chaser, no serial | 3.1 |
| the flash not booting (CFG = 010, the flash's pins on sysCONFIG) | no chaser after a power cycle without the PC | 3.3 |
| the PLL (VCCAUX = +2V5 from U603) | the RGB LED red, `pll_lock` false | 3.2 |
| the Si5351 (its crystal Y301, the I2C pull-ups) | no ACK at 0x60, or outputs that do not count | 4.2 |
| the CLK IN comparator (its bias at mid-rail, the 1 k) | CLK IN counts nothing or the wrong frequency | 4.3 |
| the DAC (MODE, SLEEP, the FSADJ 2 k, REFIO) | both outputs stuck at 0 V | 5.1 |
| an output stage (the swapped FDA outputs of the first rev A were found by trace_paths; the DAC port 2 reversal too) | one DAC at the wrong polarity or amplitude | 5.1 |
| the ADC's clock or data lines, the capture phase | a noisy or scrambled capture | 6.1, 6.2 |
| the ADC front end (a preamp, the FDA, a clamp diode conducting) | the wrong amplitude or offset on one channel | 6.3, 6.4 |
| the SDRAM (the address and data rivers, the clock) | errors in the scan at every latency | 7.1 |
| the PHY (its straps, its 1.0 V switcher's inductor L401, the magnetics) | no ID over MDIO; no link | 7.2 |
| the HDMI, USB USER, microSD | not tested | later gateware |

## After the bring-up

The LiteX SoC (`gateware/litex/ecp5_2adc_2dac.py`): VexRiscv, the SDRAM through litedram, liteeth over the RGMII with
both delays inside the PHY, the serial console on channel B; then the capture-to-SDRAM-and-send-over-Ethernet path that
is what the board is for; then the lock-in and correlation gateware of the optics experiments.  The bring-up design stays
as the diagnostic bitstream in the flash's second slot, or the first thing loaded when something stops working.
