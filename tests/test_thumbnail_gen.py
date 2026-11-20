"""Unit + smoke tests for thumbnail_gen (scripts/thumbnail_gen.py)."""

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import thumbnail_gen as tg

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "examples" / "tri_archetype_storyboard.json"


def _blank_frame(path: Path, size=(800, 450), color=(5, 5, 8)) -> Path:
    Image.new("RGB", size, color).save(path, "PNG")
    return path


def test_score_frame_contrast_and_legibility():
    p = _blank_frame(Path("/tmp/opencode/blank_frame.png"))
    s = tg.score_frame(p)
    assert s["score"] < 0.5, s  # low contrast + low legibility on blank frame


def test_score_frame_high_contrast_punchy():
    im = Image.new("RGB", (800, 450), (255, 255, 255))
    for x in range(800):
        im.putpixel((x, 0), (0, 0, 0))
    for y in range(450):
        im.putpixel((0, y), (0, 0, 0))
    p = Path("/tmp/opencode/frame_contrast.png")
    im.save(p, "PNG")
    s = tg.score_frame(p)
    assert s["contrast"] > 0.5, s


def test_pick_thumbnail_selects_best():
    d = Path("/tmp/opencode/tg_frames")
    d.mkdir(parents=True, exist_ok=True)
    _blank_frame(d / "a.png", color=(5, 5, 8))
    # b: dark background with a bright white subject → higher contrast
    im = Image.new("RGB", (800, 450), (10, 12, 14))
    for x in range(240, 560):
        for y in range(170, 280):
            im.putpixel((x, y), (255, 255, 255))
    im.save(d / "b.png", "PNG")
    best, meta = tg.pick_thumbnail(d)
    assert best == d / "b.png", (best, meta)
    assert meta["score"] >= 0.5
    assert meta["contrast"] > 0.5


def test_generate_thumbnail_on_example_board(tmp_path):
    out = tmp_path / "thumb.jpg"
    result = tg.generate_thumbnail(
        EXAMPLE, out_path=out, thumbnails_dir=tmp_path / "thumbs"
    )
    assert result["ok"] is True
    assert out.is_file()
    assert out.stat().st_size < 2 * 1024 * 1024
    with Image.open(out) as im:
        assert im.format == "JPEG"
