"""elements/media.py — licensed photograph plates (Ken Burns, backdrop blur, credits)."""

from __future__ import annotations

import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

from canvas import SupersampledCanvas, get_font
from easings import ease_out_expo
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from elements._shared import ElementContext, _smoothstep

_IMAGE_CACHE: OrderedDict[tuple[str, int], Image.Image] = OrderedDict()
_BACKDROP_BLUR_CACHE: OrderedDict[
    tuple[str, int, int, int, float, float], Image.Image
] = OrderedDict()


def _load_image(path: str) -> Image.Image | None:
    try:
        resolved = Path(path).resolve()
        key = (str(resolved), resolved.stat().st_mtime_ns)
    except OSError as exc:
        print(f"image element: cannot stat {path}: {exc}", file=sys.stderr)
        return None
    img = _IMAGE_CACHE.get(key)
    if img is None:
        try:
            with Image.open(resolved) as opened:
                opened.load()
                img = opened.convert("RGB")
        except (OSError, ValueError) as exc:
            print(f"image element: cannot decode {path}: {exc}", file=sys.stderr)
            return None
        _IMAGE_CACHE[key] = img
        while len(_IMAGE_CACHE) > 32:
            _IMAGE_CACHE.popitem(last=False)
    else:
        _IMAGE_CACHE.move_to_end(key)
    return img


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def paint_image(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    """Raster image element: cover/contain, Ken Burns drift, fade-in, credit line.

    Images are backdrop plates: painted screen-fixed in design space (no
    camera transform — a full-bleed plate panning with the camera would
    expose canvas edges). Motion comes from ``kb_zoom``. ``src`` is absolute
    or relative to the storyboard file. Gradients/scrims are the caller's job.
    """
    src = el.get("src")
    if not src:
        print("image element missing 'src'", file=sys.stderr)
        return
    path = Path(str(src))
    if not path.is_absolute():
        path = Path(ctx.base_dir or ".") / path
    if not path.is_file():
        print(f"image element: src not found: {path}", file=sys.stderr)
        return
    img = _load_image(str(path))
    if img is None:
        return
    iw, ih = img.size
    if iw < 8 or ih < 8:
        print(f"image element: {path} too small ({iw}x{ih})", file=sys.stderr)
        return

    raw_box = el.get("box", [0, 0, ctx.width, ctx.height])
    if not isinstance(raw_box, (list, tuple)) or len(raw_box) != 4:
        raw_box = [0, 0, ctx.width, ctx.height]
    x0, y0, x1, y1 = (float(v) for v in raw_box)
    if x1 <= x0 or y1 <= y0:
        return

    scale = cv.scale
    bx0, by0 = round(x0 * scale), round(y0 * scale)
    bx1, by1 = round(x1 * scale), round(y1 * scale)
    bw, bh = bx1 - bx0, by1 - by0
    if bw <= 0 or bh <= 0:
        return

    progress = ease_out_expo(_smoothstep(0.0, 1.0, ctx.t))
    kb_zoom = float(el.get("kb_zoom", 1.08))
    zoom = 1.0 + (kb_zoom - 1.0) * progress

    fade_in = max(0.0, float(el.get("fade_in_sec", 0.6)))
    reveal = (
        1.0
        if fade_in <= 0.0
        else ease_out_expo(_smoothstep(0.0, fade_in, ctx.local_time))
    )

    fit = str(el.get("fit", "cover"))
    if fit == "backdrop_blur":
        # "social bleed": cover-crop the plate, blur + dim it to a backdrop,
        # then paste the full contained plate above it — keeps landscape
        # plates whole on 9:16 canvases. ``anchor_y`` (0..1) positions the
        # plate in the remaining vertical space (0 = top, 0.5 = centered).
        blur = float(el.get("blur", (x1 - x0) * 0.06)) * scale
        dim = float(el.get("dim", 0.72))
        anchor_y = min(1.0, max(0.0, float(el.get("anchor_y", 0.5))))
        bg_key = (str(path.resolve()), path.stat().st_mtime_ns, bw, bh, blur, dim)
        cached_bg = _BACKDROP_BLUR_CACHE.get(bg_key)
        if cached_bg is not None:
            _BACKDROP_BLUR_CACHE.move_to_end(bg_key)
            tile = cached_bg.copy()
        else:
            fill = max(bw / iw, bh / ih)
            crop_w = max(1, int(bw / fill))
            crop_h = max(1, int(bh / fill))
            left = (iw - crop_w) // 2
            top = (ih - crop_h) // 2
            tile = img.crop((left, top, left + crop_w, top + crop_h)).resize(
                (bw, bh), Image.Resampling.LANCZOS
            )
            if blur > 0.0:
                tile = tile.filter(ImageFilter.GaussianBlur(blur))
            if dim != 1.0:
                tile = ImageEnhance.Brightness(tile).enhance(dim)
            _BACKDROP_BLUR_CACHE[bg_key] = tile.copy()
            while len(_BACKDROP_BLUR_CACHE) > 16:
                _BACKDROP_BLUR_CACHE.popitem(last=False)
        fg_scale = min(bw / iw, bh / ih) / zoom
        nw, nh = max(1, int(iw * fg_scale)), max(1, int(ih * fg_scale))
        fg = img.resize((nw, nh), Image.Resampling.LANCZOS)
        fg_x = (bw - nw) // 2
        fg_y = int((bh - nh) * anchor_y)
        radius_px = int(float(el.get("radius", 0.0)) * scale)
        shadow = Image.new("L", (bw, bh), 0)
        s_off = max(4, int(bh * 0.018))
        s_rad = radius_px if radius_px > 0 else max(6, int(bh * 0.018))
        ImageDraw.Draw(shadow).rounded_rectangle(
            (fg_x + 2, fg_y + s_off, fg_x + nw + 2, fg_y + nh + s_off),
            radius=s_rad,
            fill=190,
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(6, int(bh * 0.022))))
        tile.paste((0, 0, 0), (0, 0), shadow)
        if radius_px > 0:
            tile.paste(fg, (fg_x, fg_y), _rounded_mask((nw, nh), radius_px))
        else:
            tile.paste(fg, (fg_x, fg_y))
    elif fit == "contain":
        tile = Image.new("RGB", (bw, bh), (0, 0, 0))
        fit_scale = min(bw / iw, bh / ih) / zoom
        nw, nh = max(1, int(iw * fit_scale)), max(1, int(ih * fit_scale))
        scaled = img.resize((nw, nh), Image.Resampling.LANCZOS)
        tile.paste(scaled, ((bw - nw) // 2, (bh - nh) // 2))
    else:  # cover — fill the box, crop around center
        fill = max(bw / iw, bh / ih) * zoom
        crop_w = min(iw, max(1, int(bw / fill)))
        crop_h = min(ih, max(1, int(bh / fill)))
        left, top = (iw - crop_w) // 2, (ih - crop_h) // 2
        tile = img.crop((left, top, left + crop_w, top + crop_h)).resize(
            (bw, bh), Image.Resampling.LANCZOS
        )

    if reveal < 1.0:
        tile = Image.blend(Image.new("RGB", (bw, bh), (0, 0, 0)), tile, reveal)

    # backdrop_blur applies radius to the foreground plate only
    radius = 0.0 if fit == "backdrop_blur" else float(el.get("radius", 0.0))
    if radius > 0.0:
        r = max(1, int(radius * scale))
        cv.image.paste(tile, (bx0, by0), _rounded_mask((bw, bh), r))
    else:
        cv.image.paste(tile, (bx0, by0))

    attribution = el.get("attribution")
    if attribution:
        # screen-fixed draw on the buffer — the camera would push an
        # edge-anchored credit off-canvas (it transforms position, not just scale)
        size = max(9, int((y1 - y0) * 0.020)) * scale
        max_w = int((x1 - x0) * scale) - int(24 * scale)
        font = get_font(int(size))
        while size > 8 * scale and font.getlength(str(attribution)) > max_w:
            size -= max(1, round(0.5 * scale))
            font = get_font(int(size))
        attr_y = el.get("attribution_y")
        if attr_y is not None:
            # explicit design-space y (e.g. 9:16 safe-zone above Shorts bottom chrome)
            credit_y = int(float(attr_y) * scale)
        else:
            credit_y = int(y1 * scale) - int(14 * scale)
        draw = ImageDraw.Draw(cv.image)
        draw.text(
            (int(x0 * scale) + int(12 * scale), credit_y),
            str(attribution),
            font=font,
            fill="#C7CEDE",
            anchor="ld",
            stroke_fill="#05070C",
            stroke_width=max(1, round(1.5 * scale)),
        )
