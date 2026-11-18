# Documentation Index

Entrypoint for surgical-media docs. The contract is code + `tests/`; these documents explain and record it.

## Plan & status

- [`project-plan.md`](project-plan.md) — living plan, architecture map, task status (done vs pending, with owners)
- [`../CHANGELOG.md`](../CHANGELOG.md) — release history (Keep a Changelog style)

## Architecture decision records

- [`adr/0001-stdlib-first-verified-pipeline.md`](adr/0001-stdlib-first-verified-pipeline.md) — stdlib + Pillow, no NumPy/Manim/MoviePy; perf postscript
- [`adr/0002-local-first-verification.md`](adr/0002-local-first-verification.md) — hosted CI removed; `scripts/ci_gates.sh` is the gate; GitLab mirror configured-not-verified
- [`adr/0003-optional-3d-scene-backends.md`](adr/0003-optional-3d-scene-backends.md) — `scene_spec` routing, software 3D canonical, Blender optional; license footprint note

## Design history (input, not contract)

- [`plans/Conversation with Gemini.txt`](plans/Conversation%20with%20Gemini.txt) — multi-engine design conversation behind ADR 0003
- `../Concept/` — original pipeline design transcript

## Field guides & contracts

- [`../references/storyboard-guide.md`](../references/storyboard-guide.md) — element catalog, camera semantics, safe zones, **3D scene backends** (`scene_spec` + `backend`)
- [`../references/archetypes.md`](../references/archetypes.md) — visual archetype field guide
- [`../references/ffmpeg-encoding.md`](../references/ffmpeg-encoding.md) — encoder/loudness/QC reference
- [`../schemas/`](../schemas/) — Draft 2020-12 contracts (investigation brief, beat script, storyboard)
- [`../examples/`](../examples/) — renderable boards: `tri_archetype_storyboard.json` (generated), `hybrid_3d_storyboard.json` (3D HUD showcase)

## Project surfaces

- [`../README.md`](../README.md) — human manual (quick start, repo map, verification, licensing)
- [`../SKILL.md`](../SKILL.md) — agent manifest (≤120 lines: stages, invariants, gotchas)
- [`../AGENTS.md`](../AGENTS.md) — agent working rules (repo shape, commands, hard-won invariants)
- [`../SECURITY.md`](../SECURITY.md) — scope + reporting paths
- [`../LICENSE`](../LICENSE) — MIT