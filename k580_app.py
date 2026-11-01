"""K580 Control: a small settings app for the Redragon K580RGB-PRO.

Uses k580.py (wired vendor HID channel). Run with:  pythonw k580_app.py
Changes are written to the keyboard immediately and stored on it.
"""
import colorsys
import ctypes
from ctypes import wintypes
import json
import math
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkfont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k580  # noqa: E402
import k580_theme  # noqa: E402
import k580_tray  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
APP_VERSION = "0.2.0"
UPDATE_URL = "https://api.github.com/repos/nrpabst/k580-vata-pro-control/releases/latest"
RELEASES_PAGE = "https://github.com/nrpabst/k580-vata-pro-control/releases"
PREFS_PATH = os.path.join(HERE, "settings.json")


def load_prefs():
    try:
        with open(PREFS_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_prefs(prefs):
    with open(PREFS_PATH, "w") as fh:
        json.dump(prefs, fh, indent=1)

# ---------------------------------------------------------------- key codes
HID = {}
for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    HID[c.upper()] = 0x04 + i
for i, c in enumerate("1234567890"):
    HID[c] = 0x1E + i
HID.update({
    "Enter": 0x28, "Esc": 0x29, "Backspace": 0x2A, "Tab": 0x2B, "Space": 0x2C, "-": 0x2D, "=": 0x2E,
    "[": 0x2F, "]": 0x30, "\\": 0x31, ";": 0x33, "'": 0x34, "`": 0x35, ",": 0x36, ".": 0x37,
    "/": 0x38, "CapsLock": 0x39, "PrtSc": 0x46, "ScrLk": 0x47, "Pause": 0x48, "Insert": 0x49,
    "Home": 0x4A, "PgUp": 0x4B, "Delete": 0x4C, "End": 0x4D, "PgDn": 0x4E, "Right": 0x4F,
    "Left": 0x50, "Down": 0x51, "Up": 0x52, "NumLock": 0x53, "App": 0x65,
})
for i in range(12):
    HID[f"F{i + 1}"] = 0x3A + i
for i in range(12, 24):
    HID[f"F{i + 1}"] = 0x68 + (i - 12)
HID.update({"Num/": 0x54, "Num*": 0x55, "Num-": 0x56, "Num+": 0x57, "NumEnter": 0x58, "Num0": 0x62,
            "Num.": 0x63})
for i in range(9):
    HID[f"Num{i + 1}"] = 0x59 + i
MODIFIERS = {"LCtrl": 0x01, "LShift": 0x02, "LAlt": 0x04, "LWin": 0x08,
             "RCtrl": 0x10, "RShift": 0x20, "RAlt": 0x40, "RWin": 0x80}


def combo(mods, key=None):
    """Matrix entry for modifier(s) + key, e.g. combo(["LWin"], "D")."""
    bits = 0
    for m in mods:
        bits |= MODIFIERS[m]
    return bytes([0, bits, 0, HID[key] if key else 0])


# stock app's "Mouse" list (type 0x01 entries, from the app's key-code converter)
MOUSE = {
    "Left button": "01010100", "Right button": "01020100", "Middle button": "01030100",
    "Back": "01040100", "Forward": "01050100", "Double click": "01010200",
    "Scroll up": "01080000", "Scroll down": "01090000",
}
# stock app's "Commands" list, as the shortcuts they stand for
COMMANDS = {
    "Close window": (["LAlt"], "F4"), "Lock computer": (["LWin"], "L"), "Run": (["LWin"], "R"),
    "Show desktop": (["LWin"], "D"), "Zoom in": (["LCtrl"], "="), "Zoom out": (["LCtrl"], "-"),
    "Task manager": (["LCtrl", "LShift"], "Esc"), "Undo": (["LCtrl"], "Z"), "Save": (["LCtrl"], "S"),
    "Copy": (["LCtrl"], "C"), "Paste": (["LCtrl"], "V"), "Cut": (["LCtrl"], "X"),
}


def actions():
    """Name -> 4-byte matrix entry for everything a key can be set to (grouped like the stock app)."""
    a = {"Disable": bytes(4)}
    for name, code in HID.items():
        a["Key: " + name] = bytes([0, 0, 0, code])
    for name, bit in MODIFIERS.items():
        a["Key: " + name] = bytes([0, bit, 0, 0])
    for name, hx in MOUSE.items():
        a["Mouse: " + name] = bytes.fromhex(hx)
    for usage, name in k580.CONSUMER.items():
        a["Multimedia: " + name] = bytes([0x02, 0, usage >> 8, usage & 0xFF])
    for name, (mods, key) in COMMANDS.items():
        a["Command: " + name] = combo(mods, key)
    a["Command: Lock Win key"] = bytes([0x07, 0, 0, 0x01])
    a["Fn"] = bytes([0x0D, 0, 0, 0])
    a["Show battery (Fn function)"] = bytes([0x07, 0, 0, 0x11])
    a["Win-key lock (Fn function)"] = bytes([0x07, 0, 0, 0x01])
    a["Brightness + (lighting)"] = bytes.fromhex("08030100")
    a["Brightness - (lighting)"] = bytes.fromhex("08030200")
    a["Speed + (lighting)"] = bytes.fromhex("08040100")
    a["Speed - (lighting)"] = bytes.fromhex("08040200")
    a["Volume/brightness knob mode switch (lighting)"] = bytes.fromhex("07000014")
    a["Knob function 0x19"] = bytes.fromhex("07000019")
    for n in range(5):
        a[f"G{n + 1} macro key"] = bytes([0x07, 0, n, 0x03])
    # custom firmware light switches (bound on the Fn layer automatically)
    a["Media key lights on/off (lighting)"] = bytes.fromhex("07000000")
    a["Volume/brightness key light on/off (lighting)"] = bytes.fromhex("07000013")
    return a


ACTIONS = actions()
ACTION_BY_BYTES = {v: k for k, v in ACTIONS.items()}
CATEGORIES = ["Key", "Mouse", "Multimedia", "Command", "Lighting", "Other"]


def category_of(name):
    for c in CATEGORIES[:-1]:
        if name.startswith(c + ":") or name.startswith(c + " "):
            return c
    if "(lighting)" in name:
        return "Lighting"
    return "Other"


# Windows virtual-key code -> HID usage, for "press the key you want"
VK_TO_HID = {0x0D: 0x28, 0x1B: 0x29, 0x08: 0x2A, 0x09: 0x2B, 0x20: 0x2C, 0xBD: 0x2D, 0xBB: 0x2E,
             0xDB: 0x2F, 0xDD: 0x30, 0xDC: 0x31, 0xBA: 0x33, 0xDE: 0x34, 0xC0: 0x35, 0xBC: 0x36,
             0xBE: 0x37, 0xBF: 0x38, 0x14: 0x39, 0x2C: 0x46, 0x91: 0x47, 0x13: 0x48, 0x2D: 0x49,
             0x24: 0x4A, 0x21: 0x4B, 0x2E: 0x4C, 0x23: 0x4D, 0x22: 0x4E, 0x27: 0x4F, 0x25: 0x50,
             0x28: 0x51, 0x26: 0x52, 0x90: 0x53, 0x6F: 0x54, 0x6A: 0x55, 0x6D: 0x56, 0x6B: 0x57,
             0x60: 0x62, 0x6E: 0x63, 0x5D: 0x65}
VK_TO_HID.update({0x41 + i: 0x04 + i for i in range(26)})                      # A-Z
VK_TO_HID.update({0x31 + i: 0x1E + i for i in range(9)})                       # 1-9
VK_TO_HID[0x30] = 0x27                                                       # 0
VK_TO_HID.update({0x70 + i: 0x3A + i for i in range(12)})                      # F1-F12
VK_TO_HID.update({0x61 + i: 0x59 + i for i in range(9)})                       # Num1-Num9
# Tk keysym of a modifier key -> modifier name
MOD_KEYSYMS = {"Control_L": "LCtrl", "Control_R": "RCtrl", "Shift_L": "LShift", "Shift_R": "RShift",
               "Alt_L": "LAlt", "Alt_R": "RAlt", "Win_L": "LWin", "Win_R": "RWin"}
SHORT_MODS = {"LCtrl": "^", "RCtrl": "^", "LShift": "⇧", "RShift": "⇧", "LAlt": "Alt+", "RAlt": "Alt+",
              "LWin": "Win+", "RWin": "Win+"}
SHORT_MEDIA = {"Play/Pause": "Play", "MediaPlayer": "Media", "Calculator": "Calc", "MyComputer": "PC",
               "WWW Search": "Srch", "WWW Home": "Home", "WWW Back": "Back", "WWW Fwd": "Fwd",
               "WWW Stop": "Stop", "WWW Refresh": "Rfrsh", "WWW Favorites": "Favs"}
SHORT_MOUSE = {"Left button": "M1", "Right button": "M2", "Middle button": "M3", "Back": "MBack",
               "Forward": "MFwd", "Double click": "M1x2", "Scroll up": "Whl↑", "Scroll down": "Whl↓"}


# keyboard functions (07 00 00 nn) the stock Fn layer uses, from the firmware's dispatch table
KEY_FUNCTIONS = {0x01: ("Win-key lock", "WinLk"), 0x04: ("Reset to defaults (hold)", "Reset"),
                 0x05: ("Bluetooth device 1", "BT1"), 0x06: ("Bluetooth device 2", "BT2"),
                 0x07: ("Bluetooth device 3", "BT3"), 0x08: ("2.4G pairing", "2.4G"),
                 0x09: ("Switch to cable", "Cable"), 0x11: ("Show battery", "Batt"),
                 0x12: ("One-colour lighting", "1Col")}


def short_label(entry):
    """A key-cap sized (≤5 chars) name for what a matrix entry does."""
    name = describe(entry)
    kind, _, rest = name.partition(": ")
    if entry == bytes(4):
        return "—"
    if kind == "Key":
        rest = KeyboardView.SHORT.get(rest, rest)
        return rest[:5]
    if kind == "Combination":
        parts = rest.split(" + ")
        key = parts[-1] if parts[-1] not in MODIFIERS else ""
        mods = "".join(SHORT_MODS.get(m, "") for m in parts if m in MODIFIERS)
        return (mods + key)[:5]
    if kind == "Multimedia":
        return SHORT_MEDIA.get(rest, rest)[:5]
    if kind == "Mouse":
        return SHORT_MOUSE.get(rest, rest)[:5]
    if kind == "Command":
        return rest[:5]
    if name == "Fn":
        return "Fn"
    if name.endswith("macro key"):
        return name.split()[0]
    if name.startswith("Volume/brightness knob mode"):
        return "Mode"
    if name.startswith("Knob function"):
        return "Knob"
    if "on/off (lighting)" in name:
        return "LtOn"
    if "(lighting)" in name:
        return name[:5]
    if entry[0] == 0x07 and entry[3] in KEY_FUNCTIONS:
        return KEY_FUNCTIONS[entry[3]][1]
    if entry[0] == 0x07:
        return "Fn"
    if entry[0] == 0x08:
        return "Light"
    return "•"


def describe(entry):
    name = ACTION_BY_BYTES.get(entry)
    if name:
        return name
    if entry[0] == 0x07 and entry[2] == 0 and entry[3] in KEY_FUNCTIONS:
        return "Keyboard function: " + KEY_FUNCTIONS[entry[3]][0]
    if entry[0] == 0 and entry[1] and entry[3]:
        mods = [m for m, bit in MODIFIERS.items() if entry[1] & bit]
        key = next((k for k, c in HID.items() if c == entry[3]), hex(entry[3]))
        return "Combination: " + " + ".join(mods + [key])
    return k580.describe_key(entry)

# Tk keysym -> HID usage, for the macro recorder
TK_TO_HID = {k.lower(): v for k, v in HID.items() if len(k) == 1}
TK_TO_HID.update({
    "return": 0x28, "escape": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C, "minus": 0x2D,
    "equal": 0x2E, "bracketleft": 0x2F, "bracketright": 0x30, "backslash": 0x31, "semicolon": 0x33,
    "apostrophe": 0x34, "quoteright": 0x34, "grave": 0x35, "quoteleft": 0x35, "comma": 0x36,
    "period": 0x37, "slash": 0x38, "caps_lock": 0x39, "print": 0x46, "scroll_lock": 0x47,
    "pause": 0x48, "insert": 0x49, "home": 0x4A, "prior": 0x4B, "delete": 0x4C, "end": 0x4D,
    "next": 0x4E, "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52, "num_lock": 0x53,
    "app": 0x65, "menu": 0x65,
    "control_l": 0xE0, "shift_l": 0xE1, "alt_l": 0xE2, "win_l": 0xE3,
    "control_r": 0xE4, "shift_r": 0xE5, "alt_r": 0xE6, "win_r": 0xE7,
})
for _i in range(1, 13):
    TK_TO_HID[f"f{_i}"] = 0x39 + _i

SHIFTED = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8",
           "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";",
           '"': "'", "~": "`", "<": ",", ">": ".", "?": "/"}


def text_to_events(text, delay=15):
    ev = k580.macro_event
    out = []
    for ch in text:
        shift = ch.isupper() or ch in SHIFTED
        base = SHIFTED.get(ch, ch)
        if base == " ":
            code = HID["Space"]
        elif base == "\n":
            code = HID["Enter"]
        else:
            code = HID.get(base.upper())
        if code is None:
            raise ValueError(f"can't type {ch!r}")
        if shift:
            out.append(ev(0xE1, False, delay))
        out += [ev(code, False, delay), ev(code, True, delay)]
        if shift:
            out.append(ev(0xE1, True, delay))
    return out


