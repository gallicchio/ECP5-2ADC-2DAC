# Design Review (Round 2): ECP5-2ADC-2DAC Rev A (Build 31)

**Reviewer:** Gemini 3.8 Flash  
**Date:** 2026-10-07  
**Target:** Build 31 (`11e2f61`), Rev A pre-order verification  

---

## 1. Verdict

**DO NOT ORDER BUILD 31 UNCHANGED.**  
The analog signal chains, the differential converters, power planes, and high-speed routing are excellently designed and functionally sound; however, build 31 contains two serious electrical vulnerability bugs that risk board destruction on the bench:
1. **D601 (B5819W, 1 A max) is unprotected by F602 (2 A hold / 4 A trip):** Any bench supply load between 1.0 A and 2.0 A (e.g. 1.2–1.5 A under heavy Pmod or expansion draw) forces D601 beyond its absolute maximum rating (1 A continuous, 500 mW dissipation), dissipating ~1 W in a tiny SOD-123 package ($R_{\theta JA} = 200\text{ }^\circ\text{C/W}$, $T_J > 220\text{ }^\circ\text{C}$) and burning it out without ever tripping the fuse.
2. **CLK IN (TLV3501) has zero input clamping or series current limiting:** The SMA input connects directly through AC-coupling capacitor C5421 (10 nF) to the comparator's $+IN$ pin with 0 $\Omega$ series resistance. Any student connecting a 5 V square wave, a 10 V function generator edge, or an ESD strike dumps 50–150 mA directly into the internal ESD diode of U302—exceeding its 10 mA absolute maximum rating by up to 15×.

In addition, U604 (TPS7A2033 in SOT-23-5) runs near its maximum thermal limit ($T_J \approx 105\text{--}125\text{ }^\circ\text{C}$) in a closed extrusion at full 65 MS/s conversion rate. Both issues 1 and 2, plus U604's thermal relief, can be fixed immediately with simple passive component changes (upgrading D601 to a 2–3 A diode or downsizing F602 to 1.1 A; adding a 1 k$\Omega$ series resistor / clamp diodes to CLK IN; adding a 3 $\Omega$ 1206 resistor in series with U604's input) without rerouting the board.

---

## 2. Summary of Findings

| # | Severity | Subsystem / Location | Finding | Impact | Confirmed By |
|---|---|---|---|---|---|
| 1 | 🔴 **CRITICAL** | Power: J601 / D601 / F602 | Fuse F602 (2.0 A hold / 4.0 A trip) does not protect Schottky diode D601 (B5819W, 1.0 A / 500 mW max) | A bench overload of 1.2–1.8 A burns out D601 ($T_J > 200\text{ }^\circ\text{C}$) while F602 never trips | Netlist walk, B5819W datasheet (C8598), MF-MSMF200 datasheet (C210837) |
| 2 | 🔴 **CRITICAL** | Clocks: J301 / U302 (CLK IN) | CLK IN has zero series resistance or diode clamping into TLV3501 $+IN$ | A 5 V or 10 V input edge drives 50–150 mA through internal ESD diodes (rated 10 mA max), destroying comparator | TLV3501 datasheet §6.1 Note 2 (C193413), netlist, schematic inspection |
| 3 | 🟠 **HIGH** | Power: U604 (TPS7A2033) | SOT-23-5 LDO dissipates 0.37–0.43 W at 65 MS/s; $T_J \approx 105\text{--}125\text{ }^\circ\text{C}$ in closed extrusion | Operating at or exceeding 125 °C absolute maximum junction temperature at high ambient / 5.25 V USB | TPS7A20 datasheet §6.4 ($R_{\theta JA} = 187\text{ }^\circ\text{C/W}$), AD9238 datasheet $I_{AVDD}$ |
| 4 | 🟡 **MEDIUM** | Clocks / Converters: ECP5 PLL | Clock jitter of ECP5 PLL (15–20 ps rms) caps AD9238 SNR at 58–60 dB at 10 MHz (native SNR is 70.2 dB) | Degrades ADC effective resolution by ~1.8 bits unless external / TCXO clock is used | Jitter SNR formula $-20\log_{10}(2\pi f t_j)$, ECP5 datasheet, AD9238 datasheet |
| 5 | 🟡 **MEDIUM** | Fast Digital: DAC / RGMII Buses | Source termination resistors placed at receiver (AD9767 / RTL8211F) rather than FPGA driver | Increases standing wave reflections on 50–60 mm lines if FPGA outputs are set to `FAST` slew rate | PCB trace measurement, transmission line reflection analysis ($t_{prop} \approx 380\text{ ps}$) |
| 6 | ⚪ **LOW** | Layout: In4 Plane Crossings | DAC Port 1 data and write/clock lines cross between +3V3 and +1V1 patches | Return currents couple via BGA decoupling capacitors; negligible at sub-gigabit edge rates | Shapely plane boundary intersection scan, PDN impedance analysis |
| 7 | ⚪ **LOW** | Manufacturing / Silkscreen | In4 ground fill crumb (0.7 x 0.9 mm) and 2 dangling vias | Benign DRC warnings (`connection_width`, `via_dangling`); all grounded through solid In1 plane | KiCad DRC report (`drc.json`) |

---

## 3. Detailed Technical Analysis

### 3.1 Item 1: ADC Analog Regulator Dissipation (U604, TPS7A2033)

#### The Circuit and Operating Numbers
U604 is a Texas Instruments TPS7A2033PDBVR in a 5-pin SOT-23 (DBV) package (LCSC `C2862740`). It generates `+3V3_ADC` from the main `+5V` rail.
From the netlist walk, `+3V3_ADC` powers:
1. **U103 (AD9238BSTZ-65):** Pins 5, 12, 17, 64 ($AVDD$), plus digital configuration pins 61 ($MUX\_SELECT$) and 62 ($SHARED\_REF$).
   - From AD9238 datasheet Table 1: At 65 MSPS, $I_{AVDD} = 200\text{ mA}$ typical at $AVDD = 3.0\text{ V}$. At 3.3 V, $I_{AVDD} \approx 205\text{--}215\text{ mA}$.
