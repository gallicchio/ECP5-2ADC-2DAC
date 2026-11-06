// ECP5-2ADC-2DAC rev A bring-up gateware: every block of the board reachable from the PC over the
// FT2232H's serial channel (1 Mbaud), with nothing between the PC and a register but a UART.
// Port names are the generated LPF's (gateware/ecp5_2adc_2dac.lpf); the ports this design does not
// use (HDMI, microSD, flash, RGMII data) are left out, and nextpnr is run with --lpf-allow-unconstrained.
//
// Clocks: the 25 MHz TCXO runs the UART, the registers, the LEDs and the frequency counters' gate;
// a PLL makes clk_s = 50 MHz for the converters and the SDRAM.  The five other clock inputs (CLK IN,
// the three Si5351 outputs, the PHY's RXC) each only feed a frequency counter.
//
// Register map (32-bit registers, 7-bit addresses; host/ecp5bu.py has the same table):
//   00 ID        ro  0xEC5BA2D2
//   01 VERSION   ro  BUILD_ID
//   02 SCRATCH   rw
//   03 CONTROL   rw  [0] LED mode 1 = register (0 = chaser); [1] clk_out enable (default 1)
//   04 STATUS    ro  [0] pll_lock [1] BTN0 pressed [2] BTN1 pressed [3] eth_int_n [4] ftdi_rts [5] ftdi_dtr
//                    [6] adc_a_otr [7] adc_b_otr [8] i2c_sda [9] i2c_scl [10] eth_mdio [11] uart activity
//   05 LEDS      rw  [7:0] LED0-7 (1 = on, in register mode) [8] R [9] G [10] B (1 = on)
//   06 GPIO      rw  [0] eth_rst_n (1) [1] eth_mdc (0) [2] eth_mdio out (1) [3] eth_mdio drive (0)
//                    [4] i2c_scl (1 = released) [5] i2c_sda (1 = released) [6] adc_pdwn_a (0) [7] adc_pdwn_b (0)
//                    [8] adc_dcs (1) [9] adc_dfs (0) [10] dac_mode (1 = dual port) [11] dac_sleep (0)
//                    [12] usb_pullup (0)
//   07 PMOD      rw  [7:0] PMOD A out [15:8] PMOD B out [17:16] A mode [19:18] B mode
//                    (mode 0 inputs, 1 register, 2 counter); reads give [7:0] A pins [15:8] B pins
//   08 CLKOUT    rw  what CLK OUT shows: 0 TCXO 1 clk_s 2 ADC clock 3 DAC1 clock 4 CLK IN 5-7 Si5351 CLK0-2
//                    8 PHY RXC 9 the 1 Hz gate 10 low 11 high 12 TCXO/2 13 PLL lock
//   10-16 FREQ   ro  Hz, one gate (1 s) old: TCXO (25000000 by construction), CLK IN, Si CLK0, CLK1, CLK2, RXC, clk_s
//   17 FREQSEQ   ro  the seven counters' sequence numbers, 4 bits each (bits 3:0 TCXO ... 27:24 clk_s)
//   20 ADC_CTRL  rw  [0] arm (write 1) [6:4] capture phase [8] capture on the falling edge [20:16] stats window log2
//   21 ADC_DIV   rw  ADC clock half period in clk_s cycles (0 = clk_s itself: 50 MS/s; 1 = 25 MS/s)
//   22 ADC_DECIM rw  store every (n+1)th sample
//   23 ADC_LEN   rw  samples to capture, <= 8192
//   24 ADC_STAT  ro  [0] busy [1] done [29:16] samples captured
//   25 STATSEQ   ro  statistics sequence number
//   26 A_MINMAX  ro  [11:0] min [27:16] max       27 A_SUM ro       28 B_MINMAX ro      29 B_SUM ro
//   2A OTR_N     ro  [15:0] A out-of-range samples in the window [31:16] B
//   30 DAC1_CTRL rw  [2:0] mode (0 DC 1 sine 2 sawtooth 3 square 4 triangle) [7:4] amplitude shift
//   31 DAC1_INC  rw  phase increment per sample (f = inc * f_dac / 2^32)
//   32 DAC1_DC   rw  signed 16-bit: the DC code in mode 0, else an offset in codes
//   33-35        rw  DAC2 the same
//   36 DAC_DIV   rw  [15:0] DAC clock half period (0 = 50 MS/s) [16] clock polarity (default 1 in direct mode)
//   40 SDRAM_CTRL rw [0] start (write 1) [1] abort [7:4] pattern [11:8] read latency [12] SDRAM clock polarity
//   41 SDRAM_LEN rw  words to test (1 .. 16777216)
//   42 SDRAM_STAT ro [0] init_done [1] busy [2] done
//   43 SDRAM_ERR ro  mismatches     44 first error's address     45 {expected, got}     46 words done
//   7E DUMP_LEN  rw  words a read of 7F streams
//   7F DUMP      ro  the capture memory from word 0: {4'b0, b_otr, 3'b0, b[11:0] | 4'b0, a_otr, 3'b0, a[11:0]}
`default_nettype none

module top #(parameter BUILD_ID = 32'h20261105, UART_DIV = 25, GATE_CYCLES = 25_000_000) (
    input  wire        clk_tcxo, clk_ext, clk_si0, clk_si1, clk_si2,
    output wire        clk_out,
    input  wire        btn0, btn1,
    output wire        led0, led1, led2, led3, led4, led5, led6, led7,
    output wire        led_r, led_g, led_b,
    input  wire        uart_rx, output wire uart_tx,
    input  wire        ftdi_rts, ftdi_dtr,
    // ADC
    input  wire [11:0] adc_a_d, adc_b_d,
    input  wire        adc_a_otr, adc_b_otr,
    output wire        adc_a_clk, adc_b_clk, adc_dcs, adc_dfs, adc_pdwn_a, adc_pdwn_b,
    // DAC
    output wire [13:0] dac_p1_d, dac_p2_d,
    output wire        dac_clk1, dac_clk2, dac_wrt1, dac_wrt2, dac_mode, dac_sleep,
    // SDRAM
    output wire [12:0] sdram_a, output wire [1:0] sdram_ba, inout wire [15:0] sdram_dq,
    output wire        sdram_clk, sdram_cke, sdram_cs_n, sdram_ras_n, sdram_cas_n, sdram_we_n, sdram_dqml, sdram_dqmh,
    // Ethernet: the clock, the management bus, reset
    input  wire        eth_rxc, eth_int_n,
    output wire        eth_mdc, eth_rst_n,
    inout  wire        eth_mdio,
    // USB USER: left idle
    output wire        usb_pullup,
    // Si5351
    inout  wire        i2c_scl, i2c_sda,
    // Pmods
    inout  wire [7:0]  pmoda, pmodb
);
    // ---- clocks ------------------------------------------------------------------------------------
    wire clk = clk_tcxo;
    wire clk_s, pll_lock;
    pll_sys pll (.clkin(clk_tcxo), .clkout0(clk_s), .locked(pll_lock));

    // ---- UART and the register bus ------------------------------------------------------------------
    wire [7:0] rx_data; wire rx_valid;
    wire [7:0] tx_data; wire tx_start, tx_busy;
    uart_rx #(.DIV(UART_DIV)) urx (.clk(clk), .rx(uart_rx), .data(rx_data), .valid(rx_valid));
    uart_tx #(.DIV(UART_DIV)) utx (.clk(clk), .data(tx_data), .start(tx_start), .busy(tx_busy), .tx(uart_tx));
    wire [6:0]  addr; wire [31:0] wdata; wire we; reg [31:0] rdata = 0;
    wire [15:0] dump_addr; reg [31:0] dump_data = 0; wire bus_active;
    reg  [15:0] dump_len = 0;
    regbus bus (.clk(clk), .rx_data(rx_data), .rx_valid(rx_valid), .tx_data(tx_data), .tx_start(tx_start), .tx_busy(tx_busy),
                .addr(addr), .wdata(wdata), .we(we), .rdata(rdata), .dump_len(dump_len), .dump_addr(dump_addr), .dump_data(dump_data),
                .active(bus_active));

    // ---- the one-second gate, the frequency counters -------------------------------------------------
    reg [24:0] gate_cnt = 0;
    reg gate = 0, sec = 0;
    always @(posedge clk) begin
        gate <= 1'b0;
        if (gate_cnt == GATE_CYCLES - 1) begin gate_cnt <= 0; gate <= 1'b1; sec <= ~sec; end
        else gate_cnt <= gate_cnt + 1'b1;
    end
    wire [31:0] f_tcxo, f_ext, f_si0, f_si1, f_si2, f_rxc, f_s;
    wire [15:0] q_tcxo, q_ext, q_si0, q_si1, q_si2, q_rxc, q_s;
    clkcount c0 (.clk_ref(clk), .gate(gate), .clk_x(clk_tcxo), .freq(f_tcxo), .seq(q_tcxo));
    clkcount c1 (.clk_ref(clk), .gate(gate), .clk_x(clk_ext),  .freq(f_ext),  .seq(q_ext));
    clkcount c2 (.clk_ref(clk), .gate(gate), .clk_x(clk_si0),  .freq(f_si0),  .seq(q_si0));
    clkcount c3 (.clk_ref(clk), .gate(gate), .clk_x(clk_si1),  .freq(f_si1),  .seq(q_si1));
    clkcount c4 (.clk_ref(clk), .gate(gate), .clk_x(clk_si2),  .freq(f_si2),  .seq(q_si2));
    clkcount c5 (.clk_ref(clk), .gate(gate), .clk_x(eth_rxc),  .freq(f_rxc),  .seq(q_rxc));
    clkcount c6 (.clk_ref(clk), .gate(gate), .clk_x(clk_s),    .freq(f_s),    .seq(q_s));

    // ---- registers --------------------------------------------------------------------------------
    reg [31:0] scratch = 0;
    reg [1:0]  control = 2'b10;
    reg [10:0] leds_r = 0;
    reg [12:0] gpio = 13'b0_0101_0011_0101;      // dac_mode, adc_dcs, i2c released, mdio out 1, eth_rst_n 1
    reg [19:0] pmod_r = 0;
    reg [3:0]  clkout_sel = 0;
    reg [2:0]  adc_phase = 3'd2; reg adc_neg = 0; reg [4:0] stats_log2 = 5'd16;
    reg [15:0] adc_div = 16'd1, adc_decim = 0;
    reg [13:0] adc_len = 14'd8192;
    reg [2:0]  dac1_mode = 3'd1, dac2_mode = 3'd1; reg [3:0] dac1_shift = 0, dac2_shift = 0;
    reg [31:0] dac1_inc = 32'd85899346, dac2_inc = 32'd171798692;      // 1 and 2 MHz at 50 MS/s
    reg [15:0] dac1_dc = 0, dac2_dc = 0;
    reg [15:0] dac_div = 0; reg dac_pol = 1'b1;
    reg        sd_abort = 0; reg [3:0] sd_pattern = 0, sd_rdlat = 4'd3; reg sd_pol = 0;
    reg [24:0] sd_len = 25'd4096;
    wire adc_arm_w = we && addr == 7'h20 && wdata[0];
    wire sd_start_w = we && addr == 7'h40 && wdata[0];

    always @(posedge clk) if (we) case (addr)
        7'h02: scratch <= wdata;
        7'h03: control <= wdata[1:0];
        7'h05: leds_r <= wdata[10:0];
        7'h06: gpio <= wdata[12:0];
        7'h07: pmod_r <= wdata[19:0];
        7'h08: clkout_sel <= wdata[3:0];
        7'h20: begin adc_phase <= wdata[6:4]; adc_neg <= wdata[8]; stats_log2 <= wdata[20:16]; end
        7'h21: adc_div <= wdata[15:0];
        7'h22: adc_decim <= wdata[15:0];
        7'h23: adc_len <= wdata[13:0];
        7'h30: begin dac1_mode <= wdata[2:0]; dac1_shift <= wdata[7:4]; end
        7'h31: dac1_inc <= wdata;
        7'h32: dac1_dc <= wdata[15:0];
        7'h33: begin dac2_mode <= wdata[2:0]; dac2_shift <= wdata[7:4]; end
        7'h34: dac2_inc <= wdata;
        7'h35: dac2_dc <= wdata[15:0];
        7'h36: begin dac_div <= wdata[15:0]; dac_pol <= wdata[16]; end
        7'h40: begin sd_abort <= wdata[1]; sd_pattern <= wdata[7:4]; sd_rdlat <= wdata[11:8]; sd_pol <= wdata[12]; end
        7'h41: sd_len <= wdata[24:0];
        7'h7e: dump_len <= wdata[15:0];
        default: ;
    endcase

    // the status inputs
    wire [1:0] btn_s; sync_bit sb0 (.clk_b(clk), .d(~btn0), .q(btn_s[0])); sync_bit sb1 (.clk_b(clk), .d(~btn1), .q(btn_s[1]));
    reg [23:0] act_stretch = 0;
    always @(posedge clk) if (bus_active) act_stretch <= 24'hffffff; else if (act_stretch != 0) act_stretch <= act_stretch - 1'b1;
    wire act = act_stretch != 0;

    // the converter and memory engines (declared here, instantiated below)
    wire adc_busy, adc_done; wire [13:0] adc_count; wire [15:0] stat_seq;
    wire [11:0] a_min, a_max, b_min, b_max; wire [31:0] a_sum, b_sum; wire [15:0] a_otr_n, b_otr_n;
    wire sd_init, sd_busy, sd_done; wire [31:0] sd_err, sd_ferr_a, sd_ferr_d; wire [24:0] sd_words;

    always @(*) case (addr)
        7'h00: rdata = 32'hEC5BA2D2;
        7'h01: rdata = BUILD_ID;
        7'h02: rdata = scratch;
        7'h03: rdata = {30'b0, control};
        7'h04: rdata = {20'b0, act, eth_mdio, i2c_scl, i2c_sda, adc_b_otr, adc_a_otr, ftdi_dtr, ftdi_rts, eth_int_n, btn_s[1], btn_s[0], pll_lock};
        7'h05: rdata = {21'b0, leds_r};
        7'h06: rdata = {19'b0, gpio};
        7'h07: rdata = {12'b0, pmod_r[19:16], pmodb, pmoda};
        7'h08: rdata = {28'b0, clkout_sel};
        7'h10: rdata = f_tcxo;  7'h11: rdata = f_ext;  7'h12: rdata = f_si0;  7'h13: rdata = f_si1;
        7'h14: rdata = f_si2;   7'h15: rdata = f_rxc;  7'h16: rdata = f_s;
        7'h17: rdata = {4'b0, q_s[3:0], q_rxc[3:0], q_si2[3:0], q_si1[3:0], q_si0[3:0], q_ext[3:0], q_tcxo[3:0]};
        7'h20: rdata = {11'b0, stats_log2, 7'b0, adc_neg, 1'b0, adc_phase, 4'b0};
        7'h21: rdata = {16'b0, adc_div};
        7'h22: rdata = {16'b0, adc_decim};
        7'h23: rdata = {18'b0, adc_len};
        7'h24: rdata = {2'b0, adc_count, 14'b0, adc_done, adc_busy};
        7'h25: rdata = {16'b0, stat_seq};
        7'h26: rdata = {4'b0, a_max, 4'b0, a_min};
        7'h27: rdata = a_sum;
        7'h28: rdata = {4'b0, b_max, 4'b0, b_min};
        7'h29: rdata = b_sum;
        7'h2a: rdata = {b_otr_n, a_otr_n};
        7'h30: rdata = {24'b0, dac1_shift, 1'b0, dac1_mode};
        7'h31: rdata = dac1_inc;
        7'h32: rdata = {16'b0, dac1_dc};
        7'h33: rdata = {24'b0, dac2_shift, 1'b0, dac2_mode};
        7'h34: rdata = dac2_inc;
        7'h35: rdata = {16'b0, dac2_dc};
        7'h36: rdata = {15'b0, dac_pol, dac_div};
        7'h40: rdata = {19'b0, sd_pol, sd_rdlat, sd_pattern, 2'b0, sd_abort, 1'b0};
        7'h41: rdata = {7'b0, sd_len};
        7'h42: rdata = {29'b0, sd_done, sd_busy, sd_init};
        7'h43: rdata = sd_err;
        7'h44: rdata = sd_ferr_a;
        7'h45: rdata = sd_ferr_d;
        7'h46: rdata = {7'b0, sd_words};
        7'h7e: rdata = {16'b0, dump_len};
        default: rdata = 32'hDEAD0000 | {25'b0, addr};
    endcase

    // ---- LEDs ---------------------------------------------------------------------------------------
    reg [26:0] chase = 0;
    always @(posedge clk) chase <= chase + 1'b1;
    wire [7:0] chaser = 8'b1 << chase[26:24];
    wire [7:0] leds = control[0] ? leds_r[7:0] : (btn_s[1] ? 8'hff : chaser);
    assign {led7, led6, led5, led4, led3, led2, led1, led0} = leds;
    // RGB, common anode: 0 lights.  Register mode: the register.  Chaser mode: green blinks when
    // the PLL is locked, red when it is not, blue on bus activity.
    assign led_r = control[0] ? ~leds_r[8]  : pll_lock;
    assign led_g = control[0] ? ~leds_r[9]  : ~(pll_lock & sec);
    assign led_b = control[0] ? ~leds_r[10] : ~act;

    // ---- GPIO: the PHY's management bus, the Si5351's I2C, the converters' static pins ----------------
    assign eth_rst_n = gpio[0];
    assign eth_mdc   = gpio[1];
    assign eth_mdio  = gpio[3] ? gpio[2] : 1'bz;
    assign i2c_scl   = gpio[4] ? 1'bz : 1'b0;
    assign i2c_sda   = gpio[5] ? 1'bz : 1'b0;
    assign adc_pdwn_a = gpio[6];
    assign adc_pdwn_b = gpio[7];
    assign adc_dcs    = gpio[8];
    assign adc_dfs    = gpio[9];
    assign dac_mode   = gpio[10];
    assign dac_sleep  = gpio[11];
    assign usb_pullup = gpio[12];

    // Pmods: inputs, a register, or a counter (bit n toggles at 25 MHz / 2^(n+1): 12.5 MHz down to 98 kHz)
    assign pmoda = pmod_r[17:16] == 2'd1 ? pmod_r[7:0]  : pmod_r[17:16] == 2'd2 ? chase[7:0] : 8'bz;
    assign pmodb = pmod_r[19:18] == 2'd1 ? pmod_r[15:8] : pmod_r[19:18] == 2'd2 ? chase[7:0] : 8'bz;

    // ---- the converters and the capture memory (clk_s) ----------------------------------------------
    wire adc_arm; sync_pulse sp_arm (.clk_a(clk), .pulse_a(adc_arm_w), .clk_b(clk_s), .pulse_b(adc_arm));
    wire adc_clk_d0, adc_clk_d1;
    wire [12:0] mem_waddr; wire [31:0] mem_wdata; wire mem_we;
    adc_capture #(.AW(13)) adc (
        .clk_s(clk_s), .a_d(adc_a_d), .b_d(adc_b_d), .a_otr(adc_a_otr), .b_otr(adc_b_otr),
        .clk_d0(adc_clk_d0), .clk_d1(adc_clk_d1),
        .div(adc_div), .phase(adc_phase), .negedge_cap(adc_neg), .decim(adc_decim), .len(adc_len), .arm(adc_arm),
        .stats_log2(stats_log2),
        .mem_waddr(mem_waddr), .mem_wdata(mem_wdata), .mem_we(mem_we),
        .busy(adc_busy), .done(adc_done), .count(adc_count), .stat_seq(stat_seq),
        .a_min(a_min), .a_max(a_max), .a_sum(a_sum), .b_min(b_min), .b_max(b_max), .b_sum(b_sum), .a_otr_n(a_otr_n), .b_otr_n(b_otr_n));
    ODDRX1F oddr_adc_a (.SCLK(clk_s), .RST(1'b0), .D0(adc_clk_d0), .D1(adc_clk_d1), .Q(adc_a_clk));
    ODDRX1F oddr_adc_b (.SCLK(clk_s), .RST(1'b0), .D0(adc_clk_d0), .D1(adc_clk_d1), .Q(adc_b_clk));

    reg [31:0] mem [0:8191];
    always @(posedge clk_s) if (mem_we) mem[mem_waddr] <= mem_wdata;
    reg [31:0] mem_rd = 0;
    always @(posedge clk) begin mem_rd <= mem[dump_addr[12:0]]; dump_data <= mem_rd; end

    wire dac1_d0, dac1_d1, dac1_fab, dac2_d0, dac2_d1, dac2_fab;
    dac_gen dac1 (.clk_s(clk_s), .div(dac_div), .pol(dac_pol), .mode(dac1_mode), .shift(dac1_shift), .inc(dac1_inc), .dc(dac1_dc),
                  .data(dac_p1_d), .clk_d0(dac1_d0), .clk_d1(dac1_d1), .clk_fab(dac1_fab));
    dac_gen dac2 (.clk_s(clk_s), .div(dac_div), .pol(dac_pol), .mode(dac2_mode), .shift(dac2_shift), .inc(dac2_inc), .dc(dac2_dc),
                  .data(dac_p2_d), .clk_d0(dac2_d0), .clk_d1(dac2_d1), .clk_fab(dac2_fab));
    ODDRX1F oddr_dac1c (.SCLK(clk_s), .RST(1'b0), .D0(dac1_d0), .D1(dac1_d1), .Q(dac_clk1));
    ODDRX1F oddr_dac1w (.SCLK(clk_s), .RST(1'b0), .D0(dac1_d0), .D1(dac1_d1), .Q(dac_wrt1));
    // DAC 2's clock pins (M9, P8) are in bank 8, the bottom side, whose SIOLOGIC has no DDR output register
    // (ecppack: "no word named IOLOGICA.DELAY.DEL_VALUE"): the clock goes out through the fabric instead.
    assign dac_clk2 = dac2_fab;
    assign dac_wrt2 = dac2_fab;

    // ---- the SDRAM tester (clk_s) -------------------------------------------------------------------
    wire sd_start; sync_pulse sp_sd (.clk_a(clk), .pulse_a(sd_start_w), .clk_b(clk_s), .pulse_b(sd_start));
    wire [15:0] dq_out; wire dq_oe; wire dqm;
    reg  [15:0] dq_in = 0;
    always @(posedge clk_s) dq_in <= sdram_dq;
    assign sdram_dq = dq_oe ? dq_out : 16'bz;
    assign sdram_dqml = dqm; assign sdram_dqmh = dqm;
    sdram_test sdt (.clk_s(clk_s), .a(sdram_a), .ba(sdram_ba), .cs_n(sdram_cs_n), .ras_n(sdram_ras_n), .cas_n(sdram_cas_n), .we_n(sdram_we_n),
                    .cke(sdram_cke), .dqm(dqm), .dq_out(dq_out), .dq_oe(dq_oe), .dq_in(dq_in),
                    .start(sd_start), .abort(sd_abort), .pattern(sd_pattern), .rdlat(sd_rdlat), .len(sd_len),
                    .init_done(sd_init), .busy(sd_busy), .done(sd_done), .errors(sd_err), .first_err_addr(sd_ferr_a), .first_err_data(sd_ferr_d), .words_done(sd_words));
    ODDRX1F oddr_sdclk (.SCLK(clk_s), .RST(1'b0), .D0(~sd_pol), .D1(sd_pol), .Q(sdram_clk));

    // ---- CLK OUT: any clock, chosen by register ------------------------------------------------------
    reg tcxo_half = 0; always @(posedge clk) tcxo_half <= ~tcxo_half;
    wire adc_clk_mon = adc_div == 0 ? clk_s : adc_clk_d0;
    wire dac_clk_mon = dac_div == 0 ? (clk_s ^ dac_pol) : dac1_d0;
    reg clk_out_r;
    always @(*) case (clkout_sel)
        4'd0: clk_out_r = clk_tcxo;   4'd1: clk_out_r = clk_s;      4'd2: clk_out_r = adc_clk_mon;  4'd3: clk_out_r = dac_clk_mon;
        4'd4: clk_out_r = clk_ext;    4'd5: clk_out_r = clk_si0;    4'd6: clk_out_r = clk_si1;      4'd7: clk_out_r = clk_si2;
        4'd8: clk_out_r = eth_rxc;    4'd9: clk_out_r = sec;        4'd10: clk_out_r = 1'b0;        4'd11: clk_out_r = 1'b1;
        4'd12: clk_out_r = tcxo_half; 4'd13: clk_out_r = pll_lock;  default: clk_out_r = 1'b0;
    endcase
    assign clk_out = control[1] ? clk_out_r : 1'b0;
endmodule
`default_nettype wire
