// Self-checking testbench for rtl/eth_test.v.  The register bus is here as tasks (every bus input changes on
// clk's falling edge), the PHY is sim/rgmii_phy_model.v with its own 125 MHz, 125 ppm off the FPGA's.
// The FCS of every frame comes from fcs_of() below, which is the standard's own description of the CRC (a
// shift register fed the frame's bits in wire order, most significant coefficient first, polynomial
// 0x04C11DB7) and shares nothing with the byte-wide, reflected form in the design.  It ends with the count
// of checks and PASS or FAIL.  Run it from the bringup directory:
//   iverilog -g2012 -o build/tb_eth.vvp -s tb_eth sim/tb_eth.v rtl/eth_test.v rtl/cdc.v sim/rgmii_phy_model.v sim/ecp5_sim_models.v
//   vvp -n build/tb_eth.vvp            (+vcd writes tb_eth.vcd, a very big file: only for a look at a failure)
// -Ptb_eth.PHY_PERIOD=7.999 makes the PHY's clock the fast one; -Ptb_eth.RX_DELAY=\"NONE\" takes the input delay out;
// -Ptb_eth.TX_RAM_OUTREG=0 runs the transmit buffer as the memory yosys infers instead of the DP16KD.
`timescale 1ns/1ps
module tb_eth;
    parameter real PHY_PERIOD = 8.001;
    parameter      RX_DELAY   = "SCLK_CENTERED";
    parameter      TX_RAM_OUTREG = 1;

    reg clk = 0;    always #20 clk = ~clk;                               // 25 MHz
    reg clk125 = 0; initial begin #1.3; forever #4 clk125 = ~clk125; end // 125 MHz, no particular phase to clk

    reg         tx_we = 0;
    reg  [10:0] tx_waddr = 0;
    reg  [7:0]  tx_wdata = 0;
    reg  [10:0] tx_len = 0;
    reg  [15:0] tx_count = 0;
    reg  [11:0] tx_gap = 12;
    reg         tx_start = 0, rx_clear = 0;
    reg  [10:0] rx_raddr = 0;
    wire        tx_busy, rx_captured;
    wire [31:0] tx_frames, rx_frames, rx_good, rx_bad;
    wire [10:0] rx_len;
    wire [7:0]  rx_rdata;
    wire        eth_txc, eth_tx_ctl, eth_rxc, eth_rx_ctl;
    wire [3:0]  eth_txd, eth_rxd;
    reg         phy_rst_n = 1, loopback = 1, link = 0;

    eth_test #(.RX_DELAY(RX_DELAY), .TX_RAM_OUTREG(TX_RAM_OUTREG)) dut (
        .clk(clk), .clk125(clk125),
        .tx_we(tx_we), .tx_waddr(tx_waddr), .tx_wdata(tx_wdata), .tx_len(tx_len), .tx_count(tx_count), .tx_gap(tx_gap),
        .tx_start(tx_start), .tx_busy(tx_busy), .tx_frames(tx_frames),
        .rx_clear(rx_clear), .rx_frames(rx_frames), .rx_good(rx_good), .rx_bad(rx_bad),
        .rx_captured(rx_captured), .rx_len(rx_len), .rx_raddr(rx_raddr), .rx_rdata(rx_rdata),
        .eth_txc(eth_txc), .eth_tx_ctl(eth_tx_ctl), .eth_txd(eth_txd),
        .eth_rxc(eth_rxc), .eth_rx_ctl(eth_rx_ctl), .eth_rxd(eth_rxd));
    rgmii_phy_model #(.PERIOD(PHY_PERIOD)) phy (
        .rst_n(phy_rst_n), .loopback(loopback), .link(link),
        .txc(eth_txc), .tx_ctl(eth_tx_ctl), .txd(eth_txd), .rxc(eth_rxc), .rx_ctl(eth_rx_ctl), .rxd(eth_rxd));

    integer fails = 0, checks = 0;
    task check(input [1199:0] what, input ok); begin
        checks = checks + 1;
        if (ok !== 1'b1) begin fails = fails + 1; $display("FAIL: %0s at %t", what, $time); end
        else $display("  ok: %0s", what);
    end endtask

    // ---- frames ------------------------------------------------------------------------------------
    reg [7:0] txf [0:2047];              // the frame in hand: what was last made, loaded or given to the PHY model
    // The FCS of txf[0..n-1], as the four bytes go on the wire (bits 7:0 first).
    function [31:0] fcs_of(input integer n);
        reg [31:0] r; integer i, b; reg fb;
        begin
            r = 32'hFFFFFFFF;                                    // "the first 32 bits of the frame are complemented"
            for (i = 0; i < n; i = i + 1)
                for (b = 0; b < 8; b = b + 1) begin              // bit 0 of each byte is first on the wire
                    fb = r[31] ^ txf[i][b];
                    r = {r[30:0], 1'b0} ^ (fb ? 32'h04C11DB7 : 32'h0);
                end
            r = ~r;                                              // "the remainder is complemented ...
            for (b = 0; b < 32; b = b + 1) fcs_of[b] = r[31 - b];// ... and sent x^31 first", which is bit 0 of the first FCS byte
        end
    endfunction
    // The same register run over the frame and its FCS, no complement at the end: the standard's residue.
    function [31:0] residue_of(input integer n);
        reg [31:0] r; integer i, b; reg fb;
        begin
            r = 32'hFFFFFFFF;
            for (i = 0; i < n; i = i + 1)
                for (b = 0; b < 8; b = b + 1) begin
                    fb = r[31] ^ txf[i][b];
                    r = {r[30:0], 1'b0} ^ (fb ? 32'h04C11DB7 : 32'h0);
                end
            residue_of = r;
        end
    endfunction
    // len bytes, FCS included: destination (broadcast or 02:00:00:00:00:01), source 02:EC:5B:A2:D2:01, EtherType
    // 0x88B5 (local experimental), a payload that starts 55 D5 (a second "SFD" must not restart anything).
    task make_frame(input integer len, input bcast, input [7:0] seed); integer i; reg [31:0] f; begin
        for (i = 0; i < 6; i = i + 1) txf[i] = bcast ? 8'hFF : (i == 0 ? 8'h02 : i == 5 ? 8'h01 : 8'h00);
        txf[6] = 8'h02; txf[7] = 8'hEC; txf[8] = 8'h5B; txf[9] = 8'hA2; txf[10] = 8'hD2; txf[11] = 8'h01;
        txf[12] = 8'h88; txf[13] = 8'hB5; txf[14] = 8'h55; txf[15] = 8'hD5;
        for (i = 16; i < len - 4; i = i + 1) txf[i] = seed + i * 7 + (i >> 8) * 29;
        f = fcs_of(len - 4);
        txf[len - 4] = f[7:0]; txf[len - 3] = f[15:8]; txf[len - 2] = f[23:16]; txf[len - 1] = f[31:24];
    end endtask

    // ---- the bus -------------------------------------------------------------------------------------
    task load_frame(input integer len); integer i; begin
        for (i = 0; i < len; i = i + 1) begin @(negedge clk); tx_we = 1; tx_waddr = i; tx_wdata = txf[i]; end
        @(negedge clk); tx_we = 0; tx_len = len;
    end endtask
    task send(input integer n, input integer gap); begin
        @(negedge clk); tx_count = n; tx_gap = gap;
        @(negedge clk); tx_start = 1;
        @(negedge clk); tx_start = 0;
    end endtask
    integer waited;
    task wait_tx(input integer max_cycles); begin
        waited = 0;
        while (tx_busy && waited < max_cycles) begin @(negedge clk); waited = waited + 1; end
    end endtask
    task settle; #30_000; endtask                                // three of the receiver's 10 us snapshots
    task clear_rx; begin @(negedge clk); rx_clear = 1; @(negedge clk); rx_clear = 0; end endtask
    // The captured frame against txf, read the fast way: a new address every cycle, the data two cycles behind.
    task compare_capture(input integer len, output integer errs); integer i; begin
        errs = 0;
        for (i = 0; i < len + 2; i = i + 1) begin
            @(negedge clk);
            if (i >= 2 && rx_rdata !== txf[i - 2]) errs = errs + 1;
            rx_raddr = i;
        end
    end endtask
    task give_phy(input integer len); integer i; begin for (i = 0; i < len; i = i + 1) phy.frame[i] = txf[i]; end endtask

    // every clk cycle of the whole run: a snapshot is of one instant, so the three counters agree
    integer incoherent = 0, went_back = 0;
    reg [31:0] last_frames = 0;
    always @(negedge clk) begin
        if (rx_frames !== rx_good + rx_bad) incoherent = incoherent + 1;
        if (rx_frames < last_frames && rx_frames != 0) went_back = went_back + 1;
        last_frames = rx_frames;
    end
    integer bus_changes = 0;
    always @(rx_frames or rx_good or rx_bad or rx_captured or rx_len) bus_changes = bus_changes + 1;
    function integer iddr_viol(input integer dummy);
        iddr_viol = dut.rxpin[0].iddr.viol + dut.rxpin[1].iddr.viol + dut.rxpin[2].iddr.viol + dut.rxpin[3].iddr.viol + dut.rxpin[4].iddr.viol;
    endfunction

    integer errs, k, n, exp_tx, v0;
    reg [31:0] f0, g0, b0;
    reg [7:0]  first_byte;
    integer lens [0:4];
    initial begin
        if ($test$plusargs("vcd")) begin $dumpfile("tb_eth.vcd"); $dumpvars(0, tb_eth); end
        #2000;
        // 0. the testbench's own CRC, on the check string everybody uses
        txf[0] = "1"; txf[1] = "2"; txf[2] = "3"; txf[3] = "4"; txf[4] = "5"; txf[5] = "6"; txf[6] = "7"; txf[7] = "8"; txf[8] = "9";
        check("testbench CRC-32 of \"123456789\" is 0xCBF43926", fcs_of(9) == 32'hCBF43926);

        // 1. one 64-byte broadcast frame, PHY in loopback
        $display("1. one 64-byte broadcast frame in loopback");
        make_frame(64, 1, 8'h11); load_frame(64);
        check("the frame with its FCS leaves the standard's residue 0xC704DD7B in the testbench's register", residue_of(64) == 32'hC704DD7B);
        check("idle before the first start: tx_busy 0, no frames, nothing captured", !tx_busy && tx_frames == 0 && rx_frames == 0 && !rx_captured);
        send(1, 12);
        @(negedge clk); check("tx_busy is up the cycle after tx_start", tx_busy);
        wait_tx(1000); check("tx_busy falls", !tx_busy);
        check("tx_frames = 1 when tx_busy falls", tx_frames == 1);
        settle;
        check("rx_frames = 1, rx_good = 1, rx_bad = 0", rx_frames == 1 && rx_good == 1 && rx_bad == 0);
        check("rx_captured, rx_len = 64", rx_captured && rx_len == 64);
        compare_capture(64, errs); check("the 64 captured bytes are the 64 sent", errs == 0);
        rx_raddr = 0; repeat (3) @(negedge clk);
        rx_raddr = 13; @(negedge clk); first_byte = rx_rdata; @(negedge clk);
        check("rx_rdata is valid two cycles after rx_raddr (one cycle after, it is still the old address's)", rx_rdata === txf[13] && first_byte === txf[0]);
        check("the design's CRC register holds 0xDEBB20E3 after the good frame", dut.rcrc === 32'hDEBB20E3);
        check("on the TX pins: 1 frame, preamble 7 x 55 + D5, 64 bytes, no TX_ER", phy.tx_frames_seen == 1 && phy.tx_pre_bad == 0 && phy.tx_last_len == 64 && phy.tx_er_seen == 0);
        exp_tx = 1;

        // 2. a thousand full-size frames, the least gap
        $display("2. 1000 frames of 1518 bytes, gap 12");
        clear_rx; make_frame(1518, 0, 8'h5A); load_frame(1518);
        send(1000, 12); exp_tx = exp_tx + 1000;
        #1_000_000; check("after 1 ms: still busy, some 80 frames in, none bad", tx_busy && rx_good > 70 && rx_good < 90 && rx_bad == 0);
        wait_tx(400_000); check("tx_busy falls", !tx_busy);
        check("tx_frames = 1001", tx_frames == exp_tx);
        settle;
        check("rx_frames = 1000, rx_good = 1000, rx_bad = 0", rx_frames == 1000 && rx_good == 1000 && rx_bad == 0);
        check("the capture is the first of them: rx_len = 1518", rx_captured && rx_len == 1518);
        compare_capture(1518, errs); check("the 1518 captured bytes are the 1518 sent", errs == 0);
        check("on the TX pins: 1001 frames, every preamble right, the gap never under 12 byte times", phy.tx_frames_seen == exp_tx && phy.tx_pre_bad == 0 && phy.tx_min_gap == 12);
        check("TXD/TX_CTL edges within 0.5 ns of TXC's (edge-aligned at the pins)", phy.tx_skew_viol == 0);
        check("the PHY model's elastic buffer neither ran dry nor over", phy.underruns == 0 && phy.overruns == 0);
        $display("     (the PHY's clock is %0.3f ns: it replayed with gaps down to %0d byte times)", PHY_PERIOD, phy.rx_min_ipg);

        // 6. other lengths: the minimum 60 + 4, an odd one, the longest allowed, a runt, the whole buffer
        $display("6. lengths");
        lens[0] = 64; lens[1] = 101; lens[2] = 1522; lens[3] = 60; lens[4] = 2047;
        for (k = 0; k < 5; k = k + 1) begin
            n = lens[k];
            clear_rx; make_frame(n, k[0], 8'hC3 + k); load_frame(n);
            send(3, 12 + k); exp_tx = exp_tx + 3; wait_tx(20_000); settle;
            compare_capture(n, errs);
            $display("     %0d bytes x 3:", n);
            check("3 good, 0 bad, rx_len and the captured bytes right", !tx_busy && rx_frames == 3 && rx_good == 3 && rx_bad == 0 && rx_captured && rx_len == n && errs == 0);
        end
        check("tx_frames counts them all", tx_frames == exp_tx);
        // tx_count = 0, a start while busy, a long gap
        make_frame(64, 1, 8'h77); load_frame(64); clear_rx;
        send(0, 12); wait_tx(100); #2000;
        check("tx_count = 0: tx_busy falls again, nothing is sent", !tx_busy && tx_frames == exp_tx && phy.tx_frames_seen == exp_tx);
        send(5, 200); #3000;
        @(negedge clk); tx_start = 1; @(negedge clk); tx_start = 0;          // ignored: the engine is busy
        exp_tx = exp_tx + 5; wait_tx(2000); settle;
        check("a tx_start while busy is ignored: 5 frames, not 10", tx_frames == exp_tx && rx_good == 5 && rx_frames == 5);
        v0 = iddr_viol(0);
        check("the input DDR cells never sampled within 0.52 ns of a data edge", v0 == 0);

        // 7. idle time: the two clocks slip a byte every 64 us, and a frame after any wait must still be good
        $display("7. a long idle");
        make_frame(64, 1, 8'h31); load_frame(64); clear_rx;
        #2_000_000;
        send(1, 12); exp_tx = exp_tx + 1; wait_tx(1000); settle;
        compare_capture(64, errs);
        check("one frame after 2 ms of idle in loopback is good, and captured right", rx_frames == 1 && rx_good == 1 && rx_bad == 0 && rx_captured && rx_len == 64 && errs == 0);
        @(negedge clk); loopback = 0; #20_000; loopback = 1;                 // as a driver does: loopback set, a settling wait, then the frame
        #1_000_000; clear_rx; #16_000;
        send(1, 12); exp_tx = exp_tx + 1; wait_tx(1000); settle;
        compare_capture(64, errs);
        check("loopback switched off and on, 1 ms of idle, one frame: good, and captured right", rx_frames == 1 && rx_good == 1 && rx_bad == 0 && rx_captured && rx_len == 64 && errs == 0);
        for (k = 0; k < 16; k = k + 1) begin                                 // 16 waits a sixteenth of a slip apart: every phase of one clock against the other
            #(250_000 + k * 4_000); send(1, 12); exp_tx = exp_tx + 1; wait_tx(1000);
        end
        settle;
        check("16 more single frames, 250 to 310 us apart: all good", rx_frames == 17 && rx_good == 17 && rx_bad == 0);

        // 3. frames from the wire: good, one bit flipped, RX_ER, a short preamble
        $display("3. frames injected by the PHY model (loopback off, link up)");
        @(negedge clk); loopback = 0; link = 1; #1000;
        clear_rx; settle;
        make_frame(300, 0, 8'h21); give_phy(300);
        phy.send_frame(300, 1'b0); settle;
        check("a good frame from the wire: rx_good = 1", rx_frames == 1 && rx_good == 1 && rx_bad == 0);
        phy.send_frame(300, 1'b1); settle;
        check("one bit flipped in mid-frame: rx_bad = 1, rx_good still 1", rx_frames == 2 && rx_good == 1 && rx_bad == 1);
        phy.rx_er_mid = 1; phy.send_frame(300, 1'b0); settle;
        check("RX_ER for one byte of a frame with a good CRC: rx_bad = 2", rx_frames == 3 && rx_good == 1 && rx_bad == 2);
        phy.flip_byte = 0;   phy.flip_bit = 7; phy.send_frame(300, 1'b1);
        phy.flip_byte = 299; phy.flip_bit = 7; phy.send_frame(300, 1'b1);
        phy.flip_byte = 296; phy.flip_bit = 0; phy.send_frame(300, 1'b1);
        phy.flip_byte = 295; phy.flip_bit = 3; phy.send_frame(300, 1'b1);
        phy.flip_byte = -1;  phy.flip_bit = 0; settle;
        check("a flipped bit in the first byte, the last payload byte, the FCS's first and last: 4 more bad", rx_frames == 7 && rx_good == 1 && rx_bad == 6);
        phy.preamble = 3; phy.send_frame(300, 1'b0); phy.preamble = 7; settle;
        check("a preamble of only 3 bytes: still good", rx_frames == 8 && rx_good == 2 && rx_bad == 6);
        phy.send_frame(299, 1'b0); settle;
        check("the frame cut one byte short: bad", rx_frames == 9 && rx_good == 2 && rx_bad == 7);
        check("the capture is still the first frame after the clear", rx_captured && rx_len == 300);
        compare_capture(300, errs); check("and its 300 bytes are right", errs == 0);
        f0 = rx_frames; make_frame(64, 1, 8'h77); load_frame(64);
        send(4, 12); exp_tx = exp_tx + 4; wait_tx(1000); settle;
        check("loopback off: the FPGA's frames go to the wire (4 more on the TX pins), none comes back", phy.tx_frames_seen == exp_tx && rx_frames == f0);

        // 4. rx_clear
        $display("4. rx_clear");
        clear_rx; @(negedge clk);
        check("the cycle after rx_clear: counters 0, rx_captured 0", rx_frames == 0 && rx_good == 0 && rx_bad == 0 && !rx_captured && rx_len == 0);
        settle;
        check("and they stay 0 (no old snapshot comes back)", rx_frames == 0 && rx_good == 0 && rx_bad == 0 && !rx_captured);
        make_frame(200, 1, 8'h99); give_phy(200); phy.send_frame(200, 1'b0);
        make_frame(120, 0, 8'h3C); give_phy(120); phy.send_frame(120, 1'b0); phy.send_frame(120, 1'b1); settle;
        check("three frames after the clear: 3 seen, 2 good, 1 bad", rx_frames == 3 && rx_good == 2 && rx_bad == 1);
        make_frame(200, 1, 8'h99); compare_capture(200, errs);
        check("the capture was re-armed: it is the first of the three (200 bytes), not the old one", rx_captured && rx_len == 200 && errs == 0);

        // 4b. what is captured when the first burst after a clear is a bad one
        clear_rx; settle;
        make_frame(300, 0, 8'h66); give_phy(300);
        phy.flip_byte = 150; phy.flip_bit = 5; phy.send_frame(300, 1'b1); phy.flip_byte = -1; phy.flip_bit = 0;
        phy.send_frame(300, 1'b0); settle;
        txf[150] = txf[150] ^ 8'h20; compare_capture(300, errs);
        check("a frame with a wrong CRC is captured too, as it arrived (the flipped bit is in the copy)", rx_frames == 2 && rx_good == 1 && rx_bad == 1 && rx_captured && rx_len == 300 && errs == 0);
        clear_rx; settle;
        for (k = 0; k < 40; k = k + 1) txf[k] = 8'h10 + k;                   // 40 bytes with no 0xD5 among them
        give_phy(40); phy.sfd_byte = 8'h55; phy.send_frame(40, 1'b0); phy.sfd_byte = 8'hD5; settle;
        for (k = 47; k >= 8; k = k - 1) txf[k] = txf[k - 8];                 // what the pins carried: 8 x 0x55, then the 40
        for (k = 0; k < 8; k = k + 1) txf[k] = 8'h55;
        compare_capture(48, errs);
        check("a burst with no SFD: bad, and captured whole from its first byte (8 x 55, then the 40 bytes)", rx_frames == 1 && rx_good == 0 && rx_bad == 1 && rx_captured && rx_len == 48 && errs == 0);

        // 5. RXC stopped (the PHY in reset), then slow, then back
        $display("5. the PHY's clock stopped");
        @(negedge clk); loopback = 1; link = 0; #1000;
        clear_rx; make_frame(64, 1, 8'h42); load_frame(64);
        send(2, 12); exp_tx = exp_tx + 2; wait_tx(1000); settle;
        check("before: 2 frames looped back and counted", rx_frames == 2 && rx_good == 2 && rx_captured);
        check("the input DDR cells still never sampled within 0.52 ns of a data edge", iddr_viol(0) == 0);
        phy_rst_n = 0; #50_000;
        f0 = rx_frames; g0 = rx_good; b0 = rx_bad; bus_changes = 0;
        #200_000;
        check("RXC stopped for 200 us: the receive outputs hold their values", bus_changes == 0 && rx_frames == f0 && rx_good == g0 && rx_bad == b0 && rx_captured);
        send(5, 12); exp_tx = exp_tx + 5; wait_tx(1000);
        check("the transmitter does not need RXC: 5 frames sent, tx_busy falls", !tx_busy && tx_frames == exp_tx);
        compare_capture(64, errs); check("the captured frame can still be read", errs == 0);
        clear_rx; @(negedge clk);
        check("rx_clear with RXC stopped: the outputs go to 0 all the same", rx_frames == 0 && rx_good == 0 && rx_bad == 0 && !rx_captured);
        clear_rx; #100_000;
        check("and stay 0 (a second clear on top changes nothing)", rx_frames == 0 && rx_good == 0 && rx_bad == 0 && !rx_captured);
        send(1, 12); exp_tx = exp_tx + 1; wait_tx(1000);
        check("the bus side is alive: another frame sent", !tx_busy && tx_frames == exp_tx);
        phy.rxc_div = 50; phy_rst_n = 1; #200_000;
        check("RXC back at 2.5 MHz (no gigabit link): the clear is done, the old counts do not come back", rx_frames == 0 && rx_good == 0 && rx_bad == 0 && !rx_captured && dut.r_frames == 0);
        phy.rxc_div = 1; #50_000;
        make_frame(101, 0, 8'h24); load_frame(101);
        send(2, 12); exp_tx = exp_tx + 2; wait_tx(1000); settle;
        compare_capture(101, errs);
        check("RXC back at 125 MHz: 2 frames, 2 good, the capture re-armed by the clear given without a clock", rx_frames == 2 && rx_good == 2 && rx_bad == 0 && rx_captured && rx_len == 101 && errs == 0);

        // the whole run
        check("at every clk edge of the run rx_frames = rx_good + rx_bad, and no count ever went back but to 0", incoherent == 0 && went_back == 0);
        check("TX pins over the whole run: every preamble right, never a TX_ER, never an edge off TXC", phy.tx_pre_bad == 0 && phy.tx_er_seen == 0 && phy.tx_skew_viol == 0 && phy.tx_frames_seen == exp_tx - 6);
        check("the PHY model dropped nothing it was asked to play", phy.inj_dropped == 0 && phy.underruns == 0 && phy.overruns == 0);
        $display("%0d checks, %0d failures: %s", checks, fails, fails == 0 ? "PASS" : "FAIL");
        $finish;
    end
    initial begin #200_000_000; $display("TIMEOUT"); $display("%0d checks, %0d failures: FAIL", checks, fails + 1); $finish; end
endmodule
