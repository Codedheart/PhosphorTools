"""Where the radial menu's buttons go: fanned out from the hub, pointing away from screen edges.

Pure geometry (no Tk), so it's easy to test. Screen coordinates: x right, y DOWN, angles in degrees
measured the usual way on screen (0 = right, 90 = down, -90 = up).
"""
from __future__ import annotations

import math

Area = tuple[int, int, int, int]      # left, top, right, bottom (usable screen area)


def _fits(points, r: float, area: Area, margin: float, away=(0, 0)) -> bool:
    """On screen, and (away=(sx, sy)) every button on the inward side of a nearby edge:
    sx=-1 means 'near the right edge, stay left of the hub', +1 the opposite; same for sy."""
    l, t, rgt, b = area
    cx, cy, sx, sy = away if len(away) == 4 else (0, 0, 0, 0)
    for x, y in points:
        if not (l + margin + r <= x <= rgt - margin - r and t + margin + r <= y <= b - margin - r):
            return False
        if (sx and (x - cx) * sx < -0.5) or (sy and (y - cy) * sy < -0.5):
            return False
    return True


def _near_edges(cx, cy, reach: float, area: Area) -> tuple[int, int]:
    """Which way to keep away from: (-1 near right / +1 near left / 0, -1 near bottom / +1 near top / 0)."""
    l, t, r, b = area
    sx = -1 if r - cx < reach else (1 if cx - l < reach else 0)
    sy = -1 if b - cy < reach else (1 if cy - t < reach else 0)
    return sx, sy


def _place(cx, cy, n, radius, center_deg, step_deg):
    spread = step_deg * (n - 1)
    out = []
    for i in range(n):
        a = math.radians(center_deg - spread / 2 + step_deg * i)
        out.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return out


def away_angle(cx: float, cy: float, area: Area) -> float:
    """Direction pointing away from the nearest edges: towards the middle of the usable area.
    Near the very middle there's no 'away', so the menu opens upwards."""
    l, t, r, b = area
    mx, my = (l + r) / 2, (t + b) / 2
    dx, dy = mx - cx, my - cy
    if math.hypot(dx / max(1, r - l), dy / max(1, b - t)) < 0.12:
        return -90.0
    return math.degrees(math.atan2(dy, dx))


def fan(cx: float, cy: float, n: int, item_r: float, area: Area, gap: float = 6, margin: float = 4,
        base_radius: float | None = None) -> tuple[list[tuple[float, float]], float]:
    """Positions for n buttons of radius item_r around a hub at (cx, cy).

    Buttons are spaced evenly along an arc centred on the 'away from the edges' direction. If they
    don't all fit on screen, the arc is turned a little at a time, then pushed further out, until
    they do. Returns (positions in order, radius used).
    """
    if n <= 0:
        return [], 0.0
    radius = base_radius or max(item_r * 2.6, (2 * item_r + gap) * n / math.pi)
    want = away_angle(cx, cy, area)
    best = None
    sx, sy = _near_edges(cx, cy, radius * 1.25 + item_r, area)
    if sx or sy:                                 # aim straight between the walls we're near
        want = math.degrees(math.atan2(sy, sx)) if (sx and sy) else (0 if sx > 0 else 180 if sx < 0 else
                                                                      (90 if sy > 0 else -90))
    for grow in range(0, 13):                    # push out up to ~3x if needed
        rad = radius * (1 + 0.15 * grow)
        # angle between neighbours so buttons don't touch at this radius
        step = math.degrees(2 * math.asin(min(1.0, (2 * item_r + gap) / (2 * rad))))
        if n > 1 and step * (n - 1) > 300:       # would wrap all the way round
            continue
        for turn in (0, 10, -10, 20, -20, 30, -30, 45, -45, 60, -60, 75, -75, 90, -90, 120, -120,
                     150, -150, 180):
            pts = _place(cx, cy, n, rad, want + turn, step)
            if _fits(pts, item_r, area, margin, (cx, cy, sx, sy)):
                return pts, rad
            if best is None and _fits(pts, item_r, area, margin):
                best = (pts, rad)
    if best:                                     # couldn't keep fully inward: on-screen at least
        return best
    rad = radius
    step = math.degrees(2 * math.asin(min(1.0, (2 * item_r + gap) / (2 * rad))))
    return _place(cx, cy, n, rad, want, step), rad


def bbox(points, item_r: float, hub: tuple[float, float], hub_r: float, pad: float = 2):
    """Smallest box holding the hub and all buttons: (left, top, right, bottom)."""
    xs = [x for x, _ in points] + [hub[0]]
    ys = [y for _, y in points] + [hub[1]]
    r = max(item_r, hub_r) + pad
    return (math.floor(min(xs) - r), math.floor(min(ys) - r), math.ceil(max(xs) + r), math.ceil(max(ys) + r))
