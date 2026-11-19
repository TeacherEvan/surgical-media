#!/usr/bin/env python3
"""canvas.py — supersampled canvas, additive bloom, and platform safe zones.

Pillow's ImageDraw has no sub-pixel anti-aliasing on diagonals or circles.
Every frame is therefore drawn at ``scale``x the target resolution (default
2x) and downsampled (integer supersample ⇒ BOX average; otherwise LANCZOS) in :meth:`SupersampledCanvas.final`.

All draw calls take *design-space* pixels (the target-resolution coordinate
system of the storyboard). The world camera (see camera.py) maps design
pixels to screen pixels before the supersample factor is applied, giving
crisp strokes at any zoom.

Emissive primitives (gold locks, error reds, packet dots) are additionally
drawn into a black bloom buffer; the buffer is blurred at two radii (at
half resolution) and added onto the frame on export — a cheap dual-radius
Gaussian bloom that reads as glow on dark canvases. Buffers are RGB:
ImageDraw cannot alpha-blend, so translucency is pre-blended into opaque
tones instead (see references/ffmpeg-encoding.md).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

if TYPE_CHECKING:
    from camera import WorldCamera2D

_COLOR_CACHE: dict[str, RGBA] = {}

RGBA = tuple[int, int, int, int]
RGB = tuple[int, int, int]


def parse_color(value: str | Sequence[int], default_alpha: int = 255) -> RGBA:
    key = value if isinstance(value, str) else None
    if key is not None:
        cached = _COLOR_CACHE.get(key.strip().lstrip("#"))
        if cached is not None:
            return cached
    result = _parse_color_uncached(value, default_alpha)
    if key is not None:
        _COLOR_CACHE[key.strip().lstrip("#")] = result
    return result


def _parse_color_uncached(value: str | Sequence[int], default_alpha: int = 255) -> RGBA:
    """Parse '#RRGGBB' / '#RRGGBBAA' / [r,g,b(,a)] into an RGBA tuple."""
    if isinstance(value, (list, tuple)):
        if len(value) == 3:
            return (int(value[0]), int(value[1]), int(value[2]), default_alpha)
        if len(value) == 4:
            return cast(RGBA, tuple(int(c) for c in value))
        raise ValueError(f"color sequence must have 3 or 4 items, got {value!r}")
    s = str(value).strip().lstrip("#")
    if len(s) == 6:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), default_alpha)
    if len(s) == 8:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
    if len(s) == 3:  # #RGB shorthand
        return cast(RGBA, tuple(int(c * 2, 16) for c in s) + (default_alpha,))
    raise ValueError(f"unparseable color {value!r}; expected #RRGGBB[AA]")


_BUNDLED_FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_BUNDLED_CANDIDATES = [
    str(_BUNDLED_FONTS / "Inter-Bold.ttf"),
    str(_BUNDLED_FONTS / "Inter-SemiBold.ttf"),
    str(_BUNDLED_FONTS / "Inter-Regular.ttf"),
]

_FONT_CANDIDATES = [
    *_BUNDLED_CANDIDATES,
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Black.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
]
_FONT_MONO_CANDIDATES = [
    str(_BUNDLED_FONTS / "JetBrainsMono-Bold.ttf"),
    str(_BUNDLED_FONTS / "JetBrainsMono-Regular.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "C:/Windows/Fonts/consola.ttf",
]


def rgb(value: str | Sequence[int], default_alpha: int = 255) -> RGB:
    """parse_color without alpha — ImageDraw does no alpha compositing here."""
    return parse_color(value, default_alpha)[:3]


def find_font(mono: bool = False) -> str | None:
    for candidate in _FONT_MONO_CANDIDATES if mono else _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


_FONT_CACHE: dict[tuple[int, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def get_font(
    size: int, mono: bool = False, bold: bool = True
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = max(6, int(size))
    key = (size, mono)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    path = find_font(mono=mono)
    if path:
        try:
            cached = ImageFont.truetype(path, size=size)
            _FONT_CACHE[key] = cached
            return cached
        except OSError:
            pass
    try:
        cached = ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:  # very old Pillow
        cached = ImageFont.load_default()
    _FONT_CACHE[key] = cached
    return cached


# ---------------------------------------------------------------------------
# Platform safe zones (design px). 9:16 clears Shorts/Reels/TikTok caption bar
# and right-side icon column; 16:9 clears title-safe; 1:1 feed square.
# ---------------------------------------------------------------------------

SAFE_ZONES: dict[str, tuple[int, int, int, int]] = {
    "16:9": (96, 64, -96, -64),  # x0, y0, x1 (negative = from right edge), y1
    "9:16": (84, 220, -150, -440),
    "1:1": (80, 80, -80, -80),
}


def classify_aspect(width: int, height: int) -> str:
    ratio = width / max(1, height)
    if ratio > 1.4:
        return "16:9"
    if ratio < 0.75:
        return "9:16"
    return "1:1"


def safe_rect(width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = SAFE_ZONES[classify_aspect(width, height)]
    return (x0, y0, width + x1 if x1 < 0 else x1, height + y1 if y1 < 0 else y1)


def layout_zones(width: int, height: int) -> dict[str, tuple[int, int, int, int]]:
    """Non-overlapping canvas partitions: HUD header, primary stage, captions."""
    sx0, sy0, sx1, sy1 = safe_rect(width, height)
    span = sy1 - sy0
    if classify_aspect(width, height) == "9:16":
        hud = (sx0, sy0, sx1, sy0 + int(span * 0.12))
        stage = (sx0, hud[3], sx1, sy0 + int(span * 0.78))
    elif classify_aspect(width, height) == "1:1":
        hud = (sx0, sy0, sx1, sy0 + int(span * 0.11))
        stage = (sx0, hud[3], sx1, sy0 + int(span * 0.82))
    else:  # 16:9 — centered 75% stage
        inset = int((sx1 - sx0) * 0.125)
        hud = (sx0 + inset, sy0, sx1 - inset, sy0 + int(span * 0.14))
        stage = (sx0 + inset, hud[3], sx1 - inset, sy0 + int(span * 0.88))
    captions = (sx0, stage[3] + 8, sx1, sy1)
    return {
        "safe": (sx0, sy0, sx1, sy1),
        "hud": hud,
        "stage": stage,
        "captions": captions,
    }


# ---------------------------------------------------------------------------
class _Draw:
    """Shared draw implementation bound to one pixel buffer."""

    def __init__(self, canvas: SupersampledCanvas, image: Image.Image) -> None:
        self.canvas = canvas
        self.draw = ImageDraw.Draw(image)

    # point transform -----------------------------------------------------
    def _tp(self, x: float, y: float) -> tuple[float, float]:
        cv = self.canvas
        if cv.camera is None:
            px, py = x, y
        else:
            px = (x - cv._cx) * cv._z + cv.width / 2.0 + cv._ox
            py = (y - cv._cy) * cv._z + cv.height / 2.0 + cv._oy
        s = cv.scale
        return (px * s, py * s)

    def _tw(self, width_px: float) -> int:
        zoom = self.canvas._z if self.canvas.camera else 1.0
        return max(1, round(width_px * zoom * self.canvas.scale))

    # primitives ----------------------------------------------------------
    def line(
        self,
        p0: tuple[float, float],
        p1: tuple[float, float],
        fill: str | Sequence[int],
        width: float = 2.0,
    ) -> None:
        self.draw.line(
            [self._tp(*p0), self._tp(*p1)],
            fill=rgb(fill),
            width=self._tw(width),
            joint="curve",
        )

    def polyline(
        self,
        points: Iterable[tuple[float, float]],
        fill: str | Sequence[int],
        width: float = 2.0,
        closed: bool = False,
    ) -> None:
        pts = [self._tp(x, y) for x, y in points]
        if closed and len(pts) > 2:
            pts.append(pts[0])
        self.draw.line(pts, fill=rgb(fill), width=self._tw(width), joint="curve")

    def rectangle(
        self,
        box: tuple[float, float, float, float],
        outline: str | Sequence[int] | None = None,
        fill: str | Sequence[int] | None = None,
        width: float = 2.0,
        radius: float = 0.0,
    ) -> None:
        x0, y0, x1, y1 = box
        p0 = self._tp(x0, y0)
        p1 = self._tp(x1, y1)
        xy = [
            min(p0[0], p1[0]),
            min(p0[1], p1[1]),
            max(p0[0], p1[0]),
            max(p0[1], p1[1]),
        ]
        outline_ink = rgb(outline) if outline else None
        fill_ink = rgb(fill) if fill else None
        width_ink = self._tw(width)
        if radius > 0:
            self.draw.rounded_rectangle(
                xy,
                radius=radius * self.canvas.scale,
                outline=outline_ink,
                fill=fill_ink,
                width=width_ink,
            )
        else:
            self.draw.rectangle(xy, outline=outline_ink, fill=fill_ink, width=width_ink)

    def ellipse(
        self,
        box: tuple[float, float, float, float],
        outline: str | Sequence[int] | None = None,
        fill: str | Sequence[int] | None = None,
        width: float = 2.0,
    ) -> None:
        x0, y0, x1, y1 = box
        p0 = self._tp(x0, y0)
        p1 = self._tp(x1, y1)
        xy = [
            min(p0[0], p1[0]),
            min(p0[1], p1[1]),
            max(p0[0], p1[0]),
            max(p0[1], p1[1]),
        ]
        self.draw.ellipse(
            xy,
            outline=rgb(outline) if outline else None,
            fill=rgb(fill) if fill else None,
            width=self._tw(width),
        )

    def arc(
        self,
        box: tuple[float, float, float, float],
        start_deg: float,
        end_deg: float,
        fill: str | Sequence[int],
        width: float = 2.0,
    ) -> None:
        x0, y0, x1, y1 = box
        p0 = self._tp(x0, y0)
        p1 = self._tp(x1, y1)
        xy = [
            min(p0[0], p1[0]),
            min(p0[1], p1[1]),
            max(p0[0], p1[0]),
            max(p0[1], p1[1]),
        ]
        self.draw.arc(
            xy,
            start=start_deg,
            end=end_deg,
            fill=rgb(fill),
            width=self._tw(width),
        )

    def polygon(
        self,
        points: Iterable[tuple[float, float]],
        outline: str | Sequence[int] | None = None,
        fill: str | Sequence[int] | None = None,
    ) -> None:
        pts = [self._tp(x, y) for x, y in points]
        self.draw.polygon(
            pts,
            outline=rgb(outline) if outline else None,
            fill=rgb(fill) if fill else None,
        )

    def text(
        self,
        pos: tuple[float, float],
        text: object,
        fill: str | Sequence[int],
        size: float = 32.0,
        mono: bool = False,
        anchor: str = "la",
        stroke_fill: str | Sequence[int] | None = None,
        stroke_width: float = 0.0,
        camera_scaled: bool = True,
    ) -> None:
        s = self.canvas.scale
        zoom = self.canvas._z if (self.canvas.camera and camera_scaled) else 1.0
        font = get_font(round(size * zoom * s), mono=mono)
        px, py = self._tp(*pos)
        self.draw.text(
            (px, py),
            str(text),
            font=font,
            fill=rgb(fill),
            anchor=anchor,
            stroke_fill=rgb(stroke_fill) if stroke_fill else None,
            stroke_width=round(stroke_width * zoom * s),
        )


class SupersampledCanvas:
    """2x (or N-x) supersampled scene surface with additive bloom."""

    def __init__(
        self,
        width: int,
        height: int,
        scale: int = 2,
        camera: WorldCamera2D | None = None,
        background: str = "#000000",
    ) -> None:
        if scale < 1:
            raise ValueError("scale must be >= 1")
        self.width, self.height, self.scale = int(width), int(height), int(scale)
        self.camera = camera
        self.frame_t = 0.0
        self.trauma = 0.0
        self.time_sec = 0.0
        self._z = 1.0
        self._cx = 0.0
        self._cy = 0.0
        self._ox = 0.0  # shake offset x
        self._oy = 0.0  # shake offset y
        base = rgb(background)
        self.image = Image.new(
            "RGB", (self.width * self.scale, self.height * self.scale), base
        )
        self.bloom_image = Image.new(
            "RGB", (self.width * self.scale, self.height * self.scale), (0, 0, 0)
        )
        self.draw_ = _Draw(self, self.image)
        self.bloom = _Draw(self, self.bloom_image)

    # main buffer ----------------------------------------------------------
    def set_frame(self, t: float, time_sec: float, trauma: float = 0.0) -> None:
        self.frame_t = max(0.0, min(1.0, t))
        self.time_sec = time_sec
        self.trauma = max(0.0, min(1.0, trauma))
        # bake the per-frame affine once; _tp must not re-evaluate easings per point
        cam = self.camera
        if cam is not None:
            self._z = cam.zoom_at(self.frame_t)
            self._cx, self._cy = cam._center
            if self.trauma > 0.0:
                self._ox, self._oy = cam.shake_offset(time_sec, self.trauma)
            else:
                self._ox = self._oy = 0.0
        else:
            self._z = 1.0
            self._cx = self.width / 2.0
            self._cy = self.height / 2.0
            self._ox = self._oy = 0.0

    def line(self, *a: Any, **kw: Any) -> None:
        self.draw_.line(*a, **kw)

    def polyline(self, *a: Any, **kw: Any) -> None:
        self.draw_.polyline(*a, **kw)

    def rectangle(self, *a: Any, **kw: Any) -> None:
        self.draw_.rectangle(*a, **kw)

    def ellipse(self, *a: Any, **kw: Any) -> None:
        self.draw_.ellipse(*a, **kw)

    def arc(self, *a: Any, **kw: Any) -> None:
        self.draw_.arc(*a, **kw)

    def polygon(self, *a: Any, **kw: Any) -> None:
        self.draw_.polygon(*a, **kw)

    def text(self, *a: Any, **kw: Any) -> None:
        self.draw_.text(*a, **kw)

    # bloom buffer (additive light) -----------------------------------------
    def bloom_line(self, *a: Any, **kw: Any) -> None:
        self.bloom.line(*a, **kw)

    def bloom_polyline(self, *a: Any, **kw: Any) -> None:
        self.bloom.polyline(*a, **kw)

    def bloom_rectangle(self, *a: Any, **kw: Any) -> None:
        self.bloom.rectangle(*a, **kw)

    def bloom_ellipse(self, *a: Any, **kw: Any) -> None:
        self.bloom.ellipse(*a, **kw)

    def bloom_arc(self, *a: Any, **kw: Any) -> None:
        self.bloom.arc(*a, **kw)

    def bloom_polygon(self, *a: Any, **kw: Any) -> None:
        self.bloom.polygon(*a, **kw)

    def bloom_text(self, *a: Any, **kw: Any) -> None:
        self.bloom.text(*a, **kw)

    # export -----------------------------------------------------------------
    def final(self) -> Image.Image:
        """Downsample + composite bloom → target-resolution RGB image."""
        size = (self.width, self.height)
        half = (max(1, size[0] // 2), max(1, size[1] // 2))
        # exact integer Nx SSAA: BOX is the ideal average kernel and >> cheaper than LANCZOS
        downsample = (
            Image.Resampling.BOX if self.scale >= 2 else Image.Resampling.LANCZOS
        )
        base = self.image.resize(size, downsample)
        # bloom is low-frequency by construction — run the pyramid at half res
        bloom_rgb = self.bloom_image.resize(half, Image.Resampling.LANCZOS)
        tight = bloom_rgb.filter(
            ImageFilter.GaussianBlur(radius=max(1, half[0] // 240))
        )
        wide = bloom_rgb.filter(ImageFilter.GaussianBlur(radius=max(3, half[0] // 80)))
        halo = ImageChops.add(
            tight, Image.blend(Image.new("RGB", half, (0, 0, 0)), wide, 0.6)
        )
        halo = halo.resize(size, Image.Resampling.LANCZOS)
        return ImageChops.add(base, halo)
