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

    # Battery: the routine at 0x421C runs every few ticks in every mode (the battery check at 0x7EEF
    # turned out not to run on wireless). It first copies, into lighting bytes the app can read by
    # cable or through the 2.4G dongle:
    #   0x1C (XRAM 0x3BB): the % the Fn + Right Shift gauge shows (smoothed IRAM 0x0A, or the raw %
    #                      at XRAM 0x01C8 while that is still 0xFF)
    #   0x1D-0x1E (XRAM 0x3BC-0x3BD): the raw battery reading (XRAM 0x037E-0x037F, big-endian)
    (0x421C, "9003b0", "020fb4"),                   # LJMP 0x0FB4 instead of MOV DPTR,#0x3B0
    (0x0FB4, "900d0f74168009efb4650d900d0f7407",
             "e50a" "b4ff04" "9001c8" "e0" "9003bb" "f0" "020f92"),
    # 0FB4: MOV A,0x0A ; CJNE A,#0xFF,store ; MOV DPTR,#0x1C8 ; MOVX A,@DPTR
    # 0FBD: store: MOV DPTR,#0x3BB ; MOVX @DPTR,A ; LJMP 0x0F92
    (0x0F92, "07900d0f744f802aefb45e07900d0f741a801f",
             "90037e" "e0" "9003bc" "f0" "90037f" "e0" "9003bd" "f0" "02eeb0"),
    # 0F92: copy XRAM 0x37E -> 0x3BC and 0x37F -> 0x3BD ; LJMP 0xEEB0 (G-key flags, then 0x0FC4's work)
    (0x0FC4, "f0e4a3f0a3f0", "9003b0" "02421f"),    # MOV DPTR,#0x3B0 (the replaced instruction) ; LJMP 0x421F
]
# Effects the stock firmware lacks (Rainbow wheel 6, Colorful waterfall 0x10, Rotating storm 0x12),
# built by tools/effects_asm.py into the never-erased, unused flash page at 0xEC00. Two LCALLs into the
# effect switches (?C?CCASE at 0x62A9) go through our code first; the Fn effect key stops skipping them.
EFFECTS_CODE = bytes.fromhex(
    "b40602800db410028008b4120280030262a91581158130010dc201d202c24ac22de4900e91f0900dafe09037410223a7"
    "b40602800db410028008b4120280030262a915811581900e92f0900932e0fea3e0ffc3900399e09f900398e09e500122"
    "12ec660225dd900e91e004f0900e92e0b4060590ed1d800bb4100590ed9b800390ee19aa83ab82900e8feaf0a3ebf0e4"
    "900e8df0e4900e8ef0900e8de075f006a4ff900e8ee02fff900e8fe0faa3e02ff582ea3400f583e493ffb4fe0302ed04"
    "b4ff06e4fdfefc8020900e91e02f547f75f003a42484f582e5f03434f583e493fd740193fe740293fc900192edf09000"
    "00eef0ec129749900e8de0ff900e8ee0fd127295900e8ee004f0b4060a900e8de004f0b415042202ec9902ec94474441"
    "3e3b38ff45413e3a374945423d3a364a46423d39fe4b47423d38fe4d49433c3632504b443b34fe524d453a32fe565147"
    "382e295b574d3228246060602020206468720dfefe696e78fefefe6d727a050d1270747bfefe1072767cfe090d74787d"
    "fefe0bfe797d02060afe7a7d0205fefe7a7e010508fe7b7efe04fe0014283c5064ff14283c50640014283c5064001428"
    "3c50fe0014283c50fe0014283c50640014283c50fe0014283c50fe0014283c50640014283c50640014283c5064001428"
    "3cfefe001428fefefe0014283c5064001428fefe64001428fe5064001428fefe64fe14283c5064fe14283c50fefe1428"
    "3c5064fe1428fe50fe130c07040303ff06017d7b7c08007a767475037a736f6dfe7e746d6765fe7a6f66605d5f776b60"
    "5855fe75685b504dfe756756474448776a563b3a417c706525303c017a7b16fefe080407fefefe100d101b2835171518"
    "fefe371f1d20fe2f3a262527fefe3efe2d2f333a43fe34363a40fefe3b3d41464dfe4344fe4cfe"
)
EFFECTS_PATCH = [
    (0x2013, "1262a9", "12ec00"),   # effect changed: LCALL init_sel
    (0x23BB, "1262a9", "12ec30"),  # every frame:    LCALL frame_sel
    (0x6F14, "06", "fe"),                              # Fn effect cycle: stop skipping 6
    (0x6F32, "10", "fe"),                              #                  stop skipping 0x10
    (0x6F3D, "11", "12"),                              #                  last effect 0x11 -> 0x12
    (0xEC00, "00" * len(EFFECTS_CODE), EFFECTS_CODE.hex()),
]
# Record key fix: pressing record and then record again without choosing a G key marked the G key
# the slot pointer last held (G1 by default) as recorded, so it lit up with nothing saved, until a
# restart. The stop routine (0x3BC0) now only marks the slot if a G key was chosen (bit 0x1E).
RECORD_FIX_PATCH = [
    (0x3BC2, "d21dc205", "02eea000"),               # LJMP 0xEEA0 ; NOP  (was SETB 0x1D ; CLR 0x05)
    (0xEEA0, "00" * 11, "301e07" "d21d" "c205" "023bc6" "22"),
    # EEA0: JNB 0x1E,cancel ; SETB 0x1D ; CLR 0x05 ; LJMP 0x3BC6     EEAA: cancel: RET
    # G-key 'has a recording' flags follow flash (tools/effects_asm.py build_gflags), so recordings
    # the app saves or clears light their G key right away, not after a restart.
    (0xEEB0, "00" * 65, "203c38c006c0077f00ef75f080a4f582e5f024e0f583e4937e00c3940240027e0174b62ff582e4340df583e0b4ff028002eef00fbf14d2d007d0069003b002421f"),
]
# Optional: switch to the cable whenever it's plugged in. The mode switch on the keyboard is read at
# 0x84AB (pins P5.5 / P3.1, 10 samples each): 2.4G, Bluetooth or cable (XRAM 0x3AD = 1 / 2 / 0).
# Bit 0x48 is set while the cable powers the keyboard (P3.4, debounced at 0x9EBE; it also drives the
# battery's charging logic). With this patch the cable branch wins while bit 0x48 is set, and the
# switch position takes over again when the cable is unplugged.
AUTO_WIRED_PATCH = [
    (0x84AB, "20fd12", "020fa5"),                   # LJMP 0x0FA5 instead of JB 0xFD,0x84C0
    (0x0FA5, "efb45907900d0f74048014efb45f07",
             "204806" "20fd06" "0284ae" "0284d4" "0284c0"),
    # 0FA5: JB 0x48,cable ; JB 0xFD,rest ; LJMP 0x84AE (2.4G position)
    # 0FAE: cable: LJMP 0x84D4        0FB1: rest: LJMP 0x84C0 (Bluetooth or cable position)
]
AUTO_WIRED_SITE = (0x84AB, bytes.fromhex("020fa5"))
BATTERY_BYTE = 0x1C               # lighting-block byte: battery % (0-100). Not measured on the cable (reads 0)
# bytes that only the latest custom build has (fn 0x13 light toggle, battery copy)
LATEST_SITES = [(0x37D3, bytes.fromhex("020f7c")), (0x421C, bytes.fromhex("020fb4")),
                (0x0FC4, bytes.fromhex("9003b0")),
                (0x2013, bytes.fromhex("12ec00")), (0x3BC2, bytes.fromhex("02eea0")),
                (0x0FA2, bytes.fromhex("02eeb0"))]
BATTERY_RAW = 0x1D                # lighting-block bytes 0x1D-0x1E: raw battery reading, big-endian
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


def apply(data, auto_wired=False):
    out = bytearray(data)
    for addr, old, new in PATCH + EFFECTS_PATCH + RECORD_FIX_PATCH + (AUTO_WIRED_PATCH if auto_wired else []):
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
