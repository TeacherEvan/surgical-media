"""elements/dataviz.py — scaling chart, phi divider, tesseract motif."""

from __future__ import annotations

import math
from typing import Any

from canvas import SupersampledCanvas
from easings import ease_out_expo, spring_pop

from elements._shared import (
    CYAN,
    DIM,
    GOLD,
    INK,
    PANEL,
    PANEL_EDGE,
    TAU,
    ElementContext,
    _smoothstep,
)


def paint_scaling_chart(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    box = el.get(
        "box",
        [ctx.width * 0.12, ctx.height * 0.28, ctx.width * 0.88, ctx.height * 0.72],
    )
    x0, y0, x1, y1 = [float(v) for v in box]
    exponent = float(el.get("exponent", 4.35))
    accent = el.get("accent", CYAN)
    label = str(el.get("label", "SCALING"))
    odo_from = float(el.get("odometer_from", 1.0))
    odo_to = float(el.get("odometer_to", 500.0))
    odo_suffix = str(el.get("odo_suffix", "×"))
    odo_decimals = max(0, min(2, int(el.get("odo_decimals", 1))))
    milestones = el.get("milestones")  # optional [{"u":0.25,"tag":"10×"}, ...] or []
    progress = ease_out_expo(_smoothstep(0.1, 0.94, ctx.t))

    # panel
    cv.rectangle(box, fill=PANEL, outline=PANEL_EDGE, width=2.0, radius=18.0)
    title_font = max(14, int((y1 - y0) * 0.055))
    cv.text((x0 + 28, y0 + 18), label, DIM, size=title_font, mono=True)

    # plot area (inset)
    px0, py0, px1, py1 = x0 + 40, y0 + title_font + 44, x1 - 40, y1 - 30
    base_y = py1
    cv.line((px0, base_y), (px1, base_y), PANEL_EDGE, 2.0)
    cv.line((px0, py0), (px0, base_y), PANEL_EDGE, 2.0)

    def curve_y(u: float) -> float:
        if abs(exponent) < 1e-9:
            return u
        return (math.exp(exponent * u) - 1.0) / (math.exp(exponent) - 1.0)

    # ghost of the full curve
    ghost = [
        (px0 + u * (px1 - px0), base_y - curve_y(u) * (base_y - py0))
        for u in [i / 90 for i in range(91)]
    ]
    cv.polyline(ghost, "#233149", 2.0)

    # live curve up to progress
    steps = max(2, int(90 * progress))
    live = [
        (
            px0 + (i / steps) * progress * (px1 - px0),
            base_y - curve_y((i / steps) * progress) * (base_y - py0),
        )
        for i in range(steps + 1)
    ]
    if len(live) > 1:
        cv.polyline(live, accent, 4.5)
        tip = live[-1]
        cv.bloom_ellipse((tip[0] - 9, tip[1] - 9, tip[0] + 9, tip[1] + 9), fill=accent)
        cv.ellipse((tip[0] - 6, tip[1] - 6, tip[0] + 6, tip[1] + 6), fill=accent)
        cv.line((tip[0], tip[1]), (tip[0], base_y), "#1C2A44", 1.5)

    # milestone badges on the curve
    if milestones is None:
        milestones = [
            {"u": 0.25, "tag": "10×"},
            {"u": 0.5, "tag": "100×"},
            {"u": 0.78, "tag": "500×"},
        ]
    for ms in milestones:
        u, tag = float(ms["u"]), str(ms["tag"])
        if progress > u:
            pop = spring_pop(min(1.0, (progress - u) / 0.12))
            mx = px0 + u * (px1 - px0)
            my = base_y - curve_y(u) * (base_y - py0)
            r = 13 * pop
            if r > 1.0:
                cv.ellipse((mx - r, my - r, mx + r, my + r), fill=GOLD)
                cv.bloom_ellipse(
                    (mx - r * 1.6, my - r * 1.6, mx + r * 1.6, my + r * 1.6), fill=GOLD
                )
                cv.text(
                    (mx, my - r - 8),
                    tag,
                    GOLD,
                    size=max(10, title_font - 2),
                    mono=True,
                    anchor="ms",
                )

    # quadratic odometer readout
    if odo_from > 0.0 and odo_to > 0.0:
        mult = odo_from * math.pow(odo_to / odo_from, progress**1.5)
    else:
        mult = odo_from + (odo_to - odo_from) * (progress**1.5)
    odo_size = int((y1 - y0) * 0.16)
    cv.text(
        (px1, y0 + title_font + 8),
        f"{mult:6.{odo_decimals}f}{odo_suffix}",
        accent,
        size=odo_size,
        mono=True,
        anchor="rt",
        stroke_fill="#020617",
        stroke_width=2,
    )


def paint_phi_divider(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    box = el.get(
        "box", [ctx.width * 0.2, ctx.height * 0.32, ctx.width * 0.8, ctx.height * 0.62]
    )
    x0, y0, x1, y1 = [float(v) for v in box]
    w, h = x1 - x0, y1 - y0
    t = ctx.t
    lock = _smoothstep(0.42, 0.78, t)

    # nested golden rectangles + quarter arcs (Fibonacci spiral construction)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rw, rh = w, h
    orientation = 0  # 0 right, 1 bottom, 2 left, 3 top — spiral walk
    alpha_lo, alpha_hi = "#7A5B00", GOLD
    for i in range(5):
        local_reveal = ease_out_expo(_smoothstep(0.05 + i * 0.09, 0.34 + i * 0.09, t))
        if local_reveal <= 0.01:
            break
        shade = alpha_hi if i < 3 else alpha_lo
        # golden cut on the long axis
        long_axis = "h" if rw >= rh else "v"
        if long_axis == "h":
            cut = rw / 1.6180339887
            sq = min(cut, rh)
            rx0, ry0, rx1, ry1 = cx - rw / 2, cy - rh / 2, cx - rw / 2 + sq, cy + rh / 2
            arc_box = [rx0, ry0, rx0 + 2 * sq, ry1 + sq]
            next_origin = ("h", cx - rw / 2 + sq, cy - rh / 2, rw - sq, rh)
        else:
            cut = rh / 1.6180339887
            sq = min(cut, rw)
            rx0, ry0, rx1, ry1 = cx - rw / 2, cy - rh / 2, cx + rw / 2, cy - rh / 2 + sq
            arc_box = [rx0, ry0, rx1 + sq, ry0 + 2 * sq]
            next_origin = ("v", cx - rw / 2, cy - rh / 2 + sq, rw, rh - sq)
        stroke_w = max(2.0, w * 0.006 * (1.0 - i * 0.18))
        shown = _reveal_box((rx0, ry0, rx1, ry1), local_reveal)
        cv.rectangle(shown, outline=shade, width=stroke_w)
        if local_reveal > 0.6:
            a_start = (90, 180, 270, 0)[orientation]
            cv.arc(
                arc_box,
                a_start,
                a_start + 90,
                GOLD if lock > 0.6 else shade,
                max(2.0, stroke_w * 0.8),
            )
        # recurse into the remaining rectangle
        _, nx, ny, nw, nh = next_origin
        cx, cy, rw, rh = nx + nw / 2, ny + nh / 2, nw, nh
        orientation = (orientation + 1) % 4

    # φ readout + lock pulse
    readout_size = max(16, int(h * 0.16))
    phi_text = "φ = 1.618034"
    color = GOLD if lock > 0.65 else INK
    cv.text(
        ((x0 + x1) / 2, y1 + 8),
        phi_text,
        color,
        size=readout_size,
        mono=True,
        anchor="ms",
        stroke_fill="#050508",
        stroke_width=3,
    )
    if lock > 0.98:
        pulse = math.sin(ctx.local_time * TAU * 2.2) * 0.5 + 0.5
        r = w * (0.16 + 0.05 * pulse)
        cv.bloom_ellipse(
            (
                (x0 + x1) / 2 - r,
                (y0 + y1) / 2 - r,
                (x0 + x1) / 2 + r,
                (y0 + y1) / 2 + r,
            ),
            fill="#3A2E00",
        )
        cv.text(
            ((x0 + x1) / 2, (y0 + y1) / 2),
            "LOCK",
            GOLD,
            size=int(readout_size * 1.15),
            mono=True,
            anchor="mm",
            stroke_fill="#050508",
            stroke_width=4,
        )


def _reveal_box(
    box: tuple[float, float, float, float], progress: float
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = box
    p = min(1.0, max(0.0, progress))
    return (x0, y0, x0 + (x1 - x0) * p, y1)


_TESSERACT_EDGES = [
    (i, j) for i in range(16) for j in range(i + 1, 16) if (i ^ j).bit_count() == 1
]
_TESSERACT_VERTS = [
    (x, y, z, w) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1) for w in (-1, 1)
]


def paint_tesseract(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    cx = float(el.get("cx", ctx.width * 0.5))
    cy = float(el.get("cy", ctx.height * 0.42))
    size = float(el.get("size", min(ctx.width, ctx.height) * 0.16))
    ax = ctx.local_time * 0.9 + el.get("phase", 0.0)
    ay = ctx.local_time * 1.15 + 0.7
    az = ctx.local_time * 0.65 + 1.9

    def rot(
        v: tuple[float, float, float, float], angle: float, plane: str
    ) -> tuple[float, float, float, float]:
        x, y, z, w = v
        c, s = math.cos(angle), math.sin(angle)
        if plane == "XW":
            return (x * c - w * s, y, z, x * s + w * c)
        if plane == "YZ":
            return (x, y * c - z * s, y * s + z * c, w)
        return (x * c - y * s, x * s + y * c, z, w)  # XY

    pts2d = []
    depth = []
    for vert in _TESSERACT_VERTS:
        v = rot(vert, ax, "XW")
        v = rot(v, ay, "YZ")
        v = rot(v, az, "XY")
        x, y, z, w = v
        s4 = 1.0 / (2.1 - w)  # stereographic R4 → R3
        x3, y3, z3 = x * s4, y * s4, z * s4
        s3 = 1.0 / (2.1 - z3)  # perspective R3 → R2
        pts2d.append((cx + x3 * s3 * size, cy + y3 * s3 * size))
        depth.append((w + z3) / 2.0)

    for i, j in _TESSERACT_EDGES:
        d = (depth[i] + depth[j]) / 2.0  # -1 far … +1 near
        brightness = max(0, min(255, int(90 + 150 * (d + 1.0) / 2.0)))
        green = max(0, min(255, int(brightness * 0.72)))
        color = f"#{brightness:02X}{green:02X}00"  # gold ramp, always #RRGGBB
        width = 1.2 + 2.4 * (d + 1.0) / 2.0
        cv.line(pts2d[i], pts2d[j], color, width)
        if d > 0.25:
            cv.bloom_line(pts2d[i], pts2d[j], "#4A3A00", width)

    for (px, py), d in zip(pts2d, depth):
        r = 2.2 + 2.2 * (d + 1.0) / 2.0
        cv.ellipse((px - r, py - r, px + r, py + r), fill=GOLD if d > 0 else "#8A6D00")
