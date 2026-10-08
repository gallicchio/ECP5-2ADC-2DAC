# Design review, round 2: ECP5-2ADC-2DAC rev A, build 31

Reviewer: Copilot SDK in VS Code. Tree read at commit `11e2f61` (build 31, 2026-10-07). Nothing outside this directory was written. KiCad DRC and ERC were run on a copy in `kicad_copy/`, not on the shared board.

## Verdict

**Order the five boards for bring-up. Do not hand this revision to the lab as the sheets describe it, and do not type the fabrication note's 0.3 mm into the impedance form.**

I could not find a short, an open, a swapped converter pin, a missing code, or a footprint that would make a careful first power-up dead. ERC is 0. DRC is the four warnings already named. The fabrication-and-assembly claim holds if the impedance width on the order form is corrected to 0.35 mm.

What does not hold is "student-proof, as labelled." Four holes are real, all confirmed against the datasheet, and none of them is fixed by F602:

1. CLK IN has no series resistor. The TLV3501 clamps inputs to 10 mA. A 10 V, 50 Ω source at 10 MHz puts about 128 mA into that clamp.
2. The Schottky does not keep the bench supply off USB VBUS. F601 ties `+5V` straight back to the connector. Plugging both in back-feeds the laptop.
3. The stated 5.0–5.5 V range has no margin to the LM27761's 5.8 V absolute maximum if a stiff source is hot-plugged. USBLC6 does not conduct until 6 V.
4. F602 is a 2 A hold part *after* a 1 A, 0.5 W diode. A 1.5 A fault holds the fuse and cooks D601. The build 31 sentence that the fuse protects the Schottky is false.

A current-limited 5.0 V supply, ramped, and a GPSDO on CLK IN, will bring the board up. A student with a function generator and both cables plugged in can kill U302, D601, U606, or a USB port. Those are handbook limits for this spin and copper changes before the class, not reasons to scrap a bring-up order.

## Findings

| # | If this is wrong | Finding | Confirmed by |
|---|---|---|---|
| 1 | U302 dies from a normal lab generator | CLK IN: C5421 feeds TLV3501 +IN directly. Datasheet §6.1 note 2: inputs more than 0.3 V outside the rails must be limited to **10 mA**. At 10 MHz the 10 nF is 1.6 Ω. A 10 V, 50 Ω source drives (10 − 3.6) / 50 ≈ **128 mA** into the clamp. The ADC inputs have a 100 Ω 1206 for this. CLK IN does not. A 0.5 Vpp GPSDO is fine. | [gen/sheet_fpga.py](../gen/sheet_fpga.py); TLV3501 txt lines 206–207; netlist: C5421, R5426 is the 10 k bias, not a series limiter |
| 2 | A laptop USB port | Bench path is J601 pin 2 → D601 anode → D601 cathode → F602 → `+5V`. F601 pin 2 is `+5V` and pin 1 is VBUS. The diode stops USB from feeding the header. It does not stop the bench supply from appearing on VBUS. The sheet says the opposite. | `build/netlist.net` pins of J601, D601, F601, F602 |
| 3 | LM27761, on a hot-plug of 5.5 V | Absolute maximum 5.8 V, recommended maximum 5.5 V. Author's own 10 % ring on 5.5 V is 6.05 V. USB through a real cable is overdamped (below). A short stiff bench lead is not guaranteed to be. USBLC6 VRM 5.25 V, VBR 6 V min, so it clamps only after the charge pump is already past absolute maximum. | LM27761 §6.1; TLV62569 abs max 6.0 V / recommended 5.5 V; TPS7A20 abs max 6.5 V; ST USBLC6 (local PDF is an image) |
| 4 | D601, on a bench fault between 1 and 2 A | MF-MSMF200 holds 2.00 A and trips at 4.00 A. B5819W is 1 A average and **500 mW**. F602 is downstream of the diode, so every milliamp gets there first. At 1.5 A and 0.6–0.9 V the diode is at 0.9–1.35 W in a 0.5 W package, and the fuse has not opened. At the design 0.7 A it is 0.42 W, inside the rating but hot. The build 31 fix does not do what its comment says. | MF-MSMF200 table (2.00 A hold, 4.00 A trip, 0.020–0.080 Ω); B5819W: 1 A, 500 mW, VF 0.6 V at 1 A |
| 5 | U604 over 125 °C, not into shutdown | At 5.0 V and 0.205 A, 0.35 W × 187 °C/W = 65 °C rise: 110 °C in 45 °C box air, inside the rating. At the stated **5.5 V** top end, (5.5 − 3.3) × 0.205 = 0.45 W, rise 84 °C, **TJ ≈ 129 °C** at 45 °C air. Recommended max is 125 °C. Shutdown is 165 °C rising. GND via is 1.34 mm from the pin; there is no back pour, so do not discount the JEDEC 187 °C/W. | AD9238 65 MSPS column 200 mA IAVDD; THS4521 and TLV3501 add ~5 mA; TPS7A20 DBV RθJA 187.1, TSD 165/140; U604 placement |
| 6 | Gigabit at the documented address | RXDLY and PHYAD0 have no external resistor. During configuration ECP5 user I/Os are pull-downs, up to 150 µA (DS-02012 §4.1). PHY reset (4.7 kΩ × 1 µF) releases in ~5 ms; Master SPI at 2.4 MHz MCLK is still running. Those straps are sampled through 22 Ω against that pull-down. Datasheet §7.8 requires an external resistor. TXDLY's 4.7 kΩ holds (150 µA × 4.7 kΩ = 0.70 V). RXDLY = 1 and PHY address 1 do not. | Netlist; FPGA-DS-02012 §4.1 and Table 2.16; RTL8211F Table 6 and §7.8 |
| 7 | Impedance form | Notes say 50 Ω at **0.3 mm**. `RF_W` is **0.35 mm**, `rf_width_violations` is empty, SMA feeds carry 8–11 mm of 0.35 mm copper. Type 0.35 mm. About 5 Ω if they tune for 0.3 mm. Not a respin. | [mfg/make_fab.py](../mfg/make_fab.py); [pcb/build_pcb.py](../pcb/build_pcb.py); segment widths |

