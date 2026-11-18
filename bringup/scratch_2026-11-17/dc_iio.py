"""The DC transfer through IIO: DAC 1 (or 2) at seven fixed codes, both ADCs' means at each (udp_awg.bit, the bridge)."""
import sys, time, iio, numpy as np
dacn = int(sys.argv[1]) if len(sys.argv) > 1 else 1
ctx = iio.Context("ip:127.0.0.1")
dac = ctx.find_device("ecp5-dac"); adc = ctx.find_device("ecp5-adc")
for ch in dac.channels: ch.enabled = True
adc.attrs["sampling_frequency"].value = "1562500"
for ch in adc.channels: ch.enabled = True
codes = [2048, 4096, 6144, 8192, 10240, 12288, 14336]
out = []
for c in codes:
    db = iio.Buffer(dac, 8192, True)
    p = np.full((8192, 2), 8192, np.uint16); p[:, dacn - 1] = c
    db.write(bytearray(p.tobytes())); db.push(); time.sleep(0.3)
    rb = iio.Buffer(adc, 1 << 18, False); rb.refill(); x = np.frombuffer(bytes(rb.read()), "<u2").reshape(-1, 2).astype(float); del rb
    out.append(x.mean(0)); del db
out = np.array(out)
for k, name in ((0, "ADC A"), (1, "ADC B")):
    m = out[:, k]; s, o = np.polyfit(codes, m, 1); dev = m - (s * np.array(codes) + o)
    print("DAC %d -> %s: means %s; slope %.4f (x4 %.4f), worst from a line %.2f codes" % (dacn, name, " ".join("%.1f" % v for v in m), s, 4 * s, np.abs(dev).max()))
