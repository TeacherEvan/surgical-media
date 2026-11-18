#!/usr/bin/env python3
"""Tests for scene_router — Blender probe caching and scene routing.

Blender is never really executed: ``shutil.which`` / ``subprocess.check_output``
are monkeypatched, and the module-level probe cache is reset between tests.
"""

from __future__ import annotations

import subprocess

import pytest
import scene_router


@pytest.fixture(autouse=True)
def reset_probe_cache(monkeypatch):
    monkeypatch.setattr(scene_router, "_blender_probe_cache", None)
    monkeypatch.delenv("BLENDER_BIN", raising=False)
    yield
    monkeypatch.setattr(scene_router, "_blender_probe_cache", None)


def test_probe_missing_binary(monkeypatch):
    monkeypatch.setattr(scene_router.shutil, "which", lambda _name: None)
    probe = scene_router.probe_blender_environment()
    assert probe["available"] is False
    assert probe["binary"] is None
    assert probe["version"] == (0, 0, 0)
    assert probe["eevee_engine_id"] == "BLENDER_EEVEE_NEXT"


def _fake_check_output_factory(stdout: str):
    def fake_check_output(argv, **kwargs):
        assert argv[0] == "/fake/blender"
        assert argv[1] == "--version"
        assert kwargs["text"] is True
        assert kwargs["stderr"] is subprocess.DEVNULL
        assert kwargs["timeout"] == 15
        return stdout

    return fake_check_output


def test_probe_blender_4_2(monkeypatch):
    monkeypatch.setattr(scene_router.shutil, "which", lambda _name: "/fake/blender")
    monkeypatch.setattr(
        scene_router.subprocess,
        "check_output",
        _fake_check_output_factory("Blender 4.2.3\nbuild date: 2024-10-15\n"),
    )
    probe = scene_router.probe_blender_environment()
    assert probe["available"] is True
    assert probe["binary"] == "/fake/blender"
    assert probe["version"] == (4, 2, 3)
    assert probe["eevee_engine_id"] == "BLENDER_EEVEE_NEXT"


def test_probe_blender_3_6(monkeypatch):
    monkeypatch.setattr(scene_router.shutil, "which", lambda _name: "/fake/blender")
    monkeypatch.setattr(
        scene_router.subprocess,
        "check_output",
        _fake_check_output_factory("Blender 3.6.0\n"),
    )
    probe = scene_router.probe_blender_environment()
    assert probe["available"] is True
    assert probe["version"] == (3, 6, 0)
    assert probe["eevee_engine_id"] == "BLENDER_EEVEE"


def test_probe_blender_older_than_3_6_is_unavailable(monkeypatch):
    monkeypatch.setattr(scene_router.shutil, "which", lambda _name: "/fake/blender")
    monkeypatch.setattr(
        scene_router.subprocess,
        "check_output",
        _fake_check_output_factory("Blender 3.5.1\n"),
    )
    probe = scene_router.probe_blender_environment()
    assert probe["available"] is False
    assert probe["version"] == (0, 0, 0)


def test_probe_caches_result(monkeypatch):
    calls = []

    def fake_check_output(argv, **kwargs):
        calls.append(argv)
        return "Blender 4.2.3\n"

    monkeypatch.setattr(scene_router.shutil, "which", lambda _name: "/fake/blender")
    monkeypatch.setattr(scene_router.subprocess, "check_output", fake_check_output)
    first = scene_router.probe_blender_environment()
    second = scene_router.probe_blender_environment()
    assert len(calls) == 1
    assert first == second
    # Cached copy is detached: mutating it must not poison the cache.
    first["version"] = (0, 0, 0)
    assert scene_router.probe_blender_environment()["version"] == (4, 2, 3)


def test_probe_subprocess_failure_is_unavailable(monkeypatch):
    def boom(argv, **kwargs):
        raise OSError("no exec")

    monkeypatch.setattr(scene_router.shutil, "which", lambda _name: "/fake/blender")
    monkeypatch.setattr(scene_router.subprocess, "check_output", boom)
    probe = scene_router.probe_blender_environment()
    assert probe["available"] is False
    assert probe["version"] == (0, 0, 0)
    assert probe["eevee_engine_id"] == "BLENDER_EEVEE_NEXT"


def test_route_explicit_backend_returned_as_is():
    for backend in ("blender_hybrid", "blender_3d", "manim_math", "canvas_2d"):
        assert scene_router.route_scene({"backend": backend}) == backend


def test_route_explicit_unknown_backend_raises():
    with pytest.raises(ValueError, match="unknown scene backend"):
        scene_router.route_scene({"backend": "unreal_engine_5"})


def test_route_category_with_anchors_is_hybrid():
    scene = {
        "scene_spec": {
            "category": "orbital_or_field_3d",
            "anchors_3d": [{"id": "sat", "frame": 12}],
        }
    }
    assert scene_router.route_scene(scene) == "blender_hybrid"


def test_route_category_without_anchors_is_3d():
    scene = {"scene_spec": {"category": "orbital_or_field_3d"}}
    assert scene_router.route_scene(scene) == "blender_3d"


def test_route_narration_3d_keywords():
    scene = {"narration": "Inside the plasma stellarator chamber"}
    assert scene_router.route_scene(scene) == "blender_3d"


def test_route_narration_3d_keywords_with_anchors_is_hybrid():
    scene = {
        "narration": "Inside the plasma stellarator chamber",
        "scene_spec": {"anchors_3d": [{"id": "coil", "frame": 40}]},
    }
    assert scene_router.route_scene(scene) == "blender_hybrid"


def test_route_narration_text_fallback_key():
    scene = {"narration_text": "A gpu die under the microscope"}
    assert scene_router.route_scene(scene) == "blender_3d"


def test_route_math_narration_is_manim():
    scene = {"narration": "fourier matrix equation proof theorem"}
    assert scene_router.route_scene(scene) == "manim_math"


def test_route_math_needs_two_hits():
    scene = {"narration": "an equation about nothing in particular"}
    assert scene_router.route_scene(scene) == "canvas_2d"


def test_route_plain_narration_is_canvas():
    assert scene_router.route_scene({"narration": "an essay about tea"}) == "canvas_2d"


def test_route_boolean_cutaway_forces_3d():
    scene = {"scene_spec": {"boolean_cutaway": True}}
    assert scene_router.route_scene(scene) == "blender_3d"


def test_route_explode_factor_forces_3d():
    scene = {"scene_spec": {"explode_factor": 0.5}}
    assert scene_router.route_scene(scene) == "blender_3d"
