# Design review wanted: ECP5-2ADC-2DAC rev A, a teaching board with two ADC and two DAC channels

**You are being asked to try to break this design before it is fabricated.**  It was generated, routed
and reviewed by its author with one LLM over several days, so the faults that are left are the kind that
survive self-review: assumptions nobody in the room questioned.  Be blunt and be specific.  "The ADC
front end cannot work because X" is worth more than twenty notes about silkscreen.  If you approve of
something, say what you checked, because a review that approves everything cannot be told from one that
read nothing.

Nothing has been fabricated.  Changing anything costs only time.  "Start over on this block" is an
acceptable conclusion if you can say why.

---

## 0. Ground rules: where to work and what not to touch

Several reviewers (GPT, Grok, Gemini, Claude, ...) are reading this same working tree at the same time,
and the author will read every report side by side.  So:

1. **Make one directory for yourself at the project top, named after you, and put everything you produce
   in it**: `design_review_<YourName>/`, for example `design_review_GPT-5.6Terra/`, `design_review_Grok4.6/`,
   `design_review_Gemini3.8Flash/` (the convention from the GPSDO board's review).  Notes, scratch scripts,
   extracted text, renders, DRC and ERC reports, copies of files you want to annotate, and the report itself
   go there and nowhere else.  Name the report `design_review_<YourName>/DESIGN_REVIEW_<YourName>.md`.
2. **Do not modify, move, delete or create any file outside that directory.**  Not the sheets, not the
   board, not `mfg/release/`, not the Python, not the markdown, not `build/`.  Other reviewers are reading
   those files right now; a changed file would silently invalidate their work and the author's.  To try a
   change, copy the file into your directory and change the copy.
3. **Do not touch git.**  No `git add`, `commit`, `stash`, `checkout`, `reset`, `clean`, `branch`, `mv` or
   `rm`, nothing that writes to the repository or the working tree.  Read-only commands (`git log`, `git
   show`, `git diff`, `git status`, `git blame`) are fine.  The author commits; your directory will be
   committed by them when the reviews are collected.
4. **Do not run the build or anything else that writes into the tree.**  `python3 build.py` (with or
   without flags), `gen/gen.py`, `gen/fpga.py`, `pcb/pinswap.py`, `pcb/build_pcb.py`, `mfg/make_fab.py` and
   `mfg/end_panels.py` rewrite the schematic sheets, the board, `build/` and `mfg/release/`, the very files
   under review, and a full build takes 16 minutes of CPU that the others are also using.  Everything the
   build produces is already in the tree.  `pcb/river.py`, `pcb/stamp.py` and `pcb/route_diag2.py` draw into
   `build/scratch/diag/`: run them only from a copy (next point).  The KiCad GUI writes `.kicad_prl`, lock
   files and autosaves beside whatever it opens: open a copy.  `kicad-cli pcb drc` must be run without
   `--save-board`, with `-o` pointing into your directory (§9 has the commands).
5. **If you want to run anything that writes, work on a copy inside your directory:**
   ```bash
   rsync -a --exclude build --exclude reference --exclude '*-backups' --exclude 'design_review_*' \
         --exclude .git ./ design_review_<YourName>/repo/
   ```
   About 300 MB with the datasheets.  Inside the copy `python3 build.py --no-pcb` (one minute) recreates
   `build/netlist.net` and the rest of the schematic side and is harmless there; the full build is also
   allowed there if you have the 16 minutes.  The tools that only read (`tools/trace_paths.py`,
   `sim/run.py`, `mfg/footprint_check.py`, `tools/jlc_query.py`, `pcb/rotscan.py`,
   `tools/check_pads_kicad.py`) may be run in place with their output redirected into your directory; the
   two that talk to JLCPCB append to their own caches (`tools/jlc_cache.json`,
   `mfg/jlc_footprint_cache.json`), which git ignores.
6. **Do not read the other reviewers' directories or `DESIGN_REVIEW_RESPONSE.md` until your own findings
   are written down.**  The response is the author's own review against this prompt (findings 1 to 11 with
   their dispositions, fixed in builds 21 to 25); §7 and §8 below already say what it found, so you need not
   rediscover that.  Once your report is drafted, read the response and, if you like, the other
   directories, and add a short last section: what you agree with, what you still dispute, what they
   missed.
