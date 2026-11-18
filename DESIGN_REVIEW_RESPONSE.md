# Design review response -- the author's own pass, 2026-10-04

*Written while the review was done, in the order the work happened; the findings table is the summary.  The
prompt this answers is `DESIGN_REVIEW_PROMPT.md`.  Other reviewers' reports go in `design_review_<model>/`.*

## Verdict, in one paragraph

**Order one assembled board after the end plates are checked against the extrusion** -- not five.  Nothing
found is a "start over": the architecture (an ECP5 with the converters on the west banks, the generated CAD,
the six-layer stackup, the isolation island) stands.  What the review found was of the other kind, the kind
that ships a dead or unusable board while every check passes: the release had no orderable part number for
the two converters, the six op amps, the HDMI jack and the microSD socket (they had silently become
"hand-solder"); the board was 8 mm too short and 1 mm too narrow for the enclosure it was drawn for, so the
SMAs would not have reached their end plate; the monitor's 5 V hot-plug-detect reached a 3.3 V FPGA pin
through 470 Ω; the board would have stood its magnetics on the enclosure floor in the lowest slot; the Ethernet PHY's
1.0 V switcher ran through an 0805 chip inductor rated 50 mA; and seven of the BOM's LCSC codes (eight entries of
the parts table) were the wrong part -- the DAC's 24.9 Ω loads were a 470 kΩ, the PHY's 2.49 kΩ bias resistor a 270 kΩ, the -4.4 V pump's 1.3 MΩ a
27 kΩ (a -1.3 V rail), the USB port's 27 Ω a 240 Ω, the 2.2 pF feedback capacitors a 1206 resistor.  All six
are fixed in builds 21-25 and the checks that would have caught them now run in every build; the five reviews of
build 25 are reconciled in §5 and built as builds 26-27.  Build 27 is the repository: DRC 0 errors and 0 unconnected at
every severity, 412 of 412 router nets, 438 SMT placements on 85 BOM lines, 158 x 119 mm.  The things
that cannot be checked from here are listed in §4 for Jason.

## 1. Findings, ranked

"Confirmed by" says what was checked so that a finding is not just an opinion.

