// Clock-domain crossings, the plain kind.
`default_nettype none

// A single-cycle pulse from clock domain a to clock domain b (toggle, synchronise, edge-detect).
module sync_pulse (
    input  wire clk_a, input wire pulse_a,
    input  wire clk_b, output wire pulse_b
);
    reg t_a = 0;
    always @(posedge clk_a) if (pulse_a) t_a <= ~t_a;
    reg [2:0] s_b = 0;
    always @(posedge clk_b) s_b <= {s_b[1:0], t_a};
    assign pulse_b = s_b[2] ^ s_b[1];
endmodule

// A level (a quasi-static control bit) into clock domain b.
module sync_bit (input wire clk_b, input wire d, output wire q);
    reg [1:0] s = 0;
    always @(posedge clk_b) s <= {s[0], d};
    assign q = s[1];
endmodule
`default_nettype wire
