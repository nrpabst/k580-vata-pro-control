"""Builds the extra lighting effects that the K580 firmware is missing (Rainbow wheel, Colorful
waterfall, Rotating storm) as 8051 code for the free flash at 0xEC00, plus the patch entries that
hook them in. Run it to print the bytes; k580_patch.py holds the result.

How the stock firmware runs an effect (see PROTOCOL.md, section 8c):
- When the effect changes, ?C?CCASE (0x62A9) is called at 0x2013 with A = effect id and an inline
  case table; each case sets bit 0x02, picks its speed interval and jumps to 0x23A7 (stores it in
  XRAM 0x932) which then runs the per-frame switch.
- Every frame, ?C?CCASE is called at 0x23BB with A = XRAM 0x920 (effect id). A case compares the tick
  counter 0x398 with the interval 0x932 and, when it's due, draws one step and jumps to 0x25DD
  (clears the tick counter).
- Drawing: put R in XRAM 0x192, G in XRAM 0x0000, B in A and LCALL 0x9749 (applies brightness),
  then R7 = column (0-20), R5 = row (0-5) and LCALL 0x7295 (sets that key).
- 0x3484 is the firmware's 128-entry rainbow table (3 bytes per colour). It is unevenly spaced
  (yellow to red in a few steps), so our effects compute their colours instead (build_hue).

Our two LCALLs replace the ones at 0x2013 and 0x23BB: for our effect ids they drop the return
address (the inline case table) and run our code; for everything else they LJMP to 0x62A9 as before.
"""
import math
import sys

BASE = 0xEC00
OURS = (0x06, 0x10, 0x12)            # Rainbow wheel, Colorful waterfall, Rotating storm
COLS, ROWS = 21, 6
DARK_KEYS = {6,                      # G1's grid spot: stock effects leave it dark
             102, 108, 114, 120}     # status lights above the numpad: dark unless their lock is on
                                     # (skipping them left the last effect's colour lit)
OFF = 0xFF                           # table value: draw this key black
SKIP_KEYS = {77, 88, 113, 125,       # volume/brightness key + media keys: their own lights, leave alone
             70, 75, 76, 87, 93, 99, 100, 123,   # grid spots with no key
             23, 29, 41, 47, 71}   # side light strips: the firmware drives the 8 spots listed at 0x3758
                                   # (23 29 41 47 71 77 113 125), which share the G2-G5/knob/media spots
SKIP = 0xFE                          # table value: don't touch this key
# our variables live in XRAM 0x0EF0-0x0EF5, which the stock firmware never uses (0x0E8D-0x0E92, used
# before, are scratch space of the firmware's own routines, which reset the colour phase now and then)
PHASE, EFFECT, COL, ROW, TABLE = 0x0EF0, 0x0EF1, 0x0EF2, 0x0EF3, 0x0EF4   # TABLE: 2 bytes
SIDE_MATCH = 12                      # side-light mode (lighting byte 0x12): copy a key's colour
MATCH_KEY = 0x01CA + 0 * 18 + 3 * 3  # key colour buffer (0x1CA + col * 18 + row * 3): Caps Lock
HUE_AT = 0xEF00                      # flash: build_hue (the rainbow colour routine), after the G-flag code


class Asm:
    def __init__(self, base):
        self.base, self.code, self.labels, self.fix = base, bytearray(), {}, []

    def here(self):
        return self.base + len(self.code)

    def label(self, name):
        self.labels[name] = self.here()

    def b(self, *bs):
        self.code += bytes(bs)

    def rel(self, name):                 # 1-byte relative to the end of the instruction
        self.fix.append(("rel", len(self.code), name))
        self.code.append(0)

    def abs16(self, name):
        self.fix.append(("abs", len(self.code), name))
        self.code += b"\0\0"

    def link(self):
        for kind, at, name in self.fix:
            target = self.labels[name] if isinstance(name, str) else name
            if kind == "abs":
                self.code[at:at + 2] = bytes([target >> 8, target & 0xFF])
            else:
                d = target - (self.base + at + 1)
                assert -128 <= d <= 127, (name, d)
                self.code[at] = d & 0xFF
        return bytes(self.code)

    # instructions
    def mov_dptr(self, v):
        if isinstance(v, str):
            self.b(0x90); self.abs16(v)
        else:
            self.b(0x90, v >> 8, v & 0xFF)

    def ljmp(self, t):
        self.b(0x02); self.abs16(t)

    def lcall(self, t):
        self.b(0x12); self.abs16(t)

    def cjne_a(self, imm, t):
        self.b(0xB4, imm); self.rel(t)

    def sjmp(self, t):
        self.b(0x80); self.rel(t)

    def jnc(self, t):
        self.b(0x50); self.rel(t)

    def jnb(self, bit, t):
        self.b(0x30, bit); self.rel(t)


