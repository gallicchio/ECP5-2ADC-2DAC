#!/usr/bin/env python3
"""Measure routed copper for each RGMII signal on both sides of its 22-ohm resistor."""

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
GROUPS = {
    "MAC-to-PHY transmit": (
        "ETH_TXC",
        "ETH_TX_CTL",
        "ETH_TXD0",
        "ETH_TXD1",
        "ETH_TXD2",
        "ETH_TXD3",
    ),
    "PHY-to-MAC receive": (
        "ETH_RXC",
        "ETH_RX_CTL",
        "ETH_RXD0",
        "ETH_RXD1",
        "ETH_RXD2",
        "ETH_RXD3",
    ),
}


def copper_length(net_name):
    tracks = [track for track in BOARD.GetTracks() if track.GetNetname() == net_name]
    return sum(pcbnew.ToMM(track.GetLength()) for track in tracks), len(tracks)


def physical_name(logical_name):
    matches = [
        name
        for name in NET_NAMES
        if name == logical_name or name.endswith("/" + logical_name)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"{logical_name}: expected one net, found {matches}")
    return matches[0]


def resistor_partner(net_name):
    matches = []
    for footprint in BOARD.GetFootprints():
        if not footprint.GetReference().startswith("R"):
            continue
        pads = footprint.Pads()
        if len(pads) != 2 or not any(pad.GetNetname() == net_name for pad in pads):
            continue
        partner = next(pad.GetNetname() for pad in pads if pad.GetNetname() != net_name)
        matches.append((footprint.GetReference(), partner))
    if len(matches) != 1:
        raise RuntimeError(f"{net_name}: expected one 22-ohm series resistor, found {matches}")
    return matches[0]


for group, signals in GROUPS.items():
    print(group)
    totals = []
    for signal in signals:
        mac_side = physical_name(signal)
        resistor, phy_side = resistor_partner(mac_side)
        mac_mm, mac_segments = copper_length(mac_side)
        phy_mm, phy_segments = copper_length(phy_side)
        total = mac_mm + phy_mm
        totals.append(total)
        print(
            f"  {signal:11} {resistor:5} "
            f"MAC {mac_mm:7.3f} mm/{mac_segments:d} segment(s), "
            f"PHY {phy_mm:7.3f} mm/{phy_segments:d} segment(s), "
            f"total {total:7.3f} mm"
        )
    print(
        f"  copper spread: min {min(totals):.3f} mm, "
        f"max {max(totals):.3f} mm, skew {max(totals) - min(totals):.3f} mm"
    )
