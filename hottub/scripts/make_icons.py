#!/usr/bin/env python3
"""Draw the hot tub app's icons: the app's thermometer standing in water.

    python scripts/make_icons.py

Writes into ui/public/:
    icon.svg              the browser-tab icon (favicon), rounded tile
    apple-touch-icon.png  180 x 180, for "Add to Home Screen" on iPhone
    icon-192.png          192 x 192 } for Android's home screen and the
    icon-512.png          512 x 512 } web app manifest

The PNG icons are full squares: phones round the corners themselves.
Standard library only; the drawing is a tiny supersampling rasteriser
over a 100 x 100 design, so a size takes a few seconds.  The column colours
are the thermometer's (ui/src/temperatureColours.jsx).
"""

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "ui" / "public"

TILE_TOP, TILE_BOTTOM = (0x1d, 0x45, 0x70), (0x0e, 0x22, 0x38)
WATER, CREST = (0x2a, 0x66, 0xcc), (0x8c, 0xcd, 0xf0)
GLASS, BULB = (0xe3, 0xf4, 0xfc), (0xff, 0xff, 0xff)
# Thermometer scale, top of the column = 110 °F, bottom = 60 °F.
COLOURS = [(60, "#ffffff"), (70, "#d4effb"), (78, "#8ccdf0"), (86, "#2f6fd6"),
           (94, "#7b3fc4"), (100, "#d62828"), (110, "#a3121c")]

# Geometry, in a 100 x 100 design.
TUBE_X, TUBE_TOP, TUBE_BOTTOM, TUBE_R = 50, 13, 66, 8.5
BULB_Y, BULB_R = 71, 13
COLUMN_TOP, COLUMN_R = 24, 4.2       # the column reaches about 104 °F
SCALE_TOP, SCALE_BOTTOM = 15, 66      # where 110 °F and 60 °F sit


def wave(x, base, height=2.6, length=26.0, phase=0.0):
    return base + height * math.sin(2 * math.pi * x / length + phase)


def column_colour(y):
    t = 60 + (SCALE_BOTTOM - y) / (SCALE_BOTTOM - SCALE_TOP) * 50
    t = min(110, max(60, t))
    for (t0, c0), (t1, c1) in zip(COLOURS, COLOURS[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            a = [int(c0[i:i + 2], 16) for i in (1, 3, 5)]
            b = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
            return tuple(a[k] + (b[k] - a[k]) * f for k in range(3))
    return (0xa3, 0x12, 0x1c)


def in_capsule(x, y, cx, top, bottom, r):
    if y < top:
        return (x - cx) ** 2 + (y - top) ** 2 <= r * r
    if y > bottom:
        return (x - cx) ** 2 + (y - bottom) ** 2 <= r * r
    return abs(x - cx) <= r


def in_rounded_square(x, y, radius):
    if radius == 0:
        return 0 <= x <= 100 and 0 <= y <= 100
    cx = min(max(x, radius), 100 - radius)
    cy = min(max(y, radius), 100 - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius


def colour_at(x, y, radius):
    """Colour of the design at (x, y), or None outside the tile."""
    if not in_rounded_square(x, y, radius):
        return None
    f = y / 100
    colour = tuple(TILE_TOP[k] + (TILE_BOTTOM[k] - TILE_TOP[k]) * f for k in range(3))
    # Back wave, behind the thermometer.
    if y > wave(x, 68, phase=1.4):
        colour = tuple(c * 0.55 + w * 0.45 for c, w in zip(colour, WATER))
    # Thermometer: glass, white bulb, coloured column.
    if in_capsule(x, y, TUBE_X, TUBE_TOP, TUBE_BOTTOM, TUBE_R):
        colour = GLASS
    if (x - TUBE_X) ** 2 + (y - BULB_Y) ** 2 <= BULB_R ** 2:
        colour = BULB
    if in_capsule(x, y, TUBE_X, COLUMN_TOP, BULB_Y - 6, COLUMN_R) and y < BULB_Y - 6:
        colour = column_colour(y)
    # Front water, over the bulb, with a light crest.
    front = wave(x, 77)
    if y > front:
        colour = WATER
        if y < front + 2.2:
            colour = CREST
    return colour


def render(size, radius, samples=4):
    """RGBA rows for a `size` x `size` image."""
    rows = []
    step = 100 / size
    for py in range(size):
        row = bytearray()
        for px in range(size):
            total, hits = [0.0, 0.0, 0.0], 0
            for sy in range(samples):
                for sx in range(samples):
                    c = colour_at((px + (sx + 0.5) / samples) * step,
                                  (py + (sy + 0.5) / samples) * step, radius)
                    if c is not None:
                        hits += 1
                        for k in range(3):
                            total[k] += c[k]
            if hits:
                row += bytes(int(round(total[k] / hits)) for k in range(3))
                row.append(int(round(255 * hits / samples ** 2)))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return rows


def write_png(path, rows):
    size = len(rows)
    raw = b"".join(b"\0" + row for row in rows)

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def svg():
    """The same design as SVG, with rounded corners, for the browser tab."""
    def hexc(c):
        return "#%02x%02x%02x" % tuple(int(round(v)) for v in c)

    def wave_path(base, phase):
        points = " ".join(f"{x},{wave(x, base, phase=phase):.2f}" for x in range(0, 101, 2))
        return f"M0,100 L{points} L100,100 Z"

    stops = "".join(
        f'<stop offset="{(t - 60) / 50:.2f}" stop-color="{c}"/>' for t, c in COLOURS
    )
    column_bottom = BULB_Y - 6
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<defs>
<linearGradient id="tile" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{hexc(TILE_TOP)}"/><stop offset="1" stop-color="{hexc(TILE_BOTTOM)}"/></linearGradient>
<linearGradient id="scale" gradientUnits="userSpaceOnUse" x1="0" y1="{SCALE_BOTTOM}" x2="0" y2="{SCALE_TOP}">{stops}</linearGradient>
<clipPath id="round"><rect width="100" height="100" rx="22"/></clipPath>
</defs>
<g clip-path="url(#round)">
<rect width="100" height="100" fill="url(#tile)"/>
<path d="{wave_path(68, 1.4)}" fill="{hexc(WATER)}" fill-opacity="0.45"/>
<rect x="{TUBE_X - TUBE_R}" y="{TUBE_TOP - TUBE_R}" width="{2 * TUBE_R}" height="{TUBE_BOTTOM - TUBE_TOP + 2 * TUBE_R}" rx="{TUBE_R}" fill="{hexc(GLASS)}"/>
<circle cx="{TUBE_X}" cy="{BULB_Y}" r="{BULB_R}" fill="{hexc(BULB)}"/>
<rect x="{TUBE_X - COLUMN_R}" y="{COLUMN_TOP - COLUMN_R}" width="{2 * COLUMN_R}" height="{column_bottom - COLUMN_TOP + COLUMN_R}" rx="{COLUMN_R}" fill="url(#scale)"/>
<path d="{wave_path(77, 0)}" fill="{hexc(WATER)}"/>
<path d="M{" L".join(f"{x},{wave(x, 77) + 1.1:.2f}" for x in range(0, 101, 2))}" fill="none" stroke="{hexc(CREST)}" stroke-width="2.2"/>
</g>
</svg>
"""


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "icon.svg").write_text(svg(), encoding="utf-8")
    for name, size in (("apple-touch-icon.png", 180), ("icon-192.png", 192), ("icon-512.png", 512)):
        write_png(OUT / name, render(size, radius=0, samples=3 if size > 200 else 4))
        print(f"wrote {name}")
    print("wrote icon.svg")


if __name__ == "__main__":
    main()
