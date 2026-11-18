"""blender_plate tests — offline where possible; Blender render skips without blender."""

import shutil
import subprocess
import sys
from pathlib import Path

import blender_plate
import pytest
from PIL import Image

REPO = Path(__file__).resolve().parent.parent


def _make_png(path, size=(220, 120), color=(200, 30, 30)):
    Image.new("RGB", size, color).save(path)
    return path


def test_png_dimensions_reads_ihdr(tmp_path):
    png = tmp_path / "t.png"
    _make_png(png, size=(321, 177))
    assert blender_plate.png_dimensions(png) == (321, 177)


def test_png_dimensions_rejects_non_png(tmp_path):
    bad = tmp_path / "t.jpg"
    bad.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    with pytest.raises(ValueError):
        blender_plate.png_dimensions(bad)


def test_main_without_blender_returns_2(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(blender_plate.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["blender_plate.py", "--kind", "earth", "--out", str(tmp_path / "x.png")],
    )
    assert blender_plate.main() == 2
    assert "Blender not found" in capsys.readouterr().err


@pytest.mark.skipif(
    shutil.which("blender") is None, reason="blender not installed — optional path"
)
def test_blender_renders_nonflat_transparent_plate(tmp_path):
    out = tmp_path / "plate.png"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "blender_plate.py"),
            "--kind",
            "iceberg",
            "--out",
            str(out),
            "--size",
            "200x120",
            "--seed",
            "7",
        ],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert blender_plate.png_dimensions(out) == (200, 120)
    img = Image.open(out).convert("RGBA")
    alpha = list(img.getchannel("A").getdata())
    assert min(alpha) == 0  # transparent corners for compositing
    assert max(alpha) == 255  # opaque subject
    rgb = img.convert("RGB")
    assert len(set(rgb.getdata())) > 32  # a real 3D render, not a flat fill