## Numbers asked for

### 3.1 The ADC LDO

AD9238-65 DC input power in the fast column is 600 mW at 3.0 V, i.e. the 200 mA IAVDD the author used. DRVDD is on `+3V3_DRV`, not this LDO. Add two THS4521s (~1 mA each) and the TLV3501 (3.2 mA) and the dim LED: about **0.205 A**.

| Input | Power | Rise at 187 °C/W | TJ at 45 °C air |
|---|---|---|---|
| 5.0 V | 0.35 W | 65 °C | 110 °C |
| 5.5 V | 0.45 W | 84 °C | 129 °C |

Shutdown wants ~100 °C ambient at 0.35 W, or ~80 °C ambient at 0.45 W. It will not shut down. It does exceed the 125 °C recommended limit at the top of the stated bench range, full rate, closed box. At 20 / 40 MSPS the same table is 60 / 110 mA. Fine.

The smallest copper change, if these boards will sit at 65 MSPS on a 5.5 V bench: 2.2 Ω in series with U604's input. At 0.2 A that is 0.44 V and 0.09 W in a 1206, and the LDO still has about 1.2 V of headroom (its dropout at this current is a few hundred millivolts). I would not hold a bring-up order for it. I would not run the class at 65 MSPS from 5.5 V in the extrusion without it.

### 3.2 Seams

In1 has **0 tracks**. In4 areas from the filled polygons: `+3V3` 9400 mm², `+5V` 1876, `−4V2` 1382, `+5VA` 905, `+1V1` 324 (core patch plus the corridor to the buck, not a 4 × 4 mm square), `+3V3_ADC` 325, `+3V3_DAC` 288, GND fill 2372.

41 nets have a segment whose ends sit on different In4 fills. Decide, don't count:

- **DAC_CLK1 / DAC_WRT1** on In3 ride the `+1V1` corridor and leave it. One segment is 49 mm end to end; the return is continuous in the `+1V1` plane until the edge. No stitching capacitor. Nearest GND via to the middle of that segment is 6.0 mm and 5.3 mm. The clocks already have 33 Ω. Scope them. Not a hold. The round-1 "4 × 4 mm patch" description is incomplete.
- ADC data crosses the `+3V3_ADC` edge for 3–8 mm at 65 MSPS. Tens of picoseconds. Ignore.
- Flash CS / WP / HOLD / CCLK cross the `+1V1` edge for 4–5 mm at a 2.4 MHz boot clock. Ignore.
- No analog input crosses a seam.

### 3.4 The 5 V input

