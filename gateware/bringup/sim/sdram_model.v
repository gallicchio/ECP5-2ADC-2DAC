// A behavioural W9825G6KH (SDR SDRAM, 4 x 8192 x 512 x 16) for the tester's simulation: ACTIVE, READ and
// WRITE with auto-precharge, burst length 1, the mode register's CAS latency, AUTO REFRESH counted,
// LOAD MODE checked.  It stores only the words written (an associative array), and complains about a
// read of a column never written, a command to a bank that is not active, or a CAS latency it has not
// been given.  Timing: data appear tAC = 5.4 ns after the clock edge CL cycles after READ, and hold
// tOH = 2.5 ns past the next edge.  Not modelled: tRCD, tRP, tRC, refresh intervals (the tester's
// timings are read against the datasheet by hand; see sdram_test.v).
`timescale 1ns/1ps
module sdram_model (
    input clk, input cke, input cs_n, input ras_n, input cas_n, input we_n,
    input [1:0] ba, input [12:0] a, input dqml, input dqmh, inout [15:0] dq
);
    reg [15:0] mem [0:(1<<24)-1];       // iverilog allocates lazily enough for a few thousand words
    reg        written [0:(1<<24)-1];
    reg [12:0] row [0:3];
    reg        active [0:3];
    integer    cl = 0, refreshes = 0, loads = 0, reads = 0, writes = 0, bad = 0;
    reg [15:0] dq_r = 16'hzzzz;
    reg        dq_drive = 0;
    assign dq = dq_drive ? dq_r : 16'hzzzz;
    wire [3:0] cmd = {cs_n, ras_n, cas_n, we_n};
    integer i;
    initial for (i = 0; i < 4; i = i + 1) active[i] = 0;

    // The read pipeline: rq[j]/rv[j] is data due to be driven after the j-th edge from now.  At each edge the
    // head is taken first (blocking), then the queue shifts and a READ enqueues at index CL-2: after the shift
    // at the next edge it is the head, driven tAC after the edge CL-1 edges on and valid at the CL-th, as the datasheet draws it.
    reg [15:0] rq [0:7]; reg rv [0:7]; integer k;
    reg [15:0] head_d; reg head_v;
    initial for (k = 0; k < 8; k = k + 1) rv[k] = 0;
    always @(posedge clk) begin
        head_v = rv[0]; head_d = rq[0];
        for (k = 0; k < 7; k = k + 1) begin rq[k] <= rq[k+1]; rv[k] <= rv[k+1]; end
        rv[7] <= 0;
        if (cke) case (cmd)
        4'b0000: begin                                      // LOAD MODE
            loads = loads + 1;
            cl = a[6:4];
            if (a[2:0] != 0 || a[3] != 0 || a[9] != 0) begin $display("SDRAM: mode register %h: burst/type not what the tester expects", a); bad = bad + 1; end
            $display("SDRAM: LOAD MODE CL=%0d BL=%0d at %t", cl, 1 << a[2:0], $time);
        end
        4'b0001: refreshes = refreshes + 1;                 // AUTO REFRESH
        4'b0010: begin                                      // PRECHARGE
            if (a[10]) for (i = 0; i < 4; i = i + 1) active[i] = 0; else active[ba] = 0;
        end
        4'b0011: begin row[ba] = a; active[ba] = 1; end    // ACTIVE
        4'b0100: begin                                      // WRITE (data on this edge)
            writes = writes + 1;
            if (!active[ba]) begin $display("SDRAM: WRITE to inactive bank %0d at %t", ba, $time); bad = bad + 1; end
            mem[{ba, row[ba], a[8:0]}] = dq; written[{ba, row[ba], a[8:0]}] = 1;
            if (a[10]) active[ba] = 0;
        end
        4'b0101: begin                                      // READ
            reads = reads + 1;
            if (cl != 2 && cl != 3) begin $display("SDRAM: READ with CL=%0d at %t", cl, $time); bad = bad + 1; end
            if (!active[ba]) begin $display("SDRAM: READ from inactive bank %0d at %t", ba, $time); bad = bad + 1; end
            if (!written[{ba, row[ba], a[8:0]}]) begin $display("SDRAM: READ of unwritten word %h at %t", {ba, row[ba], a[8:0]}, $time); bad = bad + 1; end
            rq[cl - 2] <= mem[{ba, row[ba], a[8:0]}]; rv[cl - 2] <= 1;      // head after CL-1 edges: driven tAC after edge CL-1, valid at edge CL
            if (a[10]) active[ba] = 0;
        end
        default: ;
        endcase
        // drive the word due at this edge tAC later; release tOH after an edge with nothing due
        if (head_v) begin #5.4 dq_r = head_d; dq_drive = 1; end
        else begin #2.5 dq_drive = 0; end
    end
endmodule
