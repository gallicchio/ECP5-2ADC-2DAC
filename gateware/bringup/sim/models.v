// Bench models for the testbench: the two converters as the FPGA sees them, an I2C slave standing in
// for the Si5351 (address 0x60, a register file with an auto-incrementing pointer), an MDIO slave
// standing in for the RTL8211F (address 1; registers 2 and 3 hold its ID 0x001C / 0xC916).
`timescale 1ns/1ps

// AD9238 port: a 12-bit sample tPD after each clock's rising edge; sine on A, a ramp on B.
module adc_model #(parameter real TPD = 3.5) (
    input clk, output reg [11:0] d, output reg otr, input [1:0] which    // 0 = sine, 1 = ramp, 2 = constant 0x800
);
    integer k = 0;
    real s;
    initial begin d = 0; otr = 0; end
    always @(posedge clk) begin
        #(TPD);
        k = k + 1;
        case (which)
        0: begin s = 2048.0 + 1800.0 * $sin(2.0 * 3.14159265358979 * k / 32.0); d = s; otr = 0; end
        1: begin d = k; otr = (k % 1000) == 0; end
        default: begin d = 12'h800; otr = 0; end
        endcase
    end
endmodule

// AD9767 port monitor: records the data at each WRT rising edge; checks the setup/hold the datasheet asks.
module dac_monitor #(parameter DEPTH = 4096) (input wrt, input clk, input [13:0] d);
    reg [13:0] log [0:DEPTH-1];
    integer n = 0, viol = 0;
    realtime t_change = 0;
    initial #1000 viol = 0;              // the first microsecond is initialisation
    always @(d) t_change = $realtime;
    always @(posedge wrt) begin
        if ($realtime - t_change < 2.0) begin viol = viol + 1; $display("DAC: data changed %0.2f ns before WRT at %t (setup 2.0 wanted)", $realtime - t_change, $time); end
        if (n < DEPTH) log[n] = d;
        n = n + 1;
    end
    always @(posedge clk) if (clk !== wrt) begin $display("DAC: CLK and WRT differ at %t", $time); viol = viol + 1; end
endmodule

// A plain I2C slave: 7-bit address, write = pointer then data (auto-increment), read from the pointer.
// Everything happens on SCL edges: bits are sampled on the rising edge, SDA is driven after the falling edge.
module i2c_slave_model #(parameter [6:0] ADDR = 7'h60) (inout scl, inout sda);
    reg [7:0] regs [0:255];
    reg [7:0] ptr = 0;
    reg sda_o = 1;                       // 1 = released
    assign sda = sda_o ? 1'bz : 1'b0;
    wire sdai = (sda === 1'b0) ? 1'b0 : 1'b1;
    wire scli = (scl === 1'b0) ? 1'b0 : 1'b1;
    integer i, nacks = 0, writes = 0, reads = 0, starts = 0, stops = 0;
    initial for (i = 0; i < 256; i = i + 1) regs[i] = 0;
    localparam IDLE = 0, ADDRESS = 1, WDATA = 2, RDATA = 3;
    integer state = IDLE, nbit = 0;      // nbit: rising edges seen in this byte (0..8; 8 = the ack clock)
    reg [7:0] sh = 0; reg first = 1, rw = 0;
    always @(negedge sdai) if (scli) begin state = ADDRESS; nbit = 0; sh = 0; starts = starts + 1; sda_o = 1; end
    always @(posedge sdai) if (scli && sda_o) begin if (state != IDLE) stops = stops + 1; state = IDLE; end
    always @(posedge scli) if (state != IDLE) begin
        if (nbit < 8) begin
            if (state != RDATA) sh = {sh[6:0], sdai};
            nbit = nbit + 1;
        end else begin                                     // the 9th clock
            if (state == RDATA && sdai) state = IDLE;      // the master's NACK ends a read
            nbit = 9;
        end
    end
    always @(negedge scli) if (state != IDLE) begin
        if (nbit == 8) begin                               // drive the ACK slot
            case (state)
            ADDRESS: if (sh[7:1] == ADDR) begin rw = sh[0]; sda_o = 0; first = 1; if (rw) reads = reads + 1; end
                     else begin nacks = nacks + 1; state = IDLE; end
            WDATA:   begin if (first) begin ptr = sh; first = 0; end else begin regs[ptr] = sh; ptr = ptr + 1; writes = writes + 1; end sda_o = 0; end
            RDATA:   sda_o = 1;                            // the master acks
            endcase
        end else if (nbit == 9) begin                      // after the ack clock: the next byte
            nbit = 0;
            if (state == ADDRESS) state = rw ? RDATA : WDATA;
            if (state == RDATA) begin sh = regs[ptr]; ptr = ptr + 1; sda_o = sh[7]; sh = {sh[6:0], 1'b1}; end
            else sda_o = 1;
        end else if (state == RDATA) begin                 // the next data bit
            sda_o = sh[7]; sh = {sh[6:0], 1'b1};
        end
    end
endmodule

// MDIO slave (clause 22).  Samples MDIO on MDC's rising edge; on a read, drives it after the
// rising edges of the turnaround's second bit and the 16 data bits.
module mdio_slave_model #(parameter [4:0] PHYAD = 5'd1) (input mdc, inout mdio);
    reg [15:0] regs [0:31];
    reg mdio_o = 1; reg drive = 0;
    assign mdio = drive ? mdio_o : 1'bz;
    wire mi = (mdio === 1'bz || mdio === 1'b1) ? 1'b1 : 1'b0;
    integer ones = 0, bitn = 0, reads = 0, writes = 0;
    reg [1:0] st, op; reg [4:0] phy, regad; reg [15:0] data; reg in_frame = 0;
    integer i; initial begin for (i = 0; i < 32; i = i + 1) regs[i] = 16'h0000; regs[2] = 16'h001C; regs[3] = 16'hC916; regs[1] = 16'h7949; end
    always @(posedge mdc) begin
        if (!in_frame) begin
            if (mi) ones = ones + 1;
            else if (ones >= 32) begin in_frame = 1; bitn = 1; st[1] = 0; end     // the ST field's first bit (0)
            else ones = 0;
        end else begin
            bitn = bitn + 1;
            case (bitn)
            2: st[0] = mi;
            3: op[1] = mi;  4: op[0] = mi;
            5,6,7,8,9: phy = {phy[3:0], mi};
            10,11,12,13,14: regad = {regad[3:0], mi};
            15: if (op == 2'b10 && phy == PHYAD) begin #10 drive = 1; mdio_o = 0; data = regs[regad]; end   // TA: the PHY drives 0 for the second bit time
            16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31: begin
                if (op == 2'b10 && phy == PHYAD) begin #10 mdio_o = data[15]; data = {data[14:0], 1'b0}; end     // data[15] after edge 16 ... data[0] after edge 31
                else if (bitn >= 17) data = {data[14:0], mi};                                                      // a write's data bits are sampled at edges 17..32
            end
            32: begin
                if (op == 2'b01 && phy == PHYAD) begin regs[regad] = {data[14:0], mi}; writes = writes + 1; end
                if (op == 2'b10 && phy == PHYAD) reads = reads + 1;
                #10 drive = 0; in_frame = 0; ones = 0;
            end
            endcase
        end
    end
endmodule
