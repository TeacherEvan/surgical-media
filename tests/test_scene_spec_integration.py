"""Integration tests: scene_spec scenes end-to-end through validation and paint.

Covers the board contract (elements OR scene_spec), the runtime validator vs
JSON Schema parity, the bundled hybrid example, and one frame of actual
rendering via render_engine.paint_frame (scale=1 to keep it fast).
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import scene_router
import storyboard
from render_engine import paint_frame

EXAMPLE = REPO / "examples" / "hybrid_3d_storyboard.json"
SCHEMA = REPO / "schemas" / "storyboard.schema.json"


def _spec_board():
    return {
        "meta": {"title": "Spec Integration Board", "seed": 7},
        "format": {"width": 320, "height": 180, "fps": 24},
        "scenes": [
            {
                "scene_id": "spec_scene",
                "archetype": "mixed",
                "duration_sec": 0.5,
                "fade_in_sec": 0.0,
                "fade_out_sec": 0.0,
                "scene_spec": {
                    "category": "exploded_hardware_3d",
                    "explode_factor": 0.8,
                    "hud_title": "TEST STACK",
                    "camera_3d": {
                        "radius_start": 7.0,
                        "radius_end": 6.0,
                        "azimuth_start_deg": -30.0,
                        "azimuth_end_deg": 20.0,
                        "elevation_deg": 22.0,
                        "focal_length_mm": 50.0,
                    },
                    "anchors_3d": [
                        {
                            "anchor_id": "anchor_compute_die",
                            "label": "COMPUTE DIE",
                            "metric": "5NM-CLASS",
                            "local_pos": [0.0, 0.0, 0.18],
                            "accent_hex": "#FACC15",
                        }
                    ],
                },
            }
        ],
    }


def _validator():
    jsonschema = pytest.importorskip("jsonschema")
    return jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8"))
    )


# ---- validation contract ----------------------------------------------------


def test_spec_board_validates_clean():
    assert storyboard.validate_storyboard(_spec_board()) == []


def test_spec_board_without_spec_or_elements_fails():
    board = _spec_board()
    board["scenes"][0].pop("scene_spec")
    errors = storyboard.validate_storyboard(board)
    assert errors != []
    assert any("elements" in e for e in errors)


def test_spec_board_with_empty_elements_and_spec_rejected_by_both_validators():
    """`elements`, when present, must be non-empty even on scene_spec scenes."""
    board = _spec_board()
    board["scenes"][0]["elements"] = []
    errors = storyboard.validate_storyboard(board)
    assert any("elements" in e for e in errors)
    pytest.importorskip("jsonschema")
    schema_errors = list(_validator().iter_errors(board))
    assert schema_errors != []


def test_example_board_validates_clean():
    board = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert storyboard.validate_storyboard(board) == []


def test_example_board_passes_json_schema():
    pytest.importorskip("jsonschema")
    board = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    errors = list(_validator().iter_errors(board))
    assert errors == []


def test_bad_anchor_rejected_by_both_validators():
    board = _spec_board()
    board["scenes"][0]["scene_spec"]["anchors_3d"][0]["local_pos"] = [0.0, 0.0]
    runtime_errors = storyboard.validate_storyboard(board)
    assert any("local_pos" in e for e in runtime_errors)
    pytest.importorskip("jsonschema")
    schema_errors = list(_validator().iter_errors(board))
    assert schema_errors != []


def test_unknown_backend_rejected_by_runtime_validator():
    board = _spec_board()
    board["scenes"][0]["backend"] = "vulkan_vr"
    errors = storyboard.validate_storyboard(board)
    assert any("backend" in e for e in errors)


# ---- routing ----------------------------------------------------------------


def test_unsupported_camera_mode_and_lighting_preset_rejected_by_both():
    board = _spec_board()
    scene = board["scenes"][0]
    scene["scene_spec"]["camera_3d"]["mode"] = "crane_sweep"
    scene["scene_spec"]["lighting_preset"] = "scientific_void"
    runtime_errors = storyboard.validate_storyboard(board)
    assert any("mode" in e for e in runtime_errors)
    assert any("lighting_preset" in e for e in runtime_errors)
    pytest.importorskip("jsonschema")
    assert list(_validator().iter_errors(board)) != []


def test_unimplemented_category_rejected_at_validation_and_render():
    board = _spec_board()
    board["scenes"][0]["scene_spec"]["category"] = "network_topology_3d"
    errors = storyboard.validate_storyboard(board)
    assert any("not implemented" in e for e in errors)
    with pytest.raises(NotImplementedError):
        paint_frame(board["scenes"][0], 320, 180, 1, 7, 0, 24)


def test_blender_adapter_uses_shared_camera_defaults():
    from render_engine import _blender_adapter_spec

    adapted = _blender_adapter_spec({"category": "exploded_hardware_3d"})["camera"]
    assert adapted["radius_start"] == scene_router.CAMERA_3D_DEFAULTS["radius_start"]
    assert adapted["radius_end"] == scene_router.CAMERA_3D_DEFAULTS["radius_end"]
    assert adapted["aperture_fstop"] == scene_router.CAMERA_3D_DEFAULTS["fstop"]


def test_example_scenes_route_to_blender_hybrid():
    board = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    for scene in board["scenes"]:
        assert scene_router.route_scene(scene) == "blender_hybrid"


def test_manim_math_backend_validates_and_warns():
    board = _spec_board()
    scene = board["scenes"][0]
    scene["backend"] = "manim_math"
    scene["elements"] = [{"type": "background", "color": "#050811"}]
    assert storyboard.validate_storyboard(board) == []
    warnings = storyboard.lint_storyboard(board)
    assert any("manim_math" in w for w in warnings)


def test_paint_frame_manim_math_falls_back_to_elements():
    board = _spec_board()
    scene = board["scenes"][0]
    scene["backend"] = "manim_math"
    scene["elements"] = [{"type": "background", "color": "#050811"}]
    frame = paint_frame(scene, 320, 180, 1, 7, 0, 24)
    assert frame.mode == "RGB"
    assert frame.size == (320, 180)


# ---- actual pixels -----------------------------------------------------------


def test_paint_frame_renders_3d_content():
    scene = _spec_board()["scenes"][0]
    for local_idx in range(3):
        frame = paint_frame(scene, 320, 180, 1, 7, local_idx, 24)
        assert frame.mode == "RGB"
        assert frame.size == (320, 180)
        assert any(hi > lo for lo, hi in frame.getextrema())


def test_paint_frame_example_scene_renders():
    board = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    scene = board["scenes"][0]
    # mid-scene frame: fade-in is over, so any content draws visible pixels
    frame = paint_frame(scene, 320, 180, 1, 20261119, 12, 24)
    assert frame.size == (320, 180)
    assert any(hi > lo for lo, hi in frame.getextrema())
