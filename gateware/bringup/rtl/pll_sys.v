// The board's one PLL: the 25 MHz TCXO to three phase-aligned clocks from a 500 MHz VCO.
//   clk125  125 MHz  CLKOP  (VCO / 4)   the RGMII transmit clock and the HDMI serialiser (5 x the pixel clock)
//   clk_s    50 MHz  CLKOS  (VCO / 10)  the converters and the SDRAM
//   clk_pix  25 MHz  CLKOS2 (VCO / 20)  the HDMI pixel clock (the TCXO's rate, but aligned to clk125)
// Written by hand in the form `ecppll` writes (2026-11-15): ecppll fits only the first output exactly and gave
// 52.08 MHz or 150 MHz for the others; 500 MHz is the one VCO in the 400-800 MHz range that divides to all three.
// The feedback is CLKOP: f(CLKOP) = 25 MHz x CLKFB_DIV / CLKI_DIV = 125 MHz, VCO = 125 MHz x CLKOP_DIV = 500 MHz.
// The three outputs have the same coarse phase (CPHASE), so their rising edges coincide; nextpnr prints the
// frequencies it derives from these parameters, which is the check that they are what this comment says.
// Until 2026-11-15 this file was `ecppll -i 25 -o 50` (VCO 600 MHz, one output).
module pll_sys
(
    input  clkin,       // 25 MHz
    output clk125,      // 125 MHz
    output clk_s,       // 50 MHz
    output clk_pix,     // 25 MHz
    output locked
);
(* FREQUENCY_PIN_CLKI="25" *)
(* FREQUENCY_PIN_CLKOP="125" *)
(* FREQUENCY_PIN_CLKOS="50" *)
(* FREQUENCY_PIN_CLKOS2="25" *)
(* ICP_CURRENT="12" *) (* LPF_RESISTOR="8" *) (* MFG_ENABLE_FILTEROPAMP="1" *) (* MFG_GMCREF_SEL="2" *)
EHXPLLL #(
        .PLLRST_ENA("DISABLED"),
        .INTFB_WAKE("DISABLED"),
        .STDBY_ENABLE("DISABLED"),
        .DPHASE_SOURCE("DISABLED"),
        .OUTDIVIDER_MUXA("DIVA"),
        .OUTDIVIDER_MUXB("DIVB"),
        .OUTDIVIDER_MUXC("DIVC"),
        .OUTDIVIDER_MUXD("DIVD"),
        .CLKI_DIV(1),
        .CLKOP_ENABLE("ENABLED"),
        .CLKOP_DIV(4),
        .CLKOP_CPHASE(1),
        .CLKOP_FPHASE(0),
        .CLKOS_ENABLE("ENABLED"),
        .CLKOS_DIV(10),
        .CLKOS_CPHASE(1),
        .CLKOS_FPHASE(0),
        .CLKOS2_ENABLE("ENABLED"),
        .CLKOS2_DIV(20),
        .CLKOS2_CPHASE(1),
        .CLKOS2_FPHASE(0),
        .FEEDBK_PATH("CLKOP"),
        .CLKFB_DIV(5)
    ) pll_i (
        .RST(1'b0),
        .STDBY(1'b0),
        .CLKI(clkin),
        .CLKOP(clk125),
        .CLKOS(clk_s),
        .CLKOS2(clk_pix),
        .CLKOS3(),
        .CLKFB(clk125),
        .CLKINTFB(),
        .PHASESEL0(1'b0),
        .PHASESEL1(1'b0),
        .PHASEDIR(1'b1),
        .PHASESTEP(1'b1),
        .PHASELOADREG(1'b1),
        .PLLWAKESYNC(1'b0),
        .ENCLKOP(1'b0),
        .LOCK(locked),
        .ENCLKOS(1'b0),
        .ENCLKOS2(1'b0),
        .ENCLKOS3(1'b0),
        .INTLOCK(),
        .REFCLK()
	);
endmodule
