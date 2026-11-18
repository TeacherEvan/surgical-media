#!/usr/bin/env python3
"""easings.py — deterministic easing library for surgical-media.

All easing functions map a normalized time ``t`` in ``[0.0, 1.0]`` to a
normalized progress in ``[0.0, 1.0]`` (spring_pop overshoots above 1.0 by
design, clamped to exactly 1.0 at t == 1.0).

Never drive camera or UI motion with raw linear ``t``; linear movement reads
as robotic. The renderer refuses the ``linear`` easing for camera zooms unless
explicitly requested in the storyboard.
"""

from __future__ import annotations

import math
from collections.abc import Callable


def clamp01(t: float) -> float:
    return 0.0 if t < 0.0 else (min(t, 1.0))


def linear(t: float) -> float:
    return clamp01(t)


def ease_out_expo(t: float) -> float:
    """Fast-start exponential settle. Use for camera zooms and playheads."""
    t = clamp01(t)
    if t >= 1.0:
        return 1.0
    return 1.0 - math.pow(2.0, -10.0 * t)


def ease_in_out_cubic(t: float) -> float:
    """Smooth symmetric cubic. Use for pans and slide transitions."""
    t = clamp01(t)
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - math.pow(-2.0 * t + 2.0, 3) / 2.0


def ease_in_out_sine(t: float) -> float:
    t = clamp01(t)
    return -(math.cos(math.pi * t) - 1.0) / 2.0


def ease_out_back(t: float, s: float = 1.70158) -> float:
    """Slight overshoot on arrival. Use for badges and node pop-ins."""
    t = clamp01(t)
    u = t - 1.0
    return 1.0 + (s + 1.0) * u * u * u + s * u * u


def spring_pop(t: float) -> float:
    """Damped harmonic approach with a small overshoot.

    f(t) = 1 - e^(-5t) * cos(8t), clamped so f(0)=0 and f(1)=1 exactly.
    Use for milestone badges, packet lock-ins, and φ-divider locks.
    """
    t = clamp01(t)
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0
    value = 1.0 - math.exp(-5.0 * t) * math.cos(8.0 * t)
    return min(1.0 + 0.35, max(0.0, value))


EASINGS: dict[str, Callable[..., float]] = {
    "linear": linear,
    "ease_out_expo": ease_out_expo,
    "ease_in_out_cubic": ease_in_out_cubic,
    "ease_in_out_sine": ease_in_out_sine,
    "ease_out_back": ease_out_back,
    "spring_pop": spring_pop,
}


def get_easing(name: str) -> Callable[..., float]:
    """Resolve an easing by name, raising ValueError listing valid names."""
    try:
        return EASINGS[name]
    except KeyError:
        valid = ", ".join(sorted(EASINGS))
        raise ValueError(f"unknown easing {name!r}; valid: {valid}") from None


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t
