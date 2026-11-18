"""Pixel-level smoke tests for the 3D→2D motion-tracked HUD compositor.

Coarse presence assertions only (no golden images) — fonts drift by host.
"""

import sys
from pathlib import Path

from PIL import ImageChops

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from canvas import SupersampledCanvas
from hybrid_compositor import composite_3d_tracked_hud

W, H = 640, 360
BACKGROUND = "#050811"


def _synthetic_anchors():
    return [
        {
            "anchor_id": "a1",
            "label": "UPLINK",
            "metric": "-71 dBm",
            "accent_hex": "#38BDF8",
            "u": 0.36,
            "v": 0.30,
            "z_depth": 4.2,
            "visible": True,
        },
        {
            "anchor_id": "a2",
            "label": "DIE TEMP",
            "metric": "87.4 C",
            "accent_hex": "#FACC15",
            "u": 0.66,
            "v": 0.34,
            "z_depth": 4.0,
            "visible": True,
        },
        {
            "anchor_id": "a3",
            "label": "MEM CTRL",
            "metric": "1.6 TB/s",
            "accent_hex": "#34D399",
            "u": 0.33,
            "v": 0.66,
            "z_depth": 5.1,
            "visible": True,
        },
        {
            "anchor_id": "a4",
            "label": "VAPOR",
            "metric": "-12 C",
            "accent_hex": "#A78BFA",
            "u": 0.67,
            "v": 0.62,
            "z_depth": 4.8,
            "visible": True,
        },
    ]


def _blank_final():
    cv = SupersampledCanvas(W, H, scale=2, background=BACKGROUND)
    return cv.final().convert("RGB")


def _changed_pixels(region) -> int:
    data = region.tobytes()
    return sum(
        1 for i in range(0, len(data), 3) if data[i] or data[i + 1] or data[i + 2]
    )


def test_composite_9_16_keeps_cards_inside_short_safe_zone(monkeypatch):
    import hybrid_compositor
    from layout_solver import LayoutBox

    w, h = 1080, 1920
    captured: dict[str, LayoutBox] = {}

    def fake_solve(boxes, **kwargs):
        captured.update({box.box_id: box for box in boxes})
        return captured

    monkeypatch.setattr(hybrid_compositor.SATLayoutSolver, "solve", fake_solve)
    cv = SupersampledCanvas(w, h, scale=1, background=BACKGROUND)
    composite_3d_tracked_hud(
        cv,
        _synthetic_anchors(),
        "FOOD WEB // PREDATOR AND PREY",
        1.0,
        aspect_ratio="9:16",
    )
    hud = captured["hud_header"]
    assert hud.x0 >= 84 and hud.x1 <= w - 84
    assert hud.y0 >= 220 and hud.y1 <= h - 440
    for box in captured.values():
        if box.box_id.startswith("anchor_card_"):
            assert 84 <= box.x0 < box.x1 <= w - 84
            assert 560 <= box.y0 < box.y1 <= 820
            assert box.y0 > hud.y1


def test_composite_paints_cards_and_leaders():
    cv = SupersampledCanvas(W, H, scale=2, background=BACKGROUND)
    cv.set_frame(0.75, 3.0)
    result = composite_3d_tracked_hud(
        cv, _synthetic_anchors(), "TESTBED // ORION", 0.75, "16:9"
    )
    assert result is None

    img = cv.final().convert("RGB")
    diff = ImageChops.difference(img, _blank_final())
    # card band: left column x≈0..400, everything below the HUD bar
    band = diff.crop((0, 100, 400, H))
    assert _changed_pixels(band) > 100  # cards + elbow leader lines painted


def test_composite_skips_invisible_anchors():
    hidden = [{**a, "visible": False} for a in _synthetic_anchors()]
    cv = SupersampledCanvas(W, H, scale=2, background=BACKGROUND)
    cv.set_frame(0.75, 3.0)
    # must not crash, and no cards appear (empty layout for anchors)
    composite_3d_tracked_hud(cv, hidden, "TESTBED // ORION", 0.75, "16:9")
    img = cv.final().convert("RGB")
    # HUD bar still painted — top band differs from a blank canvas
    diff = ImageChops.difference(img, _blank_final())
    bar = diff.crop((96, 42, 320, 100))
    assert _changed_pixels(bar) > 20


def test_composite_empty_anchor_list_paints_hud_bar():
    cv = SupersampledCanvas(W, H, scale=2, background=BACKGROUND)
    cv.set_frame(1.0, 4.0)
    composite_3d_tracked_hud(cv, [], "TESTBED // ORION", 1.0, "16:9")
    img = cv.final().convert("RGB")
    diff = ImageChops.difference(img, _blank_final())
    bar = diff.crop((96, 42, 620, 100))
    assert _changed_pixels(bar) > 20  # HUD bar + title painted, no anchors