7. **Write the report as you go**, in case the session dies: the findings table first (ranked by what it
   would cost to be wrong, with a "confirmed by" column that says what you actually checked), then the
   detail.  Numbers beat adjectives.  Say what you checked and found correct as well as what you found
   wrong; a review that approves everything cannot be told from one that read nothing.

---

## 1. What the board is for

A lab and teaching instrument for an optics/electronics course: a successor to the Icepi Zero + 8-bit
ADC/DAC module used in the course's tutorials (`~/DroneSDR/openfpga/icepi-zero-dac-adc`), with real
converters, Ethernet, and clock in/out so two boards can be phase-locked across a room.  The experiments
it must support: direct digital synthesis, captures and spectra, lock-in detection, a 40 kHz ultrasonic
link, an optical link (on-board LED to on-board photodiode), Johnson-noise cross-correlation between the
two ADC channels, two-board time transfer and a software radio over the SMAs.  Students will plug things
into it that they should not, so inputs are clamped and nothing is unrecoverable.

## 2. The architecture

| block | part | what it is |
|---|---|---|
| FPGA | Lattice ECP5 LFE5U-25F-6BG256C | 24k LUTs, caBGA256, all nine I/O banks at 3.3 V |
| memory | W9825G6KH-6 (32 MB SDR SDRAM), W25Q128JVSIQ (16 MB QSPI flash), microSD | SDRAM at up to 100 MHz on an ODDR clock; the flash boots the FPGA (Master SPI, CFG[2:0] = 010) |
| ADC | AD9238BSTZ-65: dual 12-bit, 65 MS/s | two identical DC-coupled front ends: SMA, 50 Ω/hi-Z jumper, 100 Ω + BAV99 clamp to the ±4.5 V rails, source jumper (SMA / noise resistor / photodiode), two OPA1612 stages each x1 or x10 by jumper, THS4521 fully-differential driver at gain 1 on 3.3 V (VOCM 1.65 V), 33 Ω + 22 pF, converter.  ±1 V full scale at x1; sample clocks from the FPGA |
| DAC | AD9767ASTZRL: dual 14-bit, 125 MS/s | 19.2 mA full scale into 24.9 Ω loads, OPA2810 difference amplifier (gain 4, 2 kΩ ‖ 2.2 pF), 49.9 Ω series into the SMA: ±1 V into 50 Ω, DC coupled.  Channel 2's node also drives a V-to-I LED driver (OPA2810 + SS8050 + 10 Ω, 0-48 mA) for an on-board LED or an external one |
| receiver | VBPW34S photodiode, OPA2810 transimpedance (10 kΩ ‖ 2.2 pF), diode biased at -4.4 V | selectable as channel B's source |
| noise | 0 / 100 / 1k / 10k resistors behind a DIP switch, or your own on a header | Johnson noise into either channel |
| clocks | Fox FT5HN 25 MHz TCXO ±2.5 ppm (the system clock); Si5351A with its own 25 MHz crystal (three programmable clocks, I2C from the FPGA); CLK IN: SMA, 50 Ω jumper, 10 nF, self-biased 74LVC1GU04 + 74LVC1G17 Schmitt, into a PCLK ball (the GPSDO board's front end: a 10 MHz sine or any 0.5-3.3 V square wave to 100 MHz, the FPGA's PLL locks to it); CLK OUT: 74LVC1G17 + 49.9 Ω from any FPGA clock | every converter sample clock is an FPGA output |
| Ethernet | RTL8211F-CG, RGMII at 3.3 V, 22 Ω series; G2406S magnetics; plain shielded RJ45; Bob Smith 75 Ω x4 into 1 nF/2 kV | straps: PHYAD 1, TXDLY 0, RXDLY 1, IO pads on external 3.3 V.  The line side is an isolation island (no plane on any layer, 1.5 mm same-layer DRC rule) |
| USB | FT2232H: channel A = JTAG (MPSSE), channel B = serial console, one USB-C that also powers the board; a second USB-C wired straight to FPGA pins (27 Ω, 15 kΩ pull-downs, 1.5 kΩ pull-up switched by the FPGA, ULX3S style) | the FPGA port does nothing until the gateware implements USB |
| video | mini-HDMI, four pairs through 22 nF from 3.3 V pseudo-differential outputs (ULX3S/Icepi GPDI); PCA9306 level shifter for DDC; +5 V to the monitor through a 0.5 A polyfuse; HPD 4.7 kΩ series, 10 kΩ down | |
| expansion | two Pmod sockets 0.9" apart (a double module spans both), 33 Ω series; eight white LEDs, an RGB LED, two buttons, a JTAG header, a RAILS test header | |
| power | one 5 V in (the PROG USB-C through a 2 A polyfuse, or a bench header through a Schottky); TLV62569 bucks for 3.3 V and 1.1 V; LP5907 2.5 V (VCCAUX); TPS7A2033 x2 for the converters' 3.3 V analog rails; +5VA through a ferrite; LM27761 charge pump for -4.4 V; ferrite-fed +3V3_DRV, +3V3_DAC_D, +3V3_ETH; a dim red LED on every rail | about 3 W, 0.6 A at 5 V |

