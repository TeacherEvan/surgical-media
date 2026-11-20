"""elements/visual.py — personality painters: pulsing hero orb, floating
particle dots, spinning orbit ring, audio-style equalizer bars, typewriter
text, and an animated leader arrow.

Every painter is deterministic: all motion is a pure function of
``ElementContext.t`` / ``local_time`` plus the element's parameters —
no RNG, no scene-edge state, so renders reproduce exactly.
Palette suggestions live in ``references/storyboard-guide.md`` (visual
grammar) and ``references/archetypes.md`` (persona overlays).
"""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any

from canvas import SupersampledCanvas, get_font, rgb

from elements._shared import CYAN, DIM, GOLD, INK, TAU, ElementContext

# ---------------------------------------------------------------------------
# orb_pulse — pulsing hero heart with a soft glow halo
# ---------------------------------------------------------------------------


def paint_orb_pulse(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    cx = float(el.get("cx", ctx.width * 0.5))
    cy = float(el.get("cy", ctx.height * 0.42))
    radius = float(el.get("radius", min(ctx.width, ctx.height) * 0.13))
    color = str(el.get("color", GOLD))
    pulse_hz = float(el.get("pulse_hz", 1.1))
    bob_amp = float(el.get("bob_amp", 0.0))
    bob_speed = float(el.get("bob_speed", 0.55))
    if radius < 1.0:
        return
    t = ctx.local_time
    phase = TAU * pulse_hz * t
    r = radius * (1.0 + 0.22 * math.sin(phase))
    cy += bob_amp * math.sin(TAU * bob_speed * t)
    # soft glow halo, wider than the core
    cv.bloom_ellipse(
        (cx - r * 0.78, cy - r * 0.78, cx + r * 0.78, cy + r * 0.78), fill=color
    )
    cv.ellipse((cx - r / 2, cy - r / 2, cx + r / 2, cy + r / 2), fill=color)
    # thin specular highlight offset toward lower-left (light-source feel)
    hx, hy = math.sin(phase * 0.5) * r * 0.08, math.cos(phase * 0.7) * r * 0.06
    cv.ellipse(
        (cx + hx - r * 0.2, cy + hy - r * 0.2, cx + hx + r * 0.2, cy + hy + r * 0.2),
        fill=rgb("#FFFFFF", 200),
    )


# ---------------------------------------------------------------------------
# dot_field — slow-drifting floating particle swarm (golden-spiral layout)
# ---------------------------------------------------------------------------


def paint_dot_field(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    n = max(4, int(el.get("n", 28)))
    radius = float(el.get("radius", 6.0))
    r_min, r_max = (
        float(el.get("radius_min", radius * 0.8)),
        float(el.get("radius_max", radius * 2.4)),
    )
    color = str(el.get("color", CYAN))
    speed = float(el.get("speed", 0.95))
    jitter = float(el.get("jitter", 8.0))
    bob_amp = float(el.get("bob_amp", 0.9))
    center_x = float(el.get("cx", ctx.width * 0.5))
    center_y = float(el.get("cy", ctx.height * 0.38))
    t = ctx.local_time
    for i in range(n):
        base = (i + 0.5) / n
        ang = base * TAU + t * speed * 0.7 + i * 0.31
        r = r_min + (r_max - r_min) * base + jitter * math.sin(t * 1.9 + i)
        px = center_x + r * math.cos(ang)
        py = center_y + bob_amp * math.sin(t * 3.1 + i * 0.7)
        if not (0 <= px <= ctx.width and 0 <= py <= ctx.height):
            continue
        sz = max(1.0, radius * base)
        cv.bloom_ellipse(
            (px - 1.9 * sz, py - 1.9 * sz, px + 1.9 * sz, py + 1.9 * sz), fill=color
        )
        cv.ellipse((px - sz, py - sz, px + sz, py + sz), fill=color)


# ---------------------------------------------------------------------------
# orbit_ring — dots spinning on a circle around a center
# ---------------------------------------------------------------------------


def paint_orbit_ring(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    n = max(3, int(el.get("n", 9)))
    radius = float(el.get("radius", min(ctx.width, ctx.height) * 0.2))
    cx = float(el.get("cx", ctx.width * 0.5))
    cy = float(el.get("cy", ctx.height * 0.46))
    size = float(el.get("size", 5.0))
    spin_hz = float(el.get("spin_hz", 0.42))
    pulse_hz = float(el.get("pulse_hz", 0.0))
    color = str(el.get("color", CYAN))
    t = ctx.local_time
    if radius < 1.0:
        return
    base = TAU * spin_hz * t
    for i in range(n):
        ang = base + TAU * i / n + i * 0.05
        if pulse_hz:
            pulse = 1.0 + 0.2 * math.sin(TAU * pulse_hz * t + TAU * i / n)
        else:
            pulse = 1.0 + 0.2 * math.sin(base + TAU * i / n * 0.75)
        s = size * pulse
        px = cx + radius * math.cos(ang)
        py = cy + radius * math.sin(ang)
        cv.bloom_ellipse(
            (px - 1.6 * s, py - 1.6 * s, px + 1.6 * s, py + 1.6 * s), fill=color
        )
        cv.ellipse((px - s, py - s, px + s, py + s), fill=color)


# ---------------------------------------------------------------------------
# equalizer — audio-style moving bars (sleeps with the beat)
# ---------------------------------------------------------------------------


def paint_equalizer(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    n = max(2, int(el.get("n", 12)))
    bar_w = float(el.get("bar_width", 10.0))
    gap = float(el.get("gap", 6.0))
    peak = float(el.get("peak", 230.0))
    bar_top = float(el.get("bar_top", ctx.height * 0.68))
    color = str(el.get("color", GOLD))
    beat_hz = float(el.get("beat_hz", 1.35))
    phase_step = float(el.get("phase_step", 0.52))
    t = ctx.local_time
    total_w = n * bar_w + (n - 1) * gap
    x = (ctx.width - total_w) / 2.0 + bar_w / 2.0
    for i in range(n):
        h = peak * (0.58 + 0.42 * math.sin(TAU * beat_hz * t + i * phase_step))
        y0, y1 = bar_top - h, bar_top
        box = (x + i * (bar_w + gap), y0, x + i * (bar_w + gap) + bar_w, y1)
        cv.bloom_rectangle(
            (box[0] - 1.0, box[1] - 1.0, box[2] + 1.0, box[3] + 1.0), fill=color
        )
        cv.rectangle(box, fill=color)


# ---------------------------------------------------------------------------
# typewriter_text — progressive glyph reveal with a blinking block cursor
# ---------------------------------------------------------------------------


def _cursor_visible(t: float, text: str, speed: float, hold: float) -> bool:
    """True while the blink-able block cursor is shown: from reveal until
    ``hold`` seconds after the final glyph lands (all values in seconds)."""
    if t < 0.0:
        return False
    type_done = float(len(text)) / max(speed, 1e-6)
    return t < type_done + hold


def paint_typewriter_text(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    text = str(el.get("text", ""))
    if not text.strip():
        return
    size = float(el.get("size", 22.0))
    family = el.get("family")
    bold = bool(el.get("bold", True))
    color = str(el.get("color", INK))
    accent = str(el.get("accent", GOLD))
    x = float(el.get("x", ctx.width * 0.5))
    y = float(el.get("y", ctx.height * 0.44))
    speed = float(el.get("speed", 15.0))
    start = float(el.get("start", 0.25))
    hold = float(el.get("hold", 0.6))
    cursor_hz = float(el.get("cursor_hz", 2.7))
    show_cursor = bool(el.get("cursor", True))

    t = ctx.local_time - start
    if t < 0:
        t = 0.0
    reveal = min(float(len(text)), max(0.0, t * speed))
    full = int(reveal)
    frac = reveal - full
    font = get_font(max(8, int(size)), family=family, bold=bold)
    # draw revealed glyphs, anchor "lm" at (x, y); positions come from the
    # measured prefix advance so pairs kern as designed
    pen_x = x
    for i, ch in enumerate(text[:full]):
        if ch != " ":
            cv.text(
                (pen_x, y), ch, color, size=size, anchor="lm", family=family, bold=bold
            )
        pen_x = x + font.getlength(text[: i + 1])
    # hanging cursor while there is still unseen text or the tail hasn't landed
    cursor_on = (
        show_cursor
        and _cursor_visible(t, text, speed, hold)
        and int(cursor_hz * t) % 2 == 0
    )
    if cursor_on:
        blk_w = max(1.0, size * 0.62)
        blk_h = max(1.0, size * 1.35)
        cv.rectangle(
            (pen_x + 0.5, y - blk_h / 2, pen_x + 0.5 + blk_w, y + blk_h / 2),
            fill=accent,
        )
    # partial glyph at the boundary
    if frac > 0.05 and full < len(text):
        ch = text[full]
        cv.text(
            (pen_x, y),
            ch,
            color,
            size=max(1.0, size * frac),
            anchor="lm",
            family=family,
            bold=bold,
        )


# ---------------------------------------------------------------------------
# leader_arrow — animated leader line to a point/box (walkthrough scenes)
# ---------------------------------------------------------------------------


def paint_leader_arrow(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    raw = el.get("points")
    points: list[tuple[float, float]] = []
    if isinstance(raw, list) and raw:
        for pt in raw:
            if isinstance(pt, (list, tuple)) and len(pt) == 2:
                points.append((float(pt[0]), float(pt[1])))
    if len(points) < 2:
        return
    speed = float(el.get("speed", 3.2))
    radius = float(el.get("radius", 7.5))
    color = str(el.get("color", CYAN))
    width = float(el.get("width", 4.0))
    wrap = bool(el.get("wrap", False))

    # arc length of the polyline
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in pairwise(points)]
    total = sum(lengths)
    if total <= 0:
        return

    pos = ctx.local_time * speed
    if wrap:
        pos = pos % total
    else:
        pos = min(pos, total)

    seg_at = max(0, len(points) - 2)
    pos_in_seg = min(pos, lengths[seg_at]) if lengths else 0.0
    cum = 0.0
    for i, seg_len in enumerate(lengths):
        if pos < cum + seg_len:
            seg_at = i
            pos_in_seg = max(0.0, pos - cum)
            break
        cum += seg_len
    a = points[seg_at]
    b = points[seg_at + 1]
    d_len = math.hypot(b[0] - a[0], b[1] - a[1])
    if d_len <= 0:
        return
    tt = min(1.0, max(0.0, pos_in_seg / d_len))
    cur = (a[0] + tt * (b[0] - a[0]), a[1] + tt * (b[1] - a[1]))

    # full path faint, walked portion in color
    cv.polyline(points, DIM, max(1.0, width * 0.35))
    cv.polyline([points[0], cur], color, width)

    # animated arrowhead at the cursor
    dx, dy = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(dx, dy) or 1.0
    ux, uy = dx / ln, dy / ln
    tip = (cur[0] + ux * radius, cur[1] + uy * radius)
    half_w = radius * 0.85
    base_l = (cur[0] - ux * 2.0 + uy * half_w, cur[1] - uy * 2.0 - ux * half_w)
    base_r = (cur[0] - ux * 2.0 - uy * half_w, cur[1] - uy * 2.0 + ux * half_w)
    cv.polygon([tip, base_l, base_r], fill=color)
    cv.bloom_polygon([tip, base_l, base_r], fill=color)
    # faint orbital glow around the arrow tip
    if radius > 2:
        cv.bloom_ellipse(
            (
                tip[0] - radius * 1.7,
                tip[1] - radius * 1.7,
                tip[0] + radius * 1.7,
                tip[1] + radius * 1.7,
            ),
            fill=color,
        )
