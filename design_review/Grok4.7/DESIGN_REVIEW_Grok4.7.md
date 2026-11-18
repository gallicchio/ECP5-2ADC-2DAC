# Design review: ECP5-2ADC-2DAC rev A (Grok 4.7)

**Verdict: do not start over, and do not hold the fab for a respin of the analog chains.** The ADC and DAC paths work. What is wrong is a set of claims the board will teach, plus one supply that will put a common spur under the noise lab, plus an isolation gap that is a bench clearance and not a 1500 V barrier. Fix the silkscreen and the sheet notes before ordering. Scope the two bucks and the −4.4 V rail on the first board before trusting Master SPI or the Johnson-noise lab.

I did not re-run DRC or ERC, and I did not render copper. Lengths below are summed from `ECP5-2ADC-2DAC.kicad_pcb` segments and arcs. SPICE is the author's behavioral decks, run read-only with `python3 sim/run.py`.

## Findings

Ranked by what it costs to be wrong, not by how many lines it takes to fix.

| # | Cost if wrong | Finding | Confirmed by |
|---|---|---|---|
| 1 | The noise lab measures the charge pump, not Johnson noise | −4.4 V is an LM27761 whose LDO PSRR at its own 2 MHz is 35 dB typical, with 10 µF + 100 nF at the pins and no ferrite. +5VA is ferrite-fed; the negative rail is not. Both noise-channel op amps share that rail, so the spur is common-mode and cross-correlation will not average it away. | LM27761 datasheet PSRR row (35 dB, ILOAD = 80 mA, 2 MHz). `gen/sheet_power.py` ferrite feeds stop at +5VA. Ripple magnitude is only in the datasheet figures (mV axis), not a table, so I will not invent a µV number. |
| 2 | Students learn the wrong full-scale | Silkscreen and the sheet say ±1 V into 50 Ω and ±2 V open-circuit. The simulated SMA level is ±0.913 V into 50 Ω, and the amplifier is at ±1.825 V. Open-circuit at the SMA is that amplifier swing, not ±2 V. Bandwidth is 13.5 MHz, so 125 MSPS is the data rate, not the analog bandwidth. | `python3 sim/run.py` on `sim/dac_output.cir`. Sheet text and the "±1 V MAX OUT" string in `gen/sheet_dac.py`. FSADJ 2 kΩ → 19.2 mA (1.2 V / 2 kΩ × 32) matches the AD9767 formula. |
| 3 | A student reads the sheet and later splits the rails | The power sheet says the ECP5 "has no order requirement." FPGA-DS-02012 §3.5 says the opposite for Master SPI: VCCIO8 must be above the flash VIH before at least one of VCC or VCCAUX reaches VPORUP, or PROGRAMN or INITN must be held low. The author's reading of "at least one" (VCCAUX alone satisfies it) inverts the sentence. The power tree as drawn probably still boots. | Family datasheet text, extracted locally. Rail assignment in `gen/sheet_power.py`: VCC = +1V1 buck, VCCIO8 = +3V3 buck, VCCAUX = LP5907 2.5 V hung off +3V3. TLV62569 tSS = 900 µs typical. PROGRAMN/INITN are 4.7 k to +3V3, not held low. |
| 4 | Someone hipot-tests the Ethernet and punches through | Line-side clearance rule is 1.5 mm. `Edge.Cuts` is only the board outline. There is no slot. The moat keeps planes out from under the magnetics, which is right. The author's own copper check (read after this draft) measured 1.9 mm at the 2 kV capacitor and >3 mm elsewhere. That is a bench clearance, not a 1500 V barrier. | `gen/rules.py` physical_clearance 1.5 mm. `pcb/build_pcb.py`: one `Edge.Cuts` arc-rect, `LAN_ISLAND` with `no_pour`. Actual gap: author's `moat.py` result in `DESIGN_REVIEW_RESPONSE.md`, which I did not re-measure. |
| 5 | Gigabit link fails until gateware adds the TX delay | Straps are TXDLY = 0, RXDLY = 1, which is the usual split only if the FPGA inserts ~2 ns on TXC. The shipped platform does not. Copper skew is not the problem. | Strap note in `gen/sheet_eth.py`. No `tx_delay` in `gateware/litex/ecp5_2adc_2dac.py`. Lengths measured on the board file (below). |
| 6 | A ±10 V lab source into a high-Z SMA opens the terminator | The BAV99 clamp protects the OPA1612, not the 3.3 V FDA, and not the 100 Ω 0.1 W shunt. After that resistor fails open, the 499 Ω networks still limit FDA pin current. Recoverable for the expensive parts. The 0603 is the fuse. | THS4521 abs-max and VICR (local extract). Clamp wiring in `gen/sheet_adc.py`. Overload estimate, not a sim of the failed resistor. |

