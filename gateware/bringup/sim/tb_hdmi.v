// Self-checking testbench for rtl/hdmi_test.v, through its eight pins (the two looks inside the module are
// marked "inside").  The pins are sampled in the middle of every bit; the word boundary of each channel is found
// from the control symbols, as a DVI receiver finds it; a decoder written from the DVI 1.0 specification's
// figure 3-6 (not from the encoder) turns the symbols back into data enable, the syncs and the picture, and the
// raster is measured from those.  Two whole frames of pattern 0, then a few lines each of patterns 1-3, then
// enable = 0 and back.  From gateware/bringup:
//   mkdir -p build/hdmi_check
//   iverilog -g2012 -o build/hdmi_check/tb_hdmi.vvp -s tb_hdmi sim/tb_hdmi.v rtl/hdmi_test.v sim/ecp5_sim_models.v
//   vvp -n build/hdmi_check/tb_hdmi.vvp        (about a minute; ends "N checks, M failures: PASS|FAIL")
//   python3 sim/check_hdmi.py                  (decodes the bit dump again on its own; build/hdmi_check/frame.png)
// Plusargs:  +short        40 lines instead of two frames, no picture checks (for sweeping +skew_ps)
//            +skew_ps=N    clk_pix N ps later than clk_5x's edge (0 .. 39999): the serialiser must not care
//            +dump=FILE    the pins' bits from the first lock to the end of the second frame, one hex digit
//                          {ck, d2, d1, d0} a bit (default build/hdmi_check/hdmi_bits.txt, 8.7 MB; +dump=none)
//            +vcd          build/hdmi_check/tb_hdmi.vcd (large: use with +short)
// -DGATES leaves out the two looks inside, for a synthesised netlist of hdmi_test (yosys write_verilog, with the
// suite's share/yosys/ecp5/cells_sim.v): the run then waits a whole frame for its first vertical sync.
`timescale 1ns/1ps
module tb_hdmi;
    // ---- the clocks, as one PLL makes them: 125 and 25 MHz from one time base, rising edges together ------
    reg clk_5x = 0, clk_pix0 = 0, clk_pix = 0;
    integer skew_ps = 0; real skew = 0.0;
    always #4  clk_5x = ~clk_5x;                    // rises at 4, 12, 20 ...
    always #20 clk_pix0 = ~clk_pix0;                // rises at 20, 60 ...
    always @(clk_pix0) clk_pix <= #(skew) clk_pix0;

    reg enable = 1; reg [1:0] pattern = 0;
    wire d0p, d0n, d1p, d1n, d2p, d2n, ckp, ckn, vtick;
    hdmi_test dut (.clk_pix(clk_pix), .clk_5x(clk_5x), .enable(enable), .pattern(pattern),
                   .gpdi_d0_p(d0p), .gpdi_d0_n(d0n), .gpdi_d1_p(d1p), .gpdi_d1_n(d1n), .gpdi_d2_p(d2p), .gpdi_d2_n(d2n),
                   .gpdi_ck_p(ckp), .gpdi_ck_n(ckn), .vsync_tick(vtick));

    integer checks = 0, fails = 0;
    task check(input string what, input ok); begin
        checks = checks + 1;
        if (ok) $display("  ok: %0s", what); else begin fails = fails + 1; $display("FAIL: %0s", what); end
    end endtask

    // ---- the receiver's arithmetic, from the specification ---------------------------------------------
    localparam [9:0] CTL00 = 10'b1101010100, CTL01 = 10'b0010101011, CTL10 = 10'b0101010100, CTL11 = 10'b1010101011;
    function is_ctl(input [9:0] s); is_ctl = (s == CTL00) || (s == CTL01) || (s == CTL10) || (s == CTL11); endfunction
    function [1:0] ctl_val(input [9:0] s);          // {c1, c0}
        ctl_val = (s == CTL00) ? 2'b00 : (s == CTL01) ? 2'b01 : (s == CTL10) ? 2'b10 : 2'b11;
    endfunction
    function [7:0] tmds_dec(input [9:0] s);         // bit 9: the byte was inverted; bit 8: 1 xor, 0 xnor
        reg [7:0] m; integer i;
        begin
            m = s[9] ? ~s[7:0] : s[7:0];
            tmds_dec[0] = m[0];
            for (i = 1; i < 8; i = i + 1) tmds_dec[i] = s[8] ? (m[i] ^ m[i-1]) : ~(m[i] ^ m[i-1]);
        end
    endfunction
    function integer ones(input [9:0] s); integer i; begin ones = 0; for (i = 0; i < 10; i = i + 1) ones = ones + s[i]; end endfunction
    function tm_bit8(input [7:0] d);                // the encoder's choice of xor (1) or xnor (0) for this byte
        tm_bit8 = !(ones({2'b00, d}) > 4 || (ones({2'b00, d}) == 4 && !d[0]));
    endfunction

    // ---- the picture as the task describes it (a table and a multiplication; the module counts) ---------
    function [23:0] bar_rgb(input integer k);
        case (k) 0: bar_rgb = 24'hffffff; 1: bar_rgb = 24'hffff00; 2: bar_rgb = 24'h00ffff; 3: bar_rgb = 24'h00ff00;
                 4: bar_rgb = 24'hff00ff; 5: bar_rgb = 24'hff0000; 6: bar_rgb = 24'h0000ff; default: bar_rgb = 24'h000000; endcase
    endfunction
    function [23:0] ref_rgb(input integer px, input integer py, input integer bx);
        reg [7:0] gr;
        begin
            gr = (px * 205) / 512;
            if (px == 0 || px == 639 || py == 0 || py == 479) ref_rgb = 24'hffffff;
            else if (py < 320) ref_rgb = bar_rgb(px / 80);
            else if (py >= 392 && py < 408 && px >= bx && px < bx + 16) ref_rgb = 24'hff0000;
            else ref_rgb = {gr, gr, gr};
        end
    endfunction

    // ---- sampling, word boundaries, pixels ---------------------------------------------------------------
    reg [9:0] w [0:2];                              // the last ten bits of each channel, the first sent in bit 0
    integer run [0:2], last [0:2], wph [0:2];
    reg [2:0] locked = 0, ctl;
    integer nbit = 0, c;
    reg synced = 0, seen_vs = 0, de = 0, hs = 1, vs = 1, de_q = 0, hs_q = 1, vs_q = 1, in_pic;
    integer x = 0, y = 0, frame = 0;
    reg chk_on = 1, meas_on = 1, pins_on = 0, pins_off = 0, short_run = 0;
    integer mode = 0, blk_ref = 0;
    reg [23:0] rgb;
    reg [23:0] fb [0:2*307200-1];                   // the two frames
    integer n_pix = 0, n_blank = 0, n_act = 0, n_live = 0, n_pat = 0, n_samp = 0, n_off = 0;
    integer e_de = 0, e_ctl = 0, e_c12 = 0, e_hs = 0, e_vs = 0, e_tm = 0, e_live = 0, e_pat = 0, e_compl = 0, e_off = 0, e_valign = 0;
    integer rd [0:2], rd_max [0:2];
    // the measured raster: 0 visible, 1 front porch, 2 sync, 3 back porch, 4 line (pixels); 5-9 the same in lines
    integer mn [0:9], mx [0:9], nm [0:9];
    task rec(input integer id, input integer v); begin
        if (v < mn[id]) mn[id] = v;
        if (v > mx[id]) mx[id] = v;
        nm[id] = nm[id] + 1;
    end endtask
    function all_are(input integer id, input integer v); all_are = (nm[id] > 0) && (mn[id] == v) && (mx[id] == v); endfunction
    integer pn = 0, pn_de_rise = -1, pn_de_fall = -1, pn_hs_fall = -1, pn_hs_rise = -1;
    integer hsf = 0, hsf_de = 0, hsf_vsf = -1, hsf_vsr = -1, lines_act = 0;
    reg fp_arm = 0, vbp_arm = 0;
    integer fd = 0; reg dump_on = 0;
    integer i;
    initial for (i = 0; i < 3; i = i + 1) begin w[i] = 0; run[i] = 0; last[i] = -100; wph[i] = -1; rd[i] = 0; rd_max[i] = 0; end
    initial for (i = 0; i < 10; i = i + 1) begin mn[i] = 1 << 30; mx[i] = -1; nm[i] = 0; end

    // the raster's numbers from the edges of de, hsync and vsync.  Lines are counted as hsync's leading edges:
    // the vertical front porch is those between the last visible pixel and the vsync edge, and so on.
    task measure; begin
        if (vs_q && !vs) begin
            if (!(hs_q && !hs)) e_valign = e_valign + 1;
            if (pn_de_fall >= 0) rec(6, hsf - hsf_de);
            if (hsf_vsf >= 0) rec(9, hsf - hsf_vsf);
            hsf_vsf = hsf;
        end
        if (!vs_q && vs) begin
            if (!(hs_q && !hs)) e_valign = e_valign + 1;
            if (hsf_vsf >= 0) rec(7, hsf - hsf_vsf);
            hsf_vsr = hsf; vbp_arm = 1;
        end
        if (hs_q && !hs) begin
            if (fp_arm) begin rec(1, pn - pn_de_fall); fp_arm = 0; end
            if (pn_hs_fall >= 0) rec(4, pn - pn_hs_fall);
            pn_hs_fall = pn; hsf = hsf + 1;
        end
        if (!hs_q && hs) begin if (pn_hs_fall >= 0) rec(2, pn - pn_hs_fall); pn_hs_rise = pn; end
        if (!de_q && de) begin
            if (pn_hs_rise >= 0) rec(3, pn - pn_hs_rise);
            pn_de_rise = pn;
            if (vbp_arm) begin rec(8, hsf - hsf_vsr - 1); rec(5, lines_act); vbp_arm = 0; lines_act = 0; end
            lines_act = lines_act + 1;
        end
        if (de_q && !de) begin
            if (pn_de_rise >= 0) rec(0, pn - pn_de_rise);
            pn_de_fall = pn; hsf_de = hsf; fp_arm = 1;
        end
        pn = pn + 1;
    end endtask

    // one pixel: w[0..2] hold its three symbols
    task pixel; begin
        ctl = {is_ctl(w[2]), is_ctl(w[1]), is_ctl(w[0])};
        de = !ctl[0];
        if (ctl[0]) {vs, hs} = ctl_val(w[0]);       // the syncs keep their value through the picture
        if (!synced) begin                          // the frame starts at the first picture symbol after a vertical sync
            if (ctl[0] && !vs) seen_vs = 1;
            if (seen_vs && de) begin synced = 1; x = 0; y = 0; frame = 0; end
        end
        if (synced && chk_on) begin
            n_pix = n_pix + 1;
            in_pic = (x < 640) && (y < 480);
            if (de !== in_pic) e_de = e_de + 1;
            if (!in_pic) begin
                n_blank = n_blank + 1;
                if (ctl !== 3'b111) e_ctl = e_ctl + 1;
                else begin
                    if (w[1] !== CTL00 || w[2] !== CTL00) e_c12 = e_c12 + 1;
                    if (hs !== !(x >= 656 && x < 752)) e_hs = e_hs + 1;
                    if (vs !== !((y == 489 && x >= 656) || y == 490 || (y == 491 && x < 656))) e_vs = e_vs + 1;
                end
                for (c = 0; c < 3; c = c + 1) rd[c] = 0;
            end else if (ctl == 3'b000) begin
                n_act = n_act + 1;
                rgb = {tmds_dec(w[2]), tmds_dec(w[1]), tmds_dec(w[0])};
                for (c = 0; c < 3; c = c + 1) begin
                    if (w[c][8] !== tm_bit8(tmds_dec(w[c]))) e_tm = e_tm + 1;
                    rd[c] = rd[c] + 2 * ones(w[c]) - 10;
                    if (rd[c] > rd_max[c]) rd_max[c] = rd[c];
                    if (-rd[c] > rd_max[c]) rd_max[c] = -rd[c];
                end
                if (mode != 0) begin
                    n_pat = n_pat + 1;
                    if (rgb !== (mode == 1 ? 24'hffffff : mode == 2 ? 24'h000000 : ((x + y) % 2 == 0) ? 24'hffffff : 24'h000000)) e_pat = e_pat + 1;
                end else if (!short_run && frame < 2) fb[frame * 307200 + y * 640 + x] = rgb;
                else begin
                    n_live = n_live + 1;
                    if (rgb !== ref_rgb(x, y, blk_ref + frame)) e_live = e_live + 1;
                end
            end
        end
        if (synced && meas_on) measure;
        if (synced) begin
            x = x + 1;
            if (x == 800) begin x = 0; y = y + 1; if (y == 525) begin y = 0; frame = frame + 1; end end
        end
        de_q = de; hs_q = hs; vs_q = vs;
    end endtask

    // every bit: 2.5 ns after each edge of clk_5x (the DDR model's outputs change 0.5 ns after it)
    always @(clk_5x) begin
        #2.5;
        if (pins_on) begin
            n_samp = n_samp + 1;
            if (d0n !== ~d0p || d1n !== ~d1p || d2n !== ~d2p || ckn !== ~ckp) e_compl = e_compl + 1;
        end
        if (pins_off) begin
            n_off = n_off + 1;
            if ({d0p, d0n, d1p, d1n, d2p, d2n, ckp, ckn} !== 8'b0) e_off = e_off + 1;
        end
        if (dump_on) $fwrite(fd, "%h", {ckp, d2p, d1p, d0p});
        w[0] = {d0p, w[0][9:1]}; w[1] = {d1p, w[1][9:1]}; w[2] = {d2p, w[2][9:1]};
        nbit = nbit + 1;
        // a channel's word boundary: twelve control symbols in a row, ten bits apart
        for (c = 0; c < 3; c = c + 1) if (!locked[c] && is_ctl(w[c])) begin
            run[c] = (nbit - last[c] == 10) ? run[c] + 1 : 1;
            last[c] = nbit;
            if (run[c] == 12) begin
                locked[c] = 1; wph[c] = nbit % 10;
                if (locked == 3'b111) begin pins_on = 1; if (fd != 0) dump_on = 1; end
            end
        end
        if (locked == 3'b111 && nbit % 10 == wph[0]) pixel;
    end

    // ---- the clock pair: its period and its high time ----------------------------------------------------
    reg ck_meas = 1;
    realtime t_ckr = 0, per_min = 1e9, per_max = 0, hi_min = 1e9, hi_max = 0;
    integer n_ck = 0;
    always @(posedge ckp) if (ck_meas && locked == 3'b111) begin
        if (t_ckr > 0) begin
            n_ck = n_ck + 1;
            if ($realtime - t_ckr < per_min) per_min = $realtime - t_ckr;
            if ($realtime - t_ckr > per_max) per_max = $realtime - t_ckr;
        end
        t_ckr = $realtime;
    end
    always @(negedge ckp) if (ck_meas && t_ckr > 0) begin
        if ($realtime - t_ckr < hi_min) hi_min = $realtime - t_ckr;
        if ($realtime - t_ckr > hi_max) hi_max = $realtime - t_ckr;
    end

    // ---- vsync_tick: one clk_pix cycle, 420000 cycles apart ----------------------------------------------
    integer pc = 0, pc_tick = -1, n_tick = 0, e_tickw = 0, gap_min = 1 << 30, gap_max = 0; reg vt_q = 0;
    always @(posedge clk_pix) begin
        pc = pc + 1;
        if (vtick && vt_q) e_tickw = e_tickw + 1;
        if (vtick && !vt_q) begin
            n_tick = n_tick + 1;
            if (pc_tick >= 0) begin if (pc - pc_tick < gap_min) gap_min = pc - pc_tick; if (pc - pc_tick > gap_max) gap_max = pc - pc_tick; end
            pc_tick = pc;
        end
        vt_q = vtick;
    end

    // ---- inside: when the serialiser takes its words, against clk_pix's edges ------------------------------
`ifndef GATES
    realtime t_pix = 0, ld_min = 1e9, ld_max = 0;
    always @(posedge clk_pix) t_pix = $realtime;
    always @(posedge clk_5x) if (dut.ld && locked == 3'b111) begin
        if ($realtime - t_pix < ld_min) ld_min = $realtime - t_pix;
        if ($realtime - t_pix > ld_max) ld_max = $realtime - t_pix;
    end
`endif

    // ---- the run ------------------------------------------------------------------------------------------
    function [23:0] px(input integer f, input integer xx, input integer yy); px = fb[f * 307200 + yy * 640 + xx]; endfunction
    integer e, f, k, p, y0, n_red, bx0 [0:1], by0 [0:1], bx1, by1, lo, hi, prev, v;
    reg [1023:0] dumpname;
    reg ok;
    initial begin
        short_run = $test$plusargs("short");
        if ($value$plusargs("skew_ps=%d", skew_ps)) skew = skew_ps / 1000.0;
        if (!$value$plusargs("dump=%s", dumpname)) dumpname = "build/hdmi_check/hdmi_bits.txt";
        if ($test$plusargs("vcd")) begin $dumpfile("build/hdmi_check/tb_hdmi.vcd"); $dumpvars(0, tb_hdmi); end
        if (!short_run && dumpname != "none") begin
            fd = $fopen(dumpname, "w");
            if (fd == 0) $display("info: cannot write %0s (run from gateware/bringup after mkdir -p build/hdmi_check): no bit dump", dumpname);
        end
        $display("hdmi_test: %0s, clk_pix %0d ps after clk_5x", short_run ? "short run" : "two frames of pattern 0", skew_ps);
`ifndef GATES
        // inside: start the raster two lines before the vertical sync, to save most of a frame of waiting
        #1 dut.hy = 10'd487;
`endif

        wait (synced);                              // (the watchdog at the bottom ends a run that never gets here)
        check("word boundaries found on d0, d1 and d2 (twelve control symbols in a row), the same on all three",
              locked == 3'b111 && wph[0] == wph[1] && wph[0] == wph[2]);
        check("frame start found: the first picture symbol after a vertical sync", synced);

        if (short_run) begin
            wait (y == 4 && x == 690);
            check($sformatf("lines 0 to 4: %0d pixels, %0d not the picture described", n_live, e_live), n_live == 5 * 640 && e_live == 0);
        end else begin
            // ---- two frames of pattern 0 in fb ----
            wait (frame == 2);
            if (fd != 0) begin dump_on = 0; $fclose(fd); fd = 0; end
            e = 0;
            for (f = 0; f < 2; f = f + 1) begin
                for (i = 0; i < 640; i = i + 1) begin if (px(f, i, 0) !== 24'hffffff) e = e + 1; if (px(f, i, 479) !== 24'hffffff) e = e + 1; end
                for (i = 0; i < 480; i = i + 1) begin if (px(f, 0, i) !== 24'hffffff) e = e + 1; if (px(f, 639, i) !== 24'hffffff) e = e + 1; end
            end
            check($sformatf("border: columns 0 and 639 and lines 0 and 479 are white in both frames (%0d pixels not)", e), e == 0);
            check("border is one pixel wide: (120,1) yellow, (638,160) black, (1,400) black, (120,478) grey 48",
                  px(0, 120, 1) === 24'hffff00 && px(0, 638, 160) === 24'h000000 && px(0, 1, 400) === 24'h000000 && px(0, 120, 478) === 24'h303030);
            e = 0;
            for (k = 0; k < 8; k = k + 1) if (px(0, 40 + 80 * k, 160) !== bar_rgb(k)) e = e + 1;
            check($sformatf("bars at their centres, line 160: white %06x yellow %06x cyan %06x green %06x magenta %06x red %06x blue %06x black %06x",
                  px(0, 40, 160), px(0, 120, 160), px(0, 200, 160), px(0, 280, 160), px(0, 360, 160), px(0, 440, 160), px(0, 520, 160), px(0, 600, 160)), e == 0);
            e = 0;
            for (k = 0; k < 8; k = k + 1) begin
                if (px(0, 80 * k + (k == 0 ? 1 : 0), 1) !== bar_rgb(k)) e = e + 1;                // each bar's first column, top line
                if (px(0, 80 * k + 79 - (k == 7 ? 1 : 0), 319) !== bar_rgb(k)) e = e + 1;         // its last column, bottom line
                v = ((40 + 80 * k) * 205) / 512;
                if (px(0, 40 + 80 * k, 320) !== {3{v[7:0]}}) e = e + 1;                           // and the ramp under it
            end
            check("bars are 80 pixels wide, lines 1 to 319; the ramp starts on line 320", e == 0);
            e = 0; lo = 255; hi = 0;
            for (k = 0; k < 2; k = k + 1) begin
                y0 = k ? 470 : 330; prev = 0;
                for (i = 1; i < 639; i = i + 1) begin
                    rgb = px(0, i, y0); v = rgb[7:0];
                    if (rgb[23:16] !== rgb[7:0] || rgb[15:8] !== rgb[7:0] || v < prev || v > prev + 1) e = e + 1;
                    if (v < lo) lo = v; if (v > hi) hi = v;
                    prev = v;
                end
            end
            check($sformatf("ramp (lines 330 and 470): grey, never falling, steps of 0 or 1, from %0d at column 1 to %0d at column 638", lo, hi),
                  e == 0 && lo == 0 && hi == 255);
            // the block: the red pixels below the bars
            ok = 1;
            for (f = 0; f < 2; f = f + 1) begin
                n_red = 0; bx0[f] = 999; by0[f] = 999; bx1 = -1; by1 = -1;
                for (k = 320; k < 479; k = k + 1) for (i = 1; i < 639; i = i + 1) if (px(f, i, k) === 24'hff0000) begin
                    n_red = n_red + 1;
                    if (i < bx0[f]) bx0[f] = i; if (i > bx1) bx1 = i; if (k < by0[f]) by0[f] = k; if (k > by1) by1 = k;
                end
                if (n_red != 256 || bx1 - bx0[f] != 15 || by1 - by0[f] != 15 || by0[f] != 392) ok = 0;
            end
            check($sformatf("moving block: 16 x 16 red, lines 392-407, at column %0d in the first frame and %0d in the second (one pixel on)",
                  bx0[0], bx0[1]), ok && bx0[1] == bx0[0] + 1);
            for (f = 0; f < 2; f = f + 1) begin
                e = 0;
                for (k = 0; k < 480; k = k + 1) for (i = 0; i < 640; i = i + 1) if (px(f, i, k) !== ref_rgb(i, k, bx0[f])) e = e + 1;
                check($sformatf("frame %0d: all 307200 pixels are the picture described (%0d are not)", f + 1, e), e == 0);
            end
            blk_ref = bx0[0];
        end

        // ---- patterns 1 to 3, four lines each, and back to 0 ----
        for (p = 1; p <= 3; p = p + 1) begin
            wait (x == 700); pattern = p; mode = p; n_pat = 0; e_pat = 0;       // in the blanking: the next line has it
            y0 = y; wait (y == y0 + 4 && x == 690);
            check($sformatf("pattern %0d (%0s): %0d pixels, %0d wrong", p, p == 1 ? "white" : p == 2 ? "black" : "checkerboard, white where column + line is even",
                  n_pat, e_pat), n_pat == 4 * 640 && e_pat == 0);
        end
        wait (x == 700); pattern = 0; mode = 0; n_live = 0; e_live = 0;
        y0 = y; wait (y == y0 + 3 && x == 690);
        check($sformatf("pattern 0 again: %0d pixels, %0d wrong", n_live, e_live), n_live >= 3 * 640 && e_live == 0);

        // ---- enable = 0 for a line, then back ----
        wait (x == 700); enable = 0; chk_on = 0; meas_on = 0; pins_on = 0; ck_meas = 0;
        #400 pins_off = 1; #32000 pins_off = 0;
        check($sformatf("enable = 0: all eight pins low (%0d samples, %0d with a pin high)", n_off, e_off), n_off >= 7990 && e_off == 0);
        enable = 1; k = n_pix;
        #800 t_ckr = 0; chk_on = 1; pins_on = 1; ck_meas = 1;
        y0 = y; wait (y == y0 + 3 && x == 690);
        check($sformatf("enable = 1 again: the stream is back on the same word boundary and raster position (%0d pixels compared since)", n_pix - k),
              n_pix - k > 1600 && e_de == 0 && e_ctl == 0 && e_hs == 0 && e_vs == 0 && e_live == 0);

        // ---- what was counted all the way ----
        check($sformatf("blanking: %0d pixels, every symbol on all three channels one of the four control codes (%0d not)", n_blank, e_ctl), n_blank > 0 && e_ctl == 0);
        check($sformatf("blanking: d1 and d2 carry control code 00 throughout (%0d not)", e_c12), e_c12 == 0);
        check($sformatf("data enable: 640 x 480 in 800 x 525, pixel for pixel (%0d pixels compared, %0d wrong)", n_pix, e_de), n_pix > 0 && e_de == 0);
        check($sformatf("horizontal, measured on %0d lines: visible %0d, front porch %0d, sync %0d (low), back porch %0d, line %0d pixels",
              nm[4], mn[0], mn[1], mn[2], mn[3], mn[4]),
              all_are(0, 640) && all_are(1, 16) && all_are(2, 96) && all_are(3, 48) && all_are(4, 800) && e_hs == 0);
        if (!short_run) begin
            check($sformatf("vertical, measured on %0d frames: visible %0d, front porch %0d, sync %0d (low), back porch %0d, frame %0d lines",
                  nm[5], mn[5], mn[6], mn[7], mn[8], mn[9]),
                  all_are(5, 480) && all_are(6, 10) && all_are(7, 2) && all_are(8, 33) && all_are(9, 525) && e_vs == 0);
            check("vsync changes on hsync's leading edge", e_valign == 0 && nm[7] > 0);
            check($sformatf("vsync_tick: %0d ticks, each one clk_pix cycle, %0d cycles apart", n_tick, gap_min),
                  n_tick >= 3 && e_tickw == 0 && gap_min == 420000 && gap_max == 420000);
        end else check($sformatf("vsync_tick: %0d tick, one clk_pix cycle", n_tick), n_tick == 1 && e_tickw == 0);
        check($sformatf("picture: %0d symbols, every one the transition-minimised code of its byte (%0d not)", 3 * n_act, e_tm), n_act > 0 && e_tm == 0);
        check($sformatf("running disparity of the picture symbols, from 0 at each blanking: at most %0d on d0, %0d on d1, %0d on d2 (limit 10)",
              rd_max[0], rd_max[1], rd_max[2]), rd_max[0] <= 10 && rd_max[1] <= 10 && rd_max[2] <= 10);
        check($sformatf("every _n pin the complement of its _p (%0d samples, %0d not)", n_samp, e_compl), n_samp > 0 && e_compl == 0);
        check($sformatf("clock pair: %0d periods of %0.3f ns (clk_pix's), high for %0.3f ns", n_ck, per_min, hi_min),
              n_ck > 1000 && per_min > 39.999 && per_max < 40.001 && hi_min > 19.999 && hi_max < 20.001);
`ifndef GATES
        check($sformatf("inside: the serialiser takes its words %0.3f ns after clk_pix's edge and %0.3f ns before the next (16 at least)",
              ld_min, 40.0 - ld_max), ld_min > 15.999 && 40.0 - ld_max > 15.999);
`endif
        $display("%0d checks, %0d failures: %s", checks, fails, fails == 0 ? "PASS" : "FAIL");
        $finish;
    end
    initial begin
        #60_000_000 $display("FAIL: timeout (word boundaries %b, frame start %b, frame %0d line %0d)", locked, synced, frame, y);
        $display("%0d checks, %0d failures: FAIL", checks + 1, fails + 1);
        $finish;
    end
endmodule
