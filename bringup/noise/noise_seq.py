# Record both ADCs continuously (fast.bit, 62.5 MS/s) in segments of `per` captures, for `minutes`, while Jason moves
# SW101 from one resistor to the next; each segment's raw codes and spectra are saved with its start and end time, so
# which resistor was on is read from the data afterwards.
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.join(os.environ.get("ECP5_TUTORIAL", os.path.expanduser("~/mudd/133electronics/ecp5-2adc-2dac-tutorial")),
                                "src", "verilog"))          # the tutorial's fast.py (fast.bit loaded)
import fast
minutes = float(sys.argv[1]); per = int(sys.argv[2])
os.makedirs("seq", exist_ok=True)
fa = fast.Fast(fast.find_port()); fs = fa.rate(2); fa.dacs(0); time.sleep(0.05)
T0 = time.time(); i = 0
while time.time() - T0 < 60 * minutes:
    t0 = time.time(); recs = np.array([fa.capture() for _ in range(per)]); t1 = time.time()
    n = recs.shape[1]; w = np.hanning(n); norm = fs * (w ** 2).sum() / 2
    A = np.fft.rfft((recs[:, :, 0] - recs[:, :, 0].mean(1, keepdims=True)) * w, axis=1)
    B = np.fft.rfft((recs[:, :, 1] - recs[:, :, 1].mean(1, keepdims=True)) * w, axis=1)
    paa = (np.abs(A) ** 2).mean(0) / norm; pbb = (np.abs(B) ** 2).mean(0) / norm; pab = (A * np.conj(B)).mean(0) / norm
    np.savez_compressed("seq/seg_%03d.npz" % i, rec=recs.astype(np.int16), fs=fs, t0=t0, t1=t1, paa=paa, pbb=pbb, pab=pab)
    f = np.fft.rfftfreq(n, 1 / fs); band = (f > 100e3) & (f < 5e6)
    print("%03d %s-%s  rms A %6.2f B %6.2f  A %.3g B %.3g Re(AB*) %.3g codes^2/Hz  mean A %.0f B %.0f" % (
        i, time.strftime("%H:%M:%S", time.localtime(t0)), time.strftime("%H:%M:%S", time.localtime(t1)),
        recs[:, :, 0].std(), recs[:, :, 1].std(), np.median(paa[band]), np.median(pbb[band]), np.median(pab.real[band]),
        recs[:, :, 0].mean(), recs[:, :, 1].mean()), flush=True)
    i += 1
fa.dacs(3)
print(time.strftime("%H:%M:%S"), "done", flush=True)
