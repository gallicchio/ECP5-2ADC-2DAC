# ECP5 + 2 ADC + 2 DAC

A 158 x 119 mm, 6-layer board (M3 holes in the corners, sized to slide into a Hammond 1455Q1601 extruded enclosure): a Lattice ECP5 (LFE5U-25F, caBGA256) with 32 MB SDRAM, 16 MB QSPI flash,
gigabit Ethernet, FT2232H (JTAG and serial on one USB-C that also powers the board), a second USB-C straight
to the FPGA, mini-HDMI (GPDI), microSD, two Pmods -- and the analog part that is the point of it:
two DC-coupled 12-bit 65 MSPS ADC channels (AD9238) behind OPA1612 / THS4521 front ends, and two DC-coupled
14-bit 125 MSPS DAC channels (AD9767) behind OPA2810 output stages, all on SMAs, plus an on-board LED driver
and photodiode receiver for the optical lock-in experiments.  rev A, 2026-10-02, by Jason Gallicchio and Claude.

Everything is generated.  `python3 build.py` makes the schematic, runs ERC, writes the netlist, places the
board and lets it choose the FPGA ball for every bus bit (`pcb/pinswap.py`, then the schematic is regenerated
with the swaps), proves the pin plan in yosys/nextpnr, routes the board, runs DRC with rules at least as
strict as JLCPCB's, and writes the manufacturing release (Gerbers, BOM, CPL, cost estimate, fabrication
notes) into `mfg/release/`.  `python3 build.py --clean` removes everything it made.  Nothing downstream of
`gen/`, `pcb/`, `mfg/` is hand-edited; the KiCad files are written in KiCad 10's own format.

| what | where |
|---|---|
| the schematic (7 sheets, A1/A2/A3) | `ECP5-2ADC-2DAC.kicad_sch`, `fpga/adc/dac/ethernet/usb/power.kicad_sch`, renders in `build/sch/*.png` |
| the board | `ECP5-2ADC-2DAC.kicad_pcb` |
| manufacturing release | `mfg/release/` (`*_gerbers.zip`, `*_bom.csv`, `*_cpl_jlcpcb_upload.csv`, `*_cpl_kicad_native.csv`, `FABRICATION_NOTES.txt`, `cost_estimate.csv`) |
| pin plan, constraints, LiteX platform | `build/fpga_pins.json`, `gateware/ecp5_2adc_2dac.lpf`, `gateware/litex/ecp5_2adc_2dac.py` |
| gateware proof (every pin, every clock) | `gateware/test/pins.v`, `gateware/test/build.sh` |
| analog simulations | `sim/*.cir`, run with `python3 sim/run.py sim/*.cir` |
| the generators | `gen/` (schematic), `pcb/` (placement, BGA escape, pin swaps, router, silkscreen, board writer), `mfg/` (release), `tools/` (JLCPCB queries) |
| decisions and questions | this file, `QUESTIONS.md` (gitignored, for Jason), `CLAUDE_CODE_CHAT.md` (the log) |

## Checks that are not DRC

* `python3 tools/trace_paths.py > docs/SIGNAL_PATHS.md` walks every signal path through the netlist (SMAs,
  headers, photodiode, oscillators, converter clocks) through each series part to its end, listing the
  shunt parts on every node.  Reading it against the datasheet pin figures is what found the swapped FDA
  outputs, the type-A numbering on the mini-HDMI, the SOIC numbering on the SOT-23 EEPROM, the reversed
  DAC port 2, the TCXO's second ground, the photodiode's pad-1-is-anode footprint and three reversed
  header labels in the first rev A.
* `tools/check_pads_kicad.py` loads the board with KiCad's own pcbnew and compares every pad position with
  what `pcb/fplib.py` assumed when placing and routing (all four rotations, both sides); it must report a
  worst disagreement of 0.
* `python3 pcb/rotscan.py` scores every rotation of the bus chips (SDRAM, ADC, DAC, PHY, FTDI, magnetics)
  by the total distance their signals have to travel.
* The big buses are not left to the router: `pcb/river.py` routes the SDRAM, the ADC, the DAC, the
  Ethernet PHY's RGMII lines (through their series resistors, anchored in columns beside the PHY) and the
  four HDMI pairs by construction, from the chip toward the FPGA, as nested rivers (inward from the pad
  rows, 45 degrees under the body, straight onto the FPGA's exit stubs of the same layer; a bundle bends
  where its exits lie around a corner), and the exit each lane lands on decides the FPGA ball --
  `pcb/pinswap.py` plans the rivers to write `build/pin_swaps.json`, the design regenerates around it,
  and `pcb/build_pcb.py` lays the same rivers before anything else is routed.  The recipes are
  `river.BUSES`; `python3 pcb/river.py` plans the SDRAM's river on the placed board, checks every
  clearance and draws it, `build/scratch/try_chip.py` does the same for any chip in the list.
* When a net does not route, look before rebuilding: `python3 pcb/route_diag2.py "<net>" ...` rebuilds the
  router's obstacle grid from the finished board, lifts that net's own copper, floods from its failed
  terminal on all four layers, retries the connection with a huge budget and draws postage stamps of the
  grid around the start and the goal (`build/scratch/diag/`); `python3 pcb/stamp.py BOARD x0 y0 x1 y1 [net ...]`
  draws one region from the real geometry, a panel per layer, with the fan-out lanes washed over it.
  Every routing rule in `pcb/router.py` and `pcb/build_pcb.py` (the lanes, the via cost inside them, where
  the stitching vias go, the placement standoff) came from reading those stamps, one failed net at a time.
* Every generated symbol's pin numbers were checked against the datasheet figure, not only its text table;
  `library/ours.pretty` holds the two footprints that had to be made (the trimmed-courtyard 0402 and the
  renumbered photodiode).
