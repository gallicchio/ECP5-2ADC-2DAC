"""Talk to the board directly (the bridge idle): an ADC stream at D=4, and for each packet its sequence number, header
byte 7 (the scratch build's Gray-coded count of frames received) and the means of A and B over its 256 pairs."""
import socket, sys, time, numpy as np
ip, secs, out = "192.168.8.177", float(sys.argv[1]), sys.argv[2]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 << 20)
s.bind(("", 0)); s.settimeout(1.0)
to = (ip, 50010)
s.sendto(b"I" + socket.inet_aton(ip), to); s.sendto(b"S", to); time.sleep(0.1)
import struct
mid = np.full(700, 8192, "<u2").tobytes()
for ch in (1, 2):                                   # both DAC memories at mid-scale, as the bridge's upload does
    for start in range(0, 16384, 700):
        nsmp = min(700, 16384 - start)
        s.sendto(b"W" + bytes([ch]) + struct.pack("<H", start) + mid[:2 * nsmp], to); time.sleep(0.0005)
s.sendto(b"L" + struct.pack("<H", 0), to); s.sendto(b"R\x00", to); s.sendto(b"M\x01", to)
s.sendto(b"X\x00", to); s.sendto(b"G\x04" + socket.inet_aton(ip), to)
n = int(secs * 1562500 / 256)
seq = np.zeros(n, np.int64); g = np.zeros(n, np.int64); ma = np.zeros(n); mb = np.zeros(n)
buf = bytearray(2048); k = 0
while k < n:
    try:
        m = s.recv_into(buf)
    except socket.timeout:
        print("timeout at", k); break
    if m != 8 + 1024: continue
    seq[k] = int.from_bytes(buf[0:4], "little"); g[k] = buf[7]
    x = np.frombuffer(buf, "<u2", 512, 8).reshape(256, 2)
    ma[k] = x[:, 0].mean(); mb[k] = x[:, 1].mean(); k += 1
s.sendto(b"S", to)
np.savez(out, seq=seq[:k], g=g[:k], ma=ma[:k], mb=mb[:k])
print("%d packets, %d missing from the numbering" % (k, int(seq[k - 1] - seq[0] + 1 - k)))
