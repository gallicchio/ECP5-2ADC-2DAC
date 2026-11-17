# ECP5-2ADC-2DAC rev A: whole-board pin audit (2026-11-16)

**Why.** Board A's USB programming port was dead on arrival (`REVB.md` rows 12 and 13, found on the bench that
morning). This audit ran the two checks that `CLAUDE_PCB.md` now requires (its top block, and section 10 gate
2a-2c) over the **whole** board, as scripts. The goal was to find any other fault of the same kind before more lab
time went in. The board audited is the ordered build: `build/netlist.net` of 2026-10-10, from the same commit as
the schematics.

**Result: no new fault.** The scripts find exactly the two known FT2232H faults (REVB 12 and 13), which shows they
can see this kind of error, and nothing else.

## Red flags

| severity | finding | evidence | on board A | workaround / rework | rev B |
|---|---|---|---|---|---|
| **BLOCKER** (known, REVB 12) | The FT2232H's VPHY (pin 4) and VPLL (pin 9) get **1.8 V** from VREGOUT through FB6241. They need **3.0-3.6 V**. | Netlist: `U502.4`/`U502.9` on `Net-(U502-VPHY)`, which reaches `+1V8_FTDI` (U502.49 VREGOUT) through FB6241. Data sheet: `DS_FT2232H.txt:3319` "VPHY, VPLL PHY Operating Supply Voltage 3.0 3.3 3.6 V"; `:675` and `:679` "+3.3V input". Measured on board A: 1.78 V at C6241. | USB PROG never attaches, so there is no JTAG and no UART. | `figs/rework_ftdi.png` job 1: lift FB6241's +1V8 end and wire it to R6222's +3V3 end. | FB6241's supply end on +3V3. |
| **BLOCKER** (known, REVB 13) | USB PROG's **D+ goes to the FT2232H's DM (pin 7) and D- to DP (pin 8)**. | Netlist: `J501.A6/B6` (D+), then `U501.3`, the USBLC6's internal I/O2 pairing, then `U501.4`, then `U502.7` (DM_7). Data sheet: `DS_FT2232H.txt:704-705` "7 DM", "8 DP". Generator: `gen/sheet_usb.py:74` `dmp, dpp = u.pin("8"), u.pin("7")`. The USBLC6 pairing is from `datasheets/USBLC6-2SC6_C2827654.pdf` p.1 (image): I/O1 is pins 1 and 6, I/O2 is pins 3 and 4. | USB PROG cannot enumerate, even with VPHY fixed. | No board work: a USB-A-to-C cable with D+ and D- swapped, labelled (job 2). | Swap the two pin numbers. |
| INFO | **The FT2232H data sheet contradicts itself**, which explains how REVB 12 arose: its prose says "The +1.8V LDO regulator generates the +1.8 volts for the core **and the USB transceiver cell**". | Prose: `DS_FT2232H.txt:1903-1907`. Against it: the pin table (`:675`, `:679`), the DC characteristics (`:3319`) and every reference schematic (`:3520` "regulated down to +3.3V ... to supply the VCCIO, VPLL, VPHY and VREGIN"). | - | - | Lesson: where a data sheet's prose and its pin table or DC tables disagree, the tables win, and the disagreement is flagged. |
| INFO | **Each Ethernet pair is crossed on both sides of T401.** The PHY's MDIn_P goes to TDk-, and the RJ45's + pin goes to MXk-. | `T401` pins against `drawings/g2406-1.png`: "Polarity: 2-23, 5-20, 8-17, 11-14 In-Phase". | Not a fault: the PHY's P still reaches the RJ45's + pin on all four pairs, and 1000BASE-T corrects pair polarity anyway. The green link LED blinked on board A. | - | Route the pairs straight, for a reader's sake. |
| INFO | **HDMI HPD at the FPGA ball K13** is 3.34-3.38 V at most: the sink's 5.25-5.3 V comes through R6412 4.7k (plus about 1k in the sink), with R6413 10k to ground. | `check_pairs.py`, level rows. | That is above VCCIO (3.33 V) by a few mV and under the ECP5's 3.63 V absolute maximum (`LFE5U-25F-6BG256C_C1521614.txt:3033`). | - | Optional: 4.7k/6.8k for margin. |
| LOW (REVB 11) | With the bench supply on thin leads, +5V was 4.22 V. The HDMI +5V pin (J503.18 through F501) wants 4.8-5.3 V (MEMORY: HDMI 1.4a). | Board A, 2026-11-16 (`BRINGUP_LOG.md` 1.3). | Every regulator stays inside its input range at 4.2 V. A monitor might not read the EDID. | Thick leads; or run from USB PROG (5.05 V). | REVB 11. |

