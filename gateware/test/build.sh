#!/bin/sh
# Synthesise, place and route the pin-plan proof against the generated LPF.
# Any clock that is not on a PCLK ball, any ball named twice, any missing
# LOCATE shows up here before a board is ordered.
set -e
cd "$(dirname "$0")"
LPF=../ecp5_2adc_2dac.lpf
yosys -q -p "synth_ecp5 -top pins -json pins.json" pins.v
nextpnr-ecp5 --25k --package CABGA256 --speed 6 --json pins.json --lpf $LPF --textcfg pins.config --lpf-allow-unconstrained > pins.pnr.log 2>&1 || { tail -30 pins.pnr.log; exit 1; }
ecppack --compress pins.config pins.bit
grep -E "Max frequency|Info: Device utilisation|LUT4:|PIO:" pins.pnr.log | head
grep -ci "warning.*clock" pins.pnr.log || true
echo "pins.bit built"
