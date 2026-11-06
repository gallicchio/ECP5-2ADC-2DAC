// One AD9767 port: a clock, and 14-bit samples from a numerically controlled oscillator.
// Clock generation as in adc_capture (direct = clk_s itself, else a register toggled every `div`
// cycles).  The data register updates on the DAC clock's FALLING edge, so the DAC's WRT/CLK rising
// edge (the same pin pair, tied together as the datasheet allows) lands in the middle of each
// sample: setup and hold are half a DAC period each.  In direct mode `pol` = 1 (the default) inverts the
// clock at the pad to get the same half-cycle margin; with `pol` = 0 the edges coincide (do not).
// Modes: 0 a DC code (`dc`); 1 sine; 2 sawtooth; 3 square; 4 triangle.  `shift` divides the
// amplitude by 2^shift and `dc` (signed, in codes) offsets it; the code is clipped to 0..16383.
// The sine table is rtl/sine_lut.hex (host/gen_lut.py), 1024 x 16-bit two's complement, amplitude 8191.
`default_nettype none

module dac_gen (
    input  wire        clk_s,
    input  wire [15:0] div,
    input  wire        pol,
    input  wire [2:0]  mode,
    input  wire [3:0]  shift,
    input  wire [31:0] inc,            // phase increment per sample: f = inc * f_dac / 2^32
    input  wire signed [15:0] dc,
    output reg  [13:0] data = 14'h2000,
    output wire        clk_d0, output wire clk_d1,
    output wire        clk_fab           // the same clock as a fabric signal, for pins without an IOLOGIC (bank 8)
);
    wire direct = div == 0;
    reg [15:0] divc = 0;
    reg        tog = 0, tog_q = 0;
    reg        upd = 0;                            // the cycle in which the data register updates
    always @(posedge clk_s) begin
        upd <= 1'b0;
        tog_q <= tog;
        if (direct) begin divc <= 0; tog <= 0; upd <= 1'b1; end
        else if (divc >= div - 1) begin divc <= 0; tog <= ~tog; upd <= tog; end      // tog 1 -> 0: a falling edge
        else divc <= divc + 1'b1;
    end
    // The ODDRX1F samples D0/D1 at the clock edge, so the pad shows `tog` one cycle late: its falling edge is
    // the cycle `upd` is high, which is when `data` changes.  The fabric copy is delayed a cycle to match.
    // `pol` applies to direct mode only: in divided mode the data follow the toggle, whose polarity is fixed.
    assign clk_d0 = direct ? ~pol : tog;
    assign clk_d1 = direct ?  pol : tog;
    assign clk_fab = direct ? (clk_s ^ pol) : tog_q;

    reg [15:0] lut [0:1023];
    initial $readmemh("sine_lut.hex", lut);

    // A three-stage pipeline runs every cycle on the current phase: the table, the waveform about zero, the
    // offset and clip.  At `upd` the data register takes the result and the phase advances; the next update
    // is at least two cycles away (div >= 1), or every cycle in direct mode, where the pipeline streams.
    reg [31:0] phase = 0;
    reg signed [15:0] lut_q = 0;
    reg [31:0] ph_q = 0;
    reg signed [16:0] amp_r = 0;
    reg signed [15:0] dc_r = 0;
    reg [2:0] mode_r = 0;
    always @(posedge clk_s) begin
        lut_q <= lut[phase[31:22]];
        ph_q  <= phase;
        dc_r  <= dc;
        mode_r <= mode;
        case (mode)
        3'd1: amp_r <= lut_q >>> shift;                                              // sine
        3'd2: amp_r <= $signed({1'b0, ph_q[31:18]}) - 17'sd8192;                     // sawtooth, full scale
        3'd3: amp_r <= ph_q[31] ? (17'sd8191 >>> shift) : -(17'sd8191 >>> shift);  // square
        3'd4: amp_r <= (ph_q[31] ? $signed({3'b000, ~ph_q[30:17]}) : $signed({3'b000, ph_q[30:17]})) - 17'sd8192;   // triangle
        default: amp_r <= 0;
        endcase
        if (upd) phase <= phase + inc;
    end
    wire signed [17:0] code = (mode_r == 0) ? $signed({2'b00, dc_r}) : (17'sd8192 + amp_r + dc_r);
    always @(posedge clk_s) if (upd) data <= code < 0 ? 14'd0 : code > 18'sd16383 ? 14'd16383 : code[13:0];
endmodule
`default_nettype wire