Nothing in this table is "the ADC front end cannot work."

## §6.1 ADC front end

**It works at the rated ±1 V, at 0 dB from the SMA to the ADC differential input, with a 23 MHz bandwidth that is the FDA, not an anti-alias filter.**

Author's deck, behavioral models:

- Gain from the source, before the 50 Ω divider, is −6.03 dB. That divider is the measurement setup. At the SMA, ±1 V is ±1 V differential at the ADC, which is the 2 Vpp the AD9238 wants with SENSE = GND (1.0 V reference).
- f3dB = 23.1 MHz. The 33 Ω + 22 pF to ground is the datasheet kickback network. Its pole is about 1/(2π × 33 × 22 pF) = 219 MHz. An SDR lab will alias. Say that on the sheet; the circuit is not wrong.
- x10 on the noise path is 9.1 k / 1 k = 10.1, not 10. Harmless.

Pin and bias checks, from the datasheets, not from the generator's comments:

- THS4521 on 3.3 V, VS− at ground, PD tied to +3V3_ADC. PD low is power-down; high or open runs. VOCM open is midsupply, 1.65 V, inside 0.8–2.5 V. AD9238 common-mode window is VREF/2 = 0.5 V to (AVDD+VREF)/2 = 2.15 V. 1.65 V is the right choice.
- At ±1 V into the FDA, each input pin sits near 0.575–1.075 V (0.25×Vin + 0.825). VICR at 3.3 V is about −0.1 V to 1.8–1.9 V over temperature. Rated swing is inside. The sheet's "0 to 1.6 V" was conservative.
- AD9238 pins used match the datasheet: A VIN+/VIN− = 2/3, CLK = 63; B VIN+/VIN− = 15/14. Polarity is out+ to VIN+, out− to VIN−. SHARED_REF high, MUX_SELECT high. Correct.
- OPA1612 on +5 / −4.4: VICR is (V−)+2 to (V+)−2, so −2.4 V to +3.0 V. ±1 V is inside. No phase reversal. IB ±60 nA typical, ±250 nA max; across 1 kΩ that is 60–250 µV of offset, not a noise-floor problem.
- Negative overload: the OPA1612 can swing to about 0.6 V of the −4.4 V rail, so the FDA input pin can be pushed to roughly −0.3 to −0.6 V. That is outside VICR (the output clips and recovers) and inside the −0.7 V abs-max. Differential input stays under the 1 V abs-max because of the 499 Ω networks. I would not respin for this. I would put one sentence on the sheet: overload is recoverable, not linear.

TIA deck: 10 mV/µA, f3dB 6.8 MHz, 3.5 dB of peaking near 4 MHz. The sheet already says 3.3 pF would flatten it. Agree. Not a fab issue.

## §6.2 DAC output

**The amplifier and the current-to-voltage network are wired correctly. The number printed on the board is not.**

