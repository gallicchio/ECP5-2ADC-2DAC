# Independent Design Review: ECP5-2ADC-2DAC Rev A

**Reviewer:** CopilotSDK  
**Date:** 2026-10-04  
**Status:** Complete -- do not order unchanged

## Review scope

This review assesses the pre-fabrication design against the project's stated use:
the analog signal chains, clocking, power/configuration behavior, Ethernet timing
and isolation, physical layout, manufacturing package, and mechanics. It is based
on the generated design files and local datasheets. The author's response and
other reviewers' directories were intentionally not consulted during this first
pass.

## Findings

| Rank | Severity | Finding | Consequence if wrong | Confirmed by |
|---:|---|---|---|---|
| 1 | HIGH | The Ethernet Bob Smith bridge C4951 is a general-purpose 1 nF, 2 kV DC X7R MLCC (C53084552), not a documented safety/Y capacitor with a 1.5 kVrms isolation-test rating. | The claimed 1500 Vrms cable-side isolation is unsupported; the only intentional barrier bridge may fail the test or defeat the isolation rating. | `gen/sheet_eth.py`, `gen/parts.py`, the C53084552 datasheet/listing, and the rendered board. |
| 2 | HIGH | The DAC stage's stated 13 MHz, full-scale endpoint has no dynamic margin. Its small-signal simulation is already -3 dB at 13.455 MHz and omits slew rate; an approximately 1.825 V peak amplifier waveform at 13 MHz needs 149 V/us, versus the OPA2810's 180 V/us typical slew rate. | It cannot be represented as a clean +/-1 V, 13 MHz output without characterization; large-signal roll-off and distortion will be material at the claimed band edge. | `sim/dac_stage.cir`, `sim_results.txt`, `sim/opamps.lib`, `gen/sheet_dac.py`, and the OPA2810 electrical-characteristics table. |
| 3 | MEDIUM | CLK IN uses a self-biased, unbuffered CMOS inverter as an analog squarer, with no specified threshold, amplitude-to-jitter budget, or input limiter/comparator. | The advertised weak sine/reference input can produce unquantified and potentially large phase error after the FPGA PLL; this is unsuitable evidence for the two-board phase-lock/time-transfer claim. | `gen/sheet_fpga.py`, the SN74LVC1GU04 function, and the 50 ohm/10 nF/1 Mohm network. |
| 4 | MEDIUM | The RGMII timing contract has no board skew rule or gateware implementation. The actual clock-to-data copper spreads are 23.180 mm (TX) and 23.105 mm (RX); RXDLY is enabled, but the expected FPGA TX delay is absent from the shipped pin proof. | Gigabit Ethernet may miss timing even though all traces route and DRC passes. The observed board skew is plausibly manageable, but it is not closed against ECP5 I/O timing, package delay, and the PHY setup/hold budget. | `measure_rgmii.py`, `rgmii_lengths.txt`, `gen/rules.py`, `gen/sheet_eth.py`, `gateware/litex/ecp5_2adc_2dac.py`, and the RTL8211F timing table. |
| 5 | LOW | The USB-C programming/power port presents only sink Rd resistors, yet the board is documented to consume 0.6-0.7 A at 5 V. There is no Type-C current-advertisement detection or input current limit. | A default-current USB 2.0/Type-C source can brown out, reset, or over-current-trip before FT2232 enumeration. | `gen/sheet_usb.py`, `gen/sheet_power.py`, and `README.md`. |

## Evidence log

- Created this isolated review directory before generating any review artifacts.
- Independent ERC: 0 violations. Independent DRC: two known dangling-GND-via warnings and no unconnected items.

## Verdict

**Do not release this board for fabrication unchanged.** The Ethernet isolation
claim has a concrete component-level failure, and the promised full-scale DAC
bandwidth is not credible from the selected stage or its simulation. The CLK
IN and RGMII issues are not necessarily unrecoverable after fabrication, but
they leave two advertised synchronization/network functions without a
verifiable timing budget.

