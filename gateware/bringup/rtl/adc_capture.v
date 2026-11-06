// The AD9238's two ports: sample clock generation, capture into a memory, running statistics.
// Everything here runs on clk_s (the 50 MHz PLL clock).  The ADC clock leaves through an ODDRX1F
// in the top level: `clk_d0`/`clk_d1` are what the pad shows in the first and second half of each
// clk_s cycle, so direct mode (div == 0) forwards clk_s itself (50 MS/s) and divided mode toggles a
// register every `div` cycles (25 MS/s at div = 1, 1 MS/s at div = 25; the AD9238's minimum is 1 MS/s).
// The ADC's data change tPD = 2-6 ns after its clock's rising edge; `phase` says how many clk_s
// cycles after our rising edge to latch them (1 is right at 25 MS/s), `negedge_cap` latches on the
// falling edge instead: a scan of these on the first board finds the data-valid window.
`default_nettype none

module adc_capture #(parameter AW = 13) (          // 2^AW samples of memory (8192)
    input  wire        clk_s,
    // the pins
    input  wire [11:0] a_d, input wire [11:0] b_d,
    input  wire        a_otr, input wire b_otr,
    output wire        clk_d0, output wire clk_d1,
    // control (quasi-static, from the register file; `arm` a synchronised pulse)
    input  wire [15:0] div,
    input  wire [2:0]  phase,
    input  wire        negedge_cap,
    input  wire [15:0] decim,          // store every (decim + 1)th sample
    input  wire [AW:0] len,            // samples to capture (<= 2^AW)
    input  wire        arm,
    input  wire [4:0]  stats_log2,     // statistics window: 2^n samples (n <= 24)
    // the capture memory's write port
    output reg  [AW-1:0] mem_waddr = 0,
    output reg  [31:0]   mem_wdata = 0,
    output reg           mem_we = 0,
    // status
    output reg         busy = 0,
    output reg         done = 0,
    output reg  [AW:0] count = 0,
    // statistics, published once per window (read them with seq before and after)
    output reg  [15:0] stat_seq = 0,
    output reg  [11:0] a_min = 0, output reg [11:0] a_max = 0, output reg [31:0] a_sum = 0,
    output reg  [11:0] b_min = 0, output reg [11:0] b_max = 0, output reg [31:0] b_sum = 0,
    output reg  [15:0] a_otr_n = 0, output reg [15:0] b_otr_n = 0
);
    // ---- the sample clock -------------------------------------------------------------------
    wire direct = div == 0;
    reg [15:0] divc = 0;
    reg        tog = 0;
    reg        rise = 0;                           // the cycle after which the pad shows a rising edge
    always @(posedge clk_s) begin
        rise <= 1'b0;
        if (direct) begin divc <= 0; tog <= 0; rise <= 1'b1; end
        else if (divc >= div - 1) begin divc <= 0; tog <= ~tog; rise <= ~tog; end
        else divc <= divc + 1'b1;
    end
    assign clk_d0 = direct ? 1'b1 : tog;
    assign clk_d1 = direct ? 1'b0 : tog;

    // ---- latching the data --------------------------------------------------------------------
    reg [7:0] rise_sh = 0;
    always @(posedge clk_s) rise_sh <= {rise_sh[6:0], rise};
    wire cap = direct ? 1'b1 : (phase == 0 ? rise : rise_sh[phase - 1]);
    reg [12:0] a_p = 0, b_p = 0, a_n = 0, b_n = 0;          // {otr, data}
    always @(posedge clk_s) begin a_p <= {a_otr, a_d}; b_p <= {b_otr, b_d}; end
    always @(negedge clk_s) begin a_n <= {a_otr, a_d}; b_n <= {b_otr, b_d}; end
    reg [12:0] a_s = 0, b_s = 0;
    reg        s_valid = 0;
    always @(posedge clk_s) begin
        s_valid <= cap;
        if (cap) begin a_s <= negedge_cap ? a_n : a_p; b_s <= negedge_cap ? b_n : b_p; end
    end

    // ---- the capture ---------------------------------------------------------------------------
    reg [15:0] dec = 0;
    always @(posedge clk_s) begin
        mem_we <= 1'b0;
        if (arm) begin busy <= 1'b1; done <= 1'b0; count <= 0; mem_waddr <= 0; dec <= 0; end
        else if (busy && s_valid) begin
            if (dec == 0) begin
                dec <= decim;
                mem_we <= 1'b1; mem_waddr <= count[AW-1:0];
                mem_wdata <= {3'b000, b_s, 3'b000, a_s};
                count <= count + 1'b1;
                if (count + 1'b1 >= len) begin busy <= 1'b0; done <= 1'b1; end
            end else dec <= dec - 1'b1;
        end
    end

    // ---- statistics over 2^stats_log2 samples ---------------------------------------------------
    reg [24:0] wcnt = 0;
    reg [11:0] amin = 12'hfff, amax = 0, bmin = 12'hfff, bmax = 0;
    reg [31:0] asum = 0, bsum = 0;
    reg [15:0] aotr = 0, botr = 0;
    wire [24:0] wlen = 25'd1 << stats_log2;
    always @(posedge clk_s) if (s_valid) begin
        if (wcnt + 1'b1 >= wlen) begin
            wcnt <= 0;
            a_min <= a_s[11:0] < amin ? a_s[11:0] : amin;  a_max <= a_s[11:0] > amax ? a_s[11:0] : amax;
            b_min <= b_s[11:0] < bmin ? b_s[11:0] : bmin;  b_max <= b_s[11:0] > bmax ? b_s[11:0] : bmax;
            a_sum <= asum + a_s[11:0]; b_sum <= bsum + b_s[11:0];
            a_otr_n <= aotr + a_s[12]; b_otr_n <= botr + b_s[12];
            stat_seq <= stat_seq + 1'b1;
            amin <= 12'hfff; amax <= 0; bmin <= 12'hfff; bmax <= 0; asum <= 0; bsum <= 0; aotr <= 0; botr <= 0;
        end else begin
            wcnt <= wcnt + 1'b1;
            if (a_s[11:0] < amin) amin <= a_s[11:0];  if (a_s[11:0] > amax) amax <= a_s[11:0];
            if (b_s[11:0] < bmin) bmin <= b_s[11:0];  if (b_s[11:0] > bmax) bmax <= b_s[11:0];
            asum <= asum + a_s[11:0]; bsum <= bsum + b_s[11:0];
            aotr <= aotr + a_s[12]; botr <= botr + b_s[12];
        end
    end
endmodule
`default_nettype wire
