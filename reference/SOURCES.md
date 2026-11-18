# Reference designs consulted (cloned 2026-10-01, shallow, not committed)

Clone them again with `tools/fetch_references.sh`.  Each row is the commit that was read.

| directory | repository | commit | date | licence | what was taken from it |
| --- | --- | --- | --- | --- | --- |
| `ulx3s/` | https://github.com/emard/ulx3s | 6a92cec6b177191c5b0f80e260013a1f8ec147dd | 2025-04-27 | BSD | GPDI (HDMI) resistor network, direct-USB-to-FPGA circuit, 12-bit ADC ideas |
| `butterstick-hardware/` | https://github.com/butterstick-fpga/butterstick-hardware | 0694ddfa9824a07f0c6c6981186e45f80187659c | 2023-09-19 | CERN-OHL | KSZ9031 RGMII Ethernet block, DDR3L (not used), SYZYGY |
| `orangecrab-hardware/` | https://github.com/orangecrab-fpga/orangecrab-hardware | c511d569fe2af39467041f888bc231020f40c6ac | 2024-05-08 | CERN-OHL-P / MIT | ECP5 power tree and decoupling on 6 layers, DDR3L (not used) |
| `icesugar-pro/` | https://github.com/wuxx/icesugar-pro | 087e48d9e0b0a0168ce165a961cba306335c4cf2 | 2025-09-16 | — (PDF schematic only) | SODIMM core module concept, 32 MB SDRAM + 32 MB flash on an LFE5U-25F |
| `icepi-zero/` | https://github.com/cheyao/icepi-zero | e01faa2bd35dcb7269827f8420b845d46c78c869 | 2026-09-18 | CERN-OHL-S | **the base we build on**: the LFE5U-25F-6BG256C, its sysCONFIG/JTAG/flash wiring, TLV62569 power tree, SDRAM pin style, USB-C, microSD, mini-HDMI parts that JLCPCB stocks |

`lambdaconcept/ecpix-5` has no public hardware repository (only docs: https://github.com/lambdaconcept/ecpix5-readthedocs); its DP83867-style RGMII block was not needed.
