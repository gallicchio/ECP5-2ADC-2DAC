# ECP5-2ADC-2DAC board A: the hardware configurations still to run

Written 2026-11-16 night, after the tutorial's tests pushed every interface board A can test by itself (results in
[`BRINGUP_LOG.md`](BRINGUP_LOG.md) from 18:12 on, and the tutorial repo's README, "How fast board A goes").  Each
configuration below is one cabling: what it settles, exactly what goes where, the jumpers, what the PC runs, and what
a pass looks like.  The PC switches every generator output and supply; leave them off when you connect.

The board's connectors, by name and designator (left end, top to bottom: J301 CLK IN, J302 CLK OUT, J101 ADC A IN, J102
ADC B IN, J204 DAC 1 OUT, J205 DAC 2 OUT; right end: J401 RJ45, J501 USB PROG, J502 USB USER, J503 mini-HDMI; J504
microSD on the back).  The instruments: **SDG1032X** (2 channels, 30 MHz), **33220A** (1 output, 20 MHz),
**SDS2104X Plus** (4 channels), **Fluke 45**, **E3646A**.  "BNC-SMA" means a BNC cable ending in an SMA plug (six on the
bench), or a BNC cable with an SMA-BNC adapter.

Before any of them: **put the bring-up design back** (the FPGA holds whatever tutorial design ran last): unplug and
replug J501 USB PROG (the board boots `bringup.bit` from flash), or
`openFPGALoader -c ft2232 gateware/bringup/build/bringup.bit`.

## 0. As left tonight (no instruments)

| from | to | cable |
|---|---|---|
| PC USB | J501 **USB PROG** | the swapped (green/white crossed, labelled) USB-A-to-C cable |
| PC USB | J502 **USB USER** | USB-C cable |
| lab switch | J401 **RJ45** | Ethernet (gigabit link) |
| J204 **DAC 1 OUT** | J101 **ADC A IN** | SMA-SMA |
| J205 **DAC 2 OUT** | J102 **ADC B IN** | SMA-SMA |
| J302 **CLK OUT** | J301 **CLK IN** | SMA-SMA |

Jumpers as BRINGUP.md's table (TERM in on A and B, SRC on SMA, GAIN x1, JP3001 as it was).  Power from USB PROG; the
E3646A off (its claim released at 20:14).  In this configuration the tutorial's `dev/tools/boardtest/all.py` passes
everything it checks (11 of 13; the two LED lessons need eyes).

## 1. Generators and scope: visit 2, plus tonight's two questions (about 20 minutes)

The three SMA-SMA cables off.  Then:

| instrument | channel | to | cable | the PC sets it to |
|---|---|---|---|---|
| SDG1032X | **CH1** | J101 **ADC A IN** | BNC-SMA | sine, load 50 ohm, 1 Vpp; 100 kHz-30 MHz |
| SDG1032X | **CH2** | J301 **CLK IN** | BNC-SMA | 10 MHz sine 1 Vpp, then 0.3 Vpp |
| 33220A | **Output** | J102 **ADC B IN** | BNC-SMA | sine 1 Vpp (load 50 ohm) for visit 2; **DC 0 V, output ON** for step 1c |
| SDS2104X Plus | **CH1** | J204 **DAC 1 OUT** | BNC-SMA | **50 ohm** input (or 1 Mohm with a BNC 50 ohm feed-through), DC |
| SDS2104X Plus | **CH2** | J205 **DAC 2 OUT** | BNC-SMA | the same |
| SDS2104X Plus | **CH3** | J302 **CLK OUT** | BNC-SMA | 50 ohm |
| SDS2104X Plus | CH4 | nothing (or a U.FL pigtail on J107 TAP A) | | |

Jumpers: JP3001 (CLK IN TERM) **in** for the SDG.  Type **"v2 ready"**: `bench.py v2` runs visit 2 as planned.  Then,
for REVB 21 and 22 (new tonight), the session loads the tutorial's `fast.bit` (DACs at 125 MS/s, ADCs at 62.5 MS/s) and:

* **1a. The ADC side alone (REVB 21):** the SDG's CH1 at 5, 10 and 20 MHz, 1 Vpp, into ADC A; ADC A's 2nd and 3rd
  harmonics.  Pass for the ADC side: below -45 dBc at 10 MHz.  Last night through the DAC and cable: -45 dBc at 6 MHz,
  -26 dBc at 11 MHz.  If ADC A alone is clean, the DAC stage makes the distortion; if not, the OPA1612 front end.
* **1b. The DAC side alone (REVB 21):** `fast.py --tone 5e6` etc. on DAC 1, the scope's FFT on CH1 (50 ohm): the DAC's
  own harmonics at 5, 10, 20 MHz.
* **1c. Cross-talk, the ADC side (REVB 22):** the 33220A at DC 0 V, output ON (a 50 ohm source: ADC B terminated); the
  SDG's CH1 at 3, 10 and 30 MHz into ADC A; what ADC B sees, in dBc.  Last night DAC-to-ADC: about -53 dBc at 3 MHz
  (A into B) and -45 dBc at 30 MHz (B into A).  If ADC B sees about that, the coupling is on the ADC side.
