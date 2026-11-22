"""elements/svg.py — SVG vector art & animated line-drawing element for surgical-media.

Supports inline SVG markup (``"svg": "<svg ...>"``) or external ``.svg`` files
(``"src": "assets/icon.svg"``).

Two-tier rendering:
1. Built-in stdlib + Pillow vector engine (always available, zero external deps):
   parses viewBox, groups, 2D affine transforms (translate/scale/rotate/matrix),
   styles, colors, and all core primitives (rect, circle, ellipse, line,
   polyline, polygon, path with M/L/H/V/C/S/Q/T/A/Z, text). Supports
   progressive stroke-drawing animation (``reveal: "draw"``), ``spring_pop``
   (``reveal: "pop"``), ``reveal: "fade"``, neon ``glow`` (bloom pyramid),
   rotation, scaling, and ``tint``.
2. Optional native rasterizer upgrade: when ``resvg`` or ``rsvg-convert`` is on
   PATH and the element is static (not ``reveal: "draw"``, no ``glow``/``tint``),
   rasterizes at exact 2x supersampled box resolution with full SVG filter/gradient
   fidelity and caches the RGBA plate in memory. Falls back cleanly on any error.
"""

from __future__ import annotations

import hashlib
import math
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path
from typing import Any

from canvas import SupersampledCanvas, _Draw, parse_color, rgb
from easings import ease_in_out_cubic, ease_out_expo, spring_pop
from PIL import Image, ImageFilter

from elements._shared import ElementContext, _smoothstep

Mat2D = tuple[float, float, float, float, float, float]
Pt2 = tuple[float, float]

_IDENTITY: Mat2D = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

_CSS_COLORS: dict[str, str] = {
    "white": "#FFFFFF",
    "black": "#000000",
    "red": "#EF4444",
    "green": "#22C55E",
    "blue": "#3B82F6",
    "cyan": "#38BDF8",
    "aqua": "#06B6D4",
    "yellow": "#FACC15",
    "gold": "#FFD700",
    "orange": "#F97316",
    "purple": "#A855F7",
    "violet": "#A78BFA",
    "magenta": "#EC4899",
    "pink": "#F472B6",
    "gray": "#94A3B8",
    "grey": "#94A3B8",
    "silver": "#CBD5E1",
    "teal": "#14B8A6",
    "lime": "#84CC16",
    "indigo": "#6366F1",
    "emerald": "#34D399",
    "amber": "#F59E0B",
    "slate": "#64748B",
}

_NUM_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_PATH_TOKEN_RE = re.compile(
    r"[MmLlHhVvCcSsQqTtAaZz]|[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
)
_TRANSFORM_RE = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")
_RGB_RE = re.compile(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", re.IGNORECASE)
_UNSAFE_XML_RE = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)

_MAX_CACHE_ENTRIES = 64
_RASTER_CACHE: OrderedDict[tuple[str, int, int], Image.Image] = OrderedDict()
_FILE_TEXT_CACHE: OrderedDict[tuple[str, int], str] = OrderedDict()
_SVG_DOC_CACHE: OrderedDict[
    str, tuple[tuple[float, float, float, float], list[dict[str, Any]]]
] = OrderedDict()


def _lru_set(cache: OrderedDict[Any, Any], key: Any, value: Any) -> None:
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > _MAX_CACHE_ENTRIES:
        cache.popitem(last=False)


# ---------------------------------------------------------------------------
# 2D affine matrix helpers: (a, b, c, d, e, f) => x' = a*x + c*y + e, y' = b*x + d*y + f
# ---------------------------------------------------------------------------
def _mat_mul(m1: Mat2D, m2: Mat2D) -> Mat2D:
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _apply_mat(m: Mat2D, x: float, y: float) -> Pt2:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _parse_transform(text: str | None) -> Mat2D:
    if not text:
        return _IDENTITY
    mat = _IDENTITY
    for name, raw_args in _TRANSFORM_RE.findall(text):
        nums = [float(v) for v in _NUM_RE.findall(raw_args)]
        op = name.lower()
        cur = _IDENTITY
        if op == "translate" and nums:
            tx = nums[0]
            ty = nums[1] if len(nums) > 1 else 0.0
            cur = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif op == "scale" and nums:
            sx = nums[0]
            sy = nums[1] if len(nums) > 1 else sx
            cur = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif op == "rotate" and nums:
            rad = math.radians(nums[0])
            cs, sn = math.cos(rad), math.sin(rad)
            rot = (cs, sn, -sn, cs, 0.0, 0.0)
            if len(nums) >= 3:
                cx, cy = nums[1], nums[2]
                cur = _mat_mul(
                    (1.0, 0.0, 0.0, 1.0, cx, cy),
                    _mat_mul(rot, (1.0, 0.0, 0.0, 1.0, -cx, -cy)),
                )
            else:
                cur = rot
        elif op == "matrix" and len(nums) >= 6:
            cur = (nums[0], nums[1], nums[2], nums[3], nums[4], nums[5])
        mat = _mat_mul(mat, cur)
    return mat


