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
LPF=../ecp5_2adc_2dac.lpf
mkdir -p build
case "$1" in
  blink)   TOP=blink;  SRC="rtl/blink.v rtl/uart.v" ;;
  bringup) TOP=top;    SRC="rtl/top.v rtl/uart.v rtl/regbus.v rtl/cdc.v rtl/clkcount.v rtl/adc_capture.v rtl/dac_gen.v rtl/sdram_test.v rtl/pll_sys.v" ;;
  *) echo "usage: $0 blink|bringup"; exit 2 ;;
esac
NAME=${1}
BUILD_ID=$(date +%Y%m%d)
cd rtl   # $readmemh("sine_lut.hex") is relative to the working directory
CHPARAM=""; [ "$TOP" = top ] && CHPARAM="chparam -set BUILD_ID 32'h$BUILD_ID $TOP;"
yosys -q -l ../build/$NAME.yosys.log -p "read_verilog -defer $(for f in $SRC; do echo ../$f; done | tr '\n' ' '); $CHPARAM synth_ecp5 -top $TOP -json ../build/$NAME.json" || { tail -30 ../build/$NAME.yosys.log; exit 1; }
cd ..
nextpnr-ecp5 --25k --package CABGA256 --speed 6 --json build/$NAME.json --lpf $LPF --textcfg build/$NAME.config \
    --lpf-allow-unconstrained --timing-allow-fail --seed 1 > build/$NAME.pnr.log 2>&1 || { tail -40 build/$NAME.pnr.log; exit 1; }
ecppack --compress build/$NAME.config build/$NAME.bit
grep -E "Max frequency for clock|Info: Device utilisation|LUT4:|TRELLIS_IO:|DP16KD:|EHXPLLL:" build/$NAME.pnr.log | sed 's/^Info: *//' | head -20
grep -ci "warning" build/$NAME.pnr.log | sed 's/^/warnings: /'
ls -la build/$NAME.bit
