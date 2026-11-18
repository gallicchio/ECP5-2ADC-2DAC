#!/usr/bin/env python3
"""Report routed SDR SDRAM copper lengths and their skew against the clock."""

import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
APP = Path.home() / ".local" / "kicad10" / "AppDir"

if os.environ.get("_INSIDE_KICAD_PY") != "1":
    env = dict(
        os.environ,
        _INSIDE_KICAD_PY="1",
        LD_LIBRARY_PATH=f"{APP}/usr/lib:{APP}/shared/lib",
        PYTHONPATH=f"{APP}/shared/lib/python3.11/dist-packages",
    )
    sys.exit(subprocess.call([f"{APP}/usr/bin/python3.11", __file__], env=env))

import pcbnew


BOARD = pcbnew.LoadBoard(str(ROOT / "ECP5-2ADC-2DAC.kicad_pcb"))
NET_NAMES = tuple(str(name) for name in BOARD.GetNetsByName())


def copper_length(net_name):
    tracks = [track for track in BOARD.GetTracks() if track.GetNetname() == net_name]
    return sum(pcbnew.ToMM(track.GetLength()) for track in tracks), len(tracks)


def logical_name(net_name):
    return net_name.rsplit("/", 1)[-1]


sdram_nets = sorted(name for name in NET_NAMES if logical_name(name).startswith("SDRAM_"))
lengths = {}
for net_name in sdram_nets:
    length, segments = copper_length(net_name)
    lengths[logical_name(net_name)] = length
    print(f"{logical_name(net_name):14} {length:7.3f} mm/{segments:d} segment(s)")

clock = lengths["SDRAM_CLK"]
all_lengths = tuple(lengths.values())
nonclock = tuple(length for name, length in lengths.items() if name != "SDRAM_CLK")
print()
print(f"all-net spread: {max(all_lengths) - min(all_lengths):.3f} mm")
print(f"clock length: {clock:.3f} mm")
print(
    f"clock-to-other range: {min(nonclock) - clock:.3f} to "
    f"{max(nonclock) - clock:.3f} mm"
)