# ---------------------------------------------------------------------------
# Color & style parsing
# ---------------------------------------------------------------------------
def _parse_svg_color(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    low = s.lower()
    if low in ("none", "transparent") or low.startswith("url("):
        return None
    if low in _CSS_COLORS:
        return _CSS_COLORS[low]
    m = _RGB_RE.match(s)
    if m:
        r, g, b = (min(255, max(0, int(v))) for v in m.groups())
        return f"#{r:02X}{g:02X}{b:02X}"
    if s.startswith("#"):
        hex_part = s[1:]
        if len(hex_part) == 3 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
            return "#" + "".join(c * 2 for c in hex_part)
        if len(hex_part) == 6 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
            return s
    return None


def _parse_float(raw: str | None, default: float = 0.0) -> float:
    if raw is None:
        return default
    m = _NUM_RE.search(raw)
    return float(m.group(0)) if m else default


def _parse_style_dict(elem: ET.Element, parent_style: dict[str, str]) -> dict[str, str]:
    style = dict(parent_style)
    for key in (
        "fill",
        "stroke",
        "stroke-width",
        "opacity",
        "fill-opacity",
        "stroke-opacity",
        "font-size",
        "text-anchor",
    ):
        val = elem.attrib.get(key)
        if val is not None:
            style[key] = val.strip()
    inline = elem.attrib.get("style", "")
    for decl in inline.split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            if k and v:
                style[k] = v
    return style


def _blend_opacity(color_hex: str, opacity: float) -> str:
    """Pre-blend a colour toward black (used for additive bloom tones only).

    Pillow's ``ImageDraw`` cannot alpha-composite, so this used to be applied to
    every translucent fill/stroke. That made ``fill-opacity`` scrims render as
    solid near-black rectangles which hid photos underneath. Fills and strokes
    now go through :func:`_draw_translucent` (real alpha); this helper remains
    only for the additive bloom buffer, where darkening a glow is harmless.
    """
    op = max(0.0, min(1.0, opacity))
    if op >= 0.999:
        return color_hex
    r, g, b = parse_color(color_hex)[:3]
    return f"#{int(r * op):02X}{int(g * op):02X}{int(b * op):02X}"


def _shift_points(points: list[Pt2], shift: Pt2) -> list[Pt2]:
    return [(x - shift[0], y - shift[1]) for x, y in points]


def _draw_translucent(
    cv: SupersampledCanvas,
    painter: Any,
    alpha: float,
    points: list[Pt2] | None = None,
    pad_px: float = 6.0,
) -> None:
    """Draw ``painter(draw, shift)`` with real alpha over the canvas.

    ``ImageDraw`` writes opaque pixels and cannot blend into an existing
    buffer: pre-multiplying RGB by opacity merely paints a darker colour. A
    translucent scrim over a photo therefore became a solid black box. Drawing
    the primitive onto a transparent RGBA layer and compositing that layer in
    place preserves painter order and lets the backdrop show through.

    ``painter`` receives a ``_Draw`` bound to the temporary layer plus a design
    space ``shift`` that maps the original design coordinates into that cropped
    layer. ``points`` (design space) is used to compute the crop.
    """
    a = round(max(0.0, min(1.0, alpha)) * 255)
    if a <= 0:
        return
    if a >= 255:
        painter(cv.draw_, (0.0, 0.0))
        return

    x0 = y0 = 0
    x1, y1 = cv.image.width, cv.image.height
    if points:
        px = [cv.draw_._tp(x, y) for x, y in points]
        if not px:
            return
        pad = max(6.0, float(pad_px)) * cv.scale + 2.0
        x0 = max(0, math.floor(min(p[0] for p in px) - pad))
        y0 = max(0, math.floor(min(p[1] for p in px) - pad))
        x1 = min(x1, math.ceil(max(p[0] for p in px) + pad))
        y1 = min(y1, math.ceil(max(p[1] for p in px) + pad))
    if x1 <= x0 or y1 <= y0:
        return

    layer = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    zoom = cv._z if cv.camera else 1.0
    factor = zoom * cv.scale
    painter(_Draw(cv, layer), (x0 / factor, y0 / factor))
    mask = layer.getchannel("A")
    if a != 255:
        mask = mask.point(lambda p: p * a // 255)
    cv.image.paste(layer.convert("RGB"), (x0, y0), mask)


# ---------------------------------------------------------------------------
# SVG path command parser (M/L/H/V/C/S/Q/T/A/Z)
# ---------------------------------------------------------------------------
def _sample_cubic(p0: Pt2, p1: Pt2, p2: Pt2, p3: Pt2, steps: int = 16) -> list[Pt2]:
    out: list[Pt2] = []
    for i in range(1, steps + 1):
        t = i / steps
        inv = 1.0 - t
        x = (
            inv**3 * p0[0]
            + 3.0 * inv**2 * t * p1[0]
            + 3.0 * inv * t**2 * p2[0]
            + t**3 * p3[0]
        )
        y = (
            inv**3 * p0[1]
            + 3.0 * inv**2 * t * p1[1]
            + 3.0 * inv * t**2 * p2[1]
            + t**3 * p3[1]
        )
        out.append((x, y))
    return out


def _sample_quad(p0: Pt2, p1: Pt2, p2: Pt2, steps: int = 12) -> list[Pt2]:
    out: list[Pt2] = []
    for i in range(1, steps + 1):
        t = i / steps
        inv = 1.0 - t
        x = inv * inv * p0[0] + 2.0 * inv * t * p1[0] + t * t * p2[0]
        y = inv * inv * p0[1] + 2.0 * inv * t * p1[1] + t * t * p2[1]
        out.append((x, y))
    return out


def _sample_arc(
    p0: Pt2,
    rx: float,
    ry: float,
    x_rot_deg: float,
    large_arc: bool,
    sweep: bool,
    p1: Pt2,
    steps: int = 20,
) -> list[Pt2]:
    if p0 == p1:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx < 1e-6 or ry < 1e-6:
        return [p1]
    phi = math.radians(x_rot_deg)
    c_phi, s_phi = math.cos(phi), math.sin(phi)
    dx2 = (p0[0] - p1[0]) * 0.5
    dy2 = (p0[1] - p1[1]) * 0.5
    x1p = c_phi * dx2 + s_phi * dy2
    y1p = -s_phi * dx2 + c_phi * dy2

    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1.0:
        scale = math.sqrt(lam)
        rx *= scale
        ry *= scale

    num = max(0.0, rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p)
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    factor = math.sqrt(num / max(den, 1e-12))
    if large_arc == sweep:
        factor = -factor
    cxp = factor * (rx * y1p) / ry
    cyp = factor * -(ry * x1p) / rx

    cx = c_phi * cxp - s_phi * cyp + (p0[0] + p1[0]) * 0.5
    cy = s_phi * cxp + c_phi * cyp + (p0[1] + p1[1]) * 0.5

    def _angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        mag = math.sqrt((ux * ux + uy * uy) * (vx * vx + vy * vy))
        cos_a = max(-1.0, min(1.0, dot / max(mag, 1e-12)))
        ang = math.acos(cos_a)
        return -ang if (ux * vy - uy * vx) < 0 else ang

    vx0, vy0 = (x1p - cxp) / rx, (y1p - cyp) / ry
    vx1, vy1 = (-x1p - cxp) / rx, (-y1p - cyp) / ry
    theta1 = _angle(1.0, 0.0, vx0, vy0)
    dtheta = _angle(vx0, vy0, vx1, vy1)
    if not sweep and dtheta > 0:
        dtheta -= 2.0 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2.0 * math.pi

    out: list[Pt2] = []
    for i in range(1, steps + 1):
        ang = theta1 + dtheta * (i / steps)
        ex = rx * math.cos(ang)
        ey = ry * math.sin(ang)
        out.append((c_phi * ex - s_phi * ey + cx, s_phi * ex + c_phi * ey + cy))
    return out


def parse_svg_path(d: str) -> list[tuple[list[Pt2], bool]]:
    """Parse an SVG ``d`` attribute into ``[(points, closed), ...]`` subpaths."""
    tokens = _PATH_TOKEN_RE.findall(d)
    subpaths: list[tuple[list[Pt2], bool]] = []
    cur_pts: list[Pt2] = []
    cur: Pt2 = (0.0, 0.0)
    start: Pt2 = (0.0, 0.0)
    last_ctrl: Pt2 | None = None
    last_cmd = ""
    i = 0
    cmd = ""

    def _is_cmd(tok: str) -> bool:
        return len(tok) == 1 and tok.isalpha()

    def _has_nums(count: int) -> bool:
        if i + count > len(tokens):
            return False
        return not any(_is_cmd(tokens[i + k]) for k in range(count))

    def _next_num() -> float:
        nonlocal i
        val = float(tokens[i])
        i += 1
        return val

    while i < len(tokens):
        if _is_cmd(tokens[i]):
            cmd = tokens[i]
            i += 1
        elif not cmd:
            break

        if cmd in ("M", "m"):
            if cur_pts:
                subpaths.append((cur_pts, False))
                cur_pts = []
            if not _has_nums(2):
                break
            x, y = _next_num(), _next_num()
            if cmd == "m":
                x, y = cur[0] + x, cur[1] + y
            cur = (x, y)
            start = cur
            cur_pts = [cur]
            last_ctrl = None
            last_cmd = cmd
            # Subsequent coordinate pairs after M/m are implicit L/l
            cmd = "L" if cmd == "M" else "l"
        elif cmd in ("L", "l"):
            if not _has_nums(2):
                break
            x, y = _next_num(), _next_num()
            if cmd == "l":
                x, y = cur[0] + x, cur[1] + y
            cur = (x, y)
            cur_pts.append(cur)
            last_ctrl = None
            last_cmd = cmd
        elif cmd in ("H", "h"):
            if not _has_nums(1):
                break
            x = _next_num()
            if cmd == "h":
                x += cur[0]
            cur = (x, cur[1])
            cur_pts.append(cur)
            last_ctrl = None
            last_cmd = cmd
        elif cmd in ("V", "v"):
            if not _has_nums(1):
                break
            y = _next_num()
            if cmd == "v":
                y += cur[1]
            cur = (cur[0], y)
            cur_pts.append(cur)
            last_ctrl = None
            last_cmd = cmd
        elif cmd in ("C", "c"):
            if not _has_nums(6):
                break
            x1, y1 = _next_num(), _next_num()
            x2, y2 = _next_num(), _next_num()
            x, y = _next_num(), _next_num()
            if cmd == "c":
                x1, y1 = cur[0] + x1, cur[1] + y1
                x2, y2 = cur[0] + x2, cur[1] + y2
                x, y = cur[0] + x, cur[1] + y
            cur_pts.extend(_sample_cubic(cur, (x1, y1), (x2, y2), (x, y)))
            last_ctrl = (x2, y2)
            cur = (x, y)
            last_cmd = cmd
        elif cmd in ("S", "s"):
            if not _has_nums(4):
                break
            x2, y2 = _next_num(), _next_num()
            x, y = _next_num(), _next_num()
            if cmd == "s":
                x2, y2 = cur[0] + x2, cur[1] + y2
                x, y = cur[0] + x, cur[1] + y
            if last_cmd in ("C", "c", "S", "s") and last_ctrl is not None:
                x1 = 2.0 * cur[0] - last_ctrl[0]
                y1 = 2.0 * cur[1] - last_ctrl[1]
            else:
                x1, y1 = cur
            cur_pts.extend(_sample_cubic(cur, (x1, y1), (x2, y2), (x, y)))
            last_ctrl = (x2, y2)
            cur = (x, y)
            last_cmd = cmd
        elif cmd in ("Q", "q"):
            if not _has_nums(4):
                break
            x1, y1 = _next_num(), _next_num()
            x, y = _next_num(), _next_num()
            if cmd == "q":
                x1, y1 = cur[0] + x1, cur[1] + y1
                x, y = cur[0] + x, cur[1] + y
            cur_pts.extend(_sample_quad(cur, (x1, y1), (x, y)))
            last_ctrl = (x1, y1)
            cur = (x, y)
            last_cmd = cmd
        elif cmd in ("T", "t"):
            if not _has_nums(2):
                break
            x, y = _next_num(), _next_num()
            if cmd == "t":
                x, y = cur[0] + x, cur[1] + y
            if last_cmd in ("Q", "q", "T", "t") and last_ctrl is not None:
                x1 = 2.0 * cur[0] - last_ctrl[0]
                y1 = 2.0 * cur[1] - last_ctrl[1]
            else:
                x1, y1 = cur
            cur_pts.extend(_sample_quad(cur, (x1, y1), (x, y)))
            last_ctrl = (x1, y1)
            cur = (x, y)
            last_cmd = cmd
        elif cmd in ("A", "a"):
            if not _has_nums(7):
                break
            rx, ry = _next_num(), _next_num()
            rot = _next_num()
            large = _next_num() != 0.0
            sweep = _next_num() != 0.0
            x, y = _next_num(), _next_num()
            if cmd == "a":
                x, y = cur[0] + x, cur[1] + y
            cur_pts.extend(_sample_arc(cur, rx, ry, rot, large, sweep, (x, y)))
            cur = (x, y)
            last_ctrl = None
            last_cmd = cmd
        elif cmd in ("Z", "z"):
            if cur_pts:
                subpaths.append((cur_pts, True))
                cur_pts = []
            cur = start
            last_ctrl = None
            last_cmd = cmd
            cmd = ""
        else:
            break

    if cur_pts:
        subpaths.append((cur_pts, False))
    return subpaths


# ---------------------------------------------------------------------------
# Shape extraction from SVG XML tree
# ---------------------------------------------------------------------------
def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _parse_points_attr(raw: str) -> list[Pt2]:
    nums = [float(v) for v in _NUM_RE.findall(raw)]
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]


def _rounded_rect_pts(
    x: float, y: float, w: float, h: float, rx: float, ry: float
) -> list[Pt2]:
    rx = min(rx, w * 0.5)
    ry = min(ry, h * 0.5)
    if rx <= 1e-4 or ry <= 1e-4:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    pts: list[Pt2] = []
    corners = (
        (x + w - rx, y + ry, -math.pi * 0.5, 0.0),
        (x + w - rx, y + h - ry, 0.0, math.pi * 0.5),
        (x + rx, y + h - ry, math.pi * 0.5, math.pi),
        (x + rx, y + ry, math.pi, math.pi * 1.5),
    )
    for cx, cy, a0, a1 in corners:
        for k in range(7):
            ang = a0 + (a1 - a0) * (k / 6.0)
            pts.append((cx + rx * math.cos(ang), cy + ry * math.sin(ang)))
    return pts


def _ellipse_pts(
    cx: float, cy: float, rx: float, ry: float, segs: int = 44
) -> list[Pt2]:
    return [
        (
            cx + rx * math.cos(2.0 * math.pi * i / segs),
            cy + ry * math.sin(2.0 * math.pi * i / segs),
        )
        for i in range(segs)
    ]


def _extract_viewbox(root: ET.Element) -> tuple[float, float, float, float]:
    vb = root.attrib.get("viewBox") or root.attrib.get("viewbox")
    if vb:
        nums = [float(v) for v in _NUM_RE.findall(vb)]
        if len(nums) == 4 and nums[2] > 0 and nums[3] > 0:
            return (nums[0], nums[1], nums[2], nums[3])
    w = _parse_float(root.attrib.get("width"), 100.0)
    h = _parse_float(root.attrib.get("height"), 100.0)
    return (0.0, 0.0, max(1.0, w), max(1.0, h))


def _collect_primitives(
    elem: ET.Element,
    mat: Mat2D,
    parent_style: dict[str, str],
    out: list[dict[str, Any]],
) -> None:
    tag = _local_tag(elem.tag)
    if tag in ("defs", "script", "style", "metadata", "title", "desc", "foreignobject"):
        return

    style = _parse_style_dict(elem, parent_style)
    cur_mat = _mat_mul(mat, _parse_transform(elem.attrib.get("transform")))

    if tag in ("svg", "g", "a"):
        for child in elem:
            _collect_primitives(child, cur_mat, style, out)
        return

    fill = _parse_svg_color(style.get("fill", "#FFFFFF"))
    stroke = _parse_svg_color(style.get("stroke"))
    stroke_w = max(0.5, _parse_float(style.get("stroke-width"), 1.5))
    base_op = _parse_float(style.get("opacity"), 1.0)
    fill_op = base_op * _parse_float(style.get("fill-opacity"), 1.0)
    stroke_op = base_op * _parse_float(style.get("stroke-opacity"), 1.0)

    def _push_poly(pts: list[Pt2], closed: bool) -> None:
        if len(pts) < 2:
            return
        tpts = [_apply_mat(cur_mat, px, py) for px, py in pts]
        out.append(
            {
                "kind": "poly",
                "points": tpts,
                "closed": closed,
                "fill": fill if closed else None,
                "stroke": stroke,
                "stroke_width": stroke_w,
                "fill_opacity": fill_op,
                "stroke_opacity": stroke_op,
            }
        )

    if tag == "rect":
        x = _parse_float(elem.attrib.get("x"), 0.0)
        y = _parse_float(elem.attrib.get("y"), 0.0)
        w = _parse_float(elem.attrib.get("width"), 0.0)
        h = _parse_float(elem.attrib.get("height"), 0.0)
        rx = _parse_float(elem.attrib.get("rx"), 0.0)
        ry = _parse_float(elem.attrib.get("ry"), rx)
        if w > 0 and h > 0:
            _push_poly(_rounded_rect_pts(x, y, w, h, rx, ry), True)
    elif tag == "circle":
        cx = _parse_float(elem.attrib.get("cx"), 0.0)
        cy = _parse_float(elem.attrib.get("cy"), 0.0)
        r = _parse_float(elem.attrib.get("r"), 0.0)
        if r > 0:
            _push_poly(_ellipse_pts(cx, cy, r, r), True)
    elif tag == "ellipse":
        cx = _parse_float(elem.attrib.get("cx"), 0.0)
        cy = _parse_float(elem.attrib.get("cy"), 0.0)
        rx = _parse_float(elem.attrib.get("rx"), 0.0)
        ry = _parse_float(elem.attrib.get("ry"), 0.0)
        if rx > 0 and ry > 0:
            _push_poly(_ellipse_pts(cx, cy, rx, ry), True)
    elif tag == "line":
        x1 = _parse_float(elem.attrib.get("x1"), 0.0)
        y1 = _parse_float(elem.attrib.get("y1"), 0.0)
        x2 = _parse_float(elem.attrib.get("x2"), 0.0)
        y2 = _parse_float(elem.attrib.get("y2"), 0.0)
        _push_poly([(x1, y1), (x2, y2)], False)
    elif tag == "polyline":
        _push_poly(_parse_points_attr(elem.attrib.get("points", "")), False)
    elif tag == "polygon":
        _push_poly(_parse_points_attr(elem.attrib.get("points", "")), True)
    elif tag == "path":
        d = elem.attrib.get("d", "")
        for pts, closed in parse_svg_path(d):
            _push_poly(pts, closed)
    elif tag == "text":
        txt = "".join(elem.itertext()).strip()
        if txt:
            tx = _parse_float(elem.attrib.get("x"), 0.0)
            ty = _parse_float(elem.attrib.get("y"), 0.0)
            pos = _apply_mat(cur_mat, tx, ty)
            # Estimate uniform scale from matrix for font size
            scale_est = math.hypot(cur_mat[0], cur_mat[1])
            font_sz = _parse_float(style.get("font-size"), 14.0) * max(scale_est, 0.1)
            anchor_map = {"start": "ls", "middle": "ms", "end": "rs"}
            anchor = anchor_map.get(style.get("text-anchor", "start").lower(), "ls")
            out.append(
                {
                    "kind": "text",
                    "pos": pos,
                    "text": txt,
                    "size": font_sz,
                    "fill": fill or "#FFFFFF",
                    "opacity": fill_op,
                    "anchor": anchor,
                }
            )


def _trim_polyline(pts: list[Pt2], frac: float) -> list[Pt2]:
    """Return the prefix of polyline ``pts`` covering ``frac`` in [0, 1] of total arc length."""
    if frac <= 0.0 or len(pts) < 2:
        return []
    if frac >= 1.0:
        return pts
    seg_lens: list[float] = []
    total = 0.0
    for i in range(len(pts) - 1):
        d = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        seg_lens.append(d)
        total += d
    if total <= 1e-6:
        return pts
    target = total * frac
    acc = 0.0
    out: list[Pt2] = [pts[0]]
    for i, d in enumerate(seg_lens):
        if acc + d >= target:
            rem = (target - acc) / max(d, 1e-9)
            x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * rem
            y = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * rem
            out.append((x, y))
            break
        acc += d
        out.append(pts[i + 1])
    return out


# ---------------------------------------------------------------------------
# Optional external rasterizer (resvg / rsvg-convert / headless Chromium SVG 2.0)
# ---------------------------------------------------------------------------
_SVG_RASTER_SCRIPT = (
    Path(__file__).resolve().parent.parent / "threejs" / "svg_raster.mjs"
)


def _find_chromium_svg_runner() -> tuple[str, str] | None:
    if not _SVG_RASTER_SCRIPT.is_file():
        return None
    node_bin = shutil.which("node")
    if not node_bin:
        return None
    for name in (
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
    ):
        browser = shutil.which(name)
        if browser:
            return (node_bin, browser)
    return None


def _rasterize_external(
    svg_text: str, bw: int, bh: int, *, allow_browser: bool = True
) -> Image.Image | None:
    digest = hashlib.sha256(svg_text.encode("utf-8")).hexdigest()[:16]
    cache_key = (digest, bw, bh)
    cached = _RASTER_CACHE.get(cache_key)
    if cached is not None:
        _RASTER_CACHE.move_to_end(cache_key)
        return cached

    tool = shutil.which("resvg") or shutil.which("rsvg-convert")
    browser_pair = _find_chromium_svg_runner() if (not tool and allow_browser) else None
    if not tool and browser_pair is None:
        return None

    try:
        with tempfile.TemporaryDirectory(prefix="sm_svg_") as td:
            in_svg = Path(td) / "in.svg"
            out_png = Path(td) / "out.png"
            in_svg.write_text(svg_text, encoding="utf-8")
            if tool:
                tool_name = Path(tool).name
                if tool_name == "resvg":
                    argv = [
                        tool,
                        "--width",
                        str(bw),
                        "--height",
                        str(bh),
                        str(in_svg),
                        str(out_png),
                    ]
                else:
                    argv = [
                        tool,
                        "-w",
                        str(bw),
                        "-h",
                        str(bh),
                        "-o",
                        str(out_png),
                        str(in_svg),
                    ]
            else:
                assert browser_pair is not None
                node_bin, browser_bin = browser_pair
                argv = [
                    node_bin,
                    str(_SVG_RASTER_SCRIPT),
                    "--input",
                    str(in_svg),
                    "--output",
                    str(out_png),
                    "--width",
                    str(bw),
                    "--height",
                    str(bh),
                    "--browser",
                    browser_bin,
                ]
            res = subprocess.run(argv, check=False, timeout=20, capture_output=True)
            if res.returncode != 0 or not out_png.is_file():
                return None
            with Image.open(out_png) as im:
                rgba: Image.Image = im.convert("RGBA")
                rgba.load()
            _lru_set(_RASTER_CACHE, cache_key, rgba)
            return rgba
    except Exception:  # noqa: BLE001 — fall back to built-in pure-Python renderer
        return None


def _load_svg_text(el: dict[str, Any], ctx: ElementContext) -> str | None:
    inline = el.get("svg")
    if isinstance(inline, str) and inline.strip():
        return inline
    src = el.get("src")
    if not src:
        print("svg element missing 'svg' or 'src'", file=sys.stderr)
        return None
    path = Path(str(src))
    if not path.is_absolute():
        path = Path(ctx.base_dir or ".") / path
    if not path.is_file():
        print(f"svg element: src not found: {path}", file=sys.stderr)
        return None
    try:
        resolved = path.resolve()
        key = (str(resolved), resolved.stat().st_mtime_ns)
        cached = _FILE_TEXT_CACHE.get(key)
        if cached is not None:
            _FILE_TEXT_CACHE.move_to_end(key)
            return cached
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"svg element: cannot read {path}: {exc}", file=sys.stderr)
        return None
    _lru_set(_FILE_TEXT_CACHE, key, text)
    return text


