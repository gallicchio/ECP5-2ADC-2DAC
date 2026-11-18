#!/bin/bash
# rail_test.sh NAME: the Fluke logs a rail while both ADCs are recorded for 90 s (ddc_awg loaded, bridge running);
# then the rail's mean in each of ADC B's states and its move at each of B's flips.
S=/tmp/claude-1000/-home-jason-mnt-local4TB-2TBext4-frank-stuff-mudd-OpticsPCBs-ECP5-2ADC-2DAC/9efc7873-8a3c-47bb-bd6c-4035cd9cf43e/scratchpad
N=$1
cd ~/mudd/133electronics/ecp5-2adc-2dac-tutorial/src/verilog
python3 $S/fluke_log.py 105 $S/rail_$N.txt > $S/fluke_log_$N.out 2>&1 & FP=$!
sleep 1
timeout 200 python3 $S/steps_t.py 90 $S/rail_$N.npz > /dev/null 2>&1
tail --pid=$FP -f /dev/null
python3 - "$S" "$N" <<'PY'
import sys, numpy as np
from scipy.ndimage import median_filter
S, N = sys.argv[1], sys.argv[2]
z = np.load("%s/rail_%s.npz" % (S, N)); tm, m = z["tm"], z["m"]
f = np.loadtxt("%s/rail_%s.txt" % (S, N)); ft, fv = f[:, 0], f[:, 1]
k = len(m) // 10; m10 = m[:k * 10].reshape(k, 10, 2).mean(1); t10 = tm[:k * 10].reshape(k, 10).mean(1)
b = m10[:, 1] - np.median(m10[:, 1]); s = median_filter(b, 9); lo, hi = np.percentile(s, 5), np.percentile(s, 95)
st = (s < (lo + hi) / 2).astype(int)
print("ADC B: levels %.3f codes apart, %d flips" % (hi - lo, int(np.count_nonzero(np.diff(st)))))
w = (ft > t10[0]) & (ft < t10[-1]) & (np.abs(fv - np.median(fv)) < 0.005)
fw = fv[w]; sb = np.interp(ft[w], t10, st) > 0.5
print("%s: %d readings, mean %.5f V, rms %.3f mV" % (N, w.sum(), fw.mean(), 1e3 * fw.std()))
if sb.any() and (~sb).any():
    print("  B low %.5f V (%d), B high %.5f V (%d): %+.3f mV" % (fw[sb].mean(), sb.sum(), fw[~sb].mean(), (~sb).sum(), 1e3 * (fw[sb].mean() - fw[~sb].mean())))
steps = []
for e in np.flatnonzero(np.diff(st) != 0):
    tf = t10[e]; to_low = st[e + 1] == 1
    bf = fv[(ft > tf - 2.0) & (ft < tf - 0.3)]; af = fv[(ft > tf + 0.3) & (ft < tf + 2.0)]
    if len(bf) >= 3 and len(af) >= 3:
        steps.append(1e3 * (np.median(af) - np.median(bf)) * (1 if to_low else -1))
steps = np.array(steps)
if len(steps):
    print("  flip by flip (%d): %+.3f +- %.3f mV (low minus high)" % (len(steps), steps.mean(), steps.std() / np.sqrt(len(steps))))
PY
