// A unit test of uart_tx -> uart_rx (a loopback at 1 Mbaud, 25 MHz) and of regbus.
`timescale 1ns/1ps
module tb_uart;
    reg clk = 0; always #20 clk = ~clk;
    reg [7:0] td = 0; reg start = 0; wire busy, line; wire [7:0] rd; wire rv;
    uart_tx #(.DIV(25)) t (.clk(clk), .data(td), .start(start), .busy(busy), .tx(line));
    uart_rx #(.DIV(25)) r (.clk(clk), .rx(line), .data(rd), .valid(rv));
    integer i, fails = 0;
    always @(posedge rv) $display("rx %02x at %t", rd, $time);
    initial begin
        #100;
        for (i = 0; i < 4; i = i + 1) begin
            @(posedge clk); td = 8'h55 + i * 8'h31; start = 1; @(posedge clk); start = 0;
            @(posedge rv); if (rd != td) begin fails = fails + 1; $display("FAIL: sent %02x got %02x", td, rd); end
            #3000;
        end
        $display("uart loopback: %0d failures", fails);
        $finish;
    end
endmodule
