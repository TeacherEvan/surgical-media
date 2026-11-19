"""Tests for the optional Three.js WebGL backend + network_topology_3d parity.

Unit tests monkeypatch subprocess/shutil so they never launch Chromium in CI.
One opt-in integration test renders a real 2-frame Three.js WebGL plate when
Node >= 22, Chromium, and local three.module.js are present, and skips cleanly
otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import blender_runner
import render_engine
import scene_router
import software_3d_projection
import storyboard
import threejs_bridge

THREEJS_EXAMPLE = REPO / "examples" / "threejs_3d_storyboard.json"
SCHEMA = REPO / "schemas" / "storyboard.schema.json"


@pytest.fixture(autouse=True)
def reset_threejs_probe_cache(monkeypatch):
    monkeypatch.setattr(scene_router, "_threejs_probe_cache", None)
    for var in ("NODE_BIN", "CHROME_BIN", "THREEJS_LIB"):
        monkeypatch.delenv(var, raising=False)
    yield
    monkeypatch.setattr(scene_router, "_threejs_probe_cache", None)


def _threejs_scene(backend: str = "threejs_hybrid") -> dict:
    return {
        "scene_id": "net_scene",
        "archetype": "code_report",
        "backend": backend,
        "duration_sec": 0.5,
        "fade_in_sec": 0.0,
        "fade_out_sec": 0.0,
        "scene_spec": {
            "category": "network_topology_3d",
            "hud_title": "EDGE MESH",
            "lighting_preset": "cyber_studio_volumetric",
            "camera_3d": {
                "mode": "orbit",
                "radius_start": 7.0,
                "radius_end": 5.8,
                "azimuth_start_deg": -30.0,
                "azimuth_end_deg": 25.0,
                "elevation_deg": 24.0,
                "focal_length_mm": 50.0,
            },
            "anchors_3d": [
                {
                    "anchor_id": "anchor_core",
                    "label": "CONTROL PLANE",
                    "metric": "0.8 MS P99",
                    "local_pos": [0.0, 0.0, 0.45],
                    "accent_hex": "#38BDF8",
                }
            ],
        },
    }


def _threejs_board(backend: str = "threejs_hybrid") -> dict:
    return {
        "meta": {"title": "Three.js Test Board", "seed": 42},
        "format": {"width": 320, "height": 180, "fps": 24},
        "scenes": [_threejs_scene(backend)],
    }


# ---- probe_threejs_environment ----------------------------------------------


def test_threejs_probe_missing_node(monkeypatch):
    monkeypatch.setattr(scene_router.shutil, "which", lambda _name: None)
    probe = scene_router.probe_threejs_environment()
    assert probe["available"] is False
    assert "node" in (probe["reason"] or "")


def test_threejs_probe_old_node_rejected(monkeypatch):
    monkeypatch.setattr(
        scene_router.shutil,
        "which",
        lambda name: "/fake/node" if name == "node" else None,
    )
    monkeypatch.setattr(
        scene_router.subprocess,
        "check_output",
        lambda *_a, **_k: "v20.11.0\n",
    )
    probe = scene_router.probe_threejs_environment()
    assert probe["available"] is False
    assert "< 22.0.0" in (probe["reason"] or "")


def test_threejs_probe_missing_browser(monkeypatch):
    monkeypatch.setattr(
        scene_router.shutil,
        "which",
        lambda name: "/fake/node" if name == "node" else None,
    )
    monkeypatch.setattr(
        scene_router.subprocess,
        "check_output",
        lambda *_a, **_k: "v22.14.0\n",
    )
    probe = scene_router.probe_threejs_environment()
    assert probe["available"] is False
    assert "chromium" in (probe["reason"] or "")


def test_threejs_probe_missing_three_module(monkeypatch):
    def fake_which(name: str) -> str | None:
        return {"node": "/fake/node", "chromium": "/fake/chromium"}.get(name)

    monkeypatch.setattr(scene_router.shutil, "which", fake_which)
    monkeypatch.setattr(
        scene_router.subprocess,
        "check_output",
        lambda *_a, **_k: "v22.14.0\n",
    )
    monkeypatch.setattr(scene_router, "_find_three_module", lambda: None)
    probe = scene_router.probe_threejs_environment()
    assert probe["available"] is False
    assert "three.module.js" in (probe["reason"] or "")


def test_threejs_probe_success_and_caches(monkeypatch, tmp_path):
    fake_three = tmp_path / "three.module.js"
    fake_three.write_text("export {};\n", encoding="utf-8")
    calls = []

    def fake_which(name: str) -> str | None:
        return {"node": "/fake/node", "chromium": "/fake/chromium"}.get(name)

    def fake_check_output(argv, **kwargs):
        calls.append(argv)
        return "v26.8.2\n"

    monkeypatch.setattr(scene_router.shutil, "which", fake_which)
    monkeypatch.setattr(scene_router.subprocess, "check_output", fake_check_output)
    monkeypatch.setenv("THREEJS_LIB", str(fake_three))

    first = scene_router.probe_threejs_environment()
    second = scene_router.probe_threejs_environment()
    assert first == second
    assert first["available"] is True
    assert first["node_version"] == (26, 8, 2)
    assert first["browser_binary"] == "/fake/chromium"
    assert first["three_module"] == str(fake_three)
    assert len(calls) == 1
    first["available"] = False
    assert scene_router.probe_threejs_environment()["available"] is True


# ---- routing, schema, adapter -----------------------------------------------


def test_route_explicit_threejs_backends():
    assert scene_router.route_scene({"backend": "threejs_hybrid"}) == "threejs_hybrid"
    assert scene_router.route_scene({"backend": "threejs_3d"}) == "threejs_3d"


def test_threejs_example_board_validates_and_matches_schema():
    board = json.loads(THREEJS_EXAMPLE.read_text(encoding="utf-8"))
    assert storyboard.validate_storyboard(board) == []
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8"))
    )
    assert list(validator.iter_errors(board)) == []


def test_threejs_adapter_uses_shared_camera_defaults():
    adapted = threejs_bridge.threejs_adapter_spec({"category": "network_topology_3d"})
    cam = adapted["camera_3d"]
    assert cam["radius_start"] == scene_router.CAMERA_3D_DEFAULTS["radius_start"]
    assert cam["radius_end"] == scene_router.CAMERA_3D_DEFAULTS["radius_end"]
    assert cam["focal_length_mm"] == scene_router.CAMERA_3D_DEFAULTS["focal_length_mm"]


# ---- prerender + fallback paths ---------------------------------------------


def test_prerender_threejs_unavailable_falls_back(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        render_engine.scene_router,
        "probe_threejs_environment",
        lambda: {"available": False, "reason": "no chromium"},
    )
    plates = render_engine._prerender_threejs_plates(
        _threejs_board(), tmp_path, 320, 180, 24, [1]
    )
    assert plates == {}
    assert "software 3D renderer" in capsys.readouterr().out


def test_prerender_threejs_timeout_falls_back(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        render_engine.scene_router,
        "probe_threejs_environment",
        lambda: {
            "available": True,
            "node_binary": "/fake/node",
            "browser_binary": "/fake/chromium",
            "three_module": "/fake/three.module.js",
            "runner_script": "/fake/runner.mjs",
        },
    )

    def _hang(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="node", timeout=240)

    monkeypatch.setattr(threejs_bridge.subprocess, "run", _hang)
    plates = render_engine._prerender_threejs_plates(
        _threejs_board(), tmp_path, 320, 180, 24, [1]
    )
    assert plates == {}
    assert "software fallback" in capsys.readouterr().err


def test_prerender_threejs_nonzero_exit_falls_back(monkeypatch, tmp_path, capsys):
    class _Res:
        returncode = 1
        stderr = b"synthetic webgl error"

    monkeypatch.setattr(
        render_engine.scene_router,
        "probe_threejs_environment",
        lambda: {
            "available": True,
            "node_binary": "/fake/node",
            "browser_binary": "/fake/chromium",
            "three_module": "/fake/three.module.js",
            "runner_script": "/fake/runner.mjs",
        },
    )
    monkeypatch.setattr(threejs_bridge.subprocess, "run", lambda *_a, **_k: _Res())
    plates = render_engine._prerender_threejs_plates(
        _threejs_board(), tmp_path, 320, 180, 24, [1]
    )
    assert plates == {}
    err = capsys.readouterr().err
    assert "exited 1" in err and "software fallback" in err


def test_paint_frame_threejs_hybrid_and_3d_software_fallback():
    for backend in ("threejs_hybrid", "threejs_3d"):
        scene = _threejs_scene(backend)
        frame = render_engine.paint_frame(scene, 320, 180, 1, 7, 3, 24)
        assert frame.mode == "RGB"
        assert frame.size == (320, 180)
        assert any(hi > lo for lo, hi in frame.getextrema())


def test_network_topology_parity_between_software_and_blender_helpers():
    sw_nodes = software_3d_projection.network_topology_nodes()
    bl_nodes = blender_runner._network_topology_nodes()
    assert [n[0] for n in sw_nodes] == [n[0] for n in bl_nodes]
    assert [n[1] for n in sw_nodes] == [n[1] for n in bl_nodes]
    assert "network_topology_3d" in software_3d_projection.SUPPORTED_CATEGORIES
    assert "network_topology_3d" in blender_runner.SUPPORTED_CATEGORIES


# ---- optional live headless Three.js WebGL integration ----------------------


def test_threejs_live_renders_nonflat_plate_and_anchor_tracks(tmp_path):
    probe = scene_router._probe_threejs_environment_uncached()
    if not probe.get("available"):
        pytest.skip(f"Three.js runtime unavailable: {probe.get('reason')}")

    scene = _threejs_scene("threejs_hybrid")
    plate_dir = tmp_path / "threejs_net_scene"
    spec_path = tmp_path / "spec.json"
    result = threejs_bridge.prerender_threejs_scene(
        "net_scene",
        scene["scene_spec"],
        plate_dir,
        spec_path,
        width=320,
        height=180,
        fps=24,
        n_frames=2,
        probe=probe,
        timeout=90,
    )
    assert result == plate_dir
    frame1 = plate_dir / "frame_0001.png"
    frame2 = plate_dir / "frame_0002.png"
    tracks_path = plate_dir / "anchor_tracks.json"
    assert frame1.is_file() and frame2.is_file() and tracks_path.is_file()

    with Image.open(frame1) as im:
        assert im.size == (320, 180)
        rgb = im.convert("RGB")
        assert any(hi > lo for lo, hi in rgb.getextrema())

    tracks = json.loads(tracks_path.read_text(encoding="utf-8"))
    assert tracks["total_frames"] == 2
    assert len(tracks["frames"]) == 2
    assert tracks["frames"][0]["anchors"][0]["anchor_id"] == "anchor_core"
    assert tracks["frames"][0]["anchors"][0]["visible"] is True

    # Composite the real Three.js plate through render_engine + HUD
    composited = render_engine._paint_scene_frame(
        scene,
        width=320,
        height=180,
        scale=1,
        seed=7,
        local_idx=0,
        fps=24,
        trauma=0.0,
        blender_dir=plate_dir,
    )
    assert composited.mode == "RGB"
    assert composited.size == (320, 180)


def test_external_asset_3d_parity_and_software_fallback():
    assert "external_asset_3d" in software_3d_projection.SUPPORTED_CATEGORIES
    assert "external_asset_3d" in blender_runner.SUPPORTED_CATEGORIES
    assert "external_asset_3d" in storyboard.IMPLEMENTED_3D_CATEGORIES
    scene = _threejs_scene("threejs_hybrid")
    scene["scene_spec"]["category"] = "external_asset_3d"
    assert storyboard.validate_storyboard({**_threejs_board(), "scenes": [scene]}) == []
    frame = render_engine.paint_frame(scene, 320, 180, 1, 7, 2, 24)
    assert frame.mode == "RGB"
    assert any(hi > lo for lo, hi in frame.getextrema())


def test_threejs_live_custom_script_scene_with_ibl_and_bloom(tmp_path):
    probe = scene_router._probe_threejs_environment_uncached()
    if not probe.get("available"):
        pytest.skip(f"Three.js runtime unavailable: {probe.get('reason')}")

    custom_mjs = tmp_path / "custom_torus.mjs"
    custom_mjs.write_text(
        """
