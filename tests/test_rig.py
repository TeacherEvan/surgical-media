import pytest
from rig import draw_stick_figure, two_bone_ik


def test_ik_reaches_reachable_target():
    shoulder = (0.0, 0.0)
    _elbow, hand = two_bone_ik(shoulder, (100.0, 50.0), upper=80.0, lower=80.0, bend=1)
    dist = ((hand[0] - shoulder[0]) ** 2 + (hand[1] - shoulder[1]) ** 2) ** 0.5
    assert dist == pytest.approx((100.0**2 + 50.0**2) ** 0.5, abs=0.5)


def test_ik_clamps_unreachable_target():
    _elbow, hand = two_bone_ik((0, 0), (1000, 0), upper=80.0, lower=80.0, bend=1)
    dist = (hand[0] ** 2 + hand[1] ** 2) ** 0.5
    assert dist == pytest.approx(160.0, abs=0.5)  # full extension


def test_ik_degenerate_zero_distance():
    elbow, hand = two_bone_ik((10, 10), (10, 10), 80.0, 80.0, bend=1)
    assert elbow is not None and hand is not None  # no NaN explosion


def test_elbow_bend_side_mirrors():
    elbow_down, _ = two_bone_ik((0, 0), (100, 0), 60.0, 60.0, bend=1)
    elbow_up, _ = two_bone_ik((0, 0), (100, 0), 60.0, 60.0, bend=-1)
    assert elbow_down[1] == pytest.approx(-elbow_up[1])


class _FakeCanvas:
    def __init__(self):
        self.lines = []
        self.polylines = []
        self.ellipses = []

    def line(self, a, b, color, width):
        self.lines.append((a, b, color, width))

    def polyline(self, pts, color, width, closed=False):
        self.polylines.append((list(pts), color, width))

    def ellipse(self, box, outline=None, fill=None, width=1.0):
        self.ellipses.append((box, outline, fill, width))


def test_stick_figure_draws_all_limbs():
    cv = _FakeCanvas()
    joints = draw_stick_figure(cv, 400, 600, 300, t=1.0, reach_target=(520, 300))
    assert len(cv.polylines) >= 4  # 2 legs + 2 arms
    assert len(cv.ellipses) >= 1  # hollow head
    for name in ("elbow_l", "elbow_r", "hand_l", "hand_r", "knee_l", "knee_r"):
        assert name in joints


def test_stick_figure_deterministic():
    cv1, cv2 = _FakeCanvas(), _FakeCanvas()
    draw_stick_figure(cv1, 400, 600, 300, t=2.3, reach_target=(500, 320))
    draw_stick_figure(cv2, 400, 600, 300, t=2.3, reach_target=(500, 320))
    assert cv1.polylines == cv2.polylines
