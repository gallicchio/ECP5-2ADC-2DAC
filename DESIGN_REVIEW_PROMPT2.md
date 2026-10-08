# Design review, round 2: ECP5-2ADC-2DAC rev A at build 31 -- the last look before it is ordered

**The author intends to upload this board to JLCPCB.  Your job is to find what would make the first board dead,
wrong, or embarrassing, before the money is spent.**  The first round (build 25, 2026-10-04, `DESIGN_REVIEW_PROMPT.md`)
found real faults -- eleven parts with no LCSC code, eight codes naming the wrong part, a 5 V signal into a 3.3 V pin,
a board 8 mm too short for its enclosure, a 50 mA inductor on a 600 mA rail -- and builds 26-31 fixed them and changed
more.  Every change is a new place to be wrong.  This round is about build 31: the board as it would be ordered.

Be blunt and specific.  "Do not order this because X" with a number is worth more than twenty notes about style.  If
you approve of something, say what you checked; a review that approves everything cannot be told from one that read
nothing.  Rev B is a separate list (`README.md`, "Rev B candidates": a USB 3 FIFO for full-rate streaming, LPF bypass
jumpers, a bigger FPGA, DDR3); do not propose features for it here unless the finding changes a rev A decision.

---

## 0. Ground rules: where to work and what not to touch

Several reviewers read this working tree at the same time; the author reads every report side by side; the author's
own KiCad may have the project open while you work.  So:

1. **One directory for yourself at the project top, the "2" version of your first-round directory, and everything
   you produce goes in it:** `design_review_<YourName>2/` -- `design_review_CopilotSDK2/`,
   `design_review_Gemini_3.8_Flash2/`, `design_review_Grok4.7_2/` (an underscore where the name ends in a digit), a
   new reviewer's `design_review_<YourName>2/`.  Name the report `DESIGN_REVIEW_<YourName>2.md` inside it (so
   `design_review_Grok4.7_2/DESIGN_REVIEW_Grok4.7_2.md`).  Notes, scratch scripts, extracted text, renders, DRC and ERC
   reports, copies of files you annotate: there and nowhere else.
2. **Do not modify, move, delete or create any file outside that directory.**  Not the sheets, not the board, not
   `mfg/release/`, not the Python, not the markdown, not `build/`, not the first-round directories.  Other reviewers
   are reading those files right now; a changed file silently invalidates their work and the author's.
3. **To try a change, copy first, into a temporary place, and change the copy.**  The whole project, with the
   datasheets, is about 300 MB:
   ```bash
   D=design_review_<YourName>2; mkdir -p $D
   rsync -a --exclude build --exclude reference --exclude '*-backups' --exclude 'design_review_*' --exclude .git \
         --exclude '*.lck' ./ $D/repo/
   # or, if your directory should stay small:  T=$(mktemp -d); rsync -a ... ./ $T/  -- and say in the report where it was
   ```
   Inside the copy, `python3 build.py --no-pcb` (about a minute) recreates `build/netlist.net` and the whole schematic
   side; the full `python3 build.py` (11 to 25 minutes, mostly the router) recreates the board and the release.  Both are
   harmless there and forbidden in the shared tree.
4. **Do not touch git.**  No `git add`, `commit`, `stash`, `checkout`, `reset`, `clean`, `branch`, `mv` or `rm`.
   Read-only commands (`git log`, `git show`, `git diff`, `git status`, `git blame`) are fine and useful: the builds
   are commits (§1).  The author commits your directory when the reviews are collected.
5. **Do not run anything that writes into the shared tree.**  Writers: `build.py` (any flags), `gen/gen.py`,
   `gen/fpga.py`, `pcb/pinswap.py`, `pcb/build_pcb.py`, `mfg/make_fab.py`, `mfg/end_panels.py` (they rewrite the sheets,
   the board, `build/` and `mfg/release/`); `pcb/river.py`, `pcb/stamp.py`, `pcb/route_diag.py` and `pcb/route_diag2.py`
   (they draw into `build/scratch/diag/`); the KiCad GUI (lock files, `.kicad_prl`, autosaves beside whatever it opens:
   open a copy); `kicad-cli pcb drc` with `--save-board` (never) or with `-o` outside your directory.  Readers you may run
   in place, with their output redirected into your directory, are listed in §5; the two that talk to JLCPCB append to
   their own gitignored caches (`tools/jlc_cache.json`, `mfg/jlc_footprint_cache.json`), which is fine.
6. **Form your own findings on build 31 before you read any second-round directory.**  The first-round directories,
   `DESIGN_REVIEW_RESPONSE.md` (whose section 5 reconciles them into builds 26-27) and `README.md` are history: read
   them whenever you like, but do not let them set your list.  Once your report is drafted, read the other `..2/`
   directories if they exist and add a last section: what you agree with, what you dispute, what everybody missed.
7. **Write the report as you go**, in case the session dies: the verdict (order / do not order, in one paragraph) and
   the findings table first (ranked by what it would cost to be wrong, with a "confirmed by" column naming what you
   actually ran or read), then the detail.  Numbers beat adjectives.
