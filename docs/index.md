# Documentation Index

Entrypoint for surgical-media docs. The contract is code + `tests/`; these documents explain and record it.

## Plan & status

- [`project-plan.md`](project-plan.md) — living plan, architecture map, task status (done vs pending, with owners)
- [`../CHANGELOG.md`](../CHANGELOG.md) — release history (Keep a Changelog style)

## Architecture decision records

- [`adr/0001-stdlib-first-verified-pipeline.md`](adr/0001-stdlib-first-verified-pipeline.md) — stdlib + Pillow, no NumPy/Manim/MoviePy; perf postscript
- [`adr/0002-local-first-verification.md`](adr/0002-local-first-verification.md) — hosted CI removed; `scripts/ci_gates.sh` is the gate; GitLab mirror configured-not-verified
- [`adr/0003-optional-3d-scene-backends.md`](adr/0003-optional-3d-scene-backends.md) — `scene_spec` routing, software 3D canonical, Blender optional; license footprint note
- [`adr/0004-optional-threejs-webgl-backend.md`](adr/0004-optional-threejs-webgl-backend.md) — optional headless Three.js WebGL backend (`threejs_hybrid`/`threejs_3d`, Node ≥ 22 native CDP, local `three`, Z-up camera parity, `network_topology_3d`)

- [`adr/0005-production-job-layer.md`](adr/0005-production-job-layer.md) — 3.0 job layer (flat `scripts/job_*.py`, file-based agent contract, prepare-never-publish, human approval bound to video hash)
- [`adr/0006-priority-social-video-pipeline.md`](adr/0006-priority-social-video-pipeline.md) — merge the social-media-studio-pro update into this skill; one priority pipeline, three cherry-picked scripts, dual safe-zone masks

## 3.0 wave

- [`audits/initial-baseline.md`](audits/initial-baseline.md) — Wave 0 audit (capability inventory, measured baseline)
- [`audits/surgical-media-surgical-audit-2026-11-22.md`](audits/surgical-media-surgical-audit-2026-11-22.md) — Principal-10 surgical audit & post-remediation delta (40 → 97/100)
- [`plans/Surgical_Media_3.0_Master_Implementation_Plan.md`](plans/Surgical_Media_3.0_Master_Implementation_Plan.md) — proposal (Waves 2–5 deferred)
- [`../references/job-workflow.md`](../references/job-workflow.md) — CLI + lifecycle

## Design history (input, not contract)

- [`plans/Conversation with Gemini.txt`](plans/Conversation%20with%20Gemini.txt) — multi-engine design conversation behind ADR 0003
- `../Concept/` — original pipeline design transcript

## Priority pipeline (v3.2.0 — image-first)

- [`../SKILL.md`](../SKILL.md) — the single entry point: 8-step image-first orchestration from intake to QC
- [`../references/specs-licensing-compliance.md`](../references/specs-licensing-compliance.md) — platform caps, dual 9:16 safe boxes, 2026 copyright/AI rules, model licenses
- [`../references/style-and-architecture.md`](../references/style-and-architecture.md) — 7-style execution matrix, locked timeline, originality gate
- [`../references/pipeline-scripts.md`](../references/pipeline-scripts.md) — CLI index for the three merged utilities
- [`../references/render-templates.md`](../references/render-templates.md) — pro templates mapped to shipped Blender/Three.js/FFmpeg code

## Field guides & contracts

- [`../references/storyboard-guide.md`](../references/storyboard-guide.md) — element catalog, camera semantics, safe zones, **3D scene backends** (`scene_spec` + `backend`)
- [`../references/archetypes.md`](../references/archetypes.md) — visual archetype field guide
- [`../references/ffmpeg-encoding.md`](../references/ffmpeg-encoding.md) — encoder/loudness/QC reference
- [`../schemas/`](../schemas/) — Draft 2020-12 contracts (investigation brief, beat script, storyboard)
- [`../examples/`](../examples/) — renderable boards: **`photo_essay_storyboard.json` (image-first reference)**, `tri_archetype_storyboard.json` (generated showcase), `hybrid_3d_storyboard.json` (optional 3D HUD showcase)

## Project surfaces

- [`../README.md`](../README.md) — human manual (quick start, repo map, verification, licensing)
- [`../SKILL.md`](../SKILL.md) — agent manifest (≤120 lines: stages, invariants, gotchas)
- [`../AGENTS.md`](../AGENTS.md) — agent working rules (repo shape, commands, hard-won invariants)
- [`../SECURITY.md`](../SECURITY.md) — scope + reporting paths
- [`../LICENSE`](../LICENSE) — MIT
