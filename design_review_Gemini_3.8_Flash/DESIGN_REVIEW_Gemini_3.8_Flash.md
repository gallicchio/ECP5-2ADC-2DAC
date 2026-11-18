# Design Review: ECP5-2ADC-2DAC rev A

**Reviewer:** Gemini 3.8 Flash  
**Date:** 2026-10-04  
**Project:** OpticsPCBs / ECP5-2ADC-2DAC (Lattice ECP5-25F, AD9238 Dual ADC, AD9767 Dual DAC, Gigabit Ethernet)  
**Board Status:** Build 25 (Pre-fabrication review)

---

## Executive Summary

The ECP5-2ADC-2DAC rev A is an ambitious, highly integrated teaching and laboratory instrument. The entire board is programmatically generated—from schematic sheets down to BGA escape, bus rivers, and placement.

Overall, the schematic architecture and digital core are solid: the pin assignments, bus mappings, power rail calculations, BGA decoupling loops, and DRC/ERC cleanly pass without open nets. However, this deep-dive review uncovered several **critical and high-severity design flaws** in the analog front end, PCB layout, and physical enclosure integration that should be corrected before releasing this board for manufacturing:

1. **ADC Front-End Clamping & Overdrive Destruction Risk:** The upstream BAV99 diodes clamp to +5VA / -4.4V. Under preamp saturation (especially in x10 or x100 gain modes), the OPA1612 drives -4.2V directly through 499 Ω into the THS4521 FDA. The resulting differential input voltage $|V_{ID}| \approx 2.27\text{ V}$ exceeds the THS4521 absolute maximum rating of 1.0 V by over 2.2x, risking permanent damage to the FDA.
2. **ADC Anti-Aliasing Filter Placement & Trace Asymmetry:** The ADC's 22 pF kickback filter capacitors are located ~10 mm away from the AD9238 pins, and the routed traces have a 9.75 mm (Channel A) and 8.93 mm (Channel B) length mismatch between $V_{IN+}$ and $V_{IN-}$, introducing ~10 nH of uncompensated differential parasitic inductance that degrades dynamic SFDR and harmonic distortion.
3. **High-Speed DAC Clock Crossing Split Power Planes:** `DAC_CLK1` (up to 125 MHz) and `DAC_WRT1` are routed on In3.Cu and cross the boundary between the +1V1 core power plane and the +3V3 plane on In4.Cu multiple times, introducing massive return current loop discontinuities and injecting clock noise directly into the 1.1V FPGA core rail.
4. **Mechanical Recess of USB-C Receptacles:** The board edge is 158.0 mm long in a 160.0 mm Hammond extrusion. While RJ45 and Pmod sockets protrude past the board edge, the USB-C receptacles are recessed 0.32 mm inside the board edge. When mounted behind the 1.5 mm end plate, the USB-C mouth sits 2.66 mm deep, preventing standard USB-C cables from fully latching.
5. **No Filtering on -4.4V LM27761 Rail:** The LM27761 2 MHz charge pump ripple (~2 mVpp) feeds directly into the -4.4V rail of the 1.1 nV/√Hz OPA1612 preamps with no ferrite bead or RC filter, bypassing op-amp PSRR at 2 MHz and producing spurs.

---

## Findings Table

Findings are ranked by cost and severity if left uncorrected.

| # | Severity | Subsystem | Description | Cost / Consequence | Confirmed By |
|---|---|---|---|---|---|
| 1 | 🔴 **CRITICAL** | ADC Front-End | Overdrive drives THS4521 input to -0.7V with $|V_{ID}| \approx 2.27\text{ V}$, exceeding 1.0 V abs max rating by 2.3x | Blown / degraded THS4521 FDA during student overdrive | SPICE simulation (`test_ovld.cir`), THS4521 Datasheet Table 7.1 |
| 2 | 🟠 **HIGH** | ADC Layout | Anti-aliasing 22 pF caps placed 10 mm from ADC; $V_{IN+}/V_{IN-}$ traces mismatched by 9.75 mm (Ch A) and 8.93 mm (Ch B) | ~10 nH inductance imbalance, degraded SFDR & kickback settling | Segment length extraction from `ECP5-2ADC-2DAC.kicad_pcb` |
| 3 | 🟠 **HIGH** | High-Speed Layout | `DAC_CLK1` (125 MHz) on In3 crosses +1V1/+3V3 power plane split on In4 three times; `DAC_WRT1` crosses twice | Clock jitter, EMI, high-speed hash injected into 1.1V core rail | Shapely polygon intersection of In3 tracks with In4 plane zones |
| 4 | 🟠 **HIGH** | Mechanics | USB-C receptacles (J501, J502) recessed 0.32 mm inside board edge; 2.66 mm behind outer face of Hammond end plate | Standard USB-C plugs cannot fully latch or make electrical contact | Bounding box inspection (`fplib.box_at`) vs `Hammond_1455Q1601.pdf` |
| 5 | 🟡 **MEDIUM** | Power / Analog | -4.4V rail from LM27761 has no ferrite bead or RC filter before feeding OPA1612 preamps & photodiode TIA | 2 MHz charge pump ripple creates spurs 20x above 1.1 nV/√Hz noise floor | `gen/sheet_power.py`, LM27761 ripple spec, OPA1612 high-freq PSRR |
| 6 | 🟡 **MEDIUM** | DAC Stage | Feedback has 2k ‖ 2.2 pF, but non-inverting input has only 2k to GND (no parallel cap) | Destroyed AC CMRR > 10 MHz; DAC switching glitches pass to output | `gen/sheet_dac.py`, difference amplifier AC balance analysis |
| 7 | 🟡 **MEDIUM** | DAC Output Level | 499 Ω input resistors load the 24.9 Ω DAC termination, yielding $\pm 1.825\text{ V}$ open circuit ($\pm 0.913\text{ V}$ in 50 Ω) | 8.7% gain error vs $\pm 2.0\text{ V} / \pm 1.0\text{ V}$ spec; 13 MHz at 83-91% of slew limit | `sim/dac_stage.cir`, OPA2810 slew rate specifications |
| 8 | 🟡 **MEDIUM** | Clock Front-End | CLK IN 74LVC1GU04 squarer powered from noisy +3V3 digital buck rail; threshold modulates with ripple | ~250 ps deterministic jitter on 10 MHz sine GPSDO reference | `gen/sheet_fpga.py`, CMOS inverter threshold equations |
| 9 | 🟡 **MEDIUM** | Ethernet RGMII | RGMII bus has 23.2 mm (151 ps) trace skew on TX; `ETH_RXC` in Bank 1 while data is in Bank 2 | Tightened setup/hold margins; requires careful PLL clock deskew | Netlist segment extraction and ECP5 I/O bank architecture |
| 10 | ⚪ **LOW** | Ethernet Fab | 1 nF / 2 kV Bob Smith cap C4951 in 1206 package has ~1.4 mm pad gap, 1.9 mm to GND fill | Risk of surface arc flashover during 1500 Vrms factory hi-pot test | `build/scratch/p11/moat.py`, IPC-2221B creepage standards |
| 11 | ⚪ **LOW** | Manufacturing | `mfg/jlc_rotation.py` lacks entries for narrow SOIC-8 (`SOIC-8_3.9x4.9mm_P1.27mm`) | 5 op-amps placed rotated 90°/270° if preview is missed | `mfg/jlc_rotation.py` comparison with BOM footprints |
| 12 | ⚪ **LOW** | USB FPGA | J502 has 15 kΩ pull-downs, but VBUS is tied to GND via 100k; cannot power USB devices | Port cannot operate as a standard USB Host for bus-powered devices | `gen/sheet_usb.py` |

---

## Detailed Technical Review

### 1. ADC Front End DC Operating Points, Overload & Clamping (§6.1)

#### 1.1 DC Operating Point Analysis
The THS4521 Fully Differential Amplifier (FDA) operates on a single +3.3V supply ($V_{S+} = 3.3\text{ V}$, $V_{S-} = 0\text{ V}$) with $V_{OCM} = 1.65\text{ V}$.
The single-ended input signal $V_{in}$ is applied to the non-inverting branch through $R_{g1} = 499\ \Omega$ with feedback $R_{fa} = 499\ \Omega$ to $V_{OUT-}$. The inverting branch is referenced to ground via $R_{g2} = 499\ \Omega$ with feedback $R_{fb} = 499\ \Omega$ to $V_{OUT+}$.

At the summing junctions:
$$V_{im} = V_{OUT+} \cdot \frac{R_{g2}}{R_{g2} + R_{fb}} = \frac{V_{OUT+}}{2}$$
$$V_{ip} = \frac{V_{in} \cdot R_{fa} + V_{OUT-} \cdot R_{g1}}{R_{g1} + R_{fa}} = \frac{V_{in} + V_{OUT-}}{2}$$
Since $V_{OUT+} - V_{OUT-} = V_{in}$ and $(V_{OUT+} + V_{OUT-})/2 = V_{OCM} = 1.65\text{ V}$:
$$V_{OUT+} = 1.65\text{ V} + \frac{V_{in}}{2}, \quad V_{OUT-} = 1.65\text{ V} - \frac{V_{in}}{2}$$
$$V_{ICM} = V_{im} = V_{ip} = \frac{1.65\text{ V} + V_{in}/2}{2} = 0.825\text{ V} + \frac{V_{in}}{4}$$

- For $V_{in} = -1.0\text{ V}$: $V_{ICM} = 0.825 - 0.25 = 0.575\text{ V}$.
- For $V_{in} = 0\text{ V}$: $V_{ICM} = 0.825\text{ V}$.
- For $V_{in} = +1.0\text{ V}$: $V_{ICM} = 0.825 + 0.25 = 1.075\text{ V}$.

The input common-mode range of the THS4521 on 3.3V is $-0.1\text{ V}$ to $+1.9\text{ V}$.
Under normal $\pm 1\text{ V}$ full-scale operation, $V_{ICM}$ stays between **0.575 V and 1.075 V**, providing **675 mV of margin above the negative rail** and **825 mV below the positive rail**. The sheet note's assumption that the input pins sit "around 0 to 1.6 V" is pessimistic; the resistive feedback network divides the swing by 2, centering the common mode comfortably.

#### 1.2 Overdrive and Clamping Vulnerability
The board uses BAV99 clamping diodes at the SMA connector, clamping the input to +5VA and -4.4V.
Between the clamp diodes and the THS4521 sit two non-inverting OPA1612 preamp stages, each jumper-configurable for x1 or x10 gain (total gain x1, x10, or x100). The OPA1612 runs on +5VA and -4.4V.

When an input overloads the preamp:
- At x10 gain, an input of only $-0.45\text{ V}$ drives the OPA1612 into negative saturation at its rail: $V_{o2} \approx -4.2\text{ V}$.
- At x100 gain, an input of only $-45\text{ mV}$ causes negative saturation.
- When $V_{o2} = -4.2\text{ V}$, current flows from the THS4521 input pin through $R_{g1} = 499\ \Omega$ into the OPA1612.
- The THS4521 internal ESD diode to GND turns on at $V_{IN+} \approx -0.7\text{ V}$.
- Current drawn through the ESD diode: $I = \frac{0 - (-0.7) - (-4.2)}{499\ \Omega} \approx 7.0\text{ mA}$ (70% of the 10 mA absolute maximum).
- Simultaneously, the FDA's differential feedback drives $V_{OUT+}$ to its positive rail ($\approx 3.15\text{ V}$). The inverting input $V_{IN-}$ sits at $\frac{3.15\text{ V}}{2} \approx 1.57\text{ V}$.
- The differential voltage across the inputs is:
  $$|V_{ID}| = V_{IN-} - V_{IN+} = 1.57\text{ V} - (-0.7\text{ V}) = \mathbf{2.27\text{ V}}$$
- **The Absolute Maximum Rating for $V_{ID}$ on the THS4521 is 1.0 V.**
- $2.27\text{ V}$ exceeds the maximum rating by over 2.2x. This forward-biases the internal base-emitter junctions of the input stage, resulting in permanent input offset drift, increased 1/f noise, or silicon destruction.
- The upstream BAV99 diodes provide **zero protection** against this because they sit before the x10/x100 gain stages and clamp to $\pm 5\text{ V}$.

**Recommendation:** Add a Schottky clamp (e.g., BAT54S) or back-to-back clamping diodes directly at the THS4521 inputs, or clamp the OPA1612 output between GND - 0.3V and 3.3V + 0.3V before the 499 Ω resistor.

---

### 2. DAC Output Stage & Stability (§6.2)

#### 2.1 DC Transfer & Resistor Loading
The AD9767 outputs 0 to 19.2 mA full-scale into complementary outputs $I_{OUTA}$ and $I_{OUTB}$. Each output is loaded with a 24.9 Ω resistor to ground and fed into an OPA2810 difference amplifier ($R_g = 499\ \Omega, R_f = 2\text{ k}\Omega$, nominal gain = 4.008).

Because $R_g$ (499 Ω) is in parallel with the 24.9 Ω shunt, the effective load impedance seen by each DAC output is:
$$R_{load} \approx 24.9 \parallel (499 + \dots) \approx 23.7\ \Omega$$
- At full scale ($I_A = 19.2\text{ mA}, I_B = 0$): $V_A = 0.473\text{ V}$. Feedback from the inverting input pushes reverse current through $R_{gm}$ into the 24.9 Ω load, causing $V_B = 0.018\text{ V}$ even though $I_B = 0$.
- Differential input voltage to the difference amplifier: $\Delta V = 0.473 - 0.018 = 0.455\text{ V}$.
- Output voltage: $V_{out} = 4.008 \times 0.455\text{ V} = \mathbf{\pm 1.825\text{ V}}$ open circuit ($\mathbf{\pm 0.913\text{ V}}$ into 50 Ω).
- This is 8.7% below the nominal $\pm 2.0\text{ V} / \pm 1.0\text{ V}$ stated on the schematic and silkscreen.
- Compliance voltage on AD9767 pins: swings between $0.0\text{ V}$ and $+0.473\text{ V}$, well within the $-1.0\text{ V}$ to $+1.25\text{ V}$ compliance limit.

#### 2.2 Frequency Response, Slew Rate & Cable Capacitance
- Small-signal bandwidth: SPICE simulation shows $f_{-3dB} \approx 13.5\text{ MHz}$.
- Slew rate requirement at full scale ($\pm 1.825\text{ V}$ peak, $f = 13\text{ MHz}$):
  $$\left.\frac{dV}{dt}\right|_{max} = 2\pi \times 13\text{ MHz} \times 1.825\text{ V} \approx 149\text{ V}/\mu\text{s}$$
  The OPA2810 typical slew rate is $180\text{ V}/\mu\text{s}$. Operating at 83% to 91% of maximum slew capability means full-scale 13 MHz signals will experience slew-rate induced distortion (triangular rounding).
- Cable capacitance: The 49.9 Ω series resistor $R_o$ is outside the feedback loop. Coaxial cable capacitance (e.g., 100 pF to 1000 pF) is isolated from the op-amp output pin by $R_o = 49.9\ \Omega$. Stability is maintained regardless of cable length.

#### 2.3 Unbalanced AC Feedback
The inverting feedback loop has $C_f = 2.2\text{ pF}$ in parallel with $R_f = 2\text{ k}\Omega$ ($f_z \approx 36.2\text{ MHz}$). The non-inverting input has $R_{tp} = 2\text{ k}\Omega$ to ground with **no parallel capacitor**.
Above 10 MHz, the impedance of the inverting branch falls, while the non-inverting branch remains at 2 kΩ. This destroys high-frequency CMRR, allowing high-frequency DAC glitches and common-mode clock feedthrough to couple directly to the SMA.
**Recommendation:** Add $C_{tp} = 2.2\text{ pF}$ across $R_{tp}$ to ground to match the AC impedance of the feedback network.

---

### 3. CLK IN Squarer & CLK OUT (§6.3)

#### 3.1 CLK IN Jitter Analysis
The CLK IN front-end uses an unbuffered inverter (`SN74LVC1GU04DBVR`) self-biased with a 1 MΩ feedback resistor, AC-coupled through a 10 nF capacitor. The inverted signal feeds a Schmitt trigger buffer (`SN74LVC1G17DBVR`) which drives the FPGA clock pin.

The threshold of an unbuffered CMOS inverter is $V_{th} \approx 0.5 \times V_{DD}$.
The inverter is powered directly from the main digital `+3V3` rail, which is driven by the 1.5 MHz TLV62569 switching buck and loaded by the FPGA and SDRAM.
- Switching ripple and dynamic load transients on `+3V3` are typically 10 to 20 mVpp.
- A 10 mV ripple shifts $V_{th}$ by 5 mV.
- A 10 MHz sine wave from a GPSDO at 0 dBm (0.63 Vpp into 50 Ω) has a zero-crossing slew rate of:
  $$\frac{dV}{dt} = 2\pi \times 10^7 \times 0.316\text{ V} \approx 0.020\text{ V}/\text{ns}$$
- A 5 mV threshold shift converts directly into timing jitter:
  $$\Delta t = \frac{5\text{ mV}}{0.020\text{ V}/\text{ns}} = \mathbf{250\text{ ps peak-to-peak}}$$
At 65 MSPS, 250 ps represents 1.6% of the clock period. When the FPGA PLL multiplies this reference to generate ADC/DAC clocks, this low-frequency phase noise cannot be filtered by the PLL loop bandwidth.
**Recommendation:** Power U302/U303 from a filtered rail (+3V3_ADC or an RC-filtered node: 10 Ω + 10 µF), or replace the inverter with a dedicated high-speed comparator with built-in hysteresis (e.g., TLV3501).

#### 3.2 CLK OUT Driver
The CLK OUT driver is a `SN74LVC1G17` Schmitt buffer driven by an FPGA pin through $R_o = 49.9\ \Omega$ to the SMA.
The driver's internal $R_{on} \approx 10\ \Omega$. Into 50 Ω, the output is $\approx 1.5\text{ V}$ with fast CMOS edge rates (> 1 V/ns). When driving a second board's CLK IN, the fast edges make the receiving board's squarer far less sensitive to threshold ripple than a slow sine wave.

---

### 4. Ethernet RGMII, Timing & Isolation Island (§6.4)

#### 4.1 RGMII Timing Split
- The board configures the RTL8211F PHY straps for:
  - `RXDLY = 1` (PHY adds ~2 ns internal delay to `ETH_RXC`).
  - `TXDLY = 0` (PHY does not add TX delay; gateware / LiteEth adds 2 ns phase shift via PLL).