Nothing else failed. Rows whose source is MEMORY rather than a data sheet on disk:
- 4 PCA9306 rows: there is no PCA9306 data sheet in the repository.
- 2 USBLC6 VBUS rows: the 5.5 V limit (the PDF says only "Operating voltage 5V").
- 3 rails: both USB VBUS nets (4.40-5.25 V), and the PCA9306's VREF2 node.

## Method

Every range is from the data sheet's recommended operating conditions, unless the row says otherwise, and each
entry quotes its line. The scripts read the netlist and fail on any violation.

**`tools/pin_tables.py`** holds the tables:
- **Every IC's supply, ground, reference and strap pins, by pin number.** The ECP5's 256 balls are taken from
  Lattice's own pinout CSV, `datasheets/FPGA-SC-02033-2-0-ECP5U-25-Pinout.csv`.
- **Every rail's voltage,** derived from its source. Where board A has a reading (+3V3 3.331, +1V1 1.106, +2V5 2.508,
  +3V3_ADC 3.296, +3V3_DAC 3.293, +1V0_PHY 1.011, -4V2 -4.115 V), the range is that reading +-1 %. +5V is the
  measured 4.20 V up to USB's 5.25 V.
- **The pairs**, and the ESD array's internal pin pairing.

**`tools/check_power_pins.py`** (gate 2a):
- Every IC pin that is a supply by type or name, and every IC pin sitting on a rail, must be in its part's table.
  The rail it is on must lie inside the pin's range. A rail reached through a bead, an inductor or a resistor of
  10 ohm or less counts as that rail.
- The op-amps' and comparator's V+ - V- span is checked against the data sheet.
- Each internal regulator's output may feed only the pins its data sheet names: FT2232H VREGOUT feeds only VCORE;
  RTL8211F REG_OUT feeds only DVDD10 and AVDD10.
- The RTL8211F's CFG_EXT and CFG_LDO straps must select 3.3 V I/O on DVDD_RG.

**`tools/check_pairs.py`** (gates 2b-2c):
- **Pair walks.** Each pair is walked from connector to chip through resistors, beads, the listed series capacitors
  and the USBLC6's pass-through pins. It fails unless the + reaches the + and not the -.
- **Pins against the LPF.** Every IC pin that reaches an FPGA ball through 1 kohm or less is compared, by its
  function, with the LPF's port name at that ball:
  - bus bits (TXD2 against `eth_txd[2]`, DQ7 against `sdram_dq[7]`, D5_B against `adc_b_d[5]`);
  - TX/RX and TDI/TDO crossings, and the FT2232H's MPSSE roles;
  - the sysCONFIG and JTAG balls, against Lattice's CSV.
- **Analog signs.** For ADC A and B, DAC 1 and 2 and CLK IN, the stages are traced through the netlist's own parts:
  which input each signal enters, the feedback and gain resistors, and the balance of the FDA and the difference
  amplifiers. The resulting sign is stated.
- **Logic levels.** Each chip's I/O rail is checked against the FPGA banks' (all 13 VCCIO balls are +3V3, and all
  199 LPF ports are LVCMOS33). Pull-ups and external signals into FPGA balls are checked against 3.63 V, with
  divider arithmetic.

**By reading:** the custom (`ours:`) symbols' pin functions against the data sheets' pin tables, because the scripts
trust the symbols' function names:
- RTL8211F: 41 of 41, by script.
- AD9238 (all 64), AD9767 (all 48), THS4521, TLV3501, 93LC56B, TCXO and G2406S: by eye.

The FT2232H's symbol is KiCad's own and is right; the generator chose the wrong pin by number.

**The same tables also run on the shared engine,** `~/OpticsPCBs/tools/pin_audit/pin_audit.py`, through
`boards/ECP5-2ADC-2DAC.py`.