Bulk on `+5V`: two 22 µF + five 10 µF, all 25 V X5R, plus 100 nF. Nominal **94 µF**. Figure ~80 µF after 10–15 % X5R bias loss. No electrolytic.

`sqrt(L/C)` for 1 µH and 94 µF is **0.103 Ω**. Q = 0.103 / R.

- Fuse cold resistance 0.020–0.080 Ω. Alone, that does not damp a 1 µH cable (Q ≈ 1.3–5). The author's "Q about 0.6 from the fuse" needs the cable resistance too.
- A 1 m USB cable is a few tenths of an ohm round trip. Q ≈ 0.3. Overdamped. USB hot-plug is fine.
- A short thick bench lead can be 0.3–0.5 µH and < 0.05 Ω of wire. B5819W Rd between 1 A and 3 A is about (0.9 − 0.6) / 2 A = **0.15 Ω**, which damps that case (Q ≈ 0.4) if the diode is already in the surge. If total R stays under ~0.05 Ω, Q > 1 and 5.5 V × 1.1 = 6.05 V, past 5.8 V.
- F602's placement is electrically in series and after the diode. It protects copper downstream. It does not protect D601 (finding 4).
- `+5V` vias: 15, eleven of them 0.45/0.25. Enough for 0.7 A. Copper drop is milliohms next to the fuse (14–56 mV at 0.7 A).

### 3.6 CLK IN

Pinout matches the DBV figure: 1 −IN, 2 V−, 3 +IN, 4 V+, 5 OUT, 6 SHDN. SHDN grounded enables the part (disabled only within 0.9 V of V+). Output through 33 Ω to ball **K2 = PCLKC7_0**. The PLL can use it.

10 k/10 k from `+3V3_ADC` is 1.65 V. High-pass of the 10 k bias and 10 nF is 1.6 kHz. A 10 MHz, 0.5 Vpp sine is 0.25 V peak, forty times the 6 mV hysteresis. It will square. `fIN` min is 8 MHz; `fPFD` min is 10 MHz; jitter is guaranteed only for `fPFD` > 10 MHz (Table 3.23 note 3). A 10 MHz GPSDO is the right use. Do not teach 8 MHz as a guaranteed lock.

The missing piece is current limit, finding 1. A 1 kΩ after the coupling capacitor holds a 10 V source to 6.4 mA. That is a respin, or a note that CLK IN is 3.3 V max until then.

PROGRAMN's 100 nF × 4.7 kΩ is 0.47 ms. It is not on the JTAG header and the FT2232H does not drive it, so it does not slow openFPGALoader. Accepted PROGRAMN pulse is 110 ns; the button is longer. JTAG header from the netlist: pin 1 `+3V3`, 2 TCK, 3 TMS, 4 TDI, 5 TDO, 6 GND. Custom 1×6. Labels in the generator match the nets. FTDI OFF is on RESET#.

### 4h Termination and jitter

Do not add series resistors on the converter data or the SDRAM for this spin. Periods are 8 ns (DAC 125 MHz), 10 ns (SDRAM 100 MHz), 15 ns (ADC 65 MHz). A round trip on 40 mm is ~0.5 ns. It rings and it settles inside the window. DAC clocks already have 33 Ω. RGMII already has 22 Ω, on the PHY end for both directions; moving the TX set to the FPGA is a real improvement and correctly rev B.

`SLEWRATE=FAST` on every bus group is the wrong default for SDRAM and converter data. Slow slew still meets those windows and does the job the missing resistors would have done. Keep FAST on RGMII and on the converter clocks if the timing report asks.

Phase jitter at `fPFD` < 100 MHz is 0.011 UI pp (Table 3.23). At 65 MHz that is 169 ps pp. Taking rms as about one sixth (a guess) is ~28 ps. At 10 MHz:

SNR ≤ −20 log10(2 π × 10⁷ × 28 × 10⁻¹²) ≈ **55 dB**, about 9 bits, against 74 dB for an ideal 12-bit quantizer.

Period jitter in the same table is 0.025 UI pp below 100 MHz (385 ps pp at 65 MHz), which is worse. If the sample clock comes from the ECP5 PLL, the front end is not what sets SNR at 10 MHz. Handbook sentence, not a copper change.

HDMI pairs after the build 26 jack move, trace length only:

| pair | P − N |
|---|---|
| GPDI_CK | 1.06 mm |
| GPDI_D0 | 1.05 mm |
| GPDI_D1 | 2.18 mm |
| GPDI_D2 | 1.39 mm |

