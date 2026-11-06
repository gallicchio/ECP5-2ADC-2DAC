# ECP5-2ADC-2DAC bring-up gateware.  Tools: the oss-cad-suite (yosys, nextpnr-ecp5, ecppack, iverilog);
# set OSS_CAD_SUITE if it is not at the default path in build.sh.
OSS ?= /home/jason/mudd/133electronics/icepi-zero-dac-adc/tools/oss-cad-suite
IV = $(OSS)/bin/iverilog
VVP = $(OSS)/bin/vvp
RTL = rtl/top.v rtl/uart.v rtl/regbus.v rtl/cdc.v rtl/clkcount.v rtl/adc_capture.v rtl/dac_gen.v rtl/sdram_test.v rtl/pll_sys.v
SIM = sim/ecp5_sim_models.v sim/models.v sim/sdram_model.v

all: blink bringup

blink:                      ## build/blink.bit: LEDs, CLK OUT, a serial greeting
	./build.sh blink
bringup:                    ## build/bringup.bit: the register bus and every engine
	./build.sh bringup

sim: build/tb_top.vvp       ## the self-checking testbench (about a minute)
	cd rtl && $(VVP) -n ../build/tb_top.vvp | grep -v 'VCD info' | tail -80
build/tb_top.vvp: sim/tb_top.v $(RTL) $(SIM) rtl/sine_lut.hex
	mkdir -p build && $(IV) -g2012 -o $@ -s tb_top sim/tb_top.v $(RTL) $(SIM)

sim-blink: build/tb_blink.vvp
	cd build && $(VVP) -n tb_blink.vvp | tail -20
build/tb_blink.vvp: sim/tb_blink.v rtl/blink.v rtl/uart.v
	mkdir -p build && $(IV) -g2012 -o $@ -s tb_blink sim/tb_blink.v rtl/blink.v rtl/uart.v

build/tb_file.vvp: sim/tb_file.v $(RTL) $(SIM)
	mkdir -p build && $(IV) -g2012 -o $@ -s tb_file sim/tb_file.v $(RTL) $(SIM)
test: build/tb_file.vvp     ## host/ecp5bu.py against the RTL (the Python drives the simulated UART)
	python3 host/test_sim.py

lut:
	python3 host/gen_lut.py

clean:
	rm -rf build/*.json build/*.config build/*.log build/*.vvp build/*.vcd build/*.out build/cosim_*

.PHONY: all blink bringup sim sim-blink test lut clean
