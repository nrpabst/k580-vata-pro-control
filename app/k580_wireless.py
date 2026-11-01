"""Talk to the K580RGB-PRO through its 2.4G dongle (VID 0x3554, PID 0xFA09).

20-byte output/input reports, report ID 0x13, on interface 1 collection 1 (usage page 0xFF02).
Packet: [13][cmd][count][index][sub<<4 | len][14-byte payload][sum of bytes 0..18].
"""
import ctypes
import sys
import threading
import time
from ctypes import wintypes

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from k580 import _hid_paths  # noqa: E402

VID, PID = 0x3554, 0xFA09
REPORT_ID = 0x13
LEN = 20
PAYLOAD = 14

_k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
_k32.CreateFileW.restype = wintypes.HANDLE
_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                           ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_k32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p]


def find_path():
    tag = f"vid_{VID:04x}&pid_{PID:04x}&mi_01&col01"
    for p in _hid_paths():
        if tag in p.lower():
            return p
    raise SystemExit("dongle not found")


def packet(cmd, sub=0, count=1, index=0, data=b""):
    p = bytearray(LEN)
    p[0], p[1], p[2], p[3] = REPORT_ID, cmd, count, index
    p[4] = (sub << 4) | len(data)
    p[5:5 + len(data)] = data
    p[19] = sum(p[:19]) & 0xFF
    return bytes(p)


class Dongle:
    def __init__(self):
        # separate handles: a pending synchronous ReadFile would block WriteFile on a shared one
        path = find_path()
        self.h = _k32.CreateFileW(path, 0x80000000, 3, None, 3, 0, None)
        self.hw = _k32.CreateFileW(path, 0x40000000, 3, None, 3, 0, None)
        self.replies = []
        self.lock = threading.RLock()            # one query/write at a time (UI + background poll)
        self._stop = False
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        buf = (ctypes.c_ubyte * LEN)()
        n = wintypes.DWORD()
        while not self._stop:
            if _k32.ReadFile(self.h, buf, LEN, ctypes.byref(n), None) and n.value:
                self.replies.append(bytes(buf[:n.value]))
            else:
                break

    def close(self):
        self._stop = True
        _k32.CancelIoEx(self.h, None)
        _k32.CloseHandle(self.h)
        _k32.CloseHandle(self.hw)

    def send(self, pkt):
        n = wintypes.DWORD()
        buf = (ctypes.c_ubyte * LEN).from_buffer_copy(pkt)
        if not _k32.WriteFile(self.hw, buf, LEN, ctypes.byref(n), None):
            raise OSError(ctypes.get_last_error(), "WriteFile")

    def query(self, cmd, sub=0, size=0, timeout=1.5):
        """Send a read request and gather the reply packets that echo `cmd`."""
        with self.lock:
            return self._query(cmd, sub, size, timeout)

    def _query(self, cmd, sub=0, size=0, timeout=1.5):
        self.replies.clear()
        self.send(packet(cmd, sub, data=b""))
        end = time.time() + timeout
        got, out = {}, bytearray()
        while time.time() < end:
            for r in list(self.replies):
                if r[1] & 0x7F == cmd and r[0] == REPORT_ID:
                    got[r[3]] = r
            if got and len(got) == (next(iter(got.values()))[2] & 0x7F):
                break
            time.sleep(0.02)
        for i in sorted(got):
            r = got[i]
            out += r[5:5 + (r[4] & 0x0F)]
        return bytes(out), [r.hex(" ") for r in self.replies]


def write(d, cmd, data, sub=0, timeout=1.0):
    """Write `data` in 14-byte packets; the keyboard echoes each packet as an ack."""
    with d.lock:
        _write(d, cmd, data, sub, timeout)


def _write(d, cmd, data, sub=0, timeout=1.0):
    count = (len(data) + PAYLOAD - 1) // PAYLOAD
    for i in range(count):
        d.replies.clear()
        d.send(packet(cmd, sub, count, i, data[i * PAYLOAD:(i + 1) * PAYLOAD]))
        end = time.time() + timeout
        while time.time() < end:
            ack = [r for r in d.replies if r[1] & 0x7F == cmd and r[3] == i]
            if ack:
                if ack[0][1] & 0x80:
                    raise IOError(f"CRC error on packet {i}")
                break
            time.sleep(0.01)
        else:
            raise TimeoutError(f"no ack for packet {i} of cmd 0x{cmd:02x}")


if __name__ == "__main__":
    d = Dongle()
    try:
        for cmd in [int(c, 0) for c in sys.argv[1:]] or [0x07, 0x09]:
            data, raw = d.query(cmd)
            print(f"cmd 0x{cmd:02x}: {data.hex(' ')}")
            for r in raw:
                print("   ", r)
    finally:
        d.close()