The schematic is six generated sheets (`fpga`, `adc`, `dac`, `ethernet`, `usb`, `power`) with the reasoning
printed on them as notes; `docs/SIGNAL_PATHS.md` walks every signal path through the netlist.

## 3. What the enclosure forces on the board

Hammond 1455Q1601 extrusion (125 x 51.5 x 160 mm, `datasheets/Hammond_1455Q1601.pdf`): the board slides
into its internal slots, so it is **158 x 119 mm** (the extrusion is made for a 120 mm board up to 159 mm
long), its long edges carry nothing within 3.5 mm, the six SMAs stand through the left end plate and the
RJ45, two USB-Cs, mini-HDMI and two Pmods through the right one.  `mfg/end_panels.py` draws both plates
with their cutouts (SVG and DXF, 1:1) from the placed board; the one number it cannot know is which slot the
board rides in (the slots are 2 mm apart), so every cutout's height is relative to a parameter that has to be
measured on the extrusion.

## 4. The physical board

158 x 119 mm, 6 layers (F.Cu signals / In1 GND / In2 signals / In3 signals / In4 power planes / B.Cu),
JLCPCB stackup JLC06161H-7628, ENIG, 0.8 mm BGA with filled-and-capped via-in-pad.  About 450 parts, 421
SMT placements on 84 BOM lines; the SMAs, headers, Pmod sockets, DIP switch and RJ45 are hand soldered.
The In4 planes: 3.3 V under almost everything, a 1.1 V patch under the core's balls with a corridor to its
buck, a 5 V corridor from the USB jacks down the right edge and along the bottom to the analog side.  Every
signal via has a ground via within 1.5 mm.  The analog strips (one per SMA, 17 mm pitch) run straight from
the SMAs to the converters down the left side; digital nets may not cross them.

State at the time of writing (build 25, 2026-10-04): ERC 0, DRC 0 errors and 0 unconnected at all severities
with the project's own rules (JLCPCB's capabilities or stricter, all silkscreen and courtyard checks as errors),
two warnings (ground return vias north-west of the FPGA that touch only the In1 plane); every net routed by the
build's own router or by hand; 3D renders in `docs/images/`.

## 5. How the project is built -- this deserves its own scrutiny

**There is no hand-drawn schematic and no hand-placed layout.**  `gen/` writes the six KiCad sheets from
`gen/fpga.py` (the pin plan, read from Lattice's own pinout CSV), `gen/parts.py` (every part with its LCSC
code and the reason for it) and `gen/sheet_*.py`; `pcb/` places every part (`pcb/floorplan.py`, by hand in
code, cluster by cluster) and routes every track (`pcb/escape.py` for the BGA, `pcb/river.py` for the seven
bus "rivers", `floorplan.HAND` for the converters' inputs and outputs and the whole Ethernet line side,
`pcb/router.py`, a 0.2 mm-grid A* over four signal layers, for the rest); `mfg/` writes the release.  One
command does all of it:

```bash
# (for the record; reviewers do not run these in the shared tree, see §0.4 -- in a copy, §0.5, they are fine)
python3 build.py              # schematic, ERC, netlist, pin swaps, gateware pin proof, board, DRC, release, renders (~16 min)
python3 build.py --no-pcb     # everything up to the schematic checks and the gateware proof (~1 min)
```

The board's own checks that are not DRC are listed in `README.md` ("Checks that are not DRC"): the signal
path walk, KiCad-vs-placer pad positions, the rotation scan, the rivers' clearance check, the microSD
card's blank path, the hand copper's clearance check, the isolation moat measurement.

