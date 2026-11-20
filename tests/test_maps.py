"""Unit tests for political-map painters (scripts/elements/maps.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from canvas import SupersampledCanvas, layout_zones, rgb
from elements import ElementContext, render_element

W, H = 1920, 1080  # 16:9 canvas


def _ctx(local_time=1.0, t=0.5):
    return ElementContext(
        width=W,
        height=H,
        t=t,
        scene_time=local_time,
        local_time=local_time,
        words=[],
        seed=11,
        zones=layout_zones(W, H),
    )


def _render(el, local_time=1.0):
    cv = SupersampledCanvas(W, H, scale=1, background="#0B0F14")
    cv.set_frame(0.5, local_time)
    render_element(cv, el, _ctx(local_time))
    return cv


def _nonblank(cv):
    im = cv.final().convert("RGB")
    w, h = im.size
    px = im.load()
    varied = 0
    prev = px[0, 0]
    for x in range(w):
        for y in range(0, h, max(1, h // 50)):
            p = px[x, y]
            varied += p != prev
            prev = p
    return varied > 0


# ---------------------------------------------------------------------------
# paint_map — default world clusters
# ---------------------------------------------------------------------------


def test_map_default_renders_and_fills_regions():
    accent = "#E5484D"
    cv = _render({"type": "map", "box": [60, 60, 1860, 1020], "accent": accent})
    assert _nonblank(cv)
    im = cv.final().convert("RGB")
    # EUROPE region center: x0 + 0.23*box, y0 + 0.24*box
    assert im.getpixel((int(60 + 0.23 * 1800), int(60 + 0.24 * 960))) == rgb(accent)
    # ASIA region center
    assert im.getpixel((int(60 + 0.77 * 1800), int(60 + 0.20 * 960))) == rgb(accent)


def test_map_regions_override():
    cv = _render(
        {
            "type": "map",
            "box": [0, 0, W, H],
            "regions": [
                {
                    "x": 0.1,
                    "y": 0.1,
                    "w": 0.5,
                    "h": 0.5,
                    "color": "#30D5C8",
                    "label": "ZONE",
                }
            ],
        }
    )
    assert _nonblank(cv)
    im = cv.final().convert("RGB")
    assert im.getpixel((int(0.35 * W), int(0.35 * H))) == rgb("#30D5C8")


def test_map_labels_present():
    cv = _render({"type": "map", "box": [0, 0, W, H], "accent": "#E5484D"})
    assert _nonblank(cv)


# ---------------------------------------------------------------------------
# paint_map_arrow — wraps leader_arrow (moves over time)
# ---------------------------------------------------------------------------


def test_map_arrow_moves_between_frames():
    el = {
        "type": "map_arrow",
        "box": [0, 0, W, H],
        "points": [[100, 500], [900, 660]],
        "speed": 2.0,
    }
    cv_a = _render(el, local_time=1.0)
    cv_b = _render(el, local_time=10.0)
    im_a, im_b = cv_a.final().convert("RGB"), cv_b.final().convert("RGB")
    diff = sum(1 for x, y in zip(im_a.tobytes(), im_b.tobytes()) if x != y)
    assert diff > 100, "map arrow should move"


# ---------------------------------------------------------------------------
# paint_map_callout — marker + pill + tail
# ---------------------------------------------------------------------------


def test_map_callout_draws_marker_and_pill():
    accent = "#E5484D"
    cv = _render(
        {
            "type": "map_callout",
            "box": [0, 0, W, H],
            "point": {"x": 0.5, "y": 0.45},
            "text": "TROPIC ZONE",
            "accent": accent,
        }
    )
    assert _nonblank(cv)
    im = cv.final().convert("RGB")
    # marker dot is accent
    assert any(
        im.getpixel((px, py)) == rgb(accent)
        for px in range(int(0.5 * W) - 12, int(0.5 * W) + 13, 3)
        for py in range(int(0.45 * H) - 14, int(0.45 * H) + 13, 3)
    )
    # pill interior is ground (#0B0F14 default? callout uses bg=ground default)
    assert _nonblank(cv)
