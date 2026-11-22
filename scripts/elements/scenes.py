"""elements/scenes.py — full-frame backdrop painters (solid, pastel gradients, bokeh)."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from canvas import SupersampledCanvas, parse_color, rgb
from PIL import Image, ImageDraw, ImageFilter

from elements._shared import ElementContext


def _lerp_rgb(stops: list[tuple[int, int, int]], u: float) -> tuple[int, int, int]:
    u = max(0.0, min(1.0, u))
    if len(stops) == 1:
        return stops[0]
    scaled = u * (len(stops) - 1)
    idx = min(len(stops) - 2, int(scaled))
    frac = scaled - idx
    c0, c1 = stops[idx], stops[idx + 1]
    return (
        round(c0[0] + (c1[0] - c0[0]) * frac),
        round(c0[1] + (c1[1] - c0[1]) * frac),
        round(c0[2] + (c1[2] - c0[2]) * frac),
    )


@lru_cache(maxsize=32)
def _render_gradient(
    size: tuple[int, int], colors: tuple[str, ...], direction: str
) -> Image.Image:
    stops = [rgb(c) for c in colors]
    w, h = size
    if direction == "horizontal":
        strip = Image.new("RGB", (64, 1))
        for x in range(64):
            strip.putpixel((x, 0), _lerp_rgb(stops, x / 63.0))
        return strip.resize((w, h), Image.Resampling.BILINEAR)
    if direction == "radial":
        grid = Image.new("RGB", (64, 64))
        for y in range(64):
            dy = (y - 31.5) / 31.5
            for x in range(64):
                dx = (x - 31.5) / 31.5
                r = min(1.0, math.hypot(dx, dy) / 1.25)
                grid.putpixel((x, y), _lerp_rgb(stops, r))
        return grid.resize((w, h), Image.Resampling.BILINEAR)
    if direction == "diagonal":
        grid = Image.new("RGB", (64, 64))
        for y in range(64):
            for x in range(64):
                u = (x + y) / 126.0
                grid.putpixel((x, y), _lerp_rgb(stops, u))
        return grid.resize((w, h), Image.Resampling.BILINEAR)
    # default vertical
    strip = Image.new("RGB", (1, 64))
    for y in range(64):
        strip.putpixel((0, y), _lerp_rgb(stops, y / 63.0))
    return strip.resize((w, h), Image.Resampling.BILINEAR)


@lru_cache(maxsize=32)
def _vignette_mask(size: tuple[int, int], strength: float) -> Image.Image:
    """Corner-fade mask resized to the canvas — time-independent: cacheable."""
    vw, vh = 64, 64
    vmask = Image.new("L", (vw, vh), 0)
    for y in range(vh):
        dy = (y - (vh - 1) * 0.5) / ((vh - 1) * 0.5)
        for x in range(vw):
            dx = (x - (vw - 1) * 0.5) / ((vw - 1) * 0.5)
            dist = math.hypot(dx, dy)
            edge = max(0.0, min(1.0, (dist - 0.55) / 0.85))
            vmask.putpixel((x, y), round(255 * strength * edge * edge))
    return vmask.resize(size, Image.Resampling.BILINEAR)


def paint_background(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    gradient = el.get("gradient")
    if isinstance(gradient, list) and len(gradient) >= 2:
        direction = str(el.get("direction", "vertical")).lower()
        grad_img = _render_gradient(
            cv.image.size, tuple(str(c) for c in gradient), direction
        )
        cv.image.paste(grad_img, (0, 0))
    else:
        color = parse_color(el.get("color", "#000000"))
        big = max(ctx.width, ctx.height) * 4
        cv.draw_.rectangle([-big, -big, big, big], fill=color)

    soft_glows = el.get("soft_glows")
    if isinstance(soft_glows, list) and soft_glows:
        # Render dreamy atmospheric watercolor/bokeh orbs at quarter-res for speed & silkiness
        gw = max(64, cv.width // 2)
        gh = max(64, cv.height // 2)
        for orb in soft_glows:
            if not isinstance(orb, dict):
                continue
            ox = float(orb.get("x", 0.5))
            oy = float(orb.get("y", 0.5))
            dx = float(orb.get("drift_x", 0.0)) * math.sin(ctx.t * math.pi)
            dy = float(orb.get("drift_y", 0.0)) * math.sin(ctx.t * math.pi)
            cx = (ox + dx) * gw
            cy = (oy + dy) * gh
            rad = float(orb.get("radius", 0.35)) * max(gw, gh)
            alpha = max(0.0, min(1.0, float(orb.get("alpha", 0.35))))
            col = rgb(orb.get("color", "#F6D8C8"))
            mask = Image.new("L", (gw, gh), 0)
            ImageDraw.Draw(mask).ellipse(
                (cx - rad, cy - rad, cx + rad, cy + rad),
                fill=round(255 * alpha),
            )
            blur_r = max(4.0, rad * 0.45)
            mask = mask.filter(ImageFilter.GaussianBlur(blur_r)).resize(
                cv.image.size, Image.Resampling.BILINEAR
            )
            tint = Image.new("RGB", cv.image.size, col)
            cv.image.paste(tint, (0, 0), mask)

    vignette_strength = float(el.get("vignette_strength", 0.0))
    if vignette_strength > 0.001:
        v_col = rgb(el.get("vignette_color", "#DFCFC0"))
        vmask = _vignette_mask(cv.image.size, vignette_strength)
        cv.image.paste(Image.new("RGB", cv.image.size, v_col), (0, 0), vmask)


def paint_grid(cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext) -> None:
    spacing = float(el.get("spacing", 90))
    if not math.isfinite(spacing) or spacing <= 0.0:
        return
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