## What was covered

**`check_power_pins.py`: 28 ICs (27 U parts and the TCXO X301), 196 table pins, 216 rows, 212 pass, 4 FAIL** (all
U502):
- the 196 pins include the ECP5's 51 supply, ground and CFG balls;
- 8 span rows;
- 7 regulator-consumer rows (2 of them FAIL: VPHY and VPLL on VREGOUT);
- 3 strap rows.

**`check_pairs.py`:**

| check | count | result |
|---|---|---|
| pair lines | 39 | 4 FAIL, all USB PROG |
| chip-to-FPGA lines against the LPF | 145 | all pass |
| dedicated balls against Lattice's CSV | 16 | all pass |
| analog sign chains | 5 | all + |
| level rows | 13 | all pass |

The 39 pair lines cover:
- USB PROG: 4;
- USB USER: 2;
- HDMI TMDS: 8;
- ADC VIN+/-: 4;
- DAC IOUTA/IOUTB: 4;
- CLK IN: 1;
- Ethernet, PHY and RJ45 sides of T401: 16.

The 145 chip-to-FPGA lines cover RGMII, MDIO, the ADC and DAC buses, SDRAM, flash, JTAG, UART, I2C, the clocks and
the DDC.

The five sign chains are ADC A, ADC B, DAC 1, DAC 2 and CLK IN, all non-inverting. That agrees with the bring-up's
expected transfer, ADC code = 2048 + (DAC - 8192)/4.

**Shared engine:** 193 power rows with 2 FAIL (U502.4, U502.9), and 39 pair lines with 4 FAIL (USB PROG).
It has 3 fewer rows than `check_power_pins.py` because it drops the op-amp inputs tied to ground.

## What was not checked, and why

- **Connector land patterns against the connectors' drawings** (mini-HDMI A71-05H4, microSD, the RJ45, USB4105).
  Their symbols follow the standards' pin numbering, but the footprints' pad numbering was not re-read against the
  makers' drawings, and only the SMA and RJ45 drawings are on disk.
  - Partial evidence from board A: USB-C power arrives through both connectors' VBUS (the board ran from USB PROG),
    and the Ethernet link LED blinks.
- **The W9825G6KH symbol** was checked against the JEDEC 54-pin SDRAM pinout from memory, not its data sheet's
  figure, which is an image. **The PCA9306** has no data sheet on disk; its pins are from memory.
- **Discrete pinouts** were not re-read against the data sheets: the SS8050 and AO3401A (SOT-23), the SS34 and
  1N4148W, and the BAV99s.
  - The parts that board A has exercised work as wired: Q602 passes USB PROG's 5 V (5.047 V on +5V, so the FET is
    on, not its body diode); Q601 lights D609; D601 drops 0.30 V forward; all regulators make their rails.
  - The BAV99 clamps, D101 and D102, are oriented to stay reverse-biased: anode 1 on -4V2, cathode 2 on +5VA, the
    common pin on the signal.
- **Out of scope:** timing, signal integrity and analog performance.

## Where things are

| what | where |
|---|---|
| Tables | `ECP5-2ADC-2DAC/tools/pin_tables.py`, read through `tools/audit_netlist.py` |
| Scripts | `tools/check_power_pins.py`, `tools/check_pairs.py` (`-v` prints every row; exit 1 on FAIL) |
| Full outputs | `bringup/pin_audit_power.out`, `bringup/pin_audit_pairs.out` |
| Shared-engine config and output | `~/OpticsPCBs/tools/pin_audit/boards/ECP5-2ADC-2DAC.py` and `.out` |
| Rework for REVB 12 and 13 | `bringup/figs/rework_ftdi.png`; `REVB.md`'s first block |

## Check 3: connectors against their drawings (2026-11-16)

**What.**
- Every connector on rev A, worked out from the placed pads of the ordered board file (`ECP5-2ADC-2DAC.kicad_pcb`,
  commit 5f197ee, 2026-10-10), not from the netlist. The brief is `~/OpticsPCBs/tools/pin_audit/BRIEF_CONNECTORS.md`.