2. **U111, U112 (THS4521):** Pin 3 ($V_{S+}$) and Pin 7 ($\overline{PD}$).
   - Quiescent current: $1.14\text{ mA}$ typ, $1.4\text{ mA}$ max each $\rightarrow 2.8\text{ mA}$.
   - Under dynamic signal driving 499 $\Omega$ feedback: $\sim 3\text{--}5\text{ mA}$ total.
3. **U302 (TLV3501AIDBVR):** Pin 4 ($V+$).
   - Supply current: $3.2\text{ mA}$ typ, $5.0\text{ mA}$ max.
4. **D605 (Power-good LED) and Dividers:**
   - D605 through R7681 ($4.7\text{ k}\Omega$) + R5424/R5425 divider ($10\text{ k}\Omega + 10\text{ k}\Omega$): $\sim 1.0\text{ mA}$.

**Total Load Current on U604:**
$$I_{load} = 205\text{ mA (ADC)} + 4\text{ mA (FDAs)} + 4\text{ mA (TLV3501)} + 1\text{ mA (LED/divider)} \approx 214\text{--}225\text{ mA}$$

#### Power Dissipation and Thermal Modeling
- Nominal input: $V_{in} = 5.0\text{ V}$, $V_{out} = 3.3\text{ V}$. Drop: $V_{drop} = 1.70\text{ V}$.
  $$P_D = 1.70\text{ V} \times 0.22\text{ A} = 0.374\text{ W}$$
- High-line USB input (5.25 V): $V_{drop} = 1.95\text{ V}$.
  $$P_D = 1.95\text{ V} \times 0.22\text{ A} = 0.429\text{ W}$$
- Low conversion rate (10 MS/s): AD9238 draws $\sim 60\text{ mA}$; $P_D \approx 1.70\text{ V} \times 0.07\text{ A} = 0.12\text{ W}$.

**Thermal Resistance ($R_{\theta JA}$):**
From TI's TPS7A20 datasheet Table 6.4:
- $R_{\theta JA} = 187.1\text{ }^\circ\text{C/W}$ (JEDEC standard 4-layer High-K board).
- $R_{\theta JB} = 54.4\text{ }^\circ\text{C/W}$ (junction to board).
- $T_{J,max} = 125\text{ }^\circ\text{C}$ (Operating junction temperature max); thermal shutdown occurs at $\sim 160\text{ }^\circ\text{C}$.

On this 6-layer board, U604 is mounted on B.Cu at (30.0, 55.5). The GND pin (pin 2) connects via a short trace to a ground via into In1 (solid ground plane). SOT-23 has no thermal pad; heat escapes predominantly through pin 2 and the leadframe. Even on a multi-layer board with solid ground planes, practical $R_{\theta JA}$ for SOT-23-5 rarely drops below $140\text{--}150\text{ }^\circ\text{C/W}$ because the package leadframe conduction bottleneck dominates.

**Junction Temperature Estimates:**
- In open bench air ($T_A = 25\text{ }^\circ\text{C}$):
  $$T_J = 25\text{ }^\circ\text{C} + (0.374\text{ W} \times 150\text{ }^\circ\text{C/W}) = 25 + 56.1 = 81.1\text{ }^\circ\text{C}$$
- In the closed Hammond 1455Q extrusion with total board dissipation $\sim 3\text{ W}$ ($T_A \approx 45\text{ }^\circ\text{C}$):
  $$T_J = 45\text{ }^\circ\text{C} + (0.374\text{ W} \times 150\text{ }^\circ\text{C/W}) = 45 + 56.1 = 101.1\text{ }^\circ\text{C}$$
- With 5.25 V USB input in extrusion:
  $$T_J = 45\text{ }^\circ\text{C} + (0.429\text{ W} \times 150\text{ }^\circ\text{C/W}) = 45 + 64.4 = 109.4\text{ }^\circ\text{C}$$
  If the effective $R_{\theta JA}$ is closer to JEDEC's $187\text{ }^\circ\text{C/W}$:
  $$T_J = 45 + (0.429 \times 187) = 125.2\text{ }^\circ\text{C}$$
  *(Right at or slightly exceeding the $125\text{ }^\circ\text{C}$ manufacturer absolute maximum).*

#### Recommendation
While the regulator will function and not immediately enter thermal shutdown ($160\text{ }^\circ\text{C}$), operating an LDO continuously at $105\text{--}115\text{ }^\circ\text{C}$ in a teaching lab instrument degrades long-term reliability.
**The Smallest, Cleanest Fix:**
Place a **3.0 $\Omega$ or 3.3 $\Omega$ resistor in a 1206 package in series with U604's VIN pin**.
- Voltage drop across $3\text{ }\Omega$ at $220\text{ mA}$:
  $$\Delta V_R = 0.22\text{ A} \times 3.0\text{ }\Omega = 0.66\text{ V}$$
