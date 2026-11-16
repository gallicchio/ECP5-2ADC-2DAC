// Behavioural stand-ins for the ECP5 primitives the design uses, for iverilog only
// (the oss-cad-suite's cells_sim.v has no model for either).
`timescale 1ns/1ps
module ODDRX1F (input SCLK, input RST, input D0, input D1, output reg Q);
    // Q shows D0 after the rising edge of SCLK and D1 after the falling edge (plus a small delay)
    reg d0 = 0, d1 = 0;
    always @(posedge SCLK) begin d0 <= D0; d1 <= D1; end
    always @(posedge SCLK) Q <= #0.5 D0;
    always @(negedge SCLK) Q <= #0.5 d1;
endmodule

// The PLL.  CLKOP = CLKI * CLKFB_DIV / CLKI_DIV (the feedback is CLKOP), measured from CLKI's period; the VCO is
// CLKOP * CLKOP_DIV, and CLKOS / CLKOS2 / CLKOS3 are the VCO divided by their own dividers (a divider left at 0 or
// an output not ENABLED stays low).  All outputs start together, so their rising edges coincide as equal CPHASEs
// make them on the chip.  LOCK after 50 input cycles.
module EHXPLLL #(parameter CLKI_DIV = 1, CLKFB_DIV = 1, CLKOP_DIV = 1, CLKOP_CPHASE = 0, CLKOP_FPHASE = 0,
                 CLKOS_DIV = 0, CLKOS_CPHASE = 0, CLKOS_FPHASE = 0, CLKOS2_DIV = 0, CLKOS2_CPHASE = 0, CLKOS2_FPHASE = 0,
                 CLKOS3_DIV = 0, CLKOS3_CPHASE = 0, CLKOS3_FPHASE = 0,
                 CLKOP_ENABLE = "ENABLED", CLKOS_ENABLE = "DISABLED", CLKOS2_ENABLE = "DISABLED", CLKOS3_ENABLE = "DISABLED",
                 FEEDBK_PATH = "CLKOP", PLLRST_ENA = "DISABLED", INTFB_WAKE = "DISABLED",
                 STDBY_ENABLE = "DISABLED", DPHASE_SOURCE = "DISABLED", OUTDIVIDER_MUXA = "DIVA", OUTDIVIDER_MUXB = "DIVB",
                 OUTDIVIDER_MUXC = "DIVC", OUTDIVIDER_MUXD = "DIVD") (
    input CLKI, input CLKFB, input PHASESEL1, input PHASESEL0, input PHASEDIR, input PHASESTEP, input PHASELOADREG,
    input STDBY, input PLLWAKESYNC, input RST, input ENCLKOP, input ENCLKOS, input ENCLKOS2, input ENCLKOS3,
    output reg CLKOP, output reg CLKOS, output reg CLKOS2, output reg CLKOS3, output reg LOCK, output INTLOCK, output REFCLK, output CLKINTFB);
    real t_last = 0, period = 40.0;
    integer n = 0;
    initial begin CLKOP = 0; CLKOS = 0; CLKOS2 = 0; CLKOS3 = 0; LOCK = 0; end
    always @(posedge CLKI) begin
        if (t_last != 0) period = $realtime - t_last;
        t_last = $realtime;
        n = n + 1;
        if (n > 50) LOCK = 1;
    end
    // one process per output, each toggling every half period of its own; all start at time 0, so they stay aligned
    // (the periods used here are whole picoseconds)
    // (`period` is a real, so every product below is a real; it is 40.0 until CLKI's first period has been measured)
    always begin #(period * CLKI_DIV / CLKFB_DIV / 2.0) CLKOP = ~CLKOP; end
    generate
        if (CLKOS_DIV  != 0) begin : g_os  always begin #(period * CLKI_DIV / CLKFB_DIV / CLKOP_DIV * CLKOS_DIV  / 2.0) CLKOS  = ~CLKOS;  end end
        if (CLKOS2_DIV != 0) begin : g_os2 always begin #(period * CLKI_DIV / CLKFB_DIV / CLKOP_DIV * CLKOS2_DIV / 2.0) CLKOS2 = ~CLKOS2; end end
        if (CLKOS3_DIV != 0) begin : g_os3 always begin #(period * CLKI_DIV / CLKFB_DIV / CLKOP_DIV * CLKOS3_DIV / 2.0) CLKOS3 = ~CLKOS3; end end
    endgenerate
    assign INTLOCK = LOCK; assign REFCLK = CLKI; assign CLKINTFB = CLKOP;
endmodule