This buys reproducibility and design rules expressed as code.  It costs the ability to nudge a part in the
GUI, and a reviewer has to read Python to see why the board looks as it does.  **The router is home-grown:
"passes DRC" is not "well routed".  Look at the copper.**

## 6. What I would attack first

Ordered by how much it would cost to be wrong.  These are the author's own least-confident points.

1. **The ADC front end's DC operating points.**  The OPA1612 stages run on +5VA / -4.4 V with ±1 V
   signals (x1) and are fine; the THS4521 runs on a single 3.3 V with VOCM = 1.65 V and takes a ±1 V
   single-ended, ground-referenced input through 499 Ω with 499 Ω feedback.  Its input pins then sit
   around 0 to 1.6 V -- inside its common-mode range (-0.1 to 2.2 V) by the arithmetic in
   `gen/sheet_adc.py`, but with little margin at the bottom.  The AD9238 is driven with 2 Vpp
   differential about 1.65 V.  **Check the bias arithmetic, the headroom at x10 overload, and whether a
   clamp to ±4.5 V upstream protects the 3.3 V FDA at all** (`sim/adc_frontend.cir` is the author's
   simulation; run it with `python3 sim/run.py`).
2. **The DAC output stage.**  Complementary 0-19.2 mA outputs into 24.9 Ω, an OPA2810 difference amplifier
   with gain 4 (499 Ω / 2 kΩ, 2.2 pF across the feedback), 49.9 Ω to the SMA.  ±1 V into 50 Ω means the
   amplifier swings ±2 V into 100 Ω: **is the OPA2810 happy with that at 13 MHz, and does the 2.2 pF make
   it stable with the SMA's cable capacitance?**  `sim/dac_stage.cir`.  Note the AD9767's output
   compliance is -1.0 to +1.25 V and its outputs see 24.9 Ω to ground only.
3. **The CLK IN squarer.**  A self-biased unbuffered inverter (1 MΩ feedback) through a 10 nF capacitor
   squares whatever is plugged in; its threshold drifts with the 3.3 V rail and its gain is finite, so a
   small 10 MHz sine makes a jittery clock.  The FPGA's PLL then multiplies it.  **For the two-board
   experiments, is this good enough, or should CLK IN have a comparator?**  The same question for CLK
   OUT (a 74LVC1G17 through 49.9 Ω).
4. **Ethernet.**  RGMII at 3.3 V (the RTL8211F allows it), 22 Ω series resistors, the PHY's own RX delay
   on and TX delay off, and the gateware (LiteEth) expected to add the TX delay.  **Is that the right
   split for an ECP5 at 125 MHz DDR, and do the RGMII lane lengths (the "river", `pcb/river.py`) need
   matching that they do not have?**  The isolation island: no plane on any layer under the line side,
   every other net 1.5 mm away on the same layer, the 1 nF/2 kV Bob Smith capacitor as the designed
   bridge, the jack shell to ground at its two legs.  **Enough for the 1500 V test?**
5. **Power sequencing and the ECP5's configuration.**  Master SPI needs VCCIO8 (3.3 V, from the buck)
   above the flash's VIH before VCC (1.1 V, the other buck) or VCCAUX (2.5 V, an LDO off the 3.3 V) reach
   their POR thresholds.  The author's reading: VCCAUX necessarily follows 3.3 V; VCC and 3.3 V come up
   from the same 5 V through two bucks of the same type, and the datasheet's wording ("at least one of the
   other two supplies") is satisfied by VCCAUX alone.  **Agree?**  Also the straps and pull-ups:
   PROGRAMN/INITN/DONE 4.7 kΩ up, TCK 4.7 kΩ down, TMS/TDI/TDO up, CFG[2:0] hard-wired 010, the flash's
   WP/HOLD/CS 10 kΩ up.
6. **The -4.4 V charge pump (LM27761) as an op-amp rail.**  2 MHz switching under the ADC front ends and
   the photodiode receiver, filtered by the chips' PSRR and 100 nF at each pin.  **Is that a noise
   problem for a 1.1 nV/√Hz preamp at x100 gain?**
7. **The generated layout.**  Rivers, hand copper and an A* router.  Things to look at: the SDRAM bus
   (unmatched lengths at 100 MHz), the HDMI pairs (intra-pair skew, the 22 nF capacitors' stubs), the USB
   pairs, the ADC's 33 Ω/22 pF at the converter, the return-via rule, the plane seams (the 5 V corridor
   cuts the 3.3 V plane along the bottom), the BGA's decoupling on the back under the package.
