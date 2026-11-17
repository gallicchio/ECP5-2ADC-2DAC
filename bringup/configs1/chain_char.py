"""The DAC -> cable -> ADC chain characterized through IIO at 25 MS/s (udp_awg.bit, the bridge): both paths at once,
DAC 1 -> ADC B and DAC 2 -> ADC A (2026-11-17's cabling).  Coherent: the DACs loop 16384 samples, the ADCs take 2^20
(64 loops), so every tone sits on its own bin.  (1) one tone at 7 frequencies and 3 levels: SINAD, SNR, THD, ENOB;
(2) two tones 97.7 kHz apart at 4 centres and 2 levels: IMD3 (2f1-f2, 2f2-f1) and IMD2 (f2-f1, f1+f2).  Levels in dBFS
of the ADC (2048 codes peak); DAC codes = 4 x ADC codes / 1.026 (the chain's gain)."""
import json, sys, time
import iio
import numpy as np

OUT = sys.argv[1]
N_DAC, FS, N = 16384, 25e6, 1 << 20
REP = N // N_DAC
PATHS = ((1, 1, "DAC 1 -> ADC B"), (2, 0, "DAC 2 -> ADC A"))     # (DAC, ADC channel index, name)
ctx = iio.Context("ip:127.0.0.1")
dac = ctx.find_device("ecp5-dac"); adc = ctx.find_device("ecp5-adc")
for c in dac.channels: c.enabled = True
adc.attrs["sampling_frequency"].value = "25000000"
for c in adc.channels: c.enabled = True
k = np.arange(N_DAC)


def play_and_capture(wave):                  # wave: float, ADC codes peak about 0 (the same on both DACs)
    p = np.empty((N_DAC, 2), np.uint16)
    d = np.clip(np.round(8192 + wave * 4 / 1.026), 0, 16383).astype(np.uint16)
    p[:, 0] = d; p[:, 1] = d
    db = iio.Buffer(dac, N_DAC, True); db.write(bytearray(p.tobytes())); db.push(); time.sleep(0.3)
    rb = iio.Buffer(adc, N, False); rb.refill()
    x = np.frombuffer(bytes(rb.read()), "<u2").reshape(-1, 2).astype(float)
    del rb, db
    return x


def spectrum(x):
    X = np.fft.rfft(x - x.mean()) / (len(x) / 2)
    return np.abs(X) ** 2                    # power per bin, in codes^2 (peak amplitude squared)


def fold(b):                                 # a bin above Nyquist folds back into the band
    b %= N
    return min(b, N - b)


def db(p, ref):
    return 10 * np.log10(p / ref)


res = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "sinad": [], "imd": []}
PARTS = sys.argv[2:] or ["sinad", "imd"]
FREQS = (0.1e6, 1e6, 3e6, 5e6, 7e6, 10e6, 12e6)
for lvl in ((-1, -6, -20) if "sinad" in PARTS else ()):
    for f in FREQS:
        kt = int(round(f / (FS / N_DAC)))
        a = 2048 * 10 ** (lvl / 20)
        x = play_and_capture(a * np.cos(2 * np.pi * kt * k / N_DAC))
        for dacn, ch, name in PATHS:
            P = spectrum(x[:, ch]); b0 = kt * REP
            ps = P[b0]
            harm = [P[fold(h * b0)] for h in range(2, 6)]
            pn = P[1:].sum() - ps
            pnh = pn - sum(harm)
            sinad = db(ps, pn); snr = db(ps, pnh); thd = db(sum(harm), ps)
            enob = (sinad - 1.76 + (0 - lvl)) / 6.02          # referred to full scale, as data sheets do
            res["sinad"].append(dict(path=name, f=kt * FS / N_DAC, dbfs=lvl, amp=2 * np.sqrt(ps), sinad=sinad, snr=snr, thd=thd, enob_fs=enob))
            print("%s %5.2f MHz %+3d dBFS: tone %6.1f codes pk; SINAD %5.1f dB, SNR %5.1f, THD %6.1f dBc, ENOB %.2f (at full scale)"
                  % (name, kt * FS / N_DAC / 1e6, lvl, np.sqrt(ps), sinad, snr, thd, enob), flush=True)
for lvl in ((-10, -20) if "imd" in PARTS else ()):
    for fc in (1e6, 3e6, 5e6, 10e6):
        kc = int(round(fc / (FS / N_DAC))); k1, k2 = kc - 32, kc + 32
        a = 2048 * 10 ** (lvl / 20)
        x = play_and_capture(a * (np.cos(2 * np.pi * k1 * k / N_DAC) + np.cos(2 * np.pi * k2 * k / N_DAC + 1.0)))
        for dacn, ch, name in PATHS:
            P = spectrum(x[:, ch]); b1, b2 = k1 * REP, k2 * REP
            pt = (P[b1] + P[b2]) / 2
            i3 = [db(P[fold(2 * b1 - b2)], pt), db(P[fold(2 * b2 - b1)], pt)]
            i2 = [db(P[fold(b2 - b1)], pt), db(P[fold(b1 + b2)], pt)]
            floor = db(np.median(P[b1 - 2000:b1 - 500]), pt)
            res["imd"].append(dict(path=name, fc=kc * FS / N_DAC, dbfs_each=lvl, imd3=i3, imd2=i2, floor=floor))
            print("%s two tones at %5.2f MHz, %+3d dBFS each: IMD3 %6.1f / %6.1f dBc, IMD2 %6.1f / %6.1f dBc (a bin's floor %6.1f)"
                  % (name, kc * FS / N_DAC / 1e6, lvl, i3[0], i3[1], i2[0], i2[1], floor), flush=True)
json.dump(res, open(OUT, "w"), indent=1)
