#!/usr/bin/env python3
"""hybrid_compositor.py — 3D→2D motion-tracked HUD compositor.

Consumes screen-tracked anchors (from ``software_3d_projection`` or
Blender's ``anchor_tracks.json``) and paints reticles, 45° elbow leader
lines and frosted glass telemetry cards placed by the SAT layout solver.
Design-space pixels; pre-blended slate tones (no alpha compositing —
ImageDraw cannot blend, so translucency is baked into opaque hex).
"""

from __future__ import annotations

from typing import Any

from canvas import SupersampledCanvas, get_font
from easings import spring_pop
from layout_solver import LayoutBox, SATLayoutSolver

_HUD_ACCENT = "#38BDF8"
_LABEL_FILL = "#E2E8F0"
_CARD_FILL = "#0C1220"  # pre-blended dark slate card on the #050811 stage
_HUD_FILL = "#0B1220"  # HUD bar fill
_CARD_H = 84.0
_CARD_RADIUS = 12.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else (min(value, hi))


def composite_3d_tracked_hud(
    canvas: SupersampledCanvas,
    tracked_anchors: list[dict[str, Any]],
    scene_title: str,
    t_norm: float,
    aspect_ratio: str = "16:9",
) -> None:
    """Paint reticles + elbow leaders + telemetry cards for tracked anchors.

    ``tracked_anchors`` is a list of dicts with ``u``/``v`` (normalized,
    top-left origin), ``visible``, ``label``, ``metric`` and ``accent_hex``.
    ``t_norm`` drives the per-card spring-pop reveal. Returns ``None``.
    """
    w, h = canvas.width, canvas.height

    hud_font = get_font(21, mono=True)
    label_font = get_font(18, mono=False)
    metric_font = get_font(22, mono=True)

    title = str(scene_title)
    title_w = hud_font.getlength(title)

    # 9:16 has no room for the 16:9 peripheral gutters: place a full-width
    # header inside the Shorts safe zone and dock cards in a two-column band
    # directly above the central 3D stage (otherwise the solver strands cards
    # at the canvas edges and the leader lines cross the whole frame).
    vertical = aspect_ratio == "9:16"
    if vertical:
        hud_box = (84.0, 226.0, w - 84.0, 302.0)
        card_h = _CARD_H
        locked_boxes = [
            LayoutBox("hud_header", *hud_box, locked=True, padding=12.0),
            LayoutBox(
                "center_3d_repulsor",
                84.0,
                820.0,
                w - 84.0,
                1400.0,
                locked=True,
                padding=16.0,
            ),
        ]
    else:
        hud_w = max(620.0, title_w + 52.0)
        hud_box = (96.0, 42.0, 96.0 + hud_w, 100.0)
        card_h = _CARD_H
        locked_boxes = [
            LayoutBox("hud_header", *hud_box, locked=True, padding=16.0),
            LayoutBox(
                "center_3d_repulsor",
                w * 0.29,
                h * 0.18,
                w * 0.71,
                h * 0.78,
                locked=True,
                padding=20.0,
            ),
        ]

    visible_anchors = [a for a in tracked_anchors if a.get("visible", True)]

    # Measure cards and seed free (non-locked) layout boxes.
    card_boxes = []
    for idx, anchor in enumerate(visible_anchors):
        ax = anchor["u"] * w
        ay = anchor["v"] * h
        label = str(anchor.get("label", anchor.get("anchor_id", f"A{idx}")))
        metric = str(anchor.get("metric", ""))
        label_w = label_font.getlength(label)
        metric_w = metric_font.getlength(metric)
        if vertical:
            card_w = min(440.0, max(340.0, max(label_w, metric_w) + 44.0))
            cx0 = 84.0 if idx % 2 == 0 else (w - 84.0 - card_w)
            cy0 = 560.0 + (idx // 2) * (card_h + 24.0)
        else:
            card_w = max(290.0, max(label_w, metric_w) + 44.0)
            put_left = idx % 2 == 1
            cx0 = 104.0 if put_left else (w - 104.0 - card_w)
            cy0 = _clamp(ay - card_h / 2.0, 135.0, h * 0.72)
        card_boxes.append(
            LayoutBox(
                f"anchor_card_{idx}",
                cx0,
                cy0,
                cx0 + card_w,
                cy0 + card_h,
                locked=False,
                padding=18.0,
            )
        )

    solved = SATLayoutSolver.solve(
        locked_boxes + card_boxes,
        aspect_ratio=aspect_ratio,
        width=w,
        height=h,
        iterations=60,
    )

    for idx, anchor in enumerate(visible_anchors):
        appear_t = _clamp((t_norm - idx * 0.06) * 3.5, 0.0, 1.0)
        if appear_t <= 0.02:
            continue
        pop = spring_pop(appear_t)

        accent = anchor.get("accent_hex", _HUD_ACCENT)
        ax = anchor["u"] * w
        ay = anchor["v"] * h
        box = solved[f"anchor_card_{idx}"]

        dock_x = box.x1 if box.cx < w * 0.5 else box.x0
        dock_y = box.cy
        dx = dock_x - ax
        dy = dock_y - ay
        elbow_len = min(abs(dy), abs(dx) * 0.45)
        knee_x = ax + (elbow_len if dx >= 0 else -elbow_len)
        knee_y = dock_y

        # Reticle: outer ring + white-hot core, both echoed into bloom.
        r_outer = 10.5 * pop
        canvas.ellipse(
            (ax - r_outer, ay - r_outer, ax + r_outer, ay + r_outer),
            outline=accent,
            width=2.2,
        )
        canvas.bloom_ellipse(
            (ax - r_outer, ay - r_outer, ax + r_outer, ay + r_outer),
            outline=accent,
            width=2.2,
        )
        r_inner = 4.2 * pop
        canvas.ellipse(
            (ax - r_inner, ay - r_inner, ax + r_inner, ay + r_inner),
            outline=accent,
            fill="#FFFFFF",
            width=2.0,
        )
        canvas.bloom_ellipse(
            (ax - r_inner, ay - r_inner, ax + r_inner, ay + r_inner),
            outline=accent,
            width=2.0,
        )

        # 45° elbow leader: anchor → knee → card dock.
        canvas.line((ax, ay), (knee_x, knee_y), accent, width=2.4)
        canvas.line((knee_x, knee_y), (dock_x, dock_y), accent, width=2.4)
        canvas.bloom_line((ax, ay), (knee_x, knee_y), accent, width=2.4)
        canvas.bloom_line((knee_x, knee_y), (dock_x, dock_y), accent, width=2.4)

        canvas.ellipse(
            (dock_x - 4.5, dock_y - 4.5, dock_x + 4.5, dock_y + 4.5),
            fill=accent,
        )

        # Frosted-glass telemetry card (pre-blended slate — no alpha).
        canvas.rectangle(
            (box.x0, box.y0, box.x1, box.y1),
            fill=_CARD_FILL,
            outline=accent,
            width=1.6,
            radius=_CARD_RADIUS,
        )
        label = str(anchor.get("label", anchor.get("anchor_id", f"A{idx}")))
        metric = str(anchor.get("metric", ""))
        canvas.text((box.x0 + 20.0, box.y0 + 14.0), label, _LABEL_FILL, size=18.0)
        canvas.text(
            (box.x0 + 20.0, box.y0 + 44.0), metric, accent, size=22.0, mono=True
        )
        canvas.bloom_text(
            (box.x0 + 20.0, box.y0 + 44.0), metric, accent, size=22.0, mono=True
        )

    # HUD bar — painted even with zero visible anchors.
    hx0, hy0, hx1, hy1 = hud_box
    canvas.rectangle(
        (hx0, hy0, hx1, hy1),
        fill=_HUD_FILL,
        outline=_HUD_ACCENT,
        width=1.6,
        radius=10.0,
    )
    canvas.text((hx0 + 22.0, hy0 + 16.0), title, _HUD_ACCENT, size=21.0, mono=True)
