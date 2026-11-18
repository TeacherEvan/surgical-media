# Surgical Media — Project Plan & Task Status

**Version:** 1.3.0 (in progress) · **Updated:** 2026-11-19 · **Owner:** Evan (TeacherEvan), agent-assisted
**Contract:** code + `tests/` are the contract; this plan is the living map. Verification is local-first — `bash scripts/ci_gates.sh` green *is* the quality bar ([ADR 0002](adr/0002-local-first-verification.md)).

Docs entrypoint: [`docs/index.md`](index.md) · Human manual: [`README.md`](../README.md) · Agent manifest: [`SKILL.md`](../SKILL.md) · Agent rules: [`AGENTS.md`](../AGENTS.md) · Release history: [`CHANGELOG.md`](../CHANGELOG.md)

## 1. What this project is

A deterministic, QC-gated pipeline that turns a topic prompt into a social-ready MP4:

```
research brief → audio-first timing (tts_align) → storyboard.json (schema-validated)
→ 2x-supersampled Pillow frames (render_engine) → ffmpeg H.264/AAC master → ffprobe QC
```

As of v1.3.0 a scene may optionally carry `scene_spec` + `backend` and route to a
parametric 3D pass (exploded hardware, stellarator/orbital torus) with a
motion-tracked HUD — Blender-optional, stdlib software renderer always available
([ADR 0003](adr/0003-optional-3d-scene-backends.md)).

## 2. Architecture map

| Layer | Files | Notes |
| :--- | :--- | :--- |
| Timing | `scripts/tts_align.py`, `scripts/audio_dsp.py` | Audio-first; measured edge-tts WordBoundary or offline syllable model; never re-split joined strings |
| Contract | `schemas/*.schema.json`, `scripts/storyboard.py` | Draft 2020-12 + runtime validator, pinned to parity by `tests/test_schemas_contract.py` and `tests/test_scene_spec_integration.py` |
| 2D render | `scripts/render_engine.py`, `scripts/canvas.py`, `scripts/camera.py`, `scripts/elements/`, `scripts/rig.py`, `scripts/easings.py` | RGB end-to-end, 2x SSAA floor, bloom pyramid, safe zones |
| 3D backends | `scripts/scene_router.py`, `scripts/software_3d_projection.py`, `scripts/hybrid_compositor.py`, `scripts/layout_solver.py`, `scripts/blender_runner.py` | Routing + capability probe; stdlib 4×4 look-at/Painter's sort; SAT-solved HUD cards; optional headless Blender bake with software fallback |
| Imagery | `scripts/fetch_assets.py`, `scripts/blender_plate.py` | Open-licensed photos (allowlist `by`/`by-sa`/`cc0`/`pdm`), optional Workbench plates |
| QC | `scripts/verify_output.py`, `scripts/ci_gates.sh` | yuv420p/H.264 high 4.2/+faststart, −14 LUFS, ≤150 ms A/V drift, silence detection; 8 local gates |
| Docs | `references/`, `docs/adr/`, this plan | Element catalog + 3D backend specs in [`references/storyboard-guide.md`](../references/storyboard-guide.md) |

Examples: [`examples/tri_archetype_storyboard.json`](../examples/tri_archetype_storyboard.json) (generated — regenerate via `scripts/build_demo.py`, never hand-edit) · [`examples/hybrid_3d_storyboard.json`](../examples/hybrid_3d_storyboard.json) (hand-written 3D HUD showcase).

## 3. Task status — v1.3.0 wave

### Done (verified locally)