- This is the standard, proven split for LiteEth on Lattice ECP5.

#### 4.2 Bus Skew & Bank Placement
Extracted trace lengths from FPGA to PHY:
- **TX Bus:**
  - `ETH_TXC`: 86.09 mm (1.43 ns)
  - `ETH_TX_CTL`: 91.44 mm (1.52 ns)
  - `ETH_TXD0`: 95.34 mm (1.58 ns)
  - `ETH_TXD1`: 100.72 mm (1.67 ns)
  - `ETH_TXD2`: 103.97 mm (1.72 ns)
  - `ETH_TXD3`: 109.27 mm (1.81 ns)
  - **Total TX Skew:** $109.27 - 86.09 = \mathbf{23.18\text{ mm}}$ ($\approx \mathbf{151\text{ ps}}$).
- **RX Bus:**
  - `ETH_RXC`: 60.39 mm
  - `ETH_RX_CTL`: 83.50 mm (Skew = $\mathbf{23.11\text{ mm}} \approx \mathbf{150\text{ ps}}$)
  - `ETH_RXD[3..0]`: 68.58 mm to 69.35 mm (matched within 0.77 mm / 5 ps).
- **Bank Assignment:**
  - All RGMII data and control pins are in **Bank 2 (Right)**.
  - `ETH_RXC` is assigned to ball `E8` (`PT33A, PCLKT1_1`), which is in **Bank 1 (Top)**.
  - While E8 is a true primary clock pin, routing from Bank 1 to Bank 2 IDDR cells introduces ~3 ns of clock insertion delay across the chip. LiteEth must use an internal PLL to deskew `ETH_RXC` before sampling the Bank 2 IDDR cells.

#### 4.3 Isolation Island & 1500 V Withstand
- The line side has an unbroken clearance moat:
  - All LAN signal tracks are $> 5.4\text{ mm}$ from GND fill.
  - RJ45 pins are $> 3.1\text{ mm}$ from GND fill.
- **Bottleneck:** The Bob Smith 1 nF / 2 kV capacitor (C4951) is in a **1206 package**.
  - Pad 1 is at 1.90 mm from the In1 GND plane edge.
  - Pad-to-pad distance across a 1206 footprint is only $\approx 1.4\text{ mm}$.
  - Under IPC-2221B, an uncoated external gap of 1.4 mm cannot reliably withstand a 1500 Vrms (2121 V peak) hi-pot test in standard atmospheric conditions.
  - **Recommendation:** Upgrade C4951 to an 1812 package (or mill an isolation slot beneath it) to guarantee 1500 V isolation.

---

### 5. Power Sequencing & ECP5 Configuration (§6.5)

#### 5.1 Power Sequencing
- Master SPI boot requires $V_{CCIO8} > V_{IH,flash}$ before at least one of $V_{CC}$ (1.1V) or $V_{CCAUX}$ (2.5V) reaches $V_{PORUP}$.
- $V_{CCAUX}$ is generated by an LDO fed from `+3V3` ($V_{CCIO8}$). Therefore, $V_{CCAUX}$ inherently cannot reach its POR threshold ($2.0 - 2.2\text{ V}$) until `+3V3` is already above $2.1\text{ V}$.
- However, $V_{CC}$ (1.1V) is generated by a parallel buck converter with a 1 ms soft-start ramp. It reaches its POR threshold (0.95V) in ~0.3 ms, well before `+3V3` reaches 2.3V.
- In `gen/sheet_fpga.py`, PROGRAMN and INITN have 4.7 kΩ pull-ups to +3V3 with no capacitors to ground.
- **Recommendation:** Add a 100 nF capacitor on PROGRAMN or INITN to ground to provide a guaranteed hardware reset delay during power ramp-up, eliminating any possibility of a configuration race condition.

#### 5.2 Strap & Configuration Verification
- `CFG[2:0]`: Hard-wired to `010` (Master SPI, 3.3V). Matches W25Q128JVSIQ connection.
- JTAG: TCK pulled down (4.7k), TMS/TDI/TDO pulled up (4.7k). Correct.
- Flash: WP, HOLD, CS pulled up to +3V3 with 10 kΩ. Correct.
- Dedicated CCLK driven via ECP5 `USRMCLK` primitive. Correct.

---

### 6. LM27761 Charge Pump Noise & PSRR (§6.6)