8. **If you are a cloud review working from the git branch alone** (`/code-review ultra`, or anyone who cloned): you
   have everything the build makes, because it is committed -- the sheets, the board with its zones filled,
   `mfg/release/`, `docs/`, the small build results in `build/` (`netlist.net`, `drc.json`, `erc.json`,
   `route_report.json`, `placement.json`, `lcsc.json`, `pin_swaps.json`, `bus_plan.json`).  You do not have the
   datasheet PDFs; you have their text in `docs/datasheets/txt/` and the picture-only pages in
   `docs/datasheets/drawings/`.  You cannot run KiCad; you do not need to.  You may not have the repository's
   `CLAUDE_PCB.md` (the author's lessons file, which may be uncommitted): §4 restates every rule of it that applies
   here, so nothing is lost.  Your report is your output; the author files it as `design_review_<YourName>2/`.

---

## 1. What the board is for, and what changed since round 1

What the board is for, its architecture, the enclosure and the generated build are §1-§5 of
`DESIGN_REVIEW_PROMPT.md` and have not changed: an ECP5 LFE5U-25F with an AD9238 (dual 12-bit, 65 MS/s) and an AD9767
(dual 14-bit, 125 MS/s), gigabit Ethernet, two USB-Cs, mini-HDMI, SDRAM, flash, microSD, clock in/out, 158 x 119 mm,
six layers, in a Hammond 1455Q extrusion, for an optics/electronics teaching lab.  `README.md` is the long form.

Since round 1 (build 25) the circuit, the sheets, the board and the package changed in six builds.  Each row is a
place to look; the commit is where `git diff` shows exactly what moved.

| build | date | commit | what changed | where to look |
|---|---|---|---|---|
| 26 | 2026-10-04 | `c3256ec` | The five reviews reconciled (response §5): a BAV99 anti-parallel across each THS4521's inputs; 1206 input resistors; a bead and 10 µF on the op-amp rail (now -4.2 V); a 1 nF 3 kV 1812 Bob Smith capacitor and no 1500 V claim; both RGMII delays in the PHY (TXDLY = RXDLY = 1); the DAC difference amplifier AC-balanced, labels ±0.9 / ±1.8 V; a TLV3501 comparator for CLK IN instead of the squarer; 100 nF on PROGRAMN; the USB-C and HDMI jacks moved to the edge with cutouts; +1V0_PHY on the RAILS header; four U.FL monitor taps through 49.9 Ω; the SMA feeds at their 50 Ω width | `gen/sheet_adc.py`, `sheet_dac.py`, `sheet_fpga.py` (clocks), `sheet_power.py`, `pcb/floorplan.py`; response §5 |
| 27 | 2026-10-04 | `c3256ec` | No circuit change: TAP B's jack moved so its name fits; a dozen schematic labels moved off symbols and wires | the sheets |
| 28 | 2026-10-07 | `2bf975f` | One electrical change: the DAC difference amplifiers' gain resistors 2.2 kΩ (was 2 kΩ), so the outputs are the round ±1 V into 50 Ω / ±2 V open the labels say.  A routing bug fixed that no review saw: the router narrowed every rail that touched one fine LQFP or QFN pin to that pad's width over its whole length (+3V3_ADC, +5V, +3V3 ran 150-200 mm at 0.23-0.28 mm in every build to 27); it still routes them that way and `pcb/fatten.py` then widens each track toward its class width wherever the copper round it leaves clearance.  The AD9238's DCS and PDWN_A lines hand-laid.  Readability: converters drawn as MUX-style trapezoids, dual op amps in dashed boxes, sheet essays broken into columns beside their blocks, the board centred on its page, DAC 1 above DAC 2, section names inside their boxes, every jumper's meaning beside it, the taps' names beside their jacks, "USB USER", three new checks (a measured-extent overlap model in the generator, the exported PDF read back with `pdftotext -bbox`, labels and parts kept to their section boxes) | `pcb/fatten.py`, `build/route_report.json` (`rail_widths`, `fattened`), `pcb/floorplan.adc_control_lines`, every sheet, `docs/images/` |
| 29 | 2026-10-07 | `b8c66e1` | The HEADERS and USB silkscreen paragraphs moved beside what they explain; TAPS says 50 Ω; `tools/power_path.py` (the DC drop from every rail's source to every supply pin, from the copper in the file) | `pcb/build_pcb._legend`, `tools/power_path.py` |
| 30 | 2026-10-07 | `ccf700b` | The analog supplies as In4 planes: -4V2, +5VA, +3V3_ADC and +3V3_DAC each get a patch of the power layer under its parts with a via per pin, after power_path showed the op-amp rails at 176-206 mΩ and the converters' AVDD at 42-45 mΩ (5-8 mΩ now).  Routing time halved because the rails no longer crowd the converters' pins | `pcb/build_pcb.RAIL_ZONES`, `rail_vias`; `python3 tools/power_path.py` |
| 31 | 2026-10-07 | (this commit) | Fixed before this round, on the rules of §4: three fiducials (1 mm copper, 2 mm mask, front and back), the copper layer numbers 1-6 in a row in the top slot band, JLCPCB's order-number marker on the back silkscreen in the same band, and **F602, a second 2 A resettable fuse (the same MF-MSMF200-2) on the bench 5 V header after the Schottky** -- the header had none, and a bench supply can deliver more than the 1 A Schottky survives | `pcb/place.FIDUCIALS/LAYER_MARK/ORDER_MARK`, `pcb/build_pcb.marks`, `gen/sheet_power.py` (F602), `pcb/floorplan.py` |

The pin plan (`gen/fpga.py`) and the pin swaps (`build/pin_swaps.json`) are build 27's: moving the ADC's control
lines to the FPGA's west face was tried in build 28 and reverted (it reshuffled twelve swaps and lost four nets), so
DCS and PDWN_A are hand-laid on the route the router once found, and a rev B puts them on the right face.

## 2. The state of build 31, and the claim you are asked to break

Build 31, 2026-10-07, the board as it would be ordered (`ECP5-2ADC-2DAC.kicad_pcb` with its zones filled, `mfg/release/`):

| what | build 31 |
|---|---|
| ERC | 0 |
| DRC, all severities, the project's rules (JLCPCB's capabilities or stricter; silkscreen and courtyard checks as errors) | 0 errors, 0 unconnected, schematic parity 0, 4 warnings: connection_width x2, via_dangling x2 (named below) |
| routing | every net routed (442 nets; `route_report.json` `unrouted` is empty; its `failed_connections` is the first pass's list, not the result) |
| zones | 357 filled polygons in the shipped file |
| release | Gerbers (zip and folder; the job file names six copper layers, 158.1 x 119.1 mm, ENIG), Excellon drill, BOM 91 lines, CPL 467 rows (343 top, 124 bottom) plus the native CPL, assembly PDFs, end plates, `FABRICATION_NOTES.txt`, `PLACEMENT_CHECKS.txt`, `FOOTPRINT_CHECK.txt`, `cost_estimate.csv` |
| BOM against CPL | every CPL designator on a BOM line and back; no duplicate code; no duplicate designator |
| hand solder | 0 rows: nothing |
| assembly | 439 SMT placements and 28 through-hole parts on 91 BOM lines, 46 of them Extended |
| parts | every code's JLCPCB description checked against value and package; every land pattern fitted (`FOOTPRINT_CHECK.txt`; the four PADS findings are the snapped header strips); stock and prices fetched by the build from JLCPCB's live API on 2026-10-07 (`cost_estimate.csv`); thin: C514277 AD9238BSTZ-65 at 21 for 1 a board |
| cost | ~$1112 for 5 boards, ~$222 a board, list prices |
| absolute paths | `git grep -I -n -E '/home/|/Users/|/tmp/'` in the project: none; the netlist's source is relative |
| DC drops | `python3 tools/power_path.py`, the worst supply pin per rail (copper only, beads and inductors excluded): see the table below |

The warnings, each placed (board frame, x right, y down from the top-left corner):

* two `via_dangling`: ground return vias at (66.4, 49.6) and (63.9, 51.5), north-west of the FPGA, touching the In1 plane only;
* two `connection_width`: 0.064 and 0.030 mm necks in one crumb of the In4 ground fill (§2's list below).

| rail | worst pin (chip) | resistance from the rail's source |
|---|---|---|
| +1V1 | FPGA | 2.5 mΩ (pin L9) |
| +2V5_AUX | FPGA | 105.5 mΩ (pin G11) |
| +3V3 | FT2232H | 6.8 mΩ (pin 42) |
| +3V3_ADC | AD9238 | 22.7 mΩ (pin 5) |
| +3V3_DAC | AD9767 | 7.8 mΩ (pin 47) |
| +5VA | OPA2810 1 | 7.4 mΩ (pin 8) |
| -4V2 | TIA | 26.0 mΩ (pin 4) |
| +1V0_PHY | RTL8211F | 65.6 mΩ (pin 8) |
| +3V3_ETH | RTL8211F | 69.1 mΩ (pin 29) |
| +1V8_FTDI | FT2232H | 51.2 mΩ (pin 37) |
| +3V3_DAC_D | AD9767 | 51.6 mΩ (pin 22) |
| +3V3_DRV | AD9238 | 32.8 mΩ (pin 52) |

**The author's claim: nothing in this package blocks a successful fabrication and assembly run.**  The things that
remain are the day-of-ordering steps that only Jason can do (read JLCPCB's placement preview against
`PLACEMENT_CHECKS.txt`, the bottom side's seven polarized parts first; tick epoxy-filled-and-capped vias; order the
JLC06161H-7628 impedance stack-up; "Remove order number: specify a location"; measure the extrusion's slot before the
end plates are milled) and the risks any first board carries.  Prove the claim wrong, or say what you checked and
could not fault.

Things the author knows about build 31 and has decided to live with, so that you can spend your time elsewhere (or
tell the author the decision is wrong):

* The In4 ground fill leaves a 0.7 x 0.9 mm crumb at board (150.8-151.5, 44.1-45.0): two ground vias 0.7 mm apart in
  the gap between the +5V corridor and the +3V3 plane, their annuli joined by 0.03 and 0.06 mm webs of fill.  KiCad
  reports both webs as `connection_width` warnings.  Each via is grounded through the In1 plane whatever the fab does to
  the webs; nothing floats.
* Two ground return vias north-west of the FPGA touch only the In1 plane (KiCad "dangling"): cosmetic, since round 1.
* The ADC's analog LDO runs warm at full speed (§3.1): a review question, not yet a change.
* About 150 small parts' designators are on the Fab layer, not the silkscreen (0402s in dense clusters, the BGA's
  decoupling band, the Pmod resistor columns); the assembly file carries every position.
* The silkscreen date is the day of the build, written by the build.

## 3. What to attack this round

Ordered by how much it would cost to be wrong.  Items 1-4 are new since round 1; 5-10 are round 1's list as it stands
after the fixes.

1. **The ADC's analog regulator's dissipation.**  U604, a TPS7A2033 in SOT-23-5 (RθJA 187 °C/W, JEDEC board), makes
   +3V3_ADC from +5V and feeds the AD9238's AVDD and the two THS4521s.  The AD9238 draws 200 mA at 65 MS/s (datasheet,
   IAVDD at AVDD = 3 V; a little more at 3.3 V): (5.0 - 3.3) V x 0.2 A = 0.34 W, +64 °C above ambient, so 89 °C junction
   at 25 °C and about 110 °C in a closed extrusion at 45 °C, against a 125 °C maximum (thermal shutdown about 160 °C).
   At the course's usual 10-40 MS/s it is 0.1-0.19 W.  **Is this acceptable for a lab instrument, and if not, what is
   the smallest change: a resistor in series with the LDO's input to share the drop (3 Ω: 0.6 V, 0.12 W in a 1206,
   headroom still 1.1 V), the bigger-package low-noise LDO you would name, or AVDD at 3.0 V?**  The DAC's LDO (U605,
   71 mA) is fine.  Check the author's arithmetic from the datasheet text (`docs/datasheets/txt/`), and look at the
   copper under the SOT-23-5 (`pcb/floorplan.py`, `analog_power`): RθJA on a board with planes is lower than JEDEC's
   number, by how much here?
