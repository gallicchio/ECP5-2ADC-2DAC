import sys, numpy as np
from scipy.optimize import least_squares
sys.path.insert(0, "/home/jason/mudd/133electronics/ecp5-2adc-2dac-tutorial/src/verilog")
from amodp import expected
FS = 25e6; T = 1 / FS; K = np.arange(-400, 401)

def ld(p):
    d = np.load(p); o = np.argsort(d["f"]); return d["f"][o], d["h"][o]

def folded(tile, f, delta, fc, board="ecp5", fs_dac=25e6, tilefn=None):
    """the lock-in's view: the DAC's staircase (held 1/fs_dac) through the tile and a chain pole fc, sampled at 25 MS/s"""
    fk = f[None, :] + K[:, None] * FS
    a = np.abs(fk)
    g = expected(tile, a.ravel(), board).reshape(a.shape) if tilefn is None else tilefn(a)
    g = np.where(fk < 0, np.conj(g), g)
    zoh = np.sinc(fk / fs_dac) * np.exp(-1j * np.pi * fk / fs_dac)
    ch = 1 / (1 + 1j * fk / fc)
    ph = np.exp(-2j * np.pi * fk * delta)
    return (g * zoh * ch * ph).sum(0) / (zoh * ch * ph).sum(0)

def misfit(h, m):
    r = np.log(m / h); return np.sqrt(np.mean(r.real ** 2)) * 8.686, np.degrees(np.sqrt(np.mean(r.imag ** 2)))
