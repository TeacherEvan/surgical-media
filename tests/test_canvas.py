import pytest
from canvas import (
    SupersampledCanvas,
    classify_aspect,
    layout_zones,
    parse_color,
    safe_rect,
)


def test_parse_color_hex_variants():
    assert parse_color("#FF6B00") == (255, 107, 0, 255)
    assert parse_color("#FF6B00CC") == (255, 107, 0, 204)
    assert parse_color("FF6B00") == (255, 107, 0, 255)
    assert parse_color("#F00") == (255, 0, 0, 255)
    assert parse_color((10, 20, 30)) == (10, 20, 30, 255)
    with pytest.raises(ValueError):
        parse_color("papaya")


def test_classify_aspect():
    assert classify_aspect(1920, 1080) == "16:9"
    assert classify_aspect(1080, 1920) == "9:16"
    assert classify_aspect(1080, 1080) == "1:1"


def test_safe_rect_inside_canvas():
    for w, h in ((1920, 1080), (1080, 1920), (1080, 1080)):
        x0, y0, x1, y1 = safe_rect(w, h)
        assert 0 <= x0 < x1 <= w
        assert 0 <= y0 < y1 <= h


def test_layout_zones_non_overlapping():
    for w, h in ((1920, 1080), (1080, 1920), (1080, 1080)):
        z = layout_zones(w, h)
        hud, stage, captions = z["hud"], z["stage"], z["captions"]
        assert hud[3] <= stage[1] <= stage[3] <= captions[1] <= captions[3]
        assert stage[1] < stage[3]


def test_supersampled_canvas_downsamples():
    cv = SupersampledCanvas(160, 90, scale=2, background="#050508")
    cv.set_frame(0.0, 0.0)
    cv.line((10, 10), (150, 80), "#FFFFFF", 3.0)
    img = cv.final()
    assert img.size == (160, 90)
    assert img.mode == "RGB"
    # diagonal stroke should cover a spread of pixels, not a staircase of points
    extrema = img.convert("L").getextrema()
    assert extrema[1] > 200


def test_bloom_brightens_emissive_primitives():
    plain = SupersampledCanvas(160, 90, scale=2, background="#050508")
    plain.set_frame(0.0, 0.0)
    plain.line((20, 45), (140, 45), "#202020", 2.0)
    plain_img = plain.final().convert("L")

    glow = SupersampledCanvas(160, 90, scale=2, background="#050508")
    glow.set_frame(0.0, 0.0)
    glow.line((20, 45), (140, 45), "#202020", 2.0)
    glow.bloom_line((20, 45), (140, 45), "#FFD700", 4.0)
    glow_img = glow.final().convert("L")

    plain_hist = sum(plain_img.histogram()[64:])
    glow_hist = sum(glow_img.histogram()[64:])
    assert glow_hist > plain_hist