def tables():
    """Base rainbow position (0-253; 254/255 mark skipped/dark keys) for every key, per effect:
    index col * 6 + row."""
    wheel, storm = bytearray(), bytearray()
    for c in range(COLS):
        for r in range(ROWS):
            dx, dy = c - 10, (r - 2.5) * 1.6
            ang = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
            rad = math.hypot(dx, dy)
            idx = c * ROWS + r
            special = SKIP if idx in SKIP_KEYS else OFF if idx in DARK_KEYS else None
            hue = lambda v: min(int(v) & 0xFF, 0xFD)
            wheel.append(special or hue(ang * 256))
            storm.append(special or hue(ang * 256 + rad * 14))
    return wheel, storm


GAMMA, GREEN = 2.2, 0.55               # LED colour correction for build_hue (see there)


def gamma_tables(gamma=GAMMA, green=GREEN):
    """64-step brightness curves: one for red and blue, a dimmer one for green."""
    curve = lambda scale: bytes(round(255 * scale * (i / 63) ** gamma) for i in range(64))
    return curve(1.0), curve(green)


def build_hue(base=HUE_AT):
    """Rainbow colour for hue A (0-255), worked out instead of read from the firmware's uneven
    128-colour table: A * 6 gives the sixth of the wheel (B) and how far into it (A), then one
    channel ramps while the others stay full or off. Each channel then goes through a gamma curve,
    and green through a dimmer one: the green LEDs are far brighter than the red ones, so without it
    yellow and orange wash out to pale green and red seems to appear all at once.
    Returns R5 = red, R6 = green, R4 = blue."""
    a = Asm(base)
    a.b(0x75, 0xF0, 0x06, 0xA4)                 # MOV B,#6 ; MUL AB  -> B = sixth, A = ramp
    a.b(0xFB, 0xF4, 0xFA)                       # R3 = ramp ; R2 = 255 - ramp
    a.b(0xE5, 0xF0)                             # A = sixth
    a.cjne_a(0, "s1"); a.b(0x7D, 0xFF, 0xEB, 0xFE, 0x7C, 0x00); a.sjmp("fix")   # red -> yellow
    a.label("s1")
    a.cjne_a(1, "s2"); a.b(0xEA, 0xFD, 0x7E, 0xFF, 0x7C, 0x00); a.sjmp("fix")   # yellow -> green
    a.label("s2")
    a.cjne_a(2, "s3"); a.b(0x7D, 0x00, 0x7E, 0xFF, 0xEB, 0xFC); a.sjmp("fix")   # green -> cyan
    a.label("s3")
    a.cjne_a(3, "s4"); a.b(0x7D, 0x00, 0xEA, 0xFE, 0x7C, 0xFF); a.sjmp("fix")   # cyan -> blue
    a.label("s4")
    a.cjne_a(4, "s5"); a.b(0xEB, 0xFD, 0x7E, 0x00, 0x7C, 0xFF); a.sjmp("fix")   # blue -> magenta
    a.label("s5")
    a.b(0x7D, 0xFF, 0x7E, 0x00, 0xEA, 0xFC)                                     # magenta -> red
    a.label("fix")
    for reg, table in ((0x05, "t_rb"), (0x06, "t_g"), (0x04, "t_rb")):
        a.b(0xE8 + reg, 0x03, 0x03, 0x54, 0x3F)  # A = Rn >> 2
        a.mov_dptr(table); a.b(0x93, 0xF8 + reg) # Rn = table[A]
    a.b(0x22)
    rb, g = gamma_tables()
    a.label("t_rb"); a.b(*rb)
    a.label("t_g"); a.b(*g)
    return a.link(), a.labels


