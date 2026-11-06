// Self-checking testbench for rtl/top.v: the PC's side of the UART is here as tasks, the board's
// other side as the models in models.v and sdram_model.v.  `make sim` runs it; it ends with PASS or
// the count of failures.  The gate of the frequency counters is 1 ms here (GATE_CYCLES = 25000), so
// the counts read Hz / 1000.
`timescale 1ns/1ps
module tb_top;
    localparam real BIT = 1000.0;            // 1 Mbaud
    reg clk_tcxo = 0; always #20 clk_tcxo = ~clk_tcxo;          // 25 MHz
    reg clk_ext = 0;  always #50 clk_ext = ~clk_ext;            // 10 MHz on CLK IN
    reg clk_si0 = 0;  always #500 clk_si0 = ~clk_si0;           // 1 MHz
    reg clk_si1 = 0;  always #5000 clk_si1 = ~clk_si1;          // 100 kHz
    wire clk_si2 = 1'b0;                                        // nothing (an unprogrammed Si5351 output)
    reg eth_rxc = 0;  always #4 eth_rxc = ~eth_rxc;             // 125 MHz
    reg uart_rx = 1; wire uart_tx;
    reg btn0 = 1, btn1 = 1;
    wire clk_out; wire [7:0] leds; wire led_r, led_g, led_b;
    wire [11:0] adc_a_d, adc_b_d; wire adc_a_otr, adc_b_otr, adc_a_clk, adc_b_clk, adc_dcs, adc_dfs, adc_pdwn_a, adc_pdwn_b;
    wire [13:0] dac_p1_d, dac_p2_d; wire dac_clk1, dac_clk2, dac_wrt1, dac_wrt2, dac_mode, dac_sleep;
    wire [12:0] sdram_a; wire [1:0] sdram_ba; wire [15:0] sdram_dq;
    wire sdram_clk, sdram_cke, sdram_cs_n, sdram_ras_n, sdram_cas_n, sdram_we_n, sdram_dqml, sdram_dqmh;
    wire eth_mdc, eth_rst_n, eth_mdio, usb_pullup, i2c_scl, i2c_sda;
    wire [7:0] pmoda, pmodb;
    pullup(eth_mdio); pullup(i2c_scl); pullup(i2c_sda);
    pullup sdram_pu [15:0] (sdram_dq);          // an undriven data bus reads 0xFFFF, as a wrong read latency must

    top #(.UART_DIV(25), .GATE_CYCLES(25000), .BUILD_ID(32'h20261105)) dut (
        .clk_tcxo(clk_tcxo), .clk_ext(clk_ext), .clk_si0(clk_si0), .clk_si1(clk_si1), .clk_si2(clk_si2), .clk_out(clk_out),
        .btn0(btn0), .btn1(btn1),
        .led0(leds[0]), .led1(leds[1]), .led2(leds[2]), .led3(leds[3]), .led4(leds[4]), .led5(leds[5]), .led6(leds[6]), .led7(leds[7]),
        .led_r(led_r), .led_g(led_g), .led_b(led_b), .uart_rx(uart_rx), .uart_tx(uart_tx), .ftdi_rts(1'b1), .ftdi_dtr(1'b0),
        .adc_a_d(adc_a_d), .adc_b_d(adc_b_d), .adc_a_otr(adc_a_otr), .adc_b_otr(adc_b_otr),
        .adc_a_clk(adc_a_clk), .adc_b_clk(adc_b_clk), .adc_dcs(adc_dcs), .adc_dfs(adc_dfs), .adc_pdwn_a(adc_pdwn_a), .adc_pdwn_b(adc_pdwn_b),
        .dac_p1_d(dac_p1_d), .dac_p2_d(dac_p2_d), .dac_clk1(dac_clk1), .dac_clk2(dac_clk2), .dac_wrt1(dac_wrt1), .dac_wrt2(dac_wrt2),
        .dac_mode(dac_mode), .dac_sleep(dac_sleep),
        .sdram_a(sdram_a), .sdram_ba(sdram_ba), .sdram_dq(sdram_dq), .sdram_clk(sdram_clk), .sdram_cke(sdram_cke), .sdram_cs_n(sdram_cs_n),
        .sdram_ras_n(sdram_ras_n), .sdram_cas_n(sdram_cas_n), .sdram_we_n(sdram_we_n), .sdram_dqml(sdram_dqml), .sdram_dqmh(sdram_dqmh),
        .eth_rxc(eth_rxc), .eth_int_n(1'b1), .eth_mdc(eth_mdc), .eth_rst_n(eth_rst_n), .eth_mdio(eth_mdio),
        .usb_pullup(usb_pullup), .i2c_scl(i2c_scl), .i2c_sda(i2c_sda), .pmoda(pmoda), .pmodb(pmodb));

    adc_model adc_a (.clk(adc_a_clk), .d(adc_a_d), .otr(adc_a_otr), .which(2'd0));
    adc_model adc_b (.clk(adc_b_clk), .d(adc_b_d), .otr(adc_b_otr), .which(2'd1));
    dac_monitor mon1 (.wrt(dac_wrt1), .clk(dac_clk1), .d(dac_p1_d));
    dac_monitor mon2 (.wrt(dac_wrt2), .clk(dac_clk2), .d(dac_p2_d));
    sdram_model sdram (.clk(sdram_clk), .cke(sdram_cke), .cs_n(sdram_cs_n), .ras_n(sdram_ras_n), .cas_n(sdram_cas_n), .we_n(sdram_we_n),
                       .ba(sdram_ba), .a(sdram_a), .dqml(sdram_dqml), .dqmh(sdram_dqmh), .dq(sdram_dq));
    i2c_slave_model si (.scl(i2c_scl), .sda(i2c_sda));
    mdio_slave_model phy (.mdc(eth_mdc), .mdio(eth_mdio));

    // ---- the PC's UART --------------------------------------------------------------------------
    // send_byte returns as soon as the stop bit begins (and makes sure the line has idled one bit before the
    // next start), so recv_byte is waiting before the board can answer: the PC's two directions are independent.
    realtime t_sent = 0;
    task send_byte(input [7:0] b); integer i; begin
        if ($realtime - t_sent < BIT) #(BIT - ($realtime - t_sent));
        uart_rx = 0; #(BIT);
        for (i = 0; i < 8; i = i + 1) begin uart_rx = b[i]; #(BIT); end
        uart_rx = 1; t_sent = $realtime;
    end endtask
    task recv_byte(output [7:0] b); integer i; begin
        if (uart_tx !== 1'b0) @(negedge uart_tx);
        #(BIT * 1.5);
        for (i = 0; i < 8; i = i + 1) begin b[i] = uart_tx; #(BIT); end
    end endtask
    task wr(input [6:0] a, input [31:0] d); begin
        send_byte({1'b1, a}); send_byte(d[7:0]); send_byte(d[15:8]); send_byte(d[23:16]); send_byte(d[31:24]);
        #(BIT * 1.2);                        // the board acts on a write half a bit into the stop bit
    end endtask
    task rd(input [6:0] a, output [31:0] d); reg [7:0] b0, b1, b2, b3; begin
        send_byte({1'b0, a}); recv_byte(b0); recv_byte(b1); recv_byte(b2); recv_byte(b3); d = {b3, b2, b1, b0};
    end endtask
    reg [31:0] dump [0:8191];
    task dump_words(input integer n); integer i; reg [7:0] b0, b1, b2, b3; begin
        wr(7'h7e, n); send_byte(8'h7f);
        for (i = 0; i < n; i = i + 1) begin recv_byte(b0); recv_byte(b1); recv_byte(b2); recv_byte(b3); dump[i] = {b3, b2, b1, b0}; end
    end endtask

    integer fails = 0, checks = 0;
    task check(input [639:0] what, input ok); begin
        checks = checks + 1;
        if (!ok) begin fails = fails + 1; $display("FAIL: %0s at %t", what, $time); end
        else $display("  ok: %0s", what);
    end endtask

    // ---- bit-banged I2C and MDIO through the GPIO register, as host/ecp5bu.py does ----------------
    reg [12:0] g = 13'b0_0101_0011_0101;
    task gpio(); begin wr(7'h06, g); end endtask
    task i2c_scl_(input v); begin g[4] = v; gpio(); end endtask
    task i2c_sda_(input v); begin g[5] = v; gpio(); end endtask
    task i2c_start(); begin i2c_sda_(1); i2c_scl_(1); i2c_sda_(0); i2c_scl_(0); end endtask
    task i2c_stop(); begin i2c_sda_(0); i2c_scl_(1); i2c_sda_(1); end endtask
    task i2c_write(input [7:0] b, output ack); integer i; reg [31:0] st; begin
        for (i = 7; i >= 0; i = i - 1) begin i2c_sda_(b[i]); i2c_scl_(1); i2c_scl_(0); end
        i2c_sda_(1); i2c_scl_(1); rd(7'h04, st); ack = ~st[8]; i2c_scl_(0);
    end endtask
    task i2c_read(input last, output [7:0] b); integer i; reg [31:0] st; begin
        i2c_sda_(1);
        for (i = 7; i >= 0; i = i - 1) begin i2c_scl_(1); rd(7'h04, st); b[i] = st[8]; i2c_scl_(0); end
        i2c_sda_(last); i2c_scl_(1); i2c_scl_(0); i2c_sda_(1);      // ACK = SDA low; the last byte gets a NACK
    end endtask
    task mdio_bit(input v); begin g[2] = v; g[3] = 1; g[1] = 0; gpio(); g[1] = 1; gpio(); end endtask
    task mdio_read(input [4:0] ph, input [4:0] ra, output [15:0] d); integer i; reg [31:0] st; begin
        for (i = 0; i < 32; i = i + 1) mdio_bit(1);
        mdio_bit(0); mdio_bit(1); mdio_bit(1); mdio_bit(0);
        for (i = 4; i >= 0; i = i - 1) mdio_bit(ph[i]);
        for (i = 4; i >= 0; i = i - 1) mdio_bit(ra[i]);
        g[3] = 0; g[1] = 0; gpio(); g[1] = 1; gpio();       // TA: release, one clock
        g[1] = 0; gpio(); g[1] = 1; gpio();
        for (i = 15; i >= 0; i = i - 1) begin g[1] = 0; gpio(); rd(7'h04, st); d[i] = st[10]; g[1] = 1; gpio(); end
        g[1] = 0; gpio();
    end endtask

    // ---- the tests ---------------------------------------------------------------------------------
    reg [31:0] v, v2, seq0, seq1; integer i, k, i0, errs, ack; reg [7:0] b; reg [15:0] lut [0:1023]; reg [15:0] w16;
`ifdef DEBUG
    always @(posedge dut.rx_valid) $display("  uart rx %02x at %t", dut.rx_data, $time);
    always @(posedge dut.tx_start) $display("  uart tx %02x at %t (state %0d)", dut.tx_data, $time, dut.bus.state);
    always @(posedge dut.we) $display("  reg write %02x <= %08x at %t", dut.addr, dut.wdata, $time);