- The LM27761 consists of an inverting charge pump followed by an integrated negative LDO.
- Output voltage: $-1.22\text{ V} \times (1 + 1.3\text{M} / 499\text{k}) = \mathbf{-4.398\text{ V}}$.
- Output ripple at 2 MHz switching frequency: $\approx 2\text{ mV}_{pp}$.
- The positive rail (+5VA) has a BLM18 ferrite bead + 10 µF decoupling.
- **The negative rail (-4.4V) has NO ferrite bead and NO filter**. It feeds the OPA1612 preamps directly via a 0.4 mm trace.
- At 2 MHz, the OPA1612 PSRR- degrades to $\approx 25\text{ dB}$ (attenuation factor $\approx 18$).
- Residual 2 MHz ripple at preamp input: $\frac{2\text{ mV}}{18} \approx 110\ \mu\text{V}$.
- Preamp input noise floor: $1.1\text{ nV}/\sqrt{\text{Hz}} \times \sqrt{20\text{ MHz}} \approx 4.9\ \mu\text{V}_{RMS}$.
- The 2 MHz switching spur is **over 20 times larger than the broadband noise floor**, introducing a distinct spur in the ADC spectrum.
- **Recommendation:** Insert a ferrite bead (BLM18KG601SN1D) and 10 µF ceramic capacitor on the -4.4V output before routing to the analog strip.

---

### 7. Generated Layout Analysis (§6.7)

#### 7.1 ADC Input Layout Asymmetry (Critical Finding)
Extracted track lengths from the 33 Ω / 22 pF filter to the AD9238 converter pins:
- **Channel A:**
  - `VIN+_A`: 4.64 mm
  - `VIN-_A`: 14.39 mm
  - **Length Difference:** $\mathbf{9.75\text{ mm}}$
- **Channel B:**
  - `VIN+_B`: 14.52 mm
  - `VIN-_B`: 5.59 mm
  - **Length Difference:** $\mathbf{8.93\text{ mm}}$

At 65 MSPS, the switched-capacitor input stages inject high-speed charge kickback into the trace network. A 10 mm length difference represents approximately 10 nH of uncompensated series inductance. This imbalance causes differential ringing and phase skew during the 7.7 ns sampling aperture, degrading HD2, SFDR, and channel-to-channel gain matching for the cross-correlation experiment.
**Recommendation:** Reroute the ADC input traces as tightly coupled, length-matched differential pairs directly between the filter caps and the AD9238 pins.

#### 7.2 Signals Crossing Split Power Planes on In4 (Critical Finding)
Layer In4 is a split power plane (+1V1 core patch, +5V corridor, +3V3 plane, GND fill).
Traces on In3 and B.Cu reference In4.
Geometric analysis identified several high-speed signals crossing the plane boundaries without return path stitching:
1. `/DAC/DAC_CLK1` (up to 125 MHz clock) crosses the +1V1 / +3V3 split on In3.Cu at $(69.9, 61.7)$, $(69.6, 68.0)$, and $(66.0, 102.3)$.
2. `/DAC/DAC_WRT1` crosses the +1V1 split on In3.Cu at $(68.8, 68.0)$ and $(66.0, 100.7)$.
3. `/DAC/DAC_P2_D12` crosses the +1V1 split on B.Cu three times.
4. `CCLK/MCLK` (flash clock) and `FLASH_HOLD/IO3` cross the +1V1 split on In3.Cu.
5. `SD_D1` and `SD_D2` cross the +5V corridor boundary on B.Cu at $(109.0, 86.0)$ and $(106.4, 86.0)$.

Crossing a plane split forces the high-frequency return current to divert through remote bypass capacitors, creating large inductive loops, radiated EMI, and direct noise injection into the FPGA 1.1V core rail.
**Recommendation:** Move `DAC_CLK1` and `DAC_WRT1` to F.Cu or In2.Cu (which reference the solid In1 GND plane), or reroute them to avoid crossing the 1.1V power polygon on In4.

#### 7.3 SDRAM Bus Skew
- Clock length: `SDRAM_CLK` = 16.75 mm.
- DQ bus lengths: 20.47 mm (`DQ7`) to 30.87 mm (`DQ15`).
- Maximum skew across the DQ bus: $30.87 - 20.47 = \mathbf{10.40\text{ mm}}$ ($\approx \mathbf{68\text{ ps}}$).
- At 100 MHz SDR SDRAM (10.0 ns period), 68 ps is $< 0.7\%$ of the clock period. This is well within SDR SDRAM timing margins.

#### 7.4 GPDI (HDMI) Intra-Pair Skew
- `GPDI_CK`: 1.06 mm skew (7 ps)
- `GPDI_D0`: 1.05 mm skew (7 ps)
- `GPDI_D1`: 2.18 mm skew (14 ps)
- `GPDI_D2`: 1.39 mm skew (9 ps)
- The ~2.1 mm skew on D1 arises because the 22 nF coupling capacitors (C6401-C6408) are placed in two staggered columns (x = 146.1 mm and 148.2 mm). The 14 ps skew is well within the HDMI 0.15 UI allowance (~200 ps at 720p60).

---

### 8. Mechanical Integration & Enclosure (§6.9)

#### 8.1 USB-C and HDMI Connector Recess
Connector bounding box coordinates on the right board edge ($x = 158.00\text{ mm}$):
- `J401` (RJ45): $x_{max} = \mathbf{158.84\text{ mm}}$ (protrudes 0.84 mm past board edge)
- `J303, J304` (PMODs): $x_{max} = \mathbf{158.50\text{ mm}}$ (protrude 0.50 mm past board edge)
- `J501, J502` (USB-C): $x_{max} = \mathbf{157.68\text{ mm}}$ (**recessed 0.32 mm** inside board edge)
- `J503` (mini-HDMI): $x_{max} = \mathbf{157.82\text{ mm}}$ (**recessed 0.18 mm** inside board edge)

When the board slides into the Hammond 1455Q1601 extrusion and the end plate (1.5 mm thick aluminum) is mounted:
- If the board is stopped by the RJ45 face hitting the end plate, the USB-C receptacle face sits:
  $$d = (158.84 - 157.68) + 1.50\text{ mm} = \mathbf{2.66\text{ mm}}$$
  behind the outer surface of the end plate.
- Standard USB-C plugs have a metal shroud length of 6.50 mm and require 5.50 to 6.00 mm insertion depth.
- With a 2.66 mm recess, only $6.50 - 2.66 = \mathbf{3.84\text{ mm}}$ of plug can enter the receptacle before the cable overmould hits the aluminum end plate.
- **Result:** Standard USB-C cables will fail to fully engage the internal retention springs or make reliable pin contact!
- **Recommendation:** Shift J501, J502, and J503 eastward by 1.2 to 1.5 mm so their metal receptacle lips protrude ~0.5 to 0.8 mm past the board edge, flush with the RJ45 jack.

#### 8.2 Vertical Slot Clearance
- Setting `PCB_TOP_ABOVE_FLOOR = 8.0 mm` (second slot) provides 6.4 mm of clearance under the board.
- The tallest bottom component is the G2406S magnetics module (T401), which is $4.0 \pm 0.4\text{ mm}$ tall. This leaves 2.4 mm of clearance to the extrusion floor, safely preventing shorts.

---

### 9. Manufacturing Package & Footprints (§6.8)

1. **Missing SOIC-8 CPL Rotation:**
   `mfg/jlc_rotation.py` contains a 270° correction for wide SOIC-8 (`SOIC-8_5.3x5.3mm_P1.27mm`), but lacks an entry for narrow SOIC-8 (`SOIC-8_3.9x4.9mm_P1.27mm`).
   Five critical op-amps (U101, U102, U105, U202, U203) use this footprint. In JLCPCB SMT tape & reel, narrow SOIC-8 parts follow the same EIA-481 feeder orientation and require a 270° offset. Without this entry, the generated CPL leaves them at 0° native KiCad orientation.
2. **Via-in-Pad Specs:**
   Via-in-pad under the BGA (0.3/0.15 mm) and bottom-side 0402 caps requires epoxy fill and cap (type VII). Ensure JLCPCB PO specifies "Via-in-pad: filled & capped".

---

## What Was Checked and Approved

1. **Power Regulators:** Feedback divider arithmetic for 3.33V (U601) and 1.10V (U602) bucks is exact; LP5907 (2.5V VCCAUX) and TPS7A2033 (3.3V ADC/DAC analog rails) are correct; polyfuses (2A on VBUS, 0.5A on HDMI) and Schottky diode on 5V IN are properly sized.
2. **AD9238 Dual ADC:** Pinout verified against Table 6; internal 1.0V reference configured via SENSE = GND; SHARED_REF and MUX_SELECT tied high; REFT/REFB decoupling (10 µF + 100 nF) matches datasheet recommendations.
3. **AD9767 Dual DAC:** Pinout verified against Table 6 / Figure 5; 2 kΩ FSADJ resistors correctly set 19.2 mA full scale; REFIO 100 nF bypass is correct; MODE and SLEEP straps are correct.
4. **RTL8211F Gigabit Ethernet:** Pinout and strap table verified; CFG_EXT = 1, CFG_LDO = 00 (3.3V I/O), PHYAD = 1, TXDLY = 0, RXDLY = 1; SWPA4030 2.2 µH inductor rated for 2.95 A (> 600 mA requirement).
5. **FT2232HL USB Interface:** Dual-channel JTAG / UART pinout verified; 12 kΩ reference resistor; 1.8V VREGOUT filtering to VCORE and VPHY/VPLL.
6. **BGA Decoupling:** Via-in-pad 0402 capacitors on the bottom side span power and ground ball pairs directly, achieving minimal loop inductance.
7. **KiCad DRC & ERC:** 0 DRC errors, 0 unconnected nets, 2 benign dangling ground return via warnings; 0 ERC violations.

