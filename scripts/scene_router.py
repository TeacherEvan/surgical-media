#!/usr/bin/env python3
"""scene_router.py — route a storyboard scene to a render backend.

The pipeline has six backends:

- ``blender_hybrid`` — Blender-rendered 3D plate composited with 2D canvas
  overlays (captions, kinetic type, annotations). Chosen when a scene needs
  3D *and* carries ``anchors_3d`` alignment anchors.
- ``blender_3d`` — pure Blender 3D scene.
- ``threejs_hybrid`` — headless Three.js WebGL 3D plate composited with the
  2D motion-tracked HUD (falls back to software 3D when unavailable).
- ``threejs_3d`` — pure headless Three.js WebGL 3D scene (falls back to
  software 3D when unavailable).
- ``manim_math`` — math-explainer scenes (equations, proofs), no 3D content.
- ``canvas_2d`` — the default Pillow 2D renderer.

``probe_blender_environment()`` and ``probe_threejs_environment()`` detect
usable local runtimes and cache their results in module-level private variables
so repeated calls do not re-exec subprocesses. Tests that need a fresh probe
call the ``_uncached`` helpers directly (or reset the cache).

Pure and deterministic apart from the subprocess probes; no prints — the
render layer owns logging.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

# Shared camera defaults — consumed by both the software 3D renderer and the
# Blender pre-bake adapter so an underspecified scene looks identical either way.
CAMERA_3D_DEFAULTS: dict[str, float] = {
    "focal_length_mm": 50.0,
    "fstop": 2.8,
    "radius_start": 6.2,
    "radius_end": 4.5,
    "azimuth_start_deg": -38.0,
    "azimuth_end_deg": 42.0,
    "elevation_deg": 25.0,
}
MIN_BLENDER_VERSION = (3, 6, 0)

BLENDER_CATEGORIES = {
    "exploded_hardware_3d",
    "orbital_or_field_3d",
    "organic_serpent_3d",
    "network_topology_3d",
    "rigid_body_physics_3d",
    "mathematical_manifold_3d",
    "external_asset_3d",
}

KEYWORDS_3D = {
    "3d",
    "hardware",
    "chip",
    "gpu",
    "die",
    "pcb",
    "reactor",
    "tokamak",
    "stellarator",
    "plasma",
    "orbit",
    "satellite",
    "planet",
    "molecule",
    "protein",
    "dna",
    "lattice",
    "gear",
    "robotics",
    "actuator",
    "drone",
    "chassis",
    "cutaway",
    "exploded",
    "physics",
    "collision",
    "domino",
    "fluid",
    "manifold",
    "topology",
    "volumetric",
    "server rack",
    "submarine cable",
    "fiber",
    "turbine",
    "engine",
    "battery cell",
}

KEYWORDS_MATH = {
    "equation",
    "integral",
    "derivative",
    "matrix",
    "eigenvalue",
    "fourier",
    "theorem",
    "proof",
    "latex",
    "calculus",
}

BACKENDS = (
    "blender_hybrid",
    "blender_3d",
    "threejs_hybrid",
    "threejs_3d",
    "manim_math",
    "canvas_2d",
)
_VALID_EXPLICIT = frozenset(BACKENDS) | {"auto"}

_VERSION_RE = re.compile(r"Blender\s+(\d+)\.(\d+)(?:\.(\d+))?")
MIN_NODE_VERSION = (22, 0, 0)
_NODE_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
_BROWSER_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
)

# Module-level probe caches. ``None`` means "not probed yet". Tests reset these
# (or call the uncached variants) to avoid re-execing external binaries.
_blender_probe_cache: dict[str, Any] | None = None
_threejs_probe_cache: dict[str, Any] | None = None


def _unavailable_probe() -> dict[str, Any]:
    return {
        "available": False,
        "binary": None,
        "version": (0, 0, 0),
        "eevee_engine_id": "BLENDER_EEVEE_NEXT",
    }


def _probe_blender_environment_uncached() -> dict[str, Any]:
    """Probe Blender without touching the module-level cache.

    Locates the binary via the ``BLENDER_BIN`` environment variable, falling
    back to ``shutil.which("blender")``. Runs ``blender --version`` with a
    15 s timeout and parses the version from stdout. Any failure — missing
    binary, subprocess error, timeout, unparseable output, or a version older
    than 3.6 yields ``available=False``, ``version=(0, 0, 0)`` and the modern
    EEVEE identifier.
    """
    binary = os.environ.get("BLENDER_BIN") or shutil.which("blender")
    if not binary:
        return _unavailable_probe()
    try:
        out = subprocess.check_output(
            [binary, "--version"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except Exception:  # noqa: BLE001 — any probe failure means "no usable Blender"
        return _unavailable_probe()
    match = _VERSION_RE.search(out)
    if match is None:
        return _unavailable_probe()
    major, minor = int(match.group(1)), int(match.group(2))
    patch = int(match.group(3)) if match.group(3) else 0
    version = (major, minor, patch)
    if version < MIN_BLENDER_VERSION:
        return _unavailable_probe()
    eevee_engine_id = "BLENDER_EEVEE_NEXT" if version >= (4, 2, 0) else "BLENDER_EEVEE"
    return {
        "available": True,
        "binary": binary,
        "version": version,
        "eevee_engine_id": eevee_engine_id,
    }


def probe_blender_environment() -> dict[str, Any]:
    """Return the cached Blender probe result, probing once if needed.

    The result is cached in a module-level private variable; repeated calls
    never re-exec Blender. Tests should reset the cache (or call
    ``_probe_blender_environment_uncached()``) for isolation. A shallow copy
    is returned so callers cannot mutate the cache.
    """
    global _blender_probe_cache
    if _blender_probe_cache is None:
        _blender_probe_cache = _probe_blender_environment_uncached()
    return dict(_blender_probe_cache)


def _unavailable_threejs_probe(reason: str = "unavailable") -> dict[str, Any]:
    return {
        "available": False,
        "node_binary": None,
        "node_version": (0, 0, 0),
        "browser_binary": None,
        "three_module": None,
        "runner_script": None,
        "reason": reason,
    }


def _find_three_module() -> Path | None:
    env_lib = os.environ.get("THREEJS_LIB")
    if env_lib:
        candidate = Path(env_lib)
        return candidate if candidate.is_file() else None
    script_dir = Path(__file__).resolve().parent
    candidates = (
        script_dir / "threejs" / "node_modules" / "three" / "build" / "three.module.js",
        script_dir.parent / "node_modules" / "three" / "build" / "three.module.js",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _probe_threejs_environment_uncached() -> dict[str, Any]:
    """Probe Node.js (>=22), headless Chromium/Chrome, and local three.module.js.

    All checks are local and offline: ``NODE_BIN`` / ``CHROME_BIN`` /
    ``THREEJS_LIB`` override discovery. Any missing or incompatible component
    yields ``available=False`` with a diagnostic ``reason``.
    """
    node_bin = os.environ.get("NODE_BIN") or shutil.which("node")
    if not node_bin:
        return _unavailable_threejs_probe("node binary not found")
    try:
        out = subprocess.check_output(
            [node_bin, "--version"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except Exception:  # noqa: BLE001 — any probe failure means "no usable Node"
        return _unavailable_threejs_probe("node --version failed")
    match = _NODE_VERSION_RE.search(out.strip())
    if match is None:
        return _unavailable_threejs_probe("could not parse node version")
    node_version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    if node_version < MIN_NODE_VERSION:
        return _unavailable_threejs_probe(
            f"node {node_version[0]}.{node_version[1]}.{node_version[2]} < 22.0.0"
        )

    browser_bin = os.environ.get("CHROME_BIN")
    if not browser_bin:
        for name in _BROWSER_CANDIDATES:
            found = shutil.which(name)
            if found:
                browser_bin = found
                break
    if not browser_bin:
        return _unavailable_threejs_probe("chromium/chrome binary not found")

    three_mod = _find_three_module()
    if three_mod is None:
        return _unavailable_threejs_probe(
            "three.module.js not found (run `npm install` in scripts/threejs/)"
        )

    runner = Path(__file__).resolve().parent / "threejs" / "runner.mjs"
    if not runner.is_file():
        return _unavailable_threejs_probe("scripts/threejs/runner.mjs not found")

    return {
        "available": True,
        "node_binary": node_bin,
        "node_version": node_version,
        "browser_binary": browser_bin,
        "three_module": str(three_mod),
        "runner_script": str(runner),
        "reason": None,
    }


def probe_threejs_environment() -> dict[str, Any]:
    """Return the cached Three.js runtime probe result, probing once if needed."""
    global _threejs_probe_cache
    if _threejs_probe_cache is None:
        _threejs_probe_cache = _probe_threejs_environment_uncached()
    return dict(_threejs_probe_cache)


def _keyword_hits(keywords: set[str], haystack: str) -> int:
    return sum(1 for keyword in keywords if keyword in haystack)


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def route_scene(scene: dict[str, Any]) -> str:
    """Route a scene dict to a backend: ``blender_hybrid`` | ``blender_3d`` |
    ``manim_math`` | ``canvas_2d``.

    An explicit ``scene["backend"]`` other than ``"auto"`` is validated and
    returned verbatim; an unknown explicit value raises ``ValueError`` (loud,
    not silent). Otherwise the route is inferred from ``scene_spec`` category,
    3D-anchor presence, keyword counts in the narration and 3D-ish
    ``scene_spec`` flags. Supports both ``narration`` and ``narration_text``.
    """
    explicit = scene.get("backend", "auto")
    if explicit != "auto":
        if explicit not in _VALID_EXPLICIT:
            raise ValueError(
                f"unknown scene backend {explicit!r}; "
                f"expected one of {sorted(_VALID_EXPLICIT)}"
            )
        return str(explicit)

    spec = scene.get("scene_spec") or {}
    if not isinstance(spec, dict):
        spec = {}
    category = str(spec.get("category", "") or "")
    narration = (
        f"{scene.get('narration', '')} {scene.get('narration_text', '')} "
        f"{spec.get('params', '')}"
    ).lower()

    anchors = spec.get("anchors_3d") or []
    has_anchors = bool(anchors)

    if category in BLENDER_CATEGORIES:
        return "blender_hybrid" if has_anchors else "blender_3d"

    score_3d = _keyword_hits(KEYWORDS_3D, narration)
    score_math = _keyword_hits(KEYWORDS_MATH, narration)

    explode_factor = _as_float(spec.get("explode_factor", 0) or 0)
    if score_3d >= 1 or spec.get("boolean_cutaway") or explode_factor > 0:
        return "blender_hybrid" if has_anchors else "blender_3d"

    if score_math >= 2:
        return "manim_math"

    return "canvas_2d"