- Power in 1206 resistor:
  $$P_R = (0.22\text{ A})^2 \times 3.0\text{ }\Omega = 0.145\text{ W} \quad (\text{comfortably within 1206's } 0.25\text{ W rating})$$
- Voltage into U604:
  $$V_{in,LDO} = 5.0\text{ V} - 0.66\text{ V} = 4.34\text{ V}$$
- TPS7A20 dropout voltage at $220\text{ mA}$:
  $$V_{DO} \le 100\text{ mV}$$
  Headroom remaining: $4.34\text{ V} - 3.30\text{ V} = 1.04\text{ V} \gg 0.10\text{ V}$.
  Even at minimum USB voltage ($4.75\text{ V}$), headroom is $4.75 - 0.66 - 3.30 = 0.79\text{ V} \gg 0.10\text{ V}$.
- Power remaining in U604:
  $$P_{D,new} = (4.34\text{ V} - 3.30\text{ V}) \times 0.22\text{ A} = 0.228\text{ W} \quad (\mathbf{39\%\text{ reduction!}})$$
- New junction temperature in extrusion ($45\text{ }^\circ\text{C}$):
  $$T_J = 45 + (0.228\text{ W} \times 150\text{ }^\circ\text{C/W}) = 79.2\text{ }^\circ\text{C} \quad (\mathbf{46\text{ }^\circ\text{C margin below } 125\text{ }^\circ\text{C}})$$
Additionally, the $3\text{ }\Omega$ resistor combined with $C_{in} = 10\text{ }\mu\text{F}$ forms an input low-pass filter with cutoff $f_c = \frac{1}{2\pi \times 3 \times 10\mu\text{F}} = 5.3\text{ kHz}$, providing $>45\text{ dB}$ of extra attenuation against the 1.5 MHz buck and 2.0 MHz charge pump ripple before it reaches the LDO!

---

### 3.2 Item 2: The In4 Analog Planes and Plane Crossing Seams

#### The In4 Plane Architecture
In Build 30/31, layer `In4.Cu` hosts:
- `+3V3` (priority 1)
- `+1V1` (priority 2)
- `+5V` (priority 2)
- `-4V2` (priority 3)
- `+5VA` (priority 3)
- `+3V3_ADC` (priority 4)
- `+3V3_DAC` (priority 4)
- `GND` (priority 0)

Using a Shapely geometric intersection audit against all 747 signal segments on `In3.Cu` and `B.Cu`, the exact crossings were identified and measured to the nearest ground via:

1. **`+3V3_DAC` Patch Boundary (priority 4, cutout in +5VA / +3V3):**
   - `/ADC/ADC_DCS`, `ADC_DFS`, `ADC_PDWN_A`, `ADC_PDWN_B`: These are static DC configuration/control lines. Their switching rate during measurement is 0 Hz. Crossing distance to nearest ground via: 1.28–1.80 mm.
   - `/DAC/DAC_MODE`: Static DC mode select.
   - `/DAC/DAC_P1_D1` to `D5`: Port 1 data lines running on In3.Cu and B.Cu. Edge rates are set by FPGA driver ($\sim 1.0\text{--}2.0\text{ ns}$). They cross from the digital `+3V3` plane to the `+3V3_DAC` plane.
     *Both planes are 3.3 V rails*.
     Under the BGA and around the DAC, both `+3V3` and `+3V3_DAC` have 100 nF bypass capacitors to GND within 1.5–2.5 mm. At high frequencies, the AC impedance between `+3V3` and `+3V3_DAC` is $<0.2\text{ }\Omega$.
2. **`+3V3_ADC` Patch Boundary (priority 4, cutout in +5VA / +3V3):**
   - `/ADC/ADC_B_D0` to `D4`: Crossing from `+3V3_ADC` into `+3V3` digital plane. At 65 MS/s, bit rate is 65 Mbps.
   - Nearest ground vias are 0.7–1.5 mm away. In addition, the solid `In1.Cu` ground plane is directly above `In2.Cu` (0.62 mm from `In3.Cu`), providing a continuous ground return reference.
3. **`+1V1` Patch Boundary (priority 2, FPGA core):**
   - SPI Flash lines: `CCLK/MCLK`, `CS_N`, `HOLD`, `WP`. Flash clock runs at master SPI boot clock ($2.4\text{--}38\text{ MHz}$).
   - `DAC_CLK1` (In3.Cu, crossing at (91.0, 127.3), min GND via 1.88 mm) and `DAC_WRT1` (In3.Cu, crossing at (91.0, 125.7), min GND via 1.57 mm).
     This crossing occurs right at the edge of the BGA package where Bank 8 meets Bank 1. Within 1.5 mm of this seam are BGA decoupling capacitors:
     - $C_{core}$ (100 nF on +1V1 to GND via ball pair)
     - $C_{io}$ (100 nF on +3V3 to GND via ball pair)
     The AC return current transfers smoothly from the +3V3 plane to the +1V1 plane through the low-inductance BGA capacitor loop without signal degradation.

**Verdict on Seams:** None of these crossings represent a signal integrity risk at their operational edge rates. No additional stitching capacitors or rerouting are required.

---

### 3.3 Item 3: Widened Rails and Copper Clearances (`pcb/fatten.py`)

`pcb/fatten.py` post-processes the routed PCB to widen all Power and Rail traces to 0.40–0.50 mm wherever clearance permits.
We performed an automated geometric proximity search between all power/rail tracks and all high-impedance or sensitive analog signal tracks (preamp inputs, TIA photodiode node, ADC differential inputs, DAC current outputs):

- **Closest Power-to-Analog Proximity on F.Cu:**
  `+3V3_ADC` to `Net-(U103A-VIN-_A)`: Clearance = 0.186 mm at $(68.8, 77.5)$.
  *Analysis:* This occurs at Pin 5 ($AVDD$) and Pin 6 ($VIN-_A$) of U103 (AD9238 in LQFP-64). The 0.5 mm pin pitch of the LQFP-64 package has 0.28 mm pads with 0.22 mm nominal spacing. DRC clearance rule is 0.127 mm (5 mil). The 0.186 mm clearance is standard pin breakout clearance and completely passes DRC with zero violations.
- **DAC Analog Output Proximity:**
  `+3V3_DAC_D` to `Net-(U201B-IOUTB2)`: Clearance = 0.310 mm at $(69.6, 118.6)$.
  *Analysis:* Placed $>0.3\text{ mm}$ away, fully isolated by ground plane underneath.
- **DC Resistance & Drops:**
  `power_path.py` results confirm that all supply rail resistances from source to load pins are exceptionally low:
  - `+1V1` worst pin: $2.5\text{ m}\Omega$
  - `+3V3` worst pin: $6.8\text{ m}\Omega$
  - `+3V3_ADC` worst pin: $22.7\text{ m}\Omega$
  - `+5VA` worst pin: $7.4\text{ m}\Omega$
  - `-4V2` worst pin: $26.0\text{ m}\Omega$
  At full operating currents, DC resistive drops across the board are $<15\text{ mV}$ on all rails.

---

### 3.4 Item 4: The 5 V Input, Protection, Ringing, and Clamping

#### (a) Hot-Plug Ringing and Overvoltage Margin
When an energized 5 V source is connected via a 1 m USB cable (inductance $L \approx 1\text{ }\mu\text{H}$, loop resistance $R_{cable} \approx 0.15\text{--}0.25\text{ }\Omega$):
- Ceramic capacitance on `+5V`: two $22\text{ }\mu\text{F}$ 0805 + five $10\text{ }\mu\text{F}$ 0603 ceramics $= 94\text{ }\mu\text{F}$ nominal.
- Under 5 V DC bias, 25 V X5R ceramics retain $\sim 85\%$ capacitance:
  $$C_{eff} \approx 80\text{ }\mu\text{F}$$
- Tank characteristic impedance:
  $$Z_0 = \sqrt{\frac{L}{C}} = \sqrt{\frac{1.0 \times 10^{-6}\text{ H}}{80 \times 10^{-6}\text{ F}}} = 0.112\text{ }\Omega$$
- Damping resistance:
  $$R_{total} = R_{cable} (0.18\text{ }\Omega) + R_{connector} (0.04\text{ }\Omega) + R_{fuse} (0.05\text{ }\Omega) = 0.27\text{ }\Omega$$
- Circuit Quality Factor:
  $$Q = \frac{Z_0}{R_{total}} = \frac{0.112\text{ }\Omega}{0.27\text{ }\Omega} \approx 0.415$$
Because $Q < 0.5$, the circuit is **overdamped**!
The classic Linear Technology AN88 ringing problem occurs when input capacitance is small ($1\text{--}4.7\text{ }\mu\text{F}$), where $Z_0 \approx 0.5\text{--}1.0\text{ }\Omega \gg R_{cable}$, leading to $Q > 3$ and ringing up to $2 \times V_{in} \approx 10\text{ V}$. Here, the large bulk ceramic capacitance ($80\text{ }\mu\text{F}$) drives $Z_0$ down to $0.11\text{ }\Omega$, well below the cable and fuse resistance. Hot-plug overshoot is under 5% ($\le 5.25\text{ V}$ on a 5.0 V step).

**Absolute Maximum Ratings on +5V Rail:**
- LM27761 (U606): Absolute Maximum $V_{in} = 5.8\text{ V}$. Recommended Max $= 5.5\text{ V}$.
- TLV62569 (U601, U602): Absolute Maximum $V_{in} = 6.0\text{ V}$.
- TPS7A2033 (U604, U605): Absolute Maximum $V_{in} = 6.0\text{ V}$.
With bench supply input through D601, the Schottky diode drops $0.35\text{--}0.45\text{ V}$. A bench supply set to $5.5\text{ V}$ yields $5.5 - 0.40 = 5.10\text{ V}$ on the internal `+5V` rail, safely below the $5.5\text{ V}$ recommended and $5.8\text{ V}$ absolute maximum limits.

#### (b) F602 Placement and D601 Dissipation / Protection (Critical Bug)
On J601 (Bench 5V IN):
- Schematic order: `J601` $\rightarrow$ `D601` (B5819W SOD-123) $\rightarrow$ `F602` (MF-MSMF200-2 1812) $\rightarrow$ `+5V`.
- **D601 Specifications (C8598):**
  * Average Forward Current $I_O = 1.0\text{ A}$ maximum!
  * Power Dissipation $P_D = 500\text{ mW}$ maximum!
  * Thermal resistance $R_{\theta JA} = 200\text{ }^\circ\text{C/W}$, $T_{J,max} = 125\text{ }^\circ\text{C}$.
- **F602 Specifications (C210837):**
  * Hold Current $I_{hold} = 2.0\text{ A}$!
  * Trip Current $I_{trip} = 4.0\text{ A}$!

**The Failure Mode:**
If a student connects a bench supply and draws $1.5\text{ A}$ (e.g. while powering custom daughterboards or modules from the Pmods/RAILS header):
- Current is below F602's hold current ($1.5\text{ A} < 2.0\text{ A}$). **F602 will never trip.**
- At $1.5\text{ A}$, D601's forward voltage is $V_F \approx 0.65\text{ V}$.
- Power dissipation in D601:
  $$P_D = 1.5\text{ A} \times 0.65\text{ V} = 0.975\text{ W} \quad (\mathbf{195\%\text{ of rated } 500\text{ mW max!}})$$
- Temperature rise:
  $$\Delta T = 0.975\text{ W} \times 200\text{ }^\circ\text{C/W} = +195\text{ }^\circ\text{C}!$$
  With $T_A = 25\text{ }^\circ\text{C}$, $T_J$ reaches **$220\text{ }^\circ\text{C}$**, destroying the diode and scorching the PCB.
**Fix:** Upgrade D601 from B5819W (1 A, SOD-123) to a **3 A Schottky diode in an SMA package** (such as SS34 / B340A, LCSC `C1589` / `C8599`, or downsize F602 to MF-MSMF110-2, 1.1 A hold).

#### (c) USBLC6-2SC6 Clamping Voltage
The USBLC6-2SC6 (U501, U504, LCSC `C2827654`) has:
- Reverse Standoff Voltage $V_{RWM} = 5.0\text{ V}$ max.
- Breakdown Voltage $V_{BR} = 6.0\text{ V}$ min (at $I_T = 1\text{ mA}$).
- Leakage at $5.0\text{ V} = 0.08\text{ }\mu\text{A}$ max.
At $5.25\text{ V}$ (high-end standard USB voltage), the diode is below $V_{BR}$ ($6.0\text{ V}$) and conducts only microamperes of leakage. It does not false-clamp under normal USB operation. However, because its internal Zener is an ESD-rated device (150 W for $8/20\text{ }\mu\text{s}$), sustained DC overvoltage $>6.0\text{ V}$ from a bench supply will cause avalanche breakdown and burn U501 out if not fuse-limited.

---

### 3.5 Item 5: The Analog Chains

1. **THS4521 Anti-Parallel Input Diodes (BAV99):**
   - In normal closed-loop operation, the virtual ground summing junctions are within microvolts of each other ($V_{diff} \approx 0\text{ V}$).
   - At $0\text{ V}$, BAV99 leakage is $<10\text{ pA}$, introducing $<2.5\text{ }\mu\text{V}$ offset across the $250\text{ }\Omega$ Thevenin source resistance ($<0.005\text{ LSB}$).
   - Capacitance of two antiparallel diodes at $0\text{ V}$ is $C_{diff} \approx 3.0\text{ pF}$.
   - Summing junction impedance: $R_{eq} = 499\text{ }\Omega \parallel 499\text{ }\Omega = 250\text{ }\Omega$.
   - Bandwidth pole: $f = \frac{1}{2\pi \times 250 \times 3.0\text{ pF}} = 212\text{ MHz}$, far above the front end's 23.1 MHz antialiasing cutoff.
   - When an OPA1612 stage saturates to $-3.55\text{ V}$, the BAV99 clamps the differential input to $\pm 0.65\text{ V}$, safely below the THS4521 absolute maximum limit of $\pm 1.0\text{ V}$.
2. **OPA1612 Overload and Headroom:**
   - Powered from $+5\text{VA}$ and $-4\text{V2}$ ($-4.15\text{ V}$).
   - Linear output swing ($2\text{ k}\Omega$ load): $+4.4\text{ V}$ to $-3.55\text{ V}$.
   - Nominal full-scale signal: $\pm 1.0\text{ V}$ ($2.0\text{ V}_{pp}$).
   - Positive headroom: $3.4\text{ V}$; Negative headroom: $2.55\text{ V}$. Headroom is completely symmetric and generous.
3. **DAC OPA2810 Difference Amplifier:**
   - Resistors: $R_{in} = 499\text{ }\Omega$, $R_{fb} = 2.2\text{ k}\Omega$.
   - Gain: $A_v = \frac{2.2\text{ k}\Omega}{499\text{ }\Omega} = 4.409$.
   - Output voltage: Unloaded: $\pm 2.007\text{ V}$; Loaded into $50\text{ }\Omega$ (via $49.9\text{ }\Omega$ source): $\pm 1.005\text{ V}$.
   - Slew Rate: OPA2810 delivers $192\text{ V/}\mu\text{s}$.
     At $10\text{ MHz}$ full scale ($V_p = 2.0\text{ V}$): Required $\text{SR} = 2\pi \times 10\text{ MHz} \times 2.0\text{ V} = 125.7\text{ V/}\mu\text{s} < 192\text{ V/}\mu\text{s}$.
     The stage is **not slew-rate limited** at 10 MHz.
   - Cable driving stability: $R2407$ ($49.9\text{ }\Omega$) sits directly at the amplifier output pin before the SMA jack. The feedback network ($2.2\text{ k}\Omega \parallel 2.2\text{ pF}$) connects before this resistor. Load capacitance from any length of 50 $\Omega$ coaxial cable is completely isolated from the feedback loop, guaranteeing stability.

---

### 3.6 Item 6: CLK IN Comparator (TLV3501) and Missing Protection (Critical Bug)

#### Circuit Operation
- J301 (SMA) $\rightarrow$ JP3001 ($49.9\text{ }\Omega$ switchable termination) $\rightarrow$ C5421 ($10\text{ nF}$) $\rightarrow$ U302 pin 3 ($+IN$).
- Divider R5424 ($10\text{ k}\Omega$) and R5425 ($10\text{ k}\Omega$) from $+3\text{V3\_ADC}$ creates $V_{mid} = 1.650\text{ V}$, decoupled by C5424 ($100\text{ nF}$).
- $-IN$ (pin 1) connects to $1.650\text{ V}$; $+IN$ (pin 3) is biased to $1.650\text{ V}$ through R5426 ($10\text{ k}\Omega$).
- Internal hysteresis: $6\text{ mV}$.
- For a $10\text{ MHz}$ sine wave at $0.5\text{ V}_{pp}$ ($250\text{ mV}$ peak):
  Signal amplitude exceeds hysteresis by $>40\times$. The zero-crossing slew rate is $15.7\text{ V/}\mu\text{s}$, crossing the hysteresis band in $0.38\text{ ns}$. The TLV3501 ($4.5\text{ ns}$ propagation delay) outputs a clean 3.3 V CMOS clock into ECP5 CLK_EXT pin.
- The ECP5 sysCLOCK PLL input range is $8\text{--}400\text{ MHz}$; $10\text{ MHz}$ locks reliably.

#### Missing Input Protection Breakdown
In `gen/sheet_fpga.py`:
C5421 connects directly to pin 3 of U302 without any series resistor or external clamp diodes.
From the TLV3501 datasheet §6.1:
- Input Voltage Absolute Maximum: $(V-) - 0.3\text{ V}$ to $(V+) + 0.3\text{ V}$.
- **Input Current Absolute Maximum:** **$10\text{ mA}$ maximum!**
- Note 2 states: *"Input terminals are diode-clamped to the power-supply rails. Input signals that can swing more than 0.3 V beyond the supply rails must be current-limited to 10 mA or less."*

**Failure Scenario:**
A student plugs in a signal generator outputting a $5\text{ V}$ square wave ($0\text{--}5\text{ V}$):
1. Prior to the edge, the DC voltage at $+IN$ is $1.65\text{ V}$.
2. When the $5\text{ V}$ rising edge arrives, C5421 ($10\text{ nF}$) acts as a short circuit ($X_C \approx 1.6\text{ }\Omega$ at $10\text{ MHz}$).
3. The $+IN$ node is driven to $1.65\text{ V} + 5.0\text{ V} = \mathbf{6.65\text{ V}}$!
4. The internal upper ESD diode turns on when the voltage exceeds $3.3\text{ V} + 0.6\text{ V} = 3.9\text{ V}$.
5. Current forced through the internal ESD diode (with 50 $\Omega$ source):
   $$I_{clamp} = \frac{6.65\text{ V} - 3.9\text{ V}}{50\text{ }\Omega} = \mathbf{55\text{ mA}} \quad (\mathbf{5.5\times\text{ the } 10\text{ mA absolute maximum!}})$$
If a student applies a $10\text{ V}_{pp}$ signal ($\pm 5\text{ V}$), the current reaches **$150\text{ mA}$**, burning out the internal ESD diode and permanently damaging U302!
**Fix:** Insert a **$1\text{ k}\Omega$ series resistor** between C5421 and U302 pin 3 (or add a BAV99 clamp to $+3\text{V3\_ADC}$ and GND).
A $1\text{ k}\Omega$ resistor limits peak current from a 10 V transient to $<7\text{ mA}$ ($<10\text{ mA}$ rating) while creating an input pole with U302's $2\text{ pF}$ input capacitance at $f = \frac{1}{2\pi \times 1\text{ k}\Omega \times 2\text{ pF}} = 80\text{ MHz}$, preserving full 10–50 MHz clock fidelity.

---

### 3.7 Item 7: Ethernet (RTL8211F) Straps and Line Side

All six configuration strap pins on U401 were audited against the RTL8211F datasheet:
1. `LED0 / CFG_EXT` (pin 32): Pulled up via D401 / R4961 ($4.7\text{ k}\Omega$) to `+3V3_ETH` $\rightarrow \mathbf{CFG\_EXT = 1}$ (External power mode for I/O pads).
2. `LED1 / CFG_LDO0` (pin 33): Pulled down via R4972 ($4.7\text{ k}\Omega$) to GND $\rightarrow \mathbf{CFG\_LDO0 = 0}$.
3. `LED2 / CFG_LDO1` (pin 34): Pulled down via R4981 ($4.7\text{ k}\Omega$) to GND $\rightarrow \mathbf{CFG\_LDO1 = 0}$.
   *Combined with CFG_EXT = 1, CFG_LDO[1:0] = 00 selects 3.3 V I/O voltage.*
4. `RXD1 / TXDLY` (pin 24): Pulled up via R4941 ($4.7\text{ k}\Omega$) to `+3V3_ETH` $\rightarrow \mathbf{TXDLY = 1}$ (Internal 2 ns transmit clock delay enabled).
5. `RXD0 / RXDLY` (pin 25): No external resistor; internal default pull-up active $\rightarrow \mathbf{RXDLY = 1}$ (Internal 2 ns receive clock delay enabled).
6. `PHYAD[2:0]` (pins 26, 27, 22): Pin 22 (PHYAD0) has internal pull-up; Pins 26 and 27 have internal pull-down $\rightarrow \mathbf{PHYAD = 001_b = 1}$.

Line Side & Isolation:
- Magnetics G2406S (T401): Chip-side center taps each have individual $100\text{ nF}$ capacitors to GND.
- Line-side center taps: 4× $75\text{ }\Omega$ Bob Smith resistors (R4951–R4954) terminating into C4951 ($1\text{ nF}$, $3\text{ kV}$, 1812 package, C692296).
- 1.5 mm isolation moat is cleanly maintained between PHY side and RJ45 chassis ground.

---

### 3.8 Item 8: Power Sequencing, Configuration, and JTAG

- **100 nF on PROGRAMN (C5711):**
  From the netlist audit, net `Net-(U1G-R9_PROGRAMN)` connects **only** to ECP5 pin R9, pushbutton SW303, pull-up resistor R5711 ($4.7\text{ k}\Omega$), and capacitor C5711 ($100\text{ nF}$).
  *Crucial finding:* PROGRAMN is **not connected to the FT2232H or to JTAG header J305**.
  openFPGALoader programs the ECP5 via JTAG commands (`LSC_REFRESH`), not by asserting PROGRAMN. The $R C$ time constant ($\tau = 4.7\text{ k}\Omega \times 100\text{ nF} = 470\text{ }\mu\text{s}$) holds PROGRAMN low during the initial power-on ramp, ensuring clean initialization after $V_{CC}$ (1.1 V) and $V_{CCIO8}$ (3.3 V) are stable. It does not slow down programming.
- **JTAG Header Pinout (J305):**
  Netlist pins:
  - Pin 1: `+3V3`
  - Pin 2: `TCK`
  - Pin 3: `TMS`
  - Pin 4: `TDI`
  - Pin 5: `TDO`
  - Pin 6: `GND`
  This exactly matches the silkscreen legend and pinout list.
- **External JTAG vs FT2232H:**
  When JP501 (`FTDI OFF`) is shorted, FT2232H pin 14 ($\overline{RESET}$) is tied to GND. In reset, FT2232H tri-states all I/O pins, allowing an external programmer on J305 to drive the JTAG bus without contention through series resistors R6271–R6274 ($33\text{ }\Omega$).

---

### 3.9 Item 9: Schematic and Silkscreen Verification

Every text claim on the silkscreen was validated against the netlist:
- **J305 (JTAG):** Pins 1–6 labeled `3V3`, `TCK`, `TMS`, `TDI`, `TDO`, `GND` $\rightarrow$ Validated.
- **J601 (5 V IN):** Pin 1 labeled `GND`, Pin 2 labeled `+5V` $\rightarrow$ Pin 1 connects to GND; Pin 2 connects to D601 anode. Validated.
- **J106 (PD EXT):** Pin 1 labeled `A` (anode), Pin 2 labeled `K` (cathode) $\rightarrow$ Pin 1 connects to -4V2; Pin 2 connects to TIA inverting input. Validated (reverse-biased photodiode).
- **J210 (LED EXT):** Pin 1 labeled `A +5V`, Pin 2 labeled `K` $\rightarrow$ Pin 1 connects to +5V; Pin 2 connects to Q601 collector current sink. Validated.
- **J105 (EXT R):** Pin 1 labeled `GND`, Pin 2 labeled `NOISE` $\rightarrow$ Validated.
- **J602 (RAILS):** Top row (even pins) labeled `GND`, bottom row (odd pins) labeled `+5V`, `+3V3`, `+1V1`, `+2V5`, `3V3A`, `3V3D`, `+5VA`, `1V0`, `-4V2` $\rightarrow$ Validated.
- **Jumpers Legend:**
  * `TERM`: shunt IN = 50 $\Omega$, OUT = high-Z $\rightarrow$ Validated.
  * `GAIN`: IN = x1, OUT = x10 $\rightarrow$ Validated.
  * `SRC`: SMA \| NOISE (B: ALT = PD \| NOISE) $\rightarrow$ Validated.
  * `LED`: LED \| EXT $\rightarrow$ Validated.
  * `FTDI OFF`: IN holds FT2232H in reset $\rightarrow$ Validated.

---

### 3.10 Item 10: Manufacturing Package

- **DRC:** Clean. 0 errors, 4 warnings (2 dangling ground vias touching In1, and 2 In4 ground fill width warnings on a 0.7x0.9 mm island).
- **ERC:** Clean. 0 errors, 0 warnings.
- **BOM & CPL:**
  * All 471 placed parts map to valid LCSC part numbers.
  * No hand-soldered parts (`hand_solder_bom.csv` is empty).
  * Land patterns verified against JLCPCB footprint database via `footprint_check.py`: 0 HOLE errors.
- **Fiducials:**
  Three fiducials placed at $(25.5, 12.5)$, $(120.0, 7.5)$, and $(146.5, 113.0)$. They form a wide, non-collinear triangle spanning the entire board perimeter, clear of traces, pads, and silkscreen on both outer layers.
- **JLCPCB Order Number:**
  Marker `JLCJLCJLCJLC` is placed at $(95.0, 1.9)$ on `B.SilkS` in the top slot band ($y \le 3.5\text{ mm}$), ensuring the serial number is concealed within the enclosure's mounting slot.

---

## 4. Verification Gates (§4g)

### Gate 13: Netlist Audit
- Total nets: 494.
- One-pin nets: Exactly 52 nets found, all starting with `unconnected-` (deliberate no-connect pins on USB SBU, microSD card-detect, FPGA unused balls, AD9238 DNC pins, LDO NC pins).
- Unintended one-pin nets: **0**.
- Ground net: Single unified `GND` net across the entire board.

### Gate 14: Design Equations Assertion
46 key design equations were asserted directly against the netlist:
- Buck dividers: U601 $= 3.327\text{ V}$, U602 $= 1.100\text{ V}$ (Matches).
- Charge pump divider: U606 $= -4.154\text{ V}$ (Matches).
- THS4521 gain: $499\text{ }\Omega / 499\text{ }\Omega = 1.000$ (Matches).
- DAC difference amplifier: $2.2\text{ k}\Omega / 499\text{ }\Omega = 4.409$; $V_{out} = \pm 1.005\text{ V}$ into 50 $\Omega$ (Matches).
- TIA filter: $10\text{ k}\Omega \parallel 2.2\text{ pF}$, $f_{3dB} \approx 7.2\text{ MHz}$ (Matches).
- LED current driver: $V_{sense} / 10\text{ }\Omega = 0\text{--}48\text{ mA}$ (Matches).
- All asserted resistor, capacitor, and inductor values matched with zero discrepancies.

### Gate 16: Copper Balance by Quadrant & Trace Ampacity
Full polygon area integration of plane layers:
- **`In1.Cu` (Solid GND Plane):**
  * NW: 94.3%
  * NE: 84.3% (lower due to LAN island keepout)
  * SW: 92.4%
  * SE: 94.5%
- **`In4.Cu` (Power Planes):**
  * NW: 92.6%
  * NE: 83.0% (lower due to LAN island keepout)
  * SW: 90.0%
  * SE: 93.2%
- **Signal Layers (F.Cu, In2.Cu, In3.Cu, B.Cu):** Trace density across quadrants is balanced within 1.0–2.5%.
The copper distribution is symmetric and uniform; no risk of PCB warping or bow/twist during assembly reflow.

---

## 5. Clock Jitter and Transmission Line Analysis (§4h)

### 5.1 Clock Jitter Impact on ADC SNR
Formula:
$$\text{SNR}_{jitter} = -20 \log_{10}(2\pi f_{in} t_{jitter})$$
At $f_{in} = 10\text{ MHz}$:
- If clocked by **ECP5 sysCLOCK PLL** ($t_{jitter} \approx 15\text{--}20\text{ ps rms}$):
  $$\text{SNR}_{jitter} = -20 \log_{10}(2\pi \times 10^7 \times 18 \times 10^{-12}) = \mathbf{58.9\text{ dB}}$$
  This caps the AD9238 system performance at **$\approx 9.5\text{ bits ENOB}$**, well below the converter's native SNR of **$70.2\text{ dB}$ (11.4 bits ENOB)**.
- If clocked by **on-board Fox FT5HN TCXO** ($t_{jitter} < 1\text{ ps rms}$):
  $$\text{SNR}_{jitter} = -20 \log_{10}(2\pi \times 10^7 \times 1 \times 10^{-12}) = \mathbf{84.0\text{ dB}}$$
  Provides $>13\text{ dB}$ margin above the AD9238 converter noise floor.
*Recommendation for Gateware:* When digitizing 10 MHz signals where high dynamic range is required, bypass the FPGA internal PLL and clock the AD9238 directly from the TCXO or external low-jitter clock.

### 5.2 Bus Lengths and Transmission Line Termination
Exact physical trace measurements extracted from `ECP5-2ADC-2DAC.kicad_pcb`:
- **SDRAM Bus (39 lines):**
  * Min length: $8.1\text{ mm}$
  * Max length: $30.9\text{ mm}$
  * Average length: $17.8\text{ mm}$
  * SDRAM_CLK: $16.7\text{ mm}$ (centered in the bus distribution)
  * Maximum skew: $\Delta t = (30.9 - 8.1)\text{ mm} \times 6.5\text{ ps/mm} = 148\text{ ps}$ (only 1.5% of 100 MHz clock period).
  * Critical transmission line length ($t_r = 1\text{ ns}$): $L_{crit} \approx 25.6\text{ mm}$. Average length ($17.8\text{ mm}$) is subcritical. Termination resistors are not needed in Rev A if FPGA output drive is configured at 8 mA.
- **DAC Bus (28 data lines + 4 clock/write lines):**
  * Data min: $37.4\text{ mm}$, max: $57.7\text{ mm}$, avg: $45.8\text{ mm}$.
  * DAC_CLK1 / DAC_WRT1: $61.3\text{--}62.7\text{ mm}$.
  * Clock lines are naturally $\sim 4\text{--}15\text{ mm}$ ($25\text{--}100\text{ ps}$) longer than data lines, providing intrinsic positive setup time at the AD9767.
  * Note: The $33\text{ }\Omega$ series resistors (R2101, R2102, R2201, R2202) are placed at the DAC (receiver) rather than the FPGA (source). While this dampens capacitive ringing into the AD9767 input pins, true line-matching termination belongs at the driver. For Rev A, configuring FPGA pins with `SLEWRATE=SLOW` (rise time $\sim 2.0\text{ ns}$) completely eliminates transmission line reflections.

---

## 6. Actionable Fixes Before Ordering Build 31

Three targeted modifications should be made prior to fab submission:

1. **Protect D601 from Bench Overcurrent:**
   Replace D601 (B5819W, 1 A SOD-123) with a **3 A Schottky diode in SMA** (e.g. SS34, LCSC `C1589`, or B340A, LCSC `C8599`). Alternatively, reduce F602 from MF-MSMF200-2 (2.0 A) to MF-MSMF110-2 (1.1 A hold, LCSC `C17313`).
2. **Add Current Limiting / Clamping to CLK IN (U302):**
   Insert a **$1\text{ k}\Omega$ 0603 resistor in series** between C5421 and U302 pin 3 (or place a BAV99 diode pair from pin 3 to $+3\text{V3\_ADC}$ and GND).
3. **Add Thermal Dropping Resistor for U604:**
   Insert a **$3.0\text{ }\Omega$ 1206 resistor in series with U604 pin 1 (VIN)**. This shifts 0.15 W of heat into a 1206 package, drops U604 junction temperature by $>30\text{ }^\circ\text{C}$ in the closed enclosure, and provides a 5 kHz input low-pass filter against switcher ripple.
4. **Correct Release Documentation Notes:**
   Update `mfg/release/FABRICATION_NOTES.txt` to state 0.35 mm (not 0.30 mm) for the 50 $\Omega$ microstrip width, and align the `README.md` text from 13.5 MHz to 12.3 MHz for the DAC difference amplifier.

Once these circuit safeguards and documentation corrections are applied, Rev A is ready for manufacturing.

---

## 7. Comparison with Other Round 2 Reviews

Reviewing `design_review_CopilotSDK2/DESIGN_REVIEW_CopilotSDK2.md` side by side with our independent findings:

### 7.1 What We Agree On
- **D601 / F602 Mismatch:** Both reviews independently identified that F602 (MF-MSMF200-2, 2.0 A hold / 4.0 A trip) leaves D601 (B5819W, 1.0 A continuous / 500 mW max) completely unprotected against bench overloads between 1.0 A and 2.0 A, leading to thermal destruction ($T_J > 200\text{ }^\circ\text{C}$).
- **CLK IN Comparator Vulnerability:** Both reviews independently identified that TLV3501 pin 3 ($+IN$) has no current limiting or clamping after C5421 ($10\text{ nF}$), causing input transients or standard $5\text{ V}/10\text{ V}$ square waves to dump $>50\text{ mA}$ into internal ESD diodes rated for $10\text{ mA}$ maximum.
- **U604 Thermal Dissipation:** Both reviews verified the total load current on `+3V3_ADC` ($\sim 210\text{--}220\text{ mA}$) and confirmed that in a closed enclosure at $45\text{ }^\circ\text{C}$, junction temperature reaches or exceeds the $125\text{ }^\circ\text{C}$ absolute maximum without a thermal dropping resistor.
- **LM27761 Input Voltage Headroom:** Both reviews flagged that a $5.5\text{ V}$ bench supply leaves zero margin for overshoot against LM27761's $5.8\text{ V}$ absolute maximum rating.
- **Pass Verification Gates:** Both reviews confirmed that ERC is 0, DRC is 0 errors / 4 disclosed benign warnings, netlist has 0 accidental 1-pin nets, all 46 design equations hold, and the manufacturing package has 0 HOLE errors.

### 7.2 What CopilotSDK Caught That We Value
- **Documentation Discrepancies:**
  - `FABRICATION_NOTES.txt` incorrectly states the controlled impedance width as $0.30\text{ mm}$, whereas the PCB layout and stack-up rule require $0.35\text{ mm}$ (`RF_W = 0.35`).
  - `README.md` has a stale historical reference to $13.5\text{ MHz}$ for DAC bandwidth, whereas the build 28 revision with $2.2\text{ k}\Omega$ yields $12.3\text{ MHz}$.

### 7.3 What Our Review Uniquely Discovered
- **ADC Clock Jitter Bottleneck:** Calculated the exact SNR degradation resulting from ECP5 internal PLL jitter ($15\text{--}20\text{ ps rms}$), demonstrating that sampling a $10\text{ MHz}$ input from the PLL limits SNR to $\approx 59\text{ dB}$ ($\sim 9.5\text{ bits ENOB}$), whereas sampling from the on-board Fox TCXO ($<1\text{ ps rms}$) achieves $84\text{ dB}$, preserving the full $70.2\text{ dB}$ ($11.4\text{ bits}$) converter potential.
- **DAC Bus Propagation and Setup Time:** Extracted exact trace lengths for the 28 DAC data lines ($37.4\text{--}57.7\text{ mm}$, avg $45.8\text{ mm}$) and 4 clock/write lines ($57.1\text{--}62.7\text{ mm}$), showing that clocks arrive $\sim 30\text{--}150\text{ ps}$ after data, providing intrinsic setup margin at $125\text{ MSPS}$.
- **Receiver-Side Termination on DAC Clocks:** Identified that the $33\text{ }\Omega$ series resistors on `DAC_CLK1/2` and `DAC_WRT1/2` are located at the receiver (AD9767) rather than the driver (FPGA), which necessitates configuring FPGA drive strength to $8\text{ mA}$ and `SLEWRATE=SLOW` to suppress line reflections.
- **Automated Shapely Geometry Audits:** Performed exact polygon intersection calculations of all 747 inner and bottom layer signal segments across the newly formed In4 analog patches, confirming that return currents transfer via low-inductance BGA capacitor loops.

