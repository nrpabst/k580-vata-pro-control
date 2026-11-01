"""Approximate on-screen preview of the keyboard's lighting effects.

The keyboard doesn't report its LED colours to the PC, so these are look-alikes built from the
effect, colour, speed and brightness settings, not a mirror of the real LEDs.
"""
import colorsys
import math

COLOR_RGB = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255),
             (255, 255, 255)]
MULTI = 7
# effects that only react to key presses (nothing to show while idle)
REACTIVE = {7: "ripples spread from the keys you press", 9: "keys you press fade out and back",
            12: "keys light up when you press them"}


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


def frame(hw, t, centers, color, speed, custom=None):
    """{matrix index: (r, g, b)} for effect `hw` at time t (s). centers: {idx: (x, y)} in 0..1,
    color: 0-7 (7 = multi), speed: 0..1."""
    v = 0.35 + 1.3 * speed                      # animation rate
    base = COLOR_RGB[color] if color < MULTI else None
    out = {}
    for i, (x, y) in centers.items():
        dx, dy = x - 0.5, (y - 0.5) * 0.4
        ang, rad = math.atan2(dy, dx) / (2 * math.pi), math.hypot(dx, dy)
        if hw == 1:                                           # Fixed on
            c = base or hue(x)
        elif hw == 2:                                         # Respire
            cycle = t * v * 0.5
            level = 0.5 - 0.5 * math.cos(2 * math.pi * cycle)
            c = scale(base or hue(math.floor(cycle) / 7), level)
        elif hw == 3:                                         # Rainbow
            c = hue(t * v * 0.2)
        elif hw in (4, 5):                                    # Flash away / Raindrops
            period = 1.6 if hw == 5 else 0.9
            p = (t * v / period + rnd(i)) % 1.0
            n = math.floor(t * v / period + rnd(i))
            level = max(0.0, 1 - p * 3) if rnd(i, n) < 0.3 else 0.0
            c = scale(base or hue(rnd(i, n + 7)), level)
        elif hw == 6:                                         # Rainbow wheel
            c = hue(ang + t * v * 0.3)
        elif hw == 8:                                         # Stars twinkle
            p = (t * v * 0.6 + rnd(i)) % 1.0
            level = 0.15 + 0.85 * max(0.0, math.sin(math.pi * p)) ** 6
            c = scale(base or hue(rnd(i, 3)), level)
        elif hw == 9:                                         # Shadow disappear (idle: all lit)
            c = base or hue(x)
        elif hw == 10:                                        # Retro snake
            order = (round(y * 6) * 1.0 + (x if round(y * 6) % 2 == 0 else 1 - x)) / 7
            head = (t * v * 0.12) % 1.0
            d = (head - order) % 1.0
            c = scale(base or hue(order), max(0.0, 1 - d * 12))
        elif hw == 11:                                        # Neon stream
            c = hue(x - t * v * 0.25)
        elif hw == 13:                                        # Sine wave
            level = 0.5 + 0.5 * math.sin(2 * math.pi * (x * 2 - t * v * 0.4))
            c = scale(base or hue(x), level)
        elif hw == 14:                                        # Retinue scanning
            pos = 0.5 - 0.5 * math.cos(math.pi * t * v * 0.35)
            c = scale(base or hue(t * 0.1), max(0.0, 1 - abs(x - pos) * 6))
        elif hw == 15:                                        # Rotating windmill
            c = hue(ang * 2 + t * v * 0.3)
        elif hw == 16:                                        # Colorful waterfall
            c = hue(y * 0.8 - t * v * 0.3)
        elif hw == 17:                                        # Blossoming
            c = hue(rad * 1.5 - t * v * 0.3)
        elif hw == 18:                                        # Rotating storm
            c = hue(ang + rad * 2 - t * v * 0.3)
        elif hw == 21:                                        # Self-define
            c = (custom or {}).get(i, (0, 0, 0))
        else:                                                 # OFF, and Ripples/Reaction while idle
            c = (0, 0, 0)
        out[i] = c
    return out
