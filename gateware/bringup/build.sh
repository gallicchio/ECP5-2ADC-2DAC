#!/bin/sh
# Synthesise, place, route and pack one of the bring-up designs against the generated LPF.
#   ./build.sh blink      -> build/blink.bit    (rtl/blink.v: LEDs, CLK OUT, a serial greeting)
#   ./build.sh bringup    -> build/bringup.bit  (rtl/top.v: the register bus and every engine)
# The tools are the oss-cad-suite's; set OSS_CAD_SUITE if yours is elsewhere.  Load a bitstream with
#   openFPGALoader -c ft2232 build/bringup.bit          (into the FPGA, until the next power cycle)
#   openFPGALoader -c ft2232 -f build/bringup.bit       (into the flash: it boots by itself from then on)
set -e
cd "$(dirname "$0")"
OSS=${OSS_CAD_SUITE:-/home/jason/mudd/133electronics/icepi-zero-dac-adc/tools/oss-cad-suite}
PATH="$OSS/bin:$PATH"; export PATH
LPF=build/$1.lpf
mkdir -p build
case "$1" in
  blink)   TOP=blink;  SRC="rtl/blink.v rtl/uart.v"; cp ../ecp5_2adc_2dac.lpf $LPF ;;
  bringup) TOP=top;    SRC="rtl/top.v rtl/uart.v rtl/regbus.v rtl/cdc.v rtl/clkcount.v rtl/adc_capture.v rtl/dac_gen.v rtl/sdram_test.v rtl/pll_sys.v rtl/periph.v rtl/eth_test.v rtl/hdmi_test.v"
           [ -f rtl/tmds_enc.v ] && SRC="$SRC rtl/tmds_enc.v"
           cat ../ecp5_2adc_2dac.lpf bringup_extra.lpf > $LPF ;;      # the board's constraints, then this design's pulls
  *) echo "usage: $0 blink|bringup"; exit 2 ;;
esac
NAME=${1}
BUILD_ID=$(date +%Y%m%d)
cd rtl   # $readmemh("sine_lut.hex") is relative to the working directory
CHPARAM=""; [ "$TOP" = top ] && CHPARAM="chparam -set BUILD_ID 32'h$BUILD_ID $TOP;"
yosys -q -l ../build/$NAME.yosys.log -p "read_verilog -defer $(for f in $SRC; do echo ../$f; done | tr '\n' ' '); $CHPARAM synth_ecp5 -top $TOP -json ../build/$NAME.json" || { tail -30 ../build/$NAME.yosys.log; exit 1; }
cd ..
# nextpnr's result moves some 10 % from seed to seed, and the design has two 125 MHz domains since 2026-11-15:
# try seeds until every clock meets its constraint; if none of eight does, keep the last one and say so.
OK=0
for SEED in 1 2 3 4 5 6 7 8; do
    if nextpnr-ecp5 --25k --package CABGA256 --speed 6 --json build/$NAME.json --lpf $LPF --textcfg build/$NAME.config \
        --lpf-allow-unconstrained --seed $SEED > build/$NAME.pnr.log 2>&1; then OK=1; break; fi
    grep -q "Max frequency for clock" build/$NAME.pnr.log || { tail -40 build/$NAME.pnr.log; exit 1; }     # not a timing failure
    echo "seed $SEED: $(grep -E 'Max frequency for clock.*FAIL' build/$NAME.pnr.log | tail -3 | sed 's/^Info: *//' | tr '\n' ';')"
done
if [ $OK = 0 ]; then
    echo "NO SEED MET TIMING: building seed 8 anyway (--timing-allow-fail); read build/$NAME.pnr.log before trusting this bitstream"
    nextpnr-ecp5 --25k --package CABGA256 --speed 6 --json build/$NAME.json --lpf $LPF --textcfg build/$NAME.config \
        --lpf-allow-unconstrained --timing-allow-fail --seed 8 > build/$NAME.pnr.log 2>&1 || { tail -40 build/$NAME.pnr.log; exit 1; }
fi
ecppack --compress build/$NAME.config build/$NAME.bit
echo "seed $SEED"
grep -E "Max frequency for clock|Info: Device utilisation|LUT4:|TRELLIS_IO:|DP16KD:|EHXPLLL:|MULT18X18D:" build/$NAME.pnr.log | sed 's/^Info: *//' | tail -24
grep -ci "warning" build/$NAME.pnr.log | sed 's/^/warnings: /'
ls -la build/$NAME.bit
