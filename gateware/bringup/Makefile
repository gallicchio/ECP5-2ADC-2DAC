# ECP5-2ADC-2DAC bring-up gateware.  Tools: the oss-cad-suite (yosys, nextpnr-ecp5, ecppack, iverilog);
# set OSS_CAD_SUITE if it is not at the default path in build.sh.
OSS ?= /home/jason/mudd/133electronics/icepi-zero-dac-adc/tools/oss-cad-suite
IV = $(OSS)/bin/iverilog
VVP = $(OSS)/bin/vvp
RTL = rtl/top.v rtl/uart.v rtl/regbus.v rtl/cdc.v rtl/clkcount.v rtl/adc_capture.v rtl/dac_gen.v rtl/sdram_test.v rtl/pll_sys.v \
      rtl/periph.v rtl/eth_test.v rtl/hdmi_test.v $(wildcard rtl/tmds_enc.v)
SIM = sim/ecp5_sim_models.v sim/models.v sim/models2.v sim/sdram_model.v sim/rgmii_phy_model.v

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

cosim:                      ## the Python driver against the simulated board and its bench, live (host/cosim.py's self-test)
	python3 host/cosim.py
sim-eth:                    ## the RGMII frame engine alone (sim/tb_eth.v)
	mkdir -p build && $(IV) -g2012 -o build/tb_eth.vvp -s tb_eth sim/tb_eth.v rtl/eth_test.v rtl/cdc.v sim/rgmii_phy_model.v sim/ecp5_sim_models.v && $(VVP) -n build/tb_eth.vvp | tail -30
sim-hdmi:                   ## the HDMI test picture alone (sim/tb_hdmi.v)
	mkdir -p build && $(IV) -g2012 -o build/tb_hdmi.vvp -s tb_hdmi sim/tb_hdmi.v rtl/hdmi_test.v $(wildcard rtl/tmds_enc.v) sim/ecp5_sim_models.v && $(VVP) -n build/tb_hdmi.vvp | tail -30

lut:
	python3 host/gen_lut.py

clean:
	rm -rf build/*.json build/*.config build/*.log build/*.vvp build/*.vcd build/*.out build/cosim_*

.PHONY: all blink bringup sim sim-blink sim-eth sim-hdmi cosim test lut clean