The 0.15 mm rule is not met. At 720p a bit is 1.35 ns and 2.2 mm is ~15 ps. It will display. MDI pairs are 0.58–0.91 mm (~6 ps). USB DP/DM differ by 5.8 mm on the FPGA port and 3.9 mm at the FT2232H. Fine for USB 2.

## Gates the build does not run

### 13. Netlist

- One-pin nets excluding `unconnected-*`: **0**.
- Power pin counts: GND 353, `+3V3` 118, `+5V` 29, `+3V3_ADC` 24, `+1V1` 22, `−4V2` 19, `+3V3_ETH` 17, `+5VA` 16, `+1V0_PHY` 11, `+1V8_FTDI` 9, `+3V3_DRV` 9, `+3V3_DAC_D` 8, `+3V3_DAC` 7, `+2V5_AUX` 6, `+2V5` 5. No alias (`VCC` is not a net).
- Inductive loads: the three 2.2 µH parts are inside switcher loops. No freewheel missing.
- Fused inputs: USB through F601, bench through D601 then F602 (finding 4: the fuse does not protect the diode), HDMI +5 V through F501. Pmod 3.3 V, RAILS, EXT R, PD EXT, LED EXT are not power inputs. 5 V shoved into a Pmod pin is still a lab hazard, not a missing fuse.
- Polarized parts checked: D601 anode faces the header; D101/D102 pin 1 on `−4V2`, pin 2 on `+5VA`, pin 3 on the signal (rail clamp); D111/D112 pins 1 and 2 on IN−, pin 3 on IN+ (anti-parallel; BAV99 pin 3 is K1/A2). LM27761 pins 1–9 match TI, pad on GND. TLV3501 matches DBV. No electrolytic.
- DNP: none in the netlist fields.

### 14. Equations

| Claim | Check | Result |
|---|---|---|
| `+3V3` = 0.6 × (1 + 15k/3.3k) | sheet | 3.327 V |
| `+1V1` = 0.6 × (1 + 10k/12k) | sheet | 1.100 V |
| `−4V2` = −1.22 × (1.2M+499k)/499k | sheet | **−4.15 V**. Title still says ±4.5 V. |
| OPA1612 | 9.1k/1k | 10.1, as printed |
| THS4521 | 499/499 | gain 1. PD pin 7 tied to `+3V3_ADC` is correct (PD high = run). Pin 4 VOUT+, pin 5 VOUT−. |
| DAC | 24.9 Ω BOM C22916; 2.2 kΩ BOM C4190 | 19.2 mA × 24.9 = 0.478 V; gain 4.41; ±2.11 V open, ±1.05 V into 50 Ω |
| `dac_stage.cir` | ran here | ±2.007 V open, ±1.005 V into 50 Ω, −3 dB at 12.3 MHz. Labels are within 0.5 %. |
| `adc_frontend.cir` | ran here | −3 dB at 23.1 MHz. BAV99 Cd is not in the deck. 1.5 pF against 150 Ω at the clamp is a 700 MHz pole; against 499 Ω at the FDA inputs ~200 MHz, above the 22 pF filter. It does not move x10 bandwidth. |
| `tia.cir` | ran here | −3 dB at 6.8 MHz, 3.5 dB peaking at 4 MHz. Ship it; it is not flat. |
| `pdn_bead.cir` | ran here | 0.69 Ω at 47 kHz, 5.0 mΩ at 2 MHz. Matches the sheet. |
| `led_driver.cir` | ran here | 48 mA at 0.48 V command. SS8050 is fine. |
| RSET / USB / CC / Bob Smith | BOM | 2.49 kΩ C22908; 27 Ω C25190; 5.1 kΩ to GND on both CC pins of both jacks; 1 nF 3 kV C4951 / C692296. |
| ±10 V into the 100 Ω 1206 | arithmetic | about 5.1 V across it on the negative clamp, 51 mA, **0.26 W** in a 0.25 W part. Continuous −10 V is at the rating. Say "brief". |
| Crystal | not re-opened | 12 MHz, 27 pF on a 20 pF part. |

### 16. Copper and current

