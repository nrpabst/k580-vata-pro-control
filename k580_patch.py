"""Media-key light patch for the Redragon K580RGB-PRO (firmware 0x18).

No Redragon firmware is shipped. The installer reads the keyboard's own firmware with sinowisp,
checks that it's the exact stock version this patch was made for, patches it, and
writes it back. The untouched read is kept as the user's personal roll-back image.

What the patch does: the media-key lights stay on unless lighting byte 0x11 is set,
so an app can switch them with a normal lighting write (see PROTOCOL.md, section 8b).
"""
import hashlib
import os
import subprocess

FIRMWARE_SIZE = 0xF000
# sha256 of the code areas of stock firmware (settings pages excluded, they differ per user)
STOCK_CODE_SHA256 = "01bce057ed6cc271dbaed59c21d16e5d2c7056b2810f2b05d4b2aceea65cb79e"
CODE_RANGES = [(0x0000, 0xA200), (0xA27E, 0xA400), (0xAE00, 0xBC00)]

# (address, stock bytes, patched bytes)
PATCH = [
    (0x0F67, "302762", "806300"),  # drop the unbound WASD->arrows remap that used bit 0x27
    (0x2B00, "30380b", "20270b"),  # media LED 1: off only when bit 0x27 (lighting byte 0x11) is set
    (0x2B25, "30390b", "20270b"),  # media LED 2
    (0x2B4A, "303a0b", "20270b"),  # media LED 3
    # Volume/brightness (wheel-mode) key light: on when wheel mode is set OR lighting byte 0x30 is
    # non-zero. The check lives in the now-unused WASD remap code at 0x0F6A.
    (0x2AD8, "9003b9", "020f6a"),  # LJMP 0x0F6A instead of MOV DPTR,#0x3B9
    (0x0F6A, "ebb40e07900d0f7452804f900378e0ffb409",
             "9003b9e07006" "9003cfe06003" "022ade" "022ae9"),
    # 0F6A: MOV DPTR,#0x3B9 ; MOVX A,@DPTR ; JNZ on
    # 0F70: MOV DPTR,#0x3CF (lighting byte 0x30) ; MOVX A,@DPTR ; JZ off
    # 0F76: on:  LJMP 0x2ADE      0F79: off: LJMP 0x2AE9

    # Key function 0x13 (a no-op in stock) toggles lighting byte 0x30, so a key bound to 07 00 00 13
    # switches the volume/brightness key light. Media lights need no patch: stock key function 0x00
    # (07 00 00 00) already flips lighting byte 0x11 (it was the WASD-swap toggle).
    (0x37D3, "023b3d", "020f7c"),                   # fn 0x13 -> 0x0F7C instead of the no-op at 0x3B3D
    (0x0F7C, "07900d0f74508040efb40f07900d0f74518035efb415",
             "202512" "202d0f" "9003cf" "e0" "6003" "e4" "8002" "7401" "f0" "023801" "22"),
    # 0F7C: JB 0x25,ret ; JB 0x2D,ret          (same guards as the other key functions)
    # 0F82: MOV DPTR,#0x3CF ; toggle 0 <-> 1 ; LJMP 0x3801 (fn 0x00's tail: save + feedback flash)
    # 0F91: ret: RET

    # Battery: the routine at 0x421C (runs every few ticks) first copies the battery % into lighting
    # byte 0x1C (XRAM 0x3BB, unused by stock), so the app can read it with a normal lighting read, by
    # cable or through the 2.4G dongle. Same source as the Fn + Right Shift gauge (0x2D1F): the
    # smoothed % in IRAM 0x0A, or the raw % at XRAM 0x01C8 while that is still 0xFF.
    (0x421C, "9003b0", "020f92"),                   # LJMP 0x0F92 instead of MOV DPTR,#0x3B0
    (0x0F92, "07900d0f744f802aefb45e07900d0f741a801f",
             "e50a" "b4ff04" "9001c8" "e0" "9003bb" "f0" "9003b0" "02421f"),
    # 0F92: MOV A,0x0A ; CJNE A,#0xFF,store ; MOV DPTR,#0x1C8 ; MOVX A,@DPTR
    # 0F9A: store: MOV DPTR,#0x3BB ; MOVX @DPTR,A ; MOV DPTR,#0x3B0 ; LJMP 0x421F
]
BATTERY_BYTE = 0x1C               # lighting-block byte: battery % (0-100). Not measured on the cable (reads 0)
# bytes that only the latest custom build has (fn 0x13 light toggle, battery copy)
LATEST_SITES = [(0x37D3, bytes.fromhex("020f7c")), (0x421C, bytes.fromhex("020f92")),
                (0x0F94, bytes.fromhex("b4ff04"))]
