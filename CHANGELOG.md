# Changelog

All notable changes to surgical-media. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); releases are
git-tagged (`v1.1.0`, `v1.2.0`, …) and dates are release dates.

Honest status line used throughout: **no hosted CI.** GitHub Actions was
removed 2026-11-18 (billing-locked; jobs never started). Local gates
(`bash scripts/ci_gates.sh`) are the enforced standard; the GitLab mirror
(`.gitlab-ci.yml`) is configured, not verified.

## [Unreleased]

### Added
- `organic_serpent_3d` — a genuine parametric snake asset: tapered undulating S-curve body (26×8 polygon tube with jade scale bands, gold head and emissive eyes) in `software_3d_projection.py`, and a headless-bpy curve/bevel builder with per-frame spine animation in `blender_runner.py`. Registered in router, runtime validator and storyboard schema; head/body/tail anchors track the moving spine. 7 new tests; suite now 285.
- SKILL.md/AGENTS.md now state the design-history rule: plans are *templates for creating assets*, never assets to copy; new subjects require new generators in both renderers with tests and docs in the same change.

## [1.3.0] — 2026-11-19

### Added
- **Optional parametric 3D scene backends** (`scene_spec` + `backend` on scenes): procedural `exploded_hardware_3d` and `orbital_or_field_3d` categories rendered by `scripts/software_3d_projection.py` (stdlib 4×4 look-at view matrix, Painter's-algorithm Z sort, diffuse shading, bloom-fed emissives) with normalized 3D→2D anchor tracks — Blender not required.
- `scripts/scene_router.py` — `auto`/`blender_hybrid`/`blender_3d`/`canvas_2d`/`manim_math` routing + Blender ≥3.6 capability probe (version-sniffed EEVEE id; `BLENDER_BIN` override; cached).
- `scripts/blender_runner.py` — optional headless-Blender bake (`blender -b -P`): EEVEE/Cycles selection, motion blur, compositor glare with host-API probes (4.2–4.5/5.x), `world_to_camera_view` anchor export, `anchor_tracks.json` for HUD compositing. Exploded-hardware and stellarator generators only; anything else raises `NotImplementedError`.
- `scripts/hybrid_compositor.py` + `scripts/layout_solver.py` — motion-tracked HUD: reticles, 45° elbow leaders, frosted glass cards; AABB min-axis placement with locked repulsors + 24 px clamp (no numpy).
- `render_engine.py` — `scene_spec` scenes painted 3D/plate → HUD → elements on top; pre-bake with software fallback; `paint_frame` used for both render loop and `--thumbnails`; `--estimate` reports per-scene backend routing.
- Schema + validator: `backend`/`scene_spec` on scenes; `scene_spec` satisfies the elements requirement (`anyOf` — elements-or-scene_spec); `tests/test_scene_spec_integration.py` pins both validators to parity.
- `examples/hybrid_3d_storyboard.json` — 2-scene showcase (CoWoS-style stack, stellarator torus); renders end-to-end with and without Blender.
- ADR 0003 (`docs/adr/0003-optional-3d-scene-backends.md`); `references/storyboard-guide.md` scene-backend section.
- `tests/test_layout_solver.py`, `tests/test_scene_router.py`, `tests/test_blender_runner.py`, `tests/test_software_3d_projection.py`, `tests/test_hybrid_compositor.py` — 59 new tests (285 total).
- ADR 0002 (`docs/adr/0002-local-first-verification.md`) — the decision record for removing hosted CI in favor of local-first gates (supersedes the removed GitHub Actions workflow).
- `SECURITY.md` — scope (offline, no network service), license-compliance and URL-safety reporting paths, supported versions.
- `.pre-commit-config.yaml` — optional ruff/format/whitespace hooks; explicitly documented as NOT a replacement for `scripts/ci_gates.sh`.

### Changed
- `main` branch protection enabled on GitHub: required linear history, force-push and deletion blocked, `enforce_admins: true`. Fast-forward pushes unchanged.
- `storyboard.schema.json` scene `required` is now `["scene_id","archetype","duration_sec"]`; scenes require `elements` **or** `scene_spec`.
- `scripts/ci_gates.sh`: gates 1/6 validate **every** `examples/*.json` board (runtime validator + JSON Schema); gate 7 adds a hybrid-3D thumbnail smoke alongside the 2D demo.
- Docs scaffolding: `docs/project-plan.md` (living plan + task status) and `docs/index.md` (docs entrypoint); version metadata synced to 1.3.0 (`pyproject.toml`, installer); README gains a Dependencies & Licensing section (Blender GPL subprocess note).
- 218 → 285 tests; all gates pass locally (8/8).

### Fixed
- 9:16 hybrid HUD: telemetry cards now dock in a two-column band above the 3D stage inside Shorts/Reels safe zones (previously the 16:9 gutter layout stranded cards at the canvas edges); regression test added.
- Advisory mypy pass (not enforced): `blender_plate.build_scene` annotated to
  return the scene (TYPE_CHECKING bpy import); `build_demo.board` annotated as
  `dict`; `audio_dsp` redundant re-annotation removed; `camera.zoom_at` coerces
  its `Any`-typed easing call to `float` at the boundary. No runtime behavior
  change; mypy remains advisory only.

## [1.2.0] — 2026-11-18

### Added
- `tests/test_elements.py`, `tests/test_render_engine.py` — direct coverage for the
  two largest runtime modules (previously smoke-only): helper math, dispatcher
  behavior, per-painter no-crash across `t ∈ {0, 0.5, 1}`, pixel-presence checks,
  image-painter failure path, Bresenham frame-quantization invariants.
- `tests/test_schemas_contract.py` — the hand-rolled runtime validator and
  `schemas/storyboard.schema.json` must agree on rejection mutations; new
  gate 6/8 in `ci_gates.sh` validates the example storyboard against its schema
  (`check-jsonschema`).
- `tests/test_code_syntax.py` — unit tests for the new code_terminal tokenizer.
- Regex syntax highlighting in the `code_terminal` element (comments / strings /
  numbers / keywords across Python/JS/TS/Rust-ish), rendered in bundled JetBrains Mono.
- `verify_output.py` `audio_not_silent` check — ffmpeg `silencedetect`
  (−50 dB / 0.8 s), 0.75 coverage threshold (`--max-silence-fraction`),
  parser + coverage unit tests and a silent-MP4 integration test.
- Bundled OFL JetBrains Mono v2.304 (`assets/fonts/`, SHA-256 pinned, license
  verbatim); canvas prefers it for mono. The `code_report` archetype is now
  OS-independent.
- `frame_counts()` in `render_engine.py` — cumulative Bresenham quantization;
  multi-scene A/V drift is now provably bounded (7 × 0.35 s @ 30 fps: 74 vs 70 frames).
- Direct `stick_rig` / `system_architecture` painter tests.

### Changed
- `elements.py` (940-line god module) split into `scripts/elements/` package
  (`_shared`, `scenes`, `text`, `dataviz`, `code`, `figures`, `media`);
  public API unchanged via re-exports.
- `fetch_assets.py`: https-only (incl. redirect targets), 50 MB cap on
  Content-Length/streamed bytes; `FetchError` subclasses `OSError`.
- Installer now copies the `scripts/elements/` package (previously
  `scripts/*.py` would have installed a broken skill).
- 199 → 218 tests; all gates pass locally (8/8).

### Removed
- GitHub Actions (`.github/workflows/skill-ci.yml`) — billing-locked; permanently
  red. Verification is local-first; the GitLab mirror remains optional and
  configured-not-verified.

## [1.1.0] — 2026-11-18

- Stage 1 multi-source licensed imagery (`fetch_assets.py`): Openverse +
  Wikimedia Commons (original-res 2048 px) + iNaturalist, one
  `by`/`by-sa`/`cc0`/`pdm` allowlist, `*-nd`/`*-nc` rejected, PIL-verified,
  cross-source deduped, attribution manifest baked into `image` elements.
- Raster `image` element: cover/contain/`backdrop_blur` (social bleed),
  Ken Burns drift, safe-zone `attribution_y` credits.
- Bundled OFL Inter v4.1 (SHA-256 pinned); canvas prefers it.
- Optional `blender_plate.py` (headless Workbench, transparent PNGs:
  `earth` / `iceberg` / `ringed`); never a hard requirement.
- GitLab CI mirror committed (`.gitlab-ci.yml`) + `scripts/ci_gates.sh` as
  the single gate entrypoint.

## [1.0.0] — 2026-11-15

- Initial verified pipeline: investigation brief → audio-first timing →
  storyboard → 2x-supersampled Pillow frames → ffmpeg H.264/AAC → ffprobe QC.
- 132 tests at release; Pillow + stdlib only; no golden images by design.
