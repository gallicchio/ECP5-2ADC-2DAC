// Unit test of sdram_test against sdram_model: the clock through the ODDRX1F model as in top.v, every read
// latency 1..7, patterns 0 and 6, both clock polarities.  Prints the error count of each; the latency that
// passes is the one top.v should default to (sd_rdlat).
`timescale 1ns/1ps
module tb_sdram;
    reg clk_s = 0; always #10 clk_s = ~clk_s;
    wire [12:0] a; wire [1:0] ba; wire cs_n, ras_n, cas_n, we_n, cke, dqm; wire [15:0] dq_out; wire dq_oe;
    reg  [15:0] dq_in = 0; wire [15:0] dq; wire sdram_clk;
    reg start = 0, abort = 0; reg [3:0] pattern = 0, rdlat = 4; reg [24:0] len = 64; reg pol = 0;
    wire init_done, busy, done; wire [31:0] errors, fea, fed; wire [24:0] words;
    always @(posedge clk_s) dq_in <= dq;
    assign dq = dq_oe ? dq_out : 16'bz;
    pullup pu [15:0] (dq);
    sdram_test dut (.clk_s(clk_s), .a(a), .ba(ba), .cs_n(cs_n), .ras_n(ras_n), .cas_n(cas_n), .we_n(we_n), .cke(cke), .dqm(dqm),
                    .dq_out(dq_out), .dq_oe(dq_oe), .dq_in(dq_in), .start(start), .abort(abort), .pattern(pattern), .rdlat(rdlat), .len(len),
                    .init_done(init_done), .busy(busy), .done(done), .errors(errors), .first_err_addr(fea), .first_err_data(fed), .words_done(words));
    ODDRX1F oddr (.SCLK(clk_s), .RST(1'b0), .D0(~pol), .D1(pol), .Q(sdram_clk));
    sdram_model m (.clk(sdram_clk), .cke(cke), .cs_n(cs_n), .ras_n(ras_n), .cas_n(cas_n), .we_n(we_n), .ba(ba), .a(a), .dqml(dqm), .dqmh(dqm), .dq(dq));
    integer lat, p;
    task run_one; begin
        @(posedge clk_s); start <= 1; @(posedge clk_s); start <= 0;
        wait (busy); wait (done); #100;                                  // `done` is still the last run's until the start is taken (a refresh may delay it)
        $display("pol %0d pattern %0d rdlat %0d: errors %0d of %0d (first at %0d: expected %04x got %04x)", pol, pattern, rdlat, errors, len, fea, fed[31:16], fed[15:0]);
    end endtask
    initial begin
        wait (init_done); #1000;
        $display("init done at %t: loads %0d refreshes %0d CL %0d", $time, m.loads, m.refreshes, m.cl);
        for (p = 0; p < 2; p = p + 1) begin
            pol = p;
            pattern = 0;
            for (lat = 1; lat <= 7; lat = lat + 1) begin rdlat = lat; run_one; end
            pattern = 6; rdlat = 4; run_one;
        end
        $display("model complaints: %0d", m.bad);
        $finish;
    end
endmodule
