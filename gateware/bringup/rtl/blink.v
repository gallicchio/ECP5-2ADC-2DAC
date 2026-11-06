// The first bitstream to load: no PLL, no bus, nothing that can fail but the TCXO and the LEDs.
// LED0-7 chase once round every 5 s (TCXO/2^27 per step); BTN1 lights all eight; BTN0 reverses
// the chase; the RGB LED cycles red, green, blue; CLK OUT carries the 25 MHz TCXO through its buffer;
// the serial channel prints "ECP5-2ADC-2DAC blink <n>" once a second at 115200 baud.  The converters'
// static pins are driven to their quiet states (ADC powered down, DAC asleep) and the PHY held out of reset.
`default_nettype none
module blink (
    input  wire clk_tcxo,
    output wire clk_out,
    input  wire btn0, btn1,
    output wire led0, led1, led2, led3, led4, led5, led6, led7,
    output wire led_r, led_g, led_b,
    output wire uart_tx,
    output wire adc_pdwn_a, adc_pdwn_b, adc_dcs, adc_dfs, dac_mode, dac_sleep, eth_rst_n, usb_pullup
);
    reg [27:0] c = 0;
    always @(posedge clk_tcxo) c <= c + 1'b1;
    wire [2:0] step = btn0 ? c[26:24] : ~c[26:24];          // buttons are active low: pressed reverses
    wire [7:0] chaser = 8'b1 << step;
    assign {led7, led6, led5, led4, led3, led2, led1, led0} = btn1 ? chaser : 8'hff;
    assign {led_r, led_g, led_b} = c[25:24] == 2'd0 ? 3'b011 : c[25:24] == 2'd1 ? 3'b101 : c[25:24] == 2'd2 ? 3'b110 : 3'b111;
    assign clk_out = clk_tcxo;
    assign adc_pdwn_a = 1'b1; assign adc_pdwn_b = 1'b1; assign adc_dcs = 1'b0; assign adc_dfs = 1'b0;
    assign dac_mode = 1'b1; assign dac_sleep = 1'b1; assign eth_rst_n = 1'b1; assign usb_pullup = 1'b0;

    // "ECP5-2ADC-2DAC blink <n>\r\n" once a second
    localparam N = 24;
    reg [7:0] msg [0:N-1];
    initial begin
        msg[0]="E"; msg[1]="C"; msg[2]="P"; msg[3]="5"; msg[4]="-"; msg[5]="2"; msg[6]="A"; msg[7]="D"; msg[8]="C"; msg[9]="-";
        msg[10]="2"; msg[11]="D"; msg[12]="A"; msg[13]="C"; msg[14]=" "; msg[15]="b"; msg[16]="l"; msg[17]="i"; msg[18]="n"; msg[19]="k";
        msg[20]=" "; msg[21]="0"; msg[22]=8'h0d; msg[23]=8'h0a;      // (Verilog has no "\r" escape)
    end
    reg [24:0] sec = 0; reg tick = 0; reg [3:0] n = 0;
    always @(posedge clk_tcxo) begin
        tick <= 1'b0;
        if (sec == 25'd24_999_999) begin sec <= 0; tick <= 1'b1; n <= n == 9 ? 4'd0 : n + 1'b1; end
        else sec <= sec + 1'b1;
    end
    reg [4:0] idx = N; reg start = 0; wire busy;
    reg [7:0] byte_;
    always @(posedge clk_tcxo) begin
        start <= 1'b0;
        if (tick) idx <= 0;
        else if (idx < N && !busy && !start) begin
            byte_ <= idx == 21 ? 8'h30 + n : msg[idx]; start <= 1'b1; idx <= idx + 1'b1;
        end
    end
    uart_tx #(.DIV(217)) utx (.clk(clk_tcxo), .data(byte_), .start(start), .busy(busy), .tx(uart_tx));   // 25 MHz / 115200 = 217
endmodule
`default_nettype wire