The rest of the review is more positive than the findings table alone
suggests. The nominal ADC operating point is sound, the Master-SPI power-up
ordering is sound, the measured SDRAM and HDMI trace skews are small for their
uses, and the independent KiCad/manufacturing checks are clean apart from the
two already-known cosmetic vias.

## Findings in detail

### 1. Replace C4951 and define the Ethernet isolation boundary

The line-side Bob Smith node crosses to board ground only through C4951. The
schematic deliberately identifies it as a `1nF 2kV` capacitor and the BOM maps
that value to TORCH C53084552, `CV1206X7R2kV102KN`: a general-purpose 1206 X7R
MLCC. Its part information provides a 2 kV DC component rating, not a
safety/Y classification or a documented 1500 Vrms isolation-test rating.
Those are not interchangeable: 1500 Vrms has a 2121 V peak, and a general
purpose MLCC is not evidence of a qualified insulation bridge.

The board rules make the point more important: ordinary line-side copper is
kept 1.5 mm away, but C4951 is explicitly exempt because it is the intended
bridge. The RJ45 shield is also tied directly to board ground. Therefore the
design must state exactly what the hipot test includes and where the
isolation/chassis boundary is; it cannot claim a 1500 Vrms isolation result
from the transformer alone.

Use a documented, appropriately rated safety capacitor (and the required
creepage/clearance or slot for the applicable insulation class), then test the
assembled board with the actual shield/chassis connection. If the product is
not intended to make a 1500 Vrms isolation claim, remove that claim and make
the intended non-isolated shield connection explicit.

### 2. The DAC output is a low-frequency +/-1 V stage, not a proven 13 MHz full-scale stage

The DC topology is fundamentally correct:

* The AD9767 sees approximately 0 V to 0.48 V at each 24.9 ohm load, safely
  inside its -1.0 V to +1.25 V output-compliance range.
* The OPA2810's 9.4 V total supply is valid; its specified operating range is
  4.75 V to 27 V, so the split +5 VA/-4.4 V rails are not an overvoltage
  mistake.
* The 49.9 ohm output resistor isolates normal cable capacitance from the
  amplifier output. That is the correct basic stability measure.

The endpoint claim fails the dynamic check. The supplied small-signal deck
reports 13.455 MHz at -3 dB and only 0.913 V peak at the SMA into 50 ohms at
the endpoint code. More importantly, its op-amp model is a single-pole,
rail-limited behavioral model: it has no slew-rate, distortion, output-current
or phase-margin model. The real OPA2810's relevant small-signal bandwidth at
gain 5 is 14 MHz typical and its slew rate is 180 V/us typical. A 1.825 V
peak amplifier waveform at 13 MHz alone needs 149 V/us
(`2*pi*f*Vpeak`); the nominal +/-2 V open-circuit target needs 163 V/us.
There is no minimum-slew margin, and the model cannot reveal slew-induced
distortion.

Decide which claim is required before ordering. If clean +/-1 V into 50 ohms
at 13 MHz is required, redesign and characterize this stage using the vendor
macro-model and a large-signal load/cable sweep, then verify it with a tone
FFT. Otherwise lower the documented full-scale bandwidth and state the
measured amplitude rather than labeling the SMA +/-1 V at all frequencies.

### 3. CLK IN is acceptable as an experiment, not as a specified precision reference input

The 49.9 ohm selectable termination, 10 nF AC coupling, 1 Mohm feedback
bias, unbuffered SN74LVC1GU04, and following Schmitt gate make a plausible
bring-up circuit. CLK OUT is also sensibly source-terminated with 49.9 ohms.
That supports a board-to-board demonstration with a strong CMOS source.

It does not establish the advertised precision-reference behavior. The
unbuffered gate's published guaranteed limits are digital `VIL` and `VIH`
(0.25 and 0.75 times VCC), not a controlled analog switching threshold or
input-noise-to-time-jitter specification. The 1 Mohm feedback biases at an
uncontrolled device threshold, which moves with device, supply and
temperature. For scale, a 10 MHz, 0.5 Vpp sine has a zero-crossing slope of
only 15.7 V/us; 10 mV of threshold/noise movement is about 0.64 ns of timing
movement before the FPGA PLL. That is not a defensible time-transfer budget.

