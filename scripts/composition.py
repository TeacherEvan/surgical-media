"""composition.py — framing helpers: thirds, golden-ratio anchors, off-axis boxes.

Pure geometry (stdlib). Used by authors/builders to avoid the default
"hero dead-centre in every scene" look, and by ``style_lint.py`` to detect it.
"""

from __future__ import annotations

import math

PHI = (1 + math.sqrt(5)) / 2
Box = tuple[float, float, float, float]


def thirds_points(width: float, height: float) -> list[tuple[float, float]]:
    """The four rule-of-thirds power points (TL, TR, BL, BR)."""
    xs, ys = (width / 3.0, 2 * width / 3.0), (height / 3.0, 2 * height / 3.0)
    return [(x, y) for y in ys for x in xs]


def golden_points(width: float, height: float) -> list[tuple[float, float]]:
    """The four golden-ratio (phi grid) intersections."""
    a = 1.0 / PHI
    xs, ys = (width * (1 - a), width * a), (height * (1 - a), height * a)
    return [(x, y) for y in ys for x in xs]


def box_around(cx: float, cy: float, w: float, h: float) -> Box:
    return (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def off_axis_box(
    width: float,
    height: float,
    size_frac: float = 0.5,
    anchor: str = "thirds_tl",
    aspect: float = 1.0,
) -> Box:
    """A box sitting on a thirds/golden power point instead of the canvas centre.

    ``anchor``: ``thirds_{tl,tr,bl,br}`` or ``golden_{tl,tr,bl,br}``. ``size_frac`` is
    the box width as a fraction of canvas width; ``aspect`` = height/width.
    """
    family, _, corner = anchor.partition("_")
    pts = (
        golden_points(width, height)
        if family == "golden"
        else thirds_points(width, height)
    )
    idx = {"tl": 0, "tr": 1, "bl": 2, "br": 3}.get(corner)
    if idx is None or family not in ("thirds", "golden"):
        raise ValueError(f"unknown anchor {anchor!r}")
    cx, cy = pts[idx]
    bw = width * size_frac
    return box_around(cx, cy, bw, bw * aspect)


def centeredness(box: Box, width: float, height: float) -> float:
    """0 = box centre on canvas centre, 1 = at a canvas corner (normalised distance)."""
    cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
    dx, dy = (cx - width / 2.0) / (width / 2.0), (cy - height / 2.0) / (height / 2.0)
    return min(1.0, math.hypot(dx, dy) / math.sqrt(2.0))
