// Bench models for sim/tb_eth.v: the ECP5 cells rtl/eth_test.v uses that sim/ecp5_sim_models.v does not have
// (IDDRX1F, DELAYG, DP16KD), and the RTL8211F as the FPGA's RGMII pins see it at gigabit speed.
`timescale 1ns/1ps

// The ECP5's input DDR cell.  D is sampled on both edges of SCLK; Q0 (the rising-edge sample) and Q1 (the
// sample of the falling edge after it) change together after the next rising edge, so {Q1, Q0} of one cycle
// is one RGMII byte.  The clock reaches the cell TCLK after the pin (a stand-in for the clock tree, set to what
// DELAYG's SCLK_CENTERED undoes), and D must hold still for TWIN either side of each sampling edge (the data
// sheet's 0.52 ns for the centred interface): `viol` counts the times it did not.
module IDDRX1F #(parameter GSR = "ENABLED", parameter real TCLK = 0.975, parameter real TWIN = 0.52) (
    input D, input SCLK, input RST, output reg Q0, output reg Q1
);
    reg sclk_i = 0;
    always @(SCLK) sclk_i <= #(TCLK) SCLK;
    reg dp = 0, dn = 0;
    initial begin Q0 = 0; Q1 = 0; end
    integer  viol = 0;
    realtime t_d = 0, t_s = 0;
    always @(D) begin
        t_d = $realtime;
        if (t_s > 0 && $realtime - t_s < TWIN) viol = viol + 1;         // moved too soon after a sampling edge
    end
    always @(sclk_i) begin
        t_s = $realtime;
        if (t_d > 0 && $realtime - t_d < TWIN) viol = viol + 1;         // sampled too soon after D moved
    end
    always @(posedge sclk_i) begin
        if (RST) begin Q0 <= 1'b0; Q1 <= 1'b0; end else begin Q0 <= dp; Q1 <= dn; end
        dp <= D;
    end
    always @(negedge sclk_i) dn <= D;
endmodule

// The ECP5's fixed input delay: 25 ps a tap; the named modes are the tap counts nextpnr-ecp5 writes for them.
module DELAYG #(parameter DEL_MODE = "USER_DEFINED", parameter DEL_VALUE = 0) (input A, output Z);
    localparam integer TAPS = DEL_MODE == "USER_DEFINED"  ? DEL_VALUE :
                              DEL_MODE == "SCLK_CENTERED" ? 39 :
                              DEL_MODE == "SCLK_ALIGNED"  ? 50 :
                              DEL_MODE == "SCLK_ZEROHOLD" ? 59 : 0;
    assign #(TAPS * 0.025) Z = A;        // a pin that has not moved yet still gets through (an always @(A) would wait for an edge)
endmodule

// The ECP5's block RAM in its 2048 x 9 shape, the one rtl/eth_test.v instantiates by hand for its output register
// (yosys's cells_sim.v has the ports and no behaviour).  Each port takes its address, data and write enable on
// its clock's rising edge; what it read shows after that edge (REGMODE NOREG) or after the next (OUTREG).  A
// port that writes shows the old contents (READBEFOREWRITE), the new (WRITETHROUGH) or keeps its output
// (NORMAL).  The memory starts at 0, as the default INITVALs make it.
module DP16KD #(
    parameter DATA_WIDTH_A = 18, DATA_WIDTH_B = 18, REGMODE_A = "NOREG", REGMODE_B = "NOREG",
    parameter RESETMODE = "SYNC", ASYNC_RESET_RELEASE = "SYNC", CSDECODE_A = "0b000", CSDECODE_B = "0b000",
    parameter WRITEMODE_A = "NORMAL", WRITEMODE_B = "NORMAL", GSR = "ENABLED"
) (
    input  CLKA, CEA, OCEA, WEA, RSTA, CSA0, CSA1, CSA2,
    input  ADA0, ADA1, ADA2, ADA3, ADA4, ADA5, ADA6, ADA7, ADA8, ADA9, ADA10, ADA11, ADA12, ADA13,
    input  DIA0, DIA1, DIA2, DIA3, DIA4, DIA5, DIA6, DIA7, DIA8, DIA9, DIA10, DIA11, DIA12, DIA13, DIA14, DIA15, DIA16, DIA17,
    output DOA0, DOA1, DOA2, DOA3, DOA4, DOA5, DOA6, DOA7, DOA8, DOA9, DOA10, DOA11, DOA12, DOA13, DOA14, DOA15, DOA16, DOA17,
    input  CLKB, CEB, OCEB, WEB, RSTB, CSB0, CSB1, CSB2,
    input  ADB0, ADB1, ADB2, ADB3, ADB4, ADB5, ADB6, ADB7, ADB8, ADB9, ADB10, ADB11, ADB12, ADB13,
    input  DIB0, DIB1, DIB2, DIB3, DIB4, DIB5, DIB6, DIB7, DIB8, DIB9, DIB10, DIB11, DIB12, DIB13, DIB14, DIB15, DIB16, DIB17,
    output DOB0, DOB1, DOB2, DOB3, DOB4, DOB5, DOB6, DOB7, DOB8, DOB9, DOB10, DOB11, DOB12, DOB13, DOB14, DOB15, DOB16, DOB17
);
    initial if (DATA_WIDTH_A != 9 || DATA_WIDTH_B != 9) begin
        $display("FAIL: this DP16KD model knows the 2048 x 9 shape only (DATA_WIDTH_A/B = 9)"); $finish;
    end
    wire [13:0] ada = {ADA13, ADA12, ADA11, ADA10, ADA9, ADA8, ADA7, ADA6, ADA5, ADA4, ADA3, ADA2, ADA1, ADA0};
    wire [13:0] adb = {ADB13, ADB12, ADB11, ADB10, ADB9, ADB8, ADB7, ADB6, ADB5, ADB4, ADB3, ADB2, ADB1, ADB0};
    wire [8:0]  dia = {DIA8, DIA7, DIA6, DIA5, DIA4, DIA3, DIA2, DIA1, DIA0};
    wire [8:0]  dib = {DIB8, DIB7, DIB6, DIB5, DIB4, DIB3, DIB2, DIB1, DIB0};
    // CSDECODE is "0b" and three digits, the first for CS2; a digit's last bit is its value
    wire sel_a = {CSA2, CSA1, CSA0} == {CSDECODE_A[16], CSDECODE_A[8], CSDECODE_A[0]};
    wire sel_b = {CSB2, CSB1, CSB0} == {CSDECODE_B[16], CSDECODE_B[8], CSDECODE_B[0]};
    reg [8:0] mem [0:2047];
    reg [8:0] la = 0, lb = 0, ra = 0, rb = 0;            // each port's read latch and its output register
    integer i;
    initial for (i = 0; i < 2048; i = i + 1) mem[i] = 9'd0;
    always @(posedge CLKA) begin
        if (OCEA) ra <= la;
        if (CEA && sel_a) begin
            if (!WEA) la <= mem[ada[13:3]];
            else begin
                mem[ada[13:3]] <= dia;
                if (WRITEMODE_A == "READBEFOREWRITE") la <= mem[ada[13:3]]; else if (WRITEMODE_A == "WRITETHROUGH") la <= dia;
            end
        end
        if (RSTA) begin la <= 0; ra <= 0; end
    end
    always @(posedge CLKB) begin
        if (OCEB) rb <= lb;
        if (CEB && sel_b) begin
            if (!WEB) lb <= mem[adb[13:3]];
            else begin
                mem[adb[13:3]] <= dib;
                if (WRITEMODE_B == "READBEFOREWRITE") lb <= mem[adb[13:3]]; else if (WRITEMODE_B == "WRITETHROUGH") lb <= dib;
            end
        end
        if (RSTB) begin lb <= 0; rb <= 0; end
    end
    wire [8:0] qa = REGMODE_A == "OUTREG" ? ra : la;
    wire [8:0] qb = REGMODE_B == "OUTREG" ? rb : lb;
    assign {DOA8, DOA7, DOA6, DOA5, DOA4, DOA3, DOA2, DOA1, DOA0} = qa;
    assign {DOB8, DOB7, DOB6, DOB5, DOB4, DOB3, DOB2, DOB1, DOB0} = qb;
    assign {DOA17, DOA16, DOA15, DOA14, DOA13, DOA12, DOA11, DOA10, DOA9} = 9'd0;
    assign {DOB17, DOB16, DOB15, DOB14, DOB13, DOB12, DOB11, DOB10, DOB9} = 9'd0;
endmodule

// The RTL8211F, RGMII side only, strapped TXDLY = RXDLY = 1 as on the board.
//   * Transmit pins: TXC is delayed by TXDLY inside, then TXD/TX_CTL are sampled on both of its edges.  A
//     monitor counts the frames the FPGA sends, checks each preamble (7 x 0x55, 0xD5), keeps the last
//     frame's length and the smallest gap, and counts data edges further than TSKEW from a TXC edge.
//   * loopback = 1 (BMCR bit 14): those bytes go into an elastic buffer and are played back on the receive
//     pins from the PHY's own clock, which is not the FPGA's (PERIOD = 8.001 ns: 125 ppm slow).  A frame
//     starts to play once START_FILL bytes are in, and the PHY makes up for its slower clock as a real one
//     does, by leaving fewer idle bytes between frames (never fewer than MIN_IPG).  The buffer holds frame
//     bytes only, never idle: however long the line was idle and however far the clocks slipped meanwhile,
//     the next frame starts from an empty buffer.
//   * loopback = 0 and link = 1: the receive pins carry what the wire brings, which is what the
//     testbench's send_frame plays.  The FPGA's frames go out to the wire (the monitor still counts them).
//   * Receive pins: RXD/RX_CTL change on the edges of the PHY's clock and RXC follows RXDLY later, so RXC
//     is centred in the data at the FPGA.  Between frames RXD shows the in-band status: {link, 2'b10, link}.
//   * rst_n = 0: RXC stops and the pins sit at their strap levels (RXD = 1011: PHYAD0, TXDLY and RXDLY
//     pulled up).  rxc_div (set it from the testbench) divides RXC, as a PHY without a gigabit link does
//     (5: 25 MHz, 50: 2.5 MHz); the model sends nothing but idle then.
module rgmii_phy_model #(
    parameter real    PERIOD     = 8.001,   // the PHY's own 125 MHz
    parameter real    TXDLY      = 2.0,     // added to TXC before TXD is sampled
    parameter real    RXDLY      = 2.0,     // added to RXC after the RXD edges
    parameter real    TSKEW      = 0.5,     // RGMII: data within +-0.5 ns of the clock edge at the transmitter
    parameter real    TX_HALF    = 4.0,     // half a TXC period, for the skew check
    parameter integer START_FILL = 4,
    parameter integer MIN_IPG    = 5
) (
    input  wire       rst_n,
    input  wire       loopback,
    input  wire       link,
    input  wire       txc, tx_ctl,
    input  wire [3:0] txd,
    output wire       rxc, rx_ctl,
    output wire [3:0] rxd
);
    // ---- the PHY's clock -------------------------------------------------------------------------
    // The two halves are whole picoseconds (the simulator's step) that add up to PERIOD: half of 8.001 ns
    // would be rounded, and the offset from the FPGA's clock with it.
    localparam integer HI_PS = PERIOD * 500.0;
    localparam real    T_HI  = HI_PS / 1000.0;
    localparam real    T_LO  = PERIOD - T_HI;
    integer rxc_div = 1;
    reg pclk = 0;
    always begin
        #(T_LO * rxc_div); pclk = rst_n;
        #(T_HI * rxc_div); pclk = 1'b0;
    end
    reg rxc_r = 0;
    always @(pclk) rxc_r <= #(RXDLY) pclk;

    // ---- the transmit pins -----------------------------------------------------------------------
    reg txc_d = 0;
    always @(txc) txc_d <= #(TXDLY) txc;
    reg [3:0] t_lo = 0;
    reg       t_en = 0;
    always @(posedge txc_d) begin t_lo <= txd; t_en <= tx_ctl; end

    // the monitor's results
    integer tx_frames_seen = 0;          // frames the FPGA has sent
    integer tx_last_len = 0;             // bytes after the SFD in the last of them
    integer tx_min_gap = 1000000;        // the fewest idle byte times between two of them
    integer tx_pre_bad = 0;              // frames whose preamble was not 7 x 0x55 then 0xD5
    integer tx_er_seen = 0;              // byte times with TX_ER
    integer tx_skew_viol = 0;            // TXD/TX_CTL edges further than TSKEW from a TXC edge
    reg     m_in = 0, m_sfd = 0;
    integer m_pre = 0, m_len = 0, m_gap = 0;

    // the elastic buffer: byte, TX_ER, last-of-frame
    localparam FIFO_N = 4096;
    reg [7:0] f_b [0:FIFO_N-1];
    reg       f_e [0:FIFO_N-1];
    reg       f_l [0:FIFO_N-1];
    integer   wp = 0, rp = 0, lasts_w = 0, lasts_r = 0, overruns = 0, underruns = 0;
    reg       pend = 0, pend_e = 0;      // one byte is held back so that the last of a frame can be marked
    reg [7:0] pend_b = 0;
    task push(input [7:0] b, input e, input l); begin
        f_b[wp % FIFO_N] = b; f_e[wp % FIFO_N] = e; f_l[wp % FIFO_N] = l;
        if (l) lasts_w = lasts_w + 1;
        wp = wp + 1;
        if (wp - rp > FIFO_N) begin overruns = overruns + 1; $display("PHY model: elastic buffer overrun at %t", $time); end
    end endtask

    always @(negedge txc_d) if (rst_n) begin : tx_byte
        reg [7:0] b; reg en, er;
        b = {txd, t_lo}; en = t_en === 1'b1; er = en && (tx_ctl !== 1'b1);
        if (en) begin
            if (!m_in) begin
                if (tx_frames_seen > 0 && m_gap < tx_min_gap) tx_min_gap = m_gap;
                m_in = 1; m_sfd = 0; m_pre = 0; m_len = 0;
            end
            if (m_sfd) m_len = m_len + 1;
            else if (b == 8'hD5) begin m_sfd = 1; if (m_pre != 7) tx_pre_bad = tx_pre_bad + 1; end
            else if (b == 8'h55) m_pre = m_pre + 1;
            else m_pre = -1000;                                   // anything else before the SFD spoils it
            if (er) tx_er_seen = tx_er_seen + 1;
            if (loopback) begin
                if (pend) push(pend_b, pend_e, 1'b0);
                pend = 1; pend_b = b; pend_e = er;
            end
        end else begin
            if (m_in) begin
                m_in = 0; m_gap = 0;
                tx_frames_seen = tx_frames_seen + 1; tx_last_len = m_len;
                if (!m_sfd) tx_pre_bad = tx_pre_bad + 1;
            end
            m_gap = m_gap + 1;
            if (pend) begin push(pend_b, pend_e, 1'b1); pend = 0; end
        end
    end

    realtime t_txc = 0;
    real     dt;
    always @(txc) t_txc = $realtime;
    always @(txd or tx_ctl) if (rst_n && t_txc > 0) begin
        dt = $realtime - t_txc;
        if (dt > TSKEW && dt < TX_HALF - TSKEW) begin
            tx_skew_viol = tx_skew_viol + 1;
            if (tx_skew_viol <= 3) $display("PHY model: TXD/TX_CTL moved %0.2f ns after a TXC edge at %t", dt, $time);
        end
    end

    // ---- the wire: the testbench's frames ----------------------------------------------------------
    reg [7:0] frame [0:2047];            // the testbench fills this, then calls send_frame
    integer   preamble = 7;              // 0x55 bytes before the SFD
    reg [7:0] sfd_byte = 8'hD5;          // the byte sent as the SFD (anything else: a burst with no SFD in it)
    integer   ipg_after = 12;            // idle byte times after the frame, before send_frame returns
    integer   flip_byte = -1;            // the byte `corrupt` damages (-1: the middle one) ...
    integer   flip_bit = 0;              // ... and which bit of it
    reg       rx_er_mid = 0;             // set before send_frame: RX_ER for one byte in the middle (clears itself)
    integer   inj_dropped = 0;           // frames send_frame could not deliver (reset, loopback, no link, slow clock)
    reg       inj_dv = 0, inj_er = 0;
    reg [7:0] inj_b = 0;
    task send_frame(input integer len, input corrupt);
        integer i, fb;
        begin
            if (!rst_n || loopback || !link || rxc_div != 1) begin
                inj_dropped = inj_dropped + 1;
                $display("PHY model: send_frame not delivered (reset, loopback, no link or no gigabit clock)");
            end else begin
                fb = flip_byte >= 0 ? flip_byte : len / 2;
                for (i = 0; i < preamble; i = i + 1) begin @(negedge pclk); inj_dv = 1; inj_er = 0; inj_b = 8'h55; end
                @(negedge pclk); inj_dv = 1; inj_er = 0; inj_b = sfd_byte;
                for (i = 0; i < len; i = i + 1) begin
                    @(negedge pclk);
                    inj_b  = frame[i] ^ ((corrupt && i == fb) ? (8'h01 << flip_bit) : 8'h00);
                    inj_er = rx_er_mid && i == len / 2;
                end
                @(negedge pclk); inj_dv = 0; inj_er = 0; rx_er_mid = 0;
                repeat (ipg_after) @(negedge pclk);
            end
        end
    endtask

    // ---- the receive pins --------------------------------------------------------------------------
    integer rx_frames_out = 0;           // frames put on the receive pins
    integer rx_min_ipg = 1000000;        // the fewest idle byte times between two of them
    wire [3:0] idle = {link, 2'b10, link};
    reg  [7:0] o_b = 0;
    reg        o_dv = 0, o_er = 0, o_was = 0;
    reg        playing = 0;
    integer    ipg = 1000;
    reg  [3:0] rxd_r = 0;
    reg        ctl_r = 0;
    always @(posedge pclk) begin
        if (!loopback && rp != wp) begin rp = wp; lasts_r = lasts_w; playing = 0; end       // loopback switched off: drop the rest
        if (!loopback && inj_dv && rxc_div == 1) begin
            o_dv = 1; o_b = inj_b; o_er = inj_er;
        end else if (loopback && rxc_div == 1 &&
                     (playing || (ipg >= MIN_IPG && (wp - rp >= START_FILL || lasts_w != lasts_r)))) begin
            if (wp == rp) begin
                underruns = underruns + 1; playing = 0; o_dv = 0; o_er = 0;
                $display("PHY model: elastic buffer ran dry in mid-frame at %t", $time);
            end else begin
                o_dv = 1; o_b = f_b[rp % FIFO_N]; o_er = f_e[rp % FIFO_N]; playing = !f_l[rp % FIFO_N];
                if (f_l[rp % FIFO_N]) lasts_r = lasts_r + 1;
                rp = rp + 1;
            end
        end else begin
            o_dv = 0; o_er = 0;
        end
        if (o_dv) begin
            if (!o_was && rx_frames_out > 0 && ipg < rx_min_ipg) rx_min_ipg = ipg;
            ipg = 0;
        end else begin
            if (o_was) rx_frames_out = rx_frames_out + 1;
            ipg = ipg + 1;
        end
        o_was = o_dv;
        rxd_r <= o_dv ? o_b[3:0] : idle;
        ctl_r <= o_dv;
    end
    always @(negedge pclk) begin
        rxd_r <= o_dv ? o_b[7:4] : idle;
        ctl_r <= o_dv ^ o_er;
    end
    // into reset: everything in flight is lost
    always @(negedge rst_n) begin
        rp = wp; lasts_r = lasts_w; playing = 0; pend = 0; m_in = 0; o_dv = 0; o_er = 0; o_was = 0; ipg = 1000;
    end
    assign rxc    = rst_n ? rxc_r : 1'b0;
    assign rx_ctl = rst_n ? ctl_r : 1'b0;
    assign rxd    = rst_n ? rxd_r : 4'b1011;
endmodule
