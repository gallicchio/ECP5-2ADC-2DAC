// The board and its bench, simulated, driven live by the bring-up's own Python (host/cosim.py).
// Commands arrive on a named pipe (+cmd=PATH) and answers leave on another (+resp=PATH):
//   S xx     send the byte xx (hex) to the board's UART
//   R n      wait for n bytes from the board; one hex line each, or TO if they do not come
//   W n      let n nanoseconds pass
//   T        the simulated time in ns, one line
//   F        discard the bytes received from the board so far
//   K id v   set knob `id` of the bench to v (the table is in the case statement below and in cosim.py)
//   E        end
// The bench around the board: the three SMA cables of the self-test cabling or a generator (models2.v's
// analog_channel), an SDRAM, the Si5351 (an I2C register file; its three outputs are 10, 25 and 100 MHz once
// the driver has enabled them), the PHY (MDIO registers; RGMII through sim/rgmii_phy_model.v, in loopback when
// BMCR bit 14 is set), a microSD card, a USB host, a monitor's DDC EEPROM and hot-plug pin, a Pmod-to-Pmod loop.
// The UART runs at 25 MHz / UART_DIV (4: 6.25 Mbaud) and the counters' gate is 1 ms, to keep runs short.
`timescale 1ns/1ps
module tb_cosim;
    parameter UART_DIV = 4;
    localparam real BIT = UART_DIV * 40.0;
    reg clk_tcxo = 0; always #20 clk_tcxo = ~clk_tcxo;

    // ---- the knobs ------------------------------------------------------------------------------------
    integer k_clkin = 0;            // 1  CLK IN: 0 nothing, 1 the cable from CLK OUT, 2 a generator
    real    k_clkin_hz = 10e6;      // 2  that generator's frequency
    integer k_pmod_loop = 0;        // 3  Pmod A wired to Pmod B, pin for pin
    integer k_sd = 0;               // 4  a card in the microSD socket
    integer k_usb = 0;              // 5  USB USER cabled to a host
    integer k_monitor = 0;          // 6  a monitor on the HDMI jack
    integer k_link = 0;             // 7  an Ethernet cable to a gigabit switch
    integer k_btn0 = 0, k_btn1 = 0; // 8, 9  a finger on BTN0 / BTN1
    // 10-19: the two ADC channels' sources, gains, terminations and generators (in ch_a and ch_b); 20: inject a frame

    reg gen_clk = 0; always #(0.5e9 / k_clkin_hz) gen_clk = ~gen_clk;
    wire clk_out;
    wire clk_ext = k_clkin == 1 ? clk_out : k_clkin == 2 ? gen_clk : 1'b0;

    // ---- the board --------------------------------------------------------------------------------------
    reg uart_rx = 1; wire uart_tx;
    wire [7:0] leds; wire led_r, led_g, led_b;
    wire [11:0] adc_a_d, adc_b_d; wire adc_a_otr, adc_b_otr, adc_a_clk, adc_b_clk, adc_dcs, adc_dfs, adc_pdwn_a, adc_pdwn_b;
    wire [13:0] dac_p1_d, dac_p2_d; wire dac_clk1, dac_clk2, dac_wrt1, dac_wrt2, dac_mode, dac_sleep;
    wire [12:0] sdram_a; wire [1:0] sdram_ba; wire [15:0] sdram_dq;
    wire sdram_clk, sdram_cke, sdram_cs_n, sdram_ras_n, sdram_cas_n, sdram_we_n, sdram_dqml, sdram_dqmh;
    wire eth_mdc, eth_rst_n, eth_mdio, eth_rxc, eth_txc, eth_tx_ctl, eth_rx_ctl; wire [3:0] eth_txd, eth_rxd;
    wire usb_pullup, usb_dp, usb_dn, i2c_scl, i2c_sda;
    wire sd_clk, sd_cmd; wire [3:0] sd_d;
    wire gpdi_d0_p, gpdi_d0_n, gpdi_d1_p, gpdi_d1_n, gpdi_d2_p, gpdi_d2_n, gpdi_ck_p, gpdi_ck_n, gpdi_scl, gpdi_sda;
    wire [7:0] pmoda, pmodb;
    wire clk_si0, clk_si1, clk_si2;
    pullup(eth_mdio); pullup(i2c_scl); pullup(i2c_sda); pullup(gpdi_scl); pullup(gpdi_sda);
    pullup sdram_pu [15:0] (sdram_dq);
    pullup sd_pu [3:0] (sd_d); pullup(sd_cmd);
    pulldown pa_pd [7:0] (pmoda); pulldown pb_pd [7:0] (pmodb);

    top #(.UART_DIV(UART_DIV), .GATE_CYCLES(25000), .MS_CYCLES(250)) dut (
        .clk_tcxo(clk_tcxo), .clk_ext(clk_ext), .clk_si0(clk_si0), .clk_si1(clk_si1), .clk_si2(clk_si2), .clk_out(clk_out),
        .btn0(~k_btn0[0]), .btn1(~k_btn1[0]),
        .led0(leds[0]), .led1(leds[1]), .led2(leds[2]), .led3(leds[3]), .led4(leds[4]), .led5(leds[5]), .led6(leds[6]), .led7(leds[7]),
        .led_r(led_r), .led_g(led_g), .led_b(led_b), .uart_rx(uart_rx), .uart_tx(uart_tx), .ftdi_rts(1'b1), .ftdi_dtr(1'b1),
        .adc_a_d(adc_a_d), .adc_b_d(adc_b_d), .adc_a_otr(adc_a_otr), .adc_b_otr(adc_b_otr),
        .adc_a_clk(adc_a_clk), .adc_b_clk(adc_b_clk), .adc_dcs(adc_dcs), .adc_dfs(adc_dfs), .adc_pdwn_a(adc_pdwn_a), .adc_pdwn_b(adc_pdwn_b),
        .dac_p1_d(dac_p1_d), .dac_p2_d(dac_p2_d), .dac_clk1(dac_clk1), .dac_clk2(dac_clk2), .dac_wrt1(dac_wrt1), .dac_wrt2(dac_wrt2),
        .dac_mode(dac_mode), .dac_sleep(dac_sleep),
        .sdram_a(sdram_a), .sdram_ba(sdram_ba), .sdram_dq(sdram_dq), .sdram_clk(sdram_clk), .sdram_cke(sdram_cke), .sdram_cs_n(sdram_cs_n),
        .sdram_ras_n(sdram_ras_n), .sdram_cas_n(sdram_cas_n), .sdram_we_n(sdram_we_n), .sdram_dqml(sdram_dqml), .sdram_dqmh(sdram_dqmh),
        .eth_rxc(eth_rxc), .eth_int_n(1'b1), .eth_mdc(eth_mdc), .eth_rst_n(eth_rst_n), .eth_mdio(eth_mdio),
        .eth_txc(eth_txc), .eth_tx_ctl(eth_tx_ctl), .eth_txd(eth_txd), .eth_rx_ctl(eth_rx_ctl), .eth_rxd(eth_rxd),
        .usb_pullup(usb_pullup), .usb_dp(usb_dp), .usb_dn(usb_dn),
        .sd_clk(sd_clk), .sd_cmd(sd_cmd), .sd_d(sd_d),
        .gpdi_d0_p(gpdi_d0_p), .gpdi_d0_n(gpdi_d0_n), .gpdi_d1_p(gpdi_d1_p), .gpdi_d1_n(gpdi_d1_n),
        .gpdi_d2_p(gpdi_d2_p), .gpdi_d2_n(gpdi_d2_n), .gpdi_ck_p(gpdi_ck_p), .gpdi_ck_n(gpdi_ck_n),
        .gpdi_scl(gpdi_scl), .gpdi_sda(gpdi_sda), .gpdi_hpd(k_monitor[0]), .gpdi_cec(1'b1),
        .i2c_scl(i2c_scl), .i2c_sda(i2c_sda), .pmoda(pmoda), .pmodb(pmodb));

    // ---- the converters and what is cabled to them ---------------------------------------------------------
    wire [13:0] dac1_q, dac2_q;
    dac_latch l1 (.wrt(dac_wrt1), .d(dac_p1_d), .sleep(dac_sleep), .q(dac1_q));
    dac_latch l2 (.wrt(dac_wrt2), .d(dac_p2_d), .sleep(dac_sleep), .q(dac2_q));
    dac_monitor mon1 (.wrt(dac_wrt1), .clk(dac_clk1), .d(dac_p1_d));
    dac_monitor mon2 (.wrt(dac_wrt2), .clk(dac_clk2), .d(dac_p2_d));
    analog_channel #(.SEED(11)) ch_a (.clk(adc_a_clk), .dac1(dac1_q), .dac2(dac2_q), .d(adc_a_d), .otr(adc_a_otr));
    analog_channel #(.SEED(23)) ch_b (.clk(adc_b_clk), .dac1(dac1_q), .dac2(dac2_q), .d(adc_b_d), .otr(adc_b_otr));

    sdram_model sdram (.clk(sdram_clk), .cke(sdram_cke), .cs_n(sdram_cs_n), .ras_n(sdram_ras_n), .cas_n(sdram_cas_n), .we_n(sdram_we_n),
                       .ba(sdram_ba), .a(sdram_a), .dqml(sdram_dqml), .dqmh(sdram_dqmh), .dq(sdram_dq));

    // ---- the Si5351: registers, and three clocks that run once output-enable (register 3) and the control
    //      registers (16-18) have been written as the driver writes them ------------------------------------------
    i2c_slave_model si (.scl(i2c_scl), .sda(i2c_sda));
    reg o0 = 0, o1 = 0, o2 = 0;
    always #50 o0 = ~o0;            // 10 MHz
    always #20 o1 = ~o1;            // 25 MHz
    always #5  o2 = ~o2;            // 100 MHz
    assign clk_si0 = o0 & ~si.regs[3][0] & (si.regs[16] != 0);
    assign clk_si1 = o1 & ~si.regs[3][1] & (si.regs[17] != 0);
    assign clk_si2 = o2 & ~si.regs[3][2] & (si.regs[18] != 0);
    initial #1 si.regs[3] = 8'hff;  // outputs off until programmed (the bring-up plan says so; a blank part's are)

    // ---- the PHY: MDIO registers and the RGMII model -----------------------------------------------------------
    mdio_slave_model phy (.mdc(eth_mdc), .mdio(eth_mdio));
    always #500 begin
        // BMSR: link and auto-negotiation complete with a cable (or in loopback); PHYSR (register 26): 1000 full, link
        phy.regs[1]  = (k_link != 0 || phy.regs[0][14]) ? 16'h796d : 16'h7949;
        phy.regs[26] = (k_link != 0 || phy.regs[0][14]) ? 16'h002c : 16'h0000;
    end
    initial #1 begin phy.regs[0] = 16'h1140; phy.regs[17] = 16'h0109; phy.regs[21] = 16'h0019; end   // BMCR; TXDLY (bit 8); RXDLY (bit 3)
    rgmii_phy_model rphy (.rst_n(eth_rst_n), .txc(eth_txc), .tx_ctl(eth_tx_ctl), .txd(eth_txd), .rxc(eth_rxc), .rx_ctl(eth_rx_ctl), .rxd(eth_rxd),
                          .loopback(phy.regs[0][14]), .link(k_link[0]));

    // ---- the microSD card, the USB host, the monitor, the Pmod loop ---------------------------------------------
    sd_spi_model card (.present(k_sd[0]), .sck(sd_clk), .cs_n(sd_d[3]), .mosi(sd_cmd), .miso(sd_d[0]));
    assign (pull1, highz0) usb_dp = usb_pullup ? 1'b1 : 1'bz;      // the board's 1.5 k from USB_PULLUP to D+
    usb_host_model #(.T_DEBOUNCE(100_000.0), .T_RESET(400_000.0)) host (.present(k_usb[0]), .dp(usb_dp), .dn(usb_dn));
    wire ddc_scl_m, ddc_sda_m; pullup(ddc_scl_m); pullup(ddc_sda_m);
    tranif1 tscl (gpdi_scl, ddc_scl_m, k_monitor[0]);
    tranif1 tsda (gpdi_sda, ddc_sda_m, k_monitor[0]);
    i2c_slave_model #(.ADDR(7'h50)) edid (.scl(ddc_scl_m), .sda(ddc_sda_m));
    integer e, esum;
    initial #1 begin                                                // an EDID block: the header, a maker, a name, a checksum
        edid.regs[0] = 8'h00; for (e = 1; e < 7; e = e + 1) edid.regs[e] = 8'hff; edid.regs[7] = 8'h00;
        edid.regs[8] = 8'h21; edid.regs[9] = 8'ha3;                 // "HMC": (8 << 10) | (13 << 5) | 3
        edid.regs[18] = 8'h01; edid.regs[19] = 8'h03;
        edid.regs[54] = 0; edid.regs[55] = 0; edid.regs[56] = 0; edid.regs[57] = 8'hfc; edid.regs[58] = 0;
        edid.regs[59] = "S"; edid.regs[60] = "I"; edid.regs[61] = "M"; edid.regs[62] = " "; edid.regs[63] = "L"; edid.regs[64] = "C"; edid.regs[65] = "D"; edid.regs[66] = 8'h0a;
        esum = 0; for (e = 0; e < 127; e = e + 1) esum = esum + edid.regs[e];
        edid.regs[127] = (256 - (esum % 256)) % 256;
    end
    tranif1 tp [7:0] (pmoda, pmodb, {8{k_pmod_loop[0]}});

    // ---- the PC's UART: a sender, and a receiver that queues what the board says ---------------------------------
    realtime t_sent = 0;
    task send_byte(input [7:0] bb); integer k; begin
        if ($realtime - t_sent < BIT) #(BIT - ($realtime - t_sent));
        uart_rx = 0; #(BIT);
        for (k = 0; k < 8; k = k + 1) begin uart_rx = bb[k]; #(BIT); end
        uart_rx = 1; t_sent = $realtime;
    end endtask
    reg [7:0] rxq [0:65535]; integer wp = 0, rp = 0; reg [7:0] rb; integer i;
    always begin
        @(negedge uart_tx); #(BIT * 1.5);
        for (i = 0; i < 8; i = i + 1) begin rb[i] = (uart_tx === 1'b1); #(BIT); end
        rxq[wp % 65536] = rb; wp = wp + 1;
    end

    // ---- the command loop ------------------------------------------------------------------------------------------
    integer fi, fo, r, n, b, got, waited, id; real val;
    reg [8*8:1] kind;
    reg [8*400:1] cmd_path, resp_path;
    initial begin
        if (!$value$plusargs("cmd=%s", cmd_path) || !$value$plusargs("resp=%s", resp_path)) begin
            $display("tb_cosim: run it through host/cosim.py (+cmd=PIPE +resp=PIPE)"); $finish;
        end
        fi = $fopen(cmd_path, "r"); fo = $fopen(resp_path, "w");
        #2000;
        forever begin
            r = $fscanf(fi, "%s", kind);
            if (r != 1) begin $display("tb_cosim: the command pipe closed at %t", $time); $finish; end
            case (kind[8:1])
            "S": begin r = $fscanf(fi, "%h", b); send_byte(b); end
            "W": begin r = $fscanf(fi, "%d", n); #(n); end
            "T": begin $fwrite(fo, "%0.0f\n", $realtime); $fflush(fo); end
            "F": rp = wp;                               // forget what the board has said so far
            "R": begin
                r = $fscanf(fi, "%d", n);
                got = 0; waited = 0;
                while (got < n && waited < 4000) begin
                    if (rp != wp) begin $fwrite(fo, "%02x\n", rxq[rp % 65536]); rp = rp + 1; got = got + 1; waited = 0; end
                    else begin #(BIT * 5); waited = waited + 1; end
                end
                if (got < n) $fwrite(fo, "TO\n");
                $fflush(fo);
            end
            "K": begin
                r = $fscanf(fi, "%d %f", id, val);
                case (id)
                1: k_clkin = val;      2: k_clkin_hz = val;   3: k_pmod_loop = val;  4: k_sd = val;       5: k_usb = val;
                6: k_monitor = val;    7: k_link = val;       8: k_btn0 = val;       9: k_btn1 = val;
                10: ch_a.src = val;    11: ch_b.src = val;    12: ch_a.gain = val;   13: ch_b.gain = val;
                14: ch_a.term = val != 0; 15: ch_b.term = val != 0;
                16: ch_a.gen_hz = val; 17: ch_a.gen_codes = val; 18: ch_b.gen_hz = val; 19: ch_b.gen_codes = val;
                default: $display("tb_cosim: no knob %0d", id);
                endcase
            end
            "E": begin
                $display("tb_cosim: ended at %t; DAC setup violations %0d %0d; SDRAM model complaints %0d; SD commands %0d (CRC errors %0d, unknown %0d); USB attaches %0d",
                         $time, mon1.viol, mon2.viol, sdram.bad, card.cmds, card.crc_errors, card.bad_cmds, host.connects);
                $fclose(fo); $finish;
            end
            default: begin $display("tb_cosim: unknown command %s", kind); $finish; end
            endcase
        end
    end
endmodule
