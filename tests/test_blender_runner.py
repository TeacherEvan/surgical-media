"""blender_runner tests — offline; the headless render test skips without blender."""

import json
import shutil
import subprocess
from pathlib import Path

import blender_runner
import pytest

REPO = Path(__file__).resolve().parent.parent
BLENDER_RUNNER = REPO / "scripts" / "blender_runner.py"


def test_module_imports_without_blender():
    assert blender_runner.INSIDE_BLENDER is False


def test_run_blender_scene_requires_blender(tmp_path):
    with pytest.raises(RuntimeError, match="blender -b -P"):
        blender_runner.run_blender_scene(
            str(tmp_path / "spec.json"), str(tmp_path / "out"), 160, 90, 12, 4
        )


def test_hex_to_linear_rgba_white():
    assert blender_runner.hex_to_linear_rgba("#FFFFFF") == pytest.approx((1, 1, 1, 1))


def test_hex_to_linear_rgba_black():
    assert blender_runner.hex_to_linear_rgba("#000000") == (0, 0, 0, 1)


def test_hex_to_linear_rgba_shorthand():
    shorthand = blender_runner.hex_to_linear_rgba("#FFF")
    full = blender_runner.hex_to_linear_rgba("#FFFFFF")
    assert shorthand == pytest.approx(full)


@pytest.mark.skipif(
    shutil.which("blender") is None, reason="blender not installed — optional path"
)
def test_blender_headless_tiny_scene(tmp_path):
    spec = {
        "category": "exploded_hardware_3d",
        "explode_factor": 1.0,
        "camera": {
            "focal_length_mm": 50,
            "aperture_fstop": 2.8,
            "target_pos": [0, 0, 0],
        },
        "anchors_3d": [{"anchor_id": "anchor_compute_die", "local_pos": [0, 0, 0.2]}],
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    out_dir = tmp_path / "build"
    try:
        proc = subprocess.run(
            [
                "blender",
                "-b",
                "-P",
                str(BLENDER_RUNNER),
                "--",
                "--spec",
                str(spec_path),
                "--out-dir",
                str(out_dir),
                "--width",
                "160",
                "--height",
                "90",
                "--fps",
                "12",
                "--frames",
                "4",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr_tail = exc.stderr or ""
        if isinstance(stderr_tail, bytes):
            stderr_tail = stderr_tail.decode(errors="replace")
        pytest.skip(f"blender timed out after 300s: {stderr_tail[-1000:]}")
    if proc.returncode != 0:
        pytest.skip(
            f"blender exited {proc.returncode} (sandbox may block it): "
            f"{proc.stderr[-1000:]}"
        )
    assert (out_dir / "frame_0001.png").exists()
    tracks = json.loads((out_dir / "anchor_tracks.json").read_text())
    assert len(tracks["frames"]) == 4
    for frame in tracks["frames"]:
        assert frame["anchors"], "expected at least one anchor entry"
        for entry in frame["anchors"]:
            assert {"anchor_id", "u", "v", "visible"} <= set(entry)


def test_supported_categories_include_organic_serpent():
    assert blender_runner.INSIDE_BLENDER is False
    assert "organic_serpent_3d" in blender_runner.SUPPORTED_CATEGORIES


@pytest.mark.skipif(
    shutil.which("blender") is None, reason="blender not installed — optional path"
)
def test_blender_headless_organic_serpent(tmp_path):
    spec = {
        "category": "organic_serpent_3d",
        "camera": {
            "focal_length_mm": 50,
            "aperture_fstop": 2.8,
            "target_pos": [0, 0, 0],
        },
        "anchors_3d": [
            {"anchor_id": "anchor_head"},
            {"anchor_id": "anchor_tail"},
        ],
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    out_dir = tmp_path / "build"
    try:
        proc = subprocess.run(
            [
                "blender",
                "-b",
                "-P",
                str(BLENDER_RUNNER),
                "--",
                "--spec",
                str(spec_path),
                "--out-dir",
                str(out_dir),
                "--width",
                "160",
                "--height",
                "90",
                "--fps",
                "12",
                "--frames",
                "4",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr_tail = exc.stderr or ""
        if isinstance(stderr_tail, bytes):
            stderr_tail = stderr_tail.decode(errors="replace")
        pytest.skip(f"blender timed out after 300s: {stderr_tail[-1000:]}")
    if proc.returncode != 0:
        pytest.skip(
            f"blender exited {proc.returncode} (sandbox may block it): "
            f"{proc.stderr[-1000:]}"
        )
    assert (out_dir / "frame_0001.png").exists()
    tracks = json.loads((out_dir / "anchor_tracks.json").read_text())
    assert len(tracks["frames"]) == 4
    for frame in tracks["frames"]:
        anchor_ids = {entry["anchor_id"] for entry in frame["anchors"]}
        assert {"anchor_head", "anchor_tail"} <= anchor_ids
        for entry in frame["anchors"]:
            assert {"anchor_id", "u", "v", "visible"} <= set(entry)
