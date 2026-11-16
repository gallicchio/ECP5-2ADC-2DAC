// Two small helpers of the bring-up design (2026-11-15), for the two ports that had no test at all:
// the microSD socket (a card in SPI mode, one byte at a time) and the USB USER port (its two lines watched
// and driven as plain pins, with no USB core).
`default_nettype none

// One SPI byte, mode 0, most significant bit first: MOSI changes while SCK is low, both ends sample on SCK's
// rising edge.  `div` is SCK's half period in clk cycles (32 at 25 MHz = 390 kHz, under the 400 kHz an SD card
// is initialised at; use >= 4, so the synchronised MISO is still the same bit when it is sampled).
// A pulse on `start` sends `tx`; `busy` falls when `rx` holds the byte that came back.
module spi_byte (
    input  wire       clk,
    input  wire [7:0] div,
    input  wire       start,
    input  wire [7:0] tx,
    output reg        busy = 0,
    output reg  [7:0] rx = 8'hff,
    output reg        sck = 0,
    output reg        mosi = 1,
    input  wire       miso
);
    reg [1:0] ms = 2'b11;
    always @(posedge clk) ms <= {ms[0], miso};
    reg [7:0] cnt = 0, sh = 0, rsh = 0;
    reg [2:0] bitn = 0;
    wire [7:0] reload = (div == 0) ? 8'd0 : div - 8'd1;
    always @(posedge clk) begin
        if (!busy) begin
            sck <= 1'b0;
            if (start) begin busy <= 1'b1; sh <= tx; mosi <= tx[7]; bitn <= 0; cnt <= reload; end
        end else if (cnt != 0) cnt <= cnt - 1'b1;
        else begin
            cnt <= reload;
            if (!sck) begin                             // the rising edge: both ends sample
                sck <= 1'b1;
                rsh <= {rsh[6:0], ms[1]};
            end else begin                              // the falling edge: the next bit, or the end
                sck <= 1'b0;
                bitn <= bitn + 1'b1;
                if (bitn == 3'd7) begin busy <= 1'b0; rx <= rsh; mosi <= 1'b1; end
                else begin sh <= {sh[6:0], 1'b1}; mosi <= sh[6]; end
            end
        end
    end
endmodule

// The USB USER port's D+ and D- as the FPGA sees them: rising edges counted (activity: a host's packets),
// and the milliseconds spent with both lines low (SE0: a host's bus reset is 10-50 ms of it) or in the idle
// state of a full-speed device (D+ high, D- low).  The edge counts wrap, the times stop at 65535; `clear` zeroes all four.
module usb_mon (
    input  wire        clk,
    input  wire        tick_1ms,
    input  wire        clear,
    input  wire        dp, dn,
    output wire        dp_s, dn_s,
    output reg  [15:0] dp_edges = 0,
    output reg  [15:0] dn_edges = 0,
    output reg  [15:0] se0_ms = 0,
    output reg  [15:0] j_ms = 0
);
    reg [2:0] p = 0, n = 0;
    always @(posedge clk) begin p <= {p[1:0], dp}; n <= {n[1:0], dn}; end
    assign dp_s = p[1]; assign dn_s = n[1];
    always @(posedge clk) begin
        if (clear) begin dp_edges <= 0; dn_edges <= 0; se0_ms <= 0; j_ms <= 0; end
        else begin
            if (p[1] && !p[2]) dp_edges <= dp_edges + 1'b1;
            if (n[1] && !n[2]) dn_edges <= dn_edges + 1'b1;
            if (tick_1ms && !p[1] && !n[1] && !(&se0_ms)) se0_ms <= se0_ms + 1'b1;
            if (tick_1ms &&  p[1] && !n[1] && !(&j_ms))   j_ms   <= j_ms + 1'b1;
        end
    end
endmodule
`default_nettype wire