| # | Sev | Finding | Confirmed by | Disposition |
|---|-----|---------|--------------|-------------|
| 1 | **Blocker** | Eleven SMT parts had no LCSC code -- AD9238, AD9767, 2x OPA1612, 3x OPA2810, 2x THS4521, the mini-HDMI jack, the microSD socket -- so JLCPCB would not have fitted them; they were in `hand_solder_bom.csv` with an empty code column and no check failed | `build/lcsc.json` (None for U103 U201 U101 U102 U105 U111 U112 U202 U203 J503 J504); the sheets name parts "AD9238", the LCSC table is keyed "AD9238BSTZ-65" | **FIXED (build 21)**: `parts.ALIASES`; `make_fab.py` raises on any codeless SMD part not in HAND; the hand-solder list now carries codes for the SMAs, RJ45 and DIP switch.  Release: 421 placements on 85 lines (was 408 on 77) |
| 2 | **Blocker** (mechanical) | Board 150 x 118 mm in a Hammond 1455Q1601 made for a 120 mm wide board up to 159 mm long: 9 mm between the SMAs and their end plate (barrels reach 7 mm past the edge), 2.5 mm of side play in the slots | `datasheets/Hammond_1455Q1601.pdf` ("extrusion designed for 120 mm wide PC board", slot-to-slot 120.48 +-0.89); the SMA drawing `BWSMA-KWE-Z001_C496551.pdf` p.6 | **FIXED (build 22)**: 158 x 119 mm, the east cluster shifted by `floorplan.E` = 8 mm, `place.py` the one source of the size; `mfg/end_panels.py` draws both plates |
| 3 | High | The two USB-C receptacles were classed through-hole (four shell pegs) and sent to the hand-solder list; JLCPCB places this part on the Icepi Zero | `fplib.smd` was "all pads SMD" | **FIXED (build 21)**: the footprint's own `(attr smd)` decides the assembly class; a new `th_any` flag keeps parts with holes on both sides for placement and silkscreen |
| 4 | High (mechanical) | In the extrusion's lowest slot the board's underside is ~4.4 mm above the floor; the G2406S magnetics on the back are 4.0 +-0.4 mm tall | G2406S drawing p.1; the Hammond section (slots 2 mm apart, lowest ~5 mm up) | `end_panels.py` defaults to the second slot (board top 8 mm above the floor) and says so; **Jason: measure the extrusion** |
| 4b | **High** | The PHY's 1.0 V switcher inductor L401 was an 0805 multilayer chip inductor (CMI201209U2R2KT) rated 50 mA, 0.6 Ω; Realtek requires a power inductor that withstands 600 mA with ESR under 0.8 Ω and warns a lesser one may damage the regulator.  At gigabit the core draws ~300 mA: a sagging 1.0 V rail, a flaky or dead PHY | The inductor's datasheet table; RTL8211F datasheet Table 50 notes 2 and 4 | **FIXED (build 24)**: the bucks' SWPA4030S2R2NT (2.2 µH, 2.95 A, 40 mΩ) on the back under the RGMII resistor columns, its 10 µF + 100 nF at the output pad, the +3V3_ETH 10 µF moved beside DVDD33, the switch node in the Rail class (0.4 mm).  LEFT: Realtek's layout rules also ask for the inductor on the PHY's own layer with no via on REG_OUT and a 60-mil trace; the west side of this PHY is the RGMII river and the strap staircase, there is no front-side room, and a 0.45 mm via on a 1 MHz switch node carrying 0.3 A is not the hazard the rule guards against (the rule is written for 1 A boards).  If the first board's 1.0 V rail (the RAILS header has no pin for it: probe C4991) rings or the PHY runs hot, this is where to look.  Note: the C1043 chip inductor came from this author's JLCPCB rebuild of the Icepi Zero (`IcepiZeroADCDAC/jlcbuild/parts.py`), which put it on that board's two bucks and PHY as well; whether those boards' rails held is worth knowing |
| 4c | **Blocker** | Eight LCSC codes in `gen/parts.py` named the wrong part.  "2.2pF" was C1512, a 1206 180 kΩ resistor (C1401 C2401 C2501: the TIA's and both DAC difference amplifiers' feedback capacitors -- a part that does not fit the 0402 pads at all); "24.9R" was C23178, 470 kΩ (R2401 R2402 R2501 R2502: the DAC's four IOUT loads, so 20 mA into 470 kΩ -- both DAC channels pinned at the AD9767's compliance limit); "2.49k" was C22965, 270 kΩ (R4983, the RTL8211F's RSET bias: wrong line-driver currents, probably no link); "1.3M" and "499k" were C22967 / C23200, 27 kΩ / 536 kΩ (R8301 R8302, the LM27761's divider: -1.22 x (1 + 27/536) = **-1.28 V instead of -4.4 V**, so every OPA1612 and the TIA would have lost its negative rail); "27R" was C23350, 240 Ω (R6311 R6321, the FPGA USB port's series resistors: no high-speed eye); "75R" was C23188, 5.62 kΩ (R4951-54, the Bob Smith terminations: EMI only); "47R" was the 47 kΩ's code (unused on this board).  The table was typed from memory of another project's table; the schematic, the netlist, DRC, the stock check and the rotation check all passed, because none of them asks what the code IS | `mfg/footprint_check.py` (the Icepi build's land-pattern check, adapted): "C1512 ... R1206 ... LAND worst pad-centre miss 0.998 mm"; then every code's JLCPCB description read back against its value (seven resistor lines "<-- CHECK") | **FIXED (build 25)**: C1559 (0402CG2R2C500NT), C22916 (24.9 Ω), C22908 (2.49 kΩ), C13316 (1.3 MΩ, 236 in stock), C26751 (499 kΩ), C25190 (27 Ω), C4275 (75 Ω), C23182 (47 Ω).  Two checks now gate the release: `make_fab.code_value_check` fails the build if any ordered code's JLCPCB description does not carry the schematic's value and package (self-tested on build 24's table: it flags exactly the six wrong resistor codes still in use -- the capacitor's had already been corrected -- and nothing in build 25), and `mfg/footprint_check.py` compares EasyEDA's land pattern for every ordered code with the footprint on the board ("every ordered part fits"; the ten "land" notes are 0.16-0.40 mm pad-centre differences between KiCad's and LCSC's drawings of the same package) |
| 5 | Medium | HPD: the sink pulls it to +5 V; 470 Ω series + 10 kΩ down put ~4.4 V on a 3.3 V FPGA pin (abs max 3.63 V).  Copied from the Icepi Zero, which works, through the pin's clamp | ECP5 datasheet Table 3.1; Icepi `gpdi.kicad_sch` R12/R13 | **FIXED (build 21)**: 4.7 kΩ series: 3.2 V at the pin with a 1 kΩ sink pull-up, 3.4 V worst case |
| 6 | Medium | 5 V budget ~0.6-0.7 A: more than a USB 2.0 port's 0.5 A | Power sheet note (3 W); AD9238 IAVDD 110 mA typ, AD9767 71 mA, PHY 0.4 W, FPGA 0.6 W | Silkscreen legend and README say: a USB-C / USB 3 port or the 5 V IN header |
| 7 | Low | `_pin1_marks`: the LCSC land patterns print their own pin-1 marks (the magnetics a dot, the 2835 LED a cathode triangle, the photodiode the diode symbol) except the RGB LED, which prints two bare lines | The footprints' silkscreen graphics, listed | **FIXED (build 22)**: a dot beside pad 1 of D309; the pass is general |
| 8 | Low | The FT2232H's 12 MHz crystal is a 20 pF part on 27 pF loads (16-18 pF effective): about +30 ppm | Crystal X322512MSB4SI (20 pF); FTDI's reference uses 27 pF with 18 pF crystals | Left: inside USB's +-500 ppm and FTDI's +-50 ppm with the crystal's +-10; 33 pF would be exact |
| 9 | Low | `gateware/ecp5_2adc_2dac.lpf` locates CFG0-2, DONE and INITN as user I/O | The file | Left: nextpnr accepts them unused (the pin proof passes); harmless, untidy |
| 10 | Low | The eight user LEDs run at ~0.5 mA (1 kΩ from 3.3 V, white) | Arithmetic | Left: dim by design; 470 Ω if brighter is wanted |
| 11 | Info | The AD9238 has 21 in JLCPCB stock ($71); the only thin line | `cost_estimate.csv` | Order soon or consign from Digi-Key |

### Looked for and not found