Replace the front end with a terminated limiting comparator/clock receiver
with specified additive jitter and a defined sine amplitude range, or narrow
the supported interface to strong LVCMOS clock sources and remove the
precision-reference claim. In either case, specify and measure input
amplitude, frequency, phase noise and recovered-clock jitter.

### 4. RGMII hardware routing is likely usable, but the timing implementation is missing

The RTL8211F can add about 2 ns in either direction. The board straps RXDLY
on and TXDLY off, deliberately assigning the transmit delay to FPGA gateware.
That division is valid only when the gateware actually launches a phase-shifted
TXC and constrains its source-synchronous relationship.

The shipped LiteX platform is only a pin proof. It has an RX-clock period
constraint, but no instantiated RGMII PHY, TX phase shift, output-delay
constraint, or timing proof. There is likewise no RGMII group-skew design
rule. The direct copper measurement gives these spreads, including both sides
of each 22 ohm resistor:

| Direction | Shortest | Longest | Spread |
|---|---:|---:|---:|
| MAC-to-PHY (TXC/TX_CTL/TXD[3:0]) | 86.085 mm | 109.265 mm | 23.180 mm |
| PHY-to-MAC (RXC/RX_CTL/RXD[3:0]) | 60.390 mm | 83.495 mm | 23.105 mm |

About 23 mm is roughly 0.15 ns of FR-4 trace delay, so this is not evidence
that the PCB alone will fail. It is, however, large enough that it belongs in
the RGMII timing calculation rather than being ignored. Before release, choose
one delay owner per direction, add the necessary ECP5 constraints and
phase-shift implementation (or enable PHY TXDLY), and demonstrate margin
against the RTL8211F's 1 ns setup/hold requirements with I/O, package, via and
board delays included.

### 5. USB-C power is not negotiated for the board's stated load

The USB-C receptacle correctly has two 5.1 kohm Rd resistors and its VBUS is
fused. That declares a sink, but it does not tell this design whether the
source advertises default, 1.5 A or 3 A current. The board begins consuming
its documented 0.6-0.7 A before software can make a USB-level power request,
and the 2 A PTC is not a 500 mA current limiter.

Keep the bench header as the supported power source, ship a known-capable
adapter/source with the board, or add Type-C current detection and a
power-limited startup path. Do not describe an arbitrary USB-C socket as
sufficient power merely because it is USB-C.

## Circuits checked and accepted with qualifications

### ADC nominal DC operation is correct

For the THS4521, the 499 ohm input and feedback resistors implement a
single-ended-to-differential gain of one. With VOCM open, the part defaults to
mid-supply; at a +/-1 V stage output its differential outputs are 1.15 V and
2.15 V about 1.65 V common mode. The FDA input summing nodes are about
0.575 V to 1.075 V, comfortably inside the THS4521's -0.1 V to 1.8 V
guaranteed common-mode range at 3.3 V. This is also the exact operating mode
used for the THS4521's 2 Vpp, 3.3 V characterization.

The AD9238 recommends midsupply common mode; with its 1.0 V reference it
permits 0.5 V to 2.15 V common mode and has a 2 Vpp span. Thus the FDA-to-ADC
nominal bias and the 33 ohm/22 pF acquisition network are appropriate.
Independent SPICE reports 23.08 MHz small-signal -3 dB bandwidth at x1, as
claimed.

The overload statement needs a narrower qualification. The BAV99 clamps the
input *before* the high-gain OPA1612 stages, not at the 3.3 V FDA inputs.
When an x10/x100 preamp overloads, a THS4521 input can leave its normal
common-mode range. The 499 ohm resistors do limit a rail-saturated
-4.4 V input to roughly 7.4 mA against the THS4521's -0.7 V absolute-input
limit, below its 10 mA absolute maximum, so this is not evidence of immediate
destruction. It is still ESD-clamp operation rather than a guaranteed linear
or recovery condition. Add explicit secondary clamps/current limiting at the
FDA inputs, or test repeated overdrive and recovery before promising that
student misuse is harmless.

### The negative rail is within its DC load capability, but needs a spectral acceptance test

