"""Failure-path tests: the render must never abort because a 3D pass, a
Blender plate, or Untouchable track data misbehaves. These paths are the
ones that cannot run inside CI's Blender-less environment, so they are
pinned down here with monkeypatching instead of integration.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import blender_runner
import render_engine
import software_3d_projection
from render_engine import _load_blender_tracks, _paint_scene_frame


def _spec_scene() -> dict:
    return {
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


def _paint_spec_frame(scene: dict, blender_dir: Path | None = None) -> object:
    return _paint_scene_frame(
        scene,
        width=160,
        height=96,
        scale=1,
        seed=7,
        local_idx=0,
        fps=24,
        trauma=0.0,
        blender_dir=blender_dir,
    )


# ---- software 3D pass fails -> render continues without the 3D layer --------


def test_software_3d_failure_does_not_abort_frame(monkeypatch, capsys):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("synthetic 3D failure")

    monkeypatch.setattr(software_3d_projection, "render_3d_scene_and_track", _boom)
    # NotImplementedError must NOT be swallowed — it signals an unimplemented category.
    frame = _paint_spec_frame(_spec_scene())
    assert frame is not None  # frame still painted, without the 3D layer
    err = capsys.readouterr().err
    assert "software 3D pass failed" in err


def test_software_3d_not_implemented_propagates(monkeypatch):
    def _ni(*_args, **_kwargs):
        raise NotImplementedError("synthetic unimplemented category")

    monkeypatch.setattr(software_3d_projection, "render_3d_scene_and_track", _ni)
    with pytest.raises(NotImplementedError):
        _paint_spec_frame(_spec_scene())


# ---- blender plate present but broken -> software fallback -------------------


def test_broken_blender_plate_falls_back_to_software(monkeypatch, tmp_path, capsys):
    (tmp_path / "frame_0001.png").write_bytes(b"definitely not a png")
    (tmp_path / "anchor_tracks.json").write_text(
        json.dumps({"frames": [{"anchors": []}]}), encoding="utf-8"
    )
    sentinel = [
        {
            "anchor_id": "anchor_compute_die",
            "label": "COMPUTE DIE",
            "metric": "5NM-CLASS",
            "accent_hex": "#FACC15",
            "u": 0.5,
            "v": 0.5,
            "visible": True,
        }
    ]
    calls = []

    def _fake_software(cv, spec, local_t):
        calls.append(local_t)
        return sentinel

    monkeypatch.setattr(
        software_3d_projection, "render_3d_scene_and_track", _fake_software
    )
    frame = _paint_spec_frame(_spec_scene(), blender_dir=tmp_path)
    assert frame is not None
    assert calls, "software 3D pass must run after a broken plate"
    err = capsys.readouterr().err
    assert "blender plate" in err and "software 3D fallback" in err


def test_unusable_anchor_tracks_yields_no_hud(tmp_path):
    # A structurally valid plate image with an unusable anchor_tracks.json
    # must drop the HUD, never abort.
    from PIL import Image

    Image.new("RGB", (64, 36), (5, 8, 16)).save(tmp_path / "frame_0001.png")
    (tmp_path / "anchor_tracks.json").write_text("{not json", encoding="utf-8")
    tracks = _load_blender_tracks(tmp_path / "anchor_tracks.json", {}, 0)
    assert tracks is None


def test_missing_frames_in_tracks_yields_none(tmp_path):
    (tmp_path / "anchor_tracks.json").write_text(
        json.dumps({"frames": []}), encoding="utf-8"
    )
    assert _load_blender_tracks(tmp_path / "anchor_tracks.json", {}, 0) is None


def test_anchor_tracks_merge_labels_and_accents(tmp_path):
    spec = {
        "anchors_3d": [
            {
                "anchor_id": "anchor_compute_die",
                "label": "COMPUTE DIE",
                "metric": "5NM-CLASS",
                "accent_hex": "#FACC15",
            }
        ]
    }
    payload = {
        "frames": [
            {
                "anchors": [
                    {"anchor_id": "anchor_compute_die", "x": 0.5, "y": 0.5},
                    {"anchor_id": "not_in_spec", "x": 0.1, "y": 0.1},
                ]
            }
        ]
    }
    (tmp_path / "anchor_tracks.json").write_text(json.dumps(payload), encoding="utf-8")
    tracks = _load_blender_tracks(tmp_path / "anchor_tracks.json", spec, 0)
    assert tracks is not None
    by_id = {t["anchor_id"]: t for t in tracks}
    assert by_id["anchor_compute_die"]["label"] == "COMPUTE DIE"
    assert by_id["anchor_compute_die"]["accent_hex"] == "#FACC15"
    assert by_id["not_in_spec"]["label"] == "not_in_spec"  # falls back to id


# ---- _prerender_blender_plates failure modes --------------------------------


def _board_with_spec_scene() -> dict:
    return {
        "meta": {"title": "Fallback Board", "seed": 7},
        "format": {"width": 320, "height": 180, "fps": 24},
        "scenes": [_spec_scene()],
    }


def test_prerender_returns_empty_when_blender_unavailable(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        render_engine.scene_router,
        "probe_blender_environment",
        lambda: {"available": False},
    )
    plates = render_engine._prerender_blender_plates(
        _board_with_spec_scene(), tmp_path, 320, 180, 24, [1]
    )
    assert plates == {}
    assert "software 3D renderer" in capsys.readouterr().out


def test_prerender_timeout_yields_software_fallback(monkeypatch, tmp_path, capsys):
    import subprocess as _sp

    monkeypatch.setattr(
        render_engine.scene_router,
        "probe_blender_environment",
        lambda: {"available": True, "binary": "/bin/true", "version": (4, 2, 0)},
    )

    def _hang(*_args, **_kwargs):
        raise _sp.TimeoutExpired(cmd="blender", timeout=600)

    monkeypatch.setattr(render_engine.subprocess, "run", _hang)
    plates = render_engine._prerender_blender_plates(
        _board_with_spec_scene(), tmp_path, 320, 180, 24, [1]
    )
    assert plates == {}
    assert "software fallback" in capsys.readouterr().err


def test_prerender_nonzero_exit_yields_software_fallback(monkeypatch, tmp_path, capsys):
    class _Result:
        returncode = 1
        stderr = b"synthetic blender crash"

    monkeypatch.setattr(
        render_engine.scene_router,
        "probe_blender_environment",
        lambda: {"available": True, "binary": "/bin/true", "version": (4, 2, 0)},
    )
    monkeypatch.setattr(render_engine.subprocess, "run", lambda *a, **k: _Result())
    plates = render_engine._prerender_blender_plates(
        _board_with_spec_scene(), tmp_path, 320, 180, 24, [1]
    )
    assert plates == {}
    err = capsys.readouterr().err
    assert "exited 1" in err and "software fallback" in err


# ---- blender_runner pure helpers (no bpy required) ---------------------------


def test_hex_to_linear_black_white():
    assert blender_runner.hex_to_linear_rgba("#000000") == (0.0, 0.0, 0.0, 1.0)
    r, g, b, a = blender_runner.hex_to_linear_rgba("#ffffff")
    assert (r, g, b, a) == (1.0, 1.0, 1.0, 1.0)


def test_hex_to_linear_shorthand_and_case():
    assert blender_runner.hex_to_linear_rgba("#FFF")[0] == pytest.approx(1.0)
    assert blender_runner.hex_to_linear_rgba("fff")[0] == pytest.approx(1.0)


def test_hex_to_linear_rejects_garbage():
    with pytest.raises(ValueError):
        blender_runner.hex_to_linear_rgba("#12")
    with pytest.raises(ValueError):
        blender_runner.hex_to_linear_rgba("#gggggg")


def test_cubic_ease_in_out_endpoints_and_midpoint():
    assert blender_runner._cubic_ease_in_out(0.0) == pytest.approx(0.0)
    assert blender_runner._cubic_ease_in_out(1.0) == pytest.approx(1.0)
    assert blender_runner._cubic_ease_in_out(0.5) == pytest.approx(0.5)
    # clamps out-of-range input instead of exploding
    assert blender_runner._cubic_ease_in_out(-1.0) == pytest.approx(0.0)
    assert blender_runner._cubic_ease_in_out(2.0) == pytest.approx(1.0)


def test_serpent_spine_deterministic_and_z_monotonic():
    p0 = blender_runner._serpent_spine(0.0, 0.0)
    p0b = blender_runner._serpent_spine(0.0, 0.0)
    assert p0 == p0b
    z_values = [blender_runner._serpent_spine(u / 10.0, 0.0)[2] for u in range(11)]
    assert z_values == sorted(z_values)


def test_serpent_radius_increases_along_spine():
    assert blender_runner._serpent_radius(0.0) < blender_runner._serpent_radius(1.0)


def test_serpent_anchor_u_head_tail_and_default():
    assert blender_runner._serpent_anchor_u("anchor_head_eye") == 1.0
    assert blender_runner._serpent_anchor_u("TAIL_base") == 0.0
    assert blender_runner._serpent_anchor_u("mid_spine") == 0.5