def build():
    a = Asm(BASE)
    wheel, storm = tables()
    a.label("init_sel")
    for i, eid in enumerate(OURS):
        a.cjne_a(eid, f"i{i}")
        a.sjmp("init_ours")
        a.label(f"i{i}")
    a.ljmp(0x62A9)
    a.label("init_ours")
    a.b(0x15, 0x81, 0x15, 0x81)
    a.jnb(0x01, "set_speed")
    a.b(0xC2, 0x01, 0xD2, 0x02, 0xC2, 0x4A, 0xC2, 0x2D)
    a.b(0xE4); a.mov_dptr(PHASE); a.b(0xF0)
    a.label("set_speed")
    a.mov_dptr(0x0DAF); a.b(0xE0)
    a.mov_dptr(0x3741)
    a.ljmp(0x23A7)

    a.label("frame_sel")
    for i, eid in enumerate(OURS):
        a.cjne_a(eid, f"f{i}")
        a.sjmp("frame_ours")
        a.label(f"f{i}")
    a.ljmp(0x62A9)
    a.label("frame_ours")
    a.b(0x15, 0x81, 0x15, 0x81)
    a.mov_dptr(EFFECT); a.b(0xF0)
    a.mov_dptr(0x0932); a.b(0xE0, 0xFE, 0xA3, 0xE0, 0xFF)
    a.b(0xC3)
    a.mov_dptr(0x0399); a.b(0xE0, 0x9F)
    a.mov_dptr(0x0398); a.b(0xE0, 0x9E)
    a.jnc("due")
    a.b(0x22)
    a.label("due")
    a.lcall("step")
    a.ljmp(0x25DD)

    a.label("step")
    a.mov_dptr(PHASE); a.b(0xE0, 0x24, 0x02, 0xF0)      # phase += 2 (1/128 of the rainbow per step)
    a.mov_dptr(EFFECT); a.b(0xE0)                        # A = effect id
    a.cjne_a(0x06, "s1")
    a.mov_dptr("t_wheel"); a.sjmp("store_t")
    a.label("s1")
    a.cjne_a(0x10, "s2")
    a.mov_dptr("t_wheel"); a.sjmp("store_t")            # waterfall: wheel table for skip/dark keys
    a.label("s2")
    a.mov_dptr("t_storm")
    a.label("store_t")                                  # XRAM 0xE8F:0xE90 = table address
    a.b(0xAA, 0x83, 0xAB, 0x82)                          # MOV R2,DPH ; MOV R3,DPL
    a.mov_dptr(TABLE); a.b(0xEA, 0xF0, 0xA3, 0xEB, 0xF0)
    a.b(0xE4); a.mov_dptr(COL); a.b(0xF0)            # col = 0
    a.label("col_loop")
    a.b(0xE4); a.mov_dptr(ROW); a.b(0xF0)            # row = 0
    a.label("row_loop")
    a.mov_dptr(COL); a.b(0xE0, 0x75, 0xF0, 0x06, 0xA4, 0xFF)   # R7 = col * 6
    a.mov_dptr(ROW); a.b(0xE0, 0x2F, 0xFF)                    # R7 += row
    a.mov_dptr(TABLE); a.b(0xE0, 0xFA, 0xA3, 0xE0)              # R2 = table hi, A = table lo
    a.b(0x2F, 0xF5, 0x82, 0xEA, 0x34, 0x00, 0xF5, 0x83)          # DPTR = table + R7
    a.b(0xE4, 0x93, 0xFF)                                        # R7 = table[key]
    a.cjne_a(SKIP, "not_skip")
    a.ljmp("next_key")                                           # leave this key alone
    a.label("not_skip")
    a.cjne_a(OFF, "lit")
    a.b(0xE4, 0xFD, 0xFE, 0xFC)                                  # dark key: R5 = R6 = R4 = 0
    a.sjmp("store_rgb")
    a.label("lit")
    a.mov_dptr(EFFECT); a.b(0xE0); a.cjne_a(0x10, "not_fall")
    a.mov_dptr(ROW); a.b(0xE0, 0x75, 0xF0, 0xF0, 0xA4, 0xFF)    # waterfall: R7 = -16 * row (rows
    a.label("not_fall")                                          # 1/16 of the rainbow apart, flowing down)
    a.mov_dptr(PHASE); a.b(0xE0, 0x2F)                          # A = phase + R7 (wraps at 256)
    a.lcall(HUE_AT)                                              # R5, R6, R4 = red, green, blue
    a.label("store_rgb")
    a.mov_dptr(0x0192); a.b(0xED, 0xF0)
    a.mov_dptr(0x0000); a.b(0xEE, 0xF0)
    a.b(0xEC); a.lcall(0x9749)                                   # brightness-scaled colour
    a.mov_dptr(COL); a.b(0xE0, 0xFF)
    a.mov_dptr(ROW); a.b(0xE0, 0xFD)
    a.lcall(0x7295)                                              # set key (R7 = col, R5 = row)
    a.label("next_key")
    a.mov_dptr(ROW); a.b(0xE0, 0x04, 0xF0)                    # row++
    a.cjne_a(ROWS, "row_back")
    a.mov_dptr(COL); a.b(0xE0, 0x04, 0xF0)                    # col++
    a.cjne_a(COLS, "col_back")
    a.b(0x22)                                                    # RET
    a.label("row_back"); a.ljmp("row_loop")
    a.label("col_back"); a.ljmp("col_loop")

    # Side lights, mode 12 "Match": the firmware's side-light routine (0x43AA) sends modes above 11
    # to its exit at 0x46F0; we take that jump (0x43E7). For mode 12 we load the side-light colour
    # (XRAM 0x192 / 0x0000 / 0x0DB5) from the Caps Lock key's current colour in the key colour
    # buffer and set bit 0x40, so the routine's own code at 0x46F0 paints all 8 side-light spots.
    a.label("side_match")
    a.mov_dptr(0x03B1); a.b(0xE0); a.cjne_a(SIDE_MATCH, "side_out")
    for src, dst in ((0, 0x0192), (1, 0x0000), (2, 0x0DB5)):
        a.mov_dptr(MATCH_KEY + src); a.b(0xE0)
        a.mov_dptr(dst); a.b(0xF0)
    a.b(0xD2, 0x40)                                              # SETB 0x40: paint the side lights
    a.label("side_out")
    a.ljmp(0x46F0)

    a.label("t_wheel"); a.b(*wheel)
    a.label("t_storm"); a.b(*storm)
    code = a.link()
    return code, a.labels


