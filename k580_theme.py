"""Dark theme with an animated RGB accent for K580 Control (plain Tkinter/ttk, no extra packages)."""
import colorsys
import tkinter as tk
from tkinter import ttk

BG = "#0d0e12"          # window
PANEL = "#15171e"       # pages
FIELD = "#1d202a"       # inputs, buttons
FIELD_HI = "#272b38"    # hover
BORDER = "#2c3040"
FG = "#e8eaf2"
MUTED = "#8b91a7"
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI Semibold", 10)
TITLE_FONT = ("Segoe UI Light", 18)


def hue_hex(h, s=0.85, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def dark_title_bar(root):
    """Ask Windows 10 (20H1+) / 11 to draw this window's title bar dark."""
    try:
        import ctypes
        from ctypes import wintypes
        root.update()                                # make sure the real window frame exists
        user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        hwnd = user32.GetParent(root.winfo_id()) or user32.FindWindowW(None, root.title())
        on = ctypes.c_int(1)
        for attr in (20, 19):           # DWMWA_USE_IMMERSIVE_DARK_MODE (current id, then pre-20H1 id)
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
        # Windows 10 only repaints the caption on activation changes, so nudge it
        user32.SendMessageW(hwnd, 0x0086, 0, 0)      # WM_NCACTIVATE off
        user32.SendMessageW(hwnd, 0x0086, 1, 0)      # WM_NCACTIVATE on
        # redraw the frame: NOSIZE | NOMOVE | NOZORDER | FRAMECHANGED
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
    except Exception:
        pass


def apply(root):
    """Style every ttk widget dark. Returns the ttk.Style."""
    root.configure(bg=BG)
    root.after(50, lambda: dark_title_bar(root))
    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=PANEL, foreground=FG, fieldbackground=FIELD, bordercolor=BORDER,
                 lightcolor=PANEL, darkcolor=PANEL, troughcolor=FIELD, focuscolor=PANEL,
                 selectbackground=FIELD_HI, selectforeground=FG, insertcolor=FG, font=FONT)
    st.configure("TFrame", background=PANEL)
    st.configure("Header.TFrame", background=BG)
    st.configure("TLabel", background=PANEL, foreground=FG)
    st.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
    st.configure("Header.TLabel", background=BG, foreground=MUTED)
    st.configure("TButton", background=FIELD, foreground=FG, bordercolor=BORDER, lightcolor=FIELD,
                 darkcolor=FIELD, padding=(12, 5), relief="flat", font=FONT)
    st.map("TButton", background=[("disabled", PANEL), ("pressed", BORDER), ("active", FIELD_HI)],
           foreground=[("disabled", "#4b5063")], bordercolor=[("active", MUTED)])
    st.configure("Accent.TButton", font=FONT_BOLD, foreground="#0d0e12")
    st.configure("TCheckbutton", background=PANEL, foreground=FG, indicatorbackground=FIELD,
                 indicatorforeground=FG, padding=2)
    st.map("TCheckbutton", background=[("active", PANEL)], foreground=[("disabled", "#4b5063")],
           indicatorbackground=[("disabled", PANEL), ("selected", FIELD_HI)])
    for w in ("TCombobox", "TEntry", "TSpinbox"):
        st.configure(w, fieldbackground=FIELD, background=FIELD, foreground=FG, arrowcolor=MUTED,
                     bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD, padding=4)
        st.map(w, fieldbackground=[("readonly", FIELD), ("disabled", PANEL)],
               foreground=[("disabled", "#4b5063")], bordercolor=[("focus", MUTED)])
    st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(8, 6, 8, 0))
    st.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(14, 7), borderwidth=0,
                 lightcolor=BG, bordercolor=BG, font=FONT)
    st.map("TNotebook.Tab", background=[("selected", PANEL), ("active", FIELD)],
           foreground=[("selected", FG), ("active", FG)], lightcolor=[("selected", PANEL)])
    st.configure("TSeparator", background=BORDER)
    # segmented choices (e.g. the Keys page layer): ttk.Radiobutton with style="Toolbutton"
    st.configure("Toolbutton", background=FIELD, foreground=MUTED, padding=(12, 5), borderwidth=1,
                 bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD, font=FONT)
    st.map("Toolbutton", background=[("selected", FIELD_HI), ("active", FIELD_HI)],
           foreground=[("selected", FG), ("active", FG)], bordercolor=[("selected", FG)])
    # sliders: dark recessed track, light handle (kept static: restyling a ttk.Scale makes its handle jump)
    for sc in ("Horizontal.TScale", "Vertical.TScale"):
        st.configure(sc, background=FG, troughcolor="#090a0d", bordercolor=BORDER,
                     lightcolor=FG, darkcolor=FG, sliderthickness=18, troughrelief="flat")
        st.map(sc, background=[("pressed", FG), ("active", FG)],
               lightcolor=[("pressed", FG), ("active", FG)], darkcolor=[("pressed", FG), ("active", FG)])
    # scrollbars (e.g. in long drop-down lists)
    for sb in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        st.configure(sb, background=FIELD_HI, troughcolor=BG, bordercolor=BG, arrowcolor=FG,
                     lightcolor=FIELD_HI, darkcolor=FIELD_HI, gripcount=0, arrowsize=13)
        st.map(sb, background=[("active", MUTED), ("pressed", MUTED)])
    # combobox drop-down lists are plain Tk listboxes
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", FIELD_HI)
    root.option_add("*TCombobox*Listbox.selectForeground", FG)
    root.option_add("*TCombobox*Listbox.font", FONT)
    root.option_add("*TCombobox*Listbox.borderWidth", 0)
    return st


