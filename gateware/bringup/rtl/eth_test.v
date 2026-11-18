// The RGMII tester: proves the RTL8211F's data path in both directions at gigabit speed, with no network
// stack.  The PC writes one whole Ethernet frame (destination MAC through FCS, the FCS computed by the PC)
// into a buffer; the engine sends it tx_count times, each with a preamble and SFD in front; the receiver
// counts what comes back, checks every frame's CRC-32 and keeps a copy of the first frame after a clear.
// With the PHY in PCS loopback (BMCR bit 14) the frames come straight back, so no cable is needed; with a
// link, the same counters show the traffic of the network.
//
// Three clock domains:
//   clk      25 MHz  the register bus: every port except the RGMII pins and clk125
//   clk125   125 MHz the transmitter (a PLL output; TXC is this clock, forwarded)
//   eth_rxc  125 MHz the receiver (the PHY's clock; it stops while the PHY is in reset)
// and what crosses between them:
//   tx_start, "all sent"     pulses, as a toggle through sync_pulse
//   tx_len, tx_count, tx_gap quasi-static; the engine copies them four clk125 cycles after the start's toggle
//   the counters, rx_len     by request and acknowledge, as rtl/clkcount.v does: the bus side toggles a request
//                            every 256 cycles (10 us), the other side copies its counters into holding registers
//                            and toggles the acknowledge, the bus side copies the holding registers when it has
//                            seen the acknowledge.  A new request waits for the last one's acknowledge, so the
//                            holding registers never move while they are being read: no torn values.
//   rx_clear                 rides on the same request (a flag that says "and clear"); the bus-side copies go to
//                            zero at once and stay there until the receiver has acknowledged the clear.
// If eth_rxc is not running the request is never acknowledged: the receive outputs keep their last values
// (zero after an rx_clear), and the clear is done when the clock comes back.  Nothing on the bus side waits.
//
// Speed.  Both 125 MHz domains are written to have margin on the -6 part in a full design, where the placer
// spreads things: no counter is compared with anything (the engine counts down through zero and the sign bit
// is the "last byte" flag), every strobe that enables a group of registers is itself a register, the
// received byte is registered twice before anything looks at it and brings its share of the CRC with it,
// the verdict on a frame is reached in two steps after its end.  The transmit buffer is a
// DP16KD instantiated by hand, for one reason: its output register (REGMODE_B = OUTREG).  The block RAM
// yosys infers has none, its clock-to-out is 5.8 ns, the nearest block RAM row is 20 rows from the RGMII pins
// and the placer would not keep the next register beside the RAM: 124-138 MHz, seed by seed.  With the
// register inside the RAM the output is there 1.0 ns after the clock.  TX_RAM_OUTREG = 0 gives the inferred
// memory back (the same two cycles from address to data).
//
// Transmit: an RGMII byte is the low nibble on TXC's rising edge and the high nibble on its falling edge;
// TX_CTL is TX_EN on both (TX_ER is never sent).  TXC and the data leave through ODDRX1Fs on the same
// clock, so they are edge-aligned at the pins: the PHY (strap TXDLY = 1) delays TXC by 2 ns itself.
// Per frame: 7 bytes 0x55, 0xD5, tx_len bytes of the buffer, then tx_gap idle byte times (at least 1; a
// tx_len of 0 sends one byte).  The engine's state runs four cycles ahead of the pins: the buffer's address
// and output registers, one more register (so the RAM and the pins need not be neighbours), the byte.
//
// Receive: an IDDRX1F on each pin gives the rising-edge nibble on Q0 and the following falling-edge nibble
// on Q1; RX_CTL is RX_DV on the rising edge and RX_DV xor RX_ER on the falling one.  The PHY (strap
// RXDLY = 1) sends RXC 2 ns after the data edges, centred in the data at the pins.  Inside the FPGA the
// clock then goes round the clock tree while the data go straight to the I/O register: the ECP5 data sheet
// (table 3.22, -6) asks for 3.3 ns of hold on a plain input register, and the PHY guarantees 1.2 (2.0 typical).
// So each input passes a DELAYG in the mode Lattice gives for exactly this case, "clock and data centred at
// the pin" (SCLK_CENTERED: 0.52 ns setup and hold at the pins).  RX_DELAY = "NONE" takes the delay out,
// "USER_DEFINED" with RX_DELAY_TAPS (25 ps each, 0..127) sets any other.
// A burst is everything from RX_DV rising to RX_DV falling.  The bytes after the first 0xD5 go through the
// CRC-32 (reflected, 0xEDB88320 = polynomial 0x04C11DB7 bit-reversed, start all ones, a byte a cycle); after
// a good frame's own FCS the register holds 0xDEBB20E3 whatever the frame was (the standard's 0xC704DD7B
// read in the other bit order).  When RX_DV falls: rx_frames + 1, and rx_good + 1 if an SFD was seen, the
// register holds that residue and RX_ER never rose during the burst; rx_bad + 1 otherwise.  So
// rx_frames = rx_good + rx_bad, always.
// The capture: the first burst that starts after a clear (or after power-up) is copied to a second block
// RAM, good or bad, and rx_captured rises when it ends.  A burst with an SFD is stored from the byte after
// the SFD through the FCS, and rx_len counts those bytes; a burst in which no 0xD5 ever came (the nibbles
// swapped, the clock on the wrong edge: what a first board may well show) is stored whole from its first
// byte, preamble and all, so that the PC can see what the pins carried.  rx_len saturates at 2047.
//
// Notes for the host: a tx_start while tx_busy is ignored; tx_count = 0 sends nothing and tx_busy falls
// again; tx_busy falls only after tx_frames has been refreshed, so the two can be read in either order;
// the receive counters are up to 10 us old; do not write the buffer while tx_busy; an rx_clear takes
// effect in the receiver within about 0.5 us, and a burst in flight at that moment is counted, not captured.
`default_nettype none

// The transmit buffer: 2048 bytes, written on wclk, read on rclk; q follows raddr by two rclk cycles.
module eth_txram #(parameter OUTREG = 1) (
    input  wire        wclk, input wire we,
    input  wire [10:0] waddr,
    input  wire [7:0]  wdata,
    input  wire        rclk,
    input  wire [10:0] raddr,
    output wire [7:0]  q
);
    generate if (OUTREG) begin : ebr
        // A DP16KD in its 2048 x 9 shape, wired exactly as yosys wires the one it infers for the same memory
        // (the address on AD[13:3], the byte on D[7:0], port A writes, port B reads), but for REGMODE_B.
        wire [8:0] nc;
        DP16KD #(
            .DATA_WIDTH_A(9), .DATA_WIDTH_B(9), .REGMODE_A("NOREG"), .REGMODE_B("OUTREG"),
            .RESETMODE("ASYNC"), .ASYNC_RESET_RELEASE("ASYNC"), .CSDECODE_A("0b000"), .CSDECODE_B("0b000"),
            .WRITEMODE_A("READBEFOREWRITE"), .WRITEMODE_B("READBEFOREWRITE"), .GSR("DISABLED")
        ) ram (
            .CLKA(wclk), .CEA(1'b1), .OCEA(1'b1), .WEA(we), .RSTA(1'b0), .CSA0(1'b0), .CSA1(1'b0), .CSA2(1'b0),
            .ADA0(1'b0), .ADA1(1'b0), .ADA2(1'b0), .ADA3(waddr[0]), .ADA4(waddr[1]), .ADA5(waddr[2]), .ADA6(waddr[3]),
            .ADA7(waddr[4]), .ADA8(waddr[5]), .ADA9(waddr[6]), .ADA10(waddr[7]), .ADA11(waddr[8]), .ADA12(waddr[9]), .ADA13(waddr[10]),
            .DIA0(wdata[0]), .DIA1(wdata[1]), .DIA2(wdata[2]), .DIA3(wdata[3]), .DIA4(wdata[4]), .DIA5(wdata[5]), .DIA6(wdata[6]),
            .DIA7(wdata[7]), .DIA8(1'b0), .DIA9(1'b0), .DIA10(1'b0), .DIA11(1'b0), .DIA12(1'b0), .DIA13(1'b0), .DIA14(1'b0),
            .DIA15(1'b0), .DIA16(1'b0), .DIA17(1'b0),
            .CLKB(rclk), .CEB(1'b1), .OCEB(1'b1), .WEB(1'b0), .RSTB(1'b0), .CSB0(1'b0), .CSB1(1'b0), .CSB2(1'b0),
            .ADB0(1'b0), .ADB1(1'b0), .ADB2(1'b0), .ADB3(raddr[0]), .ADB4(raddr[1]), .ADB5(raddr[2]), .ADB6(raddr[3]),
            .ADB7(raddr[4]), .ADB8(raddr[5]), .ADB9(raddr[6]), .ADB10(raddr[7]), .ADB11(raddr[8]), .ADB12(raddr[9]), .ADB13(raddr[10]),
            .DIB0(1'b0), .DIB1(1'b0), .DIB2(1'b0), .DIB3(1'b0), .DIB4(1'b0), .DIB5(1'b0), .DIB6(1'b0), .DIB7(1'b0), .DIB8(1'b0),
            .DIB9(1'b0), .DIB10(1'b0), .DIB11(1'b0), .DIB12(1'b0), .DIB13(1'b0), .DIB14(1'b0), .DIB15(1'b0), .DIB16(1'b0), .DIB17(1'b0),
            .DOB0(q[0]), .DOB1(q[1]), .DOB2(q[2]), .DOB3(q[3]), .DOB4(q[4]), .DOB5(q[5]), .DOB6(q[6]), .DOB7(q[7]), .DOB8(nc[8])
        );
    end else begin : inferred
        reg [7:0] mem [0:2047];
        always @(posedge wclk) if (we) mem[waddr] <= wdata;
        reg [7:0] q1 = 0, q2 = 0;
        always @(posedge rclk) begin q1 <= mem[raddr]; q2 <= q1; end
        assign q = q2;
    end endgenerate
endmodule

module eth_test #(
    parameter RX_DELAY      = "SCLK_CENTERED",   // the DELAYG mode on RXD and RX_CTL; "NONE" = no DELAYG
    parameter RX_DELAY_TAPS = 0,                 // with RX_DELAY = "USER_DEFINED": 25 ps steps, 0..127
    parameter TX_RAM_OUTREG = 1                  // 1: the buffer is a DP16KD with its output register; 0: inferred
) (
    input  wire        clk,          // 25 MHz bus clock (all the bus-side ports below are in this domain)
    input  wire        clk125,       // 125 MHz transmit clock from a PLL (not phase related to eth_rxc)
    // transmit buffer and control
    input  wire        tx_we,        // write tx_wdata to the frame buffer at tx_waddr
    input  wire [10:0] tx_waddr,
    input  wire [7:0]  tx_wdata,
    input  wire [10:0] tx_len,       // bytes in the frame, destination MAC through FCS (60..1518+4 allowed; quasi-static)
    input  wire [15:0] tx_count,     // frames to send per start (quasi-static)
    input  wire [11:0] tx_gap,       // idle byte times between frames (use >= 12; quasi-static)
    input  wire        tx_start,     // one-cycle pulse: send tx_count frames
    output wire        tx_busy,      // high from tx_start until the last frame has gone (synchronised into clk)
    output wire [31:0] tx_frames,    // frames sent since power-up
    // receive counters and capture
    input  wire        rx_clear,     // one-cycle pulse: zero the three counters and re-arm the capture
    output wire [31:0] rx_frames,    // frames seen since the clear
    output wire [31:0] rx_good,      // of those, frames with a correct CRC-32 and no RX_ER
    output wire [31:0] rx_bad,       // frames with a wrong CRC-32 or RX_ER during the frame
    output wire        rx_captured,  // a frame has been captured since the clear
    output wire [10:0] rx_len,       // its length in bytes (after the SFD, through the FCS)
    input  wire [10:0] rx_raddr,     // read address into the captured frame
    output wire [7:0]  rx_rdata,     // valid two clk cycles after rx_raddr (a registered block RAM read)
    // RGMII
    output wire        eth_txc, eth_tx_ctl,
    output wire [3:0]  eth_txd,
    input  wire        eth_rxc, eth_rx_ctl,
    input  wire [3:0]  eth_rxd
);
    // =================================================================================================
    // The bus side (clk)
    // =================================================================================================
    reg [7:0] tick = 0;                          // paces the snapshots: each side once every 256 cycles
    always @(posedge clk) tick <= tick + 1'b1;

    // ---- transmit: start and busy, the frame counter's snapshot ---------------------------------------
    reg  tx_busy_r = 0;
    wire tx_go = tx_start & ~tx_busy_r;          // the engine is idle whenever tx_busy_r is 0
    wire tx_go125, tx_done;
    reg  t_done = 0;                             // clk125: the last gap is over
    sync_pulse sp_go   (.clk_a(clk),    .pulse_a(tx_go),  .clk_b(clk125), .pulse_b(tx_go125));
    sync_pulse sp_done (.clk_a(clk125), .pulse_a(t_done), .clk_b(clk),    .pulse_b(tx_done));

    reg        tq = 0;                           // the request (a toggle)
    reg        tq_open = 0;                      // a request is out, its acknowledge not yet seen
    reg        tq_fin = 0;                       // the open request was made after the engine finished
    reg        t_want = 0;                       // the engine has finished: a snapshot is wanted now
    reg        tk = 0;                           // clk125: the acknowledge
    wire       tk_s;
    reg [31:0] th_frames = 0;                    // clk125: the holding register
    reg [31:0] tx_frames_r = 0;
    sync_bit sb_tk (.clk_b(clk), .d(tk), .q(tk_s));
    always @(posedge clk) begin
        if (!tq_open) begin
            if (t_want || tick == 8'h00) begin tq <= ~tq; tq_open <= 1'b1; tq_fin <= t_want; t_want <= 1'b0; end
        end else if (tk_s == tq) begin
            tq_open <= 1'b0;
            tx_frames_r <= th_frames;            // written two clk cycles ago at least, and not again before the next request
            if (tq_fin) tx_busy_r <= 1'b0;       // busy falls with the final count already on tx_frames
        end
        if (tx_done) t_want <= 1'b1;
        if (tx_go)   tx_busy_r <= 1'b1;
    end
    assign tx_busy   = tx_busy_r;
    assign tx_frames = tx_frames_r;

    // ---- receive: the snapshot and the clear ----------------------------------------------------------
    reg        rq = 0;                           // the request (a toggle)
    reg        rq_clr = 0;                       // this request also clears; set a cycle before rq toggles
    reg        rq_set = 0;                       // rq_clr is set, rq toggles next cycle
    reg        rq_open = 0;
    reg        r_want = 0;                       // an rx_clear is waiting for its turn
    reg        rk = 0;                           // eth_rxc: the acknowledge
    wire       rk_s;
    reg [31:0] rh_frames = 0, rh_good = 0, rh_bad = 0;   // eth_rxc: the holding registers
    reg        rh_cap = 0;
    reg [10:0] rh_len = 0;
    reg [31:0] rx_frames_r = 0, rx_good_r = 0, rx_bad_r = 0;
    reg        rx_captured_r = 0;
    reg [10:0] rx_len_r = 0;
    sync_bit sb_rk (.clk_b(clk), .d(rk), .q(rk_s));
    always @(posedge clk) begin
        if (rq_set) begin rq <= ~rq; rq_open <= 1'b1; rq_set <= 1'b0; end
        else if (!rq_open) begin
            if (r_want)             begin rq_clr <= 1'b1; rq_set <= 1'b1; r_want <= 1'b0; end
            else if (tick == 8'h80) begin rq_clr <= 1'b0; rq_set <= 1'b1; end
        end else if (rk_s == rq) begin
            rq_open <= 1'b0;
            // A snapshot taken before a clear that is still waiting, and the one a clear itself takes,
            // are of the old counts: they are dropped, and the outputs stay at the zeros rx_clear put there.
            if (!rq_clr && !r_want) begin
                rx_frames_r <= rh_frames; rx_good_r <= rh_good; rx_bad_r <= rh_bad;
                rx_captured_r <= rh_cap;  rx_len_r <= rh_len;
            end
        end
        if (rx_clear) begin
            r_want <= 1'b1;
            rx_frames_r <= 0; rx_good_r <= 0; rx_bad_r <= 0; rx_captured_r <= 1'b0; rx_len_r <= 0;
        end
    end
    assign rx_frames   = rx_frames_r;
    assign rx_good     = rx_good_r;
    assign rx_bad      = rx_bad_r;
    assign rx_captured = rx_captured_r;
    assign rx_len      = rx_len_r;

    // ---- the captured frame's read port ---------------------------------------------------------------
    reg [7:0] capmem [0:2047];
    reg [7:0] rd1 = 0, rd2 = 0;
    always @(posedge clk) begin rd1 <= capmem[rx_raddr]; rd2 <= rd1; end
    assign rx_rdata = rd2;

    // =================================================================================================
    // The transmitter (clk125)
    // =================================================================================================
    // The engine counts every state down, and no count is compared with anything: `s` is the number of bytes
    // of the state that follow this one, less one, as a signed number, so it goes negative on the state's last
    // byte and its sign bit is the "last byte" flag.  A state of n bytes starts at n - 2 (n = 1, or 0, starts
    // negative: one byte).  `nxt` holds what s is to start the next state with, `fs` counts the frames the
    // same way.  The three lengths less two are worked out once, before the first frame.
    localparam T_IDLE = 2'd0, T_PRE = 2'd1, T_DATA = 2'd2, T_GAP = 2'd3;
    reg [1:0]  tstate = T_IDLE;
    reg [3:0]  go_d = 0;                         // the start, 1 to 4 cycles on
    reg [10:0] len_r = 0;                        // the three quasi-static inputs, copied into this domain
    reg [11:0] gap_r = 0;
    reg [15:0] cnt_r = 0;
    reg [12:0] dlen_m2 = 0, glen_m2 = 0;         // bytes of data, byte times of gap, each less two
    reg [16:0] cnt_m2 = 0;                       // frames, less two
    reg        fnone = 0;                        // tx_count is 0
    reg [12:0] s = 13'd6, nxt = 0;
    reg [16:0] fs = 0;
    wire       last  = s[12];                    // this is the state's last byte
    wire       flast = fs[16];                   // this is the last frame
    reg        fr_inc = 0;                       // a frame's last byte has gone, a cycle ago
    reg [10:0] raddr = 0;                        // the buffer's read address: 0 up through the data
    reg [31:0] t_frames = 0;
    always @(posedge clk125) begin
        go_d <= {go_d[2:0], tx_go125};
        if (go_d[1]) begin len_r <= tx_len; gap_r <= tx_gap; cnt_r <= tx_count; end
        if (go_d[2]) begin
            dlen_m2 <= {2'b00, len_r} - 13'd2;
            glen_m2 <= {1'b0, gap_r} - 13'd2;
            cnt_m2  <= {1'b0, cnt_r} - 17'd2;
            fnone   <= ~|cnt_r;
        end
        t_done <= 1'b0; fr_inc <= 1'b0;
        if (tstate == T_IDLE) s <= 13'd6;        // the preamble and SFD: 8 bytes
        else if (last)        s <= nxt;
        else                  s <= s - 1'b1;
        case (tstate)
        T_IDLE: begin
            nxt <= dlen_m2; fs <= cnt_m2;
            if (go_d[3]) begin if (fnone) t_done <= 1'b1; else tstate <= T_PRE; end
        end
        T_PRE:  if (last) begin tstate <= T_DATA; nxt <= glen_m2; end
        T_DATA: if (last) begin tstate <= T_GAP;  nxt <= 13'd6; fr_inc <= 1'b1; end
        T_GAP:  if (last) begin
                    nxt <= dlen_m2; fs <= fs - 1'b1;
                    if (flast) begin tstate <= T_IDLE; t_done <= 1'b1; end else tstate <= T_PRE;
                end
        endcase
        if (fr_inc) t_frames <= t_frames + 1'b1;
        raddr <= tstate == T_DATA ? raddr + 1'b1 : 11'd0;
    end

    // The buffer, one more register after it, and what the engine wants on the wire delayed alongside.
    wire [7:0] tram_q;
    eth_txram #(.OUTREG(TX_RAM_OUTREG)) txram (.wclk(clk), .we(tx_we), .waddr(tx_waddr), .wdata(tx_wdata),
                                               .rclk(clk125), .raddr(raddr), .q(tram_q));
    localparam K_IDLE = 2'd0, K_PRE = 2'd1, K_SFD = 2'd2, K_DATA = 2'd3;
    wire [1:0] k0 = tstate == T_PRE  ? (last ? K_SFD : K_PRE) :
                    tstate == T_DATA ? K_DATA : K_IDLE;
    reg  [1:0] k1 = 0, k2 = 0, k3 = 0;
    reg  [7:0] tqr = 0, txb = 0;
    reg        txen = 0;
    always @(posedge clk125) begin
        k1 <= k0; k2 <= k1; k3 <= k2;
        tqr  <= tram_q;
        txen <= k3 != K_IDLE;
        txb  <= k3 == K_DATA ? tqr : k3 == K_SFD ? 8'hD5 : k3 == K_PRE ? 8'h55 : 8'h00;
    end

    // The pins.  D0 goes out in the half cycle after the rising edge, D1 in the half after the falling edge.
    ODDRX1F oddr_txc (.SCLK(clk125), .RST(1'b0), .D0(1'b1), .D1(1'b0), .Q(eth_txc));
    ODDRX1F oddr_ctl (.SCLK(clk125), .RST(1'b0), .D0(txen), .D1(txen), .Q(eth_tx_ctl));
    genvar g;
    generate for (g = 0; g < 4; g = g + 1) begin : txpin
        ODDRX1F oddr (.SCLK(clk125), .RST(1'b0), .D0(txb[g]), .D1(txb[g + 4]), .Q(eth_txd[g]));
    end endgenerate

    // The frame counter's snapshot, on request.  The strobe is a register of its own: it enables 32 others.
    reg [1:0] tq_s = 0;
    reg       t_snap = 0;
    always @(posedge clk125) begin
        tq_s   <= {tq_s[0], tq};
        t_snap <= (tq_s[1] != tk) & ~t_snap;
        if (t_snap) begin th_frames <= t_frames; tk <= ~tk; end
    end

    // =================================================================================================
    // The receiver (eth_rxc)
    // =================================================================================================
    // The pins: [3:0] RXD, [4] RX_CTL.
    wire [4:0] rx_pad = {eth_rx_ctl, eth_rxd};
    wire [4:0] rx_del, rx_q0, rx_q1;
    generate for (g = 0; g < 5; g = g + 1) begin : rxpin
        if (RX_DELAY == "NONE") begin : direct
            assign rx_del[g] = rx_pad[g];
        end else if (RX_DELAY == "USER_DEFINED") begin : taps
            DELAYG #(.DEL_MODE("USER_DEFINED"), .DEL_VALUE(RX_DELAY_TAPS)) dly (.A(rx_pad[g]), .Z(rx_del[g]));
        end else begin : preset
            DELAYG #(.DEL_MODE(RX_DELAY)) dly (.A(rx_pad[g]), .Z(rx_del[g]));
        end
        IDDRX1F iddr (.D(rx_del[g]), .SCLK(eth_rxc), .RST(1'b0), .Q0(rx_q0[g]), .Q1(rx_q1[g]));
    end endgenerate
    // Two registers before anything is decided: the first only has to be reached from the I/O cells, the
    // second comes with "this byte is 0xD5" and the byte's share of the CRC already worked out.
    // CRC-32, one byte: the frame's bits arrive bit 0 of each byte first, so the register shifts right.
    function [31:0] crc32_next (input [31:0] c, input [7:0] d);
        integer i;
        reg [31:0] x;
        begin
            x = c ^ {24'b0, d};
            for (i = 0; i < 8; i = i + 1) x = x[0] ? (x >> 1) ^ 32'hEDB88320 : (x >> 1);
            crc32_next = x;
        end
    endfunction
    localparam [31:0] CRC_RESIDUE = 32'hDEBB20E3;

    reg [7:0]  a_byte = 0, b_byte = 0;
    reg        a_dv = 0, a_er = 0, b_dv = 0, b_er = 0, b_sfd = 0;
    reg [31:0] b_dcrc = 0;                       // what this byte adds to the CRC
    always @(posedge eth_rxc) begin
        a_byte <= {rx_q1[3:0], rx_q0[3:0]};
        a_dv   <= rx_q0[4];
        a_er   <= rx_q0[4] & ~rx_q1[4];          // RX_ER = RX_DV xor the falling-edge sample; only inside a burst
        b_byte <= a_byte; b_dv <= a_dv; b_er <= a_er;
        b_sfd  <= a_byte == 8'hD5;
        b_dcrc <= crc32_next(32'd0, a_byte);
    end

    reg        in_frame = 0;                     // RX_DV was up in the last cycle
    reg        in_data = 0;                      // and the SFD has gone by
    reg        rerr = 0;                         // RX_ER seen in this burst
    reg [31:0] rcrc = 32'hFFFFFFFF;
    reg        crc_eq = 0;                       // rcrc was the residue, a cycle ago
    reg [11:0] rcnt = 0;                         // bytes stored from this burst (since its SFD, if it had one); stops at 2048
    reg        cap_en = 1;                       // this burst (or, between bursts, the next) goes to the capture memory
    reg        cap_done = 0;
    reg [10:0] cap_len = 0;
    reg        cw_we = 0;                        // the capture memory's write port, registered
    reg [10:0] cw_addr = 0;
    reg [7:0]  cw_data = 0;
    reg        e1 = 0, e1_data = 0, e1_err = 0;  // the burst has ended: one cycle on ...
    reg        e2 = 0, e2_good = 0, e2_bad = 0;  // ... and two, with the verdict
    reg [31:0] r_frames = 0, r_good = 0, r_bad = 0;
    reg [1:0]  rq_s = 0;
    reg        r_snap = 0, r_clr = 0;            // the request's strobes, registers of their own
    wire       b_end = in_frame & ~b_dv;
    always @(posedge eth_rxc) begin
        // the burst's outline
        in_frame <= b_dv;
        if (!b_dv) in_data <= 1'b0; else if (b_sfd) in_data <= 1'b1;
        if (b_dv) rerr <= (in_frame & rerr) | b_er;
        // The CRC: all ones until the SFD has passed, then every byte; it keeps its value after the burst.
        // The step is linear, next(c, d) = next(c, 0) ^ next(0, d), and the second half came with the byte.
        if (b_dv) rcrc <= in_data ? crc32_next(rcrc, 8'h00) ^ b_dcrc : 32'hFFFFFFFF;
        crc_eq <= rcrc == CRC_RESIDUE;
        // the capture: from the burst's first byte, and again from 0 after the SFD
        cw_we <= 1'b0; cw_addr <= rcnt[10:0]; cw_data <= b_byte;
        if (!b_dv || (b_sfd && !in_data)) rcnt <= 0;
        else begin
            cw_we <= cap_en & ~rcnt[11];
            if (!rcnt[11]) rcnt <= rcnt + 1'b1;
        end
        if (b_end && cap_en) begin cap_done <= 1'b1; cap_len <= rcnt[11] ? 11'd2047 : rcnt[10:0]; end
        if (!b_dv) cap_en <= ~cap_done & ~(in_frame & cap_en);
        // the verdict, two cycles after the end, and the counters
        e1 <= b_end; e1_data <= in_data; e1_err <= rerr;
        e2 <= e1;
        e2_good <= e1 &  (e1_data & ~e1_err & crc_eq);
        e2_bad  <= e1 & ~(e1_data & ~e1_err & crc_eq);
        if (e2)      r_frames <= r_frames + 1'b1;
        if (e2_good) r_good   <= r_good + 1'b1;
        if (e2_bad)  r_bad    <= r_bad + 1'b1;
        // a request from the bus side: hold the counts, and clear if it says so (the clear wins over a count)
        rq_s   <= {rq_s[0], rq};
        r_snap <= (rq_s[1] != rk) & ~r_snap;
        r_clr  <= (rq_s[1] != rk) & ~r_snap & rq_clr;
        if (r_snap) begin
            rk <= ~rk;
            rh_frames <= r_frames; rh_good <= r_good; rh_bad <= r_bad; rh_cap <= cap_done; rh_len <= cap_len;
        end
        if (r_clr) begin
            r_frames <= 0; r_good <= 0; r_bad <= 0;
            cap_done <= 1'b0; cap_en <= 1'b0;    // a capture under way is dropped; the next burst is taken
        end
    end
    always @(posedge eth_rxc) if (cw_we) capmem[cw_addr] <= cw_data;
endmodule
`default_nettype wire