def _paste_contact_shadow(
    cv: SupersampledCanvas,
    plate: Image.Image,
    paste_xy: tuple[int, int],
    el: dict[str, Any],
) -> None:
    """Soft offset shadow under a rasterised SVG (``style_match: true``).

    Grounds flat vector art on a photographic/3D plate so it reads as sitting in
    the scene instead of pasted on it. ``shadow_color`` (default near-black),
    ``shadow_opacity`` (0-1, default 0.35) and ``shadow_blur`` (fraction of the
    plate's longest side, default 0.02) tune it.
    """
    opacity = max(0.0, min(1.0, float(el.get("shadow_opacity", 0.35))))
    if opacity <= 0.0:
        return
    blur = max(1.0, float(el.get("shadow_blur", 0.02)) * max(plate.size))
    color = rgb(str(el.get("shadow_color", "#000000")))
    alpha = plate.getchannel("A")
    pad = round(blur * 3)
    canvas = Image.new("L", (plate.width + 2 * pad, plate.height + 2 * pad), 0)
    canvas.paste(alpha, (pad, pad))
    soft = canvas.filter(ImageFilter.GaussianBlur(blur)).point(
        lambda px: int(px * opacity)
    )
    layer = Image.new("RGBA", canvas.size, (*color, 0))
    layer.putalpha(soft)
    dy = round(blur * 0.8)
    cv.image.paste(layer, (paste_xy[0] - pad, paste_xy[1] - pad + dy), layer)


