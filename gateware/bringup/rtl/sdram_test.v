// A memory tester for the W9825G6KH-6 (4 banks x 8192 rows x 512 columns x 16 bits = 32 MB), on clk_s.
// Not a controller for a CPU: one access at a time, auto-precharge, burst length 1, CAS latency 2.
// Init (datasheet 7.1): >= 200 us of NOP with CKE high, PRECHARGE ALL, 8 AUTO REFRESH, LOAD MODE
// (CL = 2, BL = 1, sequential: A[12:0] = 0x020), then an AUTO REFRESH every `REFRESH` cycles (the
// 8192 rows want one every 7.8 us = 390 cycles at 50 MHz; 300 here).  A test writes pattern(addr) to
// `len` words, then reads them all back and counts the mismatches: a pass is retention over the
// seconds the write phase takes, so it proves the refresh too.  `rdlat` is how many clk_s cycles
// after the READ command the data are latched (CL = 2 plus the round trip; scan it on the first board:
// 2 or 3 should pass and the others fail with errors in every word).
// Word address: {bank[1:0], row[12:0], col[8:0]} = 24 bits = 16 M words.
`default_nettype none

module sdram_test #(parameter INIT_CYCLES = 12500, REFRESH = 300) (
    input  wire        clk_s,
    // pins (the clock leaves through an ODDRX1F in the top level; dq's tristate is there too)
    output reg  [12:0] a = 0,
    output reg  [1:0]  ba = 0,
    output reg         cs_n = 1'b1,
    output reg         ras_n = 1'b1,
    output reg         cas_n = 1'b1,
    output reg         we_n = 1'b1,
    output reg         cke = 1'b0,
    output wire        dqm,
    output reg  [15:0] dq_out = 0,
    output reg         dq_oe = 0,
    input  wire [15:0] dq_in,
    // control
    input  wire        start,          // a pulse
    input  wire        abort,
    input  wire [3:0]  pattern,
    input  wire [3:0]  rdlat,
    input  wire [24:0] len,            // words, 1 .. 2^24
    // status
    output reg         init_done = 0,
    output reg         busy = 0,
    output reg         done = 0,
    output reg  [31:0] errors = 0,
    output reg  [31:0] first_err_addr = 0,
    output reg  [31:0] first_err_data = 0,       // {expected, got}
    output reg  [24:0] words_done = 0
);
    assign dqm = 1'b0;

    // commands: {cs_n, ras_n, cas_n, we_n}
    localparam CMD_NOP = 4'b0111, CMD_ACT = 4'b0011, CMD_READ = 4'b0101, CMD_WRITE = 4'b0100,
               CMD_PRE = 4'b0010, CMD_AREF = 4'b0001, CMD_LMR = 4'b0000, CMD_DESEL = 4'b1111;
    task cmd(input [3:0] c); begin {cs_n, ras_n, cas_n, we_n} <= c; end endtask

    localparam S_INIT_WAIT = 0, S_INIT_PRE = 1, S_INIT_AREF = 2, S_INIT_LMR = 3, S_IDLE = 4,
               S_AREF = 5, S_ACT = 6, S_RW = 7, S_RD_WAIT = 8, S_WAIT = 9, S_NEXT = 10;
    reg [3:0]  state = S_INIT_WAIT;
    reg [15:0] wait_n = 0;              // NOP cycles to spend in S_WAIT, then go to `after`
    reg [3:0]  after = S_IDLE;
    reg [3:0]  aref_n = 0;
    reg [9:0]  ref_t = 0;
    reg        ref_due = 0;
    reg        reading = 0;             // phase: 0 write, 1 read
    reg        start_p = 0;             // a start that arrived during a refresh waits here for S_IDLE
    reg [24:0] addr = 0;
    reg [3:0]  lat = 0;

    function [15:0] pat(input [24:0] ad, input [3:0] p);
        case (p)
        4'd0: pat = ad[15:0] ^ {ad[23:16], ad[23:16]};
        4'd1: pat = ~(ad[15:0] ^ {ad[23:16], ad[23:16]});
        4'd2: pat = ad[0] ? 16'hAAAA : 16'h5555;
        4'd3: pat = ad[0] ? 16'h5555 : 16'hAAAA;
        4'd4: pat = 16'hFFFF;
        4'd5: pat = 16'h0000;
        4'd6: pat = {ad[7:0], ad[15:8]} ^ {12'h0, ad[19:16]} ^ (ad[15:0] << 3) ^ (ad[23:8] >> 2);
        default: pat = ad[15:0];
        endcase
    endfunction
    wire [15:0] exp_w = pat(addr, pattern);

    always @(posedge clk_s) begin
        cmd(CMD_NOP);
        dq_oe <= 1'b0;
        // refresh timer
        if (init_done) begin
            if (ref_t >= REFRESH - 1) begin ref_t <= 0; ref_due <= 1'b1; end
            else ref_t <= ref_t + 1'b1;
        end
        if (abort && busy) begin busy <= 1'b0; done <= 1'b1; state <= S_IDLE; end
        if (start && state != S_IDLE) start_p <= 1'b1;
        case (state)
        S_INIT_WAIT: begin
            cke <= 1'b1;
            if (wait_n >= INIT_CYCLES) state <= S_INIT_PRE; else wait_n <= wait_n + 1'b1;
        end
        S_INIT_PRE: begin cmd(CMD_PRE); a[10] <= 1'b1; wait_n <= 3; after <= S_INIT_AREF; aref_n <= 0; state <= S_WAIT; end
        S_INIT_AREF: begin
            cmd(CMD_AREF); aref_n <= aref_n + 1'b1; wait_n <= 5;
            after <= (aref_n == 7) ? S_INIT_LMR : S_INIT_AREF; state <= S_WAIT;
        end
        S_INIT_LMR: begin cmd(CMD_LMR); ba <= 0; a <= 13'h020; wait_n <= 3; after <= S_IDLE; state <= S_WAIT; init_done <= 1'b1; end
        S_IDLE: begin
            if (start || start_p) begin
                start_p <= 1'b0;
                busy <= 1'b1; done <= 1'b0; errors <= 0; words_done <= 0; addr <= 0; reading <= 1'b0;
                first_err_addr <= 0; first_err_data <= 0;
                state <= S_NEXT;
            end else if (ref_due) begin ref_due <= 1'b0; state <= S_AREF; after <= S_IDLE; end
        end
        S_AREF: begin cmd(CMD_AREF); wait_n <= 5; state <= S_WAIT; end        // tRFC 60 ns: 5 NOPs is 120
        S_NEXT: begin
            if (ref_due) begin ref_due <= 1'b0; state <= S_AREF; after <= S_NEXT; end
            else state <= S_ACT;
        end
        S_ACT: begin
            cmd(CMD_ACT); ba <= addr[23:22]; a <= addr[21:9];
            wait_n <= 1; after <= S_RW; state <= S_WAIT;                      // tRCD 18 ns: command, NOP, command = 40
        end
        S_RW: begin
            ba <= addr[23:22]; a <= {4'b0010, addr[8:0]};                      // A10 = 1: auto-precharge
            if (reading) begin cmd(CMD_READ); lat <= 0; state <= S_RD_WAIT; end
            else begin cmd(CMD_WRITE); dq_out <= exp_w; dq_oe <= 1'b1; wait_n <= 3; after <= S_NEXT; state <= S_WAIT; words_done <= words_done + 1'b1; end
            if (!reading && addr + 1'b1 >= len) begin addr <= 0; reading <= 1'b1; end
            else if (!reading) addr <= addr + 1'b1;
        end
        S_RD_WAIT: begin
            lat <= lat + 1'b1;
            if (lat + 1'b1 == rdlat) begin
                if (dq_in != exp_w) begin
                    if (errors == 0) begin first_err_addr <= {7'b0, addr}; first_err_data <= {exp_w, dq_in}; end
                    errors <= errors + 1'b1;
                end
                words_done <= words_done + 1'b1;
                wait_n <= 1; state <= S_WAIT;                                  // tRP after the auto-precharge
                if (addr + 1'b1 >= len) begin after <= S_IDLE; busy <= 1'b0; done <= 1'b1; end
                else begin addr <= addr + 1'b1; after <= S_NEXT; end
            end
        end
        S_WAIT: begin
            if (wait_n == 0) state <= after; else wait_n <= wait_n - 1'b1;
        end
        default: state <= S_IDLE;
        endcase
    end
endmodule
`default_nettype wire
