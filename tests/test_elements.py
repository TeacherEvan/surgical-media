"""Direct unit tests for elements.py painters and helpers.

test_visual_smoke.py guards whole-frame hue statistics; these tests isolate
the layout math and per-painter behavior at t=0.0 / 0.5 / 1.0 so individual
painters cannot regress silently.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import elements
from canvas import SupersampledCanvas, get_font, layout_zones
from elements import ElementContext, render_element

W, H = 220, 390  # 9:16-ish, small for speed

WORDS = [
    {"word": "emperor", "start": 0.0, "end": 0.4},
    {"word": "penguins", "start": 0.4, "end": 0.9},
    {"word": "huddle", "start": 0.9, "end": 1.4},
]


def _canvas():
    cv = SupersampledCanvas(W, H, scale=2, background="#050508")
    cv.set_frame(0.5, 1.0, trauma=0.0)
    return cv


def _ctx(t=0.5, local_time=1.0, words=WORDS):
    return ElementContext(
        width=W,
        height=H,
        t=t,
        scene_time=local_time,
        local_time=local_time,
        words=list(words),
        seed=3,
        zones=layout_zones(W, H),
    )


def _bytes_after(paint):
    cv = _canvas()
    before = cv.final().tobytes()
    paint(cv)
    return before, cv.final().tobytes()


# ---------- pure helpers ----------


def test_wrap_text_wraps_on_word_boundaries():
    font = get_font(20)
    text = "one two three four five six seven eight nine ten eleven twelve"
    lines = elements._wrap_text(text, font, 160)
    assert len(lines) > 1
    for line in lines[:-1]:
        assert font.getlength(line) <= 160
    assert " ".join(" ".join(lines).split()) == text


def test_wrap_text_empty_returns_empty():
    assert elements._wrap_text("", get_font(20), 100) == []
    assert elements._wrap_text("   ", get_font(20), 100) == []


def test_wrap_text_single_long_word_stays_on_own_line():
    font = get_font(20)
    lines = elements._wrap_text("supercalifragilisticexpialidocious word", font, 50)
    assert lines[0] == "supercalifragilisticexpialidocious"
    assert lines[-1] == "word"


def test_smoothstep_bounds_and_degenerate_range():
    assert elements._smoothstep(0.0, 1.0, -0.5) == 0.0
    assert elements._smoothstep(0.0, 1.0, 1.5) == 1.0
    assert elements._smoothstep(0.0, 1.0, 0.5) == pytest.approx(0.5)
    assert elements._smoothstep(1.0, 0.0, 0.5) == 1.0  # degenerate → defined behavior


def test_bezier_endpoints():
    p0, p1, p2, p3 = (0, 0), (10, 20), (30, 40), (100, 100)
    assert elements._bezier(p0, p1, p2, p3, 0.0) == pytest.approx(p0)
    assert elements._bezier(p0, p1, p2, p3, 1.0) == pytest.approx(p3)


# ---------- dispatcher ----------


def test_render_element_unknown_type_is_a_noop_with_warning(capsys):
    cv = _canvas()
    before = cv.final().tobytes()
    render_element(cv, {"type": "not_a_real_element"}, _ctx())
    assert cv.final().tobytes() == before
    assert "not_a_real_element" in capsys.readouterr().out


# ---------- painters at all t endpoints ----------

PAINTER_ELEMENTS = {
    "background": {"type": "background", "color": "#0B1020"},
    "grid": {"type": "grid", "spacing": 60},
    "hud_badge": {"type": "hud_badge", "text": "PINGUIN", "corner": "tl"},
    "scaling_chart": {"type": "scaling_chart", "odometer_to": 100.0},
    "phi_divider": {"type": "phi_divider", "fraction": 0.618, "t": 1.0, "reveal": 1.0},
    "tesseract": {"type": "tesseract", "t": 0.5, "reveal": 1.0},
    "code_terminal": {"type": "code_terminal", "lines": ["$ run", "ok"], "reveal": 1.0},
    "quote_card": {"type": "quote_card", "quote": "hello", "attribution": "a"},
    "kinetic_captions": {"type": "kinetic_captions", "accent": "#FFD700"},
    "stick_rig": {"type": "stick_rig", "height": 120},
    "system_architecture": {
        "type": "system_architecture",
        "cascade_start": 0.0,
        "cascade_step": 0.5,
        "nodes": [
            {"id": "lb", "role": "source", "label": "ORIGIN", "x": 60, "y": 195},
            {"id": "ex1", "role": "exchange", "label": "RELAY-1", "x": 170, "y": 90},
            {"id": "ex2", "role": "exchange", "label": "RELAY-2", "x": 170, "y": 300},
        ],
    },
}


@pytest.mark.parametrize("etype", sorted(PAINTER_ELEMENTS))
@pytest.mark.parametrize("t,local_time", [(0.0, 0.0), (0.5, 0.75), (1.0, 1.5)])
def test_painter_never_crashes_across_timeline(etype, t, local_time):
    cv = _canvas()
    render_element(cv, dict(PAINTER_ELEMENTS[etype]), _ctx(t=t, local_time=local_time))
    out = cv.final()
    assert out.size == (W, H)


@pytest.mark.parametrize(
    "etype", ["background", "grid", "hud_badge", "quote_card", "code_terminal"]
)
def test_painter_actually_paints_pixels(etype):
    before, after = _bytes_after(
        lambda cv: render_element(cv, dict(PAINTER_ELEMENTS[etype]), _ctx())
    )
    assert before != after


def test_hud_badge_respects_reveal_zero():
    # reveal = spring_pop(min(1, local_time/0.55)); at 0s nothing is drawn
    before, after = _bytes_after(
        lambda cv: render_element(
            cv, PAINTER_ELEMENTS["hud_badge"], _ctx(t=0.0, local_time=0.0)
        )
    )
    assert before == after


def test_kinetic_captions_without_words_is_noop():
    before, after = _bytes_after(
        lambda cv: render_element(
            cv, PAINTER_ELEMENTS["kinetic_captions"], _ctx(words=[])
        )
    )
    assert before == after


def test_kinetic_captions_highlights_current_word():
    before, after = _bytes_after(
        lambda cv: render_element(cv, PAINTER_ELEMENTS["kinetic_captions"], _ctx())
    )
    assert before != after


# ---------- image painter ----------


def test_image_painter_missing_src_warns_and_returns(capsys, tmp_path):
    cv = _canvas()
    before = cv.final().tobytes()
    render_element(cv, {"type": "image", "src": str(tmp_path / "nope.png")}, _ctx())
    assert cv.final().tobytes() == before
    assert "not found" in capsys.readouterr().err


def test_image_painter_paints_real_plate(tmp_path):
    plate = tmp_path / "plate.png"
    Image.new("RGB", (64, 48), (180, 40, 40)).save(plate)
    before, after = _bytes_after(
        lambda cv: render_element(
            cv,
            {
                "type": "image",
                "src": str(plate),
                "box": [0, 0, W, H],
                "fit": "contain",
                "attribution": "CC BY — test plate",
            },
            _ctx(),
        )
    )
    assert before != after