MEDIA_TOGGLE_KEY = "07000000"     # stock key function 0x00: toggle lighting byte 0x11
WHEEL_TOGGLE_KEY = "07000013"     # patched key function 0x13: toggle lighting byte 0x30
# A short-lived test build also changed brightness to 0-20 (5% steps) by replacing the level
# table lookup at 0x9751 with MOV B,#4 / MUL AB. It was dropped; the app still recognises it
# so it can convert brightness back when that build is uninstalled.
FINE_BRIGHTNESS_SITE = (0x9751, bytes.fromhex("75f004a4"))
FINE_BRIGHTNESS_LEVELS = 20
WHEEL_LIGHT_BYTE = 0x30           # lighting-block byte: non-zero keeps the wheel-mode key lit
MEDIA_LIGHT_BYTE = 0x11           # lighting-block byte: zero keeps the media-key lights lit

SINOWISP_ARGS = ["--platform", "sh68f90", "--vendor_id", "0x258a", "--product_id", "0x010c"]


def read_hex(path, size=FIRMWARE_SIZE):
    data = bytearray(size)
    base = 0
    for line in open(path):
        line = line.strip()
        if not line.startswith(":"):
            continue
        b = bytes.fromhex(line[1:])
        n, addr, kind = b[0], (b[1] << 8) | b[2], b[3]
        if kind == 0 and base + addr < size:
            data[base + addr:base + addr + n] = b[4:4 + n]
        elif kind == 4:
            base = ((b[4] << 8) | b[5]) << 16
    return data


def write_hex(data, path):
    lines = []
    for a in range(0, len(data), 16):
        chunk = data[a:a + 16]
        rec = bytes([len(chunk), a >> 8, a & 0xFF, 0]) + chunk
        lines.append(":" + rec.hex().upper() + "%02X" % ((-sum(rec)) & 0xFF))
    lines.append(":00000001FF")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def code_hash(data):
    return hashlib.sha256(b"".join(bytes(data[s:e]) for s, e in CODE_RANGES)).hexdigest()


def state(data):
    """'stock', 'patched' or 'unknown'."""
    if all(data[a:a + len(bytes.fromhex(new))] == bytes.fromhex(new) for a, _, new in PATCH):
        return "patched"
    if code_hash(data) == STOCK_CODE_SHA256:
        return "stock"
    return "unknown"


def apply(data):
    out = bytearray(data)
    for addr, old, new in PATCH:
        o, n = bytes.fromhex(old), bytes.fromhex(new)
        if out[addr:addr + len(o)] != o:
            raise ValueError(f"unexpected bytes at 0x{addr:04X}")
        out[addr:addr + len(n)] = n
    return out


def sinowisp(tool, *args):
    return subprocess.run([tool, *args], capture_output=True, text=True, creationflags=0x08000000)


def read_keyboard(tool, path):
    r = sinowisp(tool, "read", *SINOWISP_ARGS, path)
    if r.returncode or not os.path.exists(path):
        raise RuntimeError("Reading the keyboard failed:\n" + r.stdout[-600:] + r.stderr[-600:])


def write_keyboard(tool, path):
    r = sinowisp(tool, "write", *SINOWISP_ARGS, path)
    if r.returncode:
        raise RuntimeError("Writing the keyboard failed:\n" + r.stdout[-600:] + r.stderr[-600:])
