"""Talk to a Redragon K580RGB-PRO over its wired vendor HID channel.

Wired mode only (VID 0x258A, PID 0x010C, interface 1, collection 6).
Packets are 520-byte feature reports; see PROTOCOL.md for the layout.

    python k580.py info
    python k580.py backup  backup.json
    python k580.py restore backup.json
    python k580.py read 0x84 128 [sub]
"""
import ctypes
import json
import sys
import time
from ctypes import wintypes

VID, PID = 0x258A, 0x010C
REPORT_ID = 6           # firmware 0x18 uses 6, other firmware uses 9
REPORT_LEN = 520
CHUNK = 512

# opcodes (write; read = op | 0x80)
OP_PASSWORD = 0x02
OP_MATRIX = 0x03        # sub = layer (0..3)
OP_LED = 0x04
OP_MACRO = 0x05
OP_COLOR_GROUP = 0x06   # per-key R/G/B planes, sub = group
OP_REALTIME = 0x08
OP_RGB_TABLE = 0x0A     # 7 colors per effect, 21-byte entries

MATRIX_KEYS = 126       # 21 columns x 6 rows
LAYERS = 4
SIZES = {
    OP_LED: 128,
    OP_MATRIX: 128 * 4,       # 126 keys + 2 spare; app puts 00 00 5A A5 in the last entry of layer 0
    OP_MACRO: 1024,
    OP_COLOR_GROUP: MATRIX_KEYS * 3,
    OP_RGB_TABLE: 512,
}

_hid = ctypes.WinDLL("hid.dll")
_k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
_cfg = ctypes.WinDLL("cfgmgr32.dll")

_k32.CreateFileW.restype = wintypes.HANDLE
_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_hid.HidD_SetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
_hid.HidD_GetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]


class GUID(ctypes.Structure):
    _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD),
                ("d4", ctypes.c_ubyte * 8)]


def _hid_paths():
    guid = GUID()
    _hid.HidD_GetHidGuid(ctypes.byref(guid))
    size = wintypes.ULONG()
    _cfg.CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), ctypes.byref(guid), None, 0)
    buf = ctypes.create_unicode_buffer(size.value)
    _cfg.CM_Get_Device_Interface_ListW(ctypes.byref(guid), None, buf, size, 0)
    return [p for p in buf[:size.value].split("\0") if p]


def find_path():
    tag = f"vid_{VID:04x}&pid_{PID:04x}&mi_01&col06"
    for p in _hid_paths():
        if tag in p.lower():
            return p
    raise SystemExit("K580 not found in wired mode (turn the wireless switch off and replug)")