Pin numbering of every IC against its datasheet (list in §2); a strap with the wrong default (the PHY's
seven straps against Table 6, each with its internal pull); the ECP5 Master-SPI power-up requirement (VCCIO8
before VCC or VCCAUX: VCCAUX is an LDO off the 3.3 V, so it always follows); CFG[2:0] = 010 = Master SPI
(the ECP5 Versa board's table); the flash on the sysCONFIG balls (N8 CS, N9 CCLK, T8/T7/M7/N7 D0-D3, the
Icepi Zero's); JTAG pull-ups and the TCK pull-down; the FT2232H's channel A/B pin numbers and the EEPROM's
SOT-23 pinout (the GPSDO board's SOIC-numbered-SOT-23 mistake is not repeated); the 2835 LED's and the RGB
LED's polarity on LCSC's land patterns; the SMA's drawing against KiCad's footprint; the DIP switch's pole
pairing (1-8, 2-7, 3-6, 4-5); the diode directions (BAV99 to the rails, B5819W from the bench header, 1N4148W
into D+); the LiteX platform file against the pin plan (clocks, serial, SD, Ethernet, HDMI pairs); the
THS4521's input bias (0.825 + Vin/4: 0.58-1.08 V inside -0.1..2.2 V, and 80 mV past the limit through
499 Ω at an x10 overload, harmless); the OPA2810's load (20 mA of 75); the AD9767's compliance (0-0.48 V of
-1.0..+1.25); the LDOs' dissipation (0.19 W typ, 0.34 W worst in a SOT-23-5); the LAN island's moat on the
finished copper (1.9 mm at the 2 kV capacitor's hot pad, more than 3 mm everywhere else, no plane on any
layer under the line side, 0 violations of the 1.5 mm rule); the four SPICE decks re-run (`python3 sim/run.py`):
the ADC chain puts 2 Vpp differential on the converter for ±1 V at a terminated SMA and holds the clamp node
within -4.95..+4.99 V for ±10 V in, the DAC stage gives ±1.82 V open circuit (0.91 V into 50 Ω) with -3 dB at
13.5 MHz, the TIA 6.8 MHz with 3.5 dB of peaking, the LED driver 48 mA at the top code.  After finding 4c, every
passive's rating was read from JLCPCB's description of its code: the 100 nF are 16 V X7R, the 1 µF 25 V, the 10 µF
25 V X5R, the 22 µF 25 V, every pF value C0G, the Bob Smith capacitor 1 nF 2 kV, the ferrites 1.3 A, the fuses a
2 A hold on the 5 V input and 0.5 A on the HDMI jack's 5 V pin, the Schottky 1 A 40 V; nothing under-rated.

## 2. What was read, and how

* Every datasheet in `datasheets/` was extracted to text (`pdftotext`) and the pin tables grepped; the four
  drawings that are images (the Fox TCXO, the Xinglight LEDs, the BAT Wireless SMA, the CND-tek magnetics,
  the Hammond extrusion) were rendered and read.
* The six sheet generators and the pin plan were read end to end against those tables.
* `build/lcsc.json`, the release's BOM, CPL and hand-solder list were read, which is where finding 1 came from.
* Every LCSC code in the BOM was looked up twice: its land pattern from EasyEDA against the footprint on the board
  (`mfg/footprint_check.py`), and its JLCPCB description against the value on the schematic (`make_fab.code_value_check`).
  Finding 4c came from the first (a capacitor code that drew a 1206 resistor) and the second found the other seven.
* The placed and routed boards of builds 20-22 were queried with the scratch tools in `build/scratch/p11`
  (`near.py`, `zones.py`, `moat.py`) and the placement debugged with `build/scratch/p11/silkdbg.py`.
* The Icepi Zero's schematic (the course's previous board, built and working) was used as the reference for
  the HDMI, USB and configuration circuits copied from it.

## 3. The three earlier reviews this one learned from

`GPSDO-PYNQ-Z2/DESIGN_REVIEW_RESPONSE.md` (the release that had no ground planes, the board with no mounting
holes, DRC at default severities, a pin-1 mark that existed only on F.Fab), the Syzygy radio board's review
and its rebuttal (datasheet voltages misread, eval-board schematics trusted over an LLM's claim, a 0201
carrying 110 mW), and `ai_unleashes_chaos/docs/DESIGN_REVIEW.md` (part rotation in assembly as the most
common first-article failure; a footprint drawn from a vendor drawing as the biggest risk; the checks that
report success while checking nothing).  Each of those classes was looked for here: the pours are in the
board file (the DRC runs with `--refill-zones --save-board`); the mounting holes are in the drill file; the
DRC rules are the project's own with silkscreen and courtyard checks as errors; the marks are printed;
the land patterns are LCSC's own for every part JLCPCB fits -- and, after finding 4c, the part behind every code is
read back from JLCPCB's own description, because the Icepi rebuild's tactile switch (a code whose part had two
locating posts the board had no holes for) and this board's "2.2 pF" that was a 1206 resistor are the same
failure: a code is a name, and nothing else in the pipeline ever looked at what it names.

## 4. What cannot be checked from here -- for Jason

