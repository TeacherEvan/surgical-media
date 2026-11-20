#!/usr/bin/env python3
"""thumbnail_gen.py — pick the best CTR thumbnail frame from scene thumbnails.

Renders all scene thumbnails via ``render_thumbnails``, scores each frame,
writes the winner to ``--out`` as JPEG. Heuristics (advisory — review by eye):

- **contrast** — frame luminance spread (subject-on-background readability);
  approximated by (max-min)/255 of the frame.
- **legibility** — downscaled-to-168×94 fraction of non-white pixels
  (mobile feed legibility).
- **frame coverage** — global score = 0.55 floor; unusable frames (< 0.55
  total score) are reported as WARN but not fatal.

Monetization usage: thumbnails drive feed CTR; pick the frame with the most
visual punch while keeping small text legible at 168×94 (the feed width for
16:9 content). A top frame with embedded ≥3 word hook + contrast-rich face is
the YouTube-thumb sweet spot.

Usage:
    python3 scripts/thumbnail_gen.py --storyboard storyboard.json
        [--out dir/thumbnail.jpg] [--thumbnails-dir DIR] [--min-score 0.5]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_engine import render_thumbnails

MOBILE_FEED_WIDTH = 168  # vertical/square feed width proxy


def _frame_contrast(im: Image.Image) -> float:
    if im.width == 0 or im.height == 0:
        return 0.0
    extrema = im.convert("L").getextrema()  # single band -> (min, max)
    lo, hi = cast("tuple[int, int]", extrema)
    return float(hi - lo) / 255.0


def _frame_legibility(im: Image.Image) -> float:
    gray = im.convert("L").resize((MOBILE_FEED_WIDTH, 94), Image.Resampling.LANCZOS)
    data = gray.tobytes()
    if not data:
        return 0.0
    dark = sum(1 for b in data if b < 200)
    return dark / float(len(data))


def score_frame(path: Path) -> dict[str, float]:
    im = Image.open(path).convert("RGB")
    contrast = _frame_contrast(im)
    legibility = _frame_legibility(im)
    score = round(contrast * 0.55 + legibility * 0.45, 3)
    return {
        "contrast": round(contrast, 3),
        "legibility": round(legibility, 3),
        "score": score,
    }


def pick_thumbnail(thumbnails_dir: Path) -> tuple[Path, dict[str, Any]]:
    """Return (best frame, its score) — the highest-scoring frame."""
    best_path: Path | None = None
    best_score = -1.0
    best_meta: dict[str, Any] = {}
    for p in sorted(thumbnails_dir.glob("*.png")) + sorted(
        thumbnails_dir.glob("*.jpg")
    ):
        meta = score_frame(p)
        if meta["score"] > best_score:
            best_path, best_score, best_meta = p, meta["score"], meta
    assert best_path is not None, "no frames found"
    return best_path, best_meta


def generate_thumbnail(
    storyboard: Path,
    out_path: Path | None = None,
    thumbnails_dir: Path | None = None,
    min_score: float = 0.5,
    quality: int = 92,
    max_mb: float = 2.0,
) -> dict[str, Any]:
    """Render scene thumbnails and pick the best-scoring frame as JPEG."""
    out_path = out_path or Path(str(storyboard) + ".thumbnail.jpg")
    thumbnails_dir = thumbnails_dir or out_path.parent / ".thumbs"
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    thumbs = render_thumbnails(Path(storyboard), thumbnails_dir)
    if not thumbs:
        return {"ok": False, "reason": "no thumbnails rendered"}
    best, meta = pick_thumbnail(thumbnails_dir)
    meta["path"] = str(out_path)
    if meta["score"] < min_score:
        meta["ok"] = False
        return meta
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(best).convert("RGB")
    im.save(out_path, "JPEG", quality=quality)
    if out_path.stat().st_size > int(max_mb * 1024 * 1024):
        im.save(out_path, "JPEG", quality=max(60, quality - 40))
    meta["ok"] = True
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pick the best CTR thumbnail frame from scene thumbnails"
    )
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None, help="Output JPEG path")
    parser.add_argument(
        "--thumbnails-dir", type=Path, default=None, help="Where scene thumbnails live"
    )
    parser.add_argument("--min-score", type=float, default=0.5)
    parser.add_argument("--quality", type=int, default=92)
    args = parser.parse_args(argv)

    result = generate_thumbnail(
        args.storyboard,
        out_path=args.out,
        thumbnails_dir=args.thumbnails_dir,
        min_score=args.min_score,
        quality=args.quality,
    )
    print(json.dumps(result, indent=2))
    if not result.get("ok"):
        return 1
    print(
        f"thumbnail_gen: wrote {result['path']} (score {result['score']})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
