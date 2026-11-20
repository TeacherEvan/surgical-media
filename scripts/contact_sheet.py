#!/usr/bin/env python3
"""contact_sheet.py — one labelled tile per scene, for fast style review by eye.

Renders per-scene thumbnails (``render_engine.render_thumbnails``, including the
style grade) and tiles them into a single PNG::

    python3 scripts/contact_sheet.py examples/ref_soft_clay_poem.json /tmp/sheet.png
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from canvas import get_font
from PIL import Image, ImageDraw
from render_engine import render_thumbnails


def build_sheet(
    thumbs: list[Path], out: Path, cols: int = 3, tile_w: int = 480, label_h: int = 26
) -> Path:
    if not thumbs:
        raise ValueError("no thumbnails to tile")
    imgs = [Image.open(p).convert("RGB") for p in thumbs]
    ratio = imgs[0].height / imgs[0].width
    tile_h = round(tile_w * ratio)
    cols = max(1, min(cols, len(imgs)))
    rows = -(-len(imgs) // cols)
    gap = 8
    sheet = Image.new(
        "RGB",
        (
            cols * tile_w + (cols + 1) * gap,
            rows * (tile_h + label_h) + (rows + 1) * gap,
        ),
        (24, 24, 28),
    )
    draw = ImageDraw.Draw(sheet)
    font = get_font(15, bold=False)
    for i, (img, path) in enumerate(zip(imgs, thumbs)):
        x = gap + (i % cols) * (tile_w + gap)
        y = gap + (i // cols) * (tile_h + label_h + gap)
        sheet.paste(
            img.resize((tile_w, tile_h), Image.Resampling.LANCZOS), (x, y + label_h)
        )
        draw.text(
            (x + 2, y + 4),
            f"{i + 1:02d} · {path.stem}",
            fill=(225, 225, 230),
            font=font,
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Per-scene contact sheet for a storyboard")
    ap.add_argument("storyboard", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--cols", type=int, default=3)
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="sm_sheet_") as tmp:
        thumbs = render_thumbnails(args.storyboard, Path(tmp), scale=1)
        build_sheet(thumbs, args.output, cols=args.cols)
    print(f"contact_sheet: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
