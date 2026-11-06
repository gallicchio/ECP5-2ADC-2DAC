# ECP5-2ADC-2DAC: what rev B should change

Each row with the measurement or reading that showed it.  The candidates known before the boards arrived are in
[`../README.md`](../README.md) ("Rev B candidates") and `../DESIGN_REVIEW_RESPONSE.md` section 6; this file is for what the
bench finds.

| # | what | evidence | found |
|---|---|---|---|
| 1 | DAC 2's clock pins (M9, P8) are in bank 8, whose I/O cells have no DDR output register: a forwarded clock has to go through the fabric.  Put every converter clock on a left, right or top bank in rev B (DAC 1's N6/N5 and both ADC clocks are fine). | ecppack refused the ODDRX1F there (`gateware/bringup/README.md`), 2026-11-05 | before the boards: the gateware |