The LM27761 is specified for up to 250 mA operating output current and the
schematic gives it 10 uF input, flying and output capacitors; the combined
static negative-rail op-amp load is far below that limit. Its own specified
noise is low and its regulated 2 MHz architecture is a reasonable choice.
I found no DC capacity or capacitor-value error.

It is still a coherent 2 MHz source shared by both low-noise channels, inside
the ADC Nyquist band. The supplied simulations do not inject rail ripple or
model PSRR. Before claiming a Johnson-noise cross-correlation floor, measure
the ADC spectrum and cross-spectrum at x1/x10/x100 with inputs terminated,
then set an explicit permitted 2 MHz spur level. This is a validation
requirement, not a demonstrated schematic fault.

### Power-up and Master-SPI configuration pass

This was checked against the ECP5 POR text rather than inferred from the buck
part numbers. In Master-SPI mode, VCCIO8 must reach the flash's VIH before
*at least one* of VCC or VCCAUX reaches its POR threshold. Here the flash and
VCCIO8 share +3V3, while VCCAUX is generated from that same +3V3 rail by the
2.5 V LP5907. VCCAUX cannot reach its 2.0 V POR threshold before the
shared +3V3/VCCIO8 rail exceeds the flash's proportional VIH. The stated
condition is therefore met without requiring the independent 1.1 V buck to
be later than +3V3.

The pull-ups and Master-SPI straps were also traced through the generated
netlist. Preserve monotonic rail ramps, as required by the ECP5 data sheet.

### Routing and manufacturing evidence that passed

* **SDRAM:** direct routed-copper lengths span 22.788 mm total. The clock is
  16.746 mm and all other signals are from 8.663 mm shorter to 14.125 mm
  longer. That is roughly 0.15 ns of board skew, not a concern for the
  stated 100 MHz SDR SDRAM target.
* **HDMI:** measured FPGA-to-receptacle P/N pair skews are 3.331 mm (clock),
  3.331 mm (D0), 2.200 mm (D1), and 3.000 mm (D2). The 22 nF capacitors are
  present in every lane. The layout does not have an HDMI skew rule, but the
  resulting pair matching is good.
* **USB:** the custom 1 mm USB intra-pair-skew DRC rule passed. Both
  receptacles have ESD arrays and correct CC resistors.
* **KiCad checks:** KiCad 10.0.6 ERC reported zero violations. DRC reported
  zero unconnected items and only the two known dangling ground-return-via
  warnings.
* **Fabrication checks:** the placement-vs-KiCad audit found 0.0000 mm worst
  pad disagreement over 452 footprints/1722 pads; the footprint/BOM audit
  concluded that every ordered part fits its board footprint; the stored
  bottom-side CPL rotation checks passed.
* **Visual copper review:** the rendered board shows the two ADC strips,
  two DAC strips, converter placement, FPGA decoupling field and connector
  clearances in the intended physical order. I found no separate return-path,
  plane-seam or connector-clearance blocker beyond the Ethernet-isolation
  finding.

### Mechanics and release process

The generated end-panel report places all six left-side SMAs and the six
right-side connector openings within the Hammond plate. The unresolved
variable remains real: `PCB_TOP_ABOVE_FLOOR` depends on the actual extrusion
slot and must be measured before milling. The Pmod and RJ45 heights also
remain drawing-derived rather than test-fit. Make a cheap panel/connector
fit-check a release gate; no static PCB inspection can certify that part.

## Required disposition before an order

1. Replace/qualify C4951 and document the Ethernet high-pot test boundary.
2. Either redesign and characterize the DAC stage for the published
   amplitude/bandwidth or reduce the published claim.
3. Define a precision CLK IN implementation and its jitter acceptance test.
4. Finish RGMII gateware timing closure and test 1 Gb/s traffic under voltage
   and temperature variation.
5. Establish a supported USB power source policy or enforce it in hardware.
6. Run the analog spur/cross-spectrum test and physically test-fit the
   enclosure/end plates before production.

## Review independence

This first-pass report did not read `DESIGN_REVIEW_RESPONSE.md` or any other
`design_review_*` directory.