| Item | Evidence |
| :--- | :--- |
| Scene routing (`auto`/`blender_hybrid`/`blender_3d`/`canvas_2d`/`manim_math`) + Blender ≥3.6 capability probe | `scripts/scene_router.py`, `tests/test_scene_router.py` |
| Stdlib software 3D projection + anchor tracks | `scripts/software_3d_projection.py`, `tests/test_software_3d_projection.py` |
| Motion-tracked HUD (reticles, elbow leaders, glass cards) + SAT layout solver | `scripts/hybrid_compositor.py`, `scripts/layout_solver.py` + their tests |
| Optional headless Blender bake (EEVEE/Cycles, motion blur, glare probes, anchor export) | `scripts/blender_runner.py`, `tests/test_blender_runner.py` |
| `scene_spec`/`backend` schema + validator parity (elements-or-scene_spec) | `schemas/storyboard.schema.json`, `scripts/storyboard.py`, `tests/test_scene_spec_integration.py` |
| Hybrid example board validates + paints | `examples/hybrid_3d_storyboard.json`, gates 1/6/7 in `scripts/ci_gates.sh` |
| ADR 0003 + storyboard-guide scene-backend section | [`adr/0003-optional-3d-scene-backends.md`](adr/0003-optional-3d-scene-backends.md), [`references/storyboard-guide.md`](../references/storyboard-guide.md) |
| Docs scaffolding: this plan + [`index.md`](index.md); version metadata synced (pyproject, installer, README, SKILL) | this file; `git diff pyproject.toml install_surgical_media.sh` |
| Legal note: Blender GPL subprocess / edge-tts GPL-3.0 optional / MIT unchanged | README → Dependencies & Licensing; ADR 0003 Consequences |
| Gate hardening: all `examples/*.json` validated (gates 1/6); hybrid thumbnail smoke (gate 7) | `scripts/ci_gates.sh` |

### Pending / open (explicit gaps — not hidden)

| ID | Item | Action needed | Owner |
| :--- | :--- | :--- | :--- |
| P-01 | GitLab mirror **configured, never executed** | Import repo (Repository by URL), run one pipeline, record result here + ADR 0002 | Evan |
| P-02 | v1.3.0 not tagged/pushed | Finish wave → `ci_gates.sh` green → fast-forward push `main` → tag `v1.3.0` (main is protected: linear history only) | Evan |
| P-03 | 4 schema categories unimplemented: `network_topology_3d`, `rigid_body_physics_3d`, `mathematical_manifold_3d`, `external_asset_3d` | By design raise loud `NotImplementedError`; implement only with a tested use case (claims = code) | future |
| P-04 | `manim_math` backend accepted-with-warning, renders as `canvas_2d` | Manim deliberately excluded (ADR 0001/0003); no action unless policy changes | — |
| P-05 | mypy advisory only (configured, not enforced, not installed in gate venv) | Optional: enforce after a clean strict pass | Evan |
| P-06 | markdownlint fails on pre-existing house docs (MD022/MD031/MD034/MD060) | Fix `references/` + `docs/adr/` formatting before ever adding it as a gate | future |
| P-07 | Blender-path verification is host-dependent | Blender 5.3 present on this host; capability probes in `blender_runner.py` must keep passing on 4.2–4.5/5.x hosts | agents |

## 4. Invariants (do not regress)

The full list lives in [`AGENTS.md`](../AGENTS.md) → "Hard-won invariants" and [`SKILL.md`](../SKILL.md) → "Hard Invariants". Headlines: audio-first timing; yuv420p or nothing; RGB-only buffers; no NumPy ever; Blender optional, never required; claims = tested code; zero PII; no golden-image tests; open-licensed imagery only (AI generation is not a fallback).

## 5. Verification contract

```bash
bash scripts/ci_gates.sh   # 8 gates: boards → ruff → format → pytest → metaschema → example-vs-schema → thumbnails (2D + hybrid) → draft render + ffprobe QC
```

Single gate detail and the local-first decision: [ADR 0002](adr/0002-local-first-verification.md). Test counts quoted in docs must match the current suite run (constant-sweep rule in the documentation-maintenance workflow).

## 6. Design history (input, not contract)

- [`docs/plans/Conversation with Gemini.txt`](plans/Conversation%20with%20Gemini.txt) — the multi-engine design conversation behind ADR 0003 (NumPy-heavy reference implementation was deliberately NOT adopted; see ADR 0003 Context).
- `Concept/` — original pipeline design transcript.