"""grade.py — shared final-frame finishing pass (colour grade, halation, vignette, grain).

Every backend (2D painters, SVG, Three.js plates, Blender plates, software 3D)
ends up as one RGB ``PIL.Image`` per frame. Applying one finishing pass to that
image is what makes a WebGL render, a vector illustration and flat type read as
a single authored piece rather than three pasted layers.

Driven by the ``style.grade`` block (see ``style.py``)::

    {"grain": 0.18, "vignette": 0.2, "halation": 0.25, "warmth": 0.1}

All values are deterministic: grain tiles come from a seeded ``random.Random``
and are selected by frame index, so a given (board, seed) always renders the
same bytes. Pillow only (no NumPy, per ADR 0001). Zero-strength grade ⇒
:class:`Grader` is a pass-through.
"""

from __future__ import annotations

import random
from typing import Any

from PIL import Image, ImageChops, ImageFilter

GRAIN_TILES = 4  # distinct noise frames; cycled by frame index
GRAIN_LEVELS = 26.0  # max +/- 8-bit levels at grain == 1.0
HALATION_THRESHOLD = 170
HALATION_TINT = (255, 150, 90)  # warm film halation


def _clamp01(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


class Grader:
    """Callable finishing pass for frames of a fixed size."""

    def __init__(
        self, grade: dict[str, Any] | None, width: int, height: int, seed: int
    ):
        g = grade or {}
        self.width, self.height = int(width), int(height)
        self.grain = _clamp01(g.get("grain", 0.0))
        self.vignette = _clamp01(g.get("vignette", 0.0))
        self.halation = _clamp01(g.get("halation", 0.0))
        try:
            self.warmth = max(-1.0, min(1.0, float(g.get("warmth", 0.0))))
        except (TypeError, ValueError):
            self.warmth = 0.0
        self.seed = int(seed)
        self._vignette_mask: Image.Image | None = None
        self._grain_tiles: list[Image.Image] = []

    @property
    def active(self) -> bool:
        return bool(self.grain or self.vignette or self.halation or self.warmth)

    # -- stages ------------------------------------------------------------
    def _apply_warmth(self, frame: Image.Image) -> Image.Image:
        k = self.warmth * 0.10
        r_lut = [min(255, max(0, round(v * (1.0 + k)))) for v in range(256)]
        b_lut = [min(255, max(0, round(v * (1.0 - k)))) for v in range(256)]
        r, g, b = frame.split()
        return Image.merge("RGB", (r.point(r_lut), g, b.point(b_lut)))

    def _apply_halation(self, frame: Image.Image) -> Image.Image:
        small = frame.resize(
            (max(1, self.width // 4), max(1, self.height // 4)),
            Image.Resampling.BILINEAR,
        )
        luma = small.convert("L").point(
            [
                0 if v < HALATION_THRESHOLD else round((v - HALATION_THRESHOLD) * 3.0)
                for v in range(256)
            ]
        )
        radius = max(2.0, self.width / 120.0)
        glow = luma.filter(ImageFilter.GaussianBlur(radius))
        glow = glow.resize((self.width, self.height), Image.Resampling.BILINEAR)
        strength = self.halation * 0.55
        tint = Image.new("RGB", (self.width, self.height), HALATION_TINT)
        lit = ImageChops.multiply(tint, Image.merge("RGB", (glow, glow, glow)))
        lit = lit.point([round(v * strength) for v in range(256)] * 3)
        return ImageChops.screen(frame, lit)

    def _get_vignette(self) -> Image.Image:
        if self._vignette_mask is None:
            # radial falloff built at low res then upscaled (cheap, smooth)
            w, h = max(8, self.width // 8), max(8, self.height // 8)
            mask = Image.radial_gradient("L").resize((w, h), Image.Resampling.BICUBIC)
            # radial_gradient: 0 centre → 255 edge; shape so the centre stays clean
            lut = [
                round(255 * (1.0 - self.vignette * ((v / 255.0) ** 2.2)))
                for v in range(256)
            ]
            mask = mask.point(lut).resize(
                (self.width, self.height), Image.Resampling.BICUBIC
            )
            self._vignette_mask = Image.merge("RGB", (mask, mask, mask))
        return self._vignette_mask

    def _get_grain(self, frame_idx: int) -> Image.Image:
        if not self._grain_tiles:
            rng = random.Random(self.seed ^ 0x5EED)
            amp = self.grain * GRAIN_LEVELS / 128.0
            lut = [min(255, max(0, round(128 + (v - 128) * amp))) for v in range(256)]
            for _ in range(GRAIN_TILES):
                raw = rng.randbytes(self.width * self.height)
                tile = Image.frombytes("L", (self.width, self.height), raw).point(lut)
                self._grain_tiles.append(Image.merge("RGB", (tile, tile, tile)))
        return self._grain_tiles[frame_idx % GRAIN_TILES]

    # -- entry point -------------------------------------------------------
    def __call__(self, frame: Image.Image, frame_idx: int = 0) -> Image.Image:
        if not self.active:
            return frame
        if frame.mode != "RGB":
            frame = frame.convert("RGB")
        if frame.size != (self.width, self.height):
            raise ValueError(
                f"Grader built for {self.width}x{self.height}, got frame {frame.size}"
            )
        if self.warmth:
            frame = self._apply_warmth(frame)
        if self.halation:
            frame = self._apply_halation(frame)
        if self.vignette:
            frame = ImageChops.multiply(frame, self._get_vignette())
        if self.grain:
            frame = ImageChops.add(frame, self._get_grain(frame_idx), 1.0, -128)
        return frame


def grader_for_board(
    board: dict[str, Any], width: int, height: int, seed: int
) -> Grader:
    """Build the Grader from a board whose style has been resolved (apply_style)."""
    style = board.get("style")
    grade = style.get("grade") if isinstance(style, dict) else None
    return Grader(grade if isinstance(grade, dict) else None, width, height, seed)