Filled zones: In1 91 % of the board, no tracks. In4 90 %. In2/In3 tracks are 1–2 %. Outer layers have no zones; F.Cu tracks 1043 mm² (5.5 %), B.Cu tracks 559 mm² (3.0 %), plus pads. Usual 6-layer imbalance on 1.6 mm. I would not expect a warp JLCPCB rejects. Quadrant splits from polygon centroids are not trustworthy (one In1 polygon's centroid ate the plane), so I am not quoting them.

`+5V` narrowest neck in `rail_widths` is 1.2 mm at 0.127 mm, at a pad, not the corridor. The plane carries the current.

### 17. Upload, redone

- DRC, KiCad 10.0.6, no refill, copy of the shipped board: **4 warnings, 0 unconnected**. The two dangling GND vias and the two In4 webs (0.064 mm, 0.030 mm). ERC: **0**.
- Fiducials: 1 mm copper, 2 mm mask, both sides, at (25.5, 12.5), (120, 7.5), (146.5, 113) board coordinates. No paste drawn. All three are outside the 3.5 mm slot keep-out.
- Layer digits 1–6 read back out of the board file at y = 1.9 mm. `JLCJLCJLCJLC` on B.SilkS at (95, 1.9). The "specify a location" instruction is right.
- BOM spot check: AD9238 C514277 (21 in stock, 5 needed — still the thin one), TLV3501 C193413, both fuses C210837, 24.9 Ω C22916, 2.2 kΩ C4190. CPL angles not re-derived; that is Jason's preview.
- PHY layout vs Realtek, not a hold, do scope it: REG_OUT leaves the front-side QFN through two vias to L401 on the back, 6.2 mm away. They ask for same layer, no vias, within 200 mil. A `+3V3_ETH` segment at DVDD33 is 0.20 mm; they ask for 40 mil. The inductor is the right part (the note's 2.95 A / 40 mΩ). TLV62569DBV soft-start is 800 µs typical, no minimum; they want the 3.3 V rise slower than 0.5 ms and say < 0.1 ms can damage the internal regulator. Typical meets it. Scope DVDD33 and REG_OUT on the first board.

## What I could not fault

THS4521 PD polarity, both BAV99 wirings, LM27761 pin table including the pad, TLV3501 pin table, F602 actually in series, USB Rd on both CC pins, CLK OUT through 49.9 Ω, no tap on the comparator input, RSET and the gain resistors in the BOM, In1 empty, the build 30 plane drops (`+3V3_ADC` worst 22.7 mΩ, `+3V3_DAC` 7.8 mΩ, `+5VA` 7.4 mΩ, `−4V2` worst 26 mΩ, `+1V1` 2.5 mΩ). Series-orientation's 28 "reversed" parts, including two diodes, are a geometric check; schematic parity is clean, so they are not in backwards. 127 signal vias had no room for a return via within 1.5 mm; I did not promote that without a net list.

## Round-1 dispositions

- **R5, the RX half, rejected.** TXDLY = 1 is real. RXDLY = 1 is an internal pull-up on the far side of 22 Ω from a pin that is pulled down for the whole of configuration. The gateware adding no RX delay is only right if the strap sampled 1. It may have sampled 0. Address may be 0, which Table 11 does not list as a normal address (00001–00111). MDIO broadcast still works. Set the delay in a register, and do not hard-code address 1.
- **R11, the geometry, qualified.** The deferral can stand. The "4 × 4 mm" sentence cannot. The corridor runs south to the buck.
- **R12, incomplete.** Saying "use a USB-C charger" does not make the Schottky isolate that port from the bench header.
- R1 (BAV99; capacitance does not touch the x10 band), R8 (PROGRAMN capacitor is not in the programmer's path), the crystal load, and the ADC input length mismatch: accepted.

## Other round-2 material

No finished report was in `design_review_Gemini_3.8_Flash2/`, `design_review_Grok4.7_2/`, or `design_review2_Gemini_3.8_Flash/` when this was written (that last directory has measurements and no report; I did not use them). `design_review2_CopilotSDK/` is empty.

A draft already in this directory, kept as `prior_draft_kept.md`, says do not order. I agree with it on the CLK IN 10 mA limit, on F602 not protecting a 1 A / 0.5 W diode, on 5.5 V × 10 % clearing 5.8 V, on the 0.3 mm vs 0.35 mm note, and on U604 crossing 125 °C at 5.5 V and 45 °C. I do not agree that those require holding the fab if the five boards are bring-up boards on a current-limited 5.0 V supply. That draft does not mention the USB back-feed or the configuration pull-down on RXDLY and PHYAD0. Those two are the ones I would not want the class to learn from the sheet.
