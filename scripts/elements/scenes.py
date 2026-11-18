"""elements/scenes.py — full-frame backdrop painters."""

from __future__ import annotations

from canvas import parse_color

from elements._shared import ElementContext


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
