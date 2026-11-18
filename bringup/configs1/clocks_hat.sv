// clocks.sv -- a frequency counter and a clock generator: the board's CLK IN and CLK OUT jacks and its Si5351.
//
// A frequency counter counts the rising edges of a signal for exactly one second, here 25,000,000 periods of the
// board's oscillator (a TCXO, good to a few parts per million).  This design counts four signals at once, every
// second: CLK IN (the SMA jack) and the three outputs of the Si5351, a clock-generator chip on the board that makes
// almost any frequency from 2.5 kHz to 200 MHz out of its own 25 MHz crystal.  The laptop programs the Si5351 over
// its I2C bus, through the FPGA, and picks what leaves on CLK OUT; with the SMA cable from CLK OUT to CLK IN, the
// counter checks the whole chain.
//
// Serial port, 1,000,000 baud.  Laptop -> FPGA, each a letter, hex digits, Enter:
//   "w03ff\n"   write 0xff into Si5351 register 0x03 (over I2C, 100 kHz); the FPGA answers "k\n", or "n\n" if the chip
//               did not acknowledge
//   "o2\n"      CLK OUT's source: 0 the TCXO, 1 the TCXO / 2, 2 Si5351 CLK0, 3 CLK1, 4 CLK2, 5 held low
// FPGA -> laptop, once a second: "EEEEEEEE AAAAAAAA BBBBBBBB CCCCCCCC\n", the edges counted in that second on CLK IN,
// CLK0, CLK1 and CLK2, in hex.  The line goes out 10 ms after the second ends: each counter needs a moment (a few of
// its own clock's periods) to hand its count over, and a line sent at once would carry the second before.
//
// Each counter runs on its own signal as its clock (clkcount, from the board's bring-up design): that is the only
// way to count edges faster than the TCXO, and it means five clocks in one design.  (Rev A's lesson: a design that
// puts more than eight clocks on the FPGA's global clock network built cleanly and did not run.  Five is fine.)
//
// LEDs: LED0 toggles every second; LED1 an I2C write is under way; LED2 the last write was not acknowledged.

