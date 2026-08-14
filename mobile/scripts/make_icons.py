"""Generate the app icon set from source, with no image dependencies.

Run:  python mobile/scripts/make_icons.py

Why a script rather than checked-in artwork: the mark is pure geometry, so
keeping it as code means a colour or proportion change is a diff instead of a
binary blob nobody can edit. Pillow / cairosvg / ImageMagick are all absent
here and none belong in this repo's hash-pinned lockfile, so the PNG encoder
below is stdlib zlib and the rasteriser is a signed-distance field.

The mark: a thick ring with a wedge cut out of its right side, and a filled
dot centred in that aperture. It reads two ways on purpose — as the allocation
donut that is the product's signature visual (`renderHoldingsPie`), and as a C
for Cirvia. The dot echoes the emphasised endpoint on the price chart, and
sitting on the ring's centre line it keeps the whole mark vertically
symmetric. Colours are the shipped tokens from `app/landing.py`.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets"

# Shipped tokens (app/landing.py), converted to sRGB.
ACCENT = (0x72, 0x50, 0xBA)  # oklch(52% 0.16 295)
ACCENT_DEEP = (0x5E, 0x3B, 0xA3)  # oklch(45% 0.16 295)
CANVAS = (0xF8, 0xF5, 0xFC)  # oklch(97.5% 0.01 305)
WHITE = (0xFF, 0xFF, 0xFF)

# Geometry, in units of half-canvas (1.0 = edge).
RING_R = 0.56  # centre-line radius of the ring
RING_HW = 0.165  # half the stroke width
# The aperture has to clear both the arc's round caps (which eat ~17° each
# side) and the dot (~10°), or the remaining slivers close up at tab-bar size
# and the C reads as a solid O.
GAP_DEG = 92.0
GAP_CENTRE_DEG = 0.0  # aperture faces right
DOT_R = 0.10


def _smoothstep_alpha(distance: float, feather: float) -> float:
    """Coverage from a signed distance: 1 inside, 0 outside, soft at the edge."""
    if feather <= 0:
        return 1.0 if distance <= 0 else 0.0
    t = 0.5 - distance / feather
    return 0.0 if t <= 0 else 1.0 if t >= 1 else t


def _angle_within(angle: float, start: float, end: float) -> bool:
    span = (end - start) % (2 * math.pi)
    offset = (angle - start) % (2 * math.pi)
    return offset <= span


def _arc_sdf(x: float, y: float, r: float, hw: float, a0: float, a1: float) -> float:
    """Signed distance to a round-capped arc from a0 to a1 (counter-clockwise)."""
    if _angle_within(math.atan2(y, x), a0, a1):
        return abs(math.hypot(x, y) - r) - hw
    # Outside the sweep: nearest point is one of the two caps.
    cap0 = (r * math.cos(a0), r * math.sin(a0))
    cap1 = (r * math.cos(a1), r * math.sin(a1))
    return (
        min(math.hypot(x - cap0[0], y - cap0[1]), math.hypot(x - cap1[0], y - cap1[1]))
        - hw
    )


def _mark_sdf(x: float, y: float) -> float:
    """The whole mark: the C-ring unioned with its terminal dot."""
    half_gap = math.radians(GAP_DEG) / 2
    centre = math.radians(GAP_CENTRE_DEG)
    a0 = centre + half_gap
    a1 = centre - half_gap
    ring = _arc_sdf(x, y, RING_R, RING_HW, a0, a1)

    # The dot sits inside the aperture, on the ring's centre line — the price
    # chart's emphasised last point.
    dot_angle = centre
    dx = x - RING_R * math.cos(dot_angle)
    dy = y - RING_R * math.sin(dot_angle)
    dot = math.hypot(dx, dy) - DOT_R

    return min(ring, dot)


def _blend(bg: tuple[int, int, int], fg: tuple[int, int, int], a: float) -> tuple[int, int, int]:
    return tuple(round(b + (f - b) * a) for b, f in zip(bg, fg))  # type: ignore[return-value]


def render(
    size: int,
    *,
    background: tuple[int, int, int] | None,
    background_to: tuple[int, int, int] | None = None,
    mark: tuple[int, int, int] | None = WHITE,
    scale: float = 1.0,
) -> bytearray:
    """One RGBA buffer.

    `background=None` leaves it transparent; `scale` shrinks the mark inside
    the canvas, which is how the Android adaptive foreground stays clear of
    the 33% the launcher can crop.
    """
    buf = bytearray(size * size * 4)
    half = size / 2
    feather = 2.0 / half  # ~1px, in mark units

    for py in range(size):
        # +y up, so the geometry reads like maths rather than screen space.
        ny = -((py + 0.5) - half) / half
        row = py * size * 4
        for px in range(size):
            nx = ((px + 0.5) - half) / half

            if background is None:
                base = (0, 0, 0)
                base_a = 0.0
            elif background_to is None:
                base, base_a = background, 1.0
            else:
                # Diagonal ramp, top-left light to bottom-right deep.
                t = max(0.0, min(1.0, ((nx + 1) + (1 - ny)) / 4))
                base, base_a = _blend(background, background_to, t), 1.0

            i = row + px * 4
            if mark is None:
                r, g, b = base
                a = base_a
            else:
                cover = _smoothstep_alpha(_mark_sdf(nx / scale, ny / scale), feather / scale)
                if cover <= 0:
                    r, g, b = base
                    a = base_a
                elif base_a >= 1.0:
                    r, g, b = _blend(base, mark, cover)
                    a = 1.0
                else:
                    # Over transparency: premultiplication would darken the
                    # edge, so keep the colour flat and vary alpha only.
                    r, g, b = mark
                    a = cover

            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = b
            buf[i + 3] = round(a * 255)
    return buf


def write_png(path: Path, size: int, rgba: bytearray) -> None:
    raw = bytearray()
    stride = size * 4
    for y in range(size):
        raw.append(0)  # filter type 0 (None)
        raw.extend(rgba[y * stride : (y + 1) * stride])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)
    print(f"  {path.name}  {size}x{size}  {len(png) / 1024:.1f} KB")


def preview(rgba: bytearray, size: int, cols: int = 46) -> str:
    """ASCII silhouette, so the shape can be checked without opening a file."""
    ramp = " .:-=+*#%@"
    step = size / cols
    lines = []
    for row in range(cols // 2):
        line = []
        for col in range(cols):
            px = min(size - 1, int(col * step))
            py = min(size - 1, int(row * step * 2))
            i = (py * size + px) * 4
            a = rgba[i + 3] / 255
            # Weight by luminance so a white mark reads brighter than its
            # background rather than merely opaque.
            lum = (0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2]) / 255
            line.append(ramp[min(len(ramp) - 1, int(a * lum * len(ramp)))])
        lines.append("".join(line))
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Writing to {OUT}")

    # iOS app icon: opaque, full bleed, no rounded corners (iOS masks it).
    icon = render(1024, background=ACCENT, background_to=ACCENT_DEEP)
    write_png(OUT / "icon.png", 1024, icon)

    # Splash: the mark alone on transparency; the plugin paints the canvas.
    write_png(
        OUT / "splash-icon.png",
        1024,
        render(1024, background=None, mark=ACCENT),
    )

    # Android adaptive foreground: 0.82 fills the safe circle the launcher
    # never crops (r = 33% of the canvas) without touching its edge. Smaller
    # than that and the icon reads as a shrunken sticker next to its peers.
    write_png(
        OUT / "android-icon-foreground.png",
        1024,
        render(1024, background=None, mark=WHITE, scale=0.82),
    )
    write_png(
        OUT / "android-icon-background.png",
        1024,
        render(1024, background=ACCENT, background_to=ACCENT_DEEP, mark=None),
    )
    # Themed icons: the launcher recolours it, so only the alpha matters.
    write_png(
        OUT / "android-icon-monochrome.png",
        1024,
        render(1024, background=None, mark=WHITE, scale=0.82),
    )

    write_png(
        OUT / "favicon.png",
        48,
        render(48, background=CANVAS, mark=ACCENT),
    )

    print("\nSilhouette check (iOS icon):\n")
    print(preview(icon, 1024))


if __name__ == "__main__":
    main()
