#!/usr/bin/env python3
"""elements.py — drawable element painters for surgical-media scenes.

Each painter receives a prepared ``ElementContext`` and paints into the
supersampled canvas (and its additive bloom buffer). Painters never mutate
the canvas camera; the engine sets the frame state before dispatching.

All coordinates are design-space pixels (target resolution). Colors are hex
strings. Painters are deterministic: identical storyboard + seed ⇒ identical
frames.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from canvas import get_font, layout_zones, parse_color
from easings import ease_out_expo, spring_pop
from rig import draw_stick_figure

TAU = math.tau
GOLD = "#FFD700"
CYAN = "#38BDF8"
GREEN = "#50FA7B"
RED = "#FF5555"
PURPLE = "#BD93F9"
INK = "#E5E9F0"
DIM = "#64748B"
PANEL = "#0F172A"
PANEL_EDGE = "#1E293B"
TERMINAL_BG = "#161B22"
TERMINAL_EDGE = "#30363D"


@dataclass
class ElementContext:
    width: int
    height: int
    t: float  # scene-local normalized progress [0, 1]
    scene_time: float  # absolute seconds from video start
    local_time: float  # seconds into this scene
    words: list[dict]  # karaoke words for this scene (may be empty)
    seed: int = 0
    trauma: float = 0.0
    zones: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.zones:
            self.zones = layout_zones(self.width, self.height)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _wrap_text(text: str, font, max_width_px: float) -> list[str]:
    """Greedy word wrap measured with the actual font metrics."""
    words = str(text).split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if font.getlength(f"{current} {word}") <= max_width_px:
            current += f" {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 <= edge0:
        return 1.0
    u = min(1.0, max(0.0, (x - edge0) / (edge1 - edge0)))
    return u * u * (3.0 - 2.0 * u)


def _bezier(p0, p1, p2, p3, t: float):
    mt = 1.0 - t
    x = mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0]
    y = mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1]
    return (x, y)


# ---------------------------------------------------------------------------
# canvas-level painters
# ---------------------------------------------------------------------------


def paint_background(cv, el: dict, ctx: ElementContext) -> None:
    color = parse_color(el.get("color", "#000000"))
    big = max(ctx.width, ctx.height) * 4
    cv.draw_.rectangle([-big, -big, big, big], fill=color)


def paint_grid(cv, el: dict, ctx: ElementContext) -> None:
    spacing = float(el.get("spacing", 90))
    color = el.get("color", "#131B2E")
    color = parse_color(color, default_alpha=int(255 * float(el.get("alpha", 1.0))))
    w = max(1.0, ctx.width * 0.0012)
    x = 0.0
    while x <= ctx.width:
        cv.line((x, 0), (x, ctx.height), color, w)
        x += spacing
    y = 0.0
    while y <= ctx.height:
        cv.line((0, y), (ctx.width, y), color, w)
        y += spacing


def paint_hud_badge(cv, el: dict, ctx: ElementContext) -> None:
    text = str(el.get("text", ""))
    if not text:
        return
    corner = str(el.get("corner", "tl"))
    reveal = spring_pop(min(1.0, ctx.local_time / 0.55))
    if reveal <= 0.01:
        return
    hud = ctx.zones["hud"]
    font_size = max(14, int((hud[3] - hud[1]) * 0.42))
    font = get_font(font_size, mono=True)
    pad_x, pad_y = font_size * 0.55, font_size * 0.24
    w = font.getlength(text) + 2 * pad_x
    h = font_size + 2 * pad_y
    if corner == "tr":
        bx0 = hud[2] - w
    elif corner == "tc":
        bx0 = (hud[0] + hud[2] - w) / 2.0
    else:  # tl
        bx0 = hud[0]
    by0 = hud[1] + (hud[3] - hud[1] - h) / 2.0
    # reveal: grow from anchor with spring pop
    scale_pop = 0.6 + 0.4 * reveal
    cx, cy = bx0 + w / 2, by0 + h / 2
    sw, sh = w * scale_pop, h * scale_pop
    box = (cx - sw / 2, cy - sh / 2, cx + sw / 2, cy + sh / 2)
    cv.rectangle(box, fill="#0B1220", outline=GOLD, width=2.0, radius=h * 0.35)
    cv.text((cx, cy), text, GOLD, size=font_size, mono=True, anchor="mm")


def paint_scaling_chart(cv, el: dict, ctx: ElementContext) -> None:
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
    mult = odo_from * math.pow(odo_to / max(odo_from, 1e-9), progress**1.5)
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


def paint_phi_divider(cv, el: dict, ctx: ElementContext) -> None:
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


def _reveal_box(box, progress: float):
    x0, y0, x1, y1 = box
    p = min(1.0, max(0.0, progress))
    return (x0, y0, x0 + (x1 - x0) * p, y1)


_TESSERACT_EDGES = [
    (i, j) for i in range(16) for j in range(i + 1, 16) if (i ^ j).bit_count() == 1
]
_TESSERACT_VERTS = [
    (x, y, z, w) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1) for w in (-1, 1)
]


def paint_tesseract(cv, el: dict, ctx: ElementContext) -> None:
    cx = float(el.get("cx", ctx.width * 0.5))
    cy = float(el.get("cy", ctx.height * 0.42))
    size = float(el.get("size", min(ctx.width, ctx.height) * 0.16))
    ax = ctx.local_time * 0.9 + el.get("phase", 0.0)
    ay = ctx.local_time * 1.15 + 0.7
    az = ctx.local_time * 0.65 + 1.9

    def rot(v, angle, plane):
        x, y, z, w = v
        c, s = math.cos(angle), math.sin(angle)
        if plane == "XW":
            return (x * c - w * s, y, z, x * s + w * c)
        if plane == "YZ":
            return (x, y * c - z * s, y * s + z * c, w)
        return (x * c - y * s, x * s + y * c, z, w)  # XY

    pts2d = []
    depth = []
    for v in _TESSERACT_VERTS:
        v = rot(v, ax, "XW")
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


_NODE_W = 210.0
_NODE_H = 64.0


def paint_system_architecture(cv, el: dict, ctx: ElementContext) -> None:
    nodes = el.get("nodes", [])
    if not nodes:
        return
    cascade_start = float(el.get("cascade_start", 1.1))
    cascade_step = float(el.get("cascade_step", 0.65))
    source = next((n for n in nodes if n.get("role") == "source"), nodes[0])
    targets = [n for n in nodes if n is not source]
    font_size = max(11, int(ctx.height * 0.017))
    mono = True

    # failure cascade order: targets in declaration order
    def node_state(node) -> tuple[str, float]:
        role = node.get("role", "exchange")
        if role == "source":
            return "ok", 0.0
        idx = targets.index(node)
        fail_at = cascade_start + idx * cascade_step
        if ctx.local_time >= fail_at:
            return "fail", ctx.local_time - fail_at
        return "ok", 0.0

    # edges: cubic bezier from source to each target, animated packets
    sx, sy = float(source["x"]) + _NODE_W / 2, float(source["y"])
    for k, tgt in enumerate(targets):
        tx, ty = float(tgt["x"]) - _NODE_W / 2, float(tgt["y"])
        p0, p3 = (sx, sy), (tx, ty)
        midx = (p0[0] + p3[0]) / 2
        p1, p2 = (midx, p0[1]), (midx, p3[1])
        cv.line(p0, p3, "#1F2A3D", 1.0)  # faint guide
        # bezier spine
        spine = [_bezier(p0, p1, p2, p3, i / 60) for i in range(61)]
        cv.polyline(spine, "#26334A", 2.0)
        state, _ = node_state(tgt)
        for pk in range(2):
            p = (ctx.local_time * 0.75 + pk * 0.5 + k * 0.17) % 1.0
            pos = _bezier(p0, p1, p2, p3, p)
            if state == "ok":
                color = CYAN
            else:
                color = (
                    RED if p > 0.55 else CYAN
                )  # packets redden as they die mid-flight
            r = 5.0
            cv.ellipse((pos[0] - r, pos[1] - r, pos[0] + r, pos[1] + r), fill=color)
            if color == RED:
                cv.bloom_ellipse(
                    (pos[0] - r * 2, pos[1] - r * 2, pos[0] + r * 2, pos[1] + r * 2),
                    fill=RED,
                )

    # nodes
    for node in nodes:
        nx, ny = float(node["x"]), float(node["y"])
        state, since = node_state(node)
        ok = state == "ok"
        border = GREEN if ok else RED
        label = str(node.get("label", node["id"])).upper()
        box = (nx - _NODE_W / 2, ny - _NODE_H / 2, nx + _NODE_W / 2, ny + _NODE_H / 2)
        cv.rectangle(box, fill=TERMINAL_BG, outline=border, width=2.4, radius=10.0)
        # status dot
        dot_r = 5.0
        cv.ellipse(
            (
                nx - _NODE_W / 2 + 12,
                ny - dot_r,
                nx - _NODE_W / 2 + 12 + dot_r * 2,
                ny + dot_r,
            ),
            fill=border,
        )
        cv.bloom_ellipse(
            (
                nx - _NODE_W / 2 + 12 - dot_r,
                ny - dot_r * 2,
                nx - _NODE_W / 2 + 12 + dot_r * 3,
                ny + dot_r * 2,
            ),
            fill=border,
        )
        cv.text(
            (nx - _NODE_W / 2 + 30, ny - 14),
            label,
            INK,
            size=font_size,
            mono=mono,
            anchor="lm",
        )
        status = "200 OK" if ok else "503 TLS POOL"
        cv.text(
            (nx - _NODE_W / 2 + 30, ny + 12),
            status,
            border,
            size=font_size,
            mono=mono,
            anchor="lm",
        )
        if not ok and since < 0.35:  # failure flash
            flash = 1.0 - since / 0.35
            cv.bloom_rectangle(
                (
                    box[0] - 8 * flash,
                    box[1] - 8 * flash,
                    box[2] + 8 * flash,
                    box[3] + 8 * flash,
                ),
                fill="#2A0505",
            )


_CODE_KIND = {
    "normal": ("#C9D1D9", None),
    "add": ("#7EE787", "#1B3326"),
    "del": ("#FFA198", "#3B2526"),
    "comment": ("#8B949E", None),
    "accent": (CYAN, None),
}


def paint_code_terminal(cv, el: dict, ctx: ElementContext) -> None:
    box = el.get(
        "box",
        [ctx.width * 0.14, ctx.height * 0.24, ctx.width * 0.86, ctx.height * 0.72],
    )
    x0, y0, x1, y1 = [float(v) for v in box]
    lines = el.get("lines", [])
    title = str(el.get("title", "logs/api.log"))
    reveal = _smoothstep(0.06, 0.86, ctx.t)
    total = max(1, len(lines))
    shown = min(total, int(reveal * total) + (1 if reveal > 0 else 0))

    cv.rectangle(box, fill=TERMINAL_BG, outline=TERMINAL_EDGE, width=2.0, radius=14.0)
    bar_h = max(30.0, (y1 - y0) * 0.085)
    cv.rectangle((x0, y0, x1, y0 + bar_h), fill="#0D1117", radius=14.0)
    # square off the bottom corners of the title bar
    cv.rectangle((x0, y0 + bar_h / 2, x1, y0 + bar_h), fill="#0D1117")
    dot_y = y0 + bar_h / 2
    for i, c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        dx = x0 + 20 + i * 20
        cv.ellipse((dx - 5, dot_y - 5, dx + 5, dot_y + 5), fill=c)
    title_size = max(10, int(bar_h * 0.42))
    cv.text(
        ((x0 + x1) / 2, dot_y),
        title,
        "#8B949E",
        size=title_size,
        mono=True,
        anchor="mm",
    )

    body_top = y0 + bar_h + 12
    body_h = y1 - body_top - 12
    line_h = body_h / max(1.0, min(shown, 18))
    font_size = max(9, int(line_h * 0.58))
    mono_font = get_font(font_size, mono=True)
    cursor_on = int(ctx.local_time * 2.4) % 2 == 0

    for i, line in enumerate(lines[:shown]):
        ly = body_top + i * line_h
        if isinstance(line, str):
            line = {"text": line, "kind": "normal"}
        text = str(line.get("text", ""))
        kind = str(line.get("kind", "normal"))
        fg, row_bg = _CODE_KIND.get(kind, _CODE_KIND["normal"])
        if row_bg:
            cv.rectangle((x0 + 4, ly, x1 - 4, ly + line_h), fill=row_bg)
        gutter = str(i + 1).rjust(3)
        cv.text(
            (x0 + 14, ly + line_h / 2),
            gutter,
            "#4B5563",
            size=font_size,
            mono=True,
            anchor="lm",
        )
        cv.text(
            (x0 + 44, ly + line_h / 2), text, fg, size=font_size, mono=True, anchor="lm"
        )
        if i == shown - 1 and cursor_on:
            tx = x0 + 44 + mono_font.getlength(text) + 2
            cv.rectangle(
                (tx, ly + line_h * 0.18, tx + font_size * 0.6, ly + line_h * 0.82),
                fill=CYAN,
            )


def paint_quote_card(cv, el: dict, ctx: ElementContext) -> None:
    box = el.get(
        "box",
        [ctx.width * 0.16, ctx.height * 0.52, ctx.width * 0.84, ctx.height * 0.78],
    )
    x0, y0, x1, y1 = [float(v) for v in box]
    quote = str(el.get("quote", ""))
    attribution = str(el.get("attribution", ""))
    reveal = ease_out_expo(_smoothstep(0.18, 0.62, ctx.t))
    if reveal <= 0.01:
        return
    slide = (1.0 - reveal) * 34.0
    y0, y1 = y0 + slide, y1 + slide

    cv.rectangle(
        (x0, y0, x1, y1),
        fill="#111C31",
        outline="#2B3A55",
        width=2.0,
        radius=min(26.0, (y1 - y0) * 0.12),
    )
    inner_w = (x1 - x0) * 0.86
    glyph_size = int((y1 - y0) * 0.34)
    cv.text(
        (x0 + (x1 - x0) * 0.055, y0 + (y1 - y0) * 0.16),
        "“",
        GOLD,
        size=glyph_size,
        anchor="lm",
    )
    font_size = max(13, int((y1 - y0) * 0.115))
    font = get_font(font_size)
    max_w = inner_w - (x1 - x0) * 0.12
    lines = _wrap_text(quote, font, max_w)
    ty = y0 + (y1 - y0) * 0.30
    for line in lines[:4]:
        cv.text((x0 + (x1 - x0) * 0.075, ty), line, INK, size=font_size, anchor="lm")
        ty += font_size * 1.32
    if attribution:
        attr_text = f"— {attribution}"
        attr_size = max(10, int(font_size * 0.78))
        max_w_attr = (x1 - x0) * 0.86
        while attr_size > 8 and get_font(attr_size).getlength(attr_text) > max_w_attr:
            attr_size -= 1
        cv.text(
            (x0 + (x1 - x0) * 0.075, y1 - (y1 - y0) * 0.16),
            attr_text,
            DIM,
            size=attr_size,
            anchor="lm",
        )


def paint_kinetic_captions(cv, el: dict, ctx: ElementContext) -> None:
    words = ctx.words
    if not words:
        return
    _, cap_y0, _, cap_y1 = ctx.zones["captions"]
    font_size = el.get("size") or max(18, int(ctx.height * 0.030))
    font = get_font(int(font_size))
    accent = el.get("accent", GOLD)

    current_idx = -1
    for i, w in enumerate(words):
        if ctx.local_time >= float(w["start"]) - 0.02:
            current_idx = i
        else:
            break

    max_w = (ctx.zones["safe"][2] - ctx.zones["safe"][0]) * 0.94
    # wrap the measured token stream itself — edge-tts WordBoundary events
    # may carry multiple whitespace-separated words in one event, so
    # re-splitting a joined string would desynchronize the spans.
    tokens = [str(w["word"]) for w in words]
    lines: list[list[int]] = [[0]]
    cur_text = tokens[0]
    for i in range(1, len(tokens)):
        candidate = f"{cur_text} {tokens[i]}"
        if font.getlength(candidate) <= max_w:
            lines[-1].append(i)
            cur_text = candidate
        else:
            lines.append([i])
            cur_text = tokens[i]

    # locate the current word's line + x-offset while walking indices
    line_boxes: list[tuple[float, float, list[tuple[int, float, float]]]] = []
    space_w = max(font.getlength(" "), font_size * 0.30)
    for line in lines:
        line_words = [tokens[i] for i in line]
        content_w = sum(font.getlength(w) for w in line_words) + space_w * max(
            0, len(line_words) - 1
        )
        x = (ctx.width - content_w) / 2.0
        spans = []
        for i, w in zip(line, line_words):
            ww = font.getlength(w)
            spans.append((i, x, x + ww))
            x += ww + space_w
        line_boxes.append((content_w, 0.0, spans))

    line_h = font_size * 1.28
    block_h = line_h * len(lines)
    y = cap_y0 + max(0.0, (cap_y1 - cap_y0 - block_h) / 2.0)

    # caption backdrop
    pad = font_size * 0.45
    wide = max((s[-1][2] - s[0][1]) for _, _, s in line_boxes) if line_boxes else 0
    cv.rectangle(
        (
            ctx.width / 2 - wide / 2 - pad,
            y - pad * 0.6,
            ctx.width / 2 + wide / 2 + pad,
            y + block_h + pad * 0.6,
        ),
        fill="#05070C",
        radius=12.0,
    )

    for li, (_, _, spans) in enumerate(line_boxes):
        ly = y + li * line_h
        for wi_idx, wx0, wx1 in spans:
            wtext = words[wi_idx]["word"]
            if wi_idx < current_idx:
                fill = INK
            elif wi_idx == current_idx:
                pop = 1.0 + 0.09 * (
                    1.0
                    - _smoothstep(
                        float(words[wi_idx]["start"]),
                        float(words[wi_idx]["end"]),
                        ctx.local_time,
                    )
                )
                fill = accent
                cv.text(
                    ((wx0 + wx1) / 2, ly + line_h / 2),
                    wtext,
                    fill,
                    size=int(font_size * pop),
                    anchor="mm",
                    stroke_fill="#05070C",
                    stroke_width=3,
                )
                continue
            else:
                fill = "#39424F"
            cv.text(
                (wx0, ly + line_h / 2),
                wtext,
                fill,
                size=font_size,
                anchor="lm",
                stroke_fill="#05070C",
                stroke_width=2,
            )


def paint_stick_rig(cv, el: dict, ctx: ElementContext) -> None:
    x = float(el.get("x", ctx.width * 0.5))
    y = float(el.get("y", ctx.height * 0.88))
    height = float(el.get("height", ctx.height * 0.42))
    reach = el.get("reach_to")
    reach_side = str(el.get("reach_side", "right"))
    target = (float(reach[0]), float(reach[1])) if reach else None
    draw_stick_figure(
        cv, x, y, height, ctx.local_time, reach_target=target, reach_side=reach_side
    )


RENDERERS = {
    "background": paint_background,
    "grid": paint_grid,
    "hud_badge": paint_hud_badge,
    "scaling_chart": paint_scaling_chart,
    "phi_divider": paint_phi_divider,
    "tesseract": paint_tesseract,
    "system_architecture": paint_system_architecture,
    "code_terminal": paint_code_terminal,
    "quote_card": paint_quote_card,
    "kinetic_captions": paint_kinetic_captions,
    "stick_rig": paint_stick_rig,
}


def render_element(cv, el: dict, ctx: ElementContext) -> None:
    painter = RENDERERS.get(str(el.get("type")))
    if painter is None:
        print(
            f"render_engine: warning — unknown element type {el.get('type')!r}; skipping",
            flush=True,
        )
        return
    painter(cv, el, ctx)