`endif
    initial begin
        $dumpfile("../build/tb_top.vcd"); $dumpvars(0, tb_top);
        $readmemh("sine_lut.hex", lut);
        #2000;
        // 1. the bus
        rd(7'h00, v); check("ID register", v == 32'hEC5BA2D2);
        rd(7'h01, v); check("VERSION register", v == 32'h20261105);
        wr(7'h02, 32'hCAFE1234); rd(7'h02, v); check("SCRATCH write and read back", v == 32'hCAFE1234);
        rd(7'h5a, v); check("an unassigned register reads DEAD00xx", v == 32'hDEAD005A);
        // a broken write (two data bytes missing), then the resync: five zeros
        send_byte(8'h82); send_byte(8'h11); send_byte(8'h22);
        send_byte(8'h00); send_byte(8'h00);
        for (i = 0; i < 3; i = i + 1) begin send_byte(8'h00); recv_byte(b); recv_byte(b); recv_byte(b); recv_byte(b); end
        rd(7'h02, v); check("resync after a broken write (scratch holds the zeros)", v == 32'h00002211);
        wr(7'h02, 32'h0); rd(7'h02, v); check("bus usable after resync", v == 0);
        // 2. LEDs, buttons, GPIO, Pmods, CLK OUT
        wr(7'h03, 32'h3); wr(7'h05, 32'h05A | 32'h300); #100;
        check("LEDs from the register", leds == 8'h5A);
        check("RGB from the register (R, G on; B off; active low)", {led_r, led_g, led_b} == 3'b001);
        btn0 = 0; #200; rd(7'h04, v); check("BTN0 pressed reads 1", v[1] == 1 && v[2] == 0); btn0 = 1;
        check("PLL locked", v[0] == 1);
        check("GPIO defaults: dac_mode 1, dac_sleep 0, pdwn 0, dcs 1, eth_rst_n 1", dac_mode == 1 && dac_sleep == 0 && adc_pdwn_a == 0 && adc_pdwn_b == 0 && adc_dcs == 1 && eth_rst_n == 1);
        g = 13'b1_1100_1111_1110; gpio(); #100;
        check("GPIO written: eth_rst_n 0, pdwn 1 1, dcs 0, dfs 0, dac_sleep 1, usb_pullup 1", eth_rst_n == 0 && adc_pdwn_a == 1 && adc_pdwn_b == 1 && adc_dcs == 0 && adc_dfs == 0 && dac_sleep == 1 && usb_pullup == 1);
        g = 13'b0_0101_0011_0101; gpio();
        wr(7'h07, 32'h5_3CA5); #200; rd(7'h07, v);
        check("Pmods as register outputs read back on the pins", pmoda == 8'hA5 && pmodb == 8'h3C && v[15:0] == 16'h3CA5);
        wr(7'h07, 32'h0); #200; check("Pmods released", pmoda === 8'bz);
        wr(7'h08, 32'd11); #100; check("CLK OUT high", clk_out == 1);
        wr(7'h08, 32'd10); #100; check("CLK OUT low", clk_out == 0);
        wr(7'h08, 32'd0); #15; v = clk_out; #20; check("CLK OUT toggles (TCXO)", clk_out != v);
        // 3. the I2C bit-bang against the Si5351 stand-in
        i2c_start(); i2c_write(8'hC0, ack); check("I2C address 0x60 acked", ack);
        i2c_write(8'd3, ack); i2c_write(8'hA5, ack); i2c_write(8'h5A, ack); i2c_stop();
        check("I2C wrote two registers from pointer 3", si.regs[3] == 8'hA5 && si.regs[4] == 8'h5A && si.writes == 2);
        i2c_start(); i2c_write(8'hC0, ack); i2c_write(8'd4, ack); i2c_start(); i2c_write(8'hC1, ack); check("I2C read address acked", ack);
        i2c_read(0, b); check("I2C read register 4", b == 8'h5A);
        i2c_read(1, b); i2c_stop(); check("I2C read register 5 (auto-increment)", b == 8'h00);
        i2c_start(); i2c_write(8'hA0, ack); i2c_stop(); check("I2C: an absent address is NACKed", !ack);
        // 4. MDIO against the PHY stand-in
        mdio_read(5'd1, 5'd2, w16); check("MDIO read PHYID1 = 0x001C", w16 == 16'h001C);
        mdio_read(5'd1, 5'd3, w16); check("MDIO read PHYID2 = 0xC916", w16 == 16'hC916);
        mdio_read(5'd2, 5'd2, w16); check("MDIO read of another address gives all ones", w16 == 16'hFFFF);
        // 5. the frequency counters: wait for two gates
        rd(7'h17, seq0); #2_600_000; rd(7'h17, seq1);
        check("counters advanced (TCXO, ext, si0, si1, rxc, clk_s)", seq1[3:0] != seq0[3:0] && seq1[7:4] != seq0[7:4] && seq1[11:8] != seq0[11:8] && seq1[15:12] != seq0[15:12] && seq1[23:20] != seq0[23:20] && seq1[27:24] != seq0[27:24]);
        check("the absent clock's counter did not advance", seq1[19:16] == seq0[19:16]);
        rd(7'h10, v); check("TCXO counts its own gate: 25000", v == 25000);
        rd(7'h11, v); check("CLK IN 10 MHz -> 10000 +-1", v >= 9999 && v <= 10001);
        rd(7'h12, v); check("Si CLK0 1 MHz -> 1000 +-1", v >= 999 && v <= 1001);
        rd(7'h13, v); check("Si CLK1 100 kHz -> 100 +-1", v >= 99 && v <= 101);
        rd(7'h15, v); check("RXC 125 MHz -> 125000 +-1", v >= 124999 && v <= 125001);
        rd(7'h16, v); check("clk_s 50 MHz -> 50000 +-1", v >= 49999 && v <= 50001);
        // 6. ADC capture at 25 MS/s (div 1), phase 1
        wr(7'h21, 1); wr(7'h20, 32'h0006_0010); wr(7'h22, 0); wr(7'h23, 64); wr(7'h20, 32'h0006_0011);
        #20000; rd(7'h24, v); check("capture done, 64 samples", v[1] == 1 && v[0] == 0 && v[29:16] == 64);
        dump_words(64);
        errs = 0; for (i = 1; i < 64; i = i + 1) if (dump[i][27:16] != ((dump[i-1][27:16] + 1) & 12'hfff)) errs = errs + 1;
        check("channel B ramp: consecutive samples step by 1", errs == 0);
        // channel A: the model's sine, 32 samples a period, 2048 + 1800 sin: find the phase of sample 0 and follow it
        errs = 0; k = -1;
        for (i0 = 0; i0 < 32 && k < 0; i0 = i0 + 1) begin
            v = 2048.0 + 1800.0 * $sin(2.0 * 3.14159265358979 * i0 / 32.0);
            v2 = 2048.0 + 1800.0 * $sin(2.0 * 3.14159265358979 * (i0 + 1) / 32.0);
            if (dump[0][11:0] == v[11:0] && dump[1][11:0] == v2[11:0]) k = i0;
        end
        if (k < 0) errs = 1; else for (i = 0; i < 64; i = i + 1) begin
            v = 2048.0 + 1800.0 * $sin(2.0 * 3.14159265358979 * (k + i) / 32.0);
            if (dump[i][11:0] != v[11:0]) errs = errs + 1;
        end
        check("channel A sine follows the model sample for sample", errs == 0);
        check("no out-of-range flags on A", dump[0][12] == 0 && dump[63][12] == 0);
        // decimation by 4
        wr(7'h22, 3); wr(7'h20, 32'h0006_0011); #40000; dump_words(64);
        errs = 0; for (i = 1; i < 64; i = i + 1) if (dump[i][27:16] != ((dump[i-1][27:16] + 4) & 12'hfff)) errs = errs + 1;
        check("decimation by 4: ramp steps by 4", errs == 0);
        // direct mode: 50 MS/s, the clock is clk_s itself
        wr(7'h22, 0); wr(7'h21, 0); wr(7'h20, 32'h0006_0001); #10000; dump_words(64);
        errs = 0; for (i = 1; i < 64; i = i + 1) if (dump[i][27:16] != ((dump[i-1][27:16] + 1) & 12'hfff)) errs = errs + 1;
        check("direct 50 MS/s: ramp steps by 1", errs == 0);
        wr(7'h21, 1);
        // statistics: window 2^6 = 64 samples (set above); B is a ramp so max - min = 63
        rd(7'h25, seq0); #20000; rd(7'h25, seq1); check("statistics windows advance", seq1 != seq0);
        rd(7'h28, v); rd(7'h25, seq0);
        check("B ramp statistics: max - min = 63 over a 64-sample window", ((v[27:16] - v[11:0]) & 12'hfff) == 63);
        rd(7'h26, v); check("A sine statistics: min ~ 248, max ~ 3848", v[11:0] >= 240 && v[11:0] <= 260 && v[27:16] >= 3836 && v[27:16] <= 3856);
        rd(7'h27, v); check("A sine sum ~ 64 x 2048 = 131072 (+-1800)", v > 131072 - 1800 && v < 131072 + 1800);
        // 7. the DACs: default sine at inc 2^28 (16 samples a period), div 1 (25 MS/s)
        wr(7'h36, 32'h0001_0001); wr(7'h31, 32'h1000_0000); wr(7'h30, 32'h01);
        #5000; mon1.n = 0; #3000;
        // find the LUT index of the first logged sample, then follow in steps of 64
        k = -1;
        for (i0 = 0; i0 < 1024 && k < 0; i0 = i0 + 1)
            if (mon1.log[0] == ((8192 + $signed(lut[i0])) & 14'h3fff) && mon1.log[1] == ((8192 + $signed(lut[(i0 + 64) % 1024])) & 14'h3fff)) k = i0;
        errs = 0;
        if (k < 0) errs = 1; else for (i = 0; i < 60; i = i + 1) if (mon1.log[i] != ((8192 + $signed(lut[(k + 64 * i) % 1024])) & 14'h3fff)) errs = errs + 1;
        check("DAC1 sine: every sample is the table's, 64 entries apart", errs == 0);
        wr(7'h30, 32'h00); wr(7'h32, 32'd1234); #2000; check("DAC1 DC mode: code 1234", dac_p1_d == 1234);
        wr(7'h30, 32'h02); #2000; v = dac_p1_d; #40; check("DAC1 sawtooth steps by 1024 a sample", dac_p1_d == ((v + 1024) & 14'h3fff));
        wr(7'h33, 32'h01); wr(7'h34, 32'h1000_0000); wr(7'h35, 32'd100); #2000; mon2.n = 0; #3000;
        k = -1;
        for (i0 = 0; i0 < 1024 && k < 0; i0 = i0 + 1)
            if (mon2.log[0] == ((8292 + $signed(lut[i0])) & 14'h3fff) && mon2.log[1] == ((8292 + $signed(lut[(i0 + 64) % 1024])) & 14'h3fff)) k = i0;
        check("DAC2 sine with +100 offset follows the table", k >= 0);
        wr(7'h30, 32'h01); wr(7'h32, 32'd0); wr(7'h35, 32'd0);
        check("DAC monitors: CLK = WRT, no setup violations", mon1.viol == 0 && mon2.viol == 0);
        // direct mode (50 MS/s), inverted clock: still no setup violation
        wr(7'h36, 32'h0001_0000); #4000; mon1.viol = 0; mon2.viol = 0; #4000;
        check("DAC direct mode: no setup violations", mon1.viol == 0 && mon2.viol == 0);
        wr(7'h36, 32'h0001_0001);
        // 8. the SDRAM: wait for the initialisation, then 256 words with read latency 4
        rd(7'h42, v); if (!v[0]) begin #300_000; rd(7'h42, v); end
        check("SDRAM initialised (CKE, PRECHARGE, 8 refreshes, LOAD MODE)", v[0] == 1 && sdram.loads == 1 && sdram.refreshes >= 8 && sdram.cl == 2);
        wr(7'h41, 256); wr(7'h40, 32'h0000_0301); #150000; rd(7'h42, v); check("SDRAM test done", v[2] == 1 && v[1] == 0);     // 256 words each way: about 105 us
        rd(7'h43, v); check("SDRAM pattern 0, latency 3: 0 errors", v == 0);
        rd(7'h46, v); check("512 words done (256 written, 256 read)", v == 512);
        wr(7'h40, 32'h0000_0361); #150000; rd(7'h43, v); check("pattern 6: 0 errors", v == 0);
        wr(7'h40, 32'h0000_0201); #150000; rd(7'h43, v); check("latency 2: every word wrong", v == 256);
        wr(7'h40, 32'h0000_0501); #150000; rd(7'h43, v); check("latency 5: every word wrong", v == 256);
        rd(7'h44, v); check("first error at address 0", v == 0);
        check("SDRAM model saw nothing illegal", sdram.bad == 0);
        wr(7'h40, 32'h0000_1301); #150000; rd(7'h43, v); check("inverted SDRAM clock, latency 3: 0 errors (the model has no clock-to-out skew)", v == 0);
        // done
        $display("%0d checks, %0d failures: %s", checks, fails, fails == 0 ? "PASS" : "FAIL");
        $finish;
    end
    initial begin #200_000_000; $display("TIMEOUT"); $finish; end
endmodule