def style_listbox(widget):
    widget.configure(bg=FIELD, fg=FG, selectbackground=FIELD_HI, selectforeground=FG, relief="flat",
                     highlightthickness=1, highlightbackground=BORDER, highlightcolor=MUTED, font=FONT,
                     borderwidth=0)


def style_text(widget):
    widget.configure(bg=FIELD, fg=FG, insertbackground=FG, relief="flat", highlightthickness=1,
                     highlightbackground=BORDER, highlightcolor=MUTED, font=("Consolas", 9))


class RGBHeader(tk.Canvas):
    """Title bar with a slowly cycling RGB gradient line, which also tints accent buttons/tabs."""

    def __init__(self, master, style, title="K580 CONTROL", subtitle="VATA PRO", height=58, **kw):
        super().__init__(master, height=height, bg=BG, highlightthickness=0, **kw)
        self.style = style
        self.phase = 0.0
        self.title_id = self.create_text(18, 26, text=title, anchor="w", fill=FG, font=TITLE_FONT)
        self.sub_id = self.create_text(0, 31, text=subtitle, anchor="w", fill=MUTED,
                                       font=("Segoe UI Semibold", 9))
        self.bar = []
        self.bind("<Configure>", self._layout)
        self.after(30, self._tick)

    def _layout(self, _e=None):
        x2 = self.bbox(self.title_id)[2]
        self.coords(self.sub_id, x2 + 10, 31)
        for item in self.bar:
            self.delete(item)
        w = max(self.winfo_width(), 1)
        n = 120
        self.bar = [self.create_rectangle(i * w / n, self.winfo_height() - 3, (i + 1) * w / n + 1,
                                          self.winfo_height(), width=0) for i in range(n)]

    def _tick(self):
        self.phase = (self.phase + 0.004) % 1.0
        n = len(self.bar)
        for i, item in enumerate(self.bar):
            self.itemconfigure(item, fill=hue_hex(self.phase + i / max(n, 1)))
        accent = hue_hex(self.phase, 0.65, 1.0)
        self.winfo_toplevel()._accent_phase = self.phase
        self.itemconfigure(self.sub_id, fill=accent)
        self.style.configure("Accent.TButton", background=accent, lightcolor=accent, darkcolor=accent,
                             bordercolor=accent)
        self.style.map("Accent.TButton", background=[("active", hue_hex(self.phase, 0.45, 1.0)),
                                                     ("disabled", PANEL)],
                       foreground=[("disabled", "#4b5063")])
        self.style.map("TNotebook.Tab", foreground=[("selected", accent), ("active", FG)],
                       background=[("selected", PANEL), ("active", FIELD)])
        self.after(50, self._tick)