2. **The new In4 analog planes and their seams.**  Since build 30 the power layer holds, besides +3V3, +5V and the
   +1V1 patch, four analog patches (`pcb/build_pcb.RAIL_ZONES`, priorities 3 and 4, each inside the others' outlines).
   Signals on In3 and B.Cu return through In4; the author's own scan of build 30 counted, on In3 and B.Cu, 16 segments
   of 12 nets crossing the +3V3_ADC patch's edge (among them ADC_B_D0-D4, the ADC's own data lines, CLK_EXT, DCS and
   PDWN_A), 22 segments of 16 nets crossing the +3V3_DAC patch's edge (ADC_DCS, DFS, PDWN_A/B, DAC_P1_D1/D3/D4), 20
   crossing +5VA's, and on the +1V1 patch, besides the known DAC_CLK1 / DAC_WRT1 crossing, the flash's SPI lines
   (CS, DO, WP, HOLD and the configuration clock CCLK/MCLK).  **Which of these crossings matter at their edge rates
   (the ADC's data at 65 MS/s with the FPGA reading it, the DAC's data at up to 125 MS/s, the flash at the boot
   clock), and is there a stitching capacitor or a ground via near the seam where it matters?**  Decide, do not
   count: a 3.3 V plane seam under a 20 MHz line with the In1 ground plane two layers up is not a 10 Gb/s problem.
3. **The widened rails and the copper that touches them.**  `pcb/fatten.py` widens every Power/Rail track toward its
   class width (Rail 0.4 mm, Power 0.5 mm) where tracks, vias, pads, holes, the edge and the LAN clearance allow, after
   routing; DRC on the result is clean.  **Look at the copper (`docs/images/board_front.png`, `board_back.png`, or
   your own `kicad-cli pcb export svg`): is there a widened track that now hugs a fine pad row, a via, or an analog
   input?**  `build/route_report.json` has `rail_widths` by net before and after and `rail_thin` (rails still mostly
   below their class width: +3V3, +5V and +3V3_ADC are, and their planes carry the current; the drops are the judge:
   `python3 tools/power_path.py`, worst pins in §5).
4. **The 5 V input, both ways in.**  USB PROG: VBUS through F601 (MF-MSMF200-2, 2 A hold, about 0.05 Ω) into about
   94 µF of X5R ceramic (two 22 µF 0805 and five 10 µF 0603, all 25 V) and five regulators.  Bench: J601 through D601
   (B5819W, 1 A) and, since build 31, F602 (the same fuse).  **(a) Hot-plug ringing** (Linear's AN88): a live 5 V on a
   1 m cable (about 1 µH) into all-ceramic input capacitance rings toward twice the supply unless the series resistance
   damps it; the author's estimate is Q about 0.6 with the cable's and the fuse's resistance (overshoot about 10 %).
   The tightest absolute maximum on the rail is the LM27761 charge pump's VIN, 5.8 V; the TLV62569 bucks', LP5907's
   and TPS7A20's are in their datasheets.  A bench supply set to 5.5 V (the sheet's stated range) plus 10 % is 6.05 V.
   **Is a TVS or a bulk electrolytic on +5V warranted, or is the stated range wrong?**  (b) **F602's placement and the
   Schottky's dissipation** (0.7 A x 0.45 V = 0.3 W in SOD-123 at full load).  (c) The USBLC6-2SC6 on each USB-C: its
   VBUS pin clamps VBUS; check the part's stand-off voltage against a 5.25 V charger.
5. **The analog chains** (round 1 §6.1-6.2, as changed): the THS4521 on 3.3 V with VOCM 1.65 V and now a BAV99 across
   its inputs and 1206 input resistors -- does the BAV99's capacitance (about 1.5 pF) or leakage touch the x10
   setting's bandwidth or offset?  The OPA1612 stages on +5VA / -4V2 (the pump's output through a bead; the rail is
   -4.15 to -4.2 V now, not -4.4: is the headroom at x10 overload still right?).  The DAC's OPA2810 difference
   amplifier at gain 4 with 2.2 kΩ: ±1 V into 50 Ω, ±2 V open; its stability into a cable (`sim/dac_stage.cir`).  The
   TIA (`sim/tia.cir`).  Run `python3 sim/run.py sim/*.cir` and say whether the decks still describe the sheets.
6. **CLK IN** is a TLV3501 comparator since build 26 (the squarer is gone): check its threshold network, hysteresis,
   input protection (the SMA sees anything a student plugs in), the 10 nF coupling, and whether a 10 MHz sine at
   0.5 Vpp makes a clock the ECP5's PLL will lock to.  CLK OUT: 74LVC1G17 through 49.9 Ω.
7. **Ethernet**: RGMII at 3.3 V, 22 Ω series at the PHY, both delays inside the PHY (so the gateware adds none); the
   line side's isolation island with a 1 nF 3 kV capacitor and no 1500 V claim; the magnetics' and jack's pinout; the
   straps.  Nothing changed here since build 26 except the capacitor: check the strap table once more against the
   RTL8211F text.
