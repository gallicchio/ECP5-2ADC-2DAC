#!/bin/bash
# Open a board or schematic in the KiCad 10 GUI, ON XWAYLAND.
#
#   ./kicad-gui.sh ECP5-2ADC-2DAC.kicad_pcb
#   ./kicad-gui.sh                 # just the project manager
#   KICAD=9 ./kicad-gui.sh ...     # the other AppImage
#
# WHY THIS EXISTS.  IcepiZeroADCDAC Prompt 29 (and this board, Prompt 2): no middle-wheel scroll, layer visibility not
# repainting until you zoom, a schematic page change not repainting until you
# zoom, and the pointer freezing for a second or two at a time.  None of that
# is the board -- it is KiCad's OpenGL canvas talking to a NATIVE WAYLAND
# surface.  This session is GNOME on Wayland (XDG_SESSION_TYPE=wayland), the
# AppImage ships its own GTK3 and its own libwayland-client, so it does NOT
# fall back to X11 the way a distribution build without Wayland support would,
# and KiCad's canvas is the accelerated one (canvas_type: 2 in
# ~/.config/kicad/10.0/kicad_common.json).
#
# Three separate things go wrong in that combination, and all three are known
# upstream rather than particular to this machine:
#
#   * SCROLL.  Wayland delivers pointer-button 2 and the "axis" events for a
#     wheel through different protocol objects, and wxWidgets' GTK3 backend
#     does not synthesise the middle-drag KiCad binds panning to.  On X11 the
#     same events arrive as button presses and it works.
#   * REPAINT.  The GAL canvas damages a region and asks GTK to blit it; under
#     Wayland the compositor owns the buffer swap, and a repaint triggered by
#     something other than a view transform (a layer toggled, a sheet opened)
#     is dropped until the next real transform -- which is why ZOOMING fixes
#     it every time.  Zoom changes the view matrix, so the whole canvas is
#     redrawn and the compositor gets a new buffer.
#   * FREEZES.  Not KiCad's: `dmesg` shows this machine re-enumerating the
#     88XXau_wfb USB WiFi dongle on hub 5-3 over and over, with a WARNING out
#     of the driver each time.  A USB re-enumeration stalls the input stack
#     for about as long as the pointer stalls.  Unplugging that dongle is the
#     test; it has nothing to do with KiCad or with this board.
#
# GDK_BACKEND=x11 puts the whole application on XWayland, which is running
# already (/usr/bin/Xwayland, DISPLAY=:0), and the first two go away.  The
# cost is that the window is scaled by XWayland rather than drawn natively,
# so on a HiDPI screen it is slightly softer.  That is the trade.
#
# If it is still slow after this, the next thing to try is the software
# canvas: Preferences -> Common -> Graphics -> Fallback, or set
# graphics.canvas_type to 1 in kicad_common.json.  This board is not big --
# see README, Prompt 29 -- so it should not need it.
set -euo pipefail
VER="${KICAD:-10}"
A="${KICAD_APPDIR:-$HOME/.local/kicad${VER}/AppDir}"
if [ ! -d "$A" ]; then
    echo "error: $A not found.  Extract the AppImage first:" >&2
    echo "  cd ~/.local && mkdir kicad${VER} && cd kicad${VER} \\" >&2
    echo "    && ~/.local/bin/kicad-${VER}*-x86_64.AppImage --appimage-extract \\" >&2
    echo "    && mv squashfs-root AppDir" >&2
    exit 1
fi
export GDK_BACKEND=x11
export QT_QPA_PLATFORM=xcb          # for the 3D viewer's Qt bits, if any
unset WAYLAND_DISPLAY               # belt and braces: GTK prefers it if set
export LD_LIBRARY_PATH="$A/usr/lib:$A/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export KICAD${VER}_FOOTPRINT_DIR="$A/share/kicad/footprints"
export KICAD${VER}_SYMBOL_DIR="$A/share/kicad/symbols"
export KICAD${VER}_3DMODEL_DIR="$A/share/kicad/3dmodels"
export KICAD_FOOTPRINT_DIR="$A/share/kicad/footprints"
export KICAD_SYMBOL_DIR="$A/share/kicad/symbols"

# Which binary: the file extension decides, so that one script opens either.
BIN="$A/usr/bin/kicad"
if [ $# -gt 0 ]; then
    case "$1" in
        *.kicad_pcb) BIN="$A/usr/bin/pcbnew" ;;
        *.kicad_sch) BIN="$A/usr/bin/eeschema" ;;
    esac
fi
exec "$BIN" "$@"