- Script: `~/OpticsPCBs/tools/pin_audit/connectors/ECP5-2ADC-2DAC.py`; output beside it as `ECP5-2ADC-2DAC.out`;
  shared helpers in `connectors/_ECP5_2ADC_2DAC_lib.py`.
- **Parser check (section 0 of the output).** Every computed pad position was compared with the routed track ends.
  Same-net track ends sit on 9-13 of the netted pads of each connector, and on 20 of 24 of T401's. T401 and J504 are
  on B.Cu, which shows that KiCad's B.Cu mirror and the rotations are handled.
- **The Pmod truth.** Digilent Pmod Interface Specification 1.3.1
  (`~/OpticsPCBs/IcepiZeroADCDAC/datasheets/pmod-interface-specification-1_3_1.pdf`), rendered and read:
  - p.4, fig. 2 ("Spec B"): a module's plug on its west edge, top view. Pin 1 is at the north. The 1-6 column is
    0.25" from the edge and the 7-12 column 0.15".
  - p.5, fig. 5 detail: a host socket on its east edge, top view. Pin 1 is at the north. The 1-6 column is 0.50"
    from the edge and the 7-12 column 0.40".
  - In both figures, pins 1-6 are the row farther from the edge. On a right-angle part that row is the upper one,
    because its leads bend farther back. So when two spec parts mate, upper row meets upper row and pin 1 meets pin 1.
- **Jason's decision (2026-11-16).** "The ECP5 and PMOD boards need to be fixed in their REVBs to match the standard.
  I will mark the existing boards as special and wrong and not to be used with standard PMODs." So the rev A sockets
  are reported here as **non-standard and marked**: they mate only with our rev A plugs. Every rev B goes to the spec.

### Red flags

