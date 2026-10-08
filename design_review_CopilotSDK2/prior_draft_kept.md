# ECP5-2ADC-2DAC rev A, build 31: independent second-round review

**Reviewer:** CopilotSDK  
**Review date:** 2026-10-07  
**Scope:** Build 31 as committed, including the schematic, board, manufacturing
release, committed build evidence, source generators, simulations, and component
datasheet text. This review does not run `build.py` or modify shared design files.

## Verdict

**Do not order build 31 unchanged.** The board does not need a new architecture,
but four bounded pre-order corrections are required. The new bench-input fuse does
not protect the 1 A Schottky ahead of it; the CLK IN comparator has no
overvoltage-current limiter despite being exposed at an SMA; the stated 5.0--5.5 V
bench-input range leaves the LM27761 without guaranteed transient margin; and the
ADC LDO exceeds its 125 C recommended junction limit in the stated closed-box,
full-rate case when calculated with its datasheet thermal resistance. Any one can
make a first board unreliable or permanently damaged. Correct those items,
regenerate the release, and rerun the checks below; the rest of the fabrication
package is in unusually good shape.

## Findings

| Rank | Finding | Impact | Confirmed by |
|---:|---|---|---|
| 1 | **F602 cannot protect D601.** The new F602 is downstream of D601 but is a 2.00 A-hold / 4.00 A-trip PTC; D601 is a 1 A, 0.5 W SOD-123 Schottky. | A bench-supply overload between 1 and 2 A can persist without tripping F602 while exceeding D601's continuous-current and dissipation ratings. The build-31 safety fix therefore does not meet its stated purpose. | [power source](../gen/sheet_power.py), [PTC datasheet](../docs/datasheets/txt/MF-MSMF200-2_C210837.txt), [Schottky datasheet](../docs/datasheets/txt/B5819W_SL_C8598.txt), [BOM](../mfg/release/ECP5-2ADC-2DAC_bom.csv) |
| 2 | **CLK IN has no external input-current protection.** After C5421 the SMA signal is directly on TLV3501 `+IN`; R5426 is only a 10 k bias resistor. | A normal 50 ohm source carrying a 10 V sine can inject at least `(10 - 3.6) / 50 = 128 mA` into the comparator's internal input clamp, versus its 10 mA maximum. The 10 nF capacitor blocks DC, not AC or transients. This conflicts with a student-accessible SMA and the review brief's input-protection requirement. | [CLK IN circuit](../gen/sheet_fpga.py), [TLV3501 limits](../docs/datasheets/txt/TLV3501AIDBVR_C193413.txt), [netlist audit](./netlist_audit.txt) |
| 3 | **The 5 V input claim is outside the LM27761 transient margin.** The release permits 5.5 V at J601, yet U606 has 5.8 V absolute maximum and 5.5 V recommended maximum VIN. | The author's own 10% ringing estimate gives `5.5 V x 1.10 = 6.05 V`, already 0.25 V above absolute maximum. The cold PTC may be only 20 mOhm; with the stated 1 uH cable and about 94 uF ceramic bank, `Z0 = sqrt(L/C) = 103 mOhm`, so its resistance cannot guarantee the claimed damping. | [input circuit](../gen/sheet_power.py), [PTC datasheet](../docs/datasheets/txt/MF-MSMF200-2_C210837.txt), [LM27761 limits](../docs/datasheets/txt/LM27761DSGR_C129351.txt), [5 V power trace](./power_path_5V.txt) |
| 4 | **U604 has no demonstrated full-rate thermal margin.** Its load is not just the ADC: +3V3_ADC also powers both THS4521 channels, U302, and D605. | At the stated 5.5 V input and 45 C enclosure ambient, the conservative datasheet load is about 208 mA and `P = (5.5 - 3.3) x 0.208 = 0.458 W`. With the TPS7A20 DBV `RthetaJA = 187.1 C/W`, `TJ = 45 + 0.458 x 187.1 = 131 C`, above the 125 C recommended operating limit. | [+3V3_ADC path](./power_path_3V3_ADC.txt), [AD9238 current table](../docs/datasheets/txt/AD9238BSTZ-65_C514277.txt), [THS4521 current table](../docs/datasheets/txt/THS4521IDGKR_C170157.txt), [TPS7A20 thermal data](../docs/datasheets/txt/TPS7A2033PDBVR_C2862740.txt) |
| 5 | **The controlled-impedance instruction states the wrong SMA width.** It says 0.3 mm, while the committed board generator requires all SMA feeds to be 0.35 mm for the declared 50 ohm stack-up. | An order-form or fabrication calculation made from the release instruction can be set up for copper different from the actual board. This is a release-document error, not a reason to respin the PCB. | [fabrication notes](../mfg/release/FABRICATION_NOTES.txt), [RF width rule](../pcb/build_pcb.py) |
| 6 | **One historical DAC bandwidth sentence is stale.** The current sheet and simulation say -3 dB at 12.3 MHz, but the README's decision text still says 13.5 MHz. | The current circuit still supports the stated 10 MHz full-scale use, but the teaching/design record should not preserve a pre-build-28 value. | [DAC sheet source](../gen/sheet_dac.py), [simulation output](./simulations.txt), [README](../README.md) |

### 1. F602 is sized above D601's safe continuous current

The actual series order is `J601 -> D601 -> F602 -> +5V`; putting the
protection after the diode is reasonable only if it opens before the diode is
overloaded. It does not:

* MF-MSMF200 specifies 2.00 A hold, 4.00 A trip, and 20--80 mOhm initial
  resistance at 23 C.
* B5819W specifies 1 A average rectified current, 500 mW dissipation, and
  200 C/W junction-to-ambient resistance.

Thus a 1.5 A fault is within F602's hold rating but exceeds D601's continuous
rating. At the 0.6--0.9 V forward-drop range shown by the diode data, it also
puts approximately 0.9--1.35 W in a 0.5 W package. This is not remedied by
F602's location, because all of that current reaches D601 first.

**Required correction:** either make D601 and its footprint thermally/current
capable of the 2 A protected path, or choose a protection strategy whose
guaranteed hold/fault behavior protects the diode while retaining adequate
margin above the approximately 0.7 A board load. Do not describe the present
2 A PTC as protection for a 1 A diode.

### 2. CLK IN can destroy U302 from an ordinary lab-source misuse

The intended 0.3 V peak reference input works: at 10 MHz the 10 nF coupling
capacitor and 10 k bias form a high-pass corner far below the signal frequency,
and 6 mV internal hysteresis is much smaller than the intended input swing.
The output's 33 ohm resistor is also appropriately placed at the comparator.

That is not protection. C5421 feeds `+IN` directly; the 10 k R5426 goes to the
AC-grounded mid-rail and cannot limit a fast overvoltage. The TLV3501 explicitly
states that inputs beyond a rail by 0.3 V are clamped and must be limited to
10 mA. Its 3.3 V maximum label also does not protect against an accidentally
selected 5 V/10 V generator, a ringing clock cable, or ESD at an SMA.

**Required correction:** add a series resistor after C5421 sized to keep
worst-case clamp current below 10 mA (and verify the normal 50 ohm,
0.3 V-peak reference amplitude afterward). Prefer external clamps after that
resistor if the connector's advertised student-use robustness is retained.
Explicitly print a safe external voltage range; a clean 0--3.3 V square wave
remains valid after the protection is designed.

### 3. The 5 V transient calculation does not support the published range

The hot-plug resonance is approximately

```text
f0 = 1 / (2 pi sqrt(1 uH x 94 uF)) = 16.4 kHz
Z0 = sqrt(1 uH / 94 uF) = 103 mOhm
```

The PTC's *minimum* 20 mOhm initial resistance is not enough to bound this
network's Q; neither cable resistance, bench-supply output impedance, diode
dynamic resistance, nor ceramic DC-bias derating is a controlled design
parameter in the release. More importantly, even the claimed 10% overshoot
already violates U606's 5.8 V absolute maximum at the allowed 5.5 V input.

**Required correction:** specify an input ceiling that remains inside the
LM27761 operating limit under a measured worst-case plug-in transient, or add
guaranteed damping/overvoltage protection common to both USB and bench paths,
then validate it with the lowest source impedance, minimum PTC resistance, and
effective—not nominal—ceramic capacitance. A TVS whose clamp voltage exceeds
5.8 V is not a solution for U606.

### 4. U604 needs its heat shared before committing the layout

The ADC's 200 mA maximum IAVDD is the dominant load. The two THS4521 channels
add up to 2.5 mA maximum, U302 is up to 5 mA, and the rail LED/divider add
about 0.3 mA. The approximately 208 mA total remains below U604's 300 mA
electrical current limit, but not within a proven thermal limit at the stated
input and ambient conditions. At 5.25 V, the same calculation gives about
121 C using the published thermal resistance, only 4 C below the recommended
limit.

The local planes may improve the actual theta-JA; no thermal measurement or
layout-specific simulation establishes the required reduction, so it cannot be
assumed for an order decision. The small, credible correction suggested in the
brief works numerically: a 3 ohm input resistor at 208 mA drops 0.624 V and
dissipates 0.13 W, leaving U604 at about 0.328 W and an estimated 106 C at
45 C. It still leaves about 0.83 V headroom from a 4.75 V USB supply. Validate
load transient behavior and resistor pulse/power rating before choosing it; a
larger low-noise LDO with suitable thermal data is the alternative.

### 5. Release-document corrections

* Change the 50 ohm SMA width in
  [FABRICATION_NOTES.txt](../mfg/release/FABRICATION_NOTES.txt) from **0.3 mm**
  to **0.35 mm**, or change the board rule and revalidate impedance. The
  generator's `RF_W = 0.35` assertion is unambiguous.
* Change the stale 13.5 MHz historical DAC statement in
  [README.md](../README.md) to the current 12.3 MHz result. The current
  generated DAC sheet already states 12.3 MHz, and
  [dac_stage.cir](../sim/dac_stage.cir) reproduced 12.27 MHz in this review.

## Checks completed without finding an order blocker

| Check | Result |
|---|---|
| KiCad ERC | Fresh `kicad-cli sch erc --severity-all`: no violations on all seven sheets. |
| KiCad DRC | Fresh `kicad-cli pcb drc --severity-all`: zero errors, zero unconnected items, and only the four disclosed warnings (two deliberately dangling GND vias and the two narrow In4 GND-fill webs). |
| Board-coordinate agreement | [check_pads_kicad.txt](./check_pads_kicad.txt) reports 471 footprints / 1,766 pads with 0.0000 mm worst disagreement. |
| Netlist audit | 494 nets. The 52 one-pin entries are all explicitly named `unconnected-*`: USB SBU/card-detect/utility pins, documented IC NC/DNC pins, and unused FPGA/FTDI pins. The 15 named supply rails are distinct and have 5--353 connected pins; there is no accidental one-pin functional or rail net. See [netlist_audit.txt](./netlist_audit.txt). |
| Rail resistance | Fresh [power_path.txt](./power_path.txt) matches the committed report. The +3V3_ADC path reaches the AD9238 worst AVDD pin at 22.7 mOhm; the relevant path geometry is in [power_path_3V3_ADC.txt](./power_path_3V3_ADC.txt). |
| Analog simulations | All five decks exit successfully. The ADC front end is -3 dB at 23.08 MHz and clamps a simulated +/-10 V input node at -4.78 V / +4.99 V; the DAC stage reaches +/-1.005 V into 50 ohm and -3 dB at 12.27 MHz; the TIA is -3 dB at 6.80 MHz; the bead model has its 0.686 ohm peak at 47.4 kHz and is 5.0 mOhm at 2 MHz. See [simulations.txt](./simulations.txt). |
| Clock function | The intended 10 MHz reference path is functionally sound once protected: the TLV3501 is powered at 3.3 V, biased at 1.65 V, has 6 mV hysteresis, and feeds an ECP5 PCLK through 33 ohm. The U302 fault is its missing external protection, not its threshold or speed. |
| Ethernet timing straps | The [RTL8211F source](../gen/sheet_eth.py) pulls `RXD1/TXDLY` high with 4.7 k and uses the part's internal pull-up on `RXD0/RXDLY`; the [datasheet table](../docs/datasheets/txt/RTL8211F-CG-Datasheet.txt) assigns those multiplexed pins exactly that way. Both PHY delays are enabled, so zero gateware delay is correct. |
| PROGRAMN RC | 4.7 k x 100 nF is 470 us, much longer than the ECP5's 110 ns accepted-low minimum. It delays configuration safely; it does not make a normal button/programmer pulse too short. |
| USB-C role detection | Both USB-C receptacles carry independent 5.1 k Rd resistors on CC1 and CC2, correctly declaring a sink/device. The board's 0.6--0.7 A power draw still requires the documented USB 3 / adequate Type-C source, not a 500 mA USB 2 source. |
| Manufacturing package | BOM/CPL bidirectional coverage, the empty hand-solder BOM, the committed footprint-fit report, and the JLC rotation-rule check are internally consistent. The four `PADS` results are the deliberately snapped header strips; there is no `HOLE` result. [jlc_rotation.txt](./jlc_rotation.txt) still satisfies all ten recorded bottom-side readings. |
| Copper coverage | KiCad SVGs rasterized at 10 pixels/mm show F/In1/In2/In3/In4/B coverage of 31.1/96.2/13.7/11.1/96.3/17.5%. Quadrants have no bare-all-layer region; the only large inner-plane reduction is the intentional Ethernet isolation area (top-right In1/In4 about 89%). See [copper_balance.txt](./copper_balance.txt). The F.Cu/B.Cu difference is worth retaining in the fabrication record, but the two nearly solid inner planes make it a fabrication watch item, not an order stop. |