def paint_svg(cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext) -> None:
    """Paint an inline or file-backed SVG into ``box`` with optional animation and glow."""
    svg_text = _load_svg_text(el, ctx)
    if not svg_text:
        return
    if _UNSAFE_XML_RE.search(svg_text):
        print(
            "svg element: rejected unsafe DOCTYPE/ENTITY declaration", file=sys.stderr
        )
        return

    raw_box = el.get("box", [0, 0, ctx.width, ctx.height])
    if not isinstance(raw_box, (list, tuple)) or len(raw_box) != 4:
        raw_box = [0, 0, ctx.width, ctx.height]
    x0, y0, x1, y1 = (float(v) for v in raw_box)
    box_w, box_h = x1 - x0, y1 - y0
    if box_w <= 0 or box_h <= 0:
        return

    reveal_mode = str(el.get("reveal", "none")).lower()
    glow = bool(el.get("glow", False))
    tint = _parse_svg_color(str(el["tint"])) if el.get("tint") else None
    opacity = max(0.0, min(1.0, float(el.get("opacity", 1.0))))
    rot0 = float(el.get("rotation_deg", 0.0))
    rot1 = float(el.get("rotation_end_deg", rot0))
    sc0 = float(el.get("scale_start", 1.0))
    sc1 = float(el.get("scale_end", sc0))
    render_mode = str(el.get("render_mode", "auto")).lower()

    t_ease = ease_in_out_cubic(ctx.t)
    anim_scale = sc0 + (sc1 - sc0) * t_ease
    anim_rot = rot0 + (rot1 - rot0) * t_ease

    fade_alpha = 1.0
    draw_progress = 1.0
    if reveal_mode == "fade":
        fade_in = max(0.05, float(el.get("fade_in_sec", 0.5)))
        fade_alpha = ease_out_expo(_smoothstep(0.0, fade_in, ctx.local_time))
    elif reveal_mode == "pop":
        pop_sec = max(0.05, float(el.get("fade_in_sec", 0.55)))
        anim_scale *= max(0.01, spring_pop(_smoothstep(0.0, pop_sec, ctx.local_time)))
    elif reveal_mode == "draw":
        draw_progress = ease_out_expo(_smoothstep(0.0, 0.88, ctx.t))

    total_opacity = opacity * fade_alpha
    if total_opacity <= 0.01:
        return

    # Fast path: optional native SVG 2.0 rasterizer (resvg / rsvg-convert / Chromium)
    # Supports pop/fade/scale/rotation AND optional canvas bloom (glow: true)!
    if (
        render_mode in ("auto", "raster", "browser")
        and reveal_mode != "draw"
        and tint is None
    ):
        bw = max(1, round(box_w * cv.scale))
        bh = max(1, round(box_h * cv.scale))
        raster = _rasterize_external(
            svg_text, bw, bh, allow_browser=(render_mode != "vector")
        )
        if raster is not None:
            plate = raster
            cam_zoom = cv._z if cv.camera else 1.0
            eff_scale = anim_scale * cam_zoom
            if abs(eff_scale - 1.0) > 1e-3:
                sw_px = max(1, round(plate.width * eff_scale))
                sh_px = max(1, round(plate.height * eff_scale))
                plate = plate.resize((sw_px, sh_px), Image.Resampling.LANCZOS)
            if abs(anim_rot) > 1e-3:
                plate = plate.rotate(
                    -anim_rot, resample=Image.Resampling.BICUBIC, expand=True
                )
            if total_opacity < 0.999:
                r_ch, g_ch, b_ch, a_ch = plate.split()
                a_ch = a_ch.point(lambda px: int(px * total_opacity))
                plate = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))
            cx_f, cy_f = cv.draw_._tp(x0 + box_w * 0.5, y0 + box_h * 0.5)
            cx_px = round(cx_f)
            cy_px = round(cy_f)
            paste_xy = (cx_px - plate.width // 2, cy_px - plate.height // 2)
            if el.get("style_match"):
                _paste_contact_shadow(cv, plate, paste_xy, el)
            cv.image.paste(plate, paste_xy, plate)
            if glow:
                cv.bloom_image.paste(plate.convert("RGB"), paste_xy, plate)
            return

    # Pure-Python stdlib SVG vector engine (always available; parsed doc cached)
    doc_key = hashlib.sha256(svg_text.encode("utf-8")).hexdigest()[:16]
    cached_doc = _SVG_DOC_CACHE.get(doc_key)
    if cached_doc is not None:
        _SVG_DOC_CACHE.move_to_end(doc_key)
        (vx, vy, vw, vh), local_primitives = cached_doc
    else:
        try:
            root = ET.fromstring(svg_text)
        except ET.ParseError as exc:
            print(f"svg element: XML parse error: {exc}", file=sys.stderr)
            return
        vx, vy, vw, vh = _extract_viewbox(root)
        local_primitives = []
        _collect_primitives(root, _IDENTITY, {}, local_primitives)
        _lru_set(_SVG_DOC_CACHE, doc_key, ((vx, vy, vw, vh), local_primitives))

    if not local_primitives:
        return

    fit = str(el.get("fit", "contain")).lower()
    if fit == "stretch":
        sx, sy = box_w / vw, box_h / vh
    elif fit == "cover":
        s = max(box_w / vw, box_h / vh)
        sx, sy = s, s
    else:  # contain
        s = min(box_w / vw, box_h / vh)
        sx, sy = s, s

    ox = x0 + (box_w - vw * sx) * 0.5
    oy = y0 + (box_h - vh * sy) * 0.5
    base_mat: Mat2D = (sx, 0.0, 0.0, sy, ox - vx * sx, oy - vy * sy)

    # Apply optional center scale/rotation
    if abs(anim_scale - 1.0) > 1e-4 or abs(anim_rot) > 1e-4:
        cx, cy = x0 + box_w * 0.5, y0 + box_h * 0.5
        rad = math.radians(anim_rot)
        cs, sn = math.cos(rad) * anim_scale, math.sin(rad) * anim_scale
        xform = _mat_mul(
            (1.0, 0.0, 0.0, 1.0, cx, cy),
            _mat_mul((cs, sn, -sn, cs, 0.0, 0.0), (1.0, 0.0, 0.0, 1.0, -cx, -cy)),
        )
        base_mat = _mat_mul(xform, base_mat)

    scale_est = math.hypot(base_mat[0], base_mat[1])
    primitives: list[dict[str, Any]] = []
    for lp in local_primitives:
        if lp["kind"] == "text":
            tx, ty = lp["pos"]
            primitives.append(
                {
                    **lp,
                    "pos": _apply_mat(base_mat, tx, ty),
                    "size": float(lp["size"]) * max(scale_est, 0.1),
                }
            )
        else:
            primitives.append(
                {
                    **lp,
                    "points": [_apply_mat(base_mat, px, py) for px, py in lp["points"]],
                }
            )

    avg_scale = (sx + sy) * 0.5 * abs(anim_scale)
    stroke_scale = float(el.get("stroke_scale", 1.0))

    for prim in primitives:
        if prim["kind"] == "text":
            fill_hex = tint or str(prim["fill"])
            eff_op = total_opacity * float(prim["opacity"])
            if reveal_mode == "draw":
                eff_op *= _smoothstep(0.55, 0.95, draw_progress)
            if eff_op <= 0.02:
                continue
            t_pos = prim["pos"]
            t_text = str(prim["text"])
            t_size = max(8.0, float(prim["size"]))
            t_fill = fill_hex
            t_anchor = str(prim["anchor"])
            _draw_translucent(
                cv,
                lambda d, sh, pos=t_pos, text=t_text, size=t_size, fill=t_fill, anchor=t_anchor: (
                    d.text(
                        (pos[0] - sh[0], pos[1] - sh[1]),
                        text,
                        size=size,
                        fill=fill,
                        anchor=anchor,
                    )
                ),
                eff_op,
            )
            continue

        pts: list[Pt2] = prim["points"]
        closed = bool(prim["closed"])
        fill_raw = prim["fill"]
        stroke_raw = prim["stroke"]
        fill_hex = tint if (tint and fill_raw) else fill_raw
        stroke_hex = tint if (tint and stroke_raw) else stroke_raw
        sw = max(1.0, float(prim["stroke_width"]) * avg_scale * stroke_scale)
        fill_alpha = total_opacity * float(prim["fill_opacity"])
        stroke_alpha = total_opacity * float(prim["stroke_opacity"])

        if reveal_mode == "draw":
            # Progressive stroke draw; fills fade in smoothly after 60% stroke
            draw_pts = pts + [pts[0]] if closed else pts
            trimmed = _trim_polyline(draw_pts, draw_progress)
            fill_reveal = _smoothstep(0.58, 1.0, draw_progress)
            if fill_hex and closed and fill_reveal > 0.02:
                _draw_translucent(
                    cv,
                    lambda d, sh, poly=pts, fill=fill_hex: d.polygon(
                        _shift_points(poly, sh), fill=fill
                    ),
                    fill_alpha * fill_reveal,
                    points=pts,
                )
            outline_col = stroke_hex or fill_hex
            if outline_col and len(trimmed) >= 2:
                _draw_translucent(
                    cv,
                    lambda d, sh, line=trimmed, col=outline_col, width=sw: d.polyline(
                        _shift_points(line, sh), col, width=width
                    ),
                    stroke_alpha,
                    points=trimmed,
                    pad_px=sw,
                )
                if glow:
                    cv.bloom_polyline(
                        trimmed,
                        _blend_opacity(str(outline_col), stroke_alpha),
                        width=max(1.5, sw * 1.15),
                    )
        else:
            if closed and fill_hex:
                _draw_translucent(
                    cv,
                    lambda d, sh, poly=pts, fill=fill_hex: d.polygon(
                        _shift_points(poly, sh), fill=fill
                    ),
                    fill_alpha,
                    points=pts,
                )
                if stroke_hex:
                    stroke_pts = pts + [pts[0]]
                    _draw_translucent(
                        cv,
                        lambda d, sh, line=stroke_pts, col=stroke_hex, width=sw: (
                            d.polyline(_shift_points(line, sh), col, width=width)
                        ),
                        stroke_alpha,
                        points=stroke_pts,
                        pad_px=sw,
                    )
                if glow:
                    cv.bloom_polygon(
                        pts,
                        outline=_blend_opacity(
                            str(stroke_hex or fill_hex), stroke_alpha or fill_alpha
                        ),
                    )
            elif stroke_hex:
                draw_pts = pts + [pts[0]] if closed else pts
                _draw_translucent(
                    cv,
                    lambda d, sh, line=draw_pts, col=stroke_hex, width=sw: d.polyline(
                        _shift_points(line, sh), col, width=width
                    ),
                    stroke_alpha,
                    points=draw_pts,
                    pad_px=sw,
                )
                if glow:
                    cv.bloom_polyline(
                        draw_pts,
                        _blend_opacity(str(stroke_hex), stroke_alpha),
                        width=max(1.5, sw * 1.15),
                    )