8. **Power sequencing and configuration** (round 1 §6.5): unchanged, plus 100 nF on PROGRAMN since build 26 -- does it
   slow a programmer's PROGRAMN pulse past what openFPGALoader expects?  The JTAG header's pinout against the FT2232H's
   channel A and an external programmer (the FTDI OFF jumper).
9. **The sheets and the silkscreen as claims.**  Build 28 rewrote the sheets' notes as columns beside their blocks and
   put a legend, limits and jumper meanings on the silkscreen.  Every sentence there is a claim about the circuit:
   check each against the netlist (`docs/SIGNAL_PATHS.md`) and the parts (`gen/parts.py`).  A wrong note on a
   teaching board teaches the wrong thing.  Round 1 found three header pin lists printed in reverse; what is there
   now?
10. **The manufacturing package** (round 1 §6.8), re-read: `mfg/release/` as uploaded.  The CPL now moves four parts
    to JLCPCB's own origin (the Pmod sockets, the USB-Cs: `PLACEMENT_CHECKS.txt`), predicts every unread rotation from
    JLCPCB's drawings, and stores the bottom side mirrored left-right (180 from KiCad's own convention, corrected in
    `mfg/jlc_rotation.py`); the rotation *reading* is Jason's on ordering day, but the *logic* is reviewable:
    `mfg/jlc_rotation.py`, `mfg/footprint_check.py`, `mfg/make_fab.py`.  Also the new marks: are the fiducials where a
    pick-and-place camera can use them, and is the order-number marker where JLCPCB's instructions say it works?

## 4. The standard the board is held to: CLAUDE_PCB.md, restated as checks

The repository's `CLAUDE_PCB.md` is the author's lessons file: every rule in it is something Jason asked for or a
fault a fab, a reviewer or a working board found, on six boards.  Round 1's reviewers never saw it, and about half of
it was written after round 1 (the ECP5 lessons of builds 26-31, and Hans Rosenberg's *Electronic Product Development
Checklist* folded in on 2026-10-07).  Below is every rule that applies to this board, as a question, with the author's
belief in brackets.  **Each "believed" is a claim to test, not a fact.**  Where a rule is not met and the author knows
it, it says so; where you find one not met that the author did not know, that is a finding.

### 4a. The schematic (CLAUDE_PCB.md §4)

* **One-pin nets:** none but deliberate test pads.  [believed: ERC 0; a netlist walk is quick: `build/netlist.net`]
* **One name per rail:** no "VCC" on one sheet and "+5V" on another; print every power net with its pin count and the
  sheets it appears on.  [believed: the rails are +5V, +5VA, +3V3, +3V3_ADC, +3V3_DAC, +3V3_DAC_D, +3V3_DRV, +3V3_ETH,
  +1V1, +2V5, +2V5_AUX, +1V0_PHY, +1V8_FTDI, -4V2, GND; `tools/power_path.py` lists what it finds]
* **One ground net, poured as one plane,** even where a datasheet draws AGND and DGND apart.  [believed: GND only; In1
  solid; the AD9238's and AD9767's AGND/DGND pins all on GND -- check that the datasheets' star-point advice was
  considered, not just ignored]
* **Copied blocks** bring their net names: a repeated name silently merges two nets.  [believed: the two ADC channels
  and two DAC channels are generated tiles with channel-suffixed names; check for an unsuffixed survivor]
* **Inductive loads** each have a freewheel path.  [none on the board: the bucks' inductors are inside their loops]
* **A fuse on every input** that can deliver more than the copper and connectors survive.  [USB: F601; bench: F602
  since build 31; HDMI's +5 V to the monitor: F501, 0.5 A.  Anything else that is an input?  The Pmods' 3.3 V, the RAILS
  header, the EXT R and PD EXT headers, the LED EXT header: what happens when a student feeds 5 V into one?]
* **Polarized parts** the right way round, and every capacitor rated above the worst voltage with margin.  [believed:
  the 1 nF Bob Smith at 3 kV; the 5 V rail's ceramics at 25 V; the 22 nF HDMI coupling at 50 V; read the rest from
  `mfg/release/cost_estimate.csv` part numbers]
* **Coupled windings:** the magnetics' dots and the common-mode chokes wired common-mode.  [the G2406S against its
  drawing in `docs/datasheets/drawings/`]
* **No floating inputs:** unused logic inputs, op-amp sections, ADC channels, FPGA pins.  [believed: every op-amp
  section used; the comparator's unused pins?  The FT2232H's unused channel pins?  The ECP5's unused balls are
  inputs with pull-ups by default]
* **Values:** assert each design equation against the values the netlist carries: the OPA1612 x1/x10 gains, the
  THS4521's 499/499, the DAC's 24.9 Ω loads and 499 Ω / 2.2 kΩ gain, the 49.9 Ω output and tap resistors, the LDOs'
  and bucks' dividers (the sheet prints "+3V3 = 0.6 V x (1 + 15k/3.3k) = 3.33 V" and "+1V1 = 0.6 V x (1 + 10k/12k)";
  the LM27761's divider), the LED currents, the Bob Smith 75 Ω, the PHY's RSET, the USB 27 Ω, the crystal loads
  (27 pF on a 20 pF crystal, known), the ADC's 33 Ω + 22 pF, the TIA's 10 kΩ ‖ 2.2 pF.  [the generator computes
  some; nobody has asserted all of them: do]
* **Ratings** at the worst-case input: resistor power and voltage (the 100 Ω clamp resistor with ±10 V applied -- round
  1's Grok finding; the 1206 input resistors since build 26), diode currents, the LED driver's SS8050.
* **Options where unsure:** a DNP footprint for an alternative, a jumper between two configurations.  [the 50 Ω / hi-Z,
  x1 / x10, source and FTDI OFF jumpers exist; is there a place where a 0 Ω or DNP would have rescued a wrong guess?]
* **Flow and drawing:** signals left to right, power from the top, series parts horizontal, shunts vertical; no label
  that vanishes and reappears except power; notes at the node in 50-70 character columns; limits at every connector;
  "why" boxes; converters drawn as MUX-style trapezoids with the clock from below; dual op amps in dashed boxes with
  the power unit under the gap; one decoupling capacitor per supply pin drawn at that pin; no comment that names a
  part that is not there; no four-way junctions; nothing overlapping (the generator's measured-extent model plus
  `gen/check_sch_text.py` on the exported PDF: 0 complaints).  [read `docs/images/ECP5-2ADC-2DAC_schematic.pdf` as a
  student would]
* **Pins:** every pin of every generated symbol against the datasheet's pin **figure**, not only its table (round 1
  found an FDA's outputs swapped, a mini-HDMI with type-A numbering, a SOT-23-6 EEPROM numbered like a SOIC, a
  bit-reversed DAC port, a TCXO's ground drawn as an enable, a photodiode with pad 1 the anode).  [done for every IC
  in `DESIGN_REVIEW_PROMPT.md` §8; the parts new since build 26 -- TLV3501, the U.FL jacks, the BAV99s at the FDAs, the
  3 kV 1812, F602 -- have had one pair of eyes]
* **Trace every path** with the netlist walk (`docs/SIGNAL_PATHS.md`, `python3 tools/trace_paths.py`).

### 4b. Placement and routing (§5)

* **Floorplan:** connectors and blocks decided first; each signal path through its chips in schematic order; each
  chip's passives hung off its pins; room for labels.  Identical channels laid out identically, ADC A above ADC B and
  DAC 1 above DAC 2.  [`pcb/floorplan.py`; `docs/images/board_3d_top.png`]
* **Orientation follows the schematic:** a horizontal series resistor is horizontal on the board.
  [`build/route_report.json` `series_orientation`]
* **Decoupling at the pins,** straight to a ground via, on the back if closer; **each ground pad its own via** at the
  pad (Rosenberg: shared vias are shared inductance).  [the BGA's 100 nF on the back on pairs of ball vias
  (`bga_caps_on_pairs`); the converters' and PHY's capacitors: count the pads that share a via]
* **Power in pours or wide traces; measure the drop, not the width:** `python3 tools/power_path.py` gives the DC
  resistance from each rail's source to every supply pin along the copper in the file, and `--path NET` prints the
  worst pin's route.  [build 31's worst pins are in §5; the analog rails are planes since build 30]
* **Every rail's width measured by net** against its rule.  [`route_report.json` `rail_widths` / `rail_thin`]
* **Stack-up chosen first** from the fab's table: JLC06161H-7628, F.Cu signals / In1 ground / In2, In3 signals / In4
  power / B.Cu.  Rosenberg's order: ground on L2 with nothing but via holes in it.  [In1 holds no tracks: check
  `grep -c 'layer "In1.Cu"' ECP5-2ADC-2DAC.kicad_pcb` for segments]
* **Layout order:** ground planes, then the critical lines (the analog inputs, the clocks, reset), then the
  high-current paths, then each block, then the links between blocks.  [the build does: planes, BGA escape, rivers,
  hand copper (the converters' inputs and outputs, the line side), ground vias, rail vias, the router]
* **Unshielded inductors** not in line along their axes.  [the two bucks' 4 x 4 mm inductors on the back under the
  POWER section, and the PHY's 1.0 V inductor: `pcb/floorplan.py` lines near `L617`; look at `board_3d_bottom.png`]
* **Aggressors and victims:** the bucks (1.5 MHz), the charge pump (2 MHz), the PHY, the FPGA and the SDRAM are
  aggressors; the ADC front ends, the TIA and the noise resistors are victims.  Distance first.  [the bucks are in the
  far corner from the converters; the pump is under the front ends with a bead on its output since build 26: §3.5]
* **No floating copper.**  [KiCad removes zone islands; the In4 crumb of §2 is via-attached; the new fiducials and
  layer numbers are netless by design]
* **Copper balance:** about the same copper on every layer over the whole board.  [not computed by the build: compute
  each layer's copper fraction by quadrant from the Gerbers (`gerbv`, `pcb-tools`) or from the board file's fills and
  tracks, and say whether a region is bare on every layer]
* **Vias as large as the room allows:** the 0.3/0.15 via only where it must be.  [the board uses 0.3/0.15 for signals
  and 0.45/0.25 for ground returns and rails: `grep -c '(drill 0.15)'` versus `0.25`]
* **Room to assemble:** nothing tighter than JLCPCB's spacing rules (their published minimums for 0402s and for parts
  next to tall ones).  [the BGA's decoupling band and the converter strips are the densest]
* **Paste:** every pad that needs solder has an opening; test pads, fiducials and edge contacts do not; an exposed pad
  gets a window-pane pattern.  [the PHY's 3.6 mm exposed pad has nine paste windows; check the others in the
  `F_Paste` / `B_Paste` Gerbers, and that the fiducials have no paste]
* **Fiducials:** three on the board, as far apart as the board allows.  [since build 31: (25.5, 12.5), (120, 7.5) and
  (146.5, 113) from the top-left corner, front and back; JLCPCB adds its own on the panel rails.  Rosenberg also wants
  three round each fine-pitch part; the author did not add those -- argue if you think the 0.4 mm LQFP-64 and QFN-40
  need them at JLCPCB]
* **Layer markers:** each copper layer's number in copper on that layer at one spot.  [since build 31: "1" to "6" at
  x 70-83, y 1.9 mm, in the top slot band; the inner layers' digits are islands inside the ground planes]
* **Check footprints at 1:1:** print the placed board at 1:1 and lay the connectors on it -- Jason's, after the parts
  arrive; the end plates are drawn from the same placement (`mfg/release/end_panel_*.svg`)
* **DC resistance of high-current paths**, return included.  [5 V at 0.7 A: the +5V plane and the two fuses;
  `power_path` gives the copper part]
* **Clean traces:** no zig-zags, loops or detours round a part's own pins; order reversals get one layer change.  [the
  router is home-grown: look at the copper, not the DRC]
* **No vias in holes;** zones filled in the shipped file (356 filled polygons in build 30; `FABRICATION_NOTES.txt`
  says the count).
* **Pin headers anchor on pin 1;** the board sits in the middle of its page (25 mm margin) and the gerbers, drill and
  CPL agree on the frame (the board's corner at (25, 25) on the page).  [`FABRICATION_NOTES.txt` "Coordinates"]
* **Swappable pins chosen by the board** (river routing with late assignment): the FPGA's balls are assigned where the
  rivers arrive (`pcb/pinswap.py`, `build/pin_swaps.json`), then the schematic and the gateware constraints are
  generated from the result.  [`gateware/` holds the pin proof]
* **A slow control line on the FPGA's far face is the first route to fail:** the AD9238's DCS and PDWN_A come from
  bank 8 and are hand-laid.  [a rev B item; check the hand route does not hug anything it should not:
  `pcb/floorplan.adc_control_lines`]

### 4c. Silkscreen (§6)

* **Identity:** name, "by Jason Gallicchio and Claude", URL, the build date, "rev A" least prominent.
* **Connectors:** big names right beside the connector they name, never between two; every connector that leaves the
  board labelled with what it is for and its limits ("±1V MAX", "3.3V MAX", "5 V IN"); a U.FL tap's name beside it and
  no designator.
* **Header pins:** every pin labelled next to itself, top row above, bottom row below, rotated with the header; the
  RAILS header's rail names under their pins.
* **Jumpers:** what each does, right beside it: the 2-pin jumpers' two states, the 3-pin selectors' two choices beside
  the outer pins with a tick through the centre pin.  [since build 28; `route_report.json` reports labels that landed
  far from their jumper]
* **Test points and taps** labelled with the rail or the reading.
* **Region labels inside the box,** under its top edge; a part and its label in the same box (`silk_label_outside_box`,
  `silk_part_outside_box` in the report).
* **Overlap:** nothing on anything -- silk on silk, silk on pads, silk over the edge, silk on the fiducials' mask
  openings.  **Printable sizes:** 0.8 mm text, 0.15 mm lines.  [DRC runs the silkscreen checks as errors]
* **Pin-1 marks** only where the pad pattern is symmetric and the library prints nothing (the RGB LED); a cathode bar
  on polarised two-pad parts that print none.
* **Prose:** left-justified, broken at sentences, grammatical; **legend paragraphs beside what they explain** (the
  HEADERS paragraph above the POWER box, the USB paragraph under the FTDI, TAPS says 50 Ω).
* **Card slot:** the microSD on the back says which way the contacts face and where the card goes in.
* **Ports named for the student:** "USB PROG" and "USB USER".
* **Judge from KiCad's own rendering** (`kicad-cli pcb export svg`, rasterised), not a quick plot.

### 4d. Mechanical (§7)

* Connectors point out (the 3D render, not the footprint's rotation); faces stand past the board edge by the end
  plate's thickness; USB-C and HDMI sit where their drawings say so a fat plug seats; room for fat plugs beside each
  other; SMAs spread evenly along one edge; mounting holes clear of headers; keep-outs where cards and plugs slide
  in; the enclosure checked against its drawing (the board was 8 mm short in round 1); part heights against the
  floor and the slots; every part with a 3D model.  [`docs/images/board_3d_*.png`, `mfg/release/end_panels.txt`]

### 4e. Manufacturing package (§8)

* **Upload files:** gerbers zip, BOM (one line per LCSC code), CPL JLC-corrected (`_cpl.csv`) and native, assembly
  notes to paste (`FABRICATION_NOTES.txt`), the cost estimate, `PLACEMENT_CHECKS.txt`.
* **Nothing hand-soldered:** `hand_solder_bom.csv` is its header alone; the through-hole parts (six SMAs, the RJ45,
  the DIP switch, the headers as 1x40 / 2x40 strips, the Pmod sockets) are fitted by JLCPCB.
* **DRC** at least as strict as JLCPCB's rules at every severity, 0 errors, schematic parity, zones filled and saved,
  unconnected items counted (`build/drc.json`).
* **CPL rotations:** the bottom-side mirror, then per-part corrections read in a preview or predicted from JLCPCB's
  own drawing (`FOOTPRINT_CHECK.txt`, `PLACEMENT_CHECKS.txt`); **positions moved to JLCPCB's origin** where their
  drawing's zero is not KiCad's (the USB-Cs by 1.3 mm, the Pmod sockets); two-pad polarized parts read by the polarity
  mark.  Jason reads the preview; you may check the logic.
* **Every code checked against its description** (value and package; the ICs by part number; the through-hole parts
  by pitch), **every land pattern fitted to the board** (`FOOTPRINT_CHECK.txt`: HOLE stops the order, PADS and LAND
  want a look -- the four PADS findings are the snapped header strips), **every part in stock with a timestamp**
  (`cost_estimate.csv`; the AD9238 at 21 in stock for 5 needed is the thin one).
* **Order number:** `JLCJLCJLCJLC` on the back silkscreen in the top slot band since build 31; the notes say to choose
  "Remove order number: specify a location".
* **JLCPCB's options:** 6 layers, green, ENIG, 1 oz outer / 0.5 oz inner, epoxy-filled-and-capped vias (via-in-pad under
  the BGA, the back-side decoupling on ball vias), impedance control on JLC06161H-7628, Standard PCBA both sides plus
  through-hole; lead time about two weeks to the US; DDP duty.  [`FABRICATION_NOTES.txt`]
* **Cost estimate** calibrated against the cart on the last two boards (about $5 low each).

### 4f. Bring-up and debuggability (§9)

* **Plug in, don't hold:** labelled test points with ground nearby, U.FL taps on the nodes worth scoping, headers
  that take standard probes.  [four taps: TAP A and TAP B after the second preamps, TAP TIA, TAP -4V2; the RAILS
  header with nine rails and grounds; the JTAG header]
* **A tap's series resistor is its divider and its load:** 49.9 Ω here, so a 50 Ω scope halves the signal and loads the
  node with 100 Ω; the OPA1612 drives it (10 mA at ±1 V against ±55 mA short-circuit).  **Never tap a node whose
  amplitude sets a timing** (the comparator's input): check that no tap does.
* **Read the DNP flag before saying what is fitted.**  [believed: nothing is DNP on this board; check the BOM
  against the sheets for a part drawn but not ordered]
* **Rails at a glance:** an LED per rail (D601-D609), dim so as not to load a quiet rail.
* **Bring-up order** written down: `DESIGN_REVIEW_RESPONSE.md` §4 (bench supply at 0.8 A limit, the nine rail LEDs,
  USB PROG, openFPGALoader, the flash, Ethernet, the SMAs).  [a `HANDBOOK.md` does not exist yet]
* **Firmware is part of the design:** `gateware/` holds a pin proof (yosys + nextpnr with a stub) and a generated
  LiteX platform file, not a working SoC.  The platform file sets `SLEWRATE=FAST` on the bus groups: say which
  outputs should be slow (§4h).

### 4g. Verification gates (§10) -- which the build runs, which you must run

1. ERC clean with the netlist exported [build].  2. Every symbol pin against the datasheet figure [done once; §4a].
3. A path trace of every signal, rail, clock and strap [`docs/SIGNAL_PATHS.md`; the straps and clocks by hand].
4. No overlaps on the sheets, in code, by `pdftotext -bbox`, and by eye [build + you].  5. DRC 0 / 0 on the shipped
file with its zones filled [build].  6. Pads where KiCad puts them (`tools/check_pads_kicad.py`); connectors pointing
out in the 3D render; every part with a 3D model [build + you].  7. Silkscreen: no overlaps, every label in its box,
0.8 mm / 0.15 mm, nothing off the board, jumper labels beside their jumpers [build].  8. Parts: every SMD part with a
code, every code's description matching, every land pattern fitting, stock and price with a timestamp [build].
9. CPL native plus JLC-corrected with `PLACEMENT_CHECKS.txt` [build].  10. Revision and date from the build [build].
11. Every rail's width by net against the rule [build; the drops by `power_path`].  12. `hand_solder_bom.csv` empty
[build].  **13. From the netlist: no one-pin nets, the power-net alias list, inductive loads' freewheel paths, fused
inputs, polarized parts listed for the preview [not in the build: run it].  14. The design equations asserted against
the netlist's values [not in the build: do the arithmetic].  15. Fiducials and layer markers [build 31]; paste
openings on exactly the pads that need them [check the Gerbers].  16. Copper balance by quadrant and current capacity
of each high-current net's narrowest track, with its drop at full current, return included [not in the build:
compute].  17. The upload-readiness pass [§2 is the author's; redo it].**

### 4h. Components, fast digital, RF, power (§12-§15; written for boards to come, applied here)

* **Capacitors:** C0G where a value sets a frequency or sits in the signal path.  [by part number in
  `cost_estimate.csv`: the 22 pF at the ADC inputs, the 2.2 pF feedback and TIA capacitors, the 18 / 27 pF crystal
  loads are C0G (0402CG...); the 100 nF decoupling X7R; the 10 µF / 22 µF / 4.7 µF / 1 µF X5R at 25 V or 16 V -- an
  X5R loses capacitance with DC bias: at 5 V on a 25 V part about 10-15 %, at 3.3 V on a 16 V 0603 more; does any
  regulator's stability or any bead's resonance (`sim/pdn_bead.cir`, 10 µF assumed) depend on the nominal value?
  The 10 nF CLK IN coupling and the 22 nF HDMI coupling are X7R: fine for coupling, say if not]
* **Resistors:** dissipation and voltage at the worst case (§4a); thin film where 1/f noise matters (the OPA1612
  stages' feedback at x10?).
* **Inductors:** the bucks' 2.2 µH (IND-SMD 4 x 4, C279948) saturation current against the TLV62569's peak; the PHY's
  1.0 V inductor the same part since round 1's finding.
* **Semiconductors:** junction temperatures at the highest ambient inside a closed extrusion (§3.1 for the LDO; the
  SS8050 LED driver at 48 mA; the Schottky).
* **Edges set the bandwidth; slowest slew that meets timing:** the ECP5's outputs to the SDRAM (100 MHz), the DAC
  (up to 125 MS/s), the ADC clock, RGMII (125 MHz DDR, 22 Ω series) and HDMI.  [the LPF/platform file sets FAST on the
  bus groups]
* **A trace is a transmission line** past about a sixth of the rise time: with 1 ns edges anything over 25 mm.  The
  SDRAM bus, the ADC and DAC data rivers and the RGMII river are 20-60 mm: series termination at the source (RGMII
  has 22 Ω; the SDRAM and the converter buses have none -- the ECP5's drive strength and slew are the knobs).
  **Say whether the converter buses and the SDRAM need resistors in rev A** (the TX resistors at the FPGA end of the
  RGMII lines and a damping leg on the converter clocks are rev B items; argue if they should not wait).
* **Impedance from the fab:** 50 Ω single-ended (the SMA runs, 0.35 mm on F.Cu over In1) and 100 Ω differential
  (the MDI pairs); the HDMI and USB pairs are routed as pairs without an impedance claim.
* **Return current under the trace:** no fast line across a split (§3.2 is the list); a ground via within about 1 mm of
  every layer change (the build's `return_vias`: a ground via within 1.5 mm of every signal via); a stitching capacitor
  where the reference changes from ground to power.
* **Differential pairs** matched within 0.1-0.15 mm (HDMI, USB, MDI: round 1's CopilotSDK measured the HDMI pairs; redo
  for build 31, the jacks moved in build 26).
* **Groups matched** to the interface's budget: the SDRAM's data to its clock, the ADC bus to its clock (the ADC's own
  DCS mode), the DAC's data to its WRT/CLK.  [the rivers are unmatched by construction; the budgets at 100 MHz
  are forgiving -- compute them]
* **Crosstalk:** long parallel runs at least three widths apart; the rivers run at the class pitch.
* **Via stubs** matter only above 10 Gb/s: not here.
* **Power integrity:** the FPGA's PDN (the +1V1 patch on In4 with the core's 100 nF on the back under the BGA; the
  bulk at the buck), the converters' AVDD planes; mixed capacitor values anti-resonate: check the combined impedance
  rather than the list.
* **Clocks:** the TCXO to the FPGA, the Si5351's three outputs, the converter clocks from the FPGA, CLK OUT: inner
  layers where possible, series termination at the source, one load per output, nothing under the crystal.  Clock
  jitter caps the ADC's SNR at -20 log10(2π f_in t_jitter): what does a 65 MHz clock from an ECP5 PLL give at 10 MHz
  input?
* **EMC:** every cable is an antenna; fast lines away from connectors and edges; filtering at what leaves the board;
  stitching along the ground pours' edges.
* **RF (§14):** the SMA launches (50 Ω microstrip, the plane under the SMA's wide centre pad), the U.FL launches, no
  floating copper.  Round 1 accepted the SMA feeds at 0.35 mm; look at the launch geometry once.
* **Power (§15):** width for current (IPC-2221: 1 A needs 0.30 mm at 10 °C rise in 1 oz outer copper, inner layers 2.6
  times the area; 0.5 oz inner here); vias about 1 A each at 0.3 mm (the +5V input's vias into the In4 corridor:
  count them); **hot-plug ringing** (§3.4); **input protection** (reverse polarity: the Schottky on the bench header,
  nothing on USB -- USB cannot be reversed; overcurrent: the fuses; a TVS: the USBLC6 on VBUS); switching converters
  laid out as their datasheets draw (the TLV62569's hot loop, the LM27761's flying capacitor; `pcb/floorplan.py`
  `analog_power` and the buck cluster); **mains stays off the board** (it does).
* **Heat where a hand can reach** (§16, for a teaching board): the extrusion's surface over the LDOs and the bucks
  stays below about 45 °C?  [3 W in a 125 x 51 x 160 mm aluminium box: estimate]

## 5. Tools: where they are and how to run them

Everything is generated and in the tree; nothing has to be built to review it.  The repository is `OpticsPCBs`, this
project is its `ECP5-2ADC-2DAC/` directory; run the commands from there unless noted, with the output into your
directory.  `KICAD` is the AppImage (`~/.local/bin/kicad-10.0.6-x86_64.AppImage` on this machine; `kicad-cli` is its
subcommand and is not on `PATH`; `KICAD_APPIMAGE` overrides the path for the scripts that need it).

```bash
D=design_review_<YourName>2; mkdir -p $D
KICAD=~/.local/bin/kicad-10.0.6-x86_64.AppImage
# KiCad's own checks and pictures (read the shipped file; NO --save-board, NO --refill-zones: the copper the Gerbers came from)
$KICAD kicad-cli pcb drc --severity-all --format json -o $D/drc.json ECP5-2ADC-2DAC.kicad_pcb
$KICAD kicad-cli sch erc --severity-all --format json -o $D/erc.json ECP5-2ADC-2DAC.kicad_sch
$KICAD kicad-cli pcb render --side top -o $D/top.png ECP5-2ADC-2DAC.kicad_pcb        # --side bottom too
$KICAD kicad-cli pcb export svg --layers F.Cu,F.SilkS,F.Mask,Edge.Cuts --page-size-mode 0 -o $D/front.svg ECP5-2ADC-2DAC.kicad_pcb
$KICAD kicad-cli pcb export svg --layers In4.Cu,Edge.Cuts -o $D/in4.svg ECP5-2ADC-2DAC.kicad_pcb    # the power planes
$KICAD kicad-cli sch export pdf -o $D/schematic.pdf ECP5-2ADC-2DAC.kicad_sch        # or read docs/images/ECP5-2ADC-2DAC_schematic.pdf
# the project's own readers (they print; redirect)
python3 tools/trace_paths.py > $D/SIGNAL_PATHS.md               # every signal path through the netlist (= docs/SIGNAL_PATHS.md)
python3 tools/power_path.py > $D/power_path.txt                 # DC resistance, source to every supply pin, per rail and chip
python3 tools/power_path.py --path +3V3_ADC                      # ... and the worst pin's route for one net (any directory; a .kicad_pcb path may be given)
python3 gen/check_sch_text.py docs/images/ECP5-2ADC-2DAC_schematic.pdf $D/sch_text.txt   # overlapping or off-page words in the PDF (needs pdftotext)
python3 sim/run.py sim/adc_frontend.cir sim/dac_stage.cir sim/tia.cir sim/led_driver.cir sim/pdn_bead.cir   # ngspice via KiCad's library
python3 mfg/footprint_check.py mfg/release/ECP5-2ADC-2DAC_bom.csv > $D/footprint_check.txt   # ordered land pattern vs the board (cached JLCPCB data)
python3 mfg/jlc_rotation.py > $D/jlc_rotation.txt               # the CPL rotation rule against the preview readings it came from
python3 tools/jlc_query.py "AD9238BSTZ-65" "TPS7A2033PDBVR"     # stock, price, description of any part (JLCPCB's API; cached)
python3 tools/check_pads_kicad.py > $D/check_pads_kicad.txt     # KiCad's pcbnew vs the placer's pad positions (needs the AppImage)
python3 pcb/rotscan.py > $D/rotscan.txt                         # which way each bus chip should face, by wire length
pdftotext -layout datasheets/<file>.pdf $D/<file>.txt           # the PDFs are in the working tree (not git); docs/datasheets/txt/ has them all as text
```

* `README.md` -- the decisions, the board, every check ("Checks that are not DRC"), the rev B list.  **Start here.**
* `DESIGN_REVIEW_PROMPT.md` -- round 1's brief: §1-§5 what the board is, §6 what was attacked, §7-§8 what was known
  and verified then, §11 the round-1 reviews in one line each.
* `DESIGN_REVIEW_RESPONSE.md` -- the author's own review of build 25 and §5 the reconciliation into builds 26-27, with
  the build 28 log.
* `CLAUDE_CODE_CHAT.md` -- every prompt and response, with every mistake; Prompts 26-31 are builds 28-31.
* `gen/fpga.py` (the pin plan), `gen/parts.py` (every part, its code and why), `gen/sheet_*.py` (the circuits with the
  notes printed on the sheets), `gen/rules.py` (the DRC rules and net classes).
* `pcb/floorplan.py` (where everything is and why, the hand copper), `pcb/build_pcb.py` (planes, vias, the router's
  rules, the silkscreen, the marks), `pcb/river.py` (the bus rivers), `pcb/fatten.py` (the rails' widening),
  `pcb/router.py`.
* `docs/SIGNAL_PATHS.md`; `docs/images/` (schematic PDF and PNGs, copper plots, 3D renders).
* `sim/` -- the SPICE decks: the ADC front end, the DAC stage, the TIA, the LED driver, the bead.
* `mfg/release/` -- Gerbers (zip and folder), BOM, CPL (JLC and native), assembly drawings, `FABRICATION_NOTES.txt`,
  `PLACEMENT_CHECKS.txt`, `FOOTPRINT_CHECK.txt`, `cost_estimate.csv`, `hand_solder_bom.csv`, the end plates.
* `build/` -- mostly ignored by git, but the small results a reviewer needs are committed (`netlist.net`, `drc.json`,
  `erc.json`, `route_report.json`, `placement.json`, `lcsc.json`, `pin_swaps.json`, `bus_plan.json`).  In the shared
  working tree it also holds `build/scratch/final<N>.*`, the board and reports of earlier numbered builds (25, 26,
  27, 28, 30), for a diff against what you have in front of you.
* The git history: `git log --format='%h %ad %s' --date=short -- .` from the project directory lists the builds;
  `git diff c3256ec..HEAD -- gen/sheet_power.py` shows one sheet's changes since round 1.

## 6. Known open items (do not spend time rediscovering these)

* The FT2232H's 12 MHz crystal is a 20 pF part loaded with 27 pF capacitors: about +30 ppm, inside USB's budget; 33 pF
  would be right (round 1).
* The eight user LEDs run at about 0.5 mA: dim.  The RGB LED and the power-good LEDs are deliberately dim.
* About 150 small parts' designators are on the Fab layer, not the silkscreen; the assembly file carries every
  position.
* Two ground return vias north-west of the FPGA touch the In1 plane only; the In4 ground crumb of §2.
* `gateware/` holds a pin proof and a generated platform file, not a working SoC.  The TCXO drives the FPGA directly,
  so the board boots with no software for the Si5351.  Both RGMII delays are inside the PHY (build 26): the gateware's
  RGMII PHY is configured with none.
* The CPL rotation reading is Jason's on ordering day; the bottom side's convention is predicted and not yet confirmed
  in a preview.
* Left as they were after round 1, with the reasoning in the response's section 5: the ADC input pair's 9-10 mm length
  mismatch with the 22 pF capacitors 10 mm from the pins; DAC_CLK1 / DAC_WRT1 on In3 crossing the +1V1 patch.
* The BAV99 across each THS4521's inputs is insurance against a failure mode no behavioural model shows.
* The AD9238's DCS and PDWN_A lines are hand-laid from bank 8 (a rev B puts them on the west face).
* Rev B (`README.md`): the FT601 / USB 3 streaming path, LPF bypass jumpers, the 45F/85F, DDR3, the RGMII TX
  resistors at the FPGA end, a damping leg on the converter clocks.  Jason deferred full-rate bidirectional streaming
  to rev B on 2026-10-07; do not reopen it.
* The "PD EXT" header's label stands beside its header, the JUMPERS legend is under the LEDs: placements the author
  accepted because the occupancy map had nothing better.

## 7. What would be most useful back

* **A verdict in one paragraph: order it, or not, and the one thing that decides it.**
* The findings table, ranked by the cost of being wrong, each with what you ran or read to confirm it.
* Your numbers for §3.1 (the LDO), §3.2 (which seams matter), §3.4 (the input), §3.6 (the comparator) and §4h (the
  SDRAM and converter buses' need for termination, the clock jitter) -- the arithmetic, not the adjective.
* The gates the build does not run (§4g items 13, 14, 16, 17), run by you, with their lists.
* Anything in the schematic or the silkscreen that is simply wrong.  It has been checked hard by people who believed
  it; the notes are claims.
* Which round-1 dispositions (`DESIGN_REVIEW_RESPONSE.md` §5) you reject, with the datasheet number that rejects them.
* What all the reviewers, round 1 and 2, missed.

## 8. Reviews received so far

Round 1 (build 25, 2026-10-04), one line each; the directories hold the reports and what each measured or ran:

| Directory | Reviewer | Verdict in one line |
|---|---|---|
| `design_review_CopilotSDK/` | CopilotSDK | Do not order unchanged: C4951 is a general-purpose 2 kV MLCC, not a safety capacitor; the DAC stage has no slew margin at 13 MHz; CLK IN is a squarer, not a reference input; RGMII TX delay has no gateware; USB-C current is not negotiated.  ADC bias, Master-SPI order, SDRAM/HDMI skew, ERC/DRC and the fab checks pass. |
| `design_review_Gemini_3.8_Flash/` | Gemini 3.8 Flash | Twelve findings: THS4521 overdrive 2.27 V across its inputs when a preamp saturates; ADC input traces mismatched; DAC_CLK1/WRT1 cross the In4 split; USB-C recessed behind the end plate; no filter on -4.4 V; DAC difference amp AC-unbalanced; squarer on the digital 3.3 V; RGMII skew; C4951 1206 gap; narrow SOIC-8 rotation; the USB port cannot be a host. |
| `design_review_Grok4.7/` | Grok 4.7 | Do not start over, do not hold the fab: the chains work; fix the claims.  -4.4 V shared 2 MHz spur under the noise lab; silkscreen ±1 V / ±2 V vs simulated ±0.91 / ±1.82 V; the power sheet's "no order requirement" sentence wrong; isolation gap is bench clearance, not 1500 V; RGMII TX delay missing in gateware; a ±10 V source into the high-Z input opens the 100 Ω shunt.  Disputes Gemini on the THS4521 overdrive. |
| `design_review_Claude-ultrareview/` | Claude Code's cloud review of PR #2 | A code review: six Python findings, two real (a clone could not build; the SMA feeds routed at 0.15 mm), four nits. |
| `DESIGN_REVIEW_RESPONSE.md` | the author | Findings 1-11, 4b, 4c with dispositions, fixed in builds 21-25; §5 reconciles the five reviews into builds 26-27; §4 is what only Jason can check; the build 28 log. |

Round 2 goes into `design_review_CopilotSDK2/`, `design_review_Gemini_3.8_Flash2/`, `design_review_Grok4.7_2/` and
`design_review_<NewReviewer>2/`; a cloud review's report is filed by the author as `design_review_Claude-ultrareview2/`.
Where reviewers disagree, the useful answer is the one with the datasheet numbers in it.