- AD9767 pin order checked against Table 6. IOUTA1 is pin 46, IOUTB1 is pin 45 (swapped relative to port 2). The schematic follows that, and code 0 leaves IOUTA off, which is the negative output. MODE pulled up (dual port). GAINCTRL low (independent FSADJ). SLEEP is active-high in the datasheet ("logic 1"), and the sheet pulls it down with 10 kΩ. That label is right.
- FSADJ 2 kΩ, VREFIO 1.2 V → 19.2 mA full scale. The sim, which includes the 499 Ω diff-amp load, gives ±1.825 V at the amplifier and ±0.913 V at a 50 Ω SMA. The silkscreen "±1 V MAX OUT / ±1 V into 50 Ω / ±2 V open circuit" is about 9% high on the loaded number and wrong on the open-circuit number. Change the string. Do not change the resistors unless a lab really needs ±1.000 V; 0.91 V is a fine teaching full-scale if the label says so.
- f3dB = 13.5 MHz with the 2.2 pF across 2 kΩ. A 125 MSPS DAC into a 14 MHz analog channel is a reconstruction filter, not a bug, as long as nobody expects a 40 MHz sine.
- OPA2810 is unity-gain stable. The SMA is behind 49.9 Ω, so cable capacitance is isolated from the feedback node. I did not run a cable-C deck. I do not expect oscillation. A 2 m coax is still worth one scope shot on the first board.
- LED driver: SS8050 SOT-23 is pin 1 base, pin 2 emitter, pin 3 collector (JSCJ drawing). The KiCad symbol extends `Q_NPN_BEC` with `Sim.Pins` 1=B 2=E 3=C, and the schematic uses it that way. The sense is 10 Ω on the emitter, VA2 is 0–0.48 V, so 0–48 mA. Midscale code is a 24 mA bias. The behavioral deck agrees. This is the classic SOT-23 footgun, and this instance is not shot.

## §6.3 Clocks

**Adequate for an FPGA PLL. Not a metrology reference. The 8 MHz note is true.**

- CLK IN: 10 nF, 1 MΩ self-bias on a 74LVC1GU04 (pin 2 in, pin 4 out, pin 1 NC), then a 74LVC1G17, 33 Ω into the FPGA. `gate_supply` puts +3V3 on pin 5 and GND on pin 3. That is the LVC1G pinout. A ≥0.5–1 Vpp 10 MHz sine or a square wave will clock a PLL.
- The threshold sits at VCC/2 and moves with the rail. 50 mV of supply motion on a 1 Vpp 10 MHz sine (slew ≈ π × 10 MHz × 1 V ≈ 31 V/µs) is about 1.6 ns of edge uncertainty. The PLL will filter whatever is above its loop bandwidth and will not filter what is inside it. Say "PLL reference," not "low jitter."
- CLK OUT: 74LVC1G17 and 49.9 Ω into the other board's AC-coupled squarer. 1.65 V into 50 Ω. Fine.
- Si5351A 10-MSOP Table 20 matches the schematic pin for pin (VDD, XA, XB, SCL, SDA, CLK2, VDDO, GND, CLK1, CLK0). Both supplies are +3V3. Outputs are not required to boot; the TCXO is the system clock. A 10 pF crystal against the internal load is a register value, not a boot bug.
- ECP5 family datasheet: fIN minimum 8 MHz, maximum 400 MHz. 10 MHz is legal. The jitter numbers are guaranteed for fPFD > 10 MHz, so a 10 MHz PFD is on the edge of that guarantee. Not a board change.

## Power, including the sequencing sentence

The bucks are right as regulators:

- +3V3 = 0.6 × (1 + 15k/3.3k) = 3.33 V. +1V1 = 0.6 × (1 + 10k/12k) = 1.10 V. TLV62569 DBV pins EN/GND/SW/VIN/FB = 1/2/3/4/5 match the generator.
- LM27761 pins 1–8 and the pad match. VOUT = −1.22 × (1.3 MΩ + 499 kΩ) / 499 kΩ = −4.40 V. The sheet's "−4.5 V" in the title block is the intent, not the divider. LDO dropout is tens of millivolts, charge-pump Rout is about 2 Ω, so a stiff 5 V at <100 mA is fine. USB VBUS at 4.5–4.75 V can put the LDO in dropout and dump 2 MHz onto the op-amp rail. That is the same spur as finding 1, reached by a different path.
- LP5907 SOT-23 pin 4 is N/C on this package (the NR pin is on the other packages). The generator no-connects pin 4. Correct. The 2.5 V orderable is Active, not NRND.
- Power-good LED on −4.4 V has its anode at ground. Correct. The 1.1 V good-LED NPN uses the same BEC symbol as the LED driver.

Sequencing, which is the sentence I was asked to attack:

FPGA-DS-02012, section 3.5, extracted here from the Lattice PDF:

> it is required to ramp VCCIO8 above VIH of the external SPI Flash, before at least one of the other two supplies (VCC and/or VCCAUX) is ramped to VPORUP. If the system cannot meet this, keep PROGRAMN or INITN low until VCCIO8 is there.

VPORUP is 0.90–1.00 V on VCC, 2.00–2.20 V on VCCAUX, 0.95–1.06 V on VCCIO8. "At least one of the other two" means the *first* of VCC and VCCAUX to hit its trip point. VCCAUX being up does not waive it. The sheet note ("no order requirement") is the wrong lesson.

The tree as built is kinder than the note:

- VCCAUX is an LDO off +3V3, so it cannot reach 2.1 V until VCCIO8 is already above that.
- Both bucks have EN tied to +5V and the same 900 µs typical soft-start. The 3.3 V rail crosses a 2.3 V flash VIH at about 70% of that ramp. The 1.1 V rail crosses 0.95 V at about 86%. If the two soft-starts match, VCCIO8 is at ~2.8 V when VCC hits VPORUP.
- PROGRAMN and INITN are pulled up to +3V3. They are not the datasheet's hold-low fallback.

I would not refuse to order on this. I would delete the "no order requirement" sentence, and I would scope +3V3 against +1V1 on the first board before calling Master SPI closed. TLV62569's 900 µs figure is typical, not a min/max, and a much faster 1.1 V ramp would violate the sentence even though the schematic "looks sequenced."

Hot-socketing note in the same datasheet: left/right banks can present a low impedance between A/B or C/D pairs if VCCIO is up and VCC has not reached POR. The two bucks rise together over ~1 ms, and most external drivers have series resistors. A caveat, not a respin.

## Ethernet

Straps as drawn: CFG_EXT = 1, CFG_LDO = 00 (3.3 V I/O), PHYAD = 1 from the internal RXD3 pull-up, no external RXD0/RXD1 resistors so TXDLY = 0 and RXDLY = 1. 3.3 V RGMII on an ECP5 is legal and has less timing margin than 2.5 V. I did not re-derive the RTL8211F strap table from the PHY datasheet page; I took the sheet's decode and checked that the resistors drawn match that decode.

Copper, summed from segments and arcs on the twelve `ETH_TX*` / `ETH_RX*` nets (via height not included; a via is <2 mm):

| Net | Length | Versus its clock |
|---|---|---|
| ETH_TXC | 57.88 mm | — |
| ETH_TXD0..D3, TX_CTL | 57.43–60.05 mm | −0.45 to +2.17 mm |
| ETH_RXC | 45.88 mm | — |
| ETH_RXD0..D3, RX_CTL | 52.87–55.73 mm | +6.99 to +9.85 mm |

TX spread is 2.6 mm, about 17 ps at 150 mm/ns. RX data is ~7–10 mm longer than RXC, about 50–70 ps. RGMII's job is a ~2 ns clock shift, not 70 ps of matching. The PHY's RX delay covers the receive side. The transmit side is uncovered until gateware delays TXC by about 2 ns. The pin-proof platform does not. This will not link at 1 Gbps until that exists. It is not a reason to respin the board. 100 Mbps will be more forgiving and should not be used as evidence that the delay split is right.

Isolation: see finding 4. Magnetics and the 1 nF / 2 kV Bob Smith capacitor are the isolation. The PCB gap is not.

## Mechanics

158 × 119 mm against a Hammond 1455Q1601 made for a 120 mm board up to 159 mm long, slot-to-slot about 120.5 mm. I checked the numbers in `pcb/place.py` and the README against the prompt's reading of the Hammond drawing. I did not re-measure the PDF. The end-plate script exists and defaults to the second slot because the G2406S on the back is 4.0 ± 0.4 mm and the lowest slot has about 4.4 mm of room. That measurement is still Jason's, on the actual extrusion. I would not hold the PCB order for it. I would not drill the plates until the extrusion is in hand.

## What I checked and will sign

