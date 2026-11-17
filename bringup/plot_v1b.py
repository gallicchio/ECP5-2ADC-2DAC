#!/usr/bin/env python3
"""plot_v1b.py: the figures of a visit-1B run, from what bench.py recorded.

    python3 bringup/plot_v1b.py                    # board A, today: figs/board_A/<date>/
    python3 bringup/plot_v1b.py --sim              # the simulated bench's run: figs/sim/board_A/<date>/
    python3 bringup/plot_v1b.py --board B --date 2026-11-17

It reads data/[sim/]board_X/<date>.jsonl, the visit's log, and the captures it names (.npz), and writes:
  dc_transfer.png        the DC path DAC -> SMA -> ADC: the ADC's mean at seven DAC codes against the ideal line, and
                         each point's distance from the fitted line
  <capture>.png          each capture (v1b_noise, v1b_sine_1MHz, and any later ones): the first microseconds in ADC
                         codes, and the spectrum in dB relative to full scale with its largest tone and spur marked
  phase_scan.png         the ADC capture-phase scan: the sine-fit residual at every phase and edge, per sample rate
The data stay on the PC (bringup/data is not in git); the figures are small and are kept in the repo.
"""
import argparse
import datetime as dt
import glob
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ADC_FULL = 4096          # AD9238: 12 bits, 2 V p-p full scale
ADC_MID = 2048
DAC_MID = 8192           # AD9767: 14 bits; the ideal ADC code is 2048 + (DAC code - 8192) / 4 through the loop cable


def records(path):
    out = []
    with open(path) as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def latest(recs, kind, key=None):
    """The last record of `kind`, or with `key`, the last one per value of key(record)."""
    hits = [r for r in recs if r.get("kind") == kind]
    if key is None:
        return hits[-1] if hits else None
    by = {}
    for r in hits:
        by[key(r)] = r
    return by


def plot_dc(dc, out, title):
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1.3]})
    codes_all = []
    for (port, ch), r in sorted(dc.items()):
        codes, means = np.array(r["codes"], float), np.array(r["means"], float)
        codes_all += list(codes)
        p = np.polyfit(codes, means, 1)
        ax.plot(codes, means, "o-", label="DAC %d -> ADC %s: slope %.4f (ideal 0.25), offset %+.1f codes, worst %.2f"
                % (port, ch.upper(), r.get("slope", p[0] * 4) * 0.25 if r.get("slope") else p[0], r.get("offset", 0), r.get("worst", 0)))
        ax2.plot(codes, means - np.polyval(p, codes), "o-", label="ADC %s" % ch.upper())
    if codes_all:
        c = np.linspace(min(codes_all), max(codes_all), 2)
        ax.plot(c, ADC_MID + (c - DAC_MID) / 4.0, "k--", lw=1, label="ideal: 2048 + (DAC - 8192) / 4")
    ax.set_ylabel("ADC mean (codes)")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    ax2.axhline(0, color="k", lw=0.8)
    ax2.set_xlabel("DAC code (14 bits)")
    ax2.set_ylabel("from the fit (codes)")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


def spectrum_db(x):
    x = np.asarray(x, float) - np.mean(x)
    w = np.blackman(len(x))
    s = np.abs(np.fft.rfft(x * w)) / (w.sum() / 2)              # a sine of amplitude A shows A
    full = ADC_FULL / 2.0                                         # a full-scale sine's amplitude
    return 20 * np.log10(np.maximum(s, 1e-9) / full)


