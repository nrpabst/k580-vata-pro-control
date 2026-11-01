"""The Profiles page: the active profile up top with a live preview of its lighting, then a card for
every saved profile (a small picture of its lighting, Load, and a menu for the rest)."""
import time
import tkinter as tk
from tkinter import messagebox, ttk

import k580
import k580_layout
import k580_preview
import k580_theme as th

UNLIT = (0x1D, 0x20, 0x2A)
CARD_W, CARD_H, GAP = 300, 152, 14


def rounded(c, x1, y1, x2, y2, r, **kw):
    """A rounded rectangle on canvas c."""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


def short_date(saved):
    """'2026-11-01 02:56' -> 'Nov 1'."""
    try:
        return time.strftime("%b ", time.strptime(saved, "%Y-%m-%d %H:%M")) + str(int(saved[8:10]))
    except ValueError:
        return saved


def hexrgb(rgb):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in rgb)


class MiniKeyboard:
    """The K580's keys as plain rectangles at `scale`, at (x, y) on canvas c."""
    X0, Y0, X1, Y1 = 21, 52, 736, 243

    def __init__(self, c, x, y, scale):
        self.c, self.items, self.centers = c, {}, {}
        w, h = self.X1 - self.X0, self.Y1 - self.Y0
        for idx, x1, y1, x2, y2 in k580_layout.LAYOUT:
            self.items[idx] = c.create_rectangle(x + (x1 - self.X0) * scale, y + (y1 - self.Y0) * scale,
                                                 x + (x2 - self.X0) * scale, y + (y2 - self.Y0) * scale,
                                                 fill=hexrgb(UNLIT), width=0)
            self.centers[idx] = (((x1 + x2) / 2 - self.X0) / w, ((y1 + y2) / 2 - self.Y0) / h)
        self.width, self.height = w * scale, h * scale

    def show(self, fills):
        for idx, item in self.items.items():
            self.c.itemconfigure(item, fill=hexrgb(fills.get(idx, UNLIT)))


class Look:
    """What a saved profile's lighting looks like, for the previews."""

    def __init__(self, data, side_names):
        led = bytes.fromhex(data["led"])
        self.hw = led[10]
        slot = self.hw - 1 if self.hw in k580.SLOT_HW else None
        b = led[0x3B + 2 * slot] if slot is not None else 7
        self.color, self.speed = b & 7, (b >> 4) / 4
        bright = (led[0x3A + 2 * slot] & 0x1F) / 4 if slot is not None else 1
        self.level = 0.35 + 0.65 * min(1.0, bright)          # keep a dark profile visible
        pal = bytes.fromhex(data.get("rgb_table", ""))
        self.colors = [tuple(pal[self.hw * 21 + i * 3:self.hw * 21 + i * 3 + 3]) or (255, 255, 255)
                       for i in range(7)] if len(pal) >= self.hw * 21 + 21 else None
        kc, n = bytes.fromhex(data.get("key_colors", "")), k580.MATRIX_KEYS
        self.custom = {i: (kc[i], kc[n + i], kc[2 * n + i]) for i in range(n)} if len(kc) >= 3 * n else {}
        self.effect = k580.EFFECTS.get(self.hw, f"Effect {self.hw}")
        self.side = side_names.get(led[0x12], "Off")

    def fills(self, t, centers):
        out = {}
        for i, c in k580_preview.frame(self.hw, t, centers, self.color, self.speed, self.custom,
                                       self.colors).items():
            out[i] = tuple(max(u, v * self.level) for u, v in zip(UNLIT, c))
        return out


class ProfilesPage:
    def __init__(self, app, f):
        self.app, self.f = app, f
        self.cards = []                 # (canvas, outline item, name)
        self.hero_kb = self.hero_look = None
        f.columnconfigure(0, weight=1)

        self.hero = tk.Canvas(f, width=2 * CARD_W + GAP, height=168, bg=th.PANEL, highlightthickness=0)
        self.hero.grid(row=0, column=0, sticky="w")

        head = ttk.Frame(f)
        head.grid(row=1, column=0, sticky="ew", pady=(22, 10))
        self.count = ttk.Label(head, text="Your profiles", font=th.FONT_BOLD)
        self.count.pack(side="left")
        ttk.Button(head, text="+  New profile", style="Accent.TButton",
                   command=lambda: self.open_form("new")).pack(side="right")

        # name form, shown for a new profile or a rename
        self.form = ttk.Frame(f)
        self.form_label = ttk.Label(self.form, text="")
        self.form_label.pack(side="left")
        self.name = tk.StringVar()
        self.entry = ttk.Entry(self.form, textvariable=self.name, width=24)
        self.entry.pack(side="left", padx=8)
        self.entry.bind("<Return>", lambda e: self.submit())
        self.entry.bind("<Escape>", lambda e: self.close_form())
        self.form_ok = ttk.Button(self.form, text="Save", style="Accent.TButton", command=self.submit)
        self.form_ok.pack(side="left")
        ttk.Button(self.form, text="Cancel", command=self.close_form).pack(side="left", padx=(8, 0))
        self.form_mode = None

        self.grid = ttk.Frame(f)
        self.grid.grid(row=3, column=0, sticky="w")
        ttk.Label(f, text="A profile holds lighting and colours (key colours and side lights too), all 4 "
                          "key layers,\nmacros, G-key recordings and keyboard settings. Saving and "
                          "loading need the USB cable.",
                  style="Muted.TLabel", justify="left").grid(row=4, column=0, sticky="w", pady=(18, 0))
        self.f.after(80, self.tick)

    # ---------- drawing
    def render(self, profiles, active):
        """profiles: {name: data}."""
        self.profiles, self.active = profiles, active
        self.draw_hero()
        for w in self.grid.winfo_children():
            w.destroy()
        self.cards, self.accent_items = [], []
        names = list(profiles)
        self.count.config(text=f"Your profiles  ·  {len(names)}" if names else "Your profiles")
        for n, name in enumerate(names + [None]):
            c = tk.Canvas(self.grid, width=CARD_W, height=CARD_H, bg=th.PANEL, highlightthickness=0)
            c.grid(row=n // 2, column=n % 2, padx=(0, GAP if n % 2 == 0 else 0), pady=(0, GAP))
            if name is None:
                self.new_card(c)
            else:
                self.card(c, name, profiles[name])

    def draw_hero(self):
        c = self.hero
        c.delete("all")
        w, h = int(c.cget("width")), int(c.cget("height"))
        self.hero_bg = rounded(c, 1, 1, w - 1, h - 1, 16, fill=th.FIELD, outline=th.BORDER, width=1)
        self.hero_bar = c.create_rectangle(1, 18, 4, h - 18, width=0, fill=th.FG)
        data = self.profiles.get(self.active)
        self.hero_kb = self.hero_look = None
        if data is None:
            self.hero_tag = c.create_text(26, 28, anchor="nw", text="NO PROFILE LOADED",
                                          font=("Segoe UI Semibold", 8), fill=th.MUTED)
            c.create_text(26, 50, anchor="nw", text="Save your setup", font=("Segoe UI Light", 22),
                          fill=th.FG)
            c.create_text(26, 98, anchor="nw", width=w - 60, fill=th.MUTED, font=th.FONT,
                          text="Keep your lighting, keys and macros as a profile, then switch between\n"
                               "profiles with one click. Load one below, or save the keyboard as a new one.")
            return
        look = Look(data, self.app.side_mode_names())
        self.hero_tag = c.create_text(26, 34, anchor="w", text="ACTIVE PROFILE", fill=th.FG,
                                      font=("Segoe UI Semibold", 8))
        c.create_text(26, 66, anchor="w", text=self.active, font=("Segoe UI Light", 22), fill=th.FG,
                      width=280)
        y = 102
        for label, value in (("Effect", look.effect), ("Side lights", look.side),
                             ("Saved", data.get("saved", ""))):
            c.create_text(26, y, anchor="w", text=label, font=th.FONT, fill=th.MUTED)
            c.create_text(106, y, anchor="w", text=value, font=th.FONT, fill=th.FG)
            y += 20
        scale = 0.40
        kx, ky = w - 22 - (MiniKeyboard.X1 - MiniKeyboard.X0) * scale, (h - 191 * scale) / 2
        rounded(c, kx - 10, ky - 10, w - 12, ky + 191 * scale + 10, 10, fill="#0d0e12", outline="")
        self.hero_kb, self.hero_look = MiniKeyboard(c, kx, ky, scale), look
        self.hero_kb.show(look.fills(time.time(), self.hero_kb.centers))

    def card(self, c, name, data):
        active = name == self.active
        outline = rounded(c, 1, 1, CARD_W - 1, CARD_H - 1, 14, fill=th.FIELD,
                          outline=th.FG if active else th.BORDER, width=2 if active else 1)
        scale = 0.36
        kw = (MiniKeyboard.X1 - MiniKeyboard.X0) * scale
        rounded(c, 10, 10, CARD_W - 10, 20 + 191 * scale, 9, fill="#0d0e12", outline="")
        kb = MiniKeyboard(c, (CARD_W - kw) / 2, 15, scale)
        try:
            look = Look(data, self.app.side_mode_names())
            kb.show(look.fills(1.7, kb.centers))
            meta = f"{look.effect}  ·  {short_date(data.get('saved', ''))}"
        except (KeyError, ValueError, IndexError):
            meta = "Can't read this profile"
        c.create_text(16, 108, anchor="w", text=name, font=("Segoe UI Semibold", 11), fill=th.FG,
                      width=170)
        c.create_text(16, 131, anchor="w", text=meta, font=("Segoe UI", 9), fill=th.MUTED, width=180)
        if active:
            c.create_text(CARD_W - 18, 108, anchor="e", text="ACTIVE", font=("Segoe UI Semibold", 8),
                          fill=th.FG, tags="badge")
            self.cards.append((c, outline, name))
            self.button(c, CARD_W - 52, 120, CARD_W - 16, 142, "•••", lambda: self.menu(c, name), small=True)
        else:
            # the whole card loads the profile; only the ••• button does something else
            hint = c.create_text(CARD_W - 18, 108, anchor="e", text="Click to load", fill=th.FG,
                                 font=("Segoe UI", 8), state="hidden")
            self.button(c, CARD_W - 52, 120, CARD_W - 16, 142, "•••", lambda: self.menu(c, name), small=True)
            c._cursor = "hand2"
            c.config(cursor="hand2")

            def click(e):
                if not any(t.startswith("btn") for t in c.gettags("current")):
                    self.app.load_profile(name)
            c.bind("<ButtonRelease-1>", click)
            c.bind("<Enter>", lambda e: (c.itemconfigure(outline, outline=th.MUTED),
                                         c.itemconfigure(hint, state="normal")))
            c.bind("<Leave>", lambda e: (c.itemconfigure(outline, outline=th.BORDER),
                                         c.itemconfigure(hint, state="hidden")))
        c.bind("<Button-3>", lambda e: self.menu(c, name, e))

    def new_card(self, c):
        outline = rounded(c, 1, 1, CARD_W - 1, CARD_H - 1, 14, fill=th.PANEL, outline=th.BORDER, width=1,
                          dash=(4, 3))
        c.create_text(CARD_W / 2, CARD_H / 2 - 14, text="+", font=("Segoe UI Light", 26), fill=th.MUTED)
        c.create_text(CARD_W / 2, CARD_H / 2 + 20, text="Save the keyboard as a new profile",
                      font=th.FONT, fill=th.MUTED)
        c.bind("<Button-1>", lambda e: self.open_form("new"))
        c.bind("<Enter>", lambda e: (c.itemconfigure(outline, outline=th.MUTED), c.config(cursor="hand2")))
        c.bind("<Leave>", lambda e: (c.itemconfigure(outline, outline=th.BORDER), c.config(cursor="")))

    def button(self, c, x1, y1, x2, y2, text, command, accent=False, small=False):
        tag = f"btn{x1}_{y1}"
        bg = rounded(c, x1, y1, x2, y2, 8, fill=th.FIELD_HI, outline=th.FG if accent else th.BORDER,
                     tags=tag)
        c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=text, fill=th.FG, tags=tag,
                      font=("Segoe UI", 8 if small else 9, "bold" if accent else "normal"))
        if accent:
            self.accent_items = getattr(self, "accent_items", []) + [(c, bg)]
        c.tag_bind(tag, "<Enter>", lambda e: (c.itemconfigure(bg, fill=th.BORDER), c.config(cursor="hand2")))
        c.tag_bind(tag, "<Leave>", lambda e: (c.itemconfigure(bg, fill=th.FIELD_HI),
                                              c.config(cursor=getattr(c, "_cursor", ""))))
        c.tag_bind(tag, "<ButtonRelease-1>", lambda e: command())

    def menu(self, c, name, e=None):
        m = tk.Menu(c, tearoff=0, bg=th.FIELD, fg=th.FG, activebackground=th.FIELD_HI,
                    activeforeground=th.FG, bd=0, font=th.FONT)
        if name != self.active:
            m.add_command(label="Load", command=lambda: self.app.load_profile(name))
        m.add_command(label="Save keyboard to this profile", command=lambda: self.app.update_profile(name))
        m.add_command(label="Rename…", command=lambda: self.open_form("rename", name))
        m.add_separator()
        m.add_command(label="Delete", command=lambda: self.app.delete_profile(name))
        x, y = (e.x_root, e.y_root) if e else (c.winfo_rootx() + CARD_W - 108, c.winfo_rooty() + 126)
        m.tk_popup(x, y)

    # ---------- name form
    def open_form(self, mode, name=None):
        self.form_mode, self.form_name = mode, name
        self.form_label.config(text="New profile name" if mode == "new" else f"Rename {name} to")
        self.form_ok.config(text="Save" if mode == "new" else "Rename")
        self.name.set("" if mode == "new" else name)
        self.form.grid(row=2, column=0, sticky="w", pady=(0, 14))
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def close_form(self):
        self.form.grid_remove()
        self.form_mode = None

    def submit(self):
        new = self.name.get().strip()
        if not new:
            return
        if new in self.profiles and new != getattr(self, "form_name", None):
            messagebox.showinfo("K580", f"There's already a profile called {new}.")
            return
        mode, old = self.form_mode, self.form_name
        self.close_form()
        if mode == "new":
            self.app.new_profile(new)
        elif new != old:
            self.app.rename_profile(old, new)

    # ---------- animation
    def tick(self):
        self.f.after(70, self.tick)
        app = self.app
        if app.state() != "normal" or app.nb.tab(app.nb.select(), "text") != "Profiles":
            return
        phase = getattr(app, "_accent_phase", 0.0)
        accent = th.hue_hex(phase, 0.65, 1.0)
        if self.hero_kb:
            self.hero_kb.show(self.hero_look.fills(time.time(), self.hero_kb.centers))
        if getattr(self, "hero_tag", None):
            self.hero.itemconfigure(self.hero_tag, fill=accent)
        self.hero.itemconfigure(self.hero_bar, fill=accent)
        for c, outline, _name in self.cards:
            c.itemconfigure(outline, outline=accent)
            c.itemconfigure("badge", fill=accent)
        for c, bg in getattr(self, "accent_items", []):
            try:
                c.itemconfigure(bg, outline=accent)
            except tk.TclError:
                pass