| severity | connector | finding | evidence (pads; drawing) | what it does on a built board | workaround / fix |
|---|---|---|---|---|---|
| **HIGH** (known, REVB 14; **re-derived and agreed**; no longer *uncertain*) | J303 PMOD A, J304 PMOD B | Both sockets are **mirrored end to end** against the spec's fig. 5. The rows are right: Pmod 1-6 is the upper row. The ends are swapped: pin 1 is at the south and +3V3 at the north. | **Part and placement.** KiCad `PinSocket_2x06_P2.54mm_Horizontal` (LCSC C22373932, HC-PM254-8.5H-2x6PW) on F.Cu, rotated 180°. The body faces east and ends 0.03 mm inside the east edge.<br>**Rows.** The odd pads are at x = 170.40. They are the row farther from the opening, so they are the upper row. By the generator's rule (pin k on pad 2k-1) they carry Pmod 1-6. LCSC's own land pattern for C22373932 also puts the body on the side of KiCad's even pads.<br>**Ends.** J303 pad 1 (pmoda[0], through R5601 33R) is at y = 133.00, the south end. Pads 11/12 (+3V3) are at y = 120.30, the north end. Fig. 5 puts pin 1 at the north. J304 is the same, 22.86 mm north. | **A bought 12-pin Pmod plugged in upright** (8 faults per socket):<br>- the board's +3V3 lands on the module's IO1 and IO7;<br>- the board's GND lands on its IO2 and IO8;<br>- the module's GND (pins 5/11) lands on pmoda[1]/[5];<br>- the module's VCC (pins 6/12) lands on pmoda[0]/[4], through 33 ohm.<br>**A bought 6-pin module** (4 faults): the same pattern.<br>**Our AMOD and RF-MOD rev A plugs:** all eight mate pin for pin, with 0 faults. | **Rev A** (marked non-standard):<br>- Use only our rev A plugs.<br>- A bought module goes in **turned over** (component side down): 0 faults, and the power lands right. The module's IO1-4 then sit on pmoda[4..7] and its IO7-10 on pmoda[0..3], in the same order. This confirms REVB 14's workaround.<br>- A 6-pin module turned over goes into the lower row, with IO1-4 on pmoda[4..7].<br>- Check the enclosure's end plate before turning a module over.<br>**Rev B:** put pin k on pad 13-2k and pin k+6 on pad 14-2k. The script checks this assignment in the same footprint and placement and finds it **as the spec**. |
| LOW | J504 microSD | **The socket's shell floats.** The symbol's `SH` pin is on GND in the netlist, but the TF-01A footprint has no pad named "SH". Pads 10-13, the four shell tabs (GND in LCSC's own symbol for C91145), carry no net on the board. | Board file: J504 pads 10-13 have no net. Netlist: `J504.SH` is on GND. | No electrical effect. The card cage is not grounded, so ESD on it has no path to ground. | Rev B: give pads 10-13 GND (rename the symbol pin, or map SH to them). |
| INFO (known, REVB 11) | J601 5 V IN | The nearest silk label to pad 2 (+5V, toward D601) is "GND", 5.6 mm away. "5 V IN" sits level with pad 1, which is GND. | Silk positions against the pads (output section 7). | Already misled the bench once. | REVB 11 (labels). |
| INFO (known, REVB 10) | J602 RAILS | Odd pads carry the rails and even pads GND. The names sit by the GND row. | Pads 1-18, output section 7. | | REVB 10 (accepted). |
| INFO, *uncertain* | J503 mini HDMI | **The pinout is HDMI type C and right pad by pad.** Pad 1 is the D2 shield and pad 18 is +5V. The handedness (which end pad 1 is, seen from the opening) **agrees with the Icepi Zero's own footprint** for the same XKB A71-05H4-111N1. That footprint was drawn independently and is used on a shipping product. **The XKB drawing itself is not on disk.** LCSC refuses scripted downloads, and the web fetch returned only the page title. | **Pads:** 1-19 run in one row at 0.4 mm pitch. Pad 1 is at the north, and the opening faces east. **Type-C pin list (MEMORY):** HDMI 1.4. LCSC's symbol for C2682170 (`library/easyeda`) agrees pin by pin. | HDMI has not yet been plugged (visit 3). If the footprint were reversed, the board's +5V would go into the sink's D2+. | **Settle it before visit 3's HDMI step.** Board unpowered, a mini-HDMI-to-HDMI cable in J503, then on the HDMI-A end:<br>- pin 18 to the board side of F501 should read about 0 ohm;<br>- pin 17 to GND should read about 0 ohm.<br>If the connector were reversed, both would read open, because they would land on AC-coupled TMDS pads. |
| INFO, *uncertain* | J504 microSD, J401 RJ45 | **Pinouts are right by function:**<br>- microSD 1 DAT2 ... 4 VDD, 5 CLK, 6 VSS ... 8 DAT1, in a monotonic 1.1 mm row;<br>- RJ45: T568 pairs 1-2 A, 3-6 B, 4-5 C, 7-8 D, + on the lower pin of each pair.<br>**Not checked:** which end is pin 1 against the Hroparts and Ckmtw drawings. Neither drawing is on disk. | microSD: SD spec (MEMORY), and LCSC's symbol agrees. RJ45: pad nets in output section 6. | **RJ45:** board A's Ethernet gave a blinking link LED at the lab switch. That fits a right-handed jack: a mirrored one would move the 10/100 pairs to pins 7-8 and 4-5. **microSD:** settles when visit 1B's SD test reads the card. | None needed if those pass. |

**Nothing new at BLOCKER, HIGH or MEDIUM.** The one HIGH is REVB 14, which this check confirms from the pads. I agree
with REVB 14's direction, its workaround and its rev B rule.

### What meets what (Pmod)

These are computed from both parts' placed pads in one frame. The module's board is turned so that its plug faces
the socket, and the two faces are centred. "Over" means the module is turned component side down.

| host | module | upright | turned over |
|---|---|---|---|
| ECP5 J303/J304 (rev A, marked) | a spec 12-pin module (fig. 2: Digilent and others) | **8 faults**: +3V3 on IO1/IO7, GND on IO2/IO8, module GND/VCC on pmoda[0,1,4,5] | 0 faults; module IO1-4 on pmoda[4..7], IO7-10 on pmoda[0..3] |
| ECP5 J303 | a spec 6-pin module | **4 faults** | 0 faults (lower row; IO1-4 on pmoda[4..7]) |
| ECP5 J303/J304 | AMOD-A, B, C, M, N, IQ-MOD, PhMOD, RF-MOD rev A plugs | **0 faults**: pmoda[k] meets /PMOD(k+1), and +3V3 meets AMOD-N's PMOD_VCC | 4-6 faults (the plug is a mirrored module; see `~/pcbs/AMOD-and-RFMOD/PIN_AUDIT.md`) |
| ECP5 J303 | PMOD_direct_to_SMA J9 (a spec module) | **6 faults**: +3V3 on the SMA centres "Pin 4"/"Pin 0", GND on "Pin 5"/"Pin 1", and the board's GND (every SMA shell, and through the coax the bench's ground) on pmoda[1]/[5] | 0 faults |
| ECP5 J303 / J304 | VerifierPCB J3 / J4 (spec power; rows of its own pad names swapped) | J3: **9 faults, including a dead short from +3V3 to GND** (pad 11 meets J3's GND-tied pad "4"). J4: 8 faults. | J3: 4 faults (pmoda[4..7] into J3's grounded pads). J4: 0 faults. |