* **1d. CLK IN's limits with a sine:** the SDG's CH2 at 1, 10 and 30 MHz, at 1 Vpp, then 0.3 Vpp.  Last night a 3.3 V
  square wave from CLK OUT counted exactly to 300 MHz; a generator's sine is the harder case.

* **1e. The two ADC channels' timing skew** (an open question of the tutorial's 1.15: equivalent-time sampling finds
  A and B 0.01-0.02 ns apart, the 25 MS/s designs 0.6-0.7 ns; nextpnr models both ADC clock pins at the same 0.25 ns
  from the clock net, so the tools can't tell).  A **BNC tee**: the SDG's CH1 (a 5 MHz sine, 1 Vpp) into both J101 ADC
  A IN and J102 ADC B IN at once (two BNC-SMA cables from the tee), so the DACs' own paths drop out.  The session runs
  `capture.sv` (the TCXO's clock straight to both ADC clock pins, E4 and R2) and `fast.sv` (the ADC clocks from a
  register) and compares B - A in each: the difference is the clock pins' skew.

* **1f. ADC B's 1.9 s steps (REVB 24)**, no generator: `make load-udp_awg`, the bridge, and `python3 trng.py --seconds
  60` in the tutorial's `src/verilog` (it prints the health tests; the steps show as B's "10 ms means" far above A's).
  First as cabled (configuration 0), to see it is still there; then the two DAC -> ADC cables crossed (DAC 2 -> ADC
  A); then ADC B IN with a 50 ohm SMA terminator and nothing else; then with USB PROG unplugged (Ethernet only, the
  bitstream already loaded).  Each run 60 s.  Meanwhile look and listen along the bench for anything switching every
  1.9 s.

The generators off and the three SMA-SMA cables back afterwards (configuration 0).

## 2. The Fluke on USB USER (REVB 20; 10 minutes)

Configuration 0, plus the Fluke 45's probes.  The bring-up design loaded (above).  The USB USER cable (J502) in.

| step | the PC runs | Fluke black on | Fluke red on | expect if all is well |
|---|---|---|---|---|
| 2a | `python3 gateware/bringup/host/ecp5bu.py gpio usb_pullup=1` | GND (a J602 even pin) | D501's **anode** (the pad toward R6313) | about 3.3 V less 1 k x 0.3 mA: 3.0 V |
| 2b | (the same) | GND | D501's **cathode** (the pad toward R6311 / the FPGA) | 2.3-2.7 V; below 2.0 V the PC never sees D+ high |
| 2c | (the same) | GND | R6313's **H13 end** | 3.3 V (if not: H13 is not driving) |
| 2d | `... gpio usb_pullup=0` | GND | **R6322's connector end** (D-) | about 0 V; last night the FPGA read D- high at rest |
| 2e | (the same) | GND | the same, **USB USER cable out** | 0 V |

Tonight's FPGA-side test already showed D501 is not backwards (REVB 20); 2b and 2d say whether D+ rises at all and
where D-'s high comes from.  Probes away afterwards.

## 3. The microSD card that doesn't answer (5 minutes)

A new card has been in J504 since the morning of 2026-11-16, and at 20:31 it answered nothing.  The bring-up's SPI-mode
check got no answer to CMD0; a pin-level probe (the FPGA driving the socket's pins one state at a time from the PC,
about 50 kHz) got no answer to CMD0, CMD8 or CMD55 in **native SD mode** (on CMD) and none in **SPI mode** (on DAT0): CMD
and DAT0 never left their pull-ups.  The FPGA's side is fine: each line driven low read back low, released read high.
So it is the card's contact, power or clock:

| step | you do | expect |
|---|---|---|
| 3a | turn the board over: J504 is mid-board on the **back**, its slot facing the Pmod end (silkscreen "card slides in here", "contacts toward the board").  Take the card out and put it back **with its gold contacts facing the board**, pushed in until it clicks and stays | the card latched, contacts toward the PCB.  (Pushed in by feel from the top, contacts facing away, it sits in the slot touching nothing: exactly the silence seen) |
| 3b | the Fluke 45, black on GND (a J602 even pin), red on **J504 pin 4** (VDD: the card's 4th contact) | 3.3 V |
| 3c | the board unpowered (both USB-C out), the Fluke on ohms: **J504 pin 3** (CMD) to **R6503**'s pad on that net, and **J504 pin 7** (DAT0) to **R6504**'s (each resistor's other pad is +3V3) | under 1 ohm each: the socket's pins are soldered.  (CLK, J504 pin 5, goes straight to the FPGA's T15 ball with nothing to probe on the way.) |
| 3d | try another microSD card | |

Then `python3 bringup/bench.py v1b --only sd` (it doesn't write the card).  Pass: the card answers CMD0/CMD8, its CID
reads back with a right CRC.  The tutorial's Linux (below) would like the card next: it is free to be overwritten.

## 4. Gigabit all the way to the PC (Jason, 2026-11-17)

**What is known (2026-11-16 night):**
- **bell is not the problem.** Its 192.168.8.207 is the ConnectX-5 at 100 Gbit/s, and the route to the board goes out
  of it. iperf3 between bell and szilard (192.168.8.180) gives 21.2 Gbit/s, and bell's card drops nothing
  (`rx_discards_phy` and `rx_out_of_buffer` 0).
- **The board is not the problem.**
  - Board A's PHY links at 1000 full, and the port it is plugged into advertises 1000BASE-T.
  - With `udp_awg.bit` at D = 0 the packet numbers advanced at the full 97,656 a second, and the board's own overrun
    count stayed 0 at every D (23:12).
  - The PC side takes every packet at 25 MS/s a channel: the tutorial's `iiod_bridge.py` with `fake_udp_awg.c`, 250 M
    pairs, none missing; GNU Radio both channels at 25.05 MS/s.
- **So the cap is on board A's branch.** About 10,900 packets a second (96 Mbit/s) arrive at bell whatever the board
  sends. One link or port between the box board A's cable plugs into and the fast switches runs at 100 Mbit/s, or a
  router's ports are in the path. The DHCP router at 192.168.8.1 is a GL.iNet (by its MAC's maker).

| from | to | cable |
|---|---|---|
| J401 **RJ45** | a gigabit port that reaches the fast switches without a 100 Mbit/s link | Ethernet (cat 5e or better) |

Then, in the tutorial repo's `src/verilog`:

```
make load-udp_awg
python3 iiod_bridge.py &
iio_attr -u ip:127.0.0.1 -d ecp5-adc sampling_frequency 25000000
python3 gr_iio_rate.py --rate 25e6 --seconds 10
```

And the other way, both DACs as a stream (non-cyclic) through GNU Radio's stock IIO sink, sent to the board alone
now that it answers ARP:

```
python3 gr_iio_tx_rate.py --rate 6250000 --seconds 10 --buffer 262144
```

Pass for the stream: the bridge's line "the board's ring ran dry 0 times while it played", at every rate up to
25 MS/s (`--rate 25000000`): the sender in C keeps one core spinning from 6.25 MS/s up, and on bell against the fake
board it never ran dry (the tutorial's E.09).

**Pass for the ADCs:** GNU Radio reports 25 MS/s a channel. The bridge's last line, when the stream stops, says **0 missing from
the numbering**, 0 dropped by a full ring, and 0 overruns. (If some go missing, `sudo sysctl -w
net.core.rmem_max=67108864` is the paste-block for you. It is 50 MB now, which held 10 s at full rate on bell.)

## 5. A monitor on mini-HDMI (stage 7's hdmi, 5 minutes)

| from | to | cable |
|---|---|---|
| J503 **mini-HDMI** | a monitor's HDMI input | mini-HDMI to HDMI |

First, unpowered, the Fluke's continuity check of the cable as BRINGUP.md's `hdmi` step says (pin 18 to F501, pin 17 to
GND).  Then `bench.py step hdmi`: the test pattern on the monitor.

## 6. Board B (visit 4)

Visits 0 and 1 on board B with `--board B` (BRINGUP.md), then configuration 0 on board B and the tutorial's
`dev/tools/boardtest/all.py`: every lesson on a second board in about a minute.

## 7. Tonight's instruments in these configurations (no extra cabling)

Late on 2026-11-16 the tutorial repo gained four instruments made of the board (its `dev/IDEAS.md` lists twenty): a
multichannel analyzer (`mca.sv`), the Allan deviation of the board's oscillators (`adev.py`), the two channels'
cross-spectrum (`xspec.py`), and **the board as an IIO device** (`iiod_bridge.py`: libiio's `iio_info`, `iio_readdev`,
and GNU Radio's IIO blocks, as for a PlutoSDR).  While a configuration above is cabled, the session can also run:

| configuration | what it adds | the PC runs (tutorial repo, `src/verilog`) |
|---|---|---|
| 1, step 1d (the SDG's CH2 at 10 MHz on CLK IN) | a **third oscillator** for the Allan deviation: TCXO, the Si5351's crystal and the SDG's reference, three pairs counted at once, which tells which one steps (tonight's record steps by about 0.1 ppm) | `adev.py` on `fastclk.bit` (counts CLK IN beside CLK0), 15 minutes |
| 1 (the SDG's CH1 on ADC A) | the generator seen through IIO in **GNU Radio Companion** (a live scope and spectrum, both channels) | `make load-udp_awg`, `python3 iiod_bridge.py &`, `gnuradio-companion ecp5_iio_scope.grc` |
| 1, with a BNC tee (the SDG's **noise** waveform into ADC A and ADC B at once) | the **cross-spectrum** of a common signal: the shared noise stands out of each ADC's own as the averages grow (idea 1; then the board's own resistors, idea 14, at visit 3) | `xspec.py` on `fast.bit` |
| 4 (gigabit to the PC) | the IIO stream at the board's full rate (both ADCs at 25 MS/s into GNU Radio), not the 1.5625 MS/s a 100 Mbit hop allows | the same as above, with `sampling_frequency=25000000` |
| 3 (a microSD that answers) | Linux could keep its root file system on the card instead of in RAM | (the tutorial's `src/linux`, once it boots over the network) |