- ADC pin map, reference straps, common-mode, FDA power-down polarity, OPA1612 VICR at the rated input.
- DAC pin map including the swapped port-1 outputs, SLEEP polarity and its pull-down, FSADJ current, SS8050 pin order.
- Buck and inverting-charge-pump pinouts and the feedback dividers. LP5907 pin 4 left open, which is correct for SOT-23.
- Si5351A 10-MSOP pinout. Single-gate LVC pinout and supply pins. PLL 8 MHz minimum.
- RGMII copper skew is small enough that matching is not the gigabit risk.

## What I would refuse to order

I would not order a board whose silkscreen teaches ±1 V / ±2 V. That is a one-line generator change, so it is not a reason to cancel the layout.

I would not sign a 1500 V isolation claim, and I would not promise the cross-correlation lab until −4.4 V has been looked at on a scope with the op amps loaded. Neither of those requires a new layout before the first spin if the sheet stops claiming them. A ferrite or an RC on −4.4 V is the change I would actually make before a second spin, after measuring the first.

I would not refuse the ADC, the DAC wiring, the clocks, or the FPGA power tree.

## What I did not do

- No DRC, no ERC, no copper renders, no fab-output diff. The prompt says those are clean; I did not spend the shared machine re-proving it.
- No cable-C stability deck.
- No extraction of the RTL8211F strap table from the PHY PDF. The resistors match the sheet's own decode.
- OPA1612 PSRR at 2 MHz is a figure, not a table row. I did not digitize it. Finding 1 stands on the LM27761's 35 dB alone: even a perfect op amp would pass a fraction of a mV-class ripple, and the two channels share it.

## After the draft: the author's response

Read `DESIGN_REVIEW_RESPONSE.md` only after the table above was on disk. I did not read the other reviewers' directories.

**Agree.**

- Do not start over. Order one assembled board, not five. Their bring-up order (current-limited 5 V, rails, USB PROG, a blinker, flash, Ethernet, then SMAs) is the right one, and it is the place to close findings 1 and 3 with a scope, not with another week of schematic reading.
- The already-fixed LCSC, board-size, HPD, and PHY-inductor faults are the class of bug that passes DRC. I did not re-open them. The new code-versus-description check is the right gate.
- Their ADC and DAC sim numbers match mine: 2 Vpp at the ADC for ±1 V at a terminated SMA, DAC ±1.82 V at the amplifier and 0.91 V into 50 Ω, 13.5 MHz, TIA peaking 3.5 dB, LED driver 48 mA. THS4521 pin bias 0.58–1.08 V matches my 0.575–1.075 V.
- VCCAUX really does follow +3V3, because it is the LP5907. That half of the sequencing sentence is closed.
- Their copper measurement is better than my rule-file reading. I accept 1.9 mm minimum, no plane under the line side. I still would not sign a hipot.

**Dispute.**

- They recorded ±0.91 V into 50 Ω and ±1.82 V open-circuit in the "looked for and not found" list, and left the silkscreen and the sheet saying ±1 V and ±2 V. That is not a clean bill. It is a label that contradicts the measurement they already trust. Fix the string before the fab package goes out. Finding 2 stands.
- "Looked for and not found" on Master SPI only checks that VCCAUX follows VCCIO8. The datasheet's trip is the *first* of VCC and VCCAUX. VCC is the 1.1 V buck, enabled from the same 5 V as the 3.3 V buck, with a 900 µs typical soft-start and no min/max in the row I read. The sheet still says "no order requirement." I agree this is unlikely to brick the first board. I do not agree that the sentence has been checked closed. Scope it during the bring-up they already planned.
- Finding 1 is absent from their list. The sim decks have no noise and no supply. 35 dB at 2 MHz on a shared negative rail is the thing most likely to make a working board fail the lab it was built for. It does not block the order. It blocks the claim.

**Missed, on my side.**

- USB 2.0's 0.5 A against a ~0.6–0.7 A budget. They already say so on the silkscreen (USB-C / USB 3, or the 5 V header). I should have checked it. Agree with leaving it as a label, not a redesign.
- The 1.0 V PHY rail has no pin on the RAILS header (probe C4991). Worth knowing during the bring-up I am endorsing. Not a new finding; they already wrote it down.
