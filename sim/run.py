#!/usr/bin/env python3
"""Run a SPICE deck through KiCad's bundled ngspice (the shared library; the
AppImage ships no ngspice executable) and print what the deck's .control
block prints.

    python3 sim/run.py sim/adc_frontend.cir [more.cir ...]
"""
import ctypes, os, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.expanduser("~/.local/kicad10/AppDir")
LIB = os.path.join(APP, "shared", "lib", "libngspice.so")
os.environ.setdefault("SPICE_LIB_DIR", os.path.join(APP, "shared", "lib", "ngspice"))

lines = []


@ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
def send_char(s, ident, user):
    t = s.decode("utf-8", "replace")
    if t.startswith("stdout "):
        t = t[7:]
    if t.strip() and not t.startswith("stderr Warning") and "Note:" not in t:
        lines.append(t)
    return 0


@ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
def send_stat(s, ident, user):
    return 0


@ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)
def controlled_exit(status, immediate, quit_, ident, user):
    return 0


def run(deck):
    ng = ctypes.CDLL(LIB)
    ng.ngSpice_Init(send_char, send_stat, controlled_exit, None, None, None, None)
    ng.ngSpice_Command.argtypes = [ctypes.c_char_p]
    del lines[:]
    ng.ngSpice_Command(("source " + os.path.abspath(deck)).encode())
    out = [l for l in lines if not l.startswith("stderr")]
    return "\n".join(out)


if __name__ == "__main__":
    for deck in sys.argv[1:]:
        print("=== " + os.path.basename(deck))
        print(run(deck))
