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
    """Deterministic affine world camera with trauma shake.

    ``mode``: ``"zoom"`` (default — zoom_start→zoom_end through ``easing``),
    ``"orbit"`` (dynamic center: pivot + ``orbit_radius`` · direction(azimuth)
    — the zoom still scales world offsets around that moving center), and
    ``"static"`` (zoom frozen at ``zoom_start``, shake active).
    """

    CAMERA_MODES = ("zoom", "orbit", "static")

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
        mode: str = "zoom",
        pivot_x: float | None = None,
        pivot_y: float | None = None,
        orbit_radius_start: float = 0.0,
        orbit_radius_end: float | None = None,
        azimuth_start_deg: float = 0.0,
        azimuth_end_deg: float | None = None,
        orbit_easing: str | None = None,
        elevation_deg: float = 0.0,
    ) -> None:
        if not (1.0 <= zoom_start <= 10.0 and 1.0 <= zoom_end <= 10.0):
            raise ValueError("zoom must be within [1.0, 10.0]")
        if not (0.0 <= pan_x <= 1.0 and 0.0 <= pan_y <= 1.0):
            raise ValueError("pan must be normalized to [0, 1]")
        if mode not in self.CAMERA_MODES:
            raise ValueError(
                f"unknown camera mode {mode!r}; valid: {self.CAMERA_MODES}"
            )
        if not (-90.0 <= elevation_deg <= 90.0):
            raise ValueError("elevation_deg must be within [-90.0, 90.0]")
        if not (-360.0 <= azimuth_start_deg <= 360.0):
            raise ValueError("azimuth_start_deg must be within [-360.0, 360.0]")
        if not (
            -360.0
            <= (azimuth_end_deg if azimuth_end_deg is not None else azimuth_start_deg)
            <= 360.0
        ):
            raise ValueError("azimuth_end_deg must be within [-360.0, 360.0]")
        if mode == "orbit":
            if not (0.5 <= orbit_radius_start <= 100.0):
                raise ValueError("orbit_radius_start must be within [0.5, 100.0]")
            radius_end = (
                orbit_radius_start if orbit_radius_end is None else orbit_radius_end
            )
            if not (0.5 <= radius_end <= 100.0):
                raise ValueError("orbit_radius_end must be within [0.5, 100.0]")
        else:
            radius_end = (
                orbit_radius_start if orbit_radius_end is None else orbit_radius_end
            )
        for key, px in (("pivot_x", pivot_x), ("pivot_y", pivot_y)):
            if px is not None and not (0.0 <= px <= 1.0):
                raise ValueError(f"{key} must be normalized to [0, 1]")
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
        self.mode = mode
        self.pivot_x = (
            (self.width / 2.0) if pivot_x is None else float(pivot_x) * self.width
        )
        self.pivot_y = (
            (self.height / 2.0) if pivot_y is None else float(pivot_y) * self.height
        )
        self.orbit_radius_start = float(orbit_radius_start)
        self.orbit_radius_end = radius_end
        self.azimuth_start_deg = float(azimuth_start_deg)
        self.azimuth_end_deg = float(
            azimuth_start_deg if azimuth_end_deg is None else azimuth_end_deg
        )
        self.orbit_easing = get_easing(orbit_easing) if orbit_easing else self.easing
        self.elevation_deg = float(elevation_deg)

    # ------------------------------------------------------------------
    @property
    def _center(self) -> tuple[float, float]:
        return (self.pan_x * self.width, self.pan_y * self.height)

    def center_at(self, t: float) -> tuple[float, float]:
        """World-space camera center at normalized scene progress ``t``."""
        if self.mode != "orbit":
            return self._center
        u = min(1.0, max(0.0, self.orbit_easing(t)))
        radius = lerp(self.orbit_radius_start, self.orbit_radius_end, u)
        az = math.radians(lerp(self.azimuth_start_deg, self.azimuth_end_deg, u))
        elev = math.radians(self.elevation_deg)
        return (
            self.pivot_x + radius * math.cos(az) * math.cos(elev),
            self.pivot_y
            + radius * math.sin(az) * math.cos(elev)
            + radius * math.sin(elev),
        )

    def zoom_at(self, t: float) -> float:
        if self.mode == "static":
            return self.zoom_start
        return float(lerp(self.zoom_start, self.zoom_end, self.easing(t)))

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
        cx, cy = self.center_at(t)
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
        return max(0.0, trauma * math.exp(-rate * max(0.0, dt)))