- [ ] Measure the extrusion: which of its four slot positions the board rides in (Hammond: the 1455 series
      takes 1.6 mm boards in four alternative vertical positions; the drawing's "1.50 mm TYP" is the rib).
      Set `PCB_TOP_ABOVE_FLOOR` in `mfg/end_panels.py` and re-run it before milling the plates.
- [ ] Upload the CPL and read JLCPCB's placement preview for the packages `FABRICATION_NOTES.txt` lists as
      unchecked: the BGA, the two LQFP-64s and the LQFP-48, the QFN-40, the MSOP-10, the DFN-8, the
      SOD-123s, the LEDs, the SOT-23s and SOT-23-6s, the magnetics, the photodiode, the TCXO.  The polarised
      ones are the ones that matter.
- [ ] Order one board, assembled, and bring it up in this order: 5 V IN from a bench supply at 0.8 A limit
      with nothing plugged in (rail LEDs D601-D609: all nine on; RAILS header: +5V, +3V3, +1V1, +2V5, 3V3A, 3V3D,
      +5VA, 1V0, -4V2), then USB PROG (the FT2232H enumerates with a blank EEPROM), then `openFPGALoader -c ft2232` a
      blinker, then the flash, then Ethernet with `ping`, then the SMAs.

## 5. The five reviews reconciled, and builds 26-27 (2026-10-04, from 10:53)

Four outside reviews of build 25 (`design_review_CopilotSDK/`, `design_review_Gemini_3.8_Flash/`,
`design_review_Grok4.7/`, `design_review_Claude-ultrareview/`) and this one.  Every finding, what it costs to be
wrong, and what build 26 does about it.  "Fix" = changed in the generators and rebuilt; "label" = the
documents, sheet notes and silkscreen now say what the circuit does; "defer" = left for the first board, with
the measurement that decides.  Jason's own addition: U.FL monitor taps, so the first board's questions are
answered by plugging a pigtail into a scope, not by holding a probe.

| # | Finding (who) | Disposition in build 26 |
|---|---|---|
| R1 | THS4521 overdrive: when a preamp saturates to -4.2 V, Gemini computes 2.27 V across the FDA's inputs (abs max 1 V); Grok says the loop keeps it under 1 V.  Both assume something about an amplifier driven outside its input range | **Fix, by construction**: a BAV99 wired anti-parallel across each FDA's two inputs (pin 3 to IN+, pins 1 and 2 to IN-).  Whatever the amplifier does, the differential input cannot exceed one diode drop (0.8-0.9 V at the 7-10 mA the 499 Ω networks allow).  In normal operation the inputs sit within millivolts of each other, so the diodes carry nanoamps and add 1.5 pF across a virtual short.  A Schottky pair was considered and rejected: at 20 MHz the FDA's loop gain is ~6, the differential error ~0.17 V peak, and a Schottky would already conduct tens of µA there |
| R2 | A ±10 V source into the high-Z input burns the 100 Ω 0603 (Grok) | **Fix**: 100 Ω 1206 (0.25 W; 43 mA, 0.18 W at ±10 V); the sheet says ±10 V max instead of ±8 |
| R3 | -4.4 V rail: the LM27761's 2 MHz ripple is common to both noise channels, no ferrite (Grok, Gemini); the LDO is in dropout from a 4.5-4.75 V USB supply (Grok) | **Fix**: a ferrite bead and 10 µF between the pump and the op amps (the rail is now `-4V2`, after the bead; the divider still senses the pump's own output), and the divider's 1.3 MΩ becomes 1.2 MΩ: -1.22 x (1.2M + 499k) / 499k = **-4.15 V**, 0.45 V of LDO headroom from a 4.75 V input.  Every op amp still has 9.2 V across it (minimum 4.5) and 2.3 V of headroom below the DAC stage's -1.8 V swing.  A U.FL tap on the rail |
| R4 | Bob Smith capacitor C4951 is a general-purpose 2 kV 1206 MLCC, 1.4 mm pad gap, 1.9 mm to the plane: not evidence of 1500 Vrms (CopilotSDK, Gemini, Grok) | **Fix + label**: a 1 nF **3 kV** X7R in **1812** (C692296: 4.5 x 3.2 mm, ~2.3 mm between its own terminals, the plane edge further from its hot pad); the sheet, README and prompt now say the magnetics are the isolation per IEEE 802.3, the capacitor is the designed bridge, and the board has not been hipot-tested.  No 1500 V claim remains |
| R5 | RGMII TX delay: TXDLY = 0 expects the gateware to shift TXC by 2 ns; the shipped platform is a pin proof, so the first gateware to run would not link at 1 Gb/s (all four) | **Fix**: RXD1 pulled up with 4.7 kΩ to DVDD_RG (+3V3_ETH): TXDLY = 1 as well as RXDLY = 1 -- both 2 ns delays inside the PHY, the "rgmii-id" convention, and the gateware adds none (LiteEth `tx_delay = rx_delay = 0`; note in `gateware/litex/ecp5_2adc_2dac.py`).  Copper skew (TX 2.6 mm, RX 7-10 mm: Grok; 23 mm clock-to-farthest-data: CopilotSDK/Gemini) is 20-150 ps against a 2 ns shift: not the risk |
| R6 | DAC stage: ±0.913 V into 50 Ω and ±1.825 V open circuit, not the ±1 / ±2 V on the sheet and silkscreen (Grok, Gemini); 149 of 180 V/µs of slew at 13 MHz full scale (CopilotSDK, Gemini); no capacitor across the 2 kΩ on the non-inverting input, so the HF common-mode balance is lost (Gemini) | **Fix + label**: 2.2 pF across the 2 kΩ to ground (the AC balance); the sheet, silkscreen and README say ±0.9 V into 50 Ω, ±1.8 V unloaded, full-scale sine to 10 MHz, -3 dB at 13.5 MHz.  The resistors stay: 0.91 V is a fine teaching full scale once the label is honest, and a bigger swing would eat the slew margin |
| R7 | CLK IN: an unbuffered inverter biased at its own threshold, which moves with the digital 3.3 V rail: 250 ps to nanoseconds of edge movement on a 10 MHz sine (all three) | **Fix**: a TLV3501 comparator (4.5 ns, 6 mV internal hysteresis, rail-to-rail inputs; C193413) on the ADC's low-noise 3.3 V rail: 50 Ω / TERM jumper as before, 10 nF coupling into IN+, IN+ biased through 10 kΩ from a 10k/10k mid-rail divider that also feeds IN- (100 nF on that node), SHDN grounded, 33 Ω into the FPGA.  The Schmitt buffer and the 1 MΩ go.  Square waves to 80 MHz (the comparator's toggle rate); a 10 MHz sine of 0.3 V peak or more |
| R8 | Power sheet says "the ECP5 has no order requirement"; the datasheet's Master-SPI rule is VCCIO8 above the flash's VIH before the FIRST of VCC and VCCAUX reaches VPORUP (Grok, Gemini); CopilotSDK and Grok agree the tree as built almost certainly meets it | **Fix + label**: 100 nF from PROGRAMN to ground (with its 4.7 kΩ: configuration cannot start until ~0.5 ms after the 3.3 V rail, which is VCCIO8 and the flash's supply, is up); the note now states the rule and why the tree meets it.  Scope +3V3 against +1V1 on the first board |
| R9 | USB-C receptacles recessed 0.32 mm inside the board edge, the mini-HDMI 0.18 mm; behind a 1.45 mm end plate a USB-C plug's shroud cannot reach (Gemini) | **Fix**: the two USB-C jacks and the HDMI jack moved east so their faces stand **2.5 mm** past the board edge.  Hammond's plates are 1.45 mm thick and the board floats up to 2 mm between them (160 mm extrusion, 158 mm board, the SMA nuts do not locate it), so the faces land between 1 mm inside and 1 mm outside the plate's outer surface: 5.5 mm or more of a USB-C plug's 6.5 mm shroud enters in the worst case.  The RJ45's and Pmods' cutouts are the whole jack body, so their recess does not matter.  `end_panels.py` follows the placement |
| R10 | ADC input traces: VIN+/VIN- mismatched by 9-10 mm with the 22 pF caps 10 mm from the pins (Gemini) | **Defer**: a 10 mm mismatch is 60 ps against a 7.7 ns aperture, and ~10 nH is 1.3 Ω at 20 MHz, below the 33 Ω series resistor's tolerance; the kickback pole (33 Ω + 22 pF) is at 219 MHz.  The first board's SFDR at 1 and 10 MHz, x1, decides; the fix would be the capacitors on the back under the pins |
| R11 | DAC_CLK1 / DAC_WRT1 on In3 cross the In4 +1V1 patch boundary (Gemini) | **Defer with reasoning**: In3's nearer reference is the In1 ground plane through In2 as much as In4; the +1V1 patch is 4 x 4 mm under the core balls with the FPGA's decoupling capacitors on its edge, which is the return path the crossing uses; the clock is 33 Ω-damped and 65-125 MHz.  Watch the DAC's spurs on the first board |
| R12 | USB-C power is not negotiated; a 2 A PTC is not a current limiter (CopilotSDK) | **Label**: the legend and README already say a USB-C or USB 3 port or the 5 V IN header; the README now says why (0.7 A before any enumeration) |
| R13 | RGMII RXC on bank 1 while the data is on bank 2 (Gemini) | **No change**: E8 is a primary clock input; the clock goes to the global network and reaches bank 2's IDDRs like any PCLK; LiteEth's ECP5 PHY handles the input delay (DELAYG).  Gateware, not board |
| R14 | Narrow SOIC-8 has no CPL rotation entry (Gemini) | **Parked by Jason** for the day of ordering, with the rest of the placement-preview reading |
| R15 | The FPGA USB port cannot be a host (Gemini) | **No change**: it is a device port by design; the README says so |
| R16 | A clone cannot build (pinout CSV ignored); SMA feeds routed at 0.15 mm; four nits (Claude ultrareview) | **Fixed** in commit dd8a89d: the CSV is tracked, `width_of` serves both routing passes and the build fails if an RF net is not 0.35 mm, the nits cleaned |
| R17 | Debugging without soldering or holding a probe (Jason) | **Add**: four U.FL (Hirose U.FL-R-SMT-1, C88374) monitor taps, each through 49.9 Ω so a 50 Ω scope input sees half the signal and a 1 MΩ input (ADALM2000) sees all of it: ADC A and B after the second preamp (before the FDA), the photodiode receiver's output, and the -4.2 V rail.  `+1V0_PHY` and `+1V8_FTDI` join the RAILS header (now 2 x 10).  A pigtail into the Siglent scope controlled from `util_bench_instruments/` closes R1, R3, R7 and R10 |

Builds: 26 is all of the above.  The log of the work follows.

### Build 26 log

* 10:53-13:00: everything in the table implemented in `gen/` (sheets: ADC, DAC, FPGA, power, Ethernet),
  `pcb/floorplan.py` (every new part placed by hand), `pcb/build_pcb.py` (silkscreen strings, the tap names,
  the rails header's ninth name), `mfg/end_panels.py` (cutouts), `sim/` (the decks follow the circuit), the
  parts table (TLV3501AIDBVR C193413, U.FL-R-SMT-1(80) C88374, 1 nF 3 kV 1812 C692296, 100 R 1206 C17901,
  1.2 M C22766) and `library/ours.pretty` (the U.FL land pattern from EasyEDA with both ground pads numbered 2,
  its 3D model in `ours.3dshapes`).  Two generated symbols were added for the schematic: a BAV99 drawn as the
  anti-parallel pair it is wired as (gen.py's checker rejects a two-unit symbol sharing pin 3), and a
  comparator triangle with its supply box.
* The schematic side: ERC 0 after three rounds (a power flag for the rail behind the bead; the rails header's
  negative flag hung into the next row, so the negative rail is last; explicit designators for the new parts
  so the strips' R1..R12 and the DAC's C1 keep their numbers, which the floorplan indexes).
* The placement took twelve passes of `build_pcb.py --place` + DRC: the 1206 needed the clamp and the
  termination jumper moved; the taps had to find room in strips that were full (A's above its strip, B's in
  the notch below the SRC jumper, the TIA's in the box's bottom row, the rail's at the power section's east
  end); the rails header grew a column, so the LED row, the 1.1 V-good transistor and the bench header moved
  east; the 1812 pushed the Bob Smith row 0.8 mm east.  Two silkscreen lessons: a U.FL's outline reaches
  2.35 mm above its anchor, past its courtyard; and a box name that is short enough for a notch's corner
  piece takes it and evicts the noise resistors' values, so the name stays long.
* A DRC that lied: `silk_overlap` named J603 against lines 100 mm away.  The board writer had copied the
  library footprint's primitive uuids into every instance (142 duplicates), and KiCad attributed J109's and
  J107's real overlaps to J603.  `pcb/board.py` now gives every primitive a per-instance uuid; both real
  overlaps were fixed.
* Simulations re-run: ADC chain -6.03 dB from the source (the 50 Ω divider) and 23.1 MHz, unchanged by the
  diodes; DAC 1.825 V unloaded / 0.913 V into 50 Ω and 13.4 MHz with the balance capacitor; TIA 6.8 MHz,
  3.5 dB of peaking; LED driver 48 mA.  Gemini's overload deck (`design_review_Gemini_3.8_Flash/test_ovld.cir`),
  re-run at -4.15 V with and without the BAV99 across the inputs: at ±5 V in the loop holds |IN+ - IN-| at
  0.45 V and the diodes carry nothing -- the 2.27 V in their report is not what their own deck computes; the
  diodes are insurance for the real part outside its common-mode range, which no behavioural model shows.
* The right-edge connectors: 2.5 mm of protrusion was the plan; the USB-C shells' rear through-hole pads and the
  mini-HDMI's legs limit it to 1.9 and 0.75 mm at 0.35 mm from the edge, so the end plates' cutouts take the
  plugs' overmoulds instead (12.8 x 6.8 and 14 x 8 mm).
* 12:38: the full build 26 started; 13:04 it routed 411 of 412 nets and stopped on the new RF-width gate.
  Three things: (1) the gate counted the router's 0.127 mm pad-entry necks as violations -- it now ignores
  segments under 1.5 mm; (2) the TXDLY pull-up on the back under RXD1's series resistor sat on the RGMII river's
  layer-change via (a short: `shorting_items`) -- it is east of the column now; (3) the flash's CS and WP pull-ups'
  3.3 V pads at x 73.3 lay over the 1.1 V corridor's east part with no room for an edge via between them and the
  flash, and the router could not reach them (build 25 had joined the two pads and found a way; build 26's
  retry burnt 1.2 M pops and gave up) -- the corridor's east edge is 72.6 mm now, so both pads are over the 3.3 V
  plane with their own vias.  Build 26 restarted 13:15.

### Build 27 log (13:40 -)

* Build 26 came back clean (DRC 0 errors, 0 unconnected, 412 of 412 nets, the release built, every ordered part
  on a land pattern that fits it), so the last pass was the one a reviewer cannot do from the files: the
  finished silkscreen and the sheets as pictures, every changed area cropped at 200 dpi.  It found the kind of
  thing DRC does not: "TAP B" printed inside the DAC 2 OUT box 6 mm from its jack (the ADC B strip's notch left
  no free cell beside J108, and the placer's fallback is "anywhere"), "TAP -4V2" 6 mm below its jack, and on the
  sheets a dozen labels on top of something -- the CLK IN note over the mid-rail divider's ground symbols, the
  comparator's power-unit designator on its capacitor's ground, the RAILS header's designator inside its body,
  the Bob Smith and PROGRAMN notes through a ground wire, the DAC's output note on the +5VA flag and its Vout
  note under it, the gain note on C1101's value, "to JP203" on R1406's value, the DAC and TIA feedback
  capacitors' values on the resistors' designators, the TAP A and TAP -4V2 notes through a wire.  Each was moved in the generators and checked in a 40-second regenerate-and-crop loop
  (`gen/gen.py`, `kicad-cli sch export pdf`, `pdftoppm`) before the build; J108 moved to the strip's empty
  bottom-left corner after a placement-plus-silkscreen dry run (`build/scratch/silk/occ_probe.py`, 45 s, no
  routing) showed the occupancy grid had room for the jack and its name there and nowhere else in the strip.
* A tool that lied by omission: `pcb/plot.py` drew every designator white, including the ones the silkscreen
  placer had sent to the fab layer because they did not fit (not printed), so its crops showed collisions that
  do not exist on the board.  It draws those dim now; the README's board pictures come from it.
* 13:25-13:43: build 27 (1096 s): DRC 0 errors and 0 unconnected at every severity, the same three warnings as
  build 26 (two In1-only ground return vias north-west of the FPGA, a 0.2 mm -4V2 stub at (15.0, 59.6)); 412 of 412
  nets; 438 SMT placements on 85 BOM lines; every ordered part on a land pattern that fits it; the Ethernet moat
  2.30 mm at C4951's hot pad; the end plates unchanged; the release at ~$209 per board for five.  The crops and the
  3D render show every tap name beside its jack.  Build 27 is the repository.

### Build 28 log (2026-10-07, 01:00 - 09:45)

* Jason read build 27's sheets and silkscreen the way a student will (Prompt 26 in `CLAUDE_CODE_CHAT.md`,
  Response 26 has every answer).  Two of his questions turned up faults that no review and no check had seen:
  * **"Is the power distribution sufficient?"** -- measured by net from the shipped file, +3V3_ADC ran 205 mm at
    0.23 mm, +5V 146 mm at 0.23 mm and +3V3 at 0.28 / 0.30 mm, against a 0.4 / 0.5 mm rule that every build log
    had claimed.  The router's "a track must not be wider than the pad it enters" rule took the narrowest pad
    of the whole net, so one 0.25 mm LQFP or QFN pin (the AD9238's, the TLV62569's, the RTL8211F's) set the
    width of every connection on the net.  Two rules that routed the rails wide and narrowed only near the
    fine pads were tried and dropped: the wide tracks took the room the converters' own signals needed, and
    three runs lost two to five nets each.  So the router lays the rails as it always did, and a pass after
    routing (`pcb/fatten.py`) widens every rail track toward its class width wherever the copper round it
    leaves room at KiCad's clearance -- the other nets' tracks, vias and pads on the layer, the holes, the
    board edge, the Ethernet island's 1.5 mm; a track that ends in a pad stays no wider than the pad.  No
    route moves, so what routed still routes, and DRC on the widened copy of a finished board showed the same
    findings as on the original.  `build/route_report.json` lists every rail's length at each width before
    (`rail_widths`) and the growth (`fattened`).  A pin-plan lesson on the way: the AD9238's DCS and
    PDWN_A lines have bank 8 balls on the FPGA's south face, 60 mm detours round the DAC that the fine grid
    found in build 27 and never again; they are hand-laid on build 27's routes now.  Moving them to bank 7's
    two spare balls was tried and reverted (the swap that follows moved a dozen other balls and lost other
    nets at the margin) and is in the rev B list.  Build 28: +3V3_ADC 208 of 219 mm at 0.38-0.40 (was 205 at 0.23), +5V 114 of 150 mm at 0.44-0.50
    (was 146 at 0.23), +3V3 60 mm at 0.45-0.50 with 52 mm at 0.28-0.30 under the FPGA's 0.32 mm balls, the other
    rails at their 0.4 mm except the few millimetres at the fine-pitch pins; 659 mm of track grew.
  * **"Which jumper do PD and NOISE belong to?"** -- the 3-pin jumpers' centre-pin tick had never printed in
    any build: the silkscreen occupancy grid's 0.25 mm cells rounded the choices' claims onto the tick's own
    cell, and the matplotlib preview drew text at a third of its size, so nothing looked wrong.  KiCad's own
    rendering (`kicad-cli pcb export svg`) is the judge now, and the tick is tested against the words' exact
    boxes.  The same look found the front legend had never printed either (its lines were 150 mm wide, no
    empty area is, and the code gave up silently); it is wrapped into columns now and reported when a paragraph
    finds no room.
* The one electrical change: R2405/R2406/R2505/R2506 2.2 kΩ (gain 4.4) so the DAC outputs are the round ±1 V into
  50 Ω / ±2 V open that the labels say.  The beads were simulated before being kept (`sim/pdn_bead.cir`).
* Three things found on the way and fixed: 70 power symbols all referenced "#PWR" (KiCad warned "annotation
  errors" on every netlist export; numbered now); the SDRAM group bus's alias, which KiCad 10 keeps in the
  project file and `kicad-cli sch upgrade` drops from a sheet (the first build-28 run failed ERC with 26
  "not a member" warnings after the manual ERC had passed -- the alias is written into `.kicad_pro` now); and the
  silkscreen date, typed in since build 25, now the build's.
* Numbers: ERC 0; DRC 0 errors, 0 unconnected, three warnings (build 27's two ground return vias north-west of
  the FPGA and a 0.2 mm +5VA stub); every net routed, two of them by hand; 470 footprints and 1764 pads where
  KiCad puts them (0.0000 mm); the exported sheets read back with 0 overlapping words after the fix below; the
  release's hand-solder BOM empty; 5 boards about $1112 (~$222 each).  Ten runs between 04:47 and 09:35, in
  the order the log above tells; none changed the circuit beyond the one resistor.

## 6. Round 2 reconciled into builds 32-33 (2026-10-07, from 19:29)

Two second-round reports arrived, on build 31 (`11e2f61`): `design_review_CopilotSDK2/` ("order the five boards for
bring-up; do not hand this revision to the lab as the sheets describe it") and `design_review2_Gemini_3.8_Flash/`
("do not order build 31 unchanged", for the bench diode and CLK IN).  Grok answered in its chat window only and
wrote no file, so its review was lost when the window closed; `DESIGN_REVIEW_PROMPT2.md` now says in bold at its top
that only a file counts and that writing one's own directory is required (CLAUDE_PCB.md §1).  The two that arrived
agree on the four findings that matter, each confirmed here against the datasheet text before anything changed:

| # | finding | who | checked against | disposition |
|---|---|---|---|---|
| R2-1 | CLK IN: C5421 feeds the TLV3501's +IN with no series resistance; its inputs are diode-clamped and "must be current-limited to 10 mA" (§6.1 note 2); a 10 V, 50 Ω generator drives about 130 mA | both | TLV3501 §6.1; netlist | **Fixed**: R5427, 1 kΩ between the 10 nF and +IN: a 10 V step is 7.7 mA, and with 2-3 pF of input the pole is 50-80 MHz.  U302 moved 1.7 mm east for it |
| R2-2 | The Schottky kept USB off the bench header, but nothing kept the bench supply off USB: F601 joined +5V straight to VBUS, so with both plugged in the board back-fed the laptop.  The sheet said the opposite | CopilotSDK | netlist (J601-D601-F602-+5V, F601 VBUS-+5V) | **Fixed**: Q602, an AO3401A P-FET between F601 and +5V with its body diode pointing VBUS -> +5V; 100 k pulls its gate to ground (on, 0.06 Ω) and 10 k from J601's + pin lifts it above the source when a bench supply is present (off; the body diode blocks +5V -> VBUS).  No drop on the USB path, so the LM27761 keeps its headroom at USB's 4.75 V.  Basic parts only |
| R2-3 | F602 (2 A hold, 4 A trip) after D601 (B5819W, 1 A, 0.5 W): a 1-2 A fault cooks the diode and never trips the fuse; build 31's comment that the fuse protects the Schottky was false | both | MF-MSMF200 table; B5819W | **Fixed**: D601 is an SS34 (3 A, 40 V, SMA, 70 °C/W, Basic C8678), lying east-west.  Gemini's alternative of a 1.1 A fuse is not taken: its code is wrong (C17313 is the MF-MSMF050-2, F501's 0.5 A part; the 1.1 A one is C89647, Extended), and a 1.1 A hold derated in a warm box nuisance-trips at the board's 0.7 A plus a Pmod load |
| R2-4 | ADC LDO U604: (5.0-5.5 - 3.3) V x 0.21 A = 0.36-0.45 W at 187 °C/W, junction 110-129 °C in a 45 °C box at 65 MS/s | both | TPS7A20 §6.4; AD9238 IAVDD 200 mA | **Fixed**: R8001, 2.2 Ω 1206 ahead of U604's input capacitor (CopilotSDK's value; Gemini's 3 Ω leaves less headroom at USB's minimum): 0.1 W moves into the resistor, the LDO is about 0.26 W (+49 °C, 94 °C in a 45 °C box at 5.0 V), it still has 0.9 V of headroom at 4.75 V, and the resistor with the 10 µF filters the 5 V at 7 kHz.  One Extended part (C2907376) |
| R2-5 | RXD0 (RXDLY) and RXD3 (PHYAD0) relied on the PHY's internal pull-ups, but the ECP5 pulls its unconfigured pins down during configuration -- exactly when the PHY leaves reset and samples straps -- so RXDLY could read 0 and the address 0 | CopilotSDK (Gemini assumed the internal pull-ups win) | ECP5 datasheet: "During configuration the user-programmable I/O are tristated with an internal pull-down resistor enabled"; Realtek §7.8: "an external pull-high or pull-low via resistor is required" | **Fixed**: R4942 and R4943, 4.7 k to +3V3_ETH on ETH_RXD0 and ETH_RXD3, on the back beside RXD1's (R4941); 150 µA against 4.7 k still reads 2.6 V.  The sheet's note says why |
| R2-6 | LM27761's 5.8 V absolute maximum against the stated 5.0-5.5 V bench range plus a 10 % ring | both | LM27761 §6.1 | **Fixed by the stated range**: 4.75-5.25 V on the sheet and in the notes.  USB hot plug is overdamped (Q 0.3-0.4 with the cable's resistance: both reviews); no TVS, whose clamp would sit above 5.8 V anyway |
| R2-7 | FABRICATION_NOTES said 50 Ω at 0.3 mm; the SMA feeds are 0.35 mm (`RF_W`) | both | `mfg/make_fab.py`, the board | **Fixed**: 0.35 mm |
| R2-8 | `SLEWRATE=FAST` on the SDRAM and the converter data, against CLAUDE_PCB.md §13's slowest-that-meets-timing | both | the platform file | **Fixed** in the generated LiteX platform: SDRAM and DAC data SLOW, the DAC clocks and WRTs FAST.  Gateware, not copper |
| R2-9 | Stale or wrong text: the power sheet's "±4.5 V"; "±10 V max" into the 100 Ω 1206 (0.26 W at a stiff -10 V); the README's ±1.8 V / 13.5 MHz DAC numbers from before build 28; "every signal via has a ground via within 1.5 mm" (127 of 500 had no room); the TIA note's 3.5 dB of peaking (from the zero-bias 70 pF, where the diode sits at 25 pF at 4.2 V: 9.2 MHz, 0.5 dB) | CopilotSDK, Gemini | the sheets, README, `sim/tia.cir` | **Fixed**: each sentence now says what the board does; the TIA deck uses 25 pF and the note says an external diode or cable peaks more and 3.3 pF flattens it |
| R2-10 | ECP5 PLL jitter (0.011 UI p-p phase jitter, 20-30 ps rms) caps the ADC's SNR near 55-59 dB at a 10 MHz input | both | ECP5 Table 3.23 | **README note**: for full SNR at high input frequencies, clock the AD9238 from the TCXO without the PLL.  No copper change |
| R2-11 | In4 seams: DAC_CLK1/DAC_WRT1 ride the +1V1 corridor for 49 mm with the nearest ground via 5-6 mm away; everything else crosses for a few mm at slow edges | both (they differ on whether it matters; neither holds the order) | the zone outlines | **Bring-up check, rev B if needed**: scope DAC_CLK1 at the DAC.  The round-1 "4 x 4 mm patch" sentence was incomplete (it has a corridor to its buck) |
| R2-12 | 33 Ω on DAC_CLK/WRT at the DAC end, not the source; HDMI pairs 1-2.2 mm apart; REG_OUT reaches L401 through two vias; the TLV62569's 0.8 ms soft start is typical, Realtek wants 3.3 V slower than 0.5 ms | Gemini; CopilotSDK | the board, the datasheets | **Rev B list** (README) and **bring-up checks**: scope DVDD33's rise and REG_OUT on the first board |

Agreed with both and left as they are: the THS4521's bias, the BAV99s (their 3 pF is a 200 MHz pole at the FDA's inputs),
the OPA1612 headroom at -4.15 V, the DAC stage (±2.007 V open, ±1.005 V into 50 Ω, 12.3 MHz), PROGRAMN's 100 nF (not
in the programmer's path), the JTAG pinout, the fiducials and marks, the copper balance (In1 91 %, In4 90 %), no
termination on the SDRAM and converter buses at these periods, the CLK IN threshold network.