export async function buildScene({ THREE, scene }) {
  const mesh = new THREE.Mesh(
    new THREE.TorusKnotGeometry(0.9, 0.28, 64, 16),
    new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      emissive: 0x0ea5e9,
      emissiveIntensity: 0.9,
      metalness: 0.85,
      roughness: 0.18,
    })
  );
  scene.add(mesh);
  return (tNorm) => {
    mesh.rotation.z = tNorm * Math.PI;
    return { anchor_knot: [0.0, 0.0, 0.0] };
  };
}
""",
        encoding="utf-8",
    )
    spec = {
        "category": "external_asset_3d",
        "lighting_preset": "cyber_studio_volumetric",
        "params": {"threejs_script": "custom_torus.mjs", "bloom_strength": 0.6},
        "anchors_3d": [
            {
                "anchor_id": "anchor_knot",
                "label": "CUSTOM KNOT",
                "metric": "PBR + BLOOM",
                "local_pos": [0.0, 0.0, 0.0],
            }
        ],
    }
    plate_dir = tmp_path / "custom_out"
    res = threejs_bridge.prerender_threejs_scene(
        "custom_knot",
        spec,
        plate_dir,
        tmp_path / "custom_spec.json",
        width=320,
        height=180,
        fps=24,
        n_frames=2,
        probe=probe,
        base_dir=tmp_path,
        timeout=90,
    )
    assert res == plate_dir
    with Image.open(plate_dir / "frame_0002.png") as im:
        assert im.size == (320, 180)
        assert any(hi > lo for lo, hi in im.convert("RGB").getextrema())
    tracks = json.loads((plate_dir / "anchor_tracks.json").read_text(encoding="utf-8"))
    assert tracks["frames"][1]["anchors"][0]["anchor_id"] == "anchor_knot"
    assert tracks["frames"][1]["anchors"][0]["visible"] is True


def test_camera_3d_cinematic_modes_validate_and_render():
    for mode in ("orbit", "dolly", "crane", "static"):
        scene = _threejs_scene("threejs_hybrid")
        scene["scene_spec"]["camera_3d"]["mode"] = mode
        board = {**_threejs_board(), "scenes": [scene]}
        assert storyboard.validate_storyboard(board) == []
        frame = render_engine.paint_frame(scene, 320, 180, 1, 7, 3, 24)
        assert frame.size == (320, 180)
        assert any(hi > lo for lo, hi in frame.getextrema())


def test_threejs_live_svg_to_3d_bevel_extrusion_and_single_frame_t(tmp_path):
    probe = scene_router._probe_threejs_environment_uncached()
    if not probe.get("available"):
        pytest.skip(f"Three.js runtime unavailable: {probe.get('reason')}")

    svg_star = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <polygon points="50,5 64,36 98,36 70,57 81,91 50,70 19,91 30,57 2,36 36,36" fill="#FACC15"/>
      <circle cx="50" cy="50" r="16" fill="#38BDF8"/>
    </svg>"""
    spec = {
        "category": "external_asset_3d",
        "lighting_preset": "cyber_studio_volumetric",
        "camera_3d": {"mode": "dolly", "radius_start": 6.5, "radius_end": 5.0},
        "params": {"svg_markup": svg_star, "bloom_strength": 0.55},
        "anchors_3d": [
            {
                "anchor_id": "anchor_asset_center",
                "label": "3D EXTRUDED SVG",
                "metric": "SVGLOADER + IBL",
                "local_pos": [0.0, 0.0, 0.0],
            }
        ],
    }
    plate_dir = tmp_path / "svg3d_out"
    res = threejs_bridge.prerender_threejs_scene(
        "svg3d",
        spec,
        plate_dir,
        tmp_path / "svg3d_spec.json",
        width=320,
        height=180,
        fps=24,
        n_frames=1,
        probe=probe,
        frame_t=0.55,
        timeout=90,
    )
    assert res == plate_dir
    f1 = plate_dir / "frame_0001.png"
    assert f1.is_file()
    with Image.open(f1) as im:
        assert im.size == (320, 180)
        assert len(set(im.convert("RGB").get_flattened_data())) > 50
