"""Record N s of 1 ms means of both ADCs through IIO (DACs at mid-scale) and look for ADC B's two-level steps."""
import sys, time, iio, numpy as np
from scipy.ndimage import median_filter
secs, out = float(sys.argv[1]), sys.argv[2]
ctx = iio.Context("ip:127.0.0.1")
dac = ctx.find_device("ecp5-dac")
for ch in dac.channels: ch.enabled = True
db = iio.Buffer(dac, 8192, True); db.write(bytearray(np.full((8192, 2), 8192, np.uint16).tobytes())); db.push()
adc = ctx.find_device("ecp5-adc"); adc.attrs["sampling_frequency"].value = "1562500"
for ch in adc.channels: ch.enabled = True
rb = iio.Buffer(adc, 1 << 18, False); means = []; carry = np.empty((0, 2)); total = 0
while total < secs * 1562500:
    rb.refill(); a = np.frombuffer(bytes(rb.read()), "<u2").reshape(-1, 2).astype(float); total += len(a)
    a = np.concatenate([carry, a]); k = len(a) // 1562
    means.append(a[:k * 1562].reshape(k, 1562, 2).mean(1)); carry = a[k * 1562:]
del rb, db
m = np.concatenate(means); np.save(out, m)
k = len(m) // 10; m10 = m[:k * 10].reshape(k, 10, 2).mean(1)
for c in (0, 1):
    v = m10[:, c] - np.median(m10[:, c])
    s = median_filter(v, 9); lo, hi = np.percentile(s, 5), np.percentile(s, 95)
    st = (s < (lo + hi) / 2).astype(int); ed = np.flatnonzero(np.diff(st) != 0)
    print("ADC %s: mean %.2f; 10 ms means %.3f codes rms; 5th-95th percentile of a 90 ms median %.3f apart; %d crossings of the midpoint"
          % ("AB"[c], np.median(m10[:, c]), v.std(), hi - lo, len(ed)))
    if len(ed) > 1:
        d = np.diff(ed) / 100.0
        print("   gaps between crossings / 1.8992 s: %s" % np.round(d / 1.8992, 2)[:30])
