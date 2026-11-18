// A DVI test picture on the mini-HDMI jack (J503; "GPDI": the four TMDS pairs come straight from FPGA pins
// through series capacitors).  640 x 480 with the 60 Hz timing from a 25.000 MHz pixel clock (800 x 525 in all:
// 31.25 kHz, 59.52 Hz, which every monitor takes), ten bits a pixel through DDR output registers on a 125 MHz
// clock (five cycles, both edges).  DVI, not HDMI: no data islands, no sound, RGB 8:8:8 full range.
//
// Timing, in pixel clocks and lines (hx, hy count from the first visible pixel; both syncs are negative):
//   horizontal  640 visible (hx 0-639), front porch 16, sync 96 (low for hx 656-751), back porch 48
//   vertical    480 visible (hy 0-479), front porch 10, sync 2, back porch 33; the vertical sync changes on
//               hsync's leading edge, as CEA-861 draws the format: low from hx 656 of line 489 to hx 655 of line 491
//
// pattern  0  a one-pixel white border on the outermost pixels (columns 0 and 639, lines 0 and 479: a cropped
//             or shifted picture loses a side); inside it eight bars, 80 pixels each, down to line 319 (white,
//             yellow, cyan, green, magenta, red, blue, black: all three channels, each alone and in pairs); below
//             them a grey ramp, black at the left to white at the right (level = column * 205 / 512, so 0-255);
//             on the ramp a red 16 x 16 block (lines 392-407) that moves one pixel a frame, column 1 to 623 and
//             back, 10.5 s each way: a picture whose block stands still is frozen
//          1  white       2  black       3  a one-pixel checkerboard (white where column + line is even);
//             these three fill all 640 x 480, with no border and no block
// Channels as DVI has them: blue on data 0 (hsync and vsync ride there through the blanking), green on data 1,
// red on data 2; the clock pair is high for the first five bits of a pixel.
//
// The pins.  The LPF makes all eight LVCMOS33, so each pair is two single-ended pins and each pin has its own
// DDR register: P takes the bits, N the same bits inverted, both loaded at the same edge from flip-flops.  (The
// demo's hdmi_out.v drives only the P pad and has an LVCMOS33D buffer make N; that needs a changed LPF and
// cannot do the next line.)  enable = 0 loads zeros into all eight: every pin low, no TMDS, no clock.  The
// raster and vsync_tick keep running, so the picture is there again within two pixels of enable = 1.
//
// The crossing from clk_pix to clk_5x.  The two clocks are outputs of one PLL: exactly 5 to 1, with a fixed
// phase between them, which this module does not need to know.  The three encoded words (30 flip-flops on
// clk_pix) change once every five clk_5x cycles; a counter of five in clk_5x decides in which of them the
// serialiser takes the words, and it is put in step with clk_pix by `tog`, a flip-flop that clk_pix toggles and
// clk_5x samples, with a second flip-flop behind the sampler so that what the logic reads has settled.  The
// cycle in which the change shows must be the counter's state 0, the state whose closing edge loads the words:
// two cycles after the edge that caught the change.  That edge is 16 to 24 ns after the words changed and 16
// to 24 ns before they change again (24 and 16 with the PLL's edges together), so the load has two clk_5x
// periods of margin on either side whatever the phase between the clocks, and all it asks is that the two
// paths that cross (tog to its sampler; a word bit through one LUT to a shift register) are shorter than one
// clk_5x period.  nextpnr holds a path between two clocks to no period, even two clocks of one PLL, but it
// reports the longest: "Max delay posedge clk_pix -> posedge clk_5x", which should read about 2 ns.  A sample
// of tog caught mid-change (possible only if the PLL puts clk_pix's edge inside the sampler's window) settles
// to the old value or the new, so the change shows a state early or late now and then.  That cannot move the
// load: the counter free-runs, and is put in step again only after four pixels in a row say it is out (the
// first four pixels after configuration, and after the PLL has lost lock); and the two positions it can
// settle in when the edges coincide are the 16 ns and the 24 ns ends of the range above, both safe.
// Nothing goes from clk_5x back to clk_pix.  enable and pattern are levels from anywhere: two flip-flops each.
`default_nettype none

module hdmi_test (
    input  wire       clk_pix,      // 25 MHz pixel clock
    input  wire       clk_5x,       // 125 MHz, phase-locked to clk_pix (same PLL)
    input  wire       enable,       // 0: all eight pins driven low (no TMDS at all); quasi-static, any clock domain
    input  wire [1:0] pattern,      // 0 bars, border, ramp and the moving block; 1 white; 2 black; 3 checkerboard; quasi-static
    output wire       gpdi_d0_p, gpdi_d0_n, gpdi_d1_p, gpdi_d1_n, gpdi_d2_p, gpdi_d2_n, gpdi_ck_p, gpdi_ck_n,
    output wire       vsync_tick    // one clk_pix cycle per frame (at the vertical sync's leading edge), enable or not
);
    localparam HA = 640, HFP = 16, HS = 96, HT = 800;           // the back porch is the rest: 48
    localparam VA = 480, VFP = 10, VS = 2,  VT = 525;           // 33
    localparam BAR_END = 320;                                   // the bars end above this line, the ramp starts on it
    localparam BLK = 16, BLK_Y = 392;                           // the moving block: its size and its top line

    // ---- the raster (clk_pix) ----------------------------------------------------------------------------
    reg [9:0] hx = 10'd0, hy = 10'd0;
    wire h_last = (hx == HT - 1);
    always @(posedge clk_pix) begin
        hx <= h_last ? 10'd0 : hx + 10'd1;
        if (h_last) hy <= (hy == VT - 1) ? 10'd0 : hy + 10'd1;
    end
    wire active = (hx < HA) && (hy < VA);
    wire hs_n   = ~((hx >= HA + HFP) && (hx < HA + HFP + HS));
    wire [9:0] vline = hy + ((hx >= HA + HFP) ? 10'd1 : 10'd0);           // the line number as hsync's leading edge counts it
    wire vs_n   = ~((vline >= VA + VFP) && (vline < VA + VFP + VS));
    reg tick = 1'b0;
    always @(posedge clk_pix) tick <= (hx == HA + HFP - 1) && (hy == VA + VFP - 1);
    assign vsync_tick = tick;

    // ---- the picture (clk_pix) ---------------------------------------------------------------------------
    // along the line: the bar number (80 pixels each) and the ramp's level (205 a pixel: 639 * 205 = 255.8 * 512)
    reg [6:0]  bx = 7'd0;
    reg [2:0]  bar = 3'd0;
    reg [16:0] ramp = 17'd0;
    always @(posedge clk_pix)
        if (h_last) begin bx <= 7'd0; bar <= 3'd0; ramp <= 17'd0; end
        else begin
            ramp <= ramp + 17'd205;
            if (bx == 7'd79) begin bx <= 7'd0; bar <= bar + 3'd1; end else bx <= bx + 7'd1;
        end
    // the block's left column: 1 .. 623 and back, a pixel a frame
    reg [9:0] blk_x = 10'd1;
    reg       blk_back = 1'b0;
    always @(posedge clk_pix) if (tick) begin
        if (!blk_back) begin if (blk_x == HA - 1 - BLK) begin blk_back <= 1'b1; blk_x <= blk_x - 10'd1; end else blk_x <= blk_x + 10'd1; end
        else           begin if (blk_x == 10'd1)        begin blk_back <= 1'b0; blk_x <= blk_x + 10'd1; end else blk_x <= blk_x - 10'd1; end
    end
    reg [1:0] pat_m = 2'd0, pat = 2'd0;
    always @(posedge clk_pix) begin pat_m <= pattern; pat <= pat_m; end

    wire border = (hx == 0) || (hx == HA - 1) || (hy == 0) || (hy == VA - 1);
    wire in_blk = (hy >= BLK_Y) && (hy < BLK_Y + BLK) && (hx >= blk_x) && (hx < blk_x + BLK);
    wire [7:0] grey = ramp[16:9];
    reg [23:0] rgb;                                             // {red, green, blue}
    always @(*) case (pat)
        2'd0:    rgb = border       ? 24'hffffff :
                       hy < BAR_END ? {{8{~bar[1]}}, {8{~bar[2]}}, {8{~bar[0]}}} :
                       in_blk       ? 24'hff0000 : {grey, grey, grey};
        2'd1:    rgb = 24'hffffff;
        2'd2:    rgb = 24'h000000;
        default: rgb = {24{~(hx[0] ^ hy[0])}};
    endcase
    reg [23:0] rgb1 = 24'd0;
    reg        de1 = 1'b0, hs1 = 1'b1, vs1 = 1'b1;
    always @(posedge clk_pix) begin rgb1 <= rgb; de1 <= active; hs1 <= hs_n; vs1 <= vs_n; end

    // ---- the three encoders (clk_pix; two more registers) ------------------------------------------------
    wire [9:0] q0, q1, q2;
    hdmi_test_tmds e0 (.clk(clk_pix), .d(rgb1[7:0]),   .c({vs1, hs1}), .de(de1), .q(q0));
    hdmi_test_tmds e1 (.clk(clk_pix), .d(rgb1[15:8]),  .c(2'b00),      .de(de1), .q(q1));
    hdmi_test_tmds e2 (.clk(clk_pix), .d(rgb1[23:16]), .c(2'b00),      .de(de1), .q(q2));

    // ---- the serialiser (clk_5x): see "the crossing" above -----------------------------------------------
    reg tog = 1'b0;
    always @(posedge clk_pix) tog <= ~tog;
    reg [2:0] tog_s = 3'b000;               // tog sampled, and two flip-flops on: the logic reads only those two
    reg [2:0] ph = 3'd0;                    // 0..4; state 0 is the cycle in which tog's change shows
    reg [1:0] miss = 2'd0;                  // pixels in a row whose change showed in another state
    reg       ld = 1'b1;                    // ph == 0: the words are taken at the edge that ends this cycle
    wire seen    = tog_s[2] ^ tog_s[1];
    wire realign = seen && (ph != 3'd0) && (miss == 2'd3);
    wire [2:0] ph_next = realign ? 3'd1 : (ph >= 3'd4) ? 3'd0 : ph + 3'd1;
    always @(posedge clk_5x) begin
        tog_s <= {tog_s[1:0], tog};
        ph    <= ph_next;
        ld    <= (ph_next == 3'd0);
        if (seen) miss <= (ph == 3'd0 || miss == 2'd3) ? 2'd0 : miss + 2'd1;
    end
    reg en_m = 1'b0, en = 1'b0;
    always @(posedge clk_5x) begin en_m <= enable; en <= en_m; end

    hdmi_test_pair p0 (.clk(clk_5x), .ld(ld), .en(en), .w(q0),             .p(gpdi_d0_p), .n(gpdi_d0_n));
    hdmi_test_pair p1 (.clk(clk_5x), .ld(ld), .en(en), .w(q1),             .p(gpdi_d1_p), .n(gpdi_d1_n));
    hdmi_test_pair p2 (.clk(clk_5x), .ld(ld), .en(en), .w(q2),             .p(gpdi_d2_p), .n(gpdi_d2_n));
    hdmi_test_pair pc (.clk(clk_5x), .ld(ld), .en(en), .w(10'b0000011111), .p(gpdi_ck_p), .n(gpdi_ck_n));
endmodule

// One pair: the word goes out two bits a cycle, the least significant first, on P, and inverted on N.  Each pin
// has its own shift register, so its DDR register's two inputs come straight from flip-flops and the two pins
// change together; with en = 0 both registers load zeros.
module hdmi_test_pair (
    input  wire       clk,          // 125 MHz
    input  wire       ld,           // one cycle in five: take w at the edge that ends it
    input  wire       en,
    input  wire [9:0] w,
    output wire       p, n
);
    reg [9:0] sp = 10'd0, sn = 10'd0;
    always @(posedge clk)
        if (ld) begin sp <= en ? w : 10'd0; sn <= en ? ~w : 10'd0; end
        else    begin sp <= {2'b00, sp[9:2]}; sn <= {2'b00, sn[9:2]}; end
    ODDRX1F ddr_p (.SCLK(clk), .RST(1'b0), .D0(sp[0]), .D1(sp[1]), .Q(p));
    ODDRX1F ddr_n (.SCLK(clk), .RST(1'b0), .D0(sn[0]), .D1(sn[1]), .Q(n));
endmodule

// The DVI 1.0 encoder (the specification's figure 3-5), a pixel a clock, two registers deep.
//   de = 0: one of the four control codes, chosen by c = {c1, c0}, and the disparity count starts again from 0
//   de = 1: d as a transition-minimised 9-bit word q_m (register 1), sent as it is or inverted, whichever
//           pulls the running disparity of the line back towards 0 (register 2)
module hdmi_test_tmds (
    input  wire       clk,
    input  wire [7:0] d,
    input  wire [1:0] c,
    input  wire       de,
    output reg  [9:0] q = 10'b1101010100
);
    function [3:0] ones8(input [7:0] v);
        integer i;
        begin ones8 = 4'd0; for (i = 0; i < 8; i = i + 1) ones8 = ones8 + {3'b000, v[i]}; end
    endfunction

    // register 1: q_m[i] = q_m[i-1] xor d[i], or xnor when d has more than four ones (or four and d[0] = 0)
    wire [3:0] n1d = ones8(d);
    wire use_xnor = (n1d > 4'd4) || (n1d == 4'd4 && !d[0]);
    wire [7:0] chain;
    assign chain[0] = d[0];
    genvar k;
    generate for (k = 1; k < 8; k = k + 1) begin : xor_chain
        assign chain[k] = chain[k-1] ^ d[k] ^ use_xnor;
    end endgenerate
    reg [8:0] qm = 9'd0;
    reg [1:0] c1 = 2'b00;
    reg       de1 = 1'b0;
    always @(posedge clk) begin qm <= {~use_xnor, chain}; c1 <= c; de1 <= de; end

    // register 2: cnt is the ones minus the zeros sent since the blanking (always even, never beyond +-8)
    wire [3:0] n1q = ones8(qm[7:0]);
    wire signed [4:0] diff = $signed({n1q, 1'b0}) - 5'sd8;      // ones minus zeros in q_m[7:0]: -8 .. +8
    reg  signed [4:0] cnt = 5'sd0;
    wire cnt_pos = !cnt[4] && (cnt != 5'sd0);
    wire cnt_neg = cnt[4];
    always @(posedge clk)
        if (!de1) begin
            cnt <= 5'sd0;
            case (c1)
                2'b00:   q <= 10'b1101010100;
                2'b01:   q <= 10'b0010101011;
                2'b10:   q <= 10'b0101010100;
                default: q <= 10'b1010101011;
            endcase
        end else if (cnt == 5'sd0 || n1q == 4'd4) begin
            q   <= {~qm[8], qm[8], qm[8] ? qm[7:0] : ~qm[7:0]};
            cnt <= qm[8] ? cnt + diff : cnt - diff;
        end else if ((cnt_pos && n1q > 4'd4) || (cnt_neg && n1q < 4'd4)) begin
            q   <= {1'b1, qm[8], ~qm[7:0]};
            cnt <= cnt + $signed({3'b000, qm[8], 1'b0}) - diff;
        end else begin
            q   <= {1'b0, qm[8], qm[7:0]};
            cnt <= cnt - $signed({3'b000, ~qm[8], 1'b0}) + diff;
        end
endmodule
`default_nettype wire