8. **The manufacturing package.**  CPL rotations are KiCad-native with corrections only for packages
   someone has read in a JLCPCB placement preview (`mfg/jlc_rotation.py`); the rest are listed in
   `FABRICATION_NOTES.txt` to be checked.  The build refuses to make a release if an SMT part has no
   LCSC code (build 20 had eleven such parts -- the converters, op amps, HDMI jack and microSD socket --
   and nobody noticed until the review), and refuses if any code's JLCPCB description does not carry the
   schematic's value and package (build 24 ordered a 470 kΩ as the DAC's 24.9 Ω loads, a 27 kΩ in the -4.4 V
   pump's divider, a 270 kΩ as the PHY's RSET, a 240 Ω in the USB port and a 1206 resistor as the 2.2 pF
   feedback capacitors -- eight codes typed wrong in `gen/parts.py`, every other check green).
   `mfg/footprint_check.py` compares EasyEDA's land pattern for every ordered code with the footprint on the
   board.  **What else of that kind is there?**  The codes of the ICs were read back the same way (the
   description carries the part number); the ones that were not are the hand-soldered parts.
9. **The mechanics.**  Board length and width from Hammond's drawing, connector protrusions from the
   footprints' courtyards; the Pmod sockets' and RJ45's heights above the board are from their drawings,
   not measured.  The end plates have not been milled or test-fitted.

## 7. Known open items (do not spend time rediscovering these)

* The FT2232H's 12 MHz crystal is a 20 pF part loaded with 27 pF capacitors (FTDI's reference values
  for an 18 pF crystal): about +30 ppm, inside USB's budget, but 33 pF would be right.
* The eight user LEDs run at about 0.5 mA (1 kΩ from 3.3 V into a white LED): dim.  The RGB LED and the
  power-good LEDs are deliberately dim.
* About a hundred small parts' designators (0402s in dense clusters, the BGA band, the Pmod resistor
  columns) are on the Fab layer, not the silkscreen; the assembly file carries every position.
* Two ground return vias north-west of the FPGA touch the In1 plane only (KiCad "dangling").  Cosmetic.
* `gateware/` holds a pin proof (yosys + nextpnr with a stub design) and a generated LiteX platform
  file, not a working SoC.  The TCXO drives the FPGA directly, so the board boots and runs with no
  software for the Si5351 (which only needs programming to use its three outputs).
* The CPL rotation table has entries for the SOT-23-5, VSSOP-8, TSOP-II-54 and the wide SOIC-8 only.

## 8. What has been verified, but is important enough to re-check