module clocks (
    input  logic       clk_tcxo,                // 25 MHz
    input  logic       clk_ext,                 // CLK IN, through its comparator
    input  logic       clk_si0, clk_si1, clk_si2,
    input  logic       eth_rxc,                 // SCRATCH: the PHY's receive clock, the switch's 125 MHz
    output logic       eth_rst_n,
    output logic       clk_out,
    inout  wire        i2c_scl, i2c_sda,        // the Si5351's I2C bus (pulled up on the board)
    input  logic       uart_rx,
    output logic       uart_tx,
    output logic [7:0] led
);
    wire clk = clk_tcxo;
    assign eth_rst_n = 1;

    // ---- the gate: one pulse every 25,000,000 clocks = one second of the TCXO ----------------------------------
    logic [24:0] g = 0;
    logic        gate = 0, sec = 0;
    always_ff @(posedge clk) begin
        gate <= g == 25_000_000 - 1;
        g    <= g == 25_000_000 - 1 ? 25'd0 : g + 1;
        if (gate) sec <= ~sec;
    end

    // ---- the counters ---------------------------------------------------------------------------------------------
    logic [31:0] f_ext, f_s0, f_s1, f_s2;
    logic [15:0] q_ext, q_s0, q_s1, q_s2;
    clkcount c_ext (.clk_ref(clk), .gate(gate), .clk_x(clk_ext), .freq(f_ext), .seq(q_ext));
    clkcount c_s0  (.clk_ref(clk), .gate(gate), .clk_x(clk_si0), .freq(f_s0),  .seq(q_s0));
    clkcount c_s1  (.clk_ref(clk), .gate(gate), .clk_x(clk_si1), .freq(f_s1),  .seq(q_s1));
    clkcount c_s2  (.clk_ref(clk), .gate(gate), .clk_x(eth_rxc), .freq(f_s2),  .seq(q_s2));   // SCRATCH: eth_rxc

    // ---- CLK OUT -----------------------------------------------------------------------------------------------
    logic [2:0] osel = 0;
    logic       half = 0;
    always_ff @(posedge clk) half <= ~half;
    always_comb
        case (osel)
            3'd0: clk_out = clk_tcxo;
            3'd1: clk_out = half;
            3'd2: clk_out = clk_si0;
            3'd3: clk_out = clk_si1;
            3'd4: clk_out = clk_si2;
            default: clk_out = 0;
        endcase

    // ---- the commands ----------------------------------------------------------------------------------------------
    logic [7:0] rx_data;  logic rx_valid;
    uart_rx #(.CLKS_PER_BIT(25)) rx (.clk(clk), .rx(uart_rx), .data(rx_data), .valid(rx_valid));
    logic [7:0]  cmd = 0;
    logic [15:0] arg = 0;
    logic        i2c_go = 0;
    wire  [4:0]  hexval = rx_data <= "9" ? rx_data - "0" : rx_data - "a" + 10;
    wire         is_hex = (rx_data >= "0" && rx_data <= "9") || (rx_data >= "a" && rx_data <= "f");
    always_ff @(posedge clk) begin
        i2c_go <= 0;
        if (rx_valid) begin
            if (cmd == 0 && (rx_data == "w" || rx_data == "o")) begin cmd <= rx_data; arg <= 0; end
            else if (is_hex && cmd != 0) arg <= {arg[11:0], hexval[3:0]};
            else if (rx_data == "\n") begin
                if (cmd == "w") i2c_go <= 1;
                if (cmd == "o") osel <= arg[2:0];
                cmd <= 0;
            end
        end
    end

    // ---- the I2C master: START, 0xC0 (the Si5351's address 0x60, write), the register, the value, STOP ------------
    // Each bit is four quarters of 2.5 us (100 kHz): SCL low while SDA changes, SCL high twice (the slave reads SDA, or
    // drives it low for an acknowledge, which we read), SCL low.  SCL and SDA are open drain: we only pull them low.
    logic [5:0]  qt = 0;                        // 62 clocks a quarter: 2.48 us
    wire         qtick = qt == 61;
    always_ff @(posedge clk) qt <= qtick ? 6'd0 : qt + 1;
    typedef enum logic [1:0] {I_IDLE, I_START, I_BITS, I_STOP} istate_t;
    istate_t     ist = I_IDLE;
    logic [1:0]  qn = 0;                        // which quarter of the bit
    logic [4:0]  bi = 0;                        // which of the 27 bits (3 bytes, each 8 bits and an acknowledge)
    logic [26:0] sh = 0;
    logic        scl = 1, sda = 1, nack = 0, done = 0;
    assign i2c_scl = scl ? 1'bz : 1'b0;
    assign i2c_sda = sda ? 1'bz : 1'b0;
    always_ff @(posedge clk) begin
        done <= 0;
        if (ist == I_IDLE) begin
            if (i2c_go) begin
                // ######################################################################
                // ##  KEY LINE: the three bytes, each followed by a 1: the acknowledge
                // ##  slot, where we let SDA go and the Si5351 pulls it low
                // ######################################################################
                sh  <= {8'hC0, 1'b1, arg[15:8], 1'b1, arg[7:0], 1'b1};
                ist <= I_START; qn <= 0; bi <= 0; nack <= 0;
            end
        end else if (qtick) begin
            qn <= qn + 1;
            case (ist)
                I_START: case (qn)
                    0: begin scl <= 1; sda <= 1; end
                    1: sda <= 0;                // SDA falls while SCL is high: START
                    2: scl <= 0;
                    3: ist <= I_BITS;
                endcase
                I_BITS: case (qn)
                    0: sda <= sh[26];
                    1: scl <= 1;
                    2: if (bi == 8 || bi == 17 || bi == 26) nack <= nack | i2c_sda;   // high = nobody acknowledged
                    3: begin
                        scl <= 0; sh <= {sh[25:0], 1'b1};
                        if (bi == 26) ist <= I_STOP; else bi <= bi + 1;
                    end
                endcase
                I_STOP: case (qn)
                    0: sda <= 0;
                    1: scl <= 1;
                    2: sda <= 1;                // SDA rises while SCL is high: STOP
                    3: begin ist <= I_IDLE; done <= 1; end
                endcase
                default: ist <= I_IDLE;
            endcase
        end
    end

    // ---- what the FPGA says: "k" or "n" after a write, and the four counts every second --------------------------
    logic [7:0] tx_data = 0;  logic tx_start = 0;  logic tx_busy;
    uart_tx #(.CLKS_PER_BIT(25)) tx (.clk(clk), .data(tx_data), .start(tx_start), .busy(tx_busy), .tx(uart_tx));
    logic [7:0] line [0:35];                    // the next line to send
    logic [5:0] len = 0, ci = 0;
    logic       sending = 0, ack_pending = 0, nack_r = 0, report_pending = 0;
    logic       rwait = 0;
    logic [17:0] rdly = 0;
    function automatic [7:0] hexchar(input [3:0] v);
        hexchar = v < 10 ? "0" + v : "a" + v - 10;
    endfunction
    logic [127:0] counts;
    assign counts = {f_ext, f_s0, f_s1, f_s2};
    always_ff @(posedge clk) begin
        tx_start <= 0;
        if (done) begin ack_pending <= 1; nack_r <= nack; end
        // ######################################################################
        // ##  KEY LINES: report 10 ms (250,000 clocks) after the gate, when every
        // ##  counter has handed over the second that just ended
        // ######################################################################
        if (gate) begin rwait <= 1; rdly <= 0; end
        else if (rwait) begin
            rdly <= rdly + 1;
            if (rdly == 249_999) begin rwait <= 0; report_pending <= 1; end
        end
        if (!sending) begin
            if (ack_pending) begin
                line[0] <= nack_r ? "n" : "k";  line[1] <= "\n";  len <= 2;  ci <= 0;  sending <= 1;  ack_pending <= 0;
            end else if (report_pending) begin
                for (int k = 0; k < 4; k++) begin
                    for (int j = 0; j < 8; j++)
                        line[9 * k + j] <= hexchar(counts[127 - 32 * k - 4 * j -: 4]);
                    line[9 * k + 8] <= k == 3 ? "\n" : " ";
                end
                len <= 36;  ci <= 0;  sending <= 1;  report_pending <= 0;
            end
        end else if (!tx_busy && !tx_start) begin
            tx_data  <= line[ci];
            tx_start <= 1;
            if (ci == len - 1) sending <= 0; else ci <= ci + 1;
        end
    end

    assign led = {5'b0, nack_r, ist != I_IDLE, sec};
endmodule


// ---- clkcount: how many edges of clk_x fall in one gate period of clk_ref (from the board's bring-up design) -----
// clk_x runs a free counter in its own domain.  Every gate pulse the ref domain toggles a request; the clk_x domain
// sees it, copies its counter into `hold` and toggles an acknowledge; the ref domain sees that, and `freq` becomes
// hold - the last hold = edges per gate.  A clock that is not there never acknowledges: then, at the next gate,
// `freq` reads 0 (rather than keeping the last count, which looked like a measurement) and `seq` does not advance.
module clkcount (
    input  logic        clk_ref,
    input  logic        gate,
    input  logic        clk_x,
    output logic [31:0] freq = 0,
    output logic [15:0] seq  = 0
);
    logic req = 0;
    always_ff @(posedge clk_ref) if (gate) req <= ~req;
    logic [31:0] cnt = 0, hold = 0;
    logic [1:0]  rs = 0;
    logic        ack = 0;
    always_ff @(posedge clk_x) begin
        cnt <= cnt + 1;
        rs  <= {rs[0], req};
        if (rs[1] != ack) begin hold <= cnt; ack <= rs[1]; end
    end
    logic [2:0]  as = 0;
    logic [31:0] last = 0;
    logic        acked = 0;                         // an acknowledge came since the last gate
    always_ff @(posedge clk_ref) begin
        as <= {as[1:0], ack};
        if (as[2] != as[1]) begin freq <= hold - last; last <= hold; seq <= seq + 1; acked <= 1; end
        else if (gate) begin
            if (!acked) freq <= 0;                  // a whole second and no answer: no clock
            acked <= 0;
        end
    end
endmodule
