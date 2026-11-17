#!/usr/bin/env python3
"""camera.py — pre-raster 2D world camera for surgical-media.

Transforms *world coordinates* (the design-space pixels of a storyboard) into
screen pixels BEFORE rasterization, so strokes, text and curves are
re-rasterized crisply at every zoom level instead of being upscaled after
the fact (the classic crop-and-stretch resolution-loss flaw).

Model::

    screen = (world - center) * zoom + screen_center + shake_offset

``center`` is derived from the normalized pan (pan_x, pan_y in [0, 1] of the
design width/height) — the point of interest the frame stays locked onto.
``zoom`` interpolates zoom_start -> zoom_end through the scene's easing.
``shake_offset`` is a deterministic pseudo-noise trauma shake (no RNG state,
fully reproducible per seed) with a quadratic trauma curve.
"""

from __future__ import annotations

import math

from easings import get_easing, lerp


class WorldCamera2D:
    """Deterministic affine world camera with trauma shake."""

    def __init__(
        self,
        width: int,
        height: int,
        zoom_start: float = 1.0,
        zoom_end: float = 1.0,
        pan_x: float = 0.5,
        pan_y: float = 0.5,
        easing: str = "ease_out_expo",
        shake_amplitude_px: float = 0.0,
        seed: int = 0,
    ) -> None:
        if not (1.0 <= zoom_start <= 10.0 and 1.0 <= zoom_end <= 10.0):
            raise ValueError("zoom must be within [1.0, 10.0]")
        if not (0.0 <= pan_x <= 1.0 and 0.0 <= pan_y <= 1.0):
            raise ValueError("pan must be normalized to [0, 1]")
        self.width = int(width)
        self.height = int(height)
        self.zoom_start = float(zoom_start)
        self.zoom_end = float(zoom_end)
        self.pan_x = float(pan_x)
        self.pan_y = float(pan_y)
        self.easing_name = easing
        self.easing = get_easing(easing)
        self.shake_amplitude_px = float(shake_amplitude_px)
        self.seed = int(seed)

    # ------------------------------------------------------------------
    @property
    def _center(self) -> tuple[float, float]:
        return (self.pan_x * self.width, self.pan_y * self.height)

    def zoom_at(self, t: float) -> float:
        return lerp(self.zoom_start, self.zoom_end, self.easing(t))

    def shake_offset(self, time_sec: float, trauma: float) -> tuple[float, float]:
        """Quadratic trauma shake, deterministic per seed and time."""
        if trauma <= 0.0 or self.shake_amplitude_px <= 0.0:
            return (0.0, 0.0)
        t2 = min(1.0, max(0.0, trauma)) ** 2
        s = self.seed * 0.6180339887
        dx = math.sin(47.3 * time_sec + s) + 0.5 * math.sin(91.7 * time_sec + 1.7 * s)
        dy = math.cos(39.1 * time_sec + 1.3 * s) + 0.5 * math.cos(
            83.9 * time_sec + 2.9 * s
        )
        norm = 1.5  # max |dx|, |dy|
        amp = self.shake_amplitude_px * t2
        return (amp * dx / norm, amp * dy / norm)

    def apply(
        self,
        x: float,
        y: float,
        t: float,
        trauma: float = 0.0,
        time_sec: float = 0.0,
    ) -> tuple[float, float]:
        """Map a world-space point to screen pixels at normalized time ``t``."""
        z = self.zoom_at(t)
        cx, cy = self._center
        sx = (x - cx) * z + self.width / 2.0
        sy = (y - cy) * z + self.height / 2.0
        if trauma > 0.0:
            dx, dy = self.shake_offset(time_sec, trauma)
            sx += dx
            sy += dy
        return (sx, sy)

    def stroke_scale(self, t: float) -> float:
        """Stroke width multiplier so lines keep weight at extreme zoom."""
        return self.zoom_at(t)

    @staticmethod
    def decay_trauma(trauma: float, dt: float, rate: float = 1.6) -> float:
        """Exponential trauma decay; trauma in [0, 1], dt in seconds."""
        if trauma <= 0.0:
            return 0.0
        return max(0.0, trauma * math.exp(-rate * dt) - 0.0)