**The rev B socket (pin k on pad 13-2k) against each part:**
- It mates the spec modules, the direct board, and the Verifier's power pins upright.
- It mates the rev A AMOD plugs only turned over.

### What was covered

**24 connectors checked; all pass except the rows above.**

| connector | count | what was checked |
|---|---|---|
| Pmod sockets | 2 (24 pads) | |
| USB-C | 2 | J501/J502, GCT USB4105, against the drawing on disk (`datasheets/USB4105-GF-A-120_C5184243.pdf` p.1):<br>- the tail row, from the viewer's left with the opening towards the viewer, is A1/B12, A4/B9, B8, A5, B7, A6, A7, B6, A8, B5, A9/B4, A12/B1. This is the drawing's order;<br>- A1 is at the end the front view puts it;<br>- VBUS is on A4, A9, B4, B9 and GND on A1, A12, B1, B12 and the shell;<br>- D+ is on A6+B6 and D- on A7+B7;<br>- CC1 and CC2 each have their own 5.1k to GND;<br>- SBU is open.<br>(The tail labels in GCT's bottom view are too small to read at the PDF's resolution, so the interleave rests on the standard 16-pin pattern. LCSC's HRO land pattern has the same pattern.) |
| mini HDMI | 1 | J503, as in the red flags. |
| microSD | 1 | J504, as in the red flags. |
| RJ45 and magnetics | 1 + 1 | J401 as in the red flags.<br>T401: G2406S on B.Cu. Seen from the top, its pads run clockwise from 1. Seen from the part's own top, that is counter-clockwise, the usual IC order; the B.Cu mirror is consistent. |
| JTAG | 1 | J305, a non-standard 1x6 for flying leads. Its silk labels 3V3, TCK, TMS, TDI, TDO and GND sit centred on pads 1-6, which carry exactly those nets. |
| bench and lead headers | 5 | J601, J602 (as above).<br>J106 PD EXT: "A" by pad 1 (-4V2, the photodiode's anode side), "K" by pad 2 (D103's cathode).<br>J210 LED EXT: "A +5V" by pad 1, "K" by pad 2.<br>J105 NOISE: an external resistor, no polarity. |
| coax | 6 SMA + 4 U.FL | The centre pad carries the signal and every other pad is GND. |

**Pmod matings computed:** 2 sockets against:
- a spec 12-pin module and a spec 6-pin module;
- 8 AMOD/RF-MOD plugs;
- the direct board;
- the Verifier.

Each was mated upright, and also turned over wherever a turned-over part could fit.

### Not checked, and why

- **The drawings of the XKB mini-HDMI, the Hroparts TF-01A and the Ckmtw RJ45.** They are not on disk. LCSC's file
  server refuses scripted downloads, and its datasheet page returned only a title. These rows rest on LCSC's own
  symbol and footprint pairs, on the Icepi Zero's footprint (for the HDMI), and on board A's behaviour. They are
  marked *uncertain* above, each with the step that settles it.
- **The HC-PM254 socket's own drawing.** LCSC's land pattern (EasyEDA cache, read-only) was used for the body side.
  The upper/lower row rule is the general one for right-angle 2-row parts.
- **The jumper headers (JP*, 12 of them) and SW101.** Shunts and a DIP switch are symmetric and mate with nothing.
- **Mechanics.** The end plates' cutouts against the connectors, and the clearance of a turned-over module.
- **The connectors' placement-rotation (CPL) question.** Deferred to ordering day by the project.