### Equations and claims cross-checked

| Item | Result |
|---|---|
| +3V3 buck | `0.6 x (1 + 15k / 3.3k) = 3.327 V`, matching the printed 3.33 V. |
| +1V1 buck | `0.6 x (1 + 10k / 12k) = 1.100 V`, matching the printed 1.10 V. |
| -4V2 pump | `-1.22 x (1.2M + 499k) / 499k = -4.15 V`, matching the sheet and leaving the stated USB low-line headroom. |
| DAC output | The 2.2 k / 499 ohm ratio gives gain 4.41; the deck produces +/-2.007 V open and +/-1.005 V into 50 ohm, matching the sheet/silkscreen limits. |
| ADC preamp gain | The open gain jumper gives `1 + 9.1k / 1k = 10.1`; the fitted shunt produces unity gain as claimed. |

## Required re-review after the corrections

1. Recalculate and verify D601/F602 fault behavior at the actual enclosure
   temperature, then update the schematic, board, BOM, CPL, and release notes.
2. Add CLK IN protection, verify its 10 MHz / 80 MHz behavior and normal
   50 ohm reference amplitude, and add an explicit connector limit.
3. Capture worst-case hot-plug waveforms on both power entries at their stated
   maximum voltage, with effective ceramic capacitance and cold PTC tolerance.
4. Reduce or demonstrate U604 thermal dissipation at 65 MS/s and the intended
   enclosure ambient.
5. Regenerate the release and rerun fresh ERC, DRC, pad-coordinate,
   footprint-fit, CPL-preview, netlist, and power-path checks.

## Evidence checked

* Required build-31 review brief: `DESIGN_REVIEW_PROMPT2.md`.
* Board overview and release process: `README.md`.
* Build-25 architecture background: `DESIGN_REVIEW_PROMPT.md`, sections 1--5.
* Fresh review artifacts created only in this directory:
  [verification_status.txt](./verification_status.txt),
  [drc_fresh.json](./drc_fresh.json), [erc_fresh.json](./erc_fresh.json),
  [SIGNAL_PATHS.generated.md](./SIGNAL_PATHS.generated.md),
  [power_path.txt](./power_path.txt), [simulations.txt](./simulations.txt),
  [check_pads_kicad.txt](./check_pads_kicad.txt), and
  [copper_balance.txt](./copper_balance.txt).
