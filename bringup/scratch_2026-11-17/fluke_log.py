import sys, time
sys.path.insert(0, "/home/jason/mudd/lab-instrument-control/fluke")
from fluke_45 import Fluke45
secs, out = float(sys.argv[1]), sys.argv[2]
d = Fluke45(serial="/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A95AME9U-if00-port0", timeout=3.0)
d.rate('S')
t0 = time.time()
with open(out, "w") as f:
    while time.time() - t0 < secs:
        v = d.read(); f.write("%.3f %s\n" % (time.time(), v)); f.flush()
d.close()
