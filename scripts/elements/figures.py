"""elements/figures.py — stick-figure rig painter."""

from __future__ import annotations

from rig import draw_stick_figure

from elements._shared import ElementContext


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
