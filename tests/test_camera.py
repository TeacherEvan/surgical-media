import math

import pytest
from camera import WorldCamera2D


def test_zoom_endpoints_and_mid():
    cam = WorldCamera2D(1920, 1080, zoom_start=1.0, zoom_end=2.0, easing="linear")
    assert cam.zoom_at(0.0) == pytest.approx(1.0)
    assert cam.zoom_at(1.0) == pytest.approx(2.0)
    assert cam.zoom_at(0.5) == pytest.approx(1.5)


def test_pan_centers_point_of_interest():
    cam = WorldCamera2D(
        1920,
        1080,
        zoom_start=2.0,
        zoom_end=2.0,
        pan_x=0.25,
        pan_y=0.75,
        easing="linear",
    )
    sx, sy = cam.apply(1920 * 0.25, 1080 * 0.75, 0.0)
    assert sx == pytest.approx(960.0)
    assert sy == pytest.approx(540.0)


def test_no_zoom_is_identity_translation():
    cam = WorldCamera2D(
        1280, 720, zoom_start=1.0, zoom_end=1.0, pan_x=0.5, pan_y=0.5, easing="linear"
    )
    assert cam.apply(100, 200, 0.0) == pytest.approx((100.0, 200.0))


def test_shake_zero_without_trauma_or_amplitude():
    cam = WorldCamera2D(1280, 720, shake_amplitude_px=20.0)
    assert cam.shake_offset(1.23, 0.0) == (0.0, 0.0)
    cam2 = WorldCamera2D(1280, 720, shake_amplitude_px=0.0)
    assert cam2.shake_offset(1.23, 1.0) == (0.0, 0.0)


def test_shake_deterministic_and_bounded():
    cam = WorldCamera2D(1280, 720, shake_amplitude_px=12.0, seed=42)
    a = cam.shake_offset(2.5, 1.0)
    b = cam.shake_offset(2.5, 1.0)
    assert a == b  # deterministic — no RNG drift
    assert math.hypot(*a) <= 12.0 * 1.01


def test_trauma_decay_monotonic():
    t = 1.0
    values = []
    while t > 0.01:
        values.append(t)
        t = WorldCamera2D.decay_trauma(t, 1.0 / 30.0)
    assert values == sorted(values, reverse=True)


def test_invalid_camera_rejected():
    with pytest.raises(ValueError):
        WorldCamera2D(1280, 720, zoom_start=0.5)
    with pytest.raises(ValueError):
        WorldCamera2D(1280, 720, pan_x=1.5)


# ---------------------------------------------------------------------------
# orbit mode
# ---------------------------------------------------------------------------


def test_orbit_mode_advances_around_pivot():
    cam = WorldCamera2D(
        1920,
        1080,
        mode="orbit",
        pivot_x=0.5,
        pivot_y=0.5,
        orbit_radius_start=50.0,
        orbit_radius_end=50.0,
        azimuth_start_deg=-30.0,
        azimuth_end_deg=90.0,
        orbit_easing="linear",
    )
    cx0, cy0 = cam.center_at(0.0)
    assert cx0 == pytest.approx(960.0 + 50.0 * math.cos(math.radians(-30)))
    assert cy0 == pytest.approx(540.0 + 50.0 * math.sin(math.radians(-30)))
    cx1, cy1 = cam.center_at(1.0)
    assert cx1 == pytest.approx(960.0 + 50.0 * math.cos(math.radians(90)))
    assert cy1 == pytest.approx(540.0 + 50.0 * math.sin(math.radians(90)))


def test_orbit_apply_matches_center_at():
    cam = WorldCamera2D(
        1280,
        720,
        mode="orbit",
        pivot_x=0.4,
        pivot_y=0.6,
        orbit_radius_start=70.0,
        azimuth_start_deg=10.0,
        azimuth_end_deg=190.0,
    )
    t = 0.35
    cx, cy = cam.center_at(t)
    sx, sy = cam.apply(500.0, 400.0, t)
    assert sx == pytest.approx((500.0 - cx) * cam.zoom_at(t) + 640.0)
    assert sy == pytest.approx((400.0 - cy) * cam.zoom_at(t) + 360.0)


def test_static_mode_freezes_zoom():
    cam = WorldCamera2D(1280, 720, mode="static", zoom_start=1.2, zoom_end=2.5)
    assert cam.zoom_at(0.0) == pytest.approx(1.2)
    assert cam.zoom_at(0.5) == pytest.approx(1.2)
    assert cam.zoom_at(1.0) == pytest.approx(1.2)
    sx, sy = cam.apply(300.0, 300.0, 0.0)
    assert sx == pytest.approx(232.0)
    assert sy == pytest.approx(288.0)


def test_orbit_invalid_params_rejected():
    with pytest.raises(ValueError):
        WorldCamera2D(1280, 720, mode="orbit", orbit_radius_start=0.1)
    with pytest.raises(ValueError):
        WorldCamera2D(1280, 720, mode="orbit", pivot_x=1.5)
    with pytest.raises(ValueError):
        WorldCamera2D(1280, 720, mode="spin")
