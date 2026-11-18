# Record both ADCs with fast.bit (62.5 MS/s), `records` captures, and keep every raw code for later analysis.
#   python3 noise_rec.py LABEL [records]
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.join(os.environ.get("ECP5_TUTORIAL", os.path.expanduser("~/mudd/133electronics/ecp5-2adc-2dac-tutorial")),
                                "src", "verilog"))          # the tutorial's fast.py (fast.bit loaded)
import fast
label = sys.argv[1]; k = int(sys.argv[2]) if len(sys.argv) > 2 else 400
fa = fast.Fast(fast.find_port())
fs = fa.rate(2)
fa.dacs(0)
time.sleep(0.05)
t0 = time.strftime("%Y-%m-%d %H:%M:%S")
recs = np.array([fa.capture() for _ in range(k)])
t1 = time.strftime("%H:%M:%S")
fa.dacs(3)
np.savez_compressed("board_a_%s.npz" % label, rec=recs.astype(np.int16), fs=fs, t0=t0, t1=t1, label=label)
n = recs.shape[1]; w = np.hanning(n)
A = np.fft.rfft((recs[:, :, 0] - recs[:, :, 0].mean(1, keepdims=True)) * w, axis=1)
B = np.fft.rfft((recs[:, :, 1] - recs[:, :, 1].mean(1, keepdims=True)) * w, axis=1)
norm = fs * (w ** 2).sum() / 2
f = np.fft.rfftfreq(n, 1 / fs)
paa = (np.abs(A) ** 2).mean(0) / norm; pbb = (np.abs(B) ** 2).mean(0) / norm; pab = (A * np.conj(B)).mean(0) / norm
band = (f > 100e3) & (f < 5e6)
print("%s: %d records of %d pairs at %.1f MS/s, %s-%s" % (label, k, n, fs / 1e6, t0[11:], t1))
print("  mean codes A %.1f B %.1f; rms A %.2f B %.2f codes" % (recs[:, :, 0].mean(), recs[:, :, 1].mean(), recs[:, :, 0].std(), recs[:, :, 1].std()))
print("  0.1-5 MHz medians: A %.3g, B %.3g codes^2/Hz; Re(cross) %.3g, |cross| %.3g; coherence %.4f"
      % (np.median(paa[band]), np.median(pbb[band]), np.median(pab.real[band]), np.median(np.abs(pab[band])),
         np.median(np.abs(pab[band]) ** 2 / (paa[band] * pbb[band]))))
