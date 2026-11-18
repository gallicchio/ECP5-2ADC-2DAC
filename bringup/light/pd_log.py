# Log ADC B (the photodiode receiver) every statistics window (0.67 s) for `seconds`, the board's LEDs dark.
import sys, time, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gateware", "bringup", "host"))
import ecp5bu
seconds = float(sys.argv[1])
bd = ecp5bu.Board(ecp5bu.find_port())
bd.leds(0, rgb=0); bd.adc_config(rate=1.5625e6, stats_log2=20)
t0 = time.time(); last = bd.rd("STATSEQ")
try:
    while time.time() - t0 < seconds:
        while ((bd.rd("STATSEQ") - last) & 0xFFFF) < 1:
            time.sleep(0.05)
        s = bd.adc_stats(); last = s["seq"]
        print("%s  ADC B mean %8.2f  (%d..%d)" % (time.strftime("%H:%M:%S"), s["b"]["mean"], s["b"]["min"], s["b"]["max"]), flush=True)
finally:
    bd.leds(None)
