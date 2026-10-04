#!/bin/bash
# Shallow-clone the open-source boards this design was studied against.  See reference/SOURCES.md.
set -e
cd "$(dirname "$0")/../reference"
for r in emard/ulx3s butterstick-fpga/butterstick-hardware orangecrab-fpga/orangecrab-hardware wuxx/icesugar-pro cheyao/icepi-zero; do
  n=$(basename "$r"); [ -d "$n" ] || git clone -q --depth 1 "https://github.com/$r.git" "$n"
done
