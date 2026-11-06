// A frequency counter: how many edges of clk_x fall in one gate period of clk_ref.
// clk_x runs a free counter in its own domain.  Every gate pulse (one a second, from the TCXO) the
// ref domain toggles a request; the clk_x domain sees it, copies its counter into `hold` and toggles
// an acknowledge; the ref domain sees that, and `freq` becomes hold - last hold = cycles per gate.
// A clock that is not there never acknowledges, and its `freq` stays at its last value with `seq`
// not advancing: so the host reads seq too.  Any clk_x frequency works, 1 Hz to the fabric's limit.
`default_nettype none

module clkcount (
    input  wire        clk_ref,
    input  wire        gate,          // one-cycle pulse, exactly once per gate period
    input  wire        clk_x,
    output reg  [31:0] freq = 0,
    output reg  [15:0] seq  = 0       // increments with every new `freq`
);
    reg req = 0;
    always @(posedge clk_ref) if (gate) req <= ~req;

    reg [31:0] cnt = 0, hold = 0;
    reg [1:0]  rs  = 0;
    reg        ack = 0;
    always @(posedge clk_x) begin
        cnt <= cnt + 1'b1;
        rs  <= {rs[0], req};
        if (rs[1] != ack) begin hold <= cnt; ack <= rs[1]; end
    end

    reg [2:0]  as = 0;
    reg [31:0] last = 0;
    always @(posedge clk_ref) begin
        as <= {as[1:0], ack};
        if (as[2] != as[1]) begin freq <= hold - last; last <= hold; seq <= seq + 1'b1; end
    end
endmodule
`default_nettype wire
