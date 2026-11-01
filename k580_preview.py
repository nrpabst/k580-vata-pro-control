"""Approximate on-screen preview of the keyboard's lighting effects.

The keyboard doesn't report its LED colours to the PC, so these are look-alikes built from the
effect, colour, speed and brightness settings, not a mirror of the real LEDs. Effects that react to
key presses are shown with simulated presses.
"""
import colorsys
import math

COLOR_RGB = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255),
             (255, 255, 255)]
MULTI = 7
# effects that react to key presses (the preview simulates presses)
REACTIVE = {4: "colours run left and right along the row of each key you press",
            7: "ripples spread from the keys you press",
            9: "keys you press go dark and fade back",
            12: "keys you press light up and fade"}
COLS, ROWS = 22, 7                           # rough key grid, to measure distances in keys
# the picture's bottom row (G1-G5, volume/brightness key, knob, media keys): no RGB effect lighting
EXTRA_KEYS = {6, 23, 29, 41, 47, 71, 77, 88, 113, 125}


def hue(h, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, max(0.0, min(1.0, v)))
    return r * 255, g * 255, b * 255


def scale(rgb, v):
    v = max(0.0, min(1.0, v))
    return rgb[0] * v, rgb[1] * v, rgb[2] * v


def rnd(i, n=0):
    """Stable pseudo-random 0..1 per key (and per round n)."""
    x = math.sin(i * 12.9898 + n * 78.233) * 43758.5453
    return x - math.floor(x)


def presses(t, keys, every=0.8, keep=4.0):
    """Simulated key presses: [(time, key index)] in the last `keep` seconds."""
    out = []
    n = math.floor(t / every)
    for k in range(n - int(keep / every), n + 1):
        out.append((k * every, keys[int(rnd(k, 5) * len(keys)) % len(keys)]))
    return out


def frame(hw, t, centers, color, speed, custom=None, colors=None):
    """{matrix index: (r, g, b)} for effect `hw` at time t (s). centers: {idx: (x, y)} in 0..1,
    color: 0-7 (7 = multi), speed: 0..1, colors: the effect's 7 colours from the keyboard."""
    rate = 0.5 + speed                        # 0.5x .. 1.5x
    base = (colors or COLOR_RGB)[color] if color < MULTI else None
    keys = sorted(i for i in centers if i not in EXTRA_KEYS)
    hits = presses(t, keys, every=1.2 / rate) if hw in REACTIVE else []
    out = {}
    for i, (x, y) in centers.items():
        dx, dy = x - 0.5, y - 0.5
        ang = math.atan2(dy * ROWS, dx * COLS) / (2 * math.pi)
        rad = math.hypot(dx * COLS, dy * ROWS) / 11          # 0 centre .. ~1 corners
        c = (0, 0, 0)
        if hw == 1:                                           # Fixed on
            c = base or hue(x)
        elif hw == 2:                                         # Respire: slow breathing
            cycle = t * (0.12 + 0.12 * speed)
            c = scale(base or hue(x), 0.5 - 0.5 * math.cos(2 * math.pi * cycle))   # multi: rainbow across
        elif hw == 3:                                         # Rainbow: whole board, slowly
            c = hue(t * (0.03 + 0.06 * speed))
        elif hw in (4, 7, 9, 12):                             # key-press effects
            level, tint = (1.0 if hw == 9 else 0.0), None
            for tp, k in hits:
                age = t - tp
                kx, ky = centers[k]
                d = math.hypot((x - kx) * COLS, (y - ky) * ROWS)   # distance in keys
                if hw == 4:                                   # Flash away: lights run left and right along
                    if abs(y - ky) * ROWS > 0.5:              # the pressed key's row, each key its own
                        continue                              # rainbow colour, fading behind the front
                    dx = abs(x - kx) * COLS
                    front = age * 12 * rate
                    if dx <= front:
                        behind = front - dx                   # keys stay lit a while, then dim
                        glow = 1.0 if behind < 4 else max(0.0, 1 - (behind - 4) / 6)
                        if glow > level:
                            level, tint = glow, hue(x * 1.3 + rnd(tp))
                elif hw == 7:                                 # Ripples: fading rings
                    front = age * 8 * rate
                    ring = max(0.0, 1 - abs(d - front)) * max(0.0, 1 - age / 1.8)
                    if ring > level:
                        level, tint = ring, hue(rnd(tp))
                elif hw == 9 and k == i:                      # Shadow disappear: off, then fades back
                    level = min(level, min(1.0, age / (1.5 / rate)))
                elif hw == 12 and k == i:                     # Reaction: on, then fades off
                    level = max(level, 1 - age / (1.5 / rate))
            c = scale(base or tint or hue(x), level)
        elif hw == 5:                                         # Raindrops: random keys light and fade
            p = (t * 0.6 * rate + rnd(i)) % 1.0
            n = math.floor(t * 0.6 * rate + rnd(i))
            c = scale(base or hue(rnd(i, n)), max(0.0, 1 - p * 2.5) if rnd(i, n + 1) < 0.5 else 0.0)
        elif hw == 6:                                         # Rainbow wheel: colours turn round the centre
            c = hue(ang + t * (0.08 + 0.15 * speed))
        elif hw == 8:                                         # Stars twinkle: random keys twinkle
            p = (t * 0.5 * rate + rnd(i)) % 1.0
            n = math.floor(t * 0.5 * rate + rnd(i))
            on = rnd(i, n + 3) < 0.35
            c = scale(base or hue(rnd(i, n)), math.sin(math.pi * p) if on else 0.0)
        elif hw == 10:                                        # Retro snake
            row = round(y * (ROWS - 1))
            order = (row + (x if row % 2 == 0 else 1 - x)) / ROWS
            d = ((t * 0.06 * rate) - order) % 1.0
            c = scale(base or hue(order), max(0.0, 1 - d * 12))
        elif hw == 11:                                        # Neon stream
            c = hue(x - t * (0.08 + 0.15 * speed))
        elif hw == 13:                                        # Sine wave: dim board, bright sine line
            wave = 0.5 + 0.35 * math.sin(2 * math.pi * (x * 1.5 - t * (0.15 + 0.25 * speed)))
            level = 0.2 + 0.8 * math.exp(-((y - wave) / 0.13) ** 2)
            c = scale(base or hue(x), level)
        elif hw == 14:                                        # Retinue scanning: a bar sweeps across
            pos = 0.5 - 0.5 * math.cos(math.pi * t * (0.2 + 0.3 * speed))
            c = scale(base or hue(t * 0.05), max(0.0, 1 - abs(x - pos) * 8))
        elif hw == 15:                                        # Rotating windmill
            c = hue(ang * 2 + t * (0.08 + 0.15 * speed))
        elif hw == 16:                                        # Colorful waterfall
            c = hue(y * 0.8 - t * (0.08 + 0.15 * speed))
        elif hw == 17:                                        # Blossoming: rainbow rings from the centre
            c = hue(rad * 1.2 - t * (0.08 + 0.15 * speed))
        elif hw == 18:                                        # Rotating storm: rainbow spiral
            c = hue(ang + rad - t * (0.08 + 0.15 * speed))
        elif hw == 21:                                        # Self-define
            c = (custom or {}).get(i, (0, 0, 0))
        out[i] = c
    if hw != 21:                            # effects don't light the bottom row (Self-define can)
        for i in EXTRA_KEYS:
            if i in out:
                out[i] = (0, 0, 0)
    return out