* The release refuses to build if any SMT part has no LCSC code (`mfg/make_fab.py`): build 20's release had
  none for the two converters, the six op amps, the HDMI jack and the microSD socket, because the sheets name
  parts by their short names and the LCSC table by part number (`parts.ALIASES` bridges them now), and the
  parts had silently joined the hand-solder list.  It also refuses if any ordered code's JLCPCB description
  does not carry the schematic's value and package (`make_fab.code_value_check`): build 24's table had eight
  codes typed wrong -- the DAC's 24.9 Ω loads were a 470 kΩ, the -4.4 V pump's 1.3 MΩ a 27 kΩ (a -1.3 V rail),
  the PHY's 2.49 kΩ RSET a 270 kΩ, the USB port's 27 Ω a 240 Ω, the 2.2 pF feedback capacitors a 1206
  resistor -- and every other check was green, because a code is only a name.
* The build fails if any track on the six SMA feed nets is not `RF_W` (0.35 mm, the 50 Ω width): the cloud
  review found builds 1-25 had routed them at 0.15 mm because the first routing pass never consulted the RF set.
* `python3 mfg/footprint_check.py` fetches EasyEDA's land pattern for every ordered code and lays it over the
  footprint on the board: a hole the board does not drill, a pad the board has no copper for, or a pad centre
  off its copper is reported with the number.  It is what found the 1206 resistor on the 0402 pads.  The
  release runs it (`mfg/release/FOOTPRINT_CHECK.txt`) and reads two more things off the same fit, the way the
  GPiBridge board did (`CLAUDE_PCB.md` §8): the quarter turn that laid JLCPCB's drawing on our footprint by
  pin number predicts the CPL rotation correction for every part nobody has yet read in a placement preview
  (7 of 7 corrections somebody has read agree with it), and where their drawing's origin is not KiCad's (the
  USB-Cs, 1.3 mm; the Pmod sockets) the uploaded CPL is moved to their origin, since JLCPCB places that.
  `ECP5-2ADC-2DAC_cpl_jlcpcb_upload.csv` is the one to upload, `_cpl_kicad_native.csv` KiCad's own numbers, and
  `PLACEMENT_CHECKS.txt` lists every predicted or moved part for the preview.  Two-pad polarised parts are
  read by the polarity mark in JLCPCB's drawing, not by pad number (they number the cathode 2).
* The CPL's bottom side: KiCad's own flip stores a footprint's pads mirrored top-to-bottom, and the mirror
  rule JLCPCB's previews taught (`jlc_rotation.BOTTOM_FLIP`) was read against such a file; `pcb/board.py`
  stores them mirrored left-to-right, which is the same placement with a stored angle 180 away, so the
  rule now turns this board's angle by 180 first (`BOTTOM_STORED_X_MIRRORED`, checked against the file every
  release).  Every bottom-side rotation in the CPLs of builds 1-27 was 180 out; the seven polarised bottom
  parts (three SOT-23-5 regulators, two BAV99, the magnetics, the microSD) are the first thing to check in
  the preview.
* The release refuses to build without filled zones in the board file or with a DRC error or unconnected
  item in `build/drc.json`.
* `build_pcb._pin1_marks` prints a dot beside pin 1 of every LCSC-pattern part whose pads are symmetric under
  a half turn and whose footprint prints no mark of its own (the RGB LED), and a cathode bar on polarised
  two-pad parts that print none; KiCad's own footprints carry their conventions.
* `mfg/end_panels.py` draws the enclosure's two end plates with every connector's cutout, 1:1, from the placed
  board (SVG and DXF in `mfg/release/`), and warns if cutouts overlap or leave the plate.
* `python3 mfg/jlc_rotation.py` re-checks the CPL rotation rule against the placement-preview readings it was
  derived from; `FABRICATION_NOTES.txt` lists the packages nobody has read in a preview yet.
* Power: about 3 W, 0.6-0.7 A at 5 V -- more than a USB 2.0 port's 0.5 A.  Power the board from a USB-C or
  USB 3 port, or from the 5 V IN header (the silkscreen legend says so).

## Monitor taps

