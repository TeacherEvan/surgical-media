"""Tests for the pure-Python parametric 3D projection renderer."""

import sys
from pathlib import Path

import pytest
from PIL import ImageChops

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from canvas import SupersampledCanvas
from software_3d_projection import (
    PerspectiveCamera3D,
    generate_box_mesh,
    generate_torus_stellarator_mesh,
    render_3d_scene_and_track,
)

W, H = 320, 180


def _axis_camera():
    return PerspectiveCamera3D(eye=(0.0, -6.0, 0.0), target=(0.0, 0.0, 0.0))


def test_project_point_on_optical_axis():
    cam = _axis_camera()
    u, v, z_depth, visible = cam.project_point((0.0, 0.0, 0.0))
    assert u == pytest.approx(0.5, abs=1e-6)
    assert v == pytest.approx(0.5, abs=1e-6)
    assert z_depth > 0.0
    assert visible is True


def test_project_point_behind_eye_is_invisible():
    cam = _axis_camera()
    # straight behind the eye along the optical axis
    u, v, z_depth, visible = cam.project_point((0.0, -16.0, 0.0))
    assert (u, v) == (0.5, 0.5)  # collapsed to screen centre
    assert z_depth <= 0.0
    assert visible is False


def test_project_point_off_axis_ordering():
    cam = _axis_camera()
    right_pt = cam.project_point((2.0, 0.0, 0.0))
    left_pt = cam.project_point((-2.0, 0.0, 0.0))
    assert right_pt[0] > 0.5 > left_pt[0]
    above_pt = cam.project_point((0.0, 0.0, 1.5))
    below_pt = cam.project_point((0.0, 0.0, -1.5))
    assert above_pt[1] < 0.5 < below_pt[1]


def test_generate_box_mesh_structure():
    faces = generate_box_mesh((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), "#112233", "#445566")
    verts = {v for face in faces for v in face["verts"]}
    assert len(verts) == 8
    assert len(faces) == 6
    for face in faces:
        nx, ny, nz = face["normal"]
        assert abs(nx * nx + ny * ny + nz * nz - 1.0) < 1e-6
        assert face["color_hex"] == "#112233"
        assert face["edge_hex"] == "#445566"


def test_generate_torus_stellarator_mesh_structure():
    polys = generate_torus_stellarator_mesh(0.5)
    assert len(polys) == 32 * 14
    coils = [p for p in polys if p["emissive"] and p["color_hex"] == "#F59E0B"]
    assert coils, "coil segments should be emissive amber"
    for p in polys:
        nx, ny, nz = p["normal"]
        assert abs(nx * nx + ny * ny + nz * nz - 1.0) < 1e-3


def _exploded_spec():
    return {
        "category": "exploded_hardware_3d",
        "camera_3d": {"radius_start": 6.2, "radius_end": 4.5},
        "anchors_3d": [
            {
                "anchor_id": "anchor_compute_die",
                "label": "COMPUTE DIE",
                "metric": "94 TFLOPS",
                "accent_hex": "#FACC15",
                "local_pos": [0.0, 0.0, 0.0],
            },
            {
                "anchor_id": "anchor_vapor_chamber",
                "label": "VAPOR CHAMBER",
                "metric": "-12 C",
                "accent_hex": "#38BDF8",
                "local_pos": [0.0, 0.0, 0.0],
            },
        ],
    }


def _changed_pixels(region) -> int:
    data = region.tobytes()
    return sum(
        1 for i in range(0, len(data), 3) if data[i] or data[i + 1] or data[i + 2]
    )


@pytest.mark.parametrize("t_norm", [0.0, 1.0])
def test_render_exploded_stack_tracks_anchors(t_norm):
    background = "#050811"
    cv = SupersampledCanvas(W, H, scale=2, background=background)
    tracked = render_3d_scene_and_track(cv, _exploded_spec(), t_norm)
    assert len(tracked) == 2
    required = {
        "anchor_id",
        "label",
        "metric",
        "accent_hex",
        "u",
        "v",
        "z_depth",
        "visible",
    }
    for entry in tracked:
        assert required <= set(entry)
        assert 0.0 <= entry["u"] <= 1.0
        assert 0.0 <= entry["v"] <= 1.0

    img = cv.final().convert("RGB")
    blank = SupersampledCanvas(W, H, scale=2, background=background).final()
    diff = ImageChops.difference(img, blank.convert("RGB"))
    # central band must contain painted 3D content, not raw background
    centre = diff.crop((W // 4, H // 4, 3 * W // 4, 3 * H // 4))
    assert _changed_pixels(centre) > 50


def test_render_unknown_category_raises_not_implemented():
    cv = SupersampledCanvas(W, H, scale=2, background="#050811")
    with pytest.raises(NotImplementedError):
        render_3d_scene_and_track(cv, {"category": "warp_drive_3d"}, 0.5)
