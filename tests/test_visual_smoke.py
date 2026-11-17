"""Pixel-level smoke checks: catches a painter that silently stops drawing.

These are not golden-image tests (fonts vary by host); they assert presence
of expected hue families in expected regions, which is robust to font drift.
"""

import json
import sys
from pathlib import Path

from canvas import SupersampledCanvas, layout_zones
from elements import ElementContext, render_element
from PIL import Image
from render_engine import estimate, render_thumbnails

sys.path.insert(0, str(Path(__file__).resolve().parent))

W, H = 320, 180


def _count_gold_pixels(img) -> int:
    data = img.convert("RGB").tobytes()
    count = 0
    for i in range(0, len(data), 3):
        r, g, b = data[i], data[i + 1], data[i + 2]
        if r > 120 and g > 80 and b < 70 and r > g > b:
            count += 1
    return count


def test_background_and_hud_badge_paint_pixels():
    cv = SupersampledCanvas(W, H, scale=2, background="#050508")
    cv.set_frame(0.5, 1.0)
    ctx = ElementContext(
        width=W,
        height=H,
        t=0.5,
        scene_time=1.0,
        local_time=1.0,
        words=[],
        seed=1,
        zones=layout_zones(W, H),
    )
    render_element(cv, {"type": "background", "color": "#050508"}, ctx)
    render_element(cv, {"type": "hud_badge", "text": "T", "corner": "tl"}, ctx)
    img = cv.final()
    assert img.size == (W, H)
    assert _count_gold_pixels(img) > 10  # gold capsule got painted


def test_kinetic_captions_render_word_colors():
    words = [
        {"word": "Alpha", "start": 0.0, "end": 0.4},
        {"word": "Beta", "start": 0.4, "end": 0.8},
        {"word": "Gamma", "start": 0.8, "end": 1.2},
    ]
    cv = SupersampledCanvas(W, H, scale=2, background="#050508")
    cv.set_frame(0.5, 0.5)
    ctx = ElementContext(
        width=W,
        height=H,
        t=0.5,
        scene_time=0.5,
        local_time=0.5,
        words=words,
        seed=1,
        zones=layout_zones(W, H),
    )
    render_element(cv, {"type": "background", "color": "#050508"}, ctx)
    render_element(cv, {"type": "kinetic_captions"}, ctx)
    img = cv.final().convert("RGB")
    assert img.getextrema()[0][1] > 80  # not a black frame — words got drawn


def test_thumbnails_and_estimate(tmp_path):
    demo = (
        Path(__file__).resolve().parent.parent
        / "examples"
        / "tri_archetype_storyboard.json"
    )
    out_dir = tmp_path / "thumbs"
    written = render_thumbnails(demo, out_dir, scale=1)
    assert len(written) == 3
    for path in written:
        img = Image.open(path)
        assert img.size == (1280, 720)
        # not an empty frame
        hist = img.convert("L").histogram()
        assert sum(1 for v in hist if v > 0) > 8

    board = json.loads(demo.read_text(encoding="utf-8"))
    est = estimate(board)
    assert est["total_frames"] == 432
    assert est["scenes"] == 3
    assert est["duration_sec"] == 14.4


def test_box_downsample_keeps_thin_lines():
    """A 2px line at 2x supersample must survive the BOX downsample as visible."""
    cv = SupersampledCanvas(W, H, scale=2, background="#050508")
    cv.set_frame(0.0, 0.0)
    cv.line((20, 90), (300, 90), "#FFFFFF", 2.0)
    img = cv.final().convert("L")
    row = [img.getpixel((x, 90)) for x in range(W)]
    assert max(row) > 200
    assert sum(1 for v in row if v > 100) > 100  # spans most of the width


def test_scaling_chart_custom_odometer_and_milestones():
    """odo_suffix / milestones params must render without crashing and draw the badge."""
    cv = SupersampledCanvas(W, H, scale=2, background="#0A0E17")
    cv.set_frame(0.9, 3.0)
    ctx = ElementContext(
        width=W,
        height=H,
        t=0.9,
        scene_time=3.0,
        local_time=3.0,
        words=[],
        seed=1,
        zones=layout_zones(W, H),
    )
    render_element(
        cv,
        {
            "type": "scaling_chart",
            "exponent": 2.0,
            "odometer_from": 0.0,
            "odometer_to": 565.0,
            "accent": "#22D3EE",
            "label": "MAX DEPTH (M)",
            "odo_suffix": " m",
            "odo_decimals": 0,
            "milestones": [{"u": 0.25, "tag": "140m"}],
            "box": [20, 30, 300, 150],
        },
        ctx,
    )
    img = cv.final().convert("RGB")
    assert img.getextrema()[0][1] > 100  # panel + chart drawn


def test_kinetic_captions_tolerates_multiword_boundary_tokens():
    """edge-tts WordBoundary events may carry 'since 2009' as ONE token."""
    words = [
        {"word": "But", "start": 0.0, "end": 0.3},
        {"word": "the ice", "start": 0.3, "end": 0.9},  # multi-word event
        {"word": "is", "start": 0.9, "end": 1.1},
        {"word": "vanishing.", "start": 1.1, "end": 1.6},
    ]
    cv = SupersampledCanvas(W, H, scale=2, background="#050508")
    cv.set_frame(0.5, 1.0)
    ctx = ElementContext(
        width=W,
        height=H,
        t=0.5,
        scene_time=1.0,
        local_time=1.0,
        words=words,
        seed=1,
        zones=layout_zones(W, H),
    )
    render_element(cv, {"type": "background", "color": "#050508"}, ctx)
    render_element(cv, {"type": "kinetic_captions", "size": 16}, ctx)
    img = cv.final().convert("RGB")
    assert img.getextrema()[0][1] > 60


def test_quote_card_long_attribution_fits_card():
    """Long attributions must shrink to fit the card instead of overflowing."""
    cv = SupersampledCanvas(W, H, scale=2, background="#050508")
    cv.set_frame(0.8, 2.0)
    ctx = ElementContext(
        width=W,
        height=H,
        t=0.8,
        scene_time=2.0,
        local_time=2.0,
        words=[],
        seed=1,
        zones=layout_zones(W, H),
    )
    render_element(
        cv,
        {
            "type": "quote_card",
            "quote": "The ice is vanishing.",
            "attribution": "IUCN RED LIST — ENDANGERED (2026)",
            "box": [16, 30, 304, 150],
        },
        ctx,
    )
    img = cv.final().convert("RGB")
    # bloom spills a few px past the border; text overflow is a ~100px bleed.
    for x in range(320, W):
        assert sum(img.getpixel((x, 135))) <= 60
