// Pin-plan proof: every ball in the generated LPF is used, every clock input
// clocks a counter (so nextpnr must put it on a PCLK and build a clock tree),
// and the DAC ports play back a ramp while the ADC ports are sampled -- the
// skeleton of every experiment on this board.  GENERATED port list: see
// gen/lpf.py; this file is kept in step with it by gateware/test/build.sh.
module pins (
    input  wire clk_tcxo, input wire clk_ext, input wire clk_si0, input wire clk_si1, input wire clk_si2,
    output wire clk_out,
    input  wire btn0, input wire btn1,
    output wire [3:0] leds_dummy,          // unused: the real LEDs are below
    output wire led0, output wire led1, output wire led2, output wire led3,
    input  wire ftdi_rts, input wire ftdi_dtr,
    input  wire uart_rx, output wire uart_tx,
    // ADC
    input  wire [11:0] adc_a_d, input wire [11:0] adc_b_d, input wire adc_a_otr, input wire adc_b_otr,
    output wire adc_a_clk, output wire adc_b_clk, output wire adc_dcs, output wire adc_dfs, output wire adc_pdwn_a, output wire adc_pdwn_b,
    // DAC
    output wire [13:0] dac_p1_d, output wire [13:0] dac_p2_d, output wire dac_clk1, output wire dac_clk2, output wire dac_wrt1, output wire dac_wrt2,
    output wire dac_mode, output wire dac_sleep,
    // SDRAM
    output wire [12:0] sdram_a, output wire [1:0] sdram_ba, inout wire [15:0] sdram_dq, output wire sdram_clk, output wire sdram_cke,
    output wire sdram_cs_n, output wire sdram_ras_n, output wire sdram_cas_n, output wire sdram_we_n, output wire sdram_dqml, output wire sdram_dqmh,
    // Ethernet RGMII
    input  wire eth_rxc, input wire eth_rx_ctl, input wire [3:0] eth_rxd, output wire eth_txc, output wire eth_tx_ctl, output wire [3:0] eth_txd,
    output wire eth_mdc, inout wire eth_mdio, output wire eth_rst_n, input wire eth_int_n,
    // GPDI
    output wire gpdi_ck_p, output wire gpdi_ck_n, output wire gpdi_d0_p, output wire gpdi_d0_n, output wire gpdi_d1_p, output wire gpdi_d1_n,
    output wire gpdi_d2_p, output wire gpdi_d2_n, input wire gpdi_hpd, inout wire gpdi_cec, inout wire gpdi_scl, inout wire gpdi_sda,
    // SD, USB, I2C, Pmods
    output wire sd_clk, inout wire sd_cmd, inout wire [3:0] sd_d,
    inout  wire usb_dp, inout wire usb_dn, output wire usb_pullup,
    inout  wire i2c_scl, inout wire i2c_sda,
    inout  wire [7:0] pmoda, inout wire [7:0] pmodb,
    // flash (the data lines; SCK goes through USRMCLK)
    output wire flash_cs_n, inout wire [3:0] flash_io
);
    // ---- every clock input drives its own counter: the proof they are clocks ----
    reg [25:0] c_tcxo = 0, c_ext = 0, c_si0 = 0, c_si1 = 0, c_si2 = 0, c_rxc = 0;
    always @(posedge clk_tcxo) c_tcxo <= c_tcxo + 1;
    always @(posedge clk_ext)  c_ext  <= c_ext + 1;
    always @(posedge clk_si0)  c_si0  <= c_si0 + 1;
    always @(posedge clk_si1)  c_si1  <= c_si1 + 1;
    always @(posedge clk_si2)  c_si2  <= c_si2 + 1;
    always @(posedge eth_rxc)  c_rxc  <= c_rxc + 1;
    assign led0 = c_tcxo[24]; assign led1 = c_ext[22] ^ btn0; assign led2 = c_si0[24] ^ c_si1[24] ^ btn1; assign led3 = c_si2[24] ^ c_rxc[25];
    assign leds_dummy = 4'b0;
    // ---- a 100 MHz sample clock from the TCXO through the PLL ----
    wire clk100, pll_lock;
    EHXPLLL #(.CLKI_DIV(1), .CLKFB_DIV(4), .CLKOP_DIV(6), .CLKOP_ENABLE("ENABLED"), .FEEDBK_PATH("CLKOP"), .CLKOP_CPHASE(2), .CLKOP_FPHASE(0))
        pll (.CLKI(clk_tcxo), .CLKFB(clk100), .CLKOP(clk100), .LOCK(pll_lock), .RST(1'b0), .STDBY(1'b0), .PHASESEL0(1'b0), .PHASESEL1(1'b0),
             .PHASEDIR(1'b0), .PHASESTEP(1'b0), .PHASELOADREG(1'b0), .PLLWAKESYNC(1'b0), .ENCLKOP(1'b0));
    // ---- DACs: a ramp on port 1, a triangle on port 2, both clocked at clk100 (ODDR-free for the test) ----
    reg [13:0] ramp = 0; reg dir = 0;
    always @(posedge clk100) begin ramp <= ramp + 1; if (ramp == 14'h3fff) dir <= ~dir; end
    assign dac_p1_d = ramp; assign dac_p2_d = dir ? ~ramp : ramp;
    assign dac_clk1 = clk100; assign dac_clk2 = clk100; assign dac_wrt1 = clk100; assign dac_wrt2 = clk100;
    assign dac_mode = 1'b1; assign dac_sleep = 1'b0;
    // ---- ADCs: sampled into registers; the sum goes out on the clock-out pin so nothing is optimised away ----
    reg [11:0] sa = 0, sb = 0; reg oa = 0, ob = 0;
    always @(posedge clk100) begin sa <= adc_a_d; sb <= adc_b_d; oa <= adc_a_otr; ob <= adc_b_otr; end
    assign adc_a_clk = clk100; assign adc_b_clk = clk100; assign adc_dcs = 1'b1; assign adc_dfs = 1'b0; assign adc_pdwn_a = 1'b0; assign adc_pdwn_b = 1'b0;
    assign clk_out = c_tcxo[0] ^ (^sa) ^ (^sb) ^ oa ^ ob ^ ftdi_rts ^ ftdi_dtr;
    // ---- UART loopback ----
    assign uart_tx = uart_rx;
    // ---- SDRAM: addresses from the ramp, data bus tri-stated from a counter bit ----
    assign sdram_a = {ramp[12:0]}; assign sdram_ba = ramp[1:0]; assign sdram_clk = clk100; assign sdram_cke = 1'b1;
    assign sdram_cs_n = ~ramp[2]; assign sdram_ras_n = ramp[3]; assign sdram_cas_n = ramp[4]; assign sdram_we_n = ramp[5];
    assign sdram_dqml = ramp[6]; assign sdram_dqmh = ramp[7];
    reg [15:0] dq_in = 0; always @(posedge clk100) dq_in <= sdram_dq;
    assign sdram_dq = ramp[8] ? {ramp, dq_in[1:0]} : 16'bz;
    // ---- Ethernet: TX side from the ramp, RX side registered on its own clock ----
    reg [4:0] rx_r = 0; always @(posedge eth_rxc) rx_r <= {eth_rx_ctl, eth_rxd};
    assign eth_txc = c_rxc[0]; assign eth_tx_ctl = rx_r[4]; assign eth_txd = rx_r[3:0];
    assign eth_mdc = c_tcxo[5]; assign eth_mdio = c_tcxo[6] ? 1'bz : c_tcxo[7]; assign eth_rst_n = pll_lock;
    // ---- GPDI pairs: the counter, as true/complement ----
    assign gpdi_ck_p = c_tcxo[1]; assign gpdi_ck_n = ~c_tcxo[1];
    assign gpdi_d0_p = c_tcxo[2]; assign gpdi_d0_n = ~c_tcxo[2];
    assign gpdi_d1_p = c_tcxo[3]; assign gpdi_d1_n = ~c_tcxo[3];
    assign gpdi_d2_p = c_tcxo[4]; assign gpdi_d2_n = ~c_tcxo[4];
    assign gpdi_cec = c_tcxo[8] ? 1'bz : 1'b0; assign gpdi_scl = c_tcxo[9] ? 1'bz : 1'b0; assign gpdi_sda = (c_tcxo[10] | gpdi_hpd | eth_int_n) ? 1'bz : 1'b0;
    // ---- SD, USB, I2C, Pmods, flash: driven or tri-stated from counter bits ----
    assign sd_clk = c_tcxo[11]; assign sd_cmd = c_tcxo[12] ? 1'bz : 1'b0; assign sd_d = c_tcxo[13] ? 4'bz : c_tcxo[17:14];
    assign usb_dp = c_tcxo[18] ? 1'bz : 1'b0; assign usb_dn = c_tcxo[18] ? 1'bz : 1'b1; assign usb_pullup = c_tcxo[19];
    assign i2c_scl = c_tcxo[20] ? 1'bz : 1'b0; assign i2c_sda = c_tcxo[21] ? 1'bz : 1'b0;
    assign pmoda = c_ext[8] ? 8'bz : c_ext[7:0]; assign pmodb = c_si0[8] ? 8'bz : c_si0[7:0];
    assign flash_cs_n = c_tcxo[22]; assign flash_io = c_tcxo[23] ? 4'bz : c_tcxo[13:10];
    // the flash clock is a dedicated pin on the ECP5: USRMCLK
    USRMCLK mclk (.USRMCLKI(c_tcxo[1]), .USRMCLKTS(1'b0));
endmodule