def parse_g_slot(slot):
    """A G-key recording (made on the keyboard): [len][0x11][0][0] then 4-byte events
    [delay low][HID usage][delay high bits][extra]. Each key appears once going down and once going
    up, so events toggle. Returns the keys pressed in order, with held modifiers folded in
    (e.g. ["Enter", "RShift+1", "Enter"]), or None if the slot is empty."""
    if not slot or slot[1] != 0x11 or slot[0] < 6:
        return None
    names = {v: k for k, v in HID.items()}
    names.update({0xE0 + i: m for i, m in enumerate(("LCtrl", "LShift", "LAlt", "LWin",
                                                     "RCtrl", "RShift", "RAlt", "RWin"))})
    down, held, out = set(), [], []
    end = min(len(slot), slot[0] + 2)
    for i in range(4, end - 3, 4):
        code = slot[i + 1]
        name = names.get(code, f"0x{code:02X}")
        pressed = code not in down
        down ^= {code}
        if 0xE0 <= code <= 0xE7:
            if pressed:
                held.append(name)
            elif name in held:
                held.remove(name)
        elif pressed:
            out.append("+".join(held + [name]))
    return out


G_SLOT = 0x80                         # bytes per G-key recording slot
G_SLOTS_AT = 1024                     # offset of slot 0 in the 0x05 macro area (flash 0xE000)
G_SLOT_COUNT = 20                     # 4 banks x G1-G5


def build_g_slot(events):
    """App macro events (k580.macro_event format) -> a G-key slot, the way the keyboard records:
    [len][0x11][0][0] then [delay low][HID][0x80 for a normal key going down | delay high][0]."""
    out = bytearray()
    for ev in events:
        release, kind = ev[0] & 0x80, (ev[0] >> 4) & 0x07
        delay = ((ev[0] & 0x0F) << 16) | (ev[1] << 8) | ev[2]
        code = ev[3]
        if kind > 1:
            raise ValueError("G keys can only play keyboard keys (no mouse actions).")
        hi = min(delay >> 8, 0x7F)
        flag = 0x80 if (kind == 0 and not release) else 0
        out += bytes([delay & 0xFF if delay < 0x8000 else 0xFF, code, flag | hi, 0])
    if len(out) + 4 > G_SLOT:
        raise ValueError(f"Too long for a G key: {len(out) // 8} keys fit at most "
                         f"{(G_SLOT - 4) // 8} key presses.")
    slot = bytes([len(out) + 2, 0x11, 0, 0]) + out
    return slot + bytes(G_SLOT - len(slot))