Every IC's pin numbering against the datasheet in `datasheets/` (ECP5 from Lattice's pinout CSV; AD9238
Table 6; AD9767 pin table; RTL8211F all 41 pins and the strap table; FT2232H; W9825G6KH; W25Q128; Si5351A;
LM27761; 93LC56B in SOT-23; SS8050; TPS7A20/LP5907/TLV62569 in SOT-23-5; 74LVC1GU04/1G17; USBLC6-2SC6;
PCA9306; the Fox TCXO's four pads from its drawing; BAV99 and both diodes' directions); every strap's
default against the PHY's table; the ECP5 power-up requirement for Master SPI; the Pmod socket's odd/even
pad numbering (rev A's first draft had ground and 3.3 V on the wrong pads); the HDMI jack's type-C pin
numbering; the microSD's blank card path; the RJ45 shield pads' net (a symbol/footprint pad-name mismatch
left them unconnected until build 17); the isolation island's moat on the finished copper; the board's
size against Hammond's drawing.

Real faults found and fixed in this review, which calibrate how much to trust the rest: the eleven
codeless parts above; HPD from the monitor (5 V) reaching a 3.3 V FPGA pin through 470 Ω (copied from the
Icepi Zero; now 4.7 kΩ); the board drawn 150 x 118 mm for an enclosure that holds 159 x 120 (the SMAs would
not have reached the end plate); USB-C receptacles classed as through-hole (their four shell pegs) and
sent to the hand-solder list; the PHY's 1.0 V switcher fed through an 0805 chip inductor rated 50 mA where
Realtek wants a 600 mA power inductor (now the bucks' 4 x 4 mm part, on the back -- Realtek's same-layer rule
is knowingly not met, see the response); eight entries of the parts table, seven of them on the board, whose LCSC
code named the wrong part (the 2.2 pF capacitors a
1206 resistor, the DAC loads 470 kΩ, the pump divider's 1.3 MΩ a 27 kΩ so the rail would have been -1.3 V,
the PHY's RSET 270 kΩ, the USB series resistors 240 Ω, the Bob Smith 75 Ω 5.62 kΩ), found by reading each
code's land pattern and description back from JLCPCB.

## 9. How to look at it

Everything is already generated and in the tree; nothing has to be built to review it (§0 says what not to
run).  The repository is `OpticsPCBs`, this project is its `ECP5-2ADC-2DAC/` directory.

* `README.md` -- the decisions, the board, every check.  **Start here.**
* `DESIGN_REVIEW_RESPONSE.md` -- the author's own review against this prompt; read it after your first
  pass (§0.6).
* `CLAUDE_CODE_CHAT.md` -- the full history: every prompt and every response, with every mistake.
* `gen/fpga.py` -- the pin plan; `gen/parts.py` -- every part and why; `gen/sheet_*.py` -- the circuits,
  with the notes that are printed on the sheets.
* `pcb/floorplan.py` -- where everything is and why; `pcb/build_pcb.py` -- the planes, the vias, the
  router's rules, the silkscreen; `pcb/river.py` -- the bus rivers.
* `docs/SIGNAL_PATHS.md` -- every signal path through the netlist; `docs/images/` -- schematic PDF and
  PNGs, copper plots, 3D renders.
* `sim/` -- the SPICE decks for the ADC front end, the DAC stage, the TIA and the LED driver.
* `mfg/release/` -- Gerbers, BOM, CPL, assembly drawings, FABRICATION_NOTES.txt, cost estimate, the end
  plates.
* `datasheets/` -- every datasheet cited anywhere.  It is in the working tree but not in git (144 MB of
  other people's copyright): `python3 tools/jlc_datasheet.py <LCSC code>` refetches the LCSC ones from
  JLCPCB; the Lattice, Hammond and Analog Devices documents came from their makers' sites.  If
  `build/scratch/review/txt/` exists, it holds a `pdftotext` of each one.
* `build/` (ignored by git, present in the shared tree) -- the netlist (`build/netlist.net`), `lcsc.json`,
  `placement.json`, `pin_swaps.json`, `drc.json`, `route_report.json`, and `build/scratch/final<N>.*`, the
  board and reports of every numbered build.

Read-only commands worth running, all writing into your own directory:

```bash
D=design_review_<YourName>; mkdir -p $D
KICAD=~/.local/bin/kicad-10.0.6-x86_64.AppImage        # kicad-cli is not on PATH on this machine
$KICAD kicad-cli pcb drc --severity-all --format json -o $D/drc.json ECP5-2ADC-2DAC.kicad_pcb   # NO --save-board
$KICAD kicad-cli sch erc --severity-all --format json -o $D/erc.json ECP5-2ADC-2DAC.kicad_sch
$KICAD kicad-cli pcb render --side top -o $D/top.png ECP5-2ADC-2DAC.kicad_pcb    # --side bottom too
$KICAD kicad-cli pcb export svg --layers F.Cu,F.SilkS,Edge.Cuts -o $D/front.svg ECP5-2ADC-2DAC.kicad_pcb
python3 tools/trace_paths.py > $D/SIGNAL_PATHS.md       # the same text as docs/SIGNAL_PATHS.md
python3 sim/run.py sim/*.cir                            # ngspice through KiCad's library; prints only
python3 mfg/footprint_check.py mfg/release/ECP5-2ADC-2DAC_bom.csv > $D/footprint_check.txt
python3 tools/jlc_query.py "AD9238BSTZ-65"              # stock, price and description of any part
pdftotext -layout datasheets/<file>.pdf $D/<file>.txt
```

The board file holds its zones filled (the build's DRC refills and saves them), so a DRC without
`--refill-zones` checks the copper the Gerbers were plotted from.

## 10. What would be most useful back

* A verdict on §6.1-6.3 (the analog chains and the clock front end) with numbers.
* Anything in the schematic that is simply wrong.  It has been checked hard, by people who believed it.
* The RGMII timing split (§6.4) and the isolation.
* Anything in the copper you would not sign off: the rivers, the hand-laid lines, the planes.
* What you would refuse to order.  The board has not been fabricated and nothing in it is sacred.
