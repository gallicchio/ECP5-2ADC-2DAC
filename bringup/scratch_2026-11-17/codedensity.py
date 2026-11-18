"""ADC code density through IIO: DAC n plays a triangle a little past the ADC's full scale (a loop of L samples, L odd so
the ADC's samples walk through every level), the ADC streams at 25 MS/s; the histogram of each channel's codes, its DNL
and INL (codes 8 .. 4087, the clipped ends left out)."""
import sys, time, iio, numpy as np
dacn, ch, secs, out = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
ctx = iio.Context("ip:127.0.0.1")
dac = ctx.find_device("ecp5-dac"); adc = ctx.find_device("ecp5-adc")
for c in dac.channels: c.enabled = True
L = 16381
k = np.arange(L)
tri = 1 - 2 * np.abs(2 * (k / L) - 1)                     # -1 .. +1 .. -1
p = np.full((L, 2), 8192, np.uint16)
p[:, dacn - 1] = np.clip(np.round(8192 + 8191.5 * tri), 0, 16383)
db = iio.Buffer(dac, L, True); db.write(bytearray(p.tobytes())); db.push(); time.sleep(0.5)
adc.attrs["sampling_frequency"].value = "25000000"
for c in adc.channels: c.enabled = True
rb = iio.Buffer(adc, 1 << 20, False)
h = np.zeros(4096, np.int64); got = 0
while got < secs * 25e6:
    rb.refill(); x = np.frombuffer(bytes(rb.read()), "<u2").reshape(-1, 2)[:, ch]
    h += np.bincount(x, minlength=4096)[:4096]; got += len(x)
del rb, db
np.save(out, h)
lo, hi = 8, 4088
hh = h[lo:hi].astype(float)
dnl = hh / hh.mean() - 1
inl = np.cumsum(dnl) - np.linspace(0, np.cumsum(dnl)[-1], len(dnl))      # end-point fit
print("%d samples; codes 0 and 4095 hold %d and %d (clipped); codes %d..%d: %.0f counts each on average"
      % (h.sum(), h[0], h[4095], lo, hi - 1, hh.mean()))
print("DNL %+.2f .. %+.2f LSB (rms %.3f); INL (end points) %+.1f .. %+.1f LSB" % (dnl.min(), dnl.max(), dnl.std(), inl.min(), inl.max()))
for a, bnd in ((8, 512), (512, 1024), (1024, 3072), (3072, 3584), (3584, 4088)):
    seg = h[a:bnd].astype(float)
    print("   codes %4d-%4d: density %.3f of the middle's" % (a, bnd - 1, seg.mean() / h[1024:3072].mean()))
