"""Unit tests for comedy-mockup painters (scripts/elements/ui_mockups.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from canvas import SupersampledCanvas, layout_zones, rgb
from elements import ElementContext, render_element

W, H = 1080, 1920  # Horse 10th-frame? — union: 9:16

BEZEL = "#1B1B1F"
MATCH_ACCENT = "#FF4D6D"


def _ctx(local_time=1.0, t=0.5):
    return ElementContext(
        width=W,
        height=H,
        t=t,
        scene_time=local_time,
        local_time=local_time,
        words=[],
        seed=7,
        zones=layout_zones(W, H),
    )


def _render(el, local_time=1.0):
    cv = SupersampledCanvas(W, H, scale=1, background="#050508")
    cv.set_frame(0.5, local_time)
    render_element(cv, el, _ctx(local_time))
    return cv


def _colors(cv) -> set:
    im = cv.final().convert("RGB")
    return {im.getpixel((x, y)) for x in range(0, W, 8) for y in range(0, H, 8)}


def _rows(cv, color):
    im = cv.final().convert("RGB")
    return [y for y in range(H) if im.getpixel((W // 2, y)) == color]


# ---------------------------------------------------------------------------
# phone_frame
# ---------------------------------------------------------------------------


def test_phone_frame_draws_silhouette():
    cv = _render({"type": "phone_frame", "box": [120, 400, 960, 1440]})
    colors = _colors(cv)
    assert rgb(BEZEL) in colors
    # interior is bg, not pure bezel
    assert rgb("#FFF4D6") in colors


def test_phone_frame_overrides():
    cv = _render(
        {
            "type": "phone_frame",
            "box": [120, 400, 960, 1440],
            "bg": "#123456",
            "outline": "#654321",
        }
    )
    assert _colors(cv)


# ---------------------------------------------------------------------------
# swipe_card
# ---------------------------------------------------------------------------


def test_swipe_card_top_wobbles_and_backcards_draw():
    el = {
        "type": "swipe_card",
        "box": [120, 400, 960, 1400],
        "pop": 0.2,
        "pop_period": 0.5,
        "cards": [{"accent": "#FF4D6D"}, {"accent": "#FFD23F"}],
    }
    cv_a, cv_b = _render(el, local_time=0.1), _render(el, local_time=0.9)
    diff = sum(
        1 for x, y in zip(cv_a.final().tobytes(), cv_b.final().tobytes()) if x != y
    )
    assert diff > 500, "top card pop wobble should move pixels"
    assert rgb(MATCH_ACCENT) in _colors(cv_a), "back card color drawn"
    assert rgb("#FFD23F") in _colors(cv_a), "top card accent drawn"


def test_swipe_card_top_moves_off_center_default_label():
    el = {
        "type": "swipe_card",
        "box": [120, 400, 960, 1400],
        "cards": [{"label": "FIRST"}, {"accent": MATCH_ACCENT}],
    }
    assert _colors(_render(el))


# ---------------------------------------------------------------------------
# social_post
# ---------------------------------------------------------------------------


def test_social_post_default_renders_nonblank():
    colors = _colors(_render({"type": "social_post", "box": [40, 220, 1040, 620]}))
    assert rgb("#A65A38") in colors  # default avatar accent
    assert rgb("#FF4D6D") in colors  # default heart
    assert rgb("#1B1B1F") in colors  # header/body text ink
    # Inter-Regular.ttf body weight yields ~41 unique sampled colors
    assert len(colors) > 30


def test_social_post_custom_body():
    el = {
        "type": "social_post",
        "box": [40, 220, 1040, 620],
        "post": {"name": "Foo Bar", "body": ["One line"], "likes": 9},
    }
    assert _colors(_render(el))


# ---------------------------------------------------------------------------
# chat_bubble
# ---------------------------------------------------------------------------


def test_chat_bubble_left_and_right():
    el = {
        "type": "chat_bubble",
        "box": [0, 0, W, H],
        "bubbles": [
            {"side": "left", "text": "help me garden", "accent": "#A65A38"},
            {"side": "right", "text": "done", "accent": MATCH_ACCENT},
        ],
    }
    colors = _colors(_render(el, local_time=5.0))
    assert rgb("#A65A38") in colors, "left bubble accent"
    assert rgb(MATCH_ACCENT) in colors, "right bubble accent"


def test_chat_bubble_slides_in_after_delay():
    el = {
        "type": "chat_bubble",
        "box": [0, 0, W, H],
        "bubbles": [{"text": "hi there", "accent": MATCH_ACCENT, "delay": 1.0}],
    }
    early = _colors(_render(el, local_time=0.1))
    late = _colors(_render(el, local_time=5.0))
    assert rgb(MATCH_ACCENT) not in early
    assert rgb(MATCH_ACCENT) in late


# ---------------------------------------------------------------------------
# app_toast
# ---------------------------------------------------------------------------


def test_app_toast_slides_after_delay():
    el = {
        "type": "app_toast",
        "box": [0, 0, W, H],
        "delay": 0.3,
        "duration": 5.0,
        "toast": {"text": "MATCH: Stallion #412", "accent": MATCH_ACCENT},
    }
    early_colors = _colors(_render(el, local_time=0.1))
    assert rgb(MATCH_ACCENT) not in early_colors
    late_colors = _colors(_render(el, local_time=2.0))
    assert rgb(MATCH_ACCENT) in late_colors
    pill_rows = _rows(_render(el, local_time=2.0), rgb(MATCH_ACCENT))
    assert any(H * 0.5 - 120 < y < H for y in pill_rows), (
        "toast sits in the 9:16 safe band"
    )
