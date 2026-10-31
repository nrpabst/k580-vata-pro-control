"""K580 Control: a small settings app for the Redragon K580RGB-PRO.

Uses k580.py (wired vendor HID channel). Run with:  pythonw k580_app.py
Changes are written to the keyboard immediately and stored on it.
"""
import colorsys
import json
import math
import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k580  # noqa: E402
import k580_theme  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

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


def describe(entry):
    name = ACTION_BY_BYTES.get(entry)
    if name:
        return name
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
    return k580.SLOT_HW.index(hw) if hw in k580.SLOT_HW else None


# ---------------------------------------------------------------- app
class KeyboardView(tk.Canvas):
    """Clickable picture of the K580. Keys can be selected, filled with a colour, or marked."""

    SCALE = 0.72
    SHORT = {"Backspace": "Bksp", "CapsLock": "Caps", "LShift": "Shift", "RShift": "Shift",
             "LCtrl": "Ctrl", "RCtrl": "Ctrl", "Insert": "Ins", "Delete": "Del", "NumLock": "NmLk",
             "NumEnter": "Ent", "Space": "Space", "Media1": "Prev", "Media2": "Play", "Media3": "Next",
             "K105": "Mode", "K114": "Wheel"}

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
            if labels and len(name) <= 5:
                items.append(self.create_text((x1 + x2) / 2 * s, ((y1 + y2) / 2 - 45) * s, text=name,
                                              fill=k580_theme.MUTED, font=("Segoe UI", 6)))
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

    def set_fills(self, fills):
        self.fills = dict(fills)
        self.redraw()

    def set_marked(self, marked):
        self.marked = set(marked)
        self.redraw()

    def redraw(self):
        accent = k580_theme.hue_hex(getattr(self.master.winfo_toplevel(), "_accent_phase", 0.5), 0.65)
        for idx, r in self.rects.items():
            c = self.fills.get(idx)
            fill = "#%02x%02x%02x" % c if c else k580_theme.FIELD
            if idx in self.selected:
                self.itemconfig(r, fill=fill, outline="#ffffff", width=3)
            elif idx in self.marked:
                self.itemconfig(r, fill=fill, outline=accent, width=2)
            else:
                self.itemconfig(r, fill=fill, outline=k580_theme.BORDER, width=1)


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
            c.grid(row=n // 6, column=n % 6, padx=2, pady=2)
            c.bind("<Button-1>", lambda e, v=rgb: self.pick(v))

        self.preview = tk.Canvas(sw, width=176, height=24, bg=k580_theme.PANEL, highlightthickness=0)
        self.preview.grid(row=2, column=0, columnspan=6, pady=(8, 0), sticky="w")
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

        self.val = tk.DoubleVar(value=1.0)
        vs = ttk.Scale(self, from_=1.0, to=0.0, variable=self.val, orient="vertical", length=size,
                       command=lambda v: self._from_hsv())
        vs.grid(row=0, column=2, padx=(8, 0), sticky="n")
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

    def _wheel_click(self, e):
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
        self.on_pick(rgb)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("K580 Control")
        self.geometry("640x720")
        self.resizable(False, False)
        self.kb = None
        self.wl = None
        self.led = None
        style = k580_theme.apply(self)

        k580_theme.RGBHeader(self, style).pack(fill="x")
        top = ttk.Frame(self, padding=(18, 6, 12, 2), style="Header.TFrame")
        top.pack(fill="x")
        self.status = ttk.Label(top, text="Not connected", style="Header.TLabel")
        self.status.pack(side="left")
        ttk.Button(top, text="Reconnect", command=self.connect).pack(side="right")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.build_lighting(nb)
        self.build_keys(nb)
        self.build_macros(nb)
        self.build_colors(nb)
        self.build_backup(nb)
        self.build_firmware(nb)
        self.connect()
        if "--tab" in sys.argv:                  # e.g. --tab Macros (handy for screenshots)
            want = sys.argv[sys.argv.index("--tab") + 1]
            for t in nb.tabs():
                if nb.tab(t, "text") == want:
                    nb.select(t)

    # ---------------- connection
    def connect(self):
        for dev in (self.kb, getattr(self, "wl", None)):
            if dev:
                dev.close()
        self.kb = self.wl = None
        try:
            self.kb = k580.K580()
            self.status.config(text=f"Connected by cable  ✓   (firmware version 0x{self.kb.firmware_version():04X})")
            first = os.path.join(HERE, "backups", "first-run.json")
            if not os.path.exists(first):
                os.makedirs(os.path.dirname(first), exist_ok=True)
                with open(first, "w") as fh:
                    json.dump(k580.backup(self.kb), fh, indent=1)
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
                self.status.config(text="Connected by 2.4G dongle  ✓  (lighting only; use the cable for keys/macros)")
                self.load_lighting()
                return
            self.wl.close()
            self.wl = None
        except SystemExit:
            pass
        self.status.config(text="Keyboard not found. Plug in the dongle or cable, then Reconnect.")

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
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="Lighting")
        f.columnconfigure(0, minsize=120)
        f.columnconfigure(1, weight=1)
        names = [k580.EFFECTS[h] for h in k580.SLOT_HW] + ["OFF"]
        self.effect = tk.StringVar()
        self.bright = tk.IntVar()
        self.speed = tk.IntVar()
        self.color = tk.StringVar()
        ttk.Label(f, text="Effect").grid(row=0, column=0, sticky="w", pady=4)
        ec = ttk.Combobox(f, textvariable=self.effect, values=names, state="readonly", width=24)
        ec.grid(row=0, column=1, sticky="w")
        ec.bind("<<ComboboxSelected>>", lambda e: self.apply_lighting(new_effect=True))
        ttk.Label(f, text="Brightness").grid(row=1, column=0, sticky="w", pady=4)
        bs = ttk.Scale(f, from_=0, to=4, variable=self.bright, length=260,
                       command=lambda v: self.bright.set(round(float(v))))
        bs.grid(row=1, column=1, sticky="w")
        bs.bind("<ButtonRelease-1>", lambda e: self.apply_lighting())
        ttk.Label(f, text="Speed").grid(row=2, column=0, sticky="w", pady=4)
        ss = ttk.Scale(f, from_=0, to=4, variable=self.speed, length=260,
                       command=lambda v: self.speed.set(round(float(v))))
        ss.grid(row=2, column=1, sticky="w")
        ss.bind("<ButtonRelease-1>", lambda e: self.apply_lighting())
        ttk.Label(f, text="Color").grid(row=3, column=0, sticky="w", pady=4)
        cc = ttk.Combobox(f, textvariable=self.color, values=k580.COLORS, state="readonly", width=24)
        cc.grid(row=3, column=1, sticky="w")
        cc.bind("<<ComboboxSelected>>", lambda e: self.apply_lighting())
        ttk.Label(f, text="Changes apply instantly. Some effects ignore speed or color.",
                  style="Muted.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=12)

        ttk.Separator(f).grid(row=5, column=0, columnspan=2, sticky="ew", pady=8)
        self.media_on = tk.BooleanVar(value=True)
        self.media_toggle = ttk.Checkbutton(f, text="Keep media-key lights on", variable=self.media_on,
                                            command=self.set_media_leds)
        self.media_toggle.grid(row=6, column=0, columnspan=2, sticky="w")
        self.wheel_on = tk.BooleanVar(value=False)
        self.wheel_toggle = ttk.Checkbutton(f, text="Keep volume/brightness key light on",
                                            variable=self.wheel_on, command=self.set_wheel_led)
        self.wheel_toggle.grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.media_note = ttk.Label(f, text="", style="Muted.TLabel")
        self.media_note.grid(row=8, column=0, columnspan=2, sticky="w", pady=(2, 0))

    # ---------------- firmware page
    FIRMWARE_NOTE = (
        "The custom firmware lets you keep the media-key and volume-key lights on all the\n"
        "time, instead of them only flashing when pressed. You turn them on or off on the\n"
        "Lighting page.\n\n"
        "Installing takes about a minute. Plug in the cable and switch wireless off first.\n"
        "Your settings are kept, and Uninstall puts the original firmware back.")

    def build_firmware(self, nb):
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="Firmware")
        ttk.Label(f, text=self.FIRMWARE_NOTE, justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(f, text="Installed now:").grid(row=1, column=0, sticky="w", pady=(14, 4))
        self.fw_state = ttk.Label(f, text="(connect the cable to check)")
        self.fw_state.grid(row=1, column=1, sticky="w", pady=(14, 4))
        self.fw_install = ttk.Button(f, text="Install custom firmware",
                                     command=lambda: self.install_firmware(removing=False),
                                     style="Accent.TButton")
        self.fw_install.grid(row=2, column=0, sticky="w", pady=6)
        self.fw_uninstall = ttk.Button(f, text="Uninstall (restore stock firmware)",
                                       command=lambda: self.install_firmware(removing=True))
        self.fw_uninstall.grid(row=2, column=1, sticky="w", pady=6)
        self.fw_hint = ttk.Label(f, text="", style="Muted.TLabel")
        self.fw_hint.grid(row=3, column=0, columnspan=2, sticky="w")
        nb.bind("<<NotebookTabChanged>>",
                lambda e: self.refresh_media_state() if nb.tab(nb.select(), "text") == "Firmware" else None)

    # ---------------- media-key lights (firmware)
    # The "switch" firmware lights the media keys unless lighting byte 0x11 is set
    # (stock firmware uses that byte for an unbound WASD/arrow swap, which this variant drops).
    MEDIA_BYTE = 0x11
    WHEEL_BYTE = 0x30   # custom firmware: non-zero keeps the volume/brightness key lit
    MARKER = os.path.join(HERE, "firmware", "installed-switch-firmware.txt")

    def firmware_variant(self):
        raw = self.kb.read(0x88, 0x2C00)          # flash dump is rotated by 0x1CA
        site = raw[0x2B00 - 0x1CA:0x2B00 - 0x1CA + 2]
        if site == b"\x20\x27":
            wheel = raw[0x2AD8 - 0x1CA:0x2AD8 - 0x1CA + 3] == b"\x02\x0f\x6a"
            return "switch" if wheel else "switch-old"
        if site == b"\x20\x6e":
            return "toggle"
        if raw[0x2AFE - 0x1CA] == 0x80:
            return "always"
        return "stock"

    def refresh_media_state(self):
        if self.kb:
            v = self.firmware_variant()
            if v == "switch":
                os.makedirs(os.path.dirname(self.MARKER), exist_ok=True)
                open(self.MARKER, "w").write("switch\n")
            elif os.path.exists(self.MARKER):
                os.remove(self.MARKER)
        else:
            v = "switch" if os.path.exists(self.MARKER) else "unknown"
        led = self.led or self.get_led()
        self.fw_state.config(text={"switch": "Custom firmware",
                                   "switch-old": "Custom (older version, no volume-key option)",
                                   "always": "Custom (older 'always on' version)",
                                   "toggle": "Custom (older toggle version)",
                                   "stock": "Stock Redragon firmware",
                                   "unknown": "(connect the cable to check)"}[v])
        old = ("always", "toggle", "switch-old")
        self.media_on.set(led[self.MEDIA_BYTE] == 0 if v in ("switch", "switch-old") else v == "always")
        self.media_toggle.config(state="normal" if v in ("switch", "switch-old") else "disabled")
        self.wheel_on.set(v == "switch" and led[self.WHEEL_BYTE] != 0)
        self.wheel_toggle.config(state="normal" if v == "switch" else "disabled")
        self.media_note.config(text={
            "switch": "When off, media keys flash when pressed and the volume/brightness key\n"
                      "lights only in brightness mode (like stock).",
            "switch-old": "Update the custom firmware (Firmware page) for the volume-key option.",
            "always": "Your current custom firmware keeps the media lights on permanently.\n"
                      "Update it from the Firmware page to get these options.",
            "toggle": "Update the custom firmware from the Firmware page to use these.",
            "stock": "These need the custom firmware (see the Firmware page).",
            "unknown": "Connect the cable once so the app can check your firmware."}[v])
        # one action at a time: stock -> only Install, any custom -> only Uninstall
        self.fw_install.config(state="normal" if v == "stock" else "disabled")
        self.fw_uninstall.config(state="normal" if v not in ("stock", "unknown") else "disabled")
        self.fw_hint.config(text={
            "stock": "", "switch": "",
            "unknown": "Connect the cable (wireless switch off) and click Reconnect to check.",
        }.get(v, "This is an older custom version. Uninstall, then Install, to get the latest."))

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
        if not messagebox.askyesno(
                "K580", ("This puts your original firmware back" if removing else
                         "This reads your keyboard's firmware, checks it's the exact version the patch is for,\n"
                         "saves an untouched copy for undo, and installs the patched version")
                + " (about a minute).\n\nKeep the cable plugged in until it says Done. Continue?"):
            return
        self.config(cursor="watch")
        self.update()
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
                k580_patch.write_hex(k580_patch.apply(fw), patched)
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
        saved["led"] = led.hex()
        k580.restore(self.kb, saved)
        self.kb.write(k580.OP_MACRO, bytes.fromhex(saved["macro_area"]))
        self.status.config(text="Connected by cable  ✓")
        self.load_lighting()
        messagebox.showinfo("K580", "Done. Installed now: " + self.fw_state.cget("text"))

    def load_lighting(self):
        self.led = bytearray(self.get_led())
        self.refresh_media_state()
        hw = self.led[10]
        self.effect.set(k580.EFFECTS.get(hw, "OFF"))
        slot = effect_slot(hw)
        if slot is not None:
            b = self.led[0x3B + 2 * slot]
            self.bright.set(self.led[0x3A + 2 * slot])
            self.speed.set(b >> 4)
            self.color.set(k580.COLORS[b & 7])

    def apply_lighting(self, new_effect=False):
        if not (self.kb or self.wl):
            self.need_kb()
            return
        name = self.effect.get()
        hw = next((h for h, n in k580.EFFECTS.items() if n == name), 0)
        led = bytearray(self.led if self.led else self.get_led())
        led[10] = hw
        led[9] = 1 if hw == 21 else 0
        slot = effect_slot(hw)
        # switching effect keeps that effect's own saved brightness/speed/color
        if slot is not None and not new_effect:
            led[0x3A + 2 * slot] = self.bright.get()
            led[0x3B + 2 * slot] = (self.speed.get() << 4) | k580.COLORS.index(self.color.get() or "red")
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.set_led(led)
        finally:
            self.config(cursor="")
        self.led = led
        if slot is not None:
            b = led[0x3B + 2 * slot]
            self.bright.set(led[0x3A + 2 * slot])
            self.speed.set(b >> 4)
            self.color.set(k580.COLORS[b & 7])

    # ---------------- keys
    def build_keys(self, nb):
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="Keys")
        self.layer = tk.StringVar(value="Normal")
        self.key = tk.StringVar()
        self.category = tk.StringVar(value="Key")
        self.action = tk.StringVar()
        keys = [f"{n}  (#{i})" for i, n in sorted(k580.KEY_NAMES.items(), key=lambda kv: kv[1])]
        ttk.Label(f, text="Layer").grid(row=0, column=0, sticky="w", pady=4)
        lc = ttk.Combobox(f, textvariable=self.layer, values=["Normal", "Fn (while holding Fn)"],
                          state="readonly", width=30)
        lc.grid(row=0, column=1, columnspan=3, sticky="w")
        lc.bind("<<ComboboxSelected>>", lambda e: self.show_key())
        ttk.Label(f, text="Key").grid(row=1, column=0, sticky="w", pady=4)
        kc = ttk.Combobox(f, textvariable=self.key, values=keys, state="readonly", width=30)
        kc.grid(row=1, column=1, columnspan=3, sticky="w")
        kc.bind("<<ComboboxSelected>>", lambda e: self.show_key())
        ttk.Label(f, text="Currently").grid(row=2, column=0, sticky="w", pady=4)
        self.current = ttk.Label(f, text="-")
        self.current.grid(row=2, column=1, columnspan=3, sticky="w")

        ttk.Separator(f).grid(row=3, column=0, columnspan=4, sticky="ew", pady=8)
        ttk.Label(f, text="Type").grid(row=4, column=0, sticky="w", pady=4)
        cc = ttk.Combobox(f, textvariable=self.category, values=CATEGORIES, state="readonly", width=14)
        cc.grid(row=4, column=1, sticky="w")
        cc.bind("<<ComboboxSelected>>", lambda e: self.fill_actions())
        ttk.Label(f, text="Function").grid(row=5, column=0, sticky="w", pady=4)
        self.action_box = ttk.Combobox(f, textvariable=self.action, state="readonly", width=30)
        self.action_box.grid(row=5, column=1, columnspan=3, sticky="w")
        ttk.Button(f, text="Apply", command=self.apply_key, style="Accent.TButton").grid(row=6, column=1, sticky="w", pady=6)

        ttk.Separator(f).grid(row=7, column=0, columnspan=4, sticky="ew", pady=8)
        ttk.Label(f, text="Key combination").grid(row=8, column=0, sticky="w")
        self.combo_mods = {m: tk.BooleanVar() for m in ("LCtrl", "LShift", "LAlt", "LWin")}
        mf = ttk.Frame(f)
        mf.grid(row=8, column=1, columnspan=3, sticky="w")
        for m, var in self.combo_mods.items():
            ttk.Checkbutton(mf, text=m[1:], variable=var).pack(side="left", padx=(0, 6))
        self.combo_key = tk.StringVar()
        ttk.Combobox(mf, textvariable=self.combo_key, values=list(HID), state="readonly", width=8)             .pack(side="left")
        ttk.Button(f, text="Apply combination", command=self.apply_combo, style="Accent.TButton").grid(row=9, column=1, sticky="w", pady=6)

        ttk.Separator(f).grid(row=10, column=0, columnspan=4, sticky="ew", pady=8)
        ttk.Button(f, text="Reset this key", command=self.reset_key).grid(row=11, column=1, sticky="w")
        ttk.Label(f, text="Macros are assigned on the Macros page.", style="Muted.TLabel")             .grid(row=12, column=0, columnspan=4, sticky="w", pady=6)
        self.fill_actions()

    def fill_actions(self):
        names = [n for n in ACTIONS if category_of(n) == self.category.get()]
        self.action_box.config(values=names)
        self.action.set(names[0] if names else "")

    def _layer_idx(self):
        return 0 if self.layer.get() == "Normal" else 1

    def _key_idx(self):
        k = self.key.get()
        return int(k.split("#")[1].rstrip(")")) if k else None

    def show_key(self):
        if not self.need_kb() or self._key_idx() is None:
            return
        m = self.kb.get_matrix(self._layer_idx())
        i = self._key_idx()
        self.current.config(text=describe(m[i * 4:i * 4 + 4]))

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

    def apply_combo(self):
        mods = [m for m, v in self.combo_mods.items() if v.get()]
        if not mods or not self.combo_key.get():
            messagebox.showinfo("K580", "Tick at least one of Ctrl/Shift/Alt/Win and pick a key.")
            return
        self._set_entry(combo(mods, self.combo_key.get()))

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
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="Macros")
        self.macros = []                 # [(name, [4-byte events])] as stored on the keyboard
        self.recorded = []
        self.recording = False
        self.mname = tk.StringVar()
        self.mtext = tk.StringVar()
        self.mmode = tk.StringVar(value="Play once")
        self.mcount = tk.IntVar(value=2)

        # keyboard picture: click keys to choose where macros go
        self.mkb = KeyboardView(f, on_click=lambda i: self.refresh_macro_keys())
        self.mkb.grid(row=0, column=0, columnspan=2, pady=(0, 4))
        self.mkey_info = ttk.Label(f, text="Click keys on the keyboard to select them.", style="Muted.TLabel")
        self.mkey_info.grid(row=1, column=0, columnspan=2, sticky="w")

        # left: saved macros
        left = ttk.Frame(f)
        left.grid(row=2, column=0, sticky="nsw", padx=(0, 12), pady=6)
        ttk.Label(left, text="Saved macros").pack(anchor="w")
        self.mlist = tk.Listbox(left, height=7, width=22, activestyle="none", exportselection=False)
        k580_theme.style_listbox(self.mlist)
        self.mlist.pack(anchor="w", pady=4)
        self.mlist.bind("<<ListboxSelect>>", lambda e: self.show_macro())
        ttk.Button(left, text="Delete macro", command=self.delete_macro).pack(anchor="w")

        # right: assign + new macro
        right = ttk.Frame(f)
        right.grid(row=2, column=1, sticky="nsew", pady=6)
        ttk.Label(right, text="Playback").grid(row=0, column=0, sticky="w")
        pf = ttk.Frame(right)
        pf.grid(row=0, column=1, sticky="w")
        ttk.Combobox(pf, textvariable=self.mmode, values=list(self.REPEAT_MODES), state="readonly",
                     width=26).pack(side="left")
        ttk.Spinbox(pf, from_=2, to=255, textvariable=self.mcount, width=4).pack(side="left", padx=6)
        bf = ttk.Frame(right)
        bf.grid(row=1, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Button(bf, text="Assign macro to selected keys", command=self.assign_macro,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(bf, text="Clear selected keys", command=self.unassign_macro).pack(side="left", padx=6)

        ttk.Separator(right).grid(row=2, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(right, text="New macro").grid(row=3, column=0, sticky="w")
        nf = ttk.Frame(right)
        nf.grid(row=3, column=1, sticky="w")
        ttk.Entry(nf, textvariable=self.mname, width=16).pack(side="left")
        self.rec_btn = ttk.Button(nf, text="● Record", command=self.toggle_record)
        self.rec_btn.pack(side="left", padx=6)
        ttk.Button(nf, text="Clear", command=self.clear_recording).pack(side="left")
        self.rec_view = tk.Text(right, height=3, width=44, state="disabled", wrap="word")
        k580_theme.style_text(self.rec_view)
        self.rec_view.grid(row=4, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(right, text="...or text").grid(row=5, column=0, sticky="w")
        tf = ttk.Frame(right)
        tf.grid(row=5, column=1, sticky="w")
        ttk.Entry(tf, textvariable=self.mtext, width=22).pack(side="left")
        ttk.Button(tf, text="Save macro", command=self.save_macro, style="Accent.TButton") \
            .pack(side="left", padx=6)
        ttk.Label(f, text="Keys with a macro are outlined in the accent colour. G1-G5 recordings aren't touched.",
                  style="Muted.TLabel").grid(row=3, column=0, columnspan=2, sticky="w")

    def load_macros(self):
        if not self.kb:
            return
        area = self.kb.read(0x80 | k580.OP_MACRO, 1024)
        self.macros = [(n, [b[i:i + 4] for i in range(0, len(b), 4)]) for n, b in parse_macros(area)]
        self.mlist.delete(0, "end")
        for i, (n, ev) in enumerate(self.macros):
            self.mlist.insert("end", f"{i + 1}. {n}  ({len(ev)} steps)")
        self.refresh_macro_keys()

    def _bindings(self):
        """matrix index -> macro index, for layer 0."""
        m = self.kb.get_matrix(0)
        return {i: m[i * 4 + 3] for i in range(k580.MATRIX_KEYS) if m[i * 4] == 0x03}

    def refresh_macro_keys(self):
        if not self.kb:
            return
        binds = self._bindings()
        self.mkb.set_marked(set(binds))
        sel = sorted(self.mkb.selected)
        if not sel:
            self.mkey_info.config(text="Click keys on the keyboard to select them.")
            return
        parts = []
        for i in sel:
            name = k580.KEY_NAMES.get(i, f"#{i}")
            j = binds.get(i)
            parts.append(f"{name} → {self.macros[j][0]}" if j is not None and j < len(self.macros) else name)
        self.mkey_info.config(text="Selected: " + ", ".join(parts))

    def show_macro(self):
        pass                                   # selection is read when assigning

    def _write_macros(self):
        area = bytearray(self.kb.read(0x80 | k580.OP_MACRO, 2048))
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
        mode, count = self.REPEAT_MODES[self.mmode.get()]
        entry = k580.macro_key(pick[0], count or max(1, self.mcount.get()), mode)
        m = bytearray(self.kb.get_matrix(0))
        for i in self.mkb.selected:
            m[i * 4:i * 4 + 4] = entry
        self.kb.write(k580.OP_MATRIX, bytes(m), sub=0)
        time.sleep(0.2)
        self.refresh_macro_keys()

    def unassign_macro(self):
        """Give the selected keys back their original function (from the first-run snapshot)."""
        if not self.need_kb() or not self.mkb.selected:
            return
        path = os.path.join(HERE, "backups", "first-run.json")
        orig = bytes.fromhex(json.load(open(path))["matrix"][0]) if os.path.exists(path) else None
        m = bytearray(self.kb.get_matrix(0))
        for i in self.mkb.selected:
            m[i * 4:i * 4 + 4] = orig[i * 4:i * 4 + 4] if orig else bytes(4)
        self.kb.write(k580.OP_MATRIX, bytes(m), sub=0)
        time.sleep(0.2)
        self.refresh_macro_keys()

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
    def build_colors(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="Key colors")
        self.key_colors = {}            # matrix index -> (r, g, b)
        self.ckb = KeyboardView(f, on_click=lambda i: None)
        self.ckb.grid(row=0, column=0, columnspan=3, pady=4)

        self.picker = ColorPicker(f, on_pick=self.apply_color)
        self.picker.grid(row=1, column=0, rowspan=3, sticky="nw", pady=(6, 0))

        side = ttk.Frame(f)
        side.grid(row=1, column=1, sticky="nw", padx=(16, 0), pady=(6, 0))
        ttk.Button(side, text="Select all", command=lambda: self.ckb.select_all(True)).pack(fill="x", pady=2)
        ttk.Button(side, text="Select none", command=lambda: self.ckb.select_all(False)).pack(fill="x", pady=2)
        ttk.Button(side, text="Save to keyboard", command=self.save_colors, style="Accent.TButton") \
            .pack(fill="x", pady=(14, 2))
        ttk.Label(f, text="Click keys to select them, then click a colour: it's applied to the\n"
                          "selected keys right away. Save sends them to the keyboard and switches\n"
                          "the effect to Self-define. Needs the cable.",
                  style="Muted.TLabel").grid(row=4, column=0, columnspan=3, sticky="w", pady=8)

    def apply_color(self, rgb):
        if not self.ckb.selected:
            return
        for idx in self.ckb.selected:
            self.key_colors[idx] = rgb
        self.ckb.set_fills(self.key_colors)

    def load_colors(self):
        if not self.kb:
            return
        planes = self.kb.get_color_group(0)
        n = k580.MATRIX_KEYS
        for idx in self.ckb.rects:
            self.key_colors[idx] = (planes[idx], planes[n + idx], planes[2 * n + idx])
        self.ckb.set_fills(self.key_colors)

    def save_colors(self):
        if not self.need_kb():
            return
        n = k580.MATRIX_KEYS
        planes = bytearray(n * 3)
        for idx, (r, g, b) in self.key_colors.items():
            planes[idx], planes[n + idx], planes[2 * n + idx] = r, g, b
        self.kb.write(k580.OP_COLOR_GROUP, bytes(planes), sub=0)
        time.sleep(0.2)
        led = bytearray(self.get_led())
        led[10], led[9] = 21, 1                    # Self-define effect
        self.set_led(led)
        self.led = led
        self.load_lighting()
        messagebox.showinfo("K580", "Colors saved. Effect set to Self-define.")

    # ---------------- backup
    def build_backup(self, nb):
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="Backup")
        ttk.Button(f, text="Save backup…", command=self.save_backup).pack(anchor="w", pady=4)
        ttk.Button(f, text="Restore backup…", command=self.load_backup).pack(anchor="w", pady=4)
        ttk.Label(f, text="Backups hold lighting, all 4 key layers and macros (incl. G-keys).",
                  style="Muted.TLabel").pack(anchor="w", pady=8)

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
    App().mainloop()
