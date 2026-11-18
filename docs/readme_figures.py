#!/usr/bin/env python3
"""The block diagram the top-level README shows (docs/images/readme_blocks.svg).

    python3 docs/readme_figures.py            write the SVG
    python3 docs/readme_figures.py --png DIR  also write a PNG into DIR, to look at

It explains the board; the part numbers are gen/parts.py's and the rates are the parts' own.
"""
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "images")
PNG_DIR = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None
# the data-viz reference palette's first three hues, and its light-surface chrome
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURFACE, INK, INK2, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#c3c2b7"


def blocks():
    W, Hh, U = 140, 78, 0.0845                             # the drawing's units, and inches a unit
    fig = plt.figure(figsize=(W * U, Hh * U))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, Hh); ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, Hh, facecolor=SURFACE, edgecolor="none"))
    FT, FS = 11.0, 9.6

    def box(x, y, w, h, title, sub=None, fill="#ffffff"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.9", facecolor=fill, edgecolor=AXIS, linewidth=0.9))
        if sub:
            ax.text(x + w / 2, y + h * 0.65, title, ha="center", va="center", fontsize=FT, color=INK, fontweight="bold")
            ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=FS, color=INK2)
        else:
            ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=FT, color=INK, fontweight="bold")

    def arrow(p0, p1, color, both=False, lw=2.0):
        ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="<|-|>" if both else "-|>", mutation_scale=11, color=color, linewidth=lw, shrinkA=0, shrinkB=0, zorder=3))

    def jack(x, y, label, side):
        ax.add_patch(FancyBboxPatch((x - 1.3, y - 1.3), 2.6, 2.6, boxstyle="round,pad=0,rounding_size=1.3", facecolor="#ffffff", edgecolor=INK2, linewidth=1.3))
        ax.text(x - 2.6 if side == "l" else x + 2.6, y, label, ha="right" if side == "l" else "left", va="center", fontsize=FS, color=INK, fontweight="bold")

    H = 8.6
    # the FPGA in the middle
    ax.add_patch(FancyBboxPatch((58, 18), 26, 46, boxstyle="round,pad=0,rounding_size=1.1", facecolor="#f3f2ee", edgecolor=AXIS, linewidth=0.9))
    ax.text(71, 59.5, "FPGA", ha="center", va="center", fontsize=12.5, color=INK, fontweight="bold")
    ax.text(71, 56.6, "Lattice ECP5-25F", ha="center", va="center", fontsize=FS, color=INK2)
    for k, s in enumerate(("your Verilog", "or a RISC-V core", "running Linux")):
        ax.text(71, 47.5 - 3.0 * k, s, ha="center", va="center", fontsize=FS, color=INK2)
    ax.text(71, 34.0, "built with Yosys", ha="center", va="center", fontsize=FS, color=INK, fontweight="bold")
    ax.text(71, 31.0, "and nextpnr", ha="center", va="center", fontsize=FS, color=INK, fontweight="bold")
    # analog in (left, top): two channels
    yA, yB = 62, 50
    for y, name in ((yA, "ADC A IN"), (yB, "ADC B IN")):
        jack(15, y, name, "l")
        box(20, y - H / 2, 15, H, "front end", "×1 or ×10, DC")
        arrow((16.3, y), (20, y), ORANGE)
    box(39, 46, 15, 20.5, "", " ")
    ax.text(46.5, 60.5, "dual ADC", ha="center", va="center", fontsize=FT, color=INK, fontweight="bold")
    ax.text(46.5, 57.3, "AD9238", ha="center", va="center", fontsize=FS, color=INK2)
    ax.text(46.5, 53.0, "2 x 12 bits", ha="center", va="center", fontsize=FS, color=INK2)
    ax.text(46.5, 50.0, "65 MS/s", ha="center", va="center", fontsize=FS, color=INK2)
    for y in (yA, yB):
        arrow((35, y), (39, y), ORANGE); arrow((54, y), (58, y), ORANGE)
    # analog out (left, bottom): two channels
    y1, y2 = 32, 20
    box(39, 16, 15, 20.5, "", " ")
    ax.text(46.5, 30.5, "dual DAC", ha="center", va="center", fontsize=FT, color=INK, fontweight="bold")
    ax.text(46.5, 27.3, "AD9767", ha="center", va="center", fontsize=FS, color=INK2)
    ax.text(46.5, 23.0, "2 x 14 bits", ha="center", va="center", fontsize=FS, color=INK2)
    ax.text(46.5, 20.0, "125 MS/s", ha="center", va="center", fontsize=FS, color=INK2)
    for y, name in ((y1, "DAC 1 OUT"), (y2, "DAC 2 OUT")):
        jack(15, y, name, "l")
        box(20, y - H / 2, 15, H, "output amp", "±1 V into 50 Ω")
        arrow((58, y), (54, y), BLUE); arrow((39, y), (35, y), BLUE); arrow((20, y), (16.3, y), BLUE)
    # clocks (bottom)
    box(58, 4.5, 26, H, "clocks", "25 MHz TCXO, Si5351")
    arrow((71, 4.5 + H), (71, 18), AQUA, lw=1.6)
    jack(15, 8.8, "CLK IN, CLK OUT", "l")
    arrow((16.3, 8.8), (58, 8.8), AQUA, both=True, lw=1.6)
    ax.text(37, 10.6, "lock two boards together", ha="center", va="center", fontsize=FS, color=INK2)
    # digital (right)
    rows = [(63.5, "gigabit Ethernet", "RTL8211F"), (52.5, "USB-C: JTAG, serial", "FT2232H"), (41.5, "32 MB SDRAM", "16 MB flash"),
            (30.5, "mini-HDMI, microSD", "second USB-C"), (19.5, "two Pmods", "8 LEDs, 2 buttons")]
    for y, t, s in rows:
        box(90, y - H / 2, 26, H, t, s)
        arrow((84, y), (90, y), INK2, both=True, lw=1.4)
    jack(121, 63.5, "to a network", "r"); arrow((116, 63.5), (119.7, 63.5), INK2, both=True, lw=1.4)
    jack(121, 52.5, "to a PC, and 5 V in", "r"); arrow((116, 52.5), (119.7, 52.5), INK2, both=True, lw=1.4)
    # legend
    x = 2.5
    for c, s, w in ((ORANGE, "analog in", 22), (BLUE, "analog out", 23), (AQUA, "clocks: every sample clock comes from the FPGA", 0)):
        ax.plot([x, x + 4], [74.6, 74.6], color=c, lw=2.4, solid_capstyle="round")
        ax.text(x + 5.2, 74.6, s, ha="left", va="center", fontsize=FS, color=INK2)
        x += w
    plt.rcParams["svg.hashsalt"] = "readme_blocks"
    fig.savefig(os.path.join(OUT, "readme_blocks.svg"), format="svg", bbox_inches="tight", pad_inches=0.12, facecolor=SURFACE, metadata={"Date": None})
    if PNG_DIR:
        fig.savefig(os.path.join(PNG_DIR, "readme_blocks.png"), dpi=110, bbox_inches="tight", pad_inches=0.12, facecolor=SURFACE)
    plt.close(fig)
    print("wrote docs/images/readme_blocks.svg")


if __name__ == "__main__":
    blocks()
