"""Finishing-pass tests: determinism, pass-through, pixel statistics (no goldens)."""

import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageStat

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import grade
import render_engine
import storyboard

W, H = 160, 90


def _flat(color=(120, 120, 120)):
    return Image.new("RGB", (W, H), color)


def test_zero_grade_is_passthrough():
    g = grade.Grader({}, W, H, 1)
    frame = _flat()
    assert not g.active
    assert g(frame, 0) is frame


def test_grain_is_deterministic_and_adds_variance():
    a = grade.Grader({"grain": 0.8}, W, H, 7)(_flat(), 3)
    b = grade.Grader({"grain": 0.8}, W, H, 7)(_flat(), 3)
    c = grade.Grader({"grain": 0.8}, W, H, 8)(_flat(), 3)
    assert a.tobytes() == b.tobytes()
    assert a.tobytes() != c.tobytes()
    assert max(ImageStat.Stat(a).stddev) > 2.0
    assert abs(ImageStat.Stat(a).mean[0] - 120) < 3.0  # zero-centred


def test_grain_varies_by_frame_and_cycles():
    g = grade.Grader({"grain": 0.5}, W, H, 7)
    f0, f1 = g(_flat(), 0).tobytes(), g(_flat(), 1).tobytes()
    assert f0 != f1
    assert g(_flat(), grade.GRAIN_TILES).tobytes() == f0


def test_vignette_darkens_edges_not_centre():
    out = grade.Grader({"vignette": 0.9}, W, H, 1)(_flat((200, 200, 200)), 0)
    assert out.getpixel((W // 2, H // 2))[0] >= 195
    assert out.getpixel((0, 0))[0] < 150


def test_warmth_shifts_red_over_blue():
    warm = grade.Grader({"warmth": 1.0}, W, H, 1)(_flat(), 0).getpixel((5, 5))
    cool = grade.Grader({"warmth": -1.0}, W, H, 1)(_flat(), 0).getpixel((5, 5))
    assert warm[0] > warm[2]
    assert cool[2] > cool[0]


def test_halation_bleeds_light_beside_highlights_only():
    img = Image.new("RGB", (W, H), (20, 20, 20))
    img.paste((255, 255, 255), (70, 35, 90, 55))
    out = grade.Grader({"halation": 1.0}, W, H, 1)(img, 0)
    assert out.getpixel((95, 45))[0] > 20  # halo outside the bright block
    assert out.getpixel((5, 5))[0] <= 21  # far dark area untouched
    assert out.getpixel((80, 45)) == (255, 255, 255)  # no clipping artefacts


def test_wrong_size_raises():
    with pytest.raises(ValueError):
        grade.Grader({"grain": 0.2}, W, H, 1)(Image.new("RGB", (10, 10)), 0)


def test_bad_values_clamped_not_crashing():
    g = grade.Grader({"grain": "x", "vignette": 9, "warmth": None}, W, H, 1)
    assert g.grain == 0.0 and g.vignette == 1.0 and g.warmth == 0.0


def test_thumbnails_apply_style_grade(tmp_path):
    base = json.loads(
        (REPO / "examples" / "tri_archetype_storyboard.json").read_text("utf-8")
    )
    base["scenes"] = base["scenes"][:1]
    plain = tmp_path / "plain.json"
    plain.write_text(json.dumps(base))
    styled = dict(base, style={"preset": "noir_restraint"})
    sp = tmp_path / "styled.json"
    sp.write_text(json.dumps(styled))
    assert storyboard.validate_storyboard(styled) == []
    a = render_engine.render_thumbnails(plain, tmp_path / "a", scale=1)[0]
    b = render_engine.render_thumbnails(sp, tmp_path / "b", scale=1)[0]
    ia, ib = Image.open(a), Image.open(b)
    assert ia.tobytes() != ib.tobytes()
    assert (
        ImageStat.Stat(ib.convert("L")).mean[0]
        < ImageStat.Stat(ia.convert("L")).mean[0]
    )


def test_svg_contact_shadow_darkens_below_plate_and_respects_opacity():
    from canvas import SupersampledCanvas
    from elements import svg

    def run(opacity):
        cv = SupersampledCanvas(200, 120, scale=1, background="#FFFFFF")
        plate = Image.new("RGBA", (40, 40), (255, 0, 0, 255))
        svg._paste_contact_shadow(
            cv, plate, (80, 30), {"shadow_opacity": opacity, "shadow_blur": 0.1}
        )
        return cv.image

    img = run(0.8)
    assert img.getpixel((100, 76))[0] < 240  # shadow just below the plate footprint
    assert img.getpixel((5, 5)) == (255, 255, 255)  # far field untouched
    assert run(0.0).getpixel((100, 76)) == (255, 255, 255)
