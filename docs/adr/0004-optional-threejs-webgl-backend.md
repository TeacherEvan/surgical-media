# ADR 0004 — Optional headless Three.js WebGL 3D backend

**Date:** 2026-11-19
**Status:** Accepted

## Context

[ADR 0003](0003-optional-3d-scene-backends.md) introduced optional parametric 3D
scenes with a pure-Python software renderer (`software_3d_projection.py`) as the
canonical fallback and headless Blender (`blender_runner.py`) as an optional
high-fidelity baker. On CPU-only hosts, however, Blender EEVEE takes ~6–10 s per
frame (~5–8 min for a 45-frame hero shot), leaving a wide performance gap between
flat Painter's-algorithm shading and full Blender renders.

Three.js (WebGL) fills that gap: PBR metallic/roughness materials, ACES Filmic
tone mapping, soft shadows, smooth normals, and emissive accents render 45 frames
at 720p in seconds under headless Chromium (SwiftShader/ANGLE) while keeping an
MIT license footprint.

## Decision

1. **Two new explicit scene backends: `threejs_hybrid` and `threejs_3d`.**
   Both are registered in `scene_router.BACKENDS`, `storyboard.VALID_BACKENDS`,
   and `schemas/storyboard.schema.json`. `threejs_hybrid` composites the
   SAT-solved 2D HUD (`hybrid_compositor.py`) over the Three.js plate;
   `threejs_3d` renders the 3D pass without HUD cards. Existing `auto` routing
   is unchanged for full backwards compatibility.
2. **Zero browser-automation npm dependencies; offline by construction.**
   `scripts/threejs/package.json` depends solely on `three` (MIT, zero
   transitive deps). `scripts/threejs/runner.mjs` drives any local
   Chromium/Chrome binary (`CHROME_BIN` or `PATH`) over native Chrome DevTools
   Protocol using Node ≥ 22 built-in `WebSocket` and `fetch`, serving
   `stage.html`, `scenes.mjs`, and the local `three.module.js` from an ephemeral
   `127.0.0.1:0` HTTP server. No CDN requests ever occur at render time.
3. **Single coordinate & plate contract across all three 3D renderers.**
   `scripts/threejs/scenes.mjs` sets `camera.up.set(0, 0, 1)` (Z-up) and derives
   `fovY` from `focal_length_mm` + 36 mm sensor width, matching
   `software_3d_projection.py` and `blender_runner.py` identically. Output is
   the exact same `frame_0001.png..frame_NNNN.png` + `anchor_tracks.json`
   contract consumed by `render_engine.py`.
4. **Optional, never required.**
   `scene_router.probe_threejs_environment()` checks Node ≥ 22, Chromium/Chrome,
   and local `three.module.js` once per process. Any missing runtime, timeout,
   or non-zero exit logs a warning and falls back to `software_3d_projection.py`
   — a render never aborts on Three.js.
5. **Four implemented categories in 3-way parity.**
   `exploded_hardware_3d`, `orbital_or_field_3d`, `organic_serpent_3d`, and the
   newly implemented `network_topology_3d` ship in all three 3D backends
   (`software_3d_projection.py`, `scripts/threejs/scenes.mjs`, and
   `blender_runner.py`).

## Consequences

- Hosts with Node ≥ 22 + Chromium + `npm install` in `scripts/threejs/` get
  fast WebGL PBR 3D plates and motion-tracked HUDs; hosts without them fall back
  transparently to software 3D.
- No new Python dependencies; MIT license unchanged (`three` is MIT).
- CI and unit tests stay offline and fast (live Chromium integration test skips
  cleanly when the runtime is absent).