def parse_macros(buf):
    """Read the app-macro table back into [(name, body_bytes)]."""
    first = int.from_bytes(buf[0:2], "little")
    if first == 0 or first % 4:
        return []
    out = []
    for i in range(first // 4):
        off = int.from_bytes(buf[i * 4:i * 4 + 2], "little")
        size = int.from_bytes(buf[i * 4 + 2:i * 4 + 4], "little")
        body = buf[off:off + size]
        n = body[0]
        out.append((body[1:1 + n].decode("utf-16le", "replace"), body[1 + n:]))
    return out


def effect_slot(hw):
    """Effect `hw` keeps its brightness/speed/color at lighting bytes 0x3A + 2 * slot (slot = hw - 1)."""
    return hw - 1 if hw in k580.SLOT_HW else None


# ---------------------------------------------------------------- app
class KeyboardView(tk.Canvas):
    """Clickable picture of the K580. Keys can be selected, filled with a colour, or marked."""

    SCALE = 0.80                     # fills the window width
    SHORT = {"Backspace": "Bksp", "CapsLock": "Caps", "LShift": "Shift", "RShift": "Shift",
             "LCtrl": "Ctrl", "RCtrl": "Ctrl", "Insert": "Ins", "Delete": "Del", "NumLock": "NmLk",
             "NumEnter": "Ent", "Space": "Space", "Media1": "Prev", "Media2": "Play", "Media3": "Next",
             "K105": "Mode", "K114": "Wheel"}
    # numpad keys: drop the "Num" so the label fits the key
    SHORT.update({f"Num{c}": c for c in "0123456789/*-+."})
    SHORT.update({"NumEnter": "Ent", "NumLock": "Lock"})
    # names that are too wide for a 1-wide key
    SHORT.update({"PrtSc": "Prt", "ScrLk": "Scr", "Pause": "Pse", "Home": "Hm", "PgUp": "Pg↑",
                  "PgDn": "Pg↓", "Up": "↑", "Down": "↓", "Left": "←", "Right": "→"})

    def __init__(self, master, on_click, labels=True):
        import k580_layout
        s = self.SCALE
        super().__init__(master, width=int(745 * s), height=int(240 * s), bg=k580_theme.BG,
                         highlightthickness=0)
        self.on_click = on_click
        self.selected = set()
        self.marked = set()
        self.fills = {}
        self.rects = {}
        self.texts = {}
        # keys that have no position in the layout file: G1-G5, mode/wheel keys, media keys
        extra = [(6, "G1"), (23, "G2"), (29, "G3"), (41, "G4"), (47, "G5"),
                 (77, "Mode"), (71, "Wheel"), (88, "Prev"), (113, "Play"), (125, "Next")]
        layout = list(k580_layout.LAYOUT) + [(idx, 21 + n * 50 + (30 if n >= 5 else 0), 252,
                                              21 + n * 50 + (30 if n >= 5 else 0) + 44, 277)
                                             for n, (idx, _) in enumerate(extra)]
        for idx, x1, y1, x2, y2 in layout:
            r = self.create_rectangle(x1 * s, (y1 - 45) * s, x2 * s, (y2 - 45) * s,
                                      fill=k580_theme.FIELD, outline=k580_theme.BORDER, width=1)
            self.rects[idx] = r
            items = [r]
            name = k580.KEY_NAMES.get(idx, "")
            name = self.SHORT.get(name, name)
            if labels:
                text, font = self.fit_label(name, (x2 - x1) * s)
                t = self.create_text((x1 + x2) / 2 * s, ((y1 + y2) / 2 - 45) * s, text=text,
                                     fill=k580_theme.MUTED, font=font)
                self.texts[idx] = t
                items.append(t)
            for it in items:
                self.tag_bind(it, "<Button-1>", lambda e, i=idx: self._click(i))
        self.redraw()

    def _click(self, idx):
        self.selected ^= {idx}
        self.redraw()
        self.on_click(idx)

    def select_all(self, on):
        self.selected = set(self.rects) if on else set()
        self.redraw()
        self.on_click(None)

    def centers(self):
        """{matrix index: (x, y)} of each key's centre, scaled to 0..1."""
        boxes = {i: self.coords(r) for i, r in self.rects.items()}
        w, h = int(self.cget("width")), int(self.cget("height"))
        return {i: ((b[0] + b[2]) / 2 / w, (b[1] + b[3]) / 2 / h) for i, b in boxes.items()}

    _fonts = {}

    @classmethod
    def fit_label(cls, text, key_px):
        """(text, font) that fits inside a key `key_px` wide: smaller type first, then fewer letters."""
        room = key_px - 4
        for size in (7, 6, 5):
            f = cls._fonts.setdefault(size, tkfont.Font(family="Segoe UI", size=size))
            if f.measure(text) <= room:
                return text, ("Segoe UI", size)
        while text and cls._fonts[5].measure(text) > room:
            text = text[:-1]
        return text, ("Segoe UI", 5)

    def set_labels(self, labels, highlight=()):
        """Replace key labels ({idx: text}); keys in `highlight` are drawn brighter."""
        for idx, t in self.texts.items():
            if idx in labels:
                x1, _, x2, _ = self.coords(self.rects[idx])
                text, font = self.fit_label(labels[idx], x2 - x1)
                self.itemconfig(t, text=text, font=font,
                                fill=k580_theme.FG if idx in highlight else k580_theme.MUTED)

    def set_fills(self, fills):
        self.fills = dict(fills)
        self.redraw()

    def set_marked(self, marked):
        self.marked = set(marked)
        self.redraw()

    def redraw(self):
        accent = k580_theme.hue_hex(getattr(self.master.winfo_toplevel(), "_accent_phase", 0.5), 0.65)
        shown = self.__dict__.setdefault("_shown", {})
        for idx, r in self.rects.items():
            c = self.fills.get(idx)
            fill = "#%02x%02x%02x" % c if c else k580_theme.FIELD
            if idx in self.selected:
                look = (fill, "#ffffff", 3)
            elif idx in self.marked:
                look = (fill, accent, 2)
            else:
                look = (fill, k580_theme.BORDER, 1)
            if shown.get(idx) != look:            # only touch keys that changed (the preview redraws a lot)
                shown[idx] = look
                self.itemconfig(r, fill=look[0], outline=look[1], width=look[2])


class ColorPicker(ttk.Frame):
    """Preset colour swatches, a small hue/saturation wheel, a brightness slider and a preview."""

    PRESETS = [(255, 0, 0), (255, 96, 0), (255, 200, 0), (0, 255, 0), (0, 255, 160), (0, 220, 255),
               (0, 64, 255), (128, 0, 255), (255, 0, 200), (255, 255, 255), (255, 140, 80), (0, 0, 0)]
    WHEEL = 104

    def __init__(self, master, on_pick):
        super().__init__(master)
        self.on_pick = on_pick
        self.hsv = [0.0, 1.0, 1.0]

        sw = ttk.Frame(self)
        sw.grid(row=0, column=0, sticky="nw")
        for n, rgb in enumerate(self.PRESETS):
            c = tk.Canvas(sw, width=26, height=26, bg=k580_theme.PANEL, highlightthickness=0, cursor="hand2")
            c.create_rectangle(2, 2, 24, 24, fill="#%02x%02x%02x" % rgb,
                               outline=k580_theme.BORDER if rgb != (0, 0, 0) else k580_theme.MUTED)
            if rgb == (0, 0, 0):
                c.create_line(5, 21, 21, 5, fill=k580_theme.MUTED)          # "off"
            c.grid(row=n // 6, column=n % 6, padx=2, pady=4)
            c.bind("<Button-1>", lambda e, v=rgb: self._user_pick(v))

        self.preview = tk.Canvas(sw, width=176, height=24, bg=k580_theme.PANEL, highlightthickness=0)
        self.preview.grid(row=2, column=0, columnspan=6, pady=(12, 0), sticky="w")
        self.prev_rect = self.preview.create_rectangle(2, 2, 60, 22, fill="#ff0000", outline=k580_theme.BORDER)
        self.prev_text = self.preview.create_text(68, 12, text="#FF0000", anchor="w", fill=k580_theme.FG,
                                                  font=("Consolas", 9))

        size = self.WHEEL
        self.wheel = tk.Canvas(self, width=size, height=size, bg=k580_theme.PANEL, highlightthickness=0,
                               cursor="crosshair")
        self.wheel.grid(row=0, column=1, padx=(18, 0), sticky="n")
        self.img = tk.PhotoImage(width=size, height=size)
        self._draw_wheel()
        self.wheel.create_image(0, 0, image=self.img, anchor="nw")
        self.marker = self.wheel.create_oval(0, 0, 0, 0, outline="#ffffff", width=2)
        self.wheel.bind("<Button-1>", self._wheel_click)
        self.wheel.bind("<B1-Motion>", self._wheel_click)
        self.user = False                 # on_pick only fires for the user's own clicks and drags

        self.val = tk.DoubleVar(value=1.0)
        vs = ttk.Scale(self, from_=1.0, to=0.0, variable=self.val, orient="vertical", length=size,
                       command=lambda v: self._from_hsv())
        vs.grid(row=0, column=2, padx=(8, 0), sticky="n")
        vs.bind("<ButtonPress-1>", lambda e: setattr(self, "user", True))
        self._place_marker()

    def _draw_wheel(self):
        size = self.WHEEL
        r0 = size / 2
        bg = k580_theme.PANEL
        rows = []
        for y in range(size):
            row = []
            for x in range(size):
                dx, dy = x - r0 + 0.5, y - r0 + 0.5
                d = math.hypot(dx, dy) / r0
                if d > 1:
                    row.append(bg)
                else:
                    h = (math.atan2(-dy, dx) / (2 * math.pi)) % 1.0
                    row.append(k580_theme.hue_hex(h, d, 1.0))
            rows.append("{" + " ".join(row) + "}")
        self.img.put(" ".join(rows))

    def _user_pick(self, rgb):
        self.user = True
        self.pick(rgb)

    def show(self, rgb):
        """Display a colour without reporting it (e.g. to show what's already on the keyboard)."""
        self.user = False
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        self.hsv = [h, s, v]
        self.val.set(v)
        self._place_marker()
        self._show(rgb)

    def _wheel_click(self, e):
        self.user = True
        r0 = self.WHEEL / 2
        dx, dy = e.x - r0, e.y - r0
        d = min(math.hypot(dx, dy) / r0, 1.0)
        self.hsv[0] = (math.atan2(-dy, dx) / (2 * math.pi)) % 1.0
        self.hsv[1] = d
        self._place_marker()
        self._from_hsv()

    def _place_marker(self):
        r0 = self.WHEEL / 2
        a = self.hsv[0] * 2 * math.pi
        x = r0 + math.cos(a) * self.hsv[1] * r0
        y = r0 - math.sin(a) * self.hsv[1] * r0
        self.wheel.coords(self.marker, x - 5, y - 5, x + 5, y + 5)

    def _from_hsv(self):
        r, g, b = colorsys.hsv_to_rgb(self.hsv[0], self.hsv[1], self.val.get())
        self._show((int(r * 255), int(g * 255), int(b * 255)))

    def pick(self, rgb):
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        self.hsv = [h, s, v]
        self.val.set(v)
        self._place_marker()
        self._show(rgb)

    def _show(self, rgb):
        hx = "#%02x%02x%02x" % rgb
        self.preview.itemconfig(self.prev_rect, fill=hx)
        self.preview.itemconfig(self.prev_text, text=hx.upper() if rgb != (0, 0, 0) else "off")
        if self.user:
            self.on_pick(rgb)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("K580 Control")
        self.geometry("660x1000")
        self.minsize(640, 520)                       # raised to fit the pages by fit_window()
        self.kb = None
        self.wl = None
        self.led = None
        style = k580_theme.apply(self)

        k580_theme.RGBHeader(self, style).pack(fill="x")
        top = ttk.Frame(self, padding=(18, 10, 20, 6), style="Header.TFrame")
        top.pack(fill="x")
        self.status = ttk.Label(top, text="Not connected", style="Header.TLabel")
        self.status.pack(side="left")
        self.battery = ttk.Label(top, text="", style="Header.TLabel")
        self.battery.pack(side="left", padx=(16, 0))
        # placed by hand so it sits between the status line and the tabs, on the right
        self.reconnect_btn = ttk.Button(self, text="Reconnect", command=self.connect, style="AccentText.TButton")
        self.reconnect_btn.place(relx=1.0, x=-58, y=87, anchor="ne")
        self.after_idle(self.reconnect_btn.lift)            # above the header row and the tab strip

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.nb = nb
        self.slider_busy = False
        self.build_lighting(nb)
        self.build_keys(nb)
        self.build_macros(nb)
        self.build_settings(nb)
        self.build_firmware(nb)
        self.connect()
        if "--tab" in sys.argv:                  # e.g. --tab Macros (handy for screenshots)
            want = sys.argv[sys.argv.index("--tab") + 1]
            for t in nb.tabs():
                if nb.tab(t, "text") == want:
                    nb.select(t)

        # system tray: closing the window hides it; the tray icon brings it back or quits
        self.prefs = load_prefs()
        if self.prefs.get("geometry"):              # reopen at the size/position it was left
            try:
                self.geometry(self.prefs["geometry"])
            except tk.TclError:
                pass
        self.after(300, self.fit_window)             # once the window is on screen and measurable
        self.iconbitmap(default=k580_tray.icon_path())
        self.tray = k580_tray.Tray()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(200, self.poll_tray)
        self.after(1000, self.poll_lighting)
        self.after(500, self.animate_preview)
        if "--tray" in sys.argv:
            self.withdraw()

    def fit_window(self):
        """Never narrower than the widest page plus its scrollbar, so nothing is cut off on the right,
        and at least tall enough for the Lighting page when the screen has room."""
        widest = max(i.winfo_reqwidth() for _o, _c, i in self.pages)
        bar = ttk.Scrollbar(self).winfo_reqwidth()
        outer = self.nametowidget(self.nb.select())
        if outer.winfo_width() < 50:                         # not laid out yet
            self.after(300, self.fit_window)
            return
        side = self.winfo_width() - outer.winfo_width()      # notebook padding and borders
        need_w = widest + bar + side
        self.minsize(need_w, 520)
        _o, canvas, inner = self.pages[0]                       # Lighting
        need_h = self.winfo_height() + inner.winfo_reqheight() - canvas.winfo_height()
        w, h = max(self.winfo_width(), need_w), self.winfo_height()
        x, y = self.winfo_x(), self.winfo_y()
        if h < need_h:
            rect = wintypes.RECT()                              # the screen minus the taskbar
            ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
            title = self.winfo_rooty() - y                      # title bar height
            h = min(need_h, rect.bottom - rect.top - title - 8)
            y = max(rect.top, min(y, rect.bottom - h - title - 8))
        if (w, h, y) != (self.winfo_width(), self.winfo_height(), self.winfo_y()):
            self.geometry(f"{w}x{h}+{x}+{y}")

    def remember_geometry(self):
        if self.state() == "normal":
            self.prefs["geometry"] = self.geometry()
            save_prefs(self.prefs)

    def on_close(self):
        self.remember_geometry()
        if self.prefs.get("close_to_tray", True):
            self.withdraw()
            if not self.prefs.get("tray_hint_shown"):
                self.tray.notify("K580 Control is still running",
                                 "It's in the system tray. Right-click the icon to quit.")
                self.prefs["tray_hint_shown"] = True
                save_prefs(self.prefs)
        else:
            self.quit_app()

    def poll_tray(self):
        try:
            while True:
                ev = self.tray.events.get_nowait()
                if ev == "open":
                    self.deiconify()
                    self.lift()
                    self.focus_force()
                elif ev == "quit":
                    self.quit_app()
                    return
                elif ev == "devices":           # cable or dongle plugged/unplugged: look right away
                    self.after(300, self.watch_connection)
                    self.after(1500, self.watch_connection)
        except Exception:
            pass
        # the dongle reports the keyboard switching on/off (command 0x0A) without being asked
        if self.wl and any(len(r) > 1 and r[1] & 0x7F == 0x0A for r in list(self.wl.replies)):
            self.wl.replies.clear()
            self.after(200, self.watch_connection)
        self.after(200, self.poll_tray)

    def quit_app(self):
        try:
            self.remember_geometry()
        except Exception:
            pass
        self.tray.close()
        for dev in (self.kb, self.wl):
            if dev:
                dev.close()
        self.destroy()

    # ---------------- connection
    def connect(self):
        for dev in (self.kb, getattr(self, "wl", None)):
            if dev:
                dev.close()
        self.kb = self.wl = None
        try:
            self.kb = k580.K580()
            self.status.config(text="Connected by cable  ✓")
            first = os.path.join(HERE, "backups", "first-run.json")
            if not os.path.exists(first):
                os.makedirs(os.path.dirname(first), exist_ok=True)
                with open(first, "w") as fh:
                    json.dump(k580.backup(self.kb), fh, indent=1)
            self.kb.fix_rgb_table()             # single-colour effects go black if this table is broken
            self.load_lighting()
            self.load_colors()
            self.load_macros()
            return
        except SystemExit:
            pass
        try:
            import k580_wireless
            self.wl = k580_wireless.Dongle()
            data, _ = self.wl.query(0x07)
            if data[:1] == b"\x01":
                self.status.config(text="Connected by 2.4G dongle  ✓  (lighting only)")
                self.load_lighting()
                return
            self.wl.close()
            self.wl = None
        except SystemExit:
            pass
        self.status.config(text="Keyboard not found. Plug in the dongle or cable, then Reconnect.")
        self.battery.config(text="")

    def get_led(self):
        if self.kb:
            return self.kb.get_led()
        data, _ = self.wl.query(0x44)
        return data

    def set_led(self, led):
        if self.kb:
            self.kb.write(k580.OP_LED, bytes(led))
        else:
            import k580_wireless
            k580_wireless.write(self.wl, 0x04, bytes(led))

    def need_kb(self):
        if not self.kb:
            messagebox.showwarning("K580", "Connect the keyboard by cable (wireless switch off), then Reconnect.")
            return False
        return True

    # ---------------- lighting
    def build_lighting(self, nb):
        f, self.lkb, self.preview_note = self.keyboard_page(
            nb, "Lighting", self.preview_clicked, "Preview of the current effect (an approximation).")
        self.lkb_centers = self.lkb.centers()
        f.columnconfigure(0, minsize=120)
        f.columnconfigure(1, weight=1)
        names = k580.effect_names(os.path.exists(self.EFFECTS_MARKER))   # updated once the firmware is read
        self.effect = tk.StringVar()
        self.bright = tk.DoubleVar()
        self.speed = tk.DoubleVar()
        self.color = tk.StringVar()
        ttk.Label(f, text="Effect").grid(row=2, column=0, sticky="nw", pady=(12, 0))
        ecell = ttk.Frame(f)
        ecell.grid(row=2, column=1, sticky="w", pady=(8, 0))
        erow = ttk.Frame(ecell)
        erow.pack(anchor="w")
        ec = self.effect_combo = ttk.Combobox(erow, textvariable=self.effect, values=names, state="readonly",
                                              width=24)

        def step(d):
            # previous / next effect, wrapping round
            names = list(self.effect_combo.cget("values"))
            cur = names.index(self.effect.get()) if self.effect.get() in names else 0
            self.effect.set(names[(cur + d) % len(names)])
            self.apply_lighting(new_effect=True)
        ttk.Button(erow, text="◀", width=3, command=lambda: step(-1)).pack(side="left", padx=(0, 4))
        ec.pack(side="left")
        ttk.Button(erow, text="▶", width=3, command=lambda: step(1)).pack(side="left", padx=(4, 0))
        # how-to for Self-define, shown right under the effect box only when it's picked
        self.sd_note = ttk.Label(ecell, style="Muted.TLabel", text=(
            "Click keys on the keyboard above, then pick a colour.\n"
            "It's saved to the keyboard as you go."))
        ec.bind("<<ComboboxSelected>>", lambda e: self.apply_lighting(new_effect=True))
        ttk.Label(f, text="Brightness").grid(row=3, column=0, sticky="w", pady=8)
        self.snap_slider(f, self.bright, self.brightness_levels).grid(row=3, column=1, sticky="w", pady=6)
        ttk.Label(f, text="Speed").grid(row=4, column=0, sticky="w", pady=8)
        self.speed_slider = self.snap_slider(f, self.speed)
        self.speed_slider.grid(row=4, column=1, sticky="w", pady=6)
        ttk.Label(f, text="Color").grid(row=5, column=0, sticky="nw", pady=(12, 0))
        ccell = ttk.Frame(f)
        ccell.grid(row=5, column=1, sticky="w", pady=(8, 0))
        self.palette = bytearray(k580.DEFAULT_PALETTE * 24)   # the keyboard's 7 colours per effect
        self.color_box = self.color_swatches(ccell)
        self._palette_job = self._keys_job = None
        self._syncing = False
        # Self-define: per-key colours, painted on the keyboard picture above
        self.ckb = self.lkb
        self.key_colors = {}            # matrix index -> (r, g, b)
        self.sel_row = ttk.Frame(ccell)
        ttk.Button(self.sel_row, text="Select all", command=lambda: self.lkb.select_all(True)) \
            .pack(side="left", padx=(0, 8))
        ttk.Button(self.sel_row, text="Select none", command=lambda: self.lkb.select_all(False)).pack(side="left")
        self.lpicker = ColorPicker(ccell, on_pick=self.lighting_pick)
        self.reset_btn = ttk.Button(ccell, text="Reset colour", command=self.reset_effect_colors)
        self.ccell = ccell
        self.layout_color_cell(False)
        self.effect_note = ttk.Label(f, text="Changes apply instantly.", style="Muted.TLabel", wraplength=560)
        self.effect_note.grid(row=6, column=0, columnspan=2, sticky="w", pady=12)

        ttk.Separator(f).grid(row=7, column=0, columnspan=2, sticky="ew", pady=12)
        # bottom: key lights (left) and side lights (right), side by side
        bottom = ttk.Frame(f)
        bottom.grid(row=8, column=0, columnspan=2, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        kl = ttk.Frame(bottom)
        kl.grid(row=0, column=0, sticky="nw")
        ttk.Label(kl, text="Key lights", font=k580_theme.FONT_BOLD).pack(anchor="w", pady=(0, 6))
        self.media_on = tk.BooleanVar(value=True)
        self.media_toggle = ttk.Checkbutton(kl, text="Keep media-key lights on", variable=self.media_on,
                                            command=self.set_media_leds)
        self.media_toggle.pack(anchor="w")
        self.wheel_on = tk.BooleanVar(value=False)
        self.wheel_toggle = ttk.Checkbutton(kl, text="Keep volume/brightness key on",
                                            variable=self.wheel_on, command=self.set_wheel_led)
        self.wheel_toggle.pack(anchor="w", pady=(8, 0))
        self.media_note = ttk.Label(kl, text="", style="Muted.TLabel", wraplength=280, justify="left")
        self.media_note.pack(anchor="w", pady=(6, 0))

        # side lights (the strips on either side of the keyboard): lighting bytes 0x12-0x15
        sf = ttk.Frame(bottom)
        sf.grid(row=0, column=1, sticky="ne", padx=(16, 0))
        ttk.Label(sf, text="Side lights", font=k580_theme.FONT_BOLD).pack(anchor="w", pady=(0, 6))
        self.side_mode = tk.StringVar()
        self.side_bright = tk.DoubleVar()
        self.side_speed = tk.DoubleVar()
        sm = ttk.Combobox(sf, textvariable=self.side_mode, values=list(self.SIDE_MODES), state="readonly",
                          width=22)
        sm.pack(anchor="w")
        sm.bind("<<ComboboxSelected>>", lambda e: self.apply_side())
        for text, var in (("Brightness", self.side_bright), ("Speed", self.side_speed)):
            row = ttk.Frame(sf)
            row.pack(anchor="w", pady=(6, 0))
            ttk.Label(row, text=text, width=9).pack(side="left")
            self.snap_slider(row, var, length=150, on_done=self.apply_side).pack(side="left")

    def preview_clicked(self, idx):
        """Self-define: clicking keys selects them for painting. Otherwise the keyboard is only a
        preview, so don't keep keys selected."""
        if self.current_hw() != 21:
            self.lkb.selected.clear()
            self.lkb.redraw()

    def layout_color_cell(self, self_define):
        """Self-define: Select all/none + wheel. Other effects: Solid colour/Rainbow + wheel + Reset."""
        for w in (self.color_box, self.sel_row, self.lpicker, self.reset_btn):
            w.pack_forget()
        if self_define:
            self.sel_row.pack(anchor="w")
            self.lpicker.pack(anchor="w", pady=(10, 0))
        else:
            self.color_box.pack(anchor="w")
            self.lpicker.pack(anchor="w", pady=(10, 0))
            self.reset_btn.pack(anchor="w", pady=(8, 0))
            if self.lkb.selected:
                self.lkb.selected.clear()
                self.lkb.redraw()

    def lighting_pick(self, rgb):
        """The Lighting wheel: paints the selected keys in Self-define, else sets the effect colour."""
        if self.current_hw() == 21:
            self.apply_color(rgb)
        else:
            self.pick_effect_color(rgb)

    def animate_preview(self):
        """Redraw the Lighting page's keyboard ~20 times a second while it's showing."""
        import k580_preview
        self.after(50, self.animate_preview)
        if self.state() != "normal" or self.nb.tab(self.nb.select(), "text") != "Lighting":
            return
        name = self.effect.get()
        hw = next((h for h, n in k580.EFFECTS.items() if n == name), 0)
        color = k580.COLORS.index(self.color.get()) if self.color.get() in k580.COLORS else 7
        speed = self.speed.get() / 4
        level = self.bright.get() / max(1, self.brightness_levels())
        fills = k580_preview.frame(hw, time.time(), self.lkb_centers, color, speed,
                                   getattr(self, "key_colors", None),
                                   [self.effect_color(i, hw) for i in range(7)])
        bg = (0x1d, 0x20, 0x2a)                      # k580_theme.FIELD: unlit keys keep their colour
        out = {}
        for i, c in fills.items():
            c = [v * level for v in c]
            out[i] = tuple(int(max(b, v)) for b, v in zip(bg, c))
        # media keys and the volume/brightness key have their own white LEDs
        for i in (88, 113, 125):
            if self.media_on.get():
                out[i] = (220, 220, 220)
        if self.wheel_on.get():
            out[77] = (220, 220, 220)
        self.lkb.set_fills(out)

    # ---------------- firmware page
    FIRMWARE_NOTE = (
        "The custom firmware lets you keep the media-key and volume-key lights on all the\n"
        "time, instead of them only flashing when pressed. You turn them on or off on the\n"
        "Lighting page or with Fn + Play/Pause and Fn + the volume/brightness key. It also lets\n"
        "the app show your battery level.\n\n"
        "Installing takes about 15 seconds. Plug in the cable and switch wireless off first.\n"
        "Your settings are kept, and Uninstall puts the original firmware back.")

    def build_firmware(self, nb):
        f = self.page(nb, "Firmware", 12)
        ttk.Label(f, text=self.FIRMWARE_NOTE, justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(f, text="Installed now:").grid(row=1, column=0, sticky="w", pady=(14, 8))
        self.fw_state = ttk.Label(f, text="(connect the cable to check)")
        self.fw_state.grid(row=1, column=1, sticky="w", pady=(14, 8))
        self.auto_wired = tk.BooleanVar(value=False)
        self.fw_auto = ttk.Checkbutton(f, text="Auto Wired Mode", variable=self.auto_wired)
        self.fw_auto.grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Label(f, text='The stock firmware requires the switch to be set to "Off" to use wired mode. '
                          "This option automatically switches to wired mode when the USB cable is "
                          "connected. You will not be able to charge over USB and connect to the "
                          "wireless dongle simultaneously.",
                  style="Muted.TLabel", wraplength=560, justify="left") \
            .grid(row=3, column=0, columnspan=2, sticky="w", padx=(26, 0), pady=(2, 4))
        self.fw_install = ttk.Button(f, text="Install custom firmware",
                                     command=lambda: self.install_firmware(removing=False),
                                     style="Accent.TButton")
        self.fw_install.grid(row=4, column=0, sticky="w", pady=10)
        self.fw_uninstall = ttk.Button(f, text="Uninstall (restore stock firmware)",
                                       command=lambda: self.install_firmware(removing=True))
        self.fw_uninstall.grid(row=4, column=1, sticky="w", pady=10)
        self.fw_hint = ttk.Label(f, text="", style="Muted.TLabel")
        self.fw_hint.grid(row=5, column=0, columnspan=2, sticky="w")
        nb.bind("<<NotebookTabChanged>>",
                lambda e: self.refresh_media_state() if nb.tab(nb.select(), "text") == "Firmware" else None,
                add="+")

    # ---------------- media-key lights (firmware)
    # The "switch" firmware lights the media keys unless lighting byte 0x11 is set
    # (stock firmware uses that byte for an unbound WASD/arrow swap, which this variant drops).
    MEDIA_BYTE = 0x11
    WHEEL_BYTE = 0x30   # custom firmware: non-zero keeps the volume/brightness key lit
    MARKER = os.path.join(HERE, "firmware", "installed-switch-firmware.txt")
    EFFECTS_MARKER = os.path.join(HERE, "firmware", "installed-effects.txt")

    def firmware_variant(self):
        """Which firmware the cabled keyboard runs (cached per connection)."""
        if getattr(self, "_variant_for", None) is not self.kb:
            self._variant_for, self._variant = self.kb, self._read_variant()
        return self._variant

    def _read_variant(self):
        import k580_patch
        flash = self.kb.read_flash
        site = flash(0x2B00, 2)
        if site == b"\x20\x27":
            if flash(0x2AD8, 3) != b"\x02\x0f\x6a":
                return "switch-old"
            addr, code = k580_patch.FINE_BRIGHTNESS_SITE
            if flash(addr, len(code)) == code:
                return "switch-fine"
            latest = all(flash(a, len(c)) == c for a, c in k580_patch.LATEST_SITES)
            addr, code = k580_patch.AUTO_WIRED_SITE
            self._auto_installed = flash(addr, len(code)) == code
            # the extra effects: any custom build that has the effect-switch hook (older or latest)
            self._has_effects = flash(0x2013, 3) == bytes.fromhex(k580_patch.EFFECTS_PATCH[0][2])
            return "switch" if latest else "switch-nofn"
        if site == b"\x20\x6e":
            return "toggle"
        if flash(0x2AFE, 1)[0] == 0x80:
            return "always"
        return "stock"

    def refresh_media_state(self):
        if self.kb:
            v = self.firmware_variant()
            if v.startswith("switch"):
                os.makedirs(os.path.dirname(self.MARKER), exist_ok=True)
                open(self.MARKER, "w").write(v + "\n")
            elif os.path.exists(self.MARKER):
                os.remove(self.MARKER)
        else:
            v = self.marker_variant() or "unknown"
        if v == "switch" and self.kb:
            self.ensure_fn_toggles()
        # once the extra effects have been seen on this keyboard, keep listing them (a reconnect or a
        # failed flash read mid-way shouldn't make them vanish); the marker file remembers them too
        has_effects = ((getattr(self, "_has_effects", False) if self.kb else False) or v == "switch"
                       or getattr(self, "_effects_seen", False) or os.path.exists(self.EFFECTS_MARKER))
        if has_effects and self.kb and v.startswith("switch"):
            self._effects_seen = True
            with open(self.EFFECTS_MARKER, "w") as fh:
                fh.write("effects\n")
        if v == "stock" and os.path.exists(self.EFFECTS_MARKER):
            os.remove(self.EFFECTS_MARKER)
            self._effects_seen = has_effects = False
        self.effect_combo.config(values=k580.effect_names(has_effects))
        led = self.led or self.get_led()
        auto = self.kb and getattr(self, "_auto_installed", False)
        self.fw_state.config(text={"switch": "Custom firmware" + (" (Auto Wired Mode)"
                                                                  if auto else ""),
                                   "switch-fine": "Custom (test version with 20 brightness steps)",
                                   "switch-nofn": "Custom (older version)",
                                   "switch-old": "Custom (older version, no volume-key option)",
                                   "always": "Custom (older 'always on' version)",
                                   "toggle": "Custom (older toggle version)",
                                   "stock": "Stock Redragon firmware",
                                   "unknown": "(connect the cable to check)"}[v])
        switch, wheel = v.startswith("switch"), v in ("switch", "switch-fine", "switch-nofn")
        self.media_on.set(led[self.MEDIA_BYTE] == 0 if switch else v == "always")
        self.media_toggle.config(state="normal" if switch else "disabled")
        self.wheel_on.set(wheel and led[self.WHEEL_BYTE] != 0)
        self.wheel_toggle.config(state="normal" if wheel else "disabled")
        self.media_note.config(text={
            "switch": "On the keyboard: Fn + Play/Pause and Fn + the volume/brightness key.",
            "switch-nofn": "When off, media keys flash when pressed and the volume/brightness key\n"
                           "lights only in brightness mode (like stock).",
            "switch-fine": "When off, media keys flash when pressed and the volume/brightness key\n"
                               "lights only in brightness mode (like stock).",
            "switch-old": "Update the custom firmware (Firmware page) for the volume-key option.",
            "always": "Your current custom firmware keeps the media lights on permanently.\n"
                      "Update it from the Firmware page to get these options.",
            "toggle": "Update the custom firmware from the Firmware page to use these.",
            "stock": "These need the custom firmware (see the Firmware page).",
            "unknown": "Connect the cable once so the app can check your firmware."}[v])
        # stock -> Install; any custom -> Reinstall (latest version, with the options ticked now) or Uninstall.
        # Reinstalling patches the saved stock copy, so it needs backups\my-original-firmware.hex.
        custom = v not in ("stock", "unknown")
        can_reinstall = custom and os.path.exists(self.OWN_ORIGINAL)
        self.fw_install.config(text="Reinstall custom firmware" if custom else "Install custom firmware",
                               state="normal" if v == "stock" or can_reinstall else "disabled")
        self.fw_auto.config(state="normal" if v == "stock" or can_reinstall else "disabled")
        if custom and self.kb and not getattr(self, "_auto_shown_for", None) is self.kb:
            self._auto_shown_for = self.kb          # start the box at what's installed
            self.auto_wired.set(bool(getattr(self, "_auto_installed", False)))
        self.fw_uninstall.config(state="normal" if can_reinstall else "disabled")
        self.fw_hint.config(text={
            "stock": "", "switch": "",
            "unknown": "Connect the cable (wireless switch off) and click Reconnect to check.",
        }.get(v, "This is an older custom version. Click Reinstall to get the latest.")
            if v == "stock" or not custom or can_reinstall else
            "Your original firmware backup (backups\\my-original-firmware.hex) is missing,\n"
            "so Reinstall and Uninstall can't run. Copy it back into the backups folder.")

    # Fn layer (layer 1) keys for the light toggles: Play/Pause and the volume/brightness (wheel-mode) key
    FN_TOGGLES = {113: "MEDIA_TOGGLE_KEY", 77: "WHEEL_TOGGLE_KEY"}

    def ensure_fn_toggles(self):
        """Bind Fn + Play/Pause and Fn + volume/brightness key to the light toggles, unless the user
        has put something else there. Done once per connection."""
        import k580_patch
        if getattr(self, "_fn_checked", None) is self.kb:
            return
        self._fn_checked = self.kb
        layer = bytearray(self.kb.get_matrix(1))
        changed = False
        for idx, name in self.FN_TOGGLES.items():
            want = bytes.fromhex(getattr(k580_patch, name))
            have = bytes(layer[idx * 4:idx * 4 + 4])
            # empty, or the old toggle-firmware binding (07 00 00 13) on Play/Pause
            if have != want and (have == bytes(4) or (idx == 113 and have.hex() == "07000013")):
                layer[idx * 4:idx * 4 + 4] = want
                changed = True
        if changed:
            self.kb.write(k580.OP_MATRIX, bytes(layer), sub=1)

    def marker_variant(self):
        try:
            v = open(self.MARKER).read().strip()
            return v if v in ("switch", "switch-fine", "switch-nofn", "switch-old") else ("switch" if v else None)
        except OSError:
            return None

    def brightness_levels(self):
        """Brightness steps the keyboard has: 4, or 20 on the dropped fine-brightness test build."""
        import k580_patch
        v = self.firmware_variant() if self.kb else self.marker_variant()
        return k580_patch.FINE_BRIGHTNESS_LEVELS if v == "switch-fine" else 4

    @staticmethod
    def scale_brightness(led, convert):
        """Rewrite every effect's brightness level (low 5 bits of lighting byte 0x38 + 2 * hw id)."""
        for hw in range(1, 22):
            a = 0x38 + 2 * hw
            led[a] = (led[a] & 0xE0) | convert(led[a] & 0x1F)

    def set_wheel_led(self):
        led = bytearray(self.led or self.get_led())
        led[self.WHEEL_BYTE] = 1 if self.wheel_on.get() else 0
        self._write_led(led)

    def set_media_leds(self):
        led = bytearray(self.led or self.get_led())
        led[self.MEDIA_BYTE] = 0 if self.media_on.get() else 1
        self._write_led(led)

    def _write_led(self, led):
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.set_led(led)
        finally:
            self.config(cursor="")
        self.led = led
        self.refresh_media_state()

    def find_sinowisp(self):
        for p in (os.path.join(HERE, "third_party", "sinowisp", "sinowisp.exe"),
                  os.path.join(HERE, "sinowisp.exe")):
            if os.path.exists(p):
                return p
        messagebox.showinfo("K580", "Pick sinowisp.exe (the open-source SinoWealth flasher, "
                                    "github.com/karstx/sinowisp, Windows release).")
        return filedialog.askopenfilename(filetypes=[("sinowisp", "sinowisp.exe")]) or None

    def wait_for_keyboard(self):
        for _ in range(40):
            time.sleep(1)
            try:
                return k580.K580()
            except SystemExit:
                continue
        return None

    OWN_ORIGINAL = os.path.join(HERE, "backups", "my-original-firmware.hex")

    def install_firmware(self, removing):
        import k580_patch
        if not self.kb:
            messagebox.showwarning("K580", "This needs the cable (wireless switch off).")
            return
        tool = self.find_sinowisp()
        if not tool:
            return
        own_original = os.path.join(HERE, "backups", "my-original-firmware.hex")
        if removing and not os.path.exists(own_original):
            messagebox.showerror("K580", "Your original firmware backup (backups\\my-original-firmware.hex) is missing.")
            return
        first_time = not removing and not os.path.exists(own_original)
        if not messagebox.askyesno(
                "K580", ("This puts your original firmware back (about 15 seconds)" if removing else
                         "This reads your keyboard's firmware, checks it's the exact version the patch is for,\n"
                         "saves an untouched copy for undo, and installs the patched version (about 30 seconds)"
                         if first_time else
                         "This installs the latest custom firmware (about 15 seconds)")
                + ".\n\nKeep the cable plugged in until it says Done. Continue?"
                + ("" if removing else "\n\nAuto Wired Mode: "
                   + ("on" if self.auto_wired.get() else "off"))):
            return
        self.config(cursor="watch")
        self.update()
        fine_before = self.firmware_variant() == "switch-fine"
        saved = k580.backup(self.kb)
        saved["macro_area"] = self.kb.read(0x80 | k580.OP_MACRO, 2048).hex()
        os.makedirs(os.path.join(HERE, "backups"), exist_ok=True)
        with open(os.path.join(HERE, "backups", "auto-before-firmware-switch.json"), "w") as fh:
            json.dump(saved, fh, indent=1)
        self.kb.close()
        self.kb = None
        try:
            if removing:
                k580_patch.write_keyboard(tool, own_original)
            else:
                if os.path.exists(own_original) and \
                        k580_patch.state(k580_patch.read_hex(own_original)) == "stock":
                    fw = k580_patch.read_hex(own_original)      # reinstall: patch the saved stock copy
                else:
                    fresh = os.path.join(HERE, "backups", "firmware-read.hex")
                    k580_patch.read_keyboard(tool, fresh)
                    fw = k580_patch.read_hex(fresh)
                    st = k580_patch.state(fw)
                    if st != "stock":
                        raise RuntimeError("This keyboard's firmware isn't the version the patch was made for "
                                           f"({st}). Nothing was changed.")
                    os.replace(fresh, own_original)
                    self.kb = self.wait_for_keyboard()       # the read reboots the keyboard
                    if self.kb:
                        self.kb.close()
                        self.kb = None
                patched = os.path.join(HERE, "backups", "patched-firmware.hex")
                k580_patch.write_hex(k580_patch.apply(fw, auto_wired=self.auto_wired.get()), patched)
                k580_patch.write_keyboard(tool, patched)
        except RuntimeError as e:
            self.kb = self.wait_for_keyboard()
            self.config(cursor="")
            messagebox.showerror("K580", str(e))
            if self.kb:
                k580.restore(self.kb, saved)
                self.kb.write(k580.OP_MACRO, bytes.fromhex(saved["macro_area"]))
            return
        self.kb = self.wait_for_keyboard()
        self.config(cursor="")
        if not self.kb:
            messagebox.showerror("K580", "The keyboard didn't come back. Run this app's install again, or\n"
                                         "write backups\\my-original-firmware.hex with sinowisp.")
            return
        time.sleep(1)
        led = bytearray.fromhex(saved["led"])
        led[self.MEDIA_BYTE] = 0          # start with the lights on (and WASD swap off on stock)
        # brightness is 0-4, except 0-20 on the dropped fine-brightness test build
        fine_after = self.firmware_variant() == "switch-fine"
        if fine_after and not fine_before:
            self.scale_brightness(led, lambda v: min(v, 4) * 5)
        elif fine_before and not fine_after:
            self.scale_brightness(led, lambda v: min(4, (v + 2) // 5))
        saved["led"] = led.hex()
        k580.restore(self.kb, saved)
        self.kb.write(k580.OP_MACRO, bytes.fromhex(saved["macro_area"]))
        self.status.config(text="Connected by cable  ✓")
        self.load_lighting()
        messagebox.showinfo("K580", "Done. Installed now: " + self.fw_state.cget("text"))

    def solid_index(self):
        """Which of the effect's 7 colour slots the solid colour uses (the selected one, else 0)."""
        c = self.color.get()
        return k580.COLORS.index(c) if c in k580.COLORS[:7] else 0

    def color_swatches(self, parent, size=26):
        """Two choices bound to self.color: the effect's solid colour, or rainbow (multi).
        Greyed out when `enabled` is False."""
        c = tk.Canvas(parent, width=260, height=size + 4, bg=k580_theme.PANEL, highlightthickness=0,
                      cursor="hand2")
        c.enabled = True
        spots = [(2, False, "Solid colour"), (132, True, "Rainbow")]   # x, is rainbow, caption

        def redraw(*_):
            c.delete("all")
            multi = self.color.get() == k580.COLORS[7]
            for x, rainbow, caption in spots:
                if rainbow:
                    for k in range(size):
                        c.create_line(x + k, 2, x + k, 2 + size, fill=k580_theme.hue_hex(k / size, 0.9, 1.0))
                else:
                    c.create_rectangle(x, 2, x + size, 2 + size, width=0,
                                       fill="#%02x%02x%02x" % self.effect_color(self.solid_index()))
                if not c.enabled:
                    c.create_rectangle(x, 2, x + size, 2 + size, fill=k580_theme.PANEL, stipple="gray75",
                                       width=0)
                on = c.enabled and rainbow == multi
                c.create_rectangle(x - 1, 1, x + size + 1, 3 + size, outline=k580_theme.FG if on else k580_theme.BORDER,
                                   width=2 if on else 1)
                c.create_text(x + size + 8, 2 + size / 2, anchor="w", text=caption,
                              fill=k580_theme.FG if on else k580_theme.MUTED, font=("Segoe UI", 9))
            c.config(cursor="hand2" if c.enabled else "")

        def click(e):
            if not c.enabled:
                return
            rainbow = e.x >= spots[1][0] - 4
            self.color.set(k580.COLORS[7] if rainbow else k580.COLORS[self.solid_index()])
            self.sync_picker()
            self.apply_lighting()

        c.redraw = redraw
        c.bind("<Button-1>", click)
        self.color.trace_add("write", redraw)
        redraw()
        return c

    def current_hw(self):
        return next((h for h, n in k580.EFFECTS.items() if n == self.effect.get()), 0)

    def effect_color(self, i, hw=None):
        """Colour i (0-6) of an effect, from the keyboard's own colour table."""
        hw = self.current_hw() if hw is None else hw
        a = hw * 21 + i * 3
        return tuple(self.palette[a:a + 3])

    def sync_picker(self):
        """Show the effect's solid colour on the wheel (without writing anything)."""
        self._syncing = True
        try:
            self.lpicker.show(self.effect_color(self.solid_index()))
        finally:
            self._syncing = False

    def pick_effect_color(self, rgb):
        """Wheel or preset on the Lighting page: this becomes the effect's solid colour."""
        hw = self.current_hw()
        if self._syncing or not self.kb or not k580.effect_options(hw)[1]:
            return
        i = self.solid_index()
        if self.color.get() != k580.COLORS[i]:          # was on rainbow: switch to the solid colour
            self.color.set(k580.COLORS[i])
            self.apply_lighting()
        a = hw * 21 + i * 3
        self.palette[a:a + 3] = bytes(rgb)
        self.color_box.redraw()
        # write once the wheel stops moving (it's a flash write on the keyboard)
        if self._palette_job:
            self.after_cancel(self._palette_job)
        self._palette_job = self.after(400, self.save_palette)

    def save_palette(self):
        self._palette_job = None
        if self.kb:
            data = bytearray(self.palette[:512])
            data[0x1FA:0x1FC] = bytes([0x5A, 0xA5])
            self.kb.write(k580.OP_RGB_TABLE, bytes(data))

    def reset_effect_colors(self):
        hw = self.current_hw()
        self.palette[hw * 21:hw * 21 + 21] = k580.DEFAULT_PALETTE
        self.color_box.redraw()
        self.sync_picker()
        self.save_palette()

    def snap_slider(self, parent, var, levels=lambda: 4, length=260, on_done=None):
        """A slider that moves freely while dragged and eases onto the nearest level on release.

        `var` holds the keyboard's own level, 0..levels(): 0-4 on stock firmware, brightness 0-20
        on the custom firmware. Drawn on a canvas rather than ttk.Scale, because recolouring a
        ttk.Scale for the RGB accent makes its handle jump.
        """
        thumb, h = 9, 18                            # half handle width, track height
        c = tk.Canvas(parent, width=length, height=h + 16, bg=k580_theme.PANEL, highlightthickness=0,
                      cursor="hand2")
        x0, x1 = thumb, length - thumb
        c.create_rectangle(0, 0, length - 1, h - 1, fill="#090a0d", outline=k580_theme.BORDER)
        fill = c.create_rectangle(1, 1, 1, h - 2, width=0)
        handle = c.create_rectangle(0, 0, 0, 0, width=0)
        grips = [c.create_line(0, 0, 0, 0, fill="#090a0d") for _ in range(3)]
        for i in range(5):
            x = x0 + i * (x1 - x0) / 4
            c.create_line(x, h + 1, x, h + 5, fill=k580_theme.MUTED)
            c.create_text(x, h + 11, text=f"{i * 25}%", fill=k580_theme.MUTED, font=("Segoe UI", 7))
        anim = {"job": None, "grab": 0.0}

        def to_x(v):
            n = levels()
            return x0 + max(0.0, min(n, v)) * (x1 - x0) / n

        def to_v(x):
            n = levels()
            return max(0.0, min(n, (x - x0) * n / (x1 - x0)))

        def draw(*_):
            try:
                x = to_x(var.get())
            except tk.TclError:
                return
            c.coords(fill, 1, 1, x, h - 1)
            c.coords(handle, x - thumb, 0, x + thumb, h)
            for i, g in enumerate(grips):
                gx = x - 3 + 3 * i
                c.coords(g, gx, 5, gx, h - 5)

        def recolour():
            if not c.winfo_exists():
                return
            phase = getattr(self, "_accent_phase", 0.5)
            on = c.enabled
            c.itemconfigure(handle, fill=k580_theme.hue_hex(phase, 0.65, 1.0) if on else k580_theme.MUTED)
            c.itemconfigure(fill, fill=k580_theme.hue_hex(phase, 0.75, 0.45) if on else k580_theme.FIELD)
            c.after(50, recolour)

        def stop_anim():
            if anim["job"]:
                c.after_cancel(anim["job"])
                anim["job"] = None

        def glide(target, then=None, frames=8):
            stop_anim()
            start = var.get()

            def step(n=1):
                t = n / frames
                var.set(start + (target - start) * (1 - (1 - t) ** 3))   # ease-out
                if n < frames:
                    anim["job"] = c.after(15, step, n + 1)
                else:
                    anim["job"] = None
                    var.set(target)
                    if then:
                        then()
            step()

        def press(e):
            if not c.enabled:
                return
            self.slider_busy = True
            stop_anim()
            hx = to_x(var.get())
            if abs(e.x - hx) <= thumb + 2:
                anim["grab"] = e.x - hx               # keep the handle under the pointer
            else:
                anim["grab"] = 0.0                    # clicked the track: jump there
                var.set(to_v(e.x))

        def motion(e):
            if c.enabled:
                var.set(to_v(e.x - anim["grab"]))

        def release(_e):
            if not c.enabled:
                return
            # the keyboard has fixed levels, so glide onto the nearest one, then apply
            def done():
                self.slider_busy = False
                (on_done or self.apply_lighting)()
            glide(round(var.get()), done)

        c.enabled = True                            # False greys it out for effects that ignore it
        c.bind("<ButtonPress-1>", press)
        c.bind("<B1-Motion>", motion)
        c.bind("<ButtonRelease-1>", release)
        var.trace_add("write", draw)
        draw()
        recolour()
        return c

    def load_lighting(self):
        led = bytearray(self.get_led())
        if len(led) < 0x80:                    # no answer (e.g. the keyboard is off behind the dongle)
            self.battery.config(text="")
            return
        self.led = led
        if self.kb:
            self.palette = bytearray(self.kb.get_rgb_table())
        self.refresh_media_state()
        self.show_lighting()
        self.load_settings()

    def show_battery(self, led):
        """Latest custom firmware copies the battery level into lighting bytes. The % is worked out
        from the raw reading with the firmware's own formula (0 % at 0x2CB, +10 % per 0x16), because
        the keyboard's smoothed % only creeps up 1 % at a time after the cable comes out."""
        import k580_patch
        v = self.firmware_variant() if self.kb else self.marker_variant()
        pct = led[k580_patch.BATTERY_BYTE]
        raw = (led[k580_patch.BATTERY_RAW] << 8) | led[k580_patch.BATTERY_RAW + 1]
        if 0x100 < raw < 0x600:                     # a real reading (the cable reports 3)
            pct = max(0, min(100, round((raw - 0x2CB) * 10 / 0x16)))
        if v != "switch":
            text = ""
        elif self.kb:                       # on the cable it charges and isn't measured
            text = "Battery: charging"
        else:
            text = f"Battery {pct}%" if pct <= 100 else "Battery: checking..."
        self.battery.config(text=text)

    # side-light modes (lighting byte 0x12), from the firmware's side-light routine at 0x43AA
    SIDE_MODES = {"Off": 0, "RGB": 1, "Rainbow cycle": 2, "White": 3, "Red": 4, "Yellow": 5, "Orange": 6,
                  "Green": 7, "Cyan": 8, "Blue": 9, "Magenta": 10, "Colour breathing": 11}
    SIDE_MODE, SIDE_BRIGHT, SIDE_SPEED = 0x12, 0x14, 0x15

    def show_side(self):
        names = {v: k for k, v in self.SIDE_MODES.items()}
        self.side_mode.set(names.get(self.led[self.SIDE_MODE], f"Mode {self.led[self.SIDE_MODE]}"))
        self.side_bright.set(min(self.led[self.SIDE_BRIGHT], 4))
        self.side_speed.set(min(self.led[self.SIDE_SPEED], 4))

    def apply_side(self):
        if not (self.kb or self.wl) or self.side_mode.get() not in self.SIDE_MODES:
            return
        led = bytearray(self.led if self.led else self.get_led())
        led[self.SIDE_MODE] = self.SIDE_MODES[self.side_mode.get()]
        led[self.SIDE_BRIGHT] = int(round(self.side_bright.get()))
        led[self.SIDE_SPEED] = int(round(self.side_speed.get()))
        self.set_led(led)
        self.led = led

    def show_lighting(self):
        self.show_battery(self.led)
        self.show_side()
        self.after_idle(self.sync_picker)
        hw = self.led[10]
        self.effect.set(k580.EFFECTS.get(hw, "OFF"))
        self.show_effect_options(hw)
        slot = effect_slot(hw)
        if slot is not None:
            b = self.led[0x3B + 2 * slot]
            self.bright.set(min(self.led[0x3A + 2 * slot] & 0x1F, self.brightness_levels()))
            self.speed.set(b >> 4)
            self.color.set(k580.COLORS[b & 7])

    def poll_lighting(self):
        """Pick up changes made on the keyboard itself (Fn effect/brightness/speed/color keys)
        while the Lighting page is showing."""
        self.after(1000, self.poll_lighting)
        self._poll_n = getattr(self, "_poll_n", 0) + 1
        if self._poll_n % 2 == 0:              # fallback; device and dongle events trigger it sooner
            self.watch_connection()
        # a read finished in the background since the last tick: use it
        led, self._polled = getattr(self, "_polled", None), None
        if led is not None and self.led and len(led) >= 0x80 and led[0x7E:0x80] == b"\x5a\xa5":
            self.show_battery(led)
            # only the settings matter here, not the battery bytes that change every reading
            changed = led[:0x1C] != self.led[:0x1C] or led[0x1F:] != self.led[0x1F:]
            if changed and not self.slider_busy:
                self.led = led
                self.show_lighting()
                self.refresh_media_state()      # Fn + Play/Pause etc. flip the key-light switches
        on_lighting = self.state() == "normal" and self.nb.tab(self.nb.select(), "text") == "Lighting"
        if (self.kb or self.wl) and (on_lighting or self._poll_n % 10 == 0):
            self.read_led_in_background()

    def read_led_in_background(self):
        """Read the lighting block on a worker thread, so a slow dongle never freezes the window."""
        if getattr(self, "_reading", False):
            return
        self._reading = True

        def work():
            try:
                self._polled = bytearray(self.get_led())
            except Exception:
                pass
            finally:
                self._reading = False
        threading.Thread(target=work, daemon=True).start()

    def watch_connection(self):
        """Every few seconds: notice the cable being unplugged or plugged in, and switch between
        cable and dongle by itself (status and battery follow)."""
        if self.kb:
            try:
                self.kb.password()                  # still there? (a 6-byte read)
            except Exception:
                self.connect()                      # unplugged: falls back to the dongle
            return
        try:
            probe = k580.K580()                     # cable plugged in while on the dongle (or nothing)?
        except (SystemExit, Exception):
            probe = None
        if probe:
            probe.close()
            self.connect()
        elif self.wl:
            try:
                data, _ = self.wl.query(0x07)
                alive = data[:1] == bytes([1])          # the dongle answers even when the keyboard is off
            except Exception:
                alive = False
            if not alive:
                self.connect()
        else:
            self.connect()                          # nothing connected yet: keep looking

    def show_effect_options(self, hw):
        """Grey out speed/color for effects that ignore them (like the stock app hides them)."""
        speed, color = k580.effect_options(hw)
        self.speed_slider.enabled = speed
        self.speed_slider.config(cursor="hand2" if speed else "")
        self.color_box.enabled = color
        self.color_box.redraw()
        self.layout_color_cell(hw == 21)
        name = k580.EFFECTS.get(hw, "OFF")
        note = "Changes apply instantly."
        if hw in (3, 6, 15, 16, 17, 18):
            note += f" {name} uses its own rainbow colors."
        elif hw == 1:
            note += " Fixed on doesn't move, so it has no speed."
        import k580_preview
        if hw in k580_preview.REACTIVE:
            note += f" {name}: {k580_preview.REACTIVE[hw]} (the preview fakes the key presses)."
        self.effect_note.config(text=note)
        if hw == 21:
            self.sd_note.pack(anchor="w", pady=(4, 0))
        else:
            self.sd_note.pack_forget()

    def apply_lighting(self, new_effect=False, keep_sliders=False):
        if not (self.kb or self.wl):
            self.need_kb()
            return
        name = self.effect.get()
        hw = next((h for h, n in k580.EFFECTS.items() if n == name), 0)
        led = bytearray(self.led if self.led else self.get_led())
        led[10] = hw
        led[9] = 1 if hw == 21 else 0
        self.show_effect_options(hw)
        slot = effect_slot(hw)
        # switching effect keeps that effect's own saved brightness/speed/color
        if slot is not None and not new_effect:
            led[0x3A + 2 * slot] = (led[0x3A + 2 * slot] & 0xE0) | int(round(self.bright.get()))
            led[0x3B + 2 * slot] = (int(round(self.speed.get())) << 4) | k580.COLORS.index(self.color.get() or "red")
        if slot is not None and not k580.effect_options(hw)[1] and hw != 21:
            # rainbow-only effects draw in one colour if a single colour is saved: keep them on multi
            led[0x3B + 2 * slot] = (led[0x3B + 2 * slot] & 0xF0) | 7
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.set_led(led)
        finally:
            self.config(cursor="")
        self.led = led
        if slot is not None and not keep_sliders:     # after a drag, leave the handles where they were dropped
            b = led[0x3B + 2 * slot]
            self.bright.set(min(led[0x3A + 2 * slot] & 0x1F, self.brightness_levels()))
            self.speed.set(b >> 4)
            self.color.set(k580.COLORS[b & 7])

    # ---------------- keys
    def page(self, nb, title, padding):
        """A notebook page that scrolls vertically when the window is shorter than its content."""
        outer = ttk.Frame(nb)
        nb.add(outer, text=title)
        canvas = tk.Canvas(outer, bg=k580_theme.PANEL, highlightthickness=0)
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=padding)
        win = canvas.create_window(0, 0, window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        if not hasattr(self, "pages"):
            self.pages = []
        self.pages.append((outer, canvas, inner))

        def fit(_e=None):
            canvas.configure(scrollregion=(0, 0, inner.winfo_reqwidth(), inner.winfo_reqheight()))
            canvas.itemconfigure(win, width=max(canvas.winfo_width(), inner.winfo_reqwidth()))
            if inner.winfo_reqheight() > canvas.winfo_height():   # scrollbar only when needed
                if not bar.winfo_ismapped():
                    bar.pack(side="right", fill="y")
            elif bar.winfo_ismapped():
                bar.pack_forget()
                canvas.yview_moveto(0)
        inner.bind("<Configure>", fit)
        canvas.bind("<Configure>", fit)

        def wheel(e):
            if bar.winfo_ismapped():
                canvas.yview_scroll(int(-e.delta / 120), "units")
        outer.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", wheel))
        outer.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))
        return inner

    KB_PAD = 10                          # Lighting, Keys and Macros share this keyboard placement

    def keyboard_page(self, nb, title, on_click, hint):
        """A page with the clickable keyboard at the top and a hint line under it, laid out the same
        on every page that has one."""
        f = self.page(nb, title, self.KB_PAD)
        kb = KeyboardView(f, on_click=on_click)
        kb.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        info = ttk.Label(f, text=hint, style="Muted.TLabel")
        info.grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 6))
        return f, kb, info

    def build_keys(self, nb):
        f, self.kkb, self.key_info = self.keyboard_page(
            nb, "Keys", self.key_clicked,
            "Each key shows what it does. Changed keys are outlined. Click a key to change it.")
        self.key_sel = None
        self.capturing = False
        self.layer = tk.StringVar(value="Normal")
        self.category = tk.StringVar(value="Key")
        self.action = tk.StringVar()
        f.columnconfigure(1, weight=1)

        top = ttk.Frame(f)
        top.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(4, 8))
        ttk.Label(top, text="Layer").pack(side="left", padx=(0, 10))
        for value, text in (("Normal", "Normal"), ("Fn", "While holding Fn")):
            ttk.Radiobutton(top, text=text, value=value, variable=self.layer, style="Toolbutton",
                            command=self.show_key).pack(side="left", padx=(0, 6))
        ttk.Button(top, text="Reset all keys on this layer", command=self.reset_layer).pack(side="right")

        ttk.Separator(f).grid(row=3, column=0, columnspan=4, sticky="ew", pady=6)
        self.sel_title = ttk.Label(f, text="No key selected", font=k580_theme.FONT_BOLD)
        self.sel_title.grid(row=4, column=0, columnspan=4, sticky="w")
        self.current = ttk.Label(f, text="Click a key on the keyboard above.", style="Muted.TLabel")
        self.current.grid(row=5, column=0, columnspan=4, sticky="w", pady=(2, 10))

        acts = ttk.Frame(f)
        acts.grid(row=6, column=0, columnspan=4, sticky="w")
        self.capture_btn = ttk.Button(acts, text="Press the new key or shortcut…", style="Accent.TButton",
                                      command=self.toggle_capture)
        self.capture_btn.pack(side="left", padx=(0, 8))
        ttk.Button(acts, text="Disable key", command=lambda: self._set_entry(bytes(4))) \
            .pack(side="left", padx=(0, 8))
        ttk.Button(acts, text="Reset key", command=self.reset_key).pack(side="left")
        self.capture_note = ttk.Label(f, text="", style="Muted.TLabel")
        self.capture_note.grid(row=7, column=0, columnspan=4, sticky="w", pady=(4, 0))

        ttk.Label(f, text="Or choose from a list (media keys, mouse buttons, commands, lighting…)") \
            .grid(row=8, column=0, columnspan=4, sticky="w", pady=(14, 6))
        row = ttk.Frame(f)
        row.grid(row=9, column=0, columnspan=4, sticky="w")
        cc = ttk.Combobox(row, textvariable=self.category, values=CATEGORIES, state="readonly", width=12)
        cc.pack(side="left")
        cc.bind("<<ComboboxSelected>>", lambda e: self.fill_actions())
        self.action_box = ttk.Combobox(row, textvariable=self.action, state="readonly", width=28)
        self.action_box.pack(side="left", padx=(8, 8))
        ttk.Button(row, text="Apply", command=self.apply_key, style="Accent.TButton").pack(side="left")
        ttk.Label(f, text="Macros are assigned on the Macros page.", style="Muted.TLabel") \
            .grid(row=10, column=0, columnspan=4, sticky="w", pady=(14, 0))
        self.fill_actions()
        nb.bind("<<NotebookTabChanged>>",
                lambda e: self.show_key() if self.kb and nb.tab(nb.select(), "text") == "Keys" else None,
                add="+")

    def key_clicked(self, idx):
        """Keys page: one key at a time."""
        if idx is None:
            return
        self.stop_capture()
        self.key_sel = idx
        self.kkb.selected = {idx}
        self.kkb.redraw()
        self.show_key()

    # "press the key you want": the next key (plus any held Ctrl/Shift/Alt/Win) becomes the mapping
    def toggle_capture(self):
        if self.capturing:
            self.stop_capture()
            return
        if self._key_idx() is None:
            self.capture_note.config(text="Click a key on the keyboard above first.")
            return
        self.capturing = True
        self.capture_mods = set()
        self.capture_btn.config(text="Cancel")
        self.capture_note.config(text="Press the key or shortcut now (on this keyboard or any other)…")
        self.focus_force()
        self.bind_all("<KeyPress>", self.on_capture_key)
        self.bind_all("<KeyRelease>", self.on_capture_release)

    def stop_capture(self, note=""):
        if not getattr(self, "capturing", False):
            return
        self.capturing = False
        self.unbind_all("<KeyPress>")
        self.unbind_all("<KeyRelease>")
        self.capture_btn.config(text="Press the new key or shortcut…")
        self.capture_note.config(text=note)

    def on_capture_key(self, e):
        if e.keysym in MOD_KEYSYMS:
            self.capture_mods.add(MOD_KEYSYMS[e.keysym])
            return "break"
        code = VK_TO_HID.get(e.keycode)
        if code is None:
            self.capture_note.config(text=f"That key ({e.keysym}) can't be assigned here. Try another, "
                                          "or pick it from the list.")
            return "break"
        bits = 0
        for m in self.capture_mods:
            bits |= MODIFIERS[m]
        self.stop_capture()
        self._set_entry(bytes([0, bits, 0, code]))
        return "break"

    def on_capture_release(self, e):
        # a modifier pressed and released on its own: map to that modifier key
        if e.keysym in MOD_KEYSYMS and self.capture_mods == {MOD_KEYSYMS[e.keysym]}:
            self.stop_capture()
            self._set_entry(bytes([0, MODIFIERS[MOD_KEYSYMS[e.keysym]], 0, 0]))
        return "break"

    def fill_actions(self):
        names = [n for n in ACTIONS if category_of(n) == self.category.get()]
        self.action_box.config(values=names)
        self.action.set(names[0] if names else "")

    def _layer_idx(self):
        return 0 if self.layer.get() == "Normal" else 1

    def first_run_layer(self):
        path = os.path.join(HERE, "backups", "first-run.json")
        try:
            with open(path) as fh:
                return bytes.fromhex(json.load(fh)["matrix"][self._layer_idx()])
        except (OSError, KeyError, ValueError, IndexError):
            return None

    def reset_layer(self):
        first = self.first_run_layer()
        if not self.need_kb() or first is None:
            return
        name = "normal" if self._layer_idx() == 0 else "Fn"
        if not messagebox.askyesno("K580", f"Put every key on the {name} layer back to how it was when this "
                                           "app first saw the keyboard?"):
            return
        self.kb.write(k580.OP_MATRIX, first, sub=self._layer_idx())
        time.sleep(0.2)
        self.show_key()

    def _key_idx(self):
        return self.key_sel

    def show_key(self):
        if not self.need_kb():
            return
        m = self.kb.get_matrix(self._layer_idx())
        self.mark_changed_keys(m)
        # every key cap shows what it does on this layer
        first = self.first_run_layer() or m
        changed = {i for i in self.kkb.rects if m[i * 4:i * 4 + 4] != first[i * 4:i * 4 + 4]}
        self.kkb.set_labels({i: short_label(m[i * 4:i * 4 + 4]) for i in self.kkb.rects}, highlight=changed)
        i = self._key_idx()
        if i is None:
            return
        name = k580.KEY_NAMES.get(i, "#%d" % i)
        name = KeyboardView.SHORT.get(name, name)
        layer = "" if self._layer_idx() == 0 else "Fn + "
        self.sel_title.config(text=f"{layer}{name}")
        self.current.config(text="Does: " + describe(m[i * 4:i * 4 + 4]))

    def mark_changed_keys(self, m):
        """Outline keys that differ from how the app first found the keyboard."""
        first = self.first_run_layer()
        if first is None:
            return
        self.kkb.set_marked({i for i in self.kkb.rects if m[i * 4:i * 4 + 4] != first[i * 4:i * 4 + 4]})

    def _set_entry(self, entry):
        if not self.need_kb() or self._key_idx() is None:
            return
        layer, i = self._layer_idx(), self._key_idx()
        m = bytearray(self.kb.get_matrix(layer))
        m[i * 4:i * 4 + 4] = entry
        self.kb.write(k580.OP_MATRIX, bytes(m), sub=layer)
        time.sleep(0.2)
        self.show_key()

    def apply_key(self):
        if self.action.get() in ACTIONS:
            self._set_entry(ACTIONS[self.action.get()])

    def reset_key(self):
        """Put the key back to what it was the first time this app saw the keyboard."""
        path = os.path.join(HERE, "backups", "first-run.json")
        if self._key_idx() is None or not os.path.exists(path):
            return
        with open(path) as fh:
            first = json.load(fh)
        m = bytes.fromhex(first["matrix"][self._layer_idx()])
        i = self._key_idx()
        self._set_entry(m[i * 4:i * 4 + 4])

    # ---------------- macros
    REPEAT_MODES = {"Play once": (k580.MACRO_TIMES, 1), "Repeat N times": (k580.MACRO_TIMES, None),
                    "Repeat while the key is held": (k580.MACRO_WHILE_HELD, 1),
                    "Repeat until any key is pressed": (k580.MACRO_UNTIL_KEY, 1)}

    def build_macros(self, nb):
        # keyboard picture: click keys to choose where macros go
        f, self.mkb, self.mkey_info = self.keyboard_page(
            nb, "Macros", lambda i: self.refresh_macro_keys(), "Click keys on the keyboard to select them.")
        self.macros = []                 # [(name, [4-byte events])] as stored on the keyboard
        self.recorded = []
        self.recording = False
        self.mname = tk.StringVar()
        self.mtext = tk.StringVar()
        self.mmode = tk.StringVar(value="Play once")
        self.mcount = tk.IntVar(value=2)


        # left: saved macros
        left = ttk.Frame(f)
        left.grid(row=2, column=0, sticky="nsw", padx=(0, 12), pady=10)
        ttk.Label(left, text="Saved macros").pack(anchor="w")
        self.mlist = tk.Listbox(left, height=7, width=22, activestyle="none", exportselection=False)
        k580_theme.style_listbox(self.mlist)
        self.mlist.pack(anchor="w", pady=8)
        self.mlist.bind("<<ListboxSelect>>", lambda e: self.show_macro())
        ttk.Button(left, text="Delete macro", command=self.delete_macro).pack(anchor="w")

        # right: assign + new macro
        right = ttk.Frame(f)
        right.grid(row=2, column=1, sticky="nsew", pady=10)
        ttk.Label(right, text="Playback").grid(row=0, column=0, sticky="w")
        pf = ttk.Frame(right)
        pf.grid(row=0, column=1, sticky="w")
        ttk.Combobox(pf, textvariable=self.mmode, values=list(self.REPEAT_MODES), state="readonly",
                     width=26).pack(side="left")
        ttk.Spinbox(pf, from_=2, to=255, textvariable=self.mcount, width=4).pack(side="left", padx=6)
        bf = ttk.Frame(right)
        bf.grid(row=1, column=0, columnspan=2, sticky="w", pady=10)
        ttk.Button(bf, text="Assign macro to selected keys", command=self.assign_macro,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(bf, text="Clear selected keys", command=self.unassign_macro).pack(side="left", padx=6)

        ttk.Separator(right).grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(right, text="New macro").grid(row=3, column=0, sticky="w")
        nf = ttk.Frame(right)
        nf.grid(row=3, column=1, sticky="w")
        ttk.Entry(nf, textvariable=self.mname, width=16).pack(side="left")
        self.rec_btn = ttk.Button(nf, text="● Record", command=self.toggle_record)
        self.rec_btn.pack(side="left", padx=6)
        ttk.Button(nf, text="Clear", command=self.clear_recording).pack(side="left")
        self.rec_view = tk.Text(right, height=3, width=44, state="disabled", wrap="word")
        k580_theme.style_text(self.rec_view)
        self.rec_view.grid(row=4, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Label(right, text="...or text").grid(row=5, column=0, sticky="w")
        tf = ttk.Frame(right)
        tf.grid(row=5, column=1, sticky="w")
        ttk.Entry(tf, textvariable=self.mtext, width=22).pack(side="left")
        ttk.Button(tf, text="Save macro", command=self.save_macro, style="Accent.TButton") \
            .pack(side="left", padx=6)
        ttk.Label(f, text="Outlined keys have a macro. On a G key, Assign saves the macro as its recording.",
                  style="Muted.TLabel").grid(row=3, column=0, columnspan=2, sticky="w")


    def load_macros(self):
        if not self.kb:
            return
        area = self.kb.read(0x80 | k580.OP_MACRO, G_SLOTS_AT + G_SLOT_COUNT * G_SLOT)   # app macros, G slots
        self.macros = [(n, [b[i:i + 4] for i in range(0, len(b), 4)]) for n, b in parse_macros(area[:1024])]
        # G1-G5 recordings made on the keyboard itself: shown when a G key is clicked
        self.g_recordings = {}
        for idx in self.G_KEYS:
            at = G_SLOTS_AT + self.g_slot(idx) * G_SLOT
            keys = parse_g_slot(area[at:at + G_SLOT])
            if keys is not None:
                self.g_recordings[idx] = "  ".join(keys) or "(no keys)"
        self.mlist.delete(0, "end")
        for i, (n, ev) in enumerate(self.macros):
            self.mlist.insert("end", f"{i + 1}. {n}  ({len(ev)} steps)")
        self.refresh_macro_keys()

    def _bindings(self):
        """matrix index -> macro index, for layer 0."""
        m = self.kb.get_matrix(0)
        return {i: m[i * 4 + 3] for i in range(k580.MATRIX_KEYS) if m[i * 4] == 0x03}

    G_KEYS = (6, 23, 29, 41, 47)        # G1-G5 matrix indexes, in recording-slot order

    def g_slot(self, idx):
        """Recording slot of a G key: 5 per macro bank (lighting byte 0x1B, 1-4)."""
        bank = (self.led[0x1B] if self.led and 1 <= self.led[0x1B] <= 4 else 1)
        return (bank - 1) * 5 + self.G_KEYS.index(idx)

    def write_g_slots(self, slots):
        """{slot: 128-byte slot data} -> keyboard (rewrites the macro area through the G slots)."""
        area = bytearray(self.kb.read(0x80 | k580.OP_MACRO, G_SLOTS_AT + G_SLOT_COUNT * G_SLOT))
        for n, data in slots.items():
            area[G_SLOTS_AT + n * G_SLOT:G_SLOTS_AT + (n + 1) * G_SLOT] = data
        self.kb.write(k580.OP_MACRO, bytes(area))
        time.sleep(0.3)

    def refresh_macro_keys(self):
        if not self.kb:
            return
        binds = self._bindings()
        recorded = getattr(self, "g_recordings", {})
        self.mkb.set_marked(set(binds) | set(recorded))
        sel = sorted(self.mkb.selected)
        if not sel:
            self.mkey_info.config(text="Click keys on the keyboard to select them.")
            return
        parts = []
        for i in sel:
            name = k580.KEY_NAMES.get(i, f"#{i}")
            j = binds.get(i)
            if i in recorded:
                parts.append(f"{name}: types {recorded[i]}")
            elif i in self.G_KEYS:
                parts.append(f"{name}: no recording")
            else:
                parts.append(f"{name} → {self.macros[j][0]}" if j is not None and j < len(self.macros) else name)
        self.mkey_info.config(text="Selected: " + ", ".join(parts))

    def show_macro(self):
        pass                                   # selection is read when assigning

    def _write_macros(self):
        area = bytearray(self.kb.read(0x80 | k580.OP_MACRO, G_SLOTS_AT + G_SLOT_COUNT * G_SLOT))
        area[:1024] = k580.build_macro_buffer(self.macros)
        self.kb.write(k580.OP_MACRO, bytes(area))
        time.sleep(0.3)

    def save_macro(self):
        if not self.need_kb():
            return
        if self.recording:
            self.toggle_record()
        try:
            if self.recorded:
                events = [k580.macro_event(c, r, d) for c, r, d in self.recorded]
            elif self.mtext.get():
                events = text_to_events(self.mtext.get())
            else:
                messagebox.showinfo("K580", "Record some keys or enter text first.")
                return
        except ValueError as e:
            messagebox.showerror("K580", str(e))
            return
        name = (self.mname.get() or self.mtext.get() or f"Macro {len(self.macros) + 1}")[:15]
        self.macros.append((name, events))
        try:
            self._write_macros()
        except ValueError as e:
            self.macros.pop()
            messagebox.showerror("K580", str(e))
            return
        self.clear_recording()
        self.mname.set("")
        self.mtext.set("")
        self.load_macros()
        self.mlist.selection_clear(0, "end")
        self.mlist.selection_set("end")

    def assign_macro(self):
        if not self.need_kb():
            return
        pick = self.mlist.curselection()
        if not pick or not self.mkb.selected:
            messagebox.showinfo("K580", "Pick a saved macro and click one or more keys first.")
            return
        g_keys = [i for i in self.mkb.selected if i in self.G_KEYS]
        others = [i for i in self.mkb.selected if i not in self.G_KEYS]
        if g_keys:                      # G keys keep their G function: the macro becomes their recording
            try:
                slot = build_g_slot(self.macros[pick[0]][1])
            except ValueError as e:
                messagebox.showerror("K580", str(e))
                return
            self.write_g_slots({self.g_slot(i): slot for i in g_keys})
        if others:
            mode, count = self.REPEAT_MODES[self.mmode.get()]
            entry = k580.macro_key(pick[0], count or max(1, self.mcount.get()), mode)
            m = bytearray(self.kb.get_matrix(0))
            for i in others:
                m[i * 4:i * 4 + 4] = entry
            self.kb.write(k580.OP_MATRIX, bytes(m), sub=0)
            time.sleep(0.2)
        self.load_macros()

    def unassign_macro(self):
        """Give the selected keys back their original function (from the first-run snapshot)."""
        if not self.need_kb() or not self.mkb.selected:
            return
        g_keys = [i for i in self.mkb.selected if i in self.G_KEYS]
        if g_keys:                      # G keys: erase their recording
            self.write_g_slots({self.g_slot(i): bytes(G_SLOT) for i in g_keys})
            if len(g_keys) == len(self.mkb.selected):
                self.load_macros()
                return
        path = os.path.join(HERE, "backups", "first-run.json")
        orig = bytes.fromhex(json.load(open(path))["matrix"][0]) if os.path.exists(path) else None
        m = bytearray(self.kb.get_matrix(0))
        for i in self.mkb.selected:
            if i not in self.G_KEYS:
                m[i * 4:i * 4 + 4] = orig[i * 4:i * 4 + 4] if orig else bytes(4)
        self.kb.write(k580.OP_MATRIX, bytes(m), sub=0)
        time.sleep(0.2)
        self.load_macros()

    def delete_macro(self):
        if not self.need_kb():
            return
        pick = self.mlist.curselection()
        if not pick:
            return
        k = pick[0]
        if not messagebox.askyesno("K580", f"Delete macro '{self.macros[k][0]}'? Keys using it are cleared."):
            return
        del self.macros[k]
        self._write_macros()
        # keys bound to later macros shift down by one; keys bound to this one are cleared
        for layer in range(k580.LAYERS):
            m = bytearray(self.kb.get_matrix(layer))
            changed = False
            for i in range(128):
                if m[i * 4] == 0x03:
                    if m[i * 4 + 3] == k:
                        m[i * 4:i * 4 + 4] = bytes(4)
                        changed = True
                    elif m[i * 4 + 3] > k:
                        m[i * 4 + 3] -= 1
                        changed = True
            if changed:
                self.kb.write(k580.OP_MATRIX, bytes(m), sub=layer)
                time.sleep(0.1)
        self.load_macros()

    def toggle_record(self):
        self.recording = not self.recording
        self.rec_btn.config(text="■ Stop" if self.recording else "● Record")
        if self.recording:
            self.last_t = None
            self.bind_all("<KeyPress>", lambda e: self.on_key(e, False))
            self.bind_all("<KeyRelease>", lambda e: self.on_key(e, True))
            self.rec_view.focus_set()
        else:
            self.unbind_all("<KeyPress>")
            self.unbind_all("<KeyRelease>")

    def on_key(self, e, release):
        code = TK_TO_HID.get(e.keysym.lower())
        if code is None:
            return "break"
        if not release and any(c == code and not r for c, r, _ in self.recorded[-1:]):
            return "break"                       # ignore key auto-repeat
        now = time.time()
        delay = 0 if self.last_t is None else int((now - self.last_t) * 1000)
        self.last_t = now
        self.recorded.append((code, release, delay))
        self.show_recording()
        return "break"

    def clear_recording(self):
        self.recorded = []
        self.show_recording()

    def show_recording(self):
        names = {v: k for k, v in TK_TO_HID.items()}
        text = "  ".join(f"{'up' if r else 'dn'}:{names.get(c, hex(c))}({d}ms)" for c, r, d in self.recorded)
        self.rec_view.config(state="normal")
        self.rec_view.delete("1.0", "end")
        self.rec_view.insert("end", text)
        self.rec_view.config(state="disabled")

    # ---------------- custom per-key colors
    def apply_color(self, rgb):
        if not self.ckb.selected:
            return
        for idx in self.ckb.selected:
            self.key_colors[idx] = rgb
        # save once the wheel stops moving (it's a flash write on the keyboard)
        if self._keys_job:
            self.after_cancel(self._keys_job)
        self._keys_job = self.after(500, self.save_colors)

    def load_colors(self):
        if not self.kb:
            return
        planes = self.kb.get_color_group(0)
        n = k580.MATRIX_KEYS
        for idx in self.ckb.rects:
            self.key_colors[idx] = (planes[idx], planes[n + idx], planes[2 * n + idx])

    def save_colors(self):
        """Send the Self-define key colours to the keyboard (and make sure Self-define is on)."""
        self._keys_job = None
        if not self.kb:
            return
        n = k580.MATRIX_KEYS
        planes = bytearray(n * 3)
        for idx, (r, g, b) in self.key_colors.items():
            planes[idx], planes[n + idx], planes[2 * n + idx] = r, g, b
        self.kb.write(k580.OP_COLOR_GROUP, bytes(planes), sub=0)
        time.sleep(0.2)
        led = bytearray(self.get_led())
        if (led[10], led[9]) != (21, 1):
            led[10], led[9] = 21, 1                # Self-define effect
            self.set_led(led)
        self.led = led

    # ---------------- settings page
    SLEEP_OPTIONS = {"Keyboard default": 0, "1 minute": 2, "3 minutes": 6, "5 minutes": 10,
                     "10 minutes": 20, "30 minutes": 60, "1 hour": 120}
    DEBOUNCE_BYTE = 0x03       # lighting block byte the firmware copies into each key's debounce counter
    SLEEP_BYTE = 0x18          # lighting block byte: sleep after value x 30 s idle (0 = firmware default)
    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def build_settings(self, nb):
        f = self.page(nb, "Settings", 14)
        f.columnconfigure(1, weight=1)
        row = 0

        def section(title):
            nonlocal row
            ttk.Label(f, text=title, font=k580_theme.FONT_BOLD).grid(row=row, column=0, columnspan=2,
                                                                     sticky="w", pady=(10 if row else 0, 2))
            row += 1

        def line(label, widget, note=None):
            nonlocal row
            ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 16))
            widget.grid(row=row, column=1, sticky="w", pady=6)
            row += 1
            if note:
                ttk.Label(f, text=note, style="Muted.TLabel").grid(row=row, column=0, columnspan=2,
                                                                   sticky="w", pady=(0, 8))
                row += 1

        section("Device")
        self.info = ttk.Label(f, text="-", justify="left")
        self.info.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        ttk.Label(f, text="Battery: the keyboard shows it on the number keys. Press Fn + Right Shift while\n"
                          "it's in wireless mode (it doesn't report it to the PC).", style="Muted.TLabel") \
            .grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 0))
        row += 1

        section("Keyboard")
        self.debounce = tk.IntVar(value=1)
        db = ttk.Spinbox(f, from_=1, to=4, textvariable=self.debounce, width=4, state="readonly",
                         command=self.set_debounce)
        line("Key debounce", db,
             "Raise this only if a key sometimes types twice from one press. Higher = more filtering,\n"
             "but very slightly slower keys. 1 is the normal setting.")
        self.sleep = tk.StringVar(value="Keyboard default")
        sc = ttk.Combobox(f, textvariable=self.sleep, values=list(self.SLEEP_OPTIONS), state="readonly", width=18)
        sc.bind("<<ComboboxSelected>>", lambda e: self.set_sleep())
        line("Sleep after", sc,
             "In wireless mode the keyboard turns itself off after this long without a key press,\n"
             "to save battery. Any key wakes it up.")

        section("App")
        self.autostart = tk.BooleanVar(value=self._autostart_enabled())
        line("Start with Windows", ttk.Checkbutton(f, variable=self.autostart, command=self.set_autostart),
             "Starts the app in the system tray when you sign in to Windows.")
        self.close_to_tray = tk.BooleanVar(value=load_prefs().get("close_to_tray", True))
        line("Keep running in the tray", ttk.Checkbutton(f, variable=self.close_to_tray,
                                                         command=self.set_close_to_tray),
             "Closing the window (X) hides it in the system tray instead of quitting.\n"
             "Click the tray icon to open it again; right-click it to quit.")
        line("Updates", ttk.Button(f, text="Check for updates", command=self.check_updates),
             f"You have version {APP_VERSION}. Checks the project's GitHub page for a newer one.")

        section("Backup and reset")
        bk = ttk.Frame(f)
        ttk.Button(bk, text="Save backup…", command=self.save_backup).pack(side="left", padx=(0, 8))
        ttk.Button(bk, text="Restore backup…", command=self.load_backup).pack(side="left")
        line("Backup", bk, "A backup holds lighting, all 4 key layers and macros (including G-keys).")
        line("Factory reset", ttk.Button(f, text="Reset keyboard to factory settings", command=self.factory_reset),
             "Puts lighting, key assignments and macros back to how they came from the factory.\n"
             "Your custom firmware (if installed) stays. Needs the cable.")

    def load_settings(self):
        conn = "cable" if self.kb else ("2.4G dongle" if self.wl else "not connected")
        fw = f"0x{self.kb.firmware_version():04X}" if self.kb else "(connect the cable to read)"
        self.info.config(text=f"Model: Redragon K580 VATA PRO\nConnection: {conn}\n"
                              f"Firmware version: {fw}\nApp version: {APP_VERSION}")
        if self.led:
            self.debounce.set(max(1, min(4, self.led[self.DEBOUNCE_BYTE] or 1)))
            v = self.led[self.SLEEP_BYTE]
            self.sleep.set(next((k for k, n in self.SLEEP_OPTIONS.items() if n == v), f"{v * 30} seconds"))

    def _set_led_byte(self, index, value):
        if not (self.kb or self.wl):
            self.need_kb()
            return
        led = bytearray(self.led or self.get_led())
        led[index] = value
        self._write_led(led)

    def set_debounce(self):
        self._set_led_byte(self.DEBOUNCE_BYTE, int(self.debounce.get()))

    def set_sleep(self):
        self._set_led_byte(self.SLEEP_BYTE, self.SLEEP_OPTIONS[self.sleep.get()])

    def set_close_to_tray(self):
        self.prefs["close_to_tray"] = bool(self.close_to_tray.get())
        save_prefs(self.prefs)

    def _autostart_enabled(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                winreg.QueryValueEx(k, "K580 Control")
                return True
        except OSError:
            return False

    def set_autostart(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if self.autostart.get():
                pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                winreg.SetValueEx(k, "K580 Control", 0, winreg.REG_SZ,
                                  f'"{pyw}" "{os.path.abspath(__file__)}" --tray')
            else:
                try:
                    winreg.DeleteValue(k, "K580 Control")
                except OSError:
                    pass

    def check_updates(self):
        import urllib.request
        try:
            with urllib.request.urlopen(UPDATE_URL, timeout=8) as r:
                latest = json.load(r).get("tag_name", "").lstrip("v")
        except Exception:
            messagebox.showinfo("K580", "Couldn't reach GitHub, or no releases have been published yet.")
            return

        def ver(s):
            return tuple(int(x) for x in s.split(".") if x.isdigit())
        if latest and ver(latest) > ver(APP_VERSION):
            if messagebox.askyesno("K580", f"Version {latest} is available (you have {APP_VERSION}).\n"
                                           "Open the download page?"):
                import webbrowser
                webbrowser.open(RELEASES_PAGE)
        else:
            messagebox.showinfo("K580", f"You're up to date ({APP_VERSION}).")

    def factory_reset(self):
        """Rebooting through the ISP bootloader makes the firmware restore its factory settings."""
        import k580_patch
        import tempfile
        if not self.kb:
            messagebox.showwarning("K580", "This needs the cable (wireless switch off).")
            return
        if not messagebox.askyesno("K580", "Reset lighting, key assignments and macros to factory settings?\n"
                                           "The keyboard restarts once. This can't be undone (save a backup\n"
                                           "on the Backup page first if you might want your settings back)."):
            return
        tool = self.find_sinowisp()
        if not tool:
            return
        self.config(cursor="watch")
        self.update()
        self.kb.close()
        self.kb = None
        try:
            k580_patch.read_keyboard(tool, os.path.join(tempfile.gettempdir(), "k580-reset-read.hex"))
        except RuntimeError as e:
            messagebox.showerror("K580", str(e))
        self.kb = self.wait_for_keyboard()
        self.config(cursor="")
        self.connect()
        messagebox.showinfo("K580", "Done. The keyboard is back to factory settings.")

    # ---------------- backup
    def save_backup(self):
        if not self.need_kb():
            return
        path = filedialog.asksaveasfilename(initialdir=os.path.join(HERE, "backups"),
                                            defaultextension=".json", filetypes=[("Backup", "*.json")])
        if not path:
            return
        data = k580.backup(self.kb)
        data["macro_area"] = self.kb.read(0x80 | k580.OP_MACRO, 2048).hex()
        with open(path, "w") as fh:
            json.dump(data, fh, indent=1)
        messagebox.showinfo("K580", "Backup saved.")

    def load_backup(self):
        if not self.need_kb():
            return
        path = filedialog.askopenfilename(initialdir=os.path.join(HERE, "backups"),
                                          filetypes=[("Backup", "*.json")])
        if not path:
            return
        with open(path) as fh:
            data = json.load(fh)
        k580.restore(self.kb, data)
        if "macro_area" in data:
            self.kb.write(k580.OP_MACRO, bytes.fromhex(data["macro_area"]))
        self.load_lighting()
        messagebox.showinfo("K580", "Backup restored.")


if __name__ == "__main__":
    if k580_tray.show_existing():          # already running: bring that window up instead
        sys.exit(0)
    App().mainloop()
