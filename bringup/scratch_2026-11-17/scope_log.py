import sys, time
sys.path.insert(0, "/home/jason/OpticsPCBs/ECP5-2ADC-2DAC/bringup")
import bench
secs, out = float(sys.argv[1]), sys.argv[2]
b = bench.Bench("A"); b.require(["SDS2104X:4"], "the scope's CH4"); sc = b.scope
sc.channel(4, on=True, impedance="1M", coupling="DC", probe=1, scale=0.005, offset=-0.0149, bwlimit="20M")
sc.acquire(resolution=10)
sc.timebase(scale=1e-3, delay=0.0); sc.trigger(mode="auto"); sc.run(); time.sleep(1)
t0 = time.time()
with open(out, "w") as f:
    while time.time() - t0 < secs:
        try:
            v = float(sc.measure("MEAN", 4)); f.write("%.3f %.7f\n" % (time.time(), v)); f.flush()
        except Exception as e:
            f.write("# %s\n" % e)
