#!/usr/bin/env python3
"""Measure each AC-coupled HDMI pair from FPGA ball to receptacle."""

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
PAIRS = (
    ("TMDS clock", "GPDI_CK_P", "GPDI_CK_N"),
    ("TMDS data 0", "GPDI_D0_P", "GPDI_D0_N"),
    ("TMDS data 1", "GPDI_D1_P", "GPDI_D1_N"),
    ("TMDS data 2", "GPDI_D2_P", "GPDI_D2_N"),
)


def physical_name(logical_name):
    matches = [
        name
        for name in NET_NAMES
        if name == logical_name or name.endswith("/" + logical_name)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"{logical_name}: expected one net, found {matches}")
    return matches[0]


def copper_length(net_name):
    tracks = [track for track in BOARD.GetTracks() if track.GetNetname() == net_name]
    return sum(pcbnew.ToMM(track.GetLength()) for track in tracks), len(tracks)


def capacitor_partner(net_name):
    matches = []
    for footprint in BOARD.GetFootprints():
        if not footprint.GetReference().startswith("C"):
            continue
        pads = footprint.Pads()
        if len(pads) != 2 or not any(pad.GetNetname() == net_name for pad in pads):
            continue
        partner = next(pad.GetNetname() for pad in pads if pad.GetNetname() != net_name)
        matches.append((footprint.GetReference(), partner))
    if len(matches) != 1:
        raise RuntimeError(f"{net_name}: expected one AC-coupling capacitor, found {matches}")
    return matches[0]


for label, positive, negative in PAIRS:
    lengths = []
    print(label)
    for logical_name in (positive, negative):
        fpga_side = physical_name(logical_name)
        capacitor, connector_side = capacitor_partner(fpga_side)
        fpga_mm, fpga_segments = copper_length(fpga_side)
        connector_mm, connector_segments = copper_length(connector_side)
        total = fpga_mm + connector_mm
        lengths.append(total)
        print(
            f"  {logical_name:9} {capacitor:5} "
            f"FPGA {fpga_mm:7.3f} mm/{fpga_segments:d} segment(s), "
            f"HDMI {connector_mm:7.3f} mm/{connector_segments:d} segment(s), "
            f"total {total:7.3f} mm"
        )
    print(f"  pair skew: {abs(lengths[0] - lengths[1]):.3f} mm")
