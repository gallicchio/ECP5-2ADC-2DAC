import sys, time, iio, numpy as np
secs, out = float(sys.argv[1]), sys.argv[2]
ctx = iio.Context("ip:127.0.0.1")
dac = ctx.find_device("ecp5-dac")
for ch in dac.channels: ch.enabled = True
db = iio.Buffer(dac, 8192, True); db.write(bytearray(np.full((8192, 2), 8192, np.uint16).tobytes())); db.push()
adc = ctx.find_device("ecp5-adc"); adc.attrs["sampling_frequency"].value = "1562500"
for ch in adc.channels: ch.enabled = True
rb = iio.Buffer(adc, 1 << 18, False); means = []; tt = []; carry = np.empty((0, 2)); total = 0
while total < secs * 1562500:
    rb.refill(); tr = time.time(); a = np.frombuffer(bytes(rb.read()), "<u2").reshape(-1, 2).astype(float); total += len(a)
    a = np.concatenate([carry, a]); k = len(a) // 1562
    means.append(a[:k * 1562].reshape(k, 1562, 2).mean(1)); tt.append((tr, k, len(carry) if False else 0)); carry = a[k * 1562:]
del rb, db
m = np.concatenate(means)
t_end = np.concatenate([[t] * k for t, k, _ in tt]); idx = np.concatenate([np.arange(k)[::-1] for t, k, _ in tt])
np.savez(out, tm=t_end - (idx + 0.5) * 1562 / 1562500, m=m)
print("%d ms of means" % len(m))