if __name__ == "__main__":
    code, labels = build()
    print(f"{len(code)} bytes at 0x{BASE:04X}, ends 0x{BASE + len(code):04X}")
    print({k: hex(v) for k, v in labels.items() if not k[0] in "if" or k.endswith("sel")})
    print(code.hex())
    print("hue routine:", build_hue()[0].hex())


def build_gflags(base=0xEEB0):
    """Keeps the G-key 'has a recording' flags (XRAM 0x0DB6 + slot) in step with flash, so G keys the
    app records or clears light up right away instead of after a restart. Runs from the 0x421C routine
    (via the battery copy at 0x0F92, which used to LJMP 0x0FC4): skipped while recording (bit 0x3C),
    and a slot that is being recorded (flag 0xFF) is left alone."""
    a = Asm(base)
    a.b(0x20, 0x3C); a.rel("done")                      # JB 0x3C,done
    a.b(0xC0, 0x06, 0xC0, 0x07)                          # PUSH AR6 ; PUSH AR7
    a.b(0x7F, 0x00)                                      # MOV R7,#0
    a.label("loop")
    a.b(0xEF, 0x75, 0xF0, 0x80, 0xA4)                    # A = R7 * 0x80
    a.b(0xF5, 0x82, 0xE5, 0xF0, 0x24, 0xE0, 0xF5, 0x83)  # DPTR = 0xE000 + slot * 0x80
    a.b(0xE4, 0x93)                                      # A = slot length byte
    a.b(0x7E, 0x00, 0xC3, 0x94, 0x02)                    # R6 = 0 ; A - 2
    a.b(0x40); a.rel("store")                            # JC store (shorter than 2: empty)
    a.b(0x7E, 0x01)                                      # R6 = 1
    a.label("store")
    a.b(0x74, 0xB6, 0x2F, 0xF5, 0x82, 0xE4, 0x34, 0x0D, 0xF5, 0x83)   # DPTR = 0x0DB6 + R7
    a.b(0xE0); a.cjne_a(0xFF, "write"); a.sjmp("next")  # recording into this slot: leave it
    a.label("write")
    a.b(0xEE, 0xF0)                                      # flag = R6
    a.label("next")
    a.b(0x0F, 0xBF, 0x14); a.rel("loop")                 # INC R7 ; CJNE R7,#20,loop
    a.b(0xD0, 0x07, 0xD0, 0x06)                          # POP AR7 ; POP AR6
    a.label("done")
    a.mov_dptr(0x03B0); a.ljmp(0x421F)                   # the instruction the battery hook replaced
    return a.link(), a.labels
