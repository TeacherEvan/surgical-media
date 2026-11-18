# ADR 0003 — Optional parametric 3D scene backends; Blender is never required

**Date:** 2026-11-19
**Status:** Accepted

## Context

Until v1.3.0 surgical-media was procedural 2D motion graphics only. A
multi-engine design (`docs/plans/Conversation with Gemini.txt`) proposed
routing scenes to headless Blender 3D, a hybrid 3D→2D motion-tracked HUD,
Manim (math), or 2D canvas. Two hard constraints shaped the adoption:

1. **ADR 0001 (stdlib-first).** The reference implementation leaned on NumPy
   and a "camera_matrix" module that never existed in this repo; Manim is
   deliberately excluded from the dependency set.
2. **Claims = code.** Skill prose may only ship what exists and is green
   locally under `pytest`.

## Decision

1. **Scene-level routing, not element-level.** A scene may carry `scene_spec`
   (a `category` plus optional `camera_3d`, `anchors_3d`, `explode_factor`,
   `lighting_preset`, `blender_engine`, `hud_title`, `transparent_bg`,
   `params`) and a `backend` (`auto` default). `scene_spec` *replaces* the
   `elements` requirement; elements still paint on top when present
   (e.g. `kinetic_captions` captions over a 3D pass).
2. **Blender is an optional accelerator, never a dependency.** The canonical
   renderer is `scripts/software_3d_projection.py`: a stdlib 4×4 look-at view
   matrix, perspective divide, Painter's-algorithm Z sort and diffuse shading
   in ~400 lines of pure Python + Pillow. When Blender ≥ 3.6 is on PATH,
   `render_engine.py` pre-bakes per-scene frame PNGs via
   `scripts/blender_runner.py` (EEVEE/Cycles, version-sniffed engine ids,
   motion-blur, compositor glare where the running Blender supports it) and
   composites those plates under the HUD instead. Any Blender failure falls
   back to the software path with a warning — a render never aborts on
   Blender.
3. **3D→2D tracking single-source by construction.** HUD anchor tracks come
   from the same software projection math (the on-disk `anchor_tracks.json`
   path mirrors it). Blender's `world_to_camera_view` export exists for the
   pre-baked path; both share the top-left-origin `(u, v, z_depth)` contract.
4. **HUD placement is solved, not eyeballed.** `scripts/layout_solver.py`
   (AABB min-axis separation, locked repulsors, canvas clamp) positions
   frosted-glass telemetry cards `hybrid_compositor.py` paints with
   supersampled reticles, 45° elbow leaders and bloom — text never renders
   inside perspective space.
5. **Two categories ship honest code: `exploded_hardware_3d` and
   `orbital_or_field_3d`.** The schema enumerates the full menu (including
   `network_topology_3d`, `rigid_body_physics_3d`, `mathematical_manifold_3d`,
   `external_asset_3d`) so the vocabulary is stable, but the runtime validator
   rejects the four unimplemented ones with the supported list before a render
   starts; both renderers also raise `NotImplementedError` as a second line
   of defence. Camera mode is `orbit` only and two lighting presets ship —
   the schema/validator enums are narrowed to exactly what the renderers honour.
6. **Manim stays out.** `backend: manim_math` validates, lints a warning, and
   renders as 2D canvas — same contract as unknown element types: loud, but
   non-fatal.
7. **No NumPy.** Geometry uses tuple math and `math`; shading is per-channel
   intensity scaling. This keeps ADR 0001 intact and `software_3d_projection`
   importable in every environment the renderer runs.

## Consequences

- Boards using `scene_spec` render anywhere (CI boxes, containers, Termux);
  hosts with Blender get EEVEE-quality plates and tracks for free.
- The integration is opt-in per scene — every existing board renders
  byte-identically.
- QC gates unchanged: same encoder invariants, the same `verify_mp4` pass.
- The EEVEE glare chain must sniff its host's API (Blender 4.2–4.5 dropped
  `Scene.node_tree` for compositor groups; 5.x dropped `FOG_GLOW` enum names)
  — handled with capability probes, documented in `blender_runner.py`.
- Render cost is real (full-frustum per frame in software mode); the intended
  use is hero scenes inside otherwise-2D boards, not minute-long 3D features.
- **License footprint unchanged.** Blender is GNU GPL (Blender Foundation) and
  is invoked only as an external subprocess (`blender -b -P`); repo code never
  imports `bpy` or links Blender (`blender_runner.py` executes inside Blender's
  own Python). No new Python dependencies — the repo stays MIT (`LICENSE`);
  optional user-installed `edge-tts` (LGPL-3.0) serves only the online TTS path
  and is never bundled. See README → Dependencies & Licensing.
- Living plan and task status: [`docs/project-plan.md`](../project-plan.md).
