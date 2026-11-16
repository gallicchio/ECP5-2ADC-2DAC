# ECP5-2ADC-2DAC rev A bring-up log

One row per result, against the pass condition of its stage in [`../BRINGUP.md`](../BRINGUP.md); the raw readings are in
`data/board_<X>/<date>.jsonl` (on the bench PC, not in git).  Boards: **A** and **B**, the two assembled ones, marked
with a pen on the back by the RAILS header.

| stage | board | date | result | pass? | notes / file |
|---|---|---|---|---|---|
| 0.1 | A | 2026-11-16 | one assembled board unwrapped, photographed top (4 photos) and back (3); standoffs fitted; a microSD card in | - | Prompt 100; to be marked A |
| 0.2 | A | 2026-11-16 | polarity and pin 1 against the render: as drawn wherever readable (ECP5, AD9238, AD9767, FT2232H, RTL8211F, W25Q128, OPA1612 x2, THS4521 x2, OPA2810 x2, TIA, BAV99 D101/D102, Q601, Q602); every position populated; connectors facing out; SW101 off | pass | not readable: D601's band, U301, U606, U302, the LEDs, D103 (all covered by the staircase or harmless) |
| 0.2 | A | 2026-11-16 | ~~JP501 (FTDI OFF) has a shunt on it~~ **Wrong: JP501 has no shunt** (Jason, Prompt 101).  The session read a shunt into a slanted photo of a bare header | - | photos cannot settle a jumper; see `CLAUDE_PCB.md` section 33 |
| 0.3 | A | 2026-11-16 | marked A; the ten shunts as in `figs/visit0_jumpers.png`; JP2009 and JP501 open; SW101 off | done | "v0 done" (Prompt 101) |
| 1.2 | A | 2026-11-16 10:34 | staircase on E3646A output 1 (adapter A9PUYBUD): 1.0 V 0.000 A, 2.5 V 0.095 A, 4.0 V 0.388 A, 5.0 V 0.369 A, all CV | pass | the tool stopped this run on its own wrong rule ("the current rises with the voltage": the bucks draw about constant power, so it falls); rule changed to the power; `report_v1a_20261116_103448.md` |
| 1.2 | A | 2026-11-16 10:35 | staircase again: 0.000, 0.090, 0.386, 0.388 A (0.00, 0.22, 1.55, 1.94 W), all CV; then 5.0 V on: 5.001 V at the supply, **0.385 A** unconfigured, three readings within 1.1 % | pass | `report_v1a_20261116_103539.md`; the cold-boot reference |
| 1.1 | A | 2026-11-16 10:35 | the eight red POWER LEDs lit | pass | Jason |
| 1.3 | A | 2026-11-16 10:36 | first Fluke walk: every pin -2.507 V, i.e. one probe on +2V5 and the other along the ground row (the names are printed above the ground row) | - | the walk tool stopped after 9 s on a rule that took any negative reading for -4V2; fixed (needs 7 rails first); REVB row 10 |
| 1.3 | A | 2026-11-16 10:37 | Fluke walk (Fluke 45 on A95AME9U): +5V **4.220**, +3V3 3.331, +1V1 1.106, +2V5 2.508, +3V3_ADC 3.296, +3V3_DAC 3.293, +5VA **4.226**, +1V0_PHY 1.011, -4V2 -4.115 V | 7 pass; +5V, +5VA low | `report_rails_20261116_103738.md` |
| 1.3 | A | 2026-11-16 10:40 | why +5V is low: 5.00 V at the supply, **4.51-4.54 V at J601** (0.47 V, about 1.2 ohm, in the BNC cable and thin wire to the board), 4.17-4.22 V at J602's +5V (0.30 V across D601 and F602, as expected of an SS34 at 0.39 A) | leads, not the board | short thick leads to J601, then read +5V again; REVB row 11 |
| - | A | 2026-11-16 10:43 | supply output OFF at Jason's request (0.000 V, 0.4 mA); set 5.0 V / 1.0 A / OVP 5.6 V; leads still on J601; claim held | - | |
