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
are fixed in builds 21-25 and the checks that would have caught them now run in every build.  Build 25 is the
repository: DRC clean at every severity, 407 of 407 router nets, 421 placements on 84 BOM lines, 158 x 119 mm.  The things
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
      with nothing plugged in (rail LEDs: all nine on; RAILS header: +5V, +3V3, +1V1, +2V5, 3V3A, 3V3D, +5VA,
      -4V4), then USB PROG (the FT2232H enumerates with a blank EEPROM), then `openFPGALoader -c ft2232` a
      blinker, then the flash, then Ethernet with `ping`, then the SMAs.
