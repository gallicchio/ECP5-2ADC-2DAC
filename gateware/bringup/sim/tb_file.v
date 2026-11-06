// The PC's side of the UART driven from a file, so host/ecp5bu.py can be run against the RTL (host/test_sim.py):
// `cmd.txt` has one record a line: "S xx" sends a byte (hex), "W n" waits n nanoseconds, "E" ends the run
// (after the board's last reply).  Every byte the board sends is appended to `resp.txt` as a hex line.
// The bench models are the same as tb_top's; clocks on CLK IN (10 MHz) and the Si5351 inputs (1 MHz, 100 kHz,
// nothing), 125 MHz RXC; the gate is 1 ms.
`timescale 1ns/1ps
module tb_file;
    localparam real BIT = 1000.0;
    reg clk_tcxo = 0; always #20 clk_tcxo = ~clk_tcxo;
    reg clk_ext = 0;  always #50 clk_ext = ~clk_ext;
    reg clk_si0 = 0;  always #500 clk_si0 = ~clk_si0;
    reg clk_si1 = 0;  always #5000 clk_si1 = ~clk_si1;
    wire clk_si2 = 1'b0;
    reg eth_rxc = 0;  always #4 eth_rxc = ~eth_rxc;
    reg uart_rx = 1; wire uart_tx;
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
        .btn0(1'b1), .btn1(1'b1),
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

    // the board's replies, byte by byte, into resp.txt
    integer fo;
    initial fo = $fopen("resp.txt", "w");
    reg [7:0] rb; integer i;
    always begin
        @(negedge uart_tx); #(BIT * 1.5);
        for (i = 0; i < 8; i = i + 1) begin rb[i] = uart_tx; #(BIT); end
        $fwrite(fo, "%02x\n", rb);
    end

    // the commands from cmd.txt
    integer fi, r, n, b; reg [8*8:1] kind;
    realtime t_sent = 0;
    task send_byte(input [7:0] bb); integer k; begin
        if ($realtime - t_sent < BIT) #(BIT - ($realtime - t_sent));
        uart_rx = 0; #(BIT);
        for (k = 0; k < 8; k = k + 1) begin uart_rx = bb[k]; #(BIT); end
        uart_rx = 1; t_sent = $realtime;
    end endtask
    initial begin
        #2000;
        fi = $fopen("cmd.txt", "r");
        if (fi == 0) begin $display("no cmd.txt"); $finish; end
        while (!$feof(fi)) begin
            r = $fscanf(fi, "%s", kind);
            if (r == 1) case (kind[8:1])
            "S": begin r = $fscanf(fi, "%h", b); send_byte(b); end
            "W": begin r = $fscanf(fi, "%d", n); #(n); end
            "E": begin #(BIT * 60); $fclose(fo); $display("tb_file: done at %t; dac viol %0d %0d; sdram bad %0d", $time, mon1.viol, mon2.viol, sdram.bad); $finish; end
            endcase
        end
        #(BIT * 60); $fclose(fo); $finish;
    end
    initial begin #2_000_000_000; $display("tb_file: TIMEOUT"); $fclose(fo); $finish; end
endmodule