class K580:
    def __init__(self, path=None):
        self.path = path or find_path()
        h = _k32.CreateFileW(self.path, 0xC0000000, 3, None, 3, 0, None)
        if h in (None, wintypes.HANDLE(-1).value):
            raise OSError(ctypes.get_last_error(), "CreateFile failed")
        self.h = h

    def close(self):
        _k32.CloseHandle(self.h)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _packet(self, op, sub, count, index, data):
        pkt = bytearray(REPORT_LEN)
        pkt[0] = REPORT_ID
        pkt[1] = op
        pkt[2] = sub
        pkt[4] = count
        pkt[5] = index
        pkt[6] = len(data) & 0xFF
        pkt[7] = len(data) >> 8
        pkt[8:8 + len(data)] = data
        return pkt

    def _set(self, pkt):
        buf = (ctypes.c_ubyte * REPORT_LEN).from_buffer(pkt)
        for _ in range(3):
            if _hid.HidD_SetFeature(self.h, buf, REPORT_LEN):
                return
            time.sleep(0.07)
        raise OSError(ctypes.get_last_error(), f"SetFeature op=0x{pkt[1]:02x}")

    def read(self, op, size, sub=0):
        """Read `size` bytes for read-opcode `op` (0x8x)."""
        out = bytearray()
        count = (size + CHUNK - 1) // CHUNK
        for i in range(count):
            out += self.read_chunk(op, i, count, min(CHUNK, size - len(out)), sub)
        return bytes(out)

    def read_chunk(self, op, index, count, n=CHUNK, sub=0):
        """Read chunk `index` of a `count`-chunk read. The keyboard serves any chunk on its own,
        so e.g. a few bytes of the 64 KB flash dump (0x88) don't need the whole dump."""
        self._set(self._req(op, sub, count, index, n))
        time.sleep(0.02)
        reply = bytearray(REPORT_LEN)
        reply[0] = REPORT_ID
        buf = (ctypes.c_ubyte * REPORT_LEN).from_buffer(reply)
        if not _hid.HidD_GetFeature(self.h, buf, REPORT_LEN):
            raise OSError(ctypes.get_last_error(), f"GetFeature op=0x{op:02x}")
        return bytes(reply[8:8 + n])

    def read_flash(self, addr, n):
        """`n` bytes of MCU flash at `addr` (the 0x88 dump is rotated by 0x1CA)."""
        off = (addr - 0x1CA) % 0x10000
        first, last = off // CHUNK, (off + n - 1) // CHUNK
        data = b"".join(self.read_chunk(0x88, i, 0x10000 // CHUNK) for i in range(first, last + 1))
        return data[off - first * CHUNK:off - first * CHUNK + n]

    def _req(self, op, sub, count, index, n):
        pkt = self._packet(op, sub, count, index, b"")
        pkt[6] = n & 0xFF
        pkt[7] = n >> 8
        return pkt

    def write(self, op, data, sub=0):
        """Write `data` with write-opcode `op` (0x0x), split into 512-byte packets."""
        if op in UNSAFE_WRITE_OPS:
            raise ValueError(f"refusing write op 0x{op:02x}: may write MCU flash")
        count = max(1, (len(data) + CHUNK - 1) // CHUNK)
        for i in range(count):
            self._set(self._packet(op, sub, count, i, data[i * CHUNK:(i + 1) * CHUNK]))
            time.sleep(0.02)

    def realtime_frame(self, rgb):
        """Send one real-time lighting frame (op 0x08): 3 bytes (R, G, B) per LED index.

        Single packet only (<= 512 bytes). Verified not to touch flash.
        """
        if len(rgb) > CHUNK:
            raise ValueError("frame must fit in one 512-byte packet")
        self._set(self._packet(OP_REALTIME, 0, 1, 0, bytes(rgb)))

    def firmware_version(self):
        """HID VersionNumber (0x0118 style; low byte is the firmware number, 0x18 = 24)."""
        class ATTR(ctypes.Structure):
            _fields_ = [("Size", wintypes.ULONG), ("VendorID", wintypes.USHORT),
                        ("ProductID", wintypes.USHORT), ("VersionNumber", wintypes.USHORT)]
        a = ATTR()
        a.Size = ctypes.sizeof(ATTR)
        _hid.HidD_GetAttributes(wintypes.HANDLE(self.h), ctypes.byref(a))
        return a.VersionNumber

    # ---- convenience ----
    def password(self):
        return self.read(0x80 | OP_PASSWORD, 6, sub=1)

    def get_led(self):
        return self.read(0x80 | OP_LED, SIZES[OP_LED])

    def get_matrix(self, layer):
        return self.read(0x80 | OP_MATRIX, SIZES[OP_MATRIX], sub=layer)

    def get_macros(self):
        return self.read(0x80 | OP_MACRO, SIZES[OP_MACRO])

    def get_color_group(self, group):
        return self.read(0x80 | OP_COLOR_GROUP, SIZES[OP_COLOR_GROUP], sub=group)

    def get_rgb_table(self):
        return self.read(0x80 | OP_RGB_TABLE, SIZES[OP_RGB_TABLE])

    def fix_rgb_table(self):
        """Effects take their single colours from the RGB table (flash 0xA800, 7 colours x 22 effects).
        Entering the ISP bootloader (firmware install) can leave a copy of the lighting block there
        instead, which turns single-colour effects black. Writes the default table back if so.
        Returns True if it had to."""
        table = self.get_rgb_table()
        entries = [table[i * 21:i * 21 + 21] for i in range(RGB_TABLE_EFFECTS)]
        if table[0x7E:0x80] != bytes([0x5A, 0xA5]) and all(any(e) for e in entries[1:]):
            return False
        data = bytearray(SIZES[OP_RGB_TABLE])
        for i in range(RGB_TABLE_EFFECTS + 2):
            data[i * 21:i * 21 + 21] = DEFAULT_PALETTE
        data[0x1FA:0x1FC] = bytes([0x5A, 0xA5])
        self.write(OP_RGB_TABLE, bytes(data))
        return True


# red, green, blue, yellow, magenta, cyan, white: the colour indexes 0-6 of the lighting block
DEFAULT_PALETTE = bytes.fromhex("ff0000 00ff00 0000ff ffff00 ff00ff 00ffff ffffff".replace(" ", ""))
RGB_TABLE_EFFECTS = 22             # hw effect ids 0-21

# Writes with these opcodes are refused: 0x88 reads back the MCU's flash, so 0x08 and the
# unnamed 0x0B/0x0E may write to it.
UNSAFE_WRITE_OPS = {0x08, 0x0B, 0x0E}

# matrix index -> key, from Dev\kb\KB.ini ([KEY] section, last field of each Kn line)
KEY_NAMES = {
    0: "Esc", 1: "`", 2: "Tab", 3: "CapsLock", 4: "LShift", 5: "LCtrl", 6: "G1", 7: "1", 8: "Q",
    9: "A", 10: "Z", 11: "LWin", 12: "F1", 13: "2", 14: "W", 15: "S", 16: "X", 17: "LAlt", 18: "F2",
    19: "3", 20: "E", 21: "D", 22: "C", 23: "G2", 24: "F3", 25: "4", 26: "R", 27: "F", 28: "V",
    29: "G3", 30: "F4", 31: "5", 32: "T", 33: "G", 34: "B", 35: "Space", 36: "F5", 37: "6", 38: "Y",
    39: "H", 40: "N", 41: "G4", 42: "F6", 43: "7", 44: "U", 45: "J", 46: "M", 47: "G5", 48: "F7",
    49: "8", 50: "I", 51: "K", 52: ",", 53: "RAlt", 54: "F8", 55: "9", 56: "O", 57: "L", 58: ".",
    59: "Fn", 60: "F9", 61: "0", 62: "P", 63: ";", 64: "/", 65: "App", 66: "F10", 67: "-", 68: "[",
    69: "'", 71: "K114", 72: "F11", 73: "=", 74: "]", 77: "K105", 78: "F12", 79: "Backspace",
    80: "\\", 81: "Enter", 82: "RShift", 83: "RCtrl", 84: "PrtSc", 85: "Insert", 86: "Delete",
    88: "Media1", 89: "Left", 90: "ScrLk", 91: "Home", 92: "End", 94: "Up", 95: "Down", 96: "Pause",
    97: "PgUp", 98: "PgDn", 101: "Right", 103: "NumLock", 104: "Num7", 105: "Num4", 106: "Num1",
    107: "Num0", 109: "Num/", 110: "Num8", 111: "Num5", 112: "Num2", 113: "Media2", 115: "Num*",
    116: "Num9", 117: "Num6", 118: "Num3", 119: "Num.", 121: "Num-", 122: "Num+", 124: "NumEnter",
    125: "Media3",
}

MODS = ["LCtrl", "LShift", "LAlt", "LGui", "RCtrl", "RShift", "RAlt", "RGui"]
CONSUMER = {0xB5: "Next", 0xB6: "Prev", 0xB7: "Stop", 0xCD: "Play/Pause", 0xE2: "Mute",
            0xE9: "Vol+", 0xEA: "Vol-", 0x6F: "Bright+", 0x70: "Bright-", 0x183: "MediaPlayer",
            0x18A: "Mail", 0x192: "Calculator", 0x194: "MyComputer", 0x221: "WWW Search",
            0x223: "WWW Home", 0x224: "WWW Back", 0x225: "WWW Fwd", 0x226: "WWW Stop",
            0x227: "WWW Refresh", 0x22A: "WWW Favorites"}

# hw effect id (LED byte 10) -> name. KB.ini LedOptN gives the hw id for list slot N, and the
# app names slot N with tc_kb_ledN from Text\en\text.xml (loader at 0x00410790 / 0x00450055).
EFFECTS = {0: "OFF", 1: "Fixed on", 2: "Respire", 3: "Rainbow", 4: "Flash away", 5: "Raindrops",
           6: "Rainbow wheel", 7: "Ripples shining", 8: "Stars twinkle", 9: "Shadow disappear",
           10: "Retro snake", 11: "Neon stream", 12: "Reaction", 13: "Sine wave",
           14: "Retinue scanning", 15: "Rotating windmill", 16: "Colorful waterfall",
           17: "Blossoming", 18: "Rotating storm", 21: "Self-define"}
# effect slot (order of LedOpt1..19 in KB.ini) -> hw effect id
SLOT_HW = list(range(1, 19)) + [21]
COLORS = ["red", "green", "blue", "yellow", "magenta", "cyan", "white", "multi/random"]
# hw effect id -> (has speed, has color), from the speed and color flags of LedOptN in KB.ini.
# Effects without a color option draw their own rainbow and ignore the color setting.
NO_SPEED = {1, 21}
NO_COLOR = {3, 15, 16, 17, 21}


def effect_options(hw):
    return hw not in NO_SPEED and hw != 0, hw not in NO_COLOR and hw != 0


def describe_key(entry):
    """Explain a 4-byte matrix entry (bytes as stored on the keyboard)."""
    t, b1, b2, b3 = entry
    if entry == b"\0\0\0\0":
        return "(none)"
    if t == 0x00:
        mods = [m for i, m in enumerate(MODS) if b1 & (1 << i)]
        keys = [f"usage 0x{k:02X}" for k in (b3, b2) if k]
        return "+".join(mods + keys)
    if t == 0x01:
        return f"mouse fn {b1:02X} {b2:02X} {b3:02X}"
    if t == 0x02:
        u = (b2 << 8) | b3
        return f"consumer {CONSUMER.get(u, hex(u))}"
    if t == 0x03:
        return f"macro #{b3} (mode {b1}, count {b2})"
    if t == 0x07:
        if b3 == 0x03:
            return f"G{b2 + 1} macro key"
        return f"keyboard fn 0x{b3:02X} (param {b2})"
    if t == 0x08:
        return f"lighting ctl {b1:02X} {b2:02X} {b3:02X}"
    if t == 0x0D:
        return "Fn"
    return entry.hex()


def decode_led(led):
    out = {
        "effect": f"{led[10]} ({EFFECTS.get(led[10], '?')})",
        "custom_flag": led[9],
        "byte11": led[11],
        "side_led(mode,color,light,speed)": tuple(led[0x12:0x16]),
        "per_effect": [],
    }
    for i in range(19):
        light, b = led[0x3A + 2 * i], led[0x3B + 2 * i]
        name = EFFECTS.get(SLOT_HW[i], "?")
        out["per_effect"].append({"slot": i, "effect": name, "light": light, "speed": b >> 4,
                                  "color": COLORS[b & 7] if (b & 0xF) < 8 else b & 0xF})
    out["trailer"] = led[0x7E:0x80].hex()
    return out


def macro_event(code, release, delay_ms=30, kind=None):
    """One 4-byte macro event, as the official app writes it.

    kind: 0 key, 1 modifier (HID 0xE0-0xE7), 2 mouse button, 3 mouse X, 4 mouse Y, 5 wheel.
    """
    if kind is None:
        kind = 1 if 0xE0 <= code <= 0xE7 else 0
    delay_ms = min(delay_ms, 0xFFFFF)
    b0 = (kind << 4) | (delay_ms >> 16) | (0x80 if release else 0)
    return bytes([b0, (delay_ms >> 8) & 0xFF, delay_ms & 0xFF, code])


def build_macro_buffer(macros):
    """macros: list of (name, [event bytes, ...]). Returns the 1024-byte 0x05 payload.

    Layout (matches the app's output, verified 2026-10-31): a table of (u16 offset, u16 size)
    per macro, then for each macro [name byte length][UTF-16LE name][4-byte events].
    """
    bodies = []
    for name, events in macros:
        nm = name.encode("utf-16le")
        bodies.append(bytes([len(nm)]) + nm + b"".join(events))
    table, offset = b"", 4 * len(bodies)
    for body in bodies:
        table += offset.to_bytes(2, "little") + len(body).to_bytes(2, "little")
        offset += len(body)
    buf = table + b"".join(bodies)
    if len(buf) > SIZES[OP_MACRO]:
        raise ValueError("macros exceed the 1024-byte buffer")
    return buf + bytes(SIZES[OP_MACRO] - len(buf))


MACRO_TIMES, MACRO_WHILE_HELD, MACRO_UNTIL_KEY = 1, 2, 4


def macro_key(index, repeat=1, mode=MACRO_TIMES):
    """Matrix entry that plays app macro `index`.

    mode 1 = play `repeat` times, 2 = repeat while the key is held,
    4 = repeat until any key is pressed (stock app's three cycle options).
    """
    return bytes([0x03, mode, repeat if mode == MACRO_TIMES else 1, index])


def backup(kb):
    data = {
        "password": kb.password().hex(),
        "led": kb.get_led().hex(),
        "matrix": [kb.get_matrix(layer).hex() for layer in range(LAYERS)],
        "macros": kb.get_macros().hex(),
        "rgb_table": kb.get_rgb_table().hex(),
        "color_groups": [kb.get_color_group(g).hex() for g in range(4)],
    }
    return data


def restore(kb, data):
    # Only the blocks whose read-back was verified on hardware. The 0x8A read returns
    # LED-block-like data, so writing it back as an RGB table is not trusted.
    kb.write(OP_LED, bytes.fromhex(data["led"]))
    time.sleep(0.1)
    for layer, hx in enumerate(data["matrix"]):
        kb.write(OP_MATRIX, bytes.fromhex(hx), sub=layer)
        time.sleep(0.1)
    kb.write(OP_MACRO, bytes.fromhex(data["macros"]))
    time.sleep(0.1)
    kb.fix_rgb_table()


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "info"
    with K580() as kb:
        if cmd == "info":
            print("path    ", kb.path)
            print("password", kb.password().hex(" "))
            print("led     ", kb.get_led().hex(" "))
        elif cmd == "backup":
            with open(argv[2], "w") as f:
                json.dump(backup(kb), f, indent=1)
            print("saved", argv[2])
        elif cmd == "restore":
            with open(argv[2]) as f:
                restore(kb, json.load(f))
            print("restored", argv[2])
        elif cmd == "keys":
            layer = int(argv[2]) if len(argv) > 2 else 0
            m = kb.get_matrix(layer)
            for i in range(MATRIX_KEYS):
                e = m[i * 4:i * 4 + 4]
                if e != b"\0\0\0\0":
                    print(f"{i:3d} {KEY_NAMES.get(i, '?'):10s} {e.hex()}  {describe_key(e)}")
        elif cmd == "led":
            print(json.dumps(decode_led(kb.get_led()), indent=1))
        elif cmd == "live":
            # python k580.py live <seconds> <key>=<rrggbb> [...]   e.g. live 3 0=ff0000 14=00ff00
            seconds = float(argv[2])
            frame = bytearray(MATRIX_KEYS * 3)
            for spec in argv[3:]:
                idx, color = spec.split("=")
                frame[int(idx) * 3:int(idx) * 3 + 3] = bytes.fromhex(color)
            end = time.time() + seconds
            while time.time() < end:
                kb.realtime_frame(frame)
                time.sleep(0.1)
        elif cmd == "dump-flash":
            # 0x88 returns flash rotated by 0x1CA; undo that so offsets are real addresses
            raw = kb.read(0x88, 0x10000)
            img = bytearray(0x10000)
            for i, v in enumerate(raw):
                img[(i + 0x1CA) & 0xFFFF] = v
            with open(argv[2], "wb") as f:
                f.write(img)
            print("saved", argv[2])
        elif cmd == "read":
            op, size = int(argv[2], 0), int(argv[3], 0)
            sub = int(argv[4], 0) if len(argv) > 4 else 0
            print(kb.read(op, size, sub).hex(" "))
        else:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