Four Hirose U.FL jacks (C88374), each fed through 49.9 Ω, so the first board's questions are answered by
pushing a U.FL-to-SMA pigtail into a scope or an ADALM2000, not by holding a probe: **TAP A** and **TAP B**
(each ADC channel after its second preamp, before the fully differential driver), **TAP TIA** (the photodiode
receiver's output) and **TAP -4V2** (the op-amp rail after its ferrite bead).  A 50 Ω scope input sees half
the signal through the 49.9 Ω; a 1 MΩ input sees all of it (with the cable's capacitance as its load).  The
rails themselves are on the RAILS header.  An OPA1612 drives a tap's 49.9 Ω plus a 50 Ω input (100 Ω to
ground) without complaint: 10 mA at ±1 V, against the datasheet's ±55 / −62 mA short-circuit current and
its 40 mA at the rails; the second preamp's own 49.9 Ω output resistor is in series as well.

## What build 26 changed (the reviews, reconciled)

The five reviews of build 25 (section 5 of `DESIGN_REVIEW_RESPONSE.md` has the table): a BAV99 anti-parallel
across each THS4521's inputs; the ADC input resistors 1206; a bead and 10 µF between the LM27761 and the op
amps, the pump at -4.15 V instead of -4.4; the Bob Smith capacitor a 1 nF 3 kV 1812 and no 1500 V claim; both
RGMII delays inside the PHY (the RXD1 strap pulled up: TXDLY = 1), so the gateware adds none; a 2.2 pF across
the DAC difference amplifier's 2 kΩ to ground, and ±0.9 V / ±1.8 V on the sheet and silkscreen instead of
±1 / ±2 V; a TLV3501 comparator for CLK IN; 100 nF on PROGRAMN and an honest power-sequencing note; the USB-C
and HDMI jacks out to the edge and end-plate cutouts that pass the plugs; `+1V0_PHY` on the RAILS header; the
four U.FL taps; and the cloud review's two code findings (a clone could not build, the SMA feeds were routed at
0.15 mm).  Not changed, with the reasons in the response: the ADC input trace asymmetry, the DAC clocks over
the In4 split, the CPL rotation table (Jason's, on the day of ordering).

Build 27 (the same day) changed no circuit.  Reading the finished silkscreen and sheets as pictures found labels
sitting on things: the TAP B jack moved to its strip's empty bottom-left corner, the one place its name fits beside
it (next to its 49.9 Ω the strip's notch left no room), the TAP -4V2 name moved under its jack, and a dozen sheet
labels that sat on symbols or wires were moved (the CLK IN note, the comparator's power unit, the RAILS header's
designator, the Bob Smith and PROGRAMN notes, the DAC's output and Vout notes, the DAC and TIA feedback
capacitors' values, the ADC gain, tap and "to JP203" notes).  `pcb/plot.py` now draws the designators that go to the fab layer (not printed) dim, so the board pictures
below show the silkscreen as it prints.

The release of 2026-10-06 (no board change) has JLCPCB fit the through-hole parts as well: the six SMA jacks,
the RJ45, the DIP switch, the 2.54 mm headers (ordered as 1x40 and 2x40 strips the assembler snaps to
length, as on the GPSDO board) and two stocked 2x6 right-angle sockets for the Pmods; nothing is left to
hand-solder.  The next build widens every silkscreen line to 0.15 mm, the thinnest JLCPCB prints (the library
outlines are 0.05 and 0.12 mm in build 27's gerbers), and carries the headers' codes in the sheets.

## What build 28 changed (Prompt 26: the sheets and the silkscreen read as a student would)

Circuit: the DAC difference amplifiers' gain resistor is 2.2 kΩ instead of 2 kΩ (gain 4.4), so the outputs are
the round ±1 V into 50 Ω and ±2 V open that the silkscreen and the sheet now say (build 26 had printed the
honest ±0.9 / ±1.8 V of gain 4); nothing else electrical.  The ferrite beads were simulated before being
kept (`sim/pdn_bead.cir`: the BLM18KG601SN1 as DCR + L || R || C between a regulator's 10 µF + 100 nF and
the load's 10 µF + 100 nF per pin; the impedance the load sees against frequency): each bead's ~1 µH
resonates with its 10 µF near 50 kHz, a 0.7 Ω peak seen by the load, far below the 1.5 and 2 MHz
switchers (5 mΩ there), and no regulator's feedback loop sits behind a bead (the LM27761's divider
senses its own output, before the bead), so nothing can oscillate round one.  The power sheet's note
says so; the damping-leg variants (`sim/pdn_leg_*.cir`) are there for a rev B if a 0.7 Ω peak at 50 kHz
ever matters.

Sheets: every converter is a MUX-style trapezoid (long side the bus, short side the analog, the clock in
from below and turning up into it; the DAC's WRT and CLK come from the left, lower than the trapezoid);
each dual op amp's three units sit in a dashed box with the power unit under the gap between the
amplifier units; the long essays at the top of the ADC, DAC and Ethernet sheets are columns broken at
sentences, and most of them moved to the blocks they describe (the gain and noise list under the two
amplifiers, "THS4521 fully-differential driver at gain 1" over its block, the series-resistor placement
notes beside the resistors, sideways); note boxes are sized to their text; the photodiode's footprint
suffix, which printed as "K1A2" across the BAV99, is hidden; the Ethernet dashed box is bigger so no
resistor sits on it; and three checks now gate the sheets: the generator's own overlap model (text against
text, text against symbol bodies, wires through text, with KiCad's measured field extents), its page-margin
check, and `gen/check_sch_text.py`, which reads the exported PDF back with `pdftotext -bbox` and fails on
any two words that overlap or one past the frame.  Power symbols are numbered (`#PWR0001`...), which ends
KiCad's "annotation errors" warning on every netlist export.

Board: the board sits in the middle of a page with a 25 mm margin and the title block below it (the design
keeps its own frame; only the written file is shifted, so gerbers, drill and CPL agree); DAC 1 is above
DAC 2 (the strips swapped: port 2's lines now cross under port 1's on In2); every section's name is inside
its box under the top edge; every part's designator is inside its section's box and every part is inside
the box its designator is in, with both lists in `build/route_report.json`; every jumper says what it does
beside itself ("50Ω IN / hiZ OUT", "x1 IN / x10 OUT", the 3-pin choices beside the outer pins with a tick
through the centre pin) and the build fails on one more than a few millimetres away; the taps' names stand
beside their jacks and their designators are not printed ("J107" read as a jumper); "USB FPGA" is "USB
USER"; the microSD says "contacts toward the board" and "card slides in here"; the noise resistor header is
"EXT R" with its pins named NOISE and GND; the legend is wrapped into columns, each paragraph beside what it explains where it can be
(HEADERS above the POWER box the headers live in, USB under the FT2232H's box; builds to 27 asked for 150 mm
lines, found no room, and printed no legend at all); the title carries the build date.  `tools/power_path.py`
measures the DC resistance from every rail's source to every supply pin along the copper the board has
(Prompts 28-30: after build 30's analog planes the worst supply pin on the board is a 33 mΩ digital one, under a millivolt at its current; the FPGA's planes are 2.5-4.5 mΩ; it joins copper by overlap, as KiCad's connectivity does).  Rails: the router had narrowed every rail that touches one fine pin (+3V3_ADC, +5V, +3V3) to
that pad's width over its whole length, 0.23-0.28 mm for 150-200 mm.  It still routes them that way (every
other rule tried moved the problem into the router: three runs lost two to five nets to the room the wide
tracks took), and afterwards `pcb/fatten.py` widens every rail track toward its class width as far as the
copper round it allows -- the other nets' tracks, vias and pads on its layer, the holes, the board edge
and the Ethernet island's 1.5 mm, each at KiCad's clearance; a track that ends in a pad stays no wider
than the pad.  The routes do not change, so what routed still routes; `build/route_report.json` lists
every rail's length at each width before (`rail_widths`) and the growth (`fattened`).  The release's hand-solder BOM is empty: everything is assembled.  ADC_DCS and
ADC_PDWN_A, two static control lines with bank 8 balls on the FPGA's south face, are the two longest routes
on the board (60 mm detours round the DAC on the back) and the router's fine-grid pass found them once, in
build 27, and never again; they are laid by hand now on build 27's own routes (`floorplan.adc_control_lines`).
Moving them to bank 7's two spare balls was tried and reverted: the swap that follows reshuffled a dozen other
balls and cost other nets at the margin -- a rev B item.

Build 29 (the same day) moved two silkscreen paragraphs to their homes and changed nothing else; its routing
came out identical.  Build 30 (the same day, Prompt 30) gave the analog supplies planes on In4: the op amps'
rails had been 60-70 mm of 0.4 mm trace from one bead, 176-206 mΩ, and the converters' AVDD 16 mm from their
LDOs, 42-45 mΩ; they are 5-8 mΩ now (Response 30 has the table), the digital supplies stay on traces, and the
routing finished in half the time.  Responses 27 and 28 in `CLAUDE_CODE_CHAT.md` answer the FT601 question (layout, cost,
the pin budget, what it buys against the ADALM2000 and the Red Pitaya) and the power-delivery one.

Answers in Response 26 of `CLAUDE_CODE_CHAT.md`: the LED is red (615-630 nm) and the VBPW34S sees it at
about 60 % of its peak sensitivity; the "0 to +0.48 V" applies to each of IOUTA and IOUTB; J305 is the
FT2232H's JTAG brought out, and an external programmer uses it with FTDI OFF fitted; an OPA1612 drives a
tap's 100 Ω without trouble; the data-rate and USB 3 questions, and the LPF jumpers, are in the rev B list.

## What build 31 changed (Prompt 31: the fixes before the second review round)

Jason, 2026-10-07: "If you think those things should be fixed before others do a design review, fix them now."  The
upload-readiness pass on build 30 (CLAUDE_PCB.md §10, gate 17) found nothing that would stop a fabrication run, and
four things the lessons file asks for that the board did not have.  Build 31 adds them and changes nothing else:

* **Three fiducials** (a 1 mm copper dot in a 2 mm mask opening, front and back) at (25.5, 12.5), (120, 7.5) and
  (146.5, 113) mm from the top-left corner -- spots build 30 had free of copper, silkscreen and courtyards on both sides,
  as far apart as the board allows (the bottom-left corner is the DIP switch's).  JLCPCB adds its own on the panel
  rails; marks on the board itself are what align the 0.4 mm LQFP-64, the QFN-40 and the BGA.
* **The copper layer numbers 1-6**, each in copper on its own layer, in a row at x 70-83, y 1.9 mm: the top slot band,
  which the extrusion hides and where no part may go.  Hold the bare board against the light to check the layer order;
  the inner layers' digits are islands inside the ground planes.
* **`JLCJLCJLCJLC` on the back silkscreen** in the same band (x 95, y 1.9): on the order form choose "Remove order
  number: specify a location" and JLCPCB's order number lands there, hidden in the extrusion.
* **F602, a second 2 A resettable fuse (the same MF-MSMF200-2, C210837) on the bench 5 V header**, after the Schottky:
  the header had none, and a bench supply delivers more than the 1 A B5819W or a 2.54 mm pin survives.  Same BOM line
  as F601, no new Extended fee.  It sits east of the bulk capacitors under the POWER box's top edge, its +5V pad on
  its own via into the +5V plane.

The marks are netless graphics (`pcb/place.FIDUCIALS`, `LAYER_MARK`, `ORDER_MARK`; `pcb/build_pcb.marks`), so they need
no symbol, no BOM row and raise no parity warning; the placer's keep list, the router's obstacle grid and the
silkscreen's occupancy map all know them.  Two things the pass found are left for the reviewers to weigh
(`DESIGN_REVIEW_PROMPT2.md` §3): the ADC's analog LDO dissipates 0.34 W in a SOT-23-5 at 65 MS/s (+64 °C at 187 °C/W),
and about 94 µF of ceramic on +5V behind a 0.05 Ω fuse rings on a hot plug toward the LM27761's 5.8 V absolute maximum
if the bench supply is set at the top of its stated 5.0-5.5 V range (build 32 states 4.75-5.25 V instead).  Build 30's DRC had four warnings, not the three
the first prompt's state line said: the two dangling ground vias and two `connection_width` necks (0.03 and 0.06 mm) in
one 0.7 x 0.9 mm crumb of the In4 ground fill at (150.8-151.5, 44.1-45.0), two ground vias 0.7 mm apart between the +5V
corridor and the +3V3 plane; harmless, and KiCad reports a zone's neck at the zone's anchor, so it took a shrink test
(shapely) to find.

## What build 34 changed (Prompt 33: JLCPCB's placement preview of build 33)

Jason's upload of build 33 showed two faults in the preview, and both were the release's, not the board's:

* **Every 2.54 mm header appeared as a whole 40-pin strip**, a 100 mm bar centred on its pin 1.  The headers were ordered
  as 1x40 / 2x40 strips for JLCPCB to snap, as on the GPSDO board, so JLCPCB's drawing was the strip.  Each header is now
  the stocked part of its own length (XFCN PZ254V-11-02P / -03P / -06P and PZ254V-12-18P): cheaper, drawn and fitted by
  pin number like any other part, and placed at the middle of its pins (the release's datum shift).
* **The six SMAs lay along the board edge and the two Pmod sockets stood a quarter turn round.**  JLCPCB numbers those
  parts' pins unlike KiCad, so no fit by pin number could predict their rotation, and the CPL sent them at KiCad's angle.
  Their corrections are now read from JLCPCB's land drawings, where the barrel and the socket body show which way the
  part faces: +90 for the SMA (barrel along +x in their drawing, -y in KiCad's) and +270 for the Pmod socket.  The
  release now fails on any such part that nobody has read.  The new headers need a correction too: JLCPCB draws them
  lying along x with pin 1 on the left, KiCad standing along y, so all of them go out at -90 (the 1x3, 1x6 and 2x9
  predicted by pin number, the 1x2 -- two pads predict nothing -- read off the drawing).
* **`mfg/preview_check.py` computes the preview**: JLCPCB's own land drawing of every top-side part, placed where the
  upload CPL says and turned as it says, against the board's pads and courtyards.  Build 34's CPL: all 347 top-side
  placements land on their pads with their bodies the right way.  Build 33's: the six SMAs and both Pmod sockets
  flagged, as the preview showed.  It runs in the build after the release and stops it on a wrong placement; the
  127 bottom-side placements are still the preview's to judge.

And the two CPLs are named for what they are: `ECP5-2ADC-2DAC_cpl_jlcpcb_upload.csv` (upload this one) and
`ECP5-2ADC-2DAC_cpl_kicad_native.csv`, the convention of every board in this repository since 2026-10-08.  The copper is
build 33's: compared item by item, all 6905 tracks, vias, footprints, zone fills and texts are the same (the file's UUIDs
and the silkscreen date differ).  BOM 95 lines, 49 Extended; about $1100 for five boards ($220 each).

## What builds 32-33 changed (Prompt 32: the second round of reviews)

CopilotSDK and Gemini 3.8 Flash reviewed build 31 (`design_review_CopilotSDK2/`, `design_review2_Gemini_3.8_Flash/`;
Grok's review was given only in its chat window and was lost).  `DESIGN_REVIEW_RESPONSE.md` §6 is the reconciliation.
Five circuit changes, each confirmed against the datasheet before it was made:

* **CLK IN: R5427, 1 kΩ** between the 10 nF and the TLV3501's +IN.  Its inputs are clamped to its rails and must be held
  to 10 mA; a 10 V generator through the capacitor alone drove about 130 mA.
* **USB PROG through Q602, a P-FET** (AO3401A) that a bench supply on J601 turns off, so the bench supply can no longer
  back-feed the laptop's VBUS through F601 (it could in every build to 31).  With USB alone the gate sits at ground
  through 100 k and the FET is 0.06 Ω; the bench input lifts the gate through 10 k above +5V, and the body diode blocks
  +5V -> VBUS.  No drop on the USB path.
* **D601 an SS34** (3 A, SMA) instead of the B5819W (1 A, 0.5 W), which a 1-2 A fault would have cooked behind the
  2 A-hold fuse without tripping it.
* **R8001, 2.2 Ω 1206 ahead of the ADC's LDO**: at 65 MS/s the AD9238's 200 mA put 0.36 W into U604's SOT-23-5
  (110 °C in a 45 °C box); 0.1 W of it is in the resistor now.
* **R4942, R4943: 4.7 k pull-ups on the PHY's RXDLY and PHYAD0 straps.**  The ECP5 pulls every unconfigured pin down
  during configuration, which is when the PHY samples them; the internal pull-ups would have lost.

And: the bench input is specified 4.75-5.25 V (the LM27761's absolute maximum is 5.8 V); the fabrication notes ask for
50 Ω at 0.35 mm, the width drawn; the generated LiteX platform drives the SDRAM and the DAC data with slow edges (the
clocks fast); the power sheet's title, the ADC input's ±10 V claim (±8 V continuous, ±10 V briefly), the DAC stage's
numbers, the return-via claim and the photodiode amplifier's note now say what the board does.

Build 32 (20:00) had one new DRC warning, a 0.2 mm router stub on the new LDO input; build 33 lays that 3 mm by hand
(`floorplan.analog_power`) and prints the bench range in the back legend.  Build 33: ERC 0; DRC 0 errors, 0 unconnected,
the same four warnings as builds 30-31; 446 SMT and 28 through-hole parts on 93 BOM lines (47 Extended: the 2.2 Ω is the one
new fee; the SS34, the AO3401A, the 1 k and the 4.7 k pull-ups are Basic); 478 footprints and 1781 pads where KiCad puts
them; the sheets' PDF read back with 0 overlapping words; nothing to hand-solder; about $1116 for five boards ($223 each).

**Sampling clock and SNR** (both reviews): an ECP5 PLL's output jitter, 20-30 ps rms, caps the AD9238's SNR near
55-59 dB for a 10 MHz input, against the converter's 70 dB (it matters less as the input frequency falls: 1 MHz loses
nothing).  For full dynamic range at high input frequencies, pass a clean clock to the ADC without the PLL: the 25 MHz
TCXO itself (25 MS/s), a Si5351 output, or a low-jitter source on CLK IN.

## Rev B candidates

* **Bypass jumpers for the DAC output and ADC input low-pass filters**, to show the DAC's images (zero-order
  hold) on a spectrum analyser and aliasing on the ADC, or to run a higher Nyquist zone on purpose.  Not in
  rev A: each filter sits in a 17 mm strip with no room for a 3-pin jumper and its labels, and a bypass
  across an RC changes the strip's loading.
* **The converters at full rate -- deferred to rev B by Jason on 2026-10-07 (Prompt 31), with the FT601 and the full-rate,
  full-depth, 2 TX + 2 RX bidirectional streaming it would carry.**  Both ADCs at 65 MS/s x 12 bits are 1.56 Gb/s and both DAC ports at 125 MS/s
  x 14 bits 3.5 Gb/s.  Gigabit Ethernet carries about 940 Mb/s of payload (one ADC channel at full rate, or
  both at 30 MS/s), so streaming at full rate needs USB 3: an FT601 (USB 3.0 FIFO, 32-bit bus to the FPGA,
  up to 5 Gb/s on the wire, 3.2 Gb/s usable) on a USB-C wired for SuperSpeed pairs.  The ECP5-25F moves the
  data easily (a 32-bit FIFO at 100 MHz); the SDRAM holds 16.8 M samples (0.13 s of both ADCs at full rate) for capture-then-send,
  which is what rev A does over Ethernet.
* The 45F/85F FPGA (a BOM change), DDR3 (a second BGA), the TX series resistors at the FPGA end of the
  RGMII lines, a damping leg on the converter clock lines: the items in Decisions and in the review
  responses.
* From the round-2 reviews (build 31): the DAC_CLK/DAC_WRT 33 Ω at the FPGA end, as source terminations
  (Gemini; rev A has them at the DAC); a stitching capacitor where DAC_CLK1/DAC_WRT1 leave the +1V1 corridor on
  In4 if the first board's scope shows ringing there (CopilotSDK: the nearest ground via is 5-6 mm away); the HDMI
  pairs matched to 0.15 mm (1-2.2 mm apart now, about 15 ps: fine at 720p); the PHY's REG_OUT inductor on the
  PHY's own layer, as Realtek asks.

## Design reviews

`DESIGN_REVIEW_PROMPT.md` is the brief for reviewers (with the ground rules for working in this tree in
parallel: one `design_review_<Name>/` directory each, no git, no build).  `DESIGN_REVIEW_RESPONSE.md` is the
author's own review of build 25.  The independent reviews of build 25 are `design_review_CopilotSDK/`,
`design_review_Gemini_3.8_Flash/` and `design_review_Grok4.7/`, each with its `DESIGN_REVIEW_<Name>.md` and the
files it measured or ran; the prompt's §11 summarises them.  `docs/datasheets/txt/` and `drawings/` are the
datasheets as text and pictures for a reviewer who has only the git tree (the PDFs are not committed).

**Round 2** (build 31, 2026-10-07): `DESIGN_REVIEW_PROMPT2.md` is the brief for the board as it would be ordered -- what
changed since round 1, the state of build 31 and the author's claim that nothing blocks the order, what to attack, the
lessons file `CLAUDE_PCB.md` restated as checks (half of it was written after round 1), every tool with the command that
runs it.  Reviewers write into the "2" version of their directories (`design_review_CopilotSDK2/`,
`design_review_Gemini_3.8_Flash2/`, `design_review_Grok4.7_2/`), copy anything they want to change into a temporary
place, and touch nothing else in the tree.

## Pictures (regenerated by every build into `docs/images/`)

![front](docs/images/board_3d_top.png)
![back](docs/images/board_3d_bottom.png)

`docs/images/ECP5-2ADC-2DAC_schematic.pdf` is the whole schematic; `sch_*.png` one sheet each;
`board_front.png` / `board_back.png` are the copper-and-silk plots.

## Decisions

### FPGA: LFE5U-25F-6BG256C

| part | LUTs | BRAM | DSP | I/O (caBGA256) | JLCPCB stock 2026-10-02 | price |
|---|---|---|---|---|---|---|
| LFE5U-25F-6BG256C | 24k | 1 Mbit | 28 | 197 | 81 | $14.25 |
| LFE5U-45F-6BG256C | 44k | 1.9 Mbit | 72 | 197 | 0 | $15.93 |
| LFE5U-85F-6BG256C | 84k | 3.7 Mbit | 156 | 197 | not listed | -- |

Only the 25F is in stock, which settles it for rev A.  What the bigger parts would buy: the 45F's 72 DSP
slices (vs 28) would let both ADC channels run a 16-tap FIR plus two lock-in multipliers plus an OFDM FFT
at the same time; the 25F does the lock-in and correlation experiments comfortably (a lock-in is two
multipliers and two accumulators per channel) and a VexRiscv Linux SoC with Ethernet fits in ~60% of it.
The footprint is identical, so a rev B with a 45F/85F is a BOM change.

### RAM: 32 MB SDR SDRAM

| option | size | part | stock | price | LiteX support on ECP5 -6 | risk |
|---|---|---|---|---|---|---|
| SDR SDRAM | 32 MB | W9825G6KH-6 | 8909 | $5.63 | litedram SDR PHY, used on ULX3S/Icepi Zero | low |
| DDR3L | 256 MB | MT41K128M16JT-125 | 1989 | $19.07 | litedram ECP5 DDR3 PHY, marginal at speed grade -6 | high |

32 MB holds 16.8 M 16-bit samples (0.13 s of both ADCs at 65 MS/s, 8 s of both at 1 MS/s, 17 s of one; a
figure of "8 s at 65 MSPS" stood here until build 28) and a Linux image.  DDR3 would hold
longer captures but the ECP5 -6 DDR3 PHY in litedram is the single biggest schedule risk on a one-night
board, and the BGA-96 adds a second escape problem.  Rev B candidate.

### ADC: one AD9238 (dual) rather than two AD9226 / AD9235

| option | bits / MSPS | supply | package | stock | price per board | notes |
|---|---|---|---|---|---|---|
| **AD9238BSTZ-65** | 2 x 12 / 65 | 3.3 V | LQFP-64 | 21 | $71 | two matched cores, shared reference, simultaneous sampling |
| 2 x AD9226ARSZ | 12 / 65 | 5 V | SSOP-28 | 24 | $157 | the classic; 5 V analog |
| 2 x AD9235BRUZ-65 | 12 / 65 | 3.3 V | TSSOP-28 | 33 | $75 | one AD9238 core each |
| 2 x AD9235BCPZ-40 | 12 / 40 | 3.3 V | LFCSP-32 | 134 | $51 | slower; most stock |

The correlation experiment wants the two channels to be as alike as possible: one die, one reference,
one clock tree.  The AD9238 is that part, and cheaper than two AD9226.  Its stock is thin (QUESTIONS.md 9).

### DAC: AD9767

| option | bits / MSPS | stock | price per board | notes |
|---|---|---|---|---|
| **AD9767ASTZRL** | 2 x 14 / 125 | 147 | $14 | dual, own WRT/CLK per port, interleaved I/Q mode |
| 2 x AD9744ARUZ | 14 / 210 | 762 | $50 | faster, two packages |
| 2 x DAC904E | 14 / 165 | 261 | $12 | cheapest; two packages, 5 V-capable |

Both DAC outputs are complementary current outputs into 24.9 ohm, taken differentially by an OPA2810 at
gain 4.4 (2.2 kΩ || 2.2 pF over 499 Ω on both inputs, since build 28): ±2.0 V unloaded, ±1.0 V into 50 ohm,
DC coupled -- the extra 10 % over gain 4 makes up for the 499 Ω inputs loading the 24.9 Ω -- flat to 12.3 MHz
(`sim/dac_stage.cir`), a full-scale sine clean to 10 MHz (the OPA2810's 192 V/µs needs 126 V/µs there).

### Ethernet, USB, clocks, power

* RTL8211F-CG (RGMII, 87k in stock, $1.38) + G2406S discrete magnetics + a plain shielded RJ45.  The
  in-stock magjacks tie the four chip-side centre taps together; this voltage-mode PHY wants them separate.
* FT2232H: channel A is JTAG (openFPGALoader -c ft2232), channel B the console -- both at once.
* Clocks.  A 25 MHz TCXO (Fox FT5HNBPK25.0, ±2.5 ppm, the GPSDO board's proven part -- 50 MHz TCXOs of that
  grade are rarer and dearer, and the ECP5's PLL makes 50/100/125 MHz from 25 as readily as from 50) is the
  FPGA's system clock; an Si5351A on its own 25 MHz crystal gives three programmable clocks (2.5 kHz-200 MHz)
  on PCLK pins, locked to each other but not to the TCXO; the PHY and the FTDI have their own crystals
  (25 and 12 MHz).  Every sample clock is an FPGA output (the AD9238's two and the AD9767's two), so the
  gateware chooses the rate and phase.  The CLK IN SMA (50 ohm by jumper, a 10 MHz GPSDO sine of 0.3 V peak
  or more, or any 0.5-3.3 V square wave to 80 MHz, squared by a TLV3501 comparator on the ADC's quiet 3.3 V:
  +IN AC-coupled and biased to mid-rail through 10 kΩ, -IN at mid-rail, 6 mV of hysteresis inside, 4.5 ns;
  builds 1-25 had the GPSDO board's self-biased inverter, whose threshold moved with the digital rail) feeds a PCLK
  pin for the FPGA's PLL to lock to -- a lab instrument's 10 MHz REF IN, from which the ADC and DAC can run at
  different, phase-locked rates -- and the CLK OUT SMA (any FPGA clock through a buffer and 49.9 ohm, 3.3 V
  CMOS) is what the next board's CLK IN takes.
* One 5 V USB-C powers everything: two bucks (3.3 V, 1.1 V), LDOs for +2.5 V, +3V3_ADC and +3V3_DAC,
  ferrite-fed +3V3_DRV/+3V3_DAC_D/+3V3_ETH/+5VA, and an LM27761 charge pump for -4.15 V (`-4V2`; the op amps
  get it through a ferrite bead and 10 µF, so the pump's 2 MHz is not common to both noise channels; -4.15 V
  rather than -4.4 V leaves the LDO 0.45 V of headroom from a 4.75 V USB supply).  ~3 W total.

## The board

158 x 119 mm, 6 layers, JLCPCB JLC06161H-7628: F.Cu signals / In1 GND / In2 signals / In3 signals / In4 power planes / B.Cu.
In4 carries a 1.1 V patch under the core's 1.1 V balls with a corridor to its buck, the 5 V plane from the
USB-C down the right edge to both bucks' input sides, 3.3 V under everything else, and since build 30 the
analog side's own planes: -4V2 under the strips west of x 27 (every op amp's V- pin), +5VA east of it to the
converters (their V+ pins, the THS4521s, the TIA), and the AD9238's and AD9767's AVDD as patches from their
LDOs on the back to the chips (ground fills what they leave); every rail pad over its plane has a via into it (a pad off its plane gets one at the plane's edge,
dropped again when the router joins the pad elsewhere), and the other rails are 0.4 mm traces.  The 3.3 V
VCCIO balls are joined by an island on In3 under the core, fed from the 3.3 V plane through three vias in the
ball gaps at the core's east edge; VCCAUX's two balls leave the via field on a hand-laid 0.127 mm track
(`floorplan.aux_feed`).
M3 mounting holes 4.2 mm in from each corner, tied to ground.  The long edges (top and bottom) carry no
connector and no part within 3.5 mm, so the board slides into the PCB slots of a Hammond 1455Q1601 extrusion
(125 x 51.5 x 160 mm; `datasheets/Hammond_1455Q1601.pdf`: made for a 120 mm wide board, up to 159 mm long
between its end plates, slots 2 mm apart) with the SMAs through the left end plate and every other connector
through the right one.  The size is the enclosure's: 119 mm wide fills the slots (120.5 mm slot to slot) and
158 mm long puts the SMAs' flanges at one end plate and the USB-C, HDMI and RJ45 faces at the other -- builds
up to 21 were 150 x 118 mm, which would have left 9 mm between the SMAs (7.5 mm of barrel past the edge) and
their plate.  The USB-C jacks stand 1.9 mm and the mini-HDMI 0.75 mm past the edge (as far as their rear
through-hole pads allow, 0.35 mm from the edge), and since the plate is 1.45 mm thick and the board can float
up to 2 mm between the plates, the USB-C and HDMI cutouts are sized for the plugs' overmoulds (12.8 x 6.8 and
14 x 8 mm), so a plug seats however the board sits -- a review (Gemini) found the build-25 jacks 0.3 mm inside
the edge, where a USB-C shroud could not have reached.  `mfg/end_panels.py` draws both end plates with their
cutouts (SVG and DXF, 1:1) from the placed board; the one number it cannot know is which slot the board rides
in, so measure the extrusion and set `PCB_TOP_ABOVE_FLOOR` before milling.  The east cluster (PHY, magnetics, jack, FTDI, USB, HDMI, Pmods, RGB LED,
microSD) is drawn 8 mm east of its 150 mm coordinates (`floorplan.E`):

* **left end**, 17 mm apart down the edge: CLK IN, CLK OUT, ADC A IN, ADC B IN, DAC 1 OUT, DAC 2 OUT, each
  name and its limit printed under its SMA, and each one's circuit in its own silkscreen box beside it (the
  termination jumper, series resistor (a 1206: ±8 V continuous, ±10 V briefly -- a stiff -10 V puts 0.26 W in it) and
  clamp first, then the op amps with their passives in a straight run to the converter, a U.FL monitor tap on
  the second preamp's output, and a BAV99 on the back under the THS4521's input pins, anti-parallel across
  them, so that a saturated preamp cannot put more than a diode drop between them (the reviews disagreed on
  whether the amplifier would survive 2.27 V there; now it cannot see it); the two ADC strips are identical,
  and so are the two DAC strips);
* **right end**, top to bottom: RJ45 (y 19), USB-C PROG (34.5; FTDI: JTAG, serial, and the board's 5 V),
  USB-C USER (48; wired straight to the FPGA, a USB device once the gateware has a core), mini-HDMI (62),
  Pmod B and Pmod A 0.9 inch apart (a Digilent Pmod VGA or an icesugar PMOD-TFTLCD spans both) -- spaced
  so that spec-maximum plugs fit side by side, "USB PROG" and "USB USER" standing beside their jacks (it was
  "USB FPGA" until build 28: a name that says whose port it is keeps the one cable out of the wrong jack);
  the microSD is on the back, inboard (there is no edge left, and a card is rarely changed), its card
  sliding in from the east over a strip of blank board that the build checks (`floorplan.SD_CARD_PATH`);
* **the Ethernet line side is an isolation island**: from x 127.3 mm (under the magnetics' body, between its
  chip-side and line-side pad rows) to the right edge and from y 3 to 29 mm, a rule area on all six copper
  layers that no plane may enter, so the jack, the magnetics' line-side pads, the Bob Smith network (four
  75 Ω into a 1 nF / 3 kV 1812 capacitor, hand-laid on the back north of the magnetics) and the eight LAN
  lines have no copper of any other net under them; a DRC rule (`gen/rules.py`, the LAN class) keeps every
  other net's copper 1.5 mm from them on the same layer, and the router puts no return via inside.  The
  magnetics are the isolation (IEEE 802.3's 1500 Vrms is theirs to meet); the capacitor is the designed
  bridge across it; the gap is a bench clearance, measured on the finished board (`build/scratch/p11/moat.py`,
  numbers in the response), and the board has not been hipot-tested -- builds up to 25 had a 1206 2 kV part
  and the reviews called its 1.4 mm pad gap and the "1500 V" wording unsupported.  The jack's shell is
  grounded at its two shield legs, one into the corner mounting hole's ring, one to a ground via just outside
  the island;
* the bottom edge, left to right: the noise-resistor DIP switch and EXT R header (your own noise
  resistor, NOISE to GND), the photodiode and
  PD EXT header, the photodiode receiver's U.FL tap, the -4.2 V charge pump (its bead and 10 µF on the back
  under it), the RAILS header (2 x 9: the rails in the bottom row with their names standing over the pins,
  the whole top row ground, `+1V0_PHY` since build 26, so a probe reaches every rail), the two bucks, the
  5 V IN bench header and the -4V2 U.FL tap; the top edge: the clock chains, eight white LEDs
  (LED0-LED7) and the two buttons, the Si5351 and the 25 MHz TCXO that is the FPGA's clock.  The RGB LED
  and its resistors have their own box west of Pmod A.
* The FPGA is in the middle, the SDRAM above it facing its north banks, flash and the JTAG header below it;
  the AD9238 and AD9767 on the left facing its west banks with their front ends and output stages further
  left; the PHY and FTDI on the right.  The Ethernet magnetics sit on the back directly under the RJ45.
  Every section is outlined on the silkscreen with its name inside, under its top edge (a name cut into
  a line that two strips share read as either strip's), every part's designator kept inside its section's
  box, and every part inside the box its designator is in (the build lists both kinds of stray); every
  3-pin jumper has its two choices printed beside its two outer pins with a tick through its centre pin
  between them, every 2-pin jumper what a shunt does, beside it ("50Ω IN / hiZ OUT", "x1 IN / x10 OUT");
  the headers' pins are named; the chips
  carry their names and ratings and every clock its frequency; a legend in the largest free area says
  what each jumper and header does, and a longer one on the back says what the board is.

The BGA is escaped by construction (`pcb/escape.py`): rings 7 and 8 leave on F.Cu, ring 6 on In2, ring 5 on
In3, ring 4 on whichever midline is free; every ball in rings 1-6 has a filled-and-capped via in its pad.
The 1.1 V core and 3.3 V VCCIO balls are joined by zone islands under the core on In2/In3.  The FPGA's
100 nF decoupling is on the back, directly under the package: each capacitor (a 0402 with a trimmed
courtyard, `library/ours.pretty`) spans a power ball's via and the via of an adjacent ground ball, so the
loop is the two vias and nothing else; the capacitors that cannot be paired that way sit in the band just
below the package, with the bulk capacitors.  The big buses are rivers (`pcb/river.py`: SDRAM, ADC, DAC, RGMII, HDMI, Pmods --
lanes laid by construction from the chip to the FPGA, which decide the balls), the converters' inputs and
outputs and the whole Ethernet line side are laid by hand (`floorplan.HAND`), and everything else is
routed by `pcb/router.py`, a 0.2 mm-grid A* over the four signal layers; the SMA feeds are 0.35 mm wide (50 ohm over the In1 plane); digital nets
may not cross the analog strip down the left; and a signal via gets a ground via within 1.5 mm for the return
current wherever there is room (`return_vias` in `pcb/build_pcb.py`; build 33: 382 of 515 signal vias, 226 of them
added for it, 133 with no room -- `build/route_report.json`, "return_vias").

Open `kicad-gui.sh` (not `kicad`) to look at the files: KiCad's OpenGL canvas under native Wayland
does not repaint after zoom and scroll; the script runs it through XWayland.
