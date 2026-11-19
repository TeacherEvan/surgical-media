# Surgical Media — Project Plan & Task Status

**Version:** 1.4.0 · **Updated:** 2026-11-19 · **Owner:** Evan (TeacherEvan), agent-assisted
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
| 3D backends | `scripts/scene_router.py`, `scripts/software_3d_projection.py`, `scripts/hybrid_compositor.py`, `scripts/layout_solver.py`, `scripts/blender_runner.py`, `scripts/threejs_bridge.py`, `scripts/threejs/` | Routing + capability probes; stdlib 4×4 look-at/Painter's sort; SAT-solved HUD cards; optional headless Three.js WebGL PBR bake (Node ≥22 CDP) and optional Blender bake, both with software fallback |
| Imagery | `scripts/fetch_assets.py`, `scripts/blender_plate.py` | Open-licensed photos (allowlist `by`/`by-sa`/`cc0`/`pdm`), optional Workbench plates |
| QC | `scripts/verify_output.py`, `scripts/ci_gates.sh` | yuv420p/H.264 high 4.2/+faststart, −14 LUFS, ≤150 ms A/V drift, silence detection; 9 local gates |
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
| Hybrid example board validates + paints | `examples/hybrid_3d_storyboard.json`, gates 1/7/8 in `scripts/ci_gates.sh` |
| `organic_serpent_3d` — authored-from-pattern snake asset (stdlib polygon tube + bpy curve builder, head/body/tail tracking) | `scripts/software_3d_projection.py`, `scripts/blender_runner.py`, their tests; router/validator/schema registration |
| Design-history rule documented (plans = templates, not copyable assets) | `SKILL.md`, `AGENTS.md`, ADR 0003 |
| ADR 0003 + storyboard-guide scene-backend section | [`adr/0003-optional-3d-scene-backends.md`](adr/0003-optional-3d-scene-backends.md), [`references/storyboard-guide.md`](../references/storyboard-guide.md) |
| Docs scaffolding: this plan + [`index.md`](index.md); version metadata synced (pyproject, installer, README, SKILL) | this file; `git diff pyproject.toml install_surgical_media.sh` |
| Legal note: Blender GPL subprocess / edge-tts LGPL-3.0 optional / MIT unchanged | README → Dependencies & Licensing; ADR 0003 Consequences |
| Gate hardening: all `examples/*.json` validated (gates 1/7); hybrid thumbnail smoke (gate 8) | `scripts/ci_gates.sh` |
| mypy strict enforced — the whole `scripts/` tree is annotated; gate 4/9 fails on any issue | `pyproject.toml` (`strict = true`), `scripts/ci_gates.sh`, `.pre-commit-config.yaml` |
| Failure-path coverage: software-3D exception containment, broken Blender plate → software fallback, plate pre-render timeout/non-zero exit, anchor-track load/merge, `blender_runner` pure helpers | `tests/test_fallback_paths.py` (16 tests; suite 285 → 302) |
| Packaging declared: `pyproject.toml` `dependencies` + `tts`/`dev` extras + coverage config; `requirements-dev.txt` gate venv; GitLab mirror installs it; `.editorconfig`; `.gitignore` hardened | `pyproject.toml`, `requirements-dev.txt`, `.gitlab-ci.yml`, `.gitignore`, `.editorconfig` |
| Agent MCP wiring (project-local, pinned, no secrets): `context7` (`sequential-thinking` attempted; removed — npx egress timeout) | `opencode.json` |
| `validate_storyboard` decomposed into per-section validators; error messages byte-identical (parity contract tests) | `scripts/storyboard.py`, `tests/test_schemas_contract.py` |
| Full local gate run green (9/9): 302 tests — all pass; draft render + ffprobe QC `ok:true`, 0 ms A/V drift | `bash scripts/ci_gates.sh` run 2026-11-19 (requirements-dev.txt venv) |
| Hybrid board renders end-to-end **without Blender** (forced `BLENDER_BIN` fallback): QC `ok:true`, 3.0 s / 720p30 / yuv420p | `BLENDER_BIN=/nonexistent-blender python scripts/render_engine.py --storyboard examples/hybrid_3d_storyboard.json --output … --quality draft` |
| Hybrid board renders end-to-end **with Blender 5.3.0**: both scenes pre-baked (45 frames each), no fallback warnings, QC `ok:true`, 0 ms drift | same command without `BLENDER_BIN` override, run 2026-11-19 |

### Pending / open (explicit gaps — not hidden)

| ID | Item | Action needed | Owner |
| :--- | :--- | :--- | :--- |
| P-01 | GitLab mirror **configured, never executed** | Import repo (Repository by URL), run one pipeline, record result here + ADR 0002 | Evan |
| P-02 | v1.3.0 tagged locally, not pushed | Push `main` (fast-forward only) + `git push origin v1.3.0` when ready — main is protected: linear history only | Evan |
| P-03 | 3 schema categories unimplemented: `rigid_body_physics_3d`, `mathematical_manifold_3d`, `external_asset_3d` (`network_topology_3d` implemented in v1.4.0 across Software 3D, Three.js, and Blender) | By design raise loud `NotImplementedError`; implement only with a tested use case (claims = code) | future |
| P-04 | `manim_math` backend accepted-with-warning, renders as `canvas_2d` | Manim deliberately excluded (ADR 0001/0003); no action unless policy changes | — |
| P-05 | ~~mypy advisory only~~ — **resolved 2026-11-19**: strict-enforced as gate 4/9, `scripts/` annotated (249 → 0), verified 9/9 green | Keep it green; the gate now fails on any regression | — |
| P-06 | markdownlint fails on pre-existing house docs (MD022/MD031/MD034/MD060) | Fix `references/` + `docs/adr/` formatting before ever adding it as a gate | future |
| P-07 | Blender-path verification is host-dependent | Blender 5.3 present on this host; capability probes in `blender_runner.py` must keep passing on 4.2–4.5/5.x hosts. Measured 2026-11-19 (CPU-only N150): EEVEE bake ≈ 6–10 s/frame — a 45-frame scene takes ~5–8 min, the 3 s hybrid board ~16 min with Blender vs ~2 min software-only. The per-scene bake timeout is 600 s (`render_engine._prerender_blender_plates`); slower scenes fall back to software by design — keep hero scenes short. | agents |

## 4. Invariants (do not regress)

The full list lives in [`AGENTS.md`](../AGENTS.md) → "Hard-won invariants" and [`SKILL.md`](../SKILL.md) → "Hard Invariants". Headlines: audio-first timing; yuv420p or nothing; RGB-only buffers; no NumPy ever; Blender optional, never required; claims = tested code; zero PII; no golden-image tests; open-licensed imagery only (AI generation is not a fallback).

## 5. Verification contract

```bash
bash scripts/ci_gates.sh   # 9 gates: boards → ruff → format → mypy --strict → pytest → metaschema → example-vs-schema → thumbnails (2D + hybrid) → draft render + ffprobe QC
```

Single gate detail and the local-first decision: [ADR 0002](adr/0002-local-first-verification.md). Test counts quoted in docs must match the current suite run (constant-sweep rule in the documentation-maintenance workflow).

## 6. Design history (input, not contract)

- [`docs/plans/Conversation with Gemini.txt`](plans/Conversation%20with%20Gemini.txt) — the multi-engine design conversation behind ADR 0003 (NumPy-heavy reference implementation was deliberately NOT adopted; see ADR 0003 Context).
- `Concept/` — original pipeline design transcript.