def plot_capture(npz, out, title):
    d = np.load(npz)
    t = d["t"].astype(float)
    dt_s = float(np.median(np.diff(t))) if len(t) > 1 else 1 / 25e6
    if dt_s > 1e-3:                                               # t in samples, not seconds
        dt_s = 1 / 25e6
    rate = 1 / dt_s
    meta = json.loads(str(d["meta"])) if "meta" in d.files else {}
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 7.5))
    n_show = min(len(t), int(4e-6 * rate) or 100)
    for name, colour in (("a", "C0"), ("b", "C1")):
        x = d[name].astype(float)
        ax.plot((np.arange(n_show) * dt_s) * 1e6, x[:n_show], ".-", color=colour, ms=3, lw=0.8,
                label="ADC %s: mean %.1f, std %.2f codes, min %d, max %d, OTR %d" % (name.upper(), x.mean(), x.std(), x.min(), x.max(),
                                                                                   int(np.sum(d["otr_" + name]))))
        db = spectrum_db(x)
        f = np.fft.rfftfreq(len(x), dt_s) / 1e6
        ax2.plot(f, db, color=colour, lw=0.7, label="ADC %s" % name.upper())
        k = int(np.argmax(db[3:])) + 3
        ax2.annotate("%.3f MHz, %.1f dBFS" % (f[k], db[k]), (f[k], db[k]), textcoords="offset points", xytext=(5, 5 + (12 if name == "b" else 0)),
                     fontsize=8, color=colour)
    ax.set_xlabel("time (us)")
    ax.set_ylabel("ADC code")
    ax.set_title("%s   (%d samples at %.0f MS/s%s)" % (title, len(t), rate / 1e6,
                                                     ("; DAC %s" % ", ".join("%s %.4f MHz" % (k.upper(), v / 1e6) for k, v in meta.get("dac_freq", {}).items()))
                                                     if meta.get("dac_freq") else ""))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    ax2.set_xlabel("frequency (MHz)")
    ax2.set_ylabel("dBFS (Blackman window)")
    ax2.set_ylim(-140, 5)
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


def plot_phase(rec, out, title):
    series = {}
    for key, v in rec["residuals"].items():
        rate, edge, phase = key.split("/")
        series.setdefault((float(rate), edge), []).append((int(phase), v))
    fig, ax = plt.subplots(figsize=(9, 5))
    for (rate, edge), pts in sorted(series.items()):
        pts.sort()
        ax.plot([p for p, _ in pts], [v for _, v in pts], "o-", label="%g MS/s, %s edge" % (rate, edge))
    ax.set_xlabel("capture phase step")
    ax.set_ylabel("sine-fit residual (codes rms)")
    ax.set_yscale("log")
    ax.set_title(title)
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="A")
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()
    ddir = os.path.join(HERE, "data", "sim" if args.sim else "", "board_%s" % args.board)
    log = os.path.join(ddir, args.date + ".jsonl")
    outdir = os.path.join(HERE, "figs", "sim" if args.sim else "", "board_%s" % args.board, args.date)
    os.makedirs(outdir, exist_ok=True)
    recs = records(log)
    who = "board %s%s, %s" % (args.board, " (simulated)" if args.sim else "", args.date)
    made = []
    dc = latest(recs, "dc_transfer", key=lambda r: (r["port"], r["channel"]))
    if dc:
        p = os.path.join(outdir, "dc_transfer.png")
        plot_dc(dc, p, "DC transfer DAC -> SMA cable -> ADC, " + who)
        made.append(p)
    caps = {}
    for r in recs:
        if r.get("kind") == "capture" and r.get("path"):
            name = os.path.basename(r["path"]).split("_", 2)[-1].rsplit(".", 1)[0]
            caps[name] = os.path.join(HERE, r["path"])
    for name, path in sorted(caps.items()):
        if os.path.exists(path):
            p = os.path.join(outdir, name + ".png")
            plot_capture(path, p, "%s, %s" % (name, who))
            made.append(p)
    ph = latest(recs, "phase_scan")
    if ph and ph.get("residuals"):
        p = os.path.join(outdir, "phase_scan.png")
        plot_phase(ph, p, "ADC capture-phase scan, " + who)
        made.append(p)
    for p in made:
        print(os.path.relpath(p, os.path.dirname(HERE)))
    if not made:
        print("nothing to plot in %s" % log)


if __name__ == "__main__":
    main()
