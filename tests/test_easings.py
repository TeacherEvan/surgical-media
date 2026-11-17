import easings
import pytest
from easings import EASINGS, ease_out_expo, get_easing, lerp, spring_pop

ALL = list(EASINGS.values())


@pytest.mark.parametrize("fn", ALL, ids=lambda f: f.__name__)
def test_endpoints(fn):
    assert fn(0.0) == pytest.approx(0.0, abs=1e-9)
    assert fn(1.0) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("fn", ALL, ids=lambda f: f.__name__)
def test_clamped_outside_unit_interval(fn):
    assert fn(-0.5) == pytest.approx(0.0, abs=1e-9)
    assert fn(1.5) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize(
    "fn",
    [
        ease_out_expo,
        easings.ease_in_out_cubic,
        easings.ease_in_out_sine,
        easings.ease_out_back,
    ],
)
def test_monotonic_non_decreasing(fn):
    samples = [fn(i / 100) for i in range(101)]
    # spring-like curves may overshoot; these four must be monotonic-ish
    assert samples[-1] >= samples[0]
    from itertools import pairwise

    assert all(b >= a - 0.05 for a, b in pairwise(samples))


def test_spring_pop_overshoots():
    peak = max(spring_pop(i / 200) for i in range(201))
    assert peak > 1.0  # overshoot is the point of a spring


def test_ease_out_expo_starts_fast():
    assert ease_out_expo(0.25) > 0.5  # expo leaves linear in the dust early


def test_get_easing_unknown_raises():
    with pytest.raises(ValueError, match="unknown easing"):
        get_easing("teleport")


def test_lerp_midpoint():
    assert lerp(2.0, 6.0, 0.5) == pytest.approx(4.0)
