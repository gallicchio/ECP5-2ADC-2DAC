// blink.v: the chaser steps, the buttons, the RGB cycle, CLK OUT, and the serial greeting (115200 baud).
`timescale 1ns/1ps
module tb_blink;
    reg clk = 0; always #20 clk = ~clk;
    reg btn0 = 1, btn1 = 1;
    wire clk_out, uart_tx; wire [7:0] leds; wire r, g, b;
    wire pa, pb, dcs, dfs, dm, ds, ern, up;
    blink dut (.clk_tcxo(clk), .clk_out(clk_out), .btn0(btn0), .btn1(btn1),
               .led0(leds[0]), .led1(leds[1]), .led2(leds[2]), .led3(leds[3]), .led4(leds[4]), .led5(leds[5]), .led6(leds[6]), .led7(leds[7]),
               .led_r(r), .led_g(g), .led_b(b), .uart_tx(uart_tx),
               .adc_pdwn_a(pa), .adc_pdwn_b(pb), .adc_dcs(dcs), .adc_dfs(dfs), .dac_mode(dm), .dac_sleep(ds), .eth_rst_n(ern), .usb_pullup(up));
    // the serial greeting
    reg [7:0] rx; integer i; reg [8*40:1] line = ""; integer nl = 0, fails = 0;
    localparam real BIT = 1e9 / 115200.0;
    always begin
        @(negedge uart_tx); #(BIT * 1.5);
        for (i = 0; i < 8; i = i + 1) begin rx[i] = uart_tx; #(BIT); end
        if (rx == 8'h0a) begin nl = nl + 1; $display("serial: %0s", line); line = ""; end
        else if (rx != 8'h0d) line = {line[8*39:1], rx};
    end
    initial begin
        // the chaser: force the counter instead of waiting 0.67 s of simulated time a step
        dut.c = 28'h080_0000; #1000;
        if (leds != 8'b0000_0001) begin fails = fails + 1; $display("FAIL: leds %b at step 0", leds); end
        dut.c = 28'h180_0000; #1000;
        if (leds != 8'b0000_0010) begin fails = fails + 1; $display("FAIL: leds %b at step 1", leds); end
        btn1 = 0; #100; if (leds != 8'hff) begin fails = fails + 1; $display("FAIL: BTN1 should light all"); end btn1 = 1;
        btn0 = 0; #100; if (leds != 8'b0100_0000) begin fails = fails + 1; $display("FAIL: BTN0 reverses (step 1 -> 6): %b", leds); end btn0 = 1;
        if ({r, g, b} != 3'b101) begin fails = fails + 1; $display("FAIL: RGB %b (c[25:24] = 1: green)", {r, g, b}); end
        if (!(pa && pb && !dcs && dm && ds && ern && !up)) begin fails = fails + 1; $display("FAIL: static pins"); end
        // the greeting: force the second counter to its end
        dut.sec = 25'd24_999_990; #(BIT * 12 * 26);
        if (nl != 1 || line != "" ) begin end
        $display("%0d greeting line(s); %0d failures: %s", nl, fails, fails == 0 && nl == 1 ? "PASS" : "FAIL");
        $finish;
    end
    initial begin #50_000_000; $display("TIMEOUT"); $finish; end
endmodule
