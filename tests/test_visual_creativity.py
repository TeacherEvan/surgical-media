"""Motion/behavior tests for the personality painters (scripts/elements/visual.py).

Asserts the things "quality" means here: elements must MOVE, must look
slightly different across time, must land glyphs/pixels when revealed, and
must reject degenerate inputs without crashing. All painters are
deterministic, so we can diff pixel buffers between timestamps.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from canvas import SupersampledCanvas, layout_zones
from elements import ElementContext, render_element
from elements.visual import _cursor_visible

W, H = 220, 390  # 9:16-ish, small for speed


def _canvas():
    cv = SupersampledCanvas(W, H, scale=2, background="#050508")
    cv.set_frame(0.5, 1.0, trauma=0.0)
    return cv


def _ctx(t, local_time):
    return ElementContext(
        width=W,
        height=H,
        t=t,
        scene_time=local_time,
        local_time=local_time,
        words=[],
        seed=3,
        zones=layout_zones(W, H),
    )


def _render(el: dict, local_time: float) -> bytes:
    cv = _canvas()
    cv.set_frame(0.5, 1.0)
    render_element(cv, el, _ctx(0.5, local_time))
    return cv.final().tobytes()


def _differs(el: dict, t_a: float, t_b: float, min_diff: int = 5) -> None:
    a = _render(el, t_a)
    b = _render(el, t_b)
    assert sum(1 for x, y in zip(a, b) if x != y) >= min_diff, (
        f"{el['type']} is static between t={t_a} and t={t_b}"
    )


# ---------------------------------------------------------------------------
# orb_pulse
# ---------------------------------------------------------------------------


def test_orb_pulse_breathes_over_time():
    _differs({"type": "orb_pulse", "radius": 30, "pulse_hz": 1.0}, 0.1, 0.55)


def test_orb_pulse_negative_radius_is_noop():
    _render({"type": "orb_pulse", "radius": -5}, 0.5)  # no crash, no hang


# ---------------------------------------------------------------------------
# dot_field
# ---------------------------------------------------------------------------


def test_dot_field_drifts_over_time():
    _differs({"type": "dot_field", "n": 8, "radius": 3}, 0.2, 0.9)


def test_dot_field_empty_is_noop():
    _render({"type": "dot_field", "n": 0}, 0.5)


# ---------------------------------------------------------------------------
# orbit_ring
# ---------------------------------------------------------------------------


def test_orbit_ring_rotates():
    _differs({"type": "orbit_ring", "n": 6, "radius": 30, "size": 4}, 0.1, 0.6)


def test_orbit_ring_pulse_moves():
    _differs(
        {"type": "orbit_ring", "n": 6, "radius": 30, "size": 6, "pulse_hz": 1.0},
        0.05,
        0.7,
    )


# ---------------------------------------------------------------------------
# equalizer
# ---------------------------------------------------------------------------


def test_equalizer_moves_bars():
    _differs({"type": "equalizer", "n": 8, "bar_width": 6, "peak": 140}, 0.0, 0.6)


# ---------------------------------------------------------------------------
# typewriter_text
# ---------------------------------------------------------------------------


def _visible_glyphs(el: dict, t: float) -> int:
    cv = _canvas()
    cv.set_frame(0.5, 1.0)
    before = cv.final().tobytes()
    render_element(cv, el, _ctx(0.5, t))
    after = cv.final().tobytes()
    return sum(1 for x, y in zip(before, after) if x != y)


def test_typewriter_reveals_more_glyphs_over_time():
    el = {
        "type": "typewriter_text",
        "text": "Deterministic typing",
        "start": 0.0,
        "speed": 12.0,
        "size": 14,
    }
    early = _visible_glyphs(el, 0.02)
    late = _visible_glyphs(el, 0.9)
    assert late > early, "typewriter never reveals new glyphs"


def test_typewriter_no_text_is_noop():
    _render({"type": "typewriter_text", "text": ""}, 0.5)


def test_typewriter_cursor_hold_is_seconds():
    text = "Hello world"
    speed, hold = 12.0, 0.6
    type_done = len(text) / speed
    # live from reveal, still live through typing + hold (all seconds)
    assert _cursor_visible(0.01, text, speed, hold)
    assert _cursor_visible(type_done + hold - 0.01, text, speed, hold)
    # the old bug: `hold` counted glyphs — cursor lingered past the text
    # and never turned off once reveal hit len(text)
    assert not _cursor_visible(type_done + hold + 0.05, text, speed, hold)
    assert not _cursor_visible(-0.1, text, speed, hold)


# ---------------------------------------------------------------------------
# leader_arrow
# ---------------------------------------------------------------------------


def test_leader_arrow_advances():
    el = {
        "type": "leader_arrow",
        "points": [[10, 380], [10, 180], [210, 180]],
        "speed": 2.0,
    }
    _differs(el, 0.1, 1.4)


def test_leader_arrow_wrap_loops():
    el = {
        "type": "leader_arrow",
        "points": [[0, 0], [200, 0]],
        "speed": 3.0,
        "wrap": True,
    }
    _differs(el, 0.2, 1.2)


def test_leader_arrow_needs_two_points():
    _render({"type": "leader_arrow", "points": [[10, 100]]}, 0.5)
    _render({"type": "leader_arrow"}, 0.5)


# ---------------------------------------------------------------------------
# misc robustness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "el",
    [
        {"type": "orb_pulse"},
        {"type": "dot_field"},
        {"type": "orbit_ring"},
        {"type": "equalizer"},
        {"type": "typewriter_text", "text": "x"},
        {"type": "leader_arrow", "points": [[0, 0], [50, 50]]},
    ],
)
def test_new_painters_never_crash_across_timeline(el):
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        frame = _render(el, t)
        assert len(frame) > 0