---

## Comparison with Author's Response and Other Reviews

*(Consulted after completing and writing down our independent review, per Ground Rule 6)*

### 1. What We Agree With
- **Author's Fixes in Builds 21–25:** We confirmed that the 11 codeless SMT parts, the 8 mismatched LCSC codes (including the 1206 resistor on 0402 pads and the 27 kΩ divider resistor), the HPD divider fix (4.7k), the PHY power inductor upgrade (SWPA4030), and the board dimension expansion to 158 x 119 mm were correctly implemented in the current build 25 tree.
- **DAC Output Swing Discrepancy (Agreement with Grok 4.7 & CopilotSDK):** All three reviews confirmed that the actual output swing is $\pm 1.825\text{ V}$ open circuit and $\pm 0.913\text{ V}$ into 50 Ω due to the 499 Ω loading on the 24.9 Ω terminations, and that the OPA2810 is operating near its slew limit at 13 MHz full-scale.
- **LM27761 Charge Pump Noise (Agreement with Grok 4.7):** Grok correctly identified that the -4.4V rail lacks a ferrite feed, allowing 2 MHz charge pump ripple to directly modulate the OPA1612 stages and corrupt the Johnson noise cross-correlation measurement.
- **Ethernet 1500 V Withstand Rating (Agreement with CopilotSDK & Grok 4.7):** CopilotSDK and Grok correctly noted that C4951 is an ordinary 1206 MLCC rather than a certified safety capacitor, and the 1.4 mm pad gap cannot guarantee passing a 1500 Vrms hi-pot test without risk of arc-over.
- **CLK IN Squarer Jitter (Agreement with CopilotSDK):** CopilotSDK noted that the self-biased unbuffered CMOS inverter has an uncontrolled threshold that drifts with +3V3 buck noise, compromising its use as a precision reference.

### 2. What We Dispute
- **Grok 4.7's Assessment of THS4521 Overload Protection:** Grok claimed: *"The OPA1612 can swing to about 0.6 V of the −4.4 V rail... Differential input stays under the 1 V abs-max because of the 499 Ω networks. I would not respin for this."*  
  **We mathematically dispute this conclusion.** When the OPA1612 saturates to -4.2V, $V_{IN+}$ is clamped to -0.7V by the THS4521 ESD diode. Because $V_{IN-}$ is held at +1.57V by the output feedback loop, the differential voltage across the pins is $|V_{ID}| = 1.57 - (-0.7) = \mathbf{2.27\text{ V}}$, which **more than doubles the 1.0 V absolute maximum rating**. In a student laboratory environment where gain can be set to x10 or x100, student overdrive will permanently damage or degrade the THS4521. This is a real hardware failure mechanism, not merely an unquantified distortion issue.

### 3. What Other Reviews Missed (Key Discoveries from This Review)
1. **ADC Input Trace Length Asymmetry (9.75 mm Ch A / 8.93 mm Ch B):** Neither CopilotSDK nor Grok 4.7 measured the individual routed trace lengths connecting the filter network to the AD9238 pins. We discovered that `VIN-_A` is 14.39 mm while `VIN+_A` is 4.64 mm. This creates an uncompensated ~10 nH differential inductance imbalance right at the ADC sampling switches, severely degrading high-frequency kickback settling and SFDR.
2. **125 MHz DAC Clocks Crossing In4 Power Plane Splits:** Neither reviewer examined the return current reference planes. We mapped the geometry and discovered that `DAC_CLK1` (up to 125 MHz clock on In3) crosses the +1V1 core power plane boundary on In4 **three times**, and `DAC_WRT1` crosses **twice**, forcing return currents across plane gaps and injecting 125 MHz switching hash into the FPGA core supply.
3. **Mechanical USB-C Recess in Hammond Enclosure:** Neither reviewer evaluated connector protrusion relative to the end plate. We discovered that the USB-C receptacles sit recessed 0.32 mm inside the board edge (2.66 mm behind the end plate face), while RJ45 and Pmods stick out past the board edge. Because standard USB-C plugs require 5.5 to 6.0 mm of insertion depth, standard cables will collide with the aluminum plate and fail to latch properly.
4. **Unbalanced Feedback in DAC Difference Amplifier:** Both other reviews missed that the non-inverting input of the OPA2810 has no capacitor across $R_{tp} = 2\text{ k}\Omega$, destroying AC common-mode rejection above 10 MHz and letting high-frequency DAC glitches feed straight to the output.
5. **Missing CPL Rotation for Narrow SOIC-8:** Neither reviewer noticed that `mfg/jlc_rotation.py` omitted narrow SOIC-8, which would cause all five OPA1612 and OPA2810 op-amps to be assembled with incorrect rotation if not manually corrected in the JLCPCB preview.

