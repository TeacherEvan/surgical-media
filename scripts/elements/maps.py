"""elements/maps.py — stylized map assets for geopolitical explainers.

Deterministic. Geography is a *vibe* of world-region clusters (not a
GeoJSON simulation), so two political-news boards share the same utility:
``paint_map`` for a stylized world map, ``paint_map_arrow`` (reuses
``leader_arrow`` for animated routes/needs), ``paint_map_callout`` for
labelled hot-spot labels with leaders. Painters accept explicit
``el["palette"]`` overrides; defaults come from style.py palette refs.

Element types: ``map``, ``map_arrow``, ``map_callout``.
"""

from __future__ import annotations

from typing import Any

from canvas import SupersampledCanvas, get_font

from elements._shared import ElementContext


def _resolve_colors(el: dict[str, Any], ctx: ElementContext) -> tuple[str, str, str]:
    """Return (ground, ink, accent) from el overrides or the style palette."""
    return (
        str(el.get("bg", el.get("ground", "#0B0F14"))),
        str(el.get("ink", el.get("text_color", "#EEF2F6"))),
        str(el.get("accent", el.get("color", "#E5484D"))),
    )


def paint_map(cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext) -> None:
    """Draw a stylized world map at ``el["box"]``.

    Regions (normalized within the box) default to a world-cluster sketch;
    override via ``el["regions"]`` = ``[{"x","y","w","h","color","label"}]``.
    """
    x0, y0, x1, y1 = (float(v) for v in el.get("box", [0, 0, ctx.width, ctx.height]))
    ground, ink, accent = _resolve_colors(el, ctx)

    default_regions: list[dict[str, Any]] = [
        {
            "x": 0.08,
            "y": 0.14,
            "w": 0.30,
            "h": 0.20,
            "color": accent,
            "label": "EUROPE",
        },
        {
            "x": 0.02,
            "y": 0.36,
            "w": 0.28,
            "h": 0.22,
            "color": accent,
            "label": "AFRICA",
        },
        {"x": 0.58, "y": 0.08, "w": 0.38, "h": 0.36, "color": accent, "label": "ASIA"},
        {
            "x": 0.55,
            "y": 0.52,
            "w": 0.40,
            "h": 0.30,
            "color": accent,
            "label": "AUSTRALIA",
        },
        {
            "x": 0.38,
            "y": 0.58,
            "w": 0.36,
            "h": 0.28,
            "color": accent,
            "label": "AMERICAS",
        },
    ]
    regions = el.get("regions") or default_regions
    if not isinstance(regions, list):
        regions = default_regions

    cv.rectangle((x0, y0, x1, y1), fill=ground, radius=18)
    font = get_font(max(12, int((y1 - y0) * 0.07)))

    for region in regions:
        if not isinstance(region, dict):
            continue
        cx0 = x0 + region["x"] * (x1 - x0) if "x" in region else x0
        cy0 = y0 + region["y"] * (y1 - y0) if "y" in region else y0
        cw = region.get("w", 0.28) * (x1 - x0)
        ch = region.get("h", 0.28) * (y1 - y0)
        cv.rectangle(
            (cx0, cy0, cx0 + cw, cy0 + ch), fill=region.get("color", accent), radius=6
        )
        label = str(region.get("label", ""))
        if label:
            t_width = font.getlength(label) * 0.7
            cv.text(
                (cx0 + cw / 2 - t_width, cy0 + ch / 2 - 6),
                label,
                ink,
                size=max(12, int((y1 - y0) * 0.07)),
                anchor="la",
            )


def paint_map_arrow(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    """Animated leader arrow across a map (reuses paint_leader_arrow)."""
    from elements.visual import paint_leader_arrow

    el = dict(el)
    if not el.get("color"):
        el["color"] = el.get("accent", "#E5484D")
    paint_leader_arrow(cv, el, ctx)


def paint_map_callout(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    """A labelled hot-spot bubble: circle marker + rounded pill + arrow tail."""
    x0, y0, x1, y1 = (float(v) for v in el.get("box", [0, 0, ctx.width, ctx.height]))
    ground, ink, accent = _resolve_colors(el, ctx)
    point = el.get("point", {"x": 0.5, "y": 0.45})
    label = str(el.get("text", el.get("label", "HOTSPOT"))).upper()
    header = str(el.get("text_color", ink))
    font = get_font(34, bold=True)

    px = x0 + float(point.get("x", 0.5)) * (x1 - x0)
    py = y0 + float(point.get("y", 0.45)) * (y1 - y0)

    # marker dot + leader line
    cv.ellipse((px - 14, py - 14, px + 14, py + 14), fill=accent)
    cv.line((px, py + 14), (px, y1 - 96), fill=accent, width=3.0)

    # callout bubble
    th = 42
    tw = font.getlength(label) * 1.5 + 56
    bx0 = min(max(px - tw / 2 + 6, x0 + 30), x1 - tw - 30)
    by0 = y1 - 96 - th - 12
    cv.rectangle(
        (bx0, by0, bx0 + tw, by0 + th), fill=ground, outline=accent, radius=8, width=2.0
    )

    # arrow tail
    bx_mid = bx0 + tw / 2
    cv.polygon(
        [
            (bx_mid - 10, by0 + th - 2),
            (bx_mid + 6, by0 + th - 2),
            (bx_mid + 2, by0 + th + 16),
        ],
        fill=accent,
    )

    # label text
    t_w = font.getlength(label)
    cv.text(
        (bx0 + tw / 2 - t_w / 2, by0 + th / 2 - 8), label, ink, size=34, anchor="mm"
    )
    header_line = str(el.get("subtitle", ""))
    if header_line:
        cv.text(
            (bx0 + 12, by0 + th - 26),
            header_line,
            header,
            size=max(12, int((y1 - y0) * 0.03)),
        )
