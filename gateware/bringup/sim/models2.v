// More bench models (2026-11-15): a microSD card in SPI mode, a USB host port as the board's USB USER lines
// see it, and the analog world between the converters (the SMA cables of the bring-up's self-test cabling, or
// a generator), so the bring-up's own Python can be run against the RTL before a board is powered.
`timescale 1ns/1ps

// A microSD card (SDHC) in SPI mode, as far as the bring-up's check goes: CMD0, CMD8, CMD55 + ACMD41 (ready
// on the third try), CMD58, CMD9 (CSD), CMD10 (CID), CMD17 (one 512-byte block: byte i of block n is
// (i * 7 + 3 + n) mod 256, ending 55 AA), each data block with a true CRC-16.  It checks the CRC-7 of CMD0
// and CMD8 as a real card does.  SCK idles low; the card samples MOSI on the rising edge and changes MISO on
// the falling edge.  `present` = 0 is an empty socket (MISO released).
module sd_spi_model (input present, input sck, input cs_n, input mosi, output miso);
    reg miso_r = 1'b1;
    assign miso = (present && !cs_n) ? miso_r : 1'bz;
    reg [7:0] cmd [0:5];
    reg [7:0] out [0:1023];
    integer n_out = 0, p_out = 0, nbit = 0, nbyte = 0, acmd_tries = 0, cmds = 0, crc_errors = 0, bad_cmds = 0, i;
    reg [7:0] sh = 8'hff, osh = 8'hff;
    reg app = 0, idle = 1;
    reg [15:0] crc16;
    function [6:0] crc7(input [39:0] d); integer k; reg [6:0] c; reg b; begin
        c = 0;
        for (k = 39; k >= 0; k = k - 1) begin b = d[k] ^ c[6]; c = {c[5:0], 1'b0}; if (b) c = c ^ 7'h09; end
        crc7 = c;
    end endfunction
    task put(input [7:0] b); begin out[n_out] = b; n_out = n_out + 1; end endtask
    task crc16_byte(input [7:0] b); integer k; reg x; begin
        for (k = 7; k >= 0; k = k - 1) begin x = b[k] ^ crc16[15]; crc16 = {crc16[14:0], 1'b0}; if (x) crc16 = crc16 ^ 16'h1021; end
    end endtask
    task data_block(input integer len, input integer kind, input [31:0] arg); integer k; reg [7:0] b; begin
        put(8'hff); put(8'hfe); crc16 = 0;                 // one gap byte, then the start token
        for (k = 0; k < len; k = k + 1) begin
            case (kind)
            0: b = (k == 510) ? 8'h55 : (k == 511) ? 8'haa : (k * 7 + 3 + arg);       // a block
            1: b = (k == 0) ? 8'h03 : (k < 6) ? 8'h53 + k : (k == 15) ? 8'h01 : 8'h20 + k;   // CID: manufacturer 03, a name
            default: b = (k == 0) ? 8'h40 : 8'h0e + k;                               // CSD version 2
            endcase
            put(b); crc16_byte(b);
        end
        put(crc16[15:8]); put(crc16[7:0]);
    end endtask
    task respond; reg [5:0] c; reg [31:0] arg; begin
        c = cmd[0][5:0]; arg = {cmd[1], cmd[2], cmd[3], cmd[4]};
        cmds = cmds + 1; n_out = 0; p_out = 0;
        put(8'hff);                                         // one byte of thinking time
        if ((c == 0 || c == 8) && crc7({cmd[0], cmd[1], cmd[2], cmd[3], cmd[4]}) != cmd[5][7:1]) begin
            crc_errors = crc_errors + 1; put(8'h09);        // idle + CRC error
        end else if (app && c == 41) begin
            acmd_tries = acmd_tries + 1;
            if (acmd_tries >= 3) idle = 0;
            put({7'b0, idle});
        end else case (c)
            0:  begin idle = 1; acmd_tries = 0; put(8'h01); end
            8:  begin put(8'h01); put(8'h00); put(8'h00); put(8'h01); put(cmd[4]); end
            55: put({7'b0, idle});
            58: begin put({7'b0, idle}); put(idle ? 8'h00 : 8'hc0); put(8'hff); put(8'h80); put(8'h00); end
            9:  begin put(8'h00); data_block(16, 2, 0); end
            10: begin put(8'h00); data_block(16, 1, 0); end
            17: begin put(8'h00); data_block(512, 0, arg); end
            default: begin bad_cmds = bad_cmds + 1; put(8'h04 | idle); end      // illegal command
        endcase
        app = (c == 55);
    end endtask
    always @(posedge cs_n) begin nbit = 0; nbyte = 0; end
    always @(posedge sck) if (present && !cs_n) begin
        sh = {sh[6:0], mosi};
        nbit = nbit + 1;
        if (nbit == 8) begin
            nbit = 0;
            if (nbyte == 0) begin
                if (sh[7:6] == 2'b01) begin cmd[0] = sh; nbyte = 1; end     // a command starts with 01
            end else begin
                cmd[nbyte] = sh; nbyte = nbyte + 1;
                if (nbyte == 6) begin nbyte = 0; respond; end
            end
        end
    end
    // MISO: the master samples on the rising edge, so each byte's first bit must be out at the falling edge that
    // ends the byte before it: every eighth falling edge loads the next byte (FF when there is none)
    integer fcnt = 0;
    always @(negedge sck) if (present && !cs_n) begin
        fcnt = fcnt + 1;
        if (fcnt % 8 == 0) begin
            if (p_out < n_out) begin osh = out[p_out]; p_out = p_out + 1; end else osh = 8'hff;
        end
        miso_r = osh[7]; osh = {osh[6:0], 1'b1};
    end
    always @(posedge cs_n) begin fcnt = 0; osh = 8'hff; miso_r = 1'b1; end
endmodule

// A USB host port as the device's two lines see it: 15 k to ground on each line, and when a line is pulled
// high (a device attached: D+ for full speed, D- for low speed) the host waits `T_DEBOUNCE`, drives both low
// for `T_RESET` (the bus reset), lets go, and sends three bursts of 40 line reversals (packets nothing
// answers).  Times are parameters so a simulation need not wait the real 100 ms and 50 ms.
module usb_host_model #(parameter real T_DEBOUNCE = 200_000.0, T_RESET = 3_000_000.0, T_BIT = 83.3) (input present, inout dp, inout dn);
    reg drive = 0, dp_o = 0, dn_o = 0;
    assign (weak0, highz1) dp = present ? 1'b0 : 1'bz;
    assign (weak0, highz1) dn = present ? 1'b0 : 1'bz;
    assign dp = drive ? dp_o : 1'bz;
    assign dn = drive ? dn_o : 1'bz;
    integer connects = 0, k, b;
    reg fs;
    always begin
        wait (present && (dp === 1'b1 || dn === 1'b1) && !drive);
        fs = (dp === 1'b1);
        #(T_DEBOUNCE);
        if (present && ((fs && dp === 1'b1) || (!fs && dn === 1'b1))) begin
            connects = connects + 1;
            drive = 1; dp_o = 0; dn_o = 0; #(T_RESET);
            drive = 0; #(20_000);
            for (b = 0; b < 3; b = b + 1) begin
                drive = 1;
                for (k = 0; k < 40; k = k + 1) begin dp_o = k[0] ^ ~fs; dn_o = ~(k[0] ^ ~fs); #(T_BIT * 2); end   // K/J reversals
                dp_o = 0; dn_o = 0; #(T_BIT * 2);                                                                   // end of packet
                drive = 0; #(100_000);
            end
            wait (!(dp === 1'b1 || dn === 1'b1) || !present);       // until the device detaches
        end
        #(1000);
    end
endmodule

// One ADC channel's analog world.  What the channel's SMA carries is chosen by `src`:
//   0  nothing (the 50 ohm termination): mid-scale plus a code of noise
//   1  a cable from DAC 1 OUT, 2 from DAC 2 OUT: the DAC's code scaled as the board does it (a full-scale DAC is
//      +-1 V into the ADC input's 50 ohm, which is the ADC's full scale at gain x1): adc = 2048 + (dac - 8192) / 4,
//      times `gain` (the preamp jumpers), times 2 when `term` is 0 (no termination: the DAC's open-circuit voltage)
//   3  a generator: a sine of `gen_hz` and `gen_codes` peak (already in codes at gain 1), times `gain`
// The AD9238 gives the sample seven clocks later, TPD after the clock edge; OTR flags a clipped sample.
module analog_channel #(parameter real TPD = 3.5, parameter integer SEED = 1) (
    input clk, input [13:0] dac1, input [13:0] dac2,
    output reg [11:0] d, output reg otr
);
    // the knobs, set by the testbench through the hierarchy (a real cannot be a port in plain Verilog)
    integer src = 0; real gain = 1.0; reg term = 1; real gen_hz = 100e3, gen_codes = 512.0;
    real v; integer q, k, seed = SEED, noise;
    reg [12:0] pipe [0:6];
    initial begin d = 12'h800; otr = 0; for (k = 0; k < 7; k = k + 1) pipe[k] = 13'h0800; end
    always @(posedge clk) begin
        case (src)
        1: v = (dac1 - 8192.0) / 4.0 * gain * (term ? 1.0 : 2.0);
        2: v = (dac2 - 8192.0) / 4.0 * gain * (term ? 1.0 : 2.0);
        3: v = gen_codes * gain * $sin(2.0 * 3.14159265358979 * gen_hz * $realtime * 1e-9);
        default: v = 0.0;
        endcase
        noise = $random(seed) % 2;                       // -1, 0 or +1 code
        q = $rtoi(2048.0 + v + (v >= 0 ? 0.5 : -0.5)) + noise;
        for (k = 6; k > 0; k = k - 1) pipe[k] = pipe[k - 1];
        pipe[0] = (q > 4095) ? {1'b1, 12'hfff} : (q < 0) ? {1'b1, 12'h000} : {1'b0, q[11:0]};
        #(TPD) d = pipe[6][11:0]; otr = pipe[6][12];
    end
endmodule

// The AD9767's two ports as voltages: each port's code as latched at its WRT rising edge.
module dac_latch (input wrt, input [13:0] d, input sleep, output reg [13:0] q);
    initial q = 14'd8192;
    always @(posedge wrt) q <= sleep ? 14'd8192 : d;
endmodule
