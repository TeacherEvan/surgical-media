import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import composition as c


def test_thirds_and_golden_points():
    pts = c.thirds_points(900, 600)
    assert (300, 200) in pts and (600, 400) in pts and len(pts) == 4
    g = c.golden_points(1000, 1000)
    assert abs(g[0][0] - 381.97) < 0.1 and abs(g[1][0] - 618.03) < 0.1


def test_off_axis_box_is_not_centered_and_centered_is_zero():
    w, h = 1280, 720
    box = c.off_axis_box(w, h, 0.3, "thirds_tl")
    assert c.centeredness(box, w, h) > 0.25
    assert c.centeredness(c.box_around(w / 2, h / 2, 100, 100), w, h) == 0.0
    assert c.off_axis_box(w, h, 0.3, "golden_br")[2] > w / 2


def test_bad_anchor():
    with pytest.raises(ValueError):
        c.off_axis_box(100, 100, 0.5, "middle")
