# Surgical Media (`v3.2.0`)

**The priority pipeline for surgical-media content generation.** A deterministic, QC-gated,
research-backed workflow that turns a topic prompt into a social-ready MP4 — mandatory
Time/Style/Platform intake, live spec refresh, authentic attributed imagery, audio-first timing,
storyboard, 2x-supersampled Pillow rendering (plus optional Three.js/Blender), ffmpeg
H.264/AAC master, and hard QC gates. The `social-media-studio-pro` update was merged into this
skill rather than shipped as a second overlapping video skill.

## Quick Start

```bash
# system deps: python>=3.10, ffmpeg + ffprobe on PATH
python3 -m pip install -r requirements.txt          # Pillow ≥ 10
python3 -m pip install -r requirements-tts.txt      # optional: edge-tts voice synthesis
python3 -m pip install -r requirements-dev.txt      # hacking on this repo: pytest/jsonschema/ruff/mypy/check-jsonschema
(cd scripts/threejs && npm install)                 # optional: headless Three.js WebGL 3D backend (requires Node >=22 + Chromium)

python3 scripts/build_demo.py                       # (re)generate the example board
python3 scripts/render_engine.py --demo --thumbnails /tmp/sm_thumbs   # seconds — see each scene first
python3 scripts/render_engine.py --demo --output demo_showcase.mp4    # ~70s on 4 cores
```

`demo_showcase.mp4` is a 14.4 s / 1280x720 / 30 fps three-scene showcase (`geometry_rig` → `doc_essay` → `code_report`). The render ends with an ffprobe QC pass; a failed gate exits 3.

Produce an actual video through the v3.2.0 image-first pipeline:

```bash
# 1. Write script.json with subject + per-scene visual hints (see schemas/script.schema.json)

# 2. Fetch licensed photographs — one query PER BEAT, not one for the whole video
python3 scripts/fetch_scene_assets.py --input script.json --out-dir assets \
  --subject "<subject>" --count 3     # --dry-run prints the derived query plan

# 3. Voice + wire plates into the board (generic filler flagged placeholder:true is stripped)
python3 scripts/tts_normalizer.py --input script.json --output script.spoken.json --report normalization.json
python3 scripts/tts_align.py --input script.spoken.json --output storyboard.json --aspect 9:16 \
  --subject "<subject>" --assets-manifest assets/manifest.json --brief investigation.json
python3 scripts/storyboard.py storyboard.json
python3 scripts/render_engine.py --storyboard storyboard.json --output final.mp4 --quality final
python3 scripts/qc_gate.py --video final.mp4 --format 9:16 --preset strict --frames-dir qc_frames --credits CREDITS.md --json qc_report.json
```

**Image-first is enforced.** `pipeline_preflight.py --board … --brief …` fails unless ≥60% of
scenes show the subject and no beat shows filler-only visuals (`subject_imagery`);
`style_lint.py --manifest assets/manifest.json` flags `no_subject_imagery`,
`low_visual_coverage`, `placeholder_visual` and `unused_assets`. Standalone boards use
`python3 scripts/asset_wire.py --board board.json --manifest assets/manifest.json --brief investigation.json --out board.wired.json`.
See [`examples/photo_essay_storyboard.json`](examples/photo_essay_storyboard.json) for a
rendering reference (full-bleed `cover`, 9:16 `backdrop_blur`, safe-zone credits).

For named real people use `scripts/media_harvester.py` (authentic portraits, face-centered
reframing, subtle safe-zone credit badges, `credits.json` + `CREDITS.md`). Before any render,
read `references/specs-licensing-compliance.md` and re-check live platform rules; see
`references/style-and-architecture.md` for the 7-style matrix and the originality gate.

## Repository Layout

| Component | Purpose |
| :--- | :--- |
| [`SKILL.md`](SKILL.md) | **Priority pipeline** (v3.2.0): image-first 8-step orchestration, invariants, gotchas (≤120 lines) |
| [`scripts/fetch_scene_assets.py`](scripts/fetch_scene_assets.py) | Per-beat licensed imagery acquisition: derives one query per scene, dedupes, merges into one manifest |
| [`scripts/asset_wire.py`](scripts/asset_wire.py) | Missing link: scores manifest plates against narration/`visual.query`/brief anchors, strips placeholder filler, inserts credited subject imagery into board |
| [`examples/photo_essay_storyboard.json`](examples/photo_essay_storyboard.json) | Image-first rendering reference — subject plates on every scene, no 3D slop |
| [`references/specs-licensing-compliance.md`](references/specs-licensing-compliance.md) | Platform caps, dual 9:16 safe boxes, 2026 copyright/AI rules, commercial TTS + renderer licenses |
| [`references/style-and-architecture.md`](references/style-and-architecture.md) | 7-style execution matrix, single locked timeline, originality gate |
| [`references/pipeline-scripts.md`](references/pipeline-scripts.md) / [`references/render-templates.md`](references/render-templates.md) | CLI index for the merged utilities; pro templates mapped to shipped code |
| [`scripts/spec_refresh.py`](scripts/spec_refresh.py) | Executable Step 2: verifies the baked platform/licensing baseline and (optionally) probes live sources; exit 3 on drift |
| [`scripts/pipeline_preflight.py`](scripts/pipeline_preflight.py) | Executable intake/style mapping + structure gate: 7-style matrix, intro/outro contract, sourced-brief originality check, image-first `subject_imagery` check |
| [`scripts/style_lint.py`](scripts/style_lint.py) | Advisory anti-slop lint: adds `no_subject_imagery`, `placeholder_visual`, `unused_assets` (pass `--manifest`) |
| [`scripts/style_apply.py`](scripts/style_apply.py) | Writes the 7-style matrix into a timed board (presets, archetypes, intro window, outro scaffolding); idempotent, reports all changes |
| [`scripts/tts_normalizer.py`](scripts/tts_normalizer.py) | Dates/numbers/currency/hashtags → spoken words before local TTS, with reviewable change report |
| [`scripts/media_harvester.py`](scripts/media_harvester.py) | Authentic real-person portraits, face-centered reframing, subtle safe-zone credit badges, `credits.json` + `CREDITS.md` |
| [`scripts/qc_gate.py`](scripts/qc_gate.py) | Hard gate: ebur128, dead-air, dual safe-zone audit overlays, credits check; exit 3 on failure |
| [`scripts/tts_align.py`](scripts/tts_align.py) | Beat script → timing-locked storyboard (edge-tts + ffprobe, or offline WPM estimate; syllable-weighted word allocation) |
| [`scripts/storyboard.py`](scripts/storyboard.py) | Stdlib storyboard validator & timeline helpers |
| [`scripts/render_engine.py`](scripts/render_engine.py) | Storyboard → MP4. Supersampled frames stream raw into ffmpeg; QC runs inline |
| [`scripts/elements/`](scripts/elements/) | Painter package split by family: `scenes`, `text`, `dataviz`, `code` (with syntax highlighting), `figures`, `media`, `svg` (inline/file SVG vector art + animated line-drawing + bloom), `visual` (`orb_pulse`, `dot_field`, `orbit_ring`, `equalizer`, `typewriter_text`, `leader_arrow` — personality painters) — registry re-exported from `elements/__init__.py` |
| [`scripts/canvas.py`](scripts/canvas.py) | `SupersampledCanvas` (2x SSAA, BOX integer downsample), half-res dual-radius Gaussian bloom, safe zones, HUD/stage/caption partition |
| [`scripts/camera.py`](scripts/camera.py) | `WorldCamera2D` — pre-raster zoom/pan with easing + deterministic trauma shake |
| [`scripts/rig.py`](scripts/rig.py) | Analytical two-bone IK, hollow-head stick-figure renderer |
| [`scripts/audio_dsp.py`](scripts/audio_dsp.py) | Stdlib SFX synth (chime/pop/whoosh/click/buzz), just-intonation pad, sidechain ducking, −1 dBFS ceiling, stereo WAV I/O |
| [`scripts/easings.py`](scripts/easings.py) | `ease_out_expo` / `ease_in_out_cubic` / `spring_pop` / … |
| [`scripts/verify_output.py`](scripts/verify_output.py) | ffprobe assertions (streams, H.264, yuv420p, fps, ≤150 ms A/V drift) |
| [`scripts/fetch_assets.py`](scripts/fetch_assets.py) | Stage 1 subject imagery: Openverse + Wikimedia Commons + iNaturalist, license allowlist (`by`/`by-sa`/`cc0`/`pdm`), PIL-verified, cross-source deduped, writes `assets/manifest.json` |
| [`scripts/blender_plate.py`](scripts/blender_plate.py) | Optional Blender (Workbench, headless) 3D plates — `earth` / `iceberg` / `ringed` → transparent PNG for the `image` element; exits 2 cleanly without Blender |
| [`scripts/scene_router.py`](scripts/scene_router.py) | Scene backend routing: `auto`/`threejs_hybrid`/`threejs_3d`/`blender_hybrid`/`blender_3d`/`canvas_2d`/`manim_math` + Three.js & Blender capability probes |
| [`scripts/threejs_bridge.py`](scripts/threejs_bridge.py) + [`scripts/threejs/`](scripts/threejs/) | Optional headless Three.js WebGL PBR renderer (Node ≥22 native CDP + local Chromium + `three.module.js`, Z-up camera parity, offline, automatic software fallback) |
| [`scripts/software_3d_projection.py`](scripts/software_3d_projection.py) | Stdlib 4×4-perspective renderer — parametric exploded-hardware, stellarator-torus, undulating snake (`organic_serpent_3d`), and `network_topology_3d`; returns normalized 3D→2D anchor tracks |
| [`scripts/hybrid_compositor.py`](scripts/hybrid_compositor.py) | Motion-tracked HUD: reticles, 45° elbow leaders, glass telemetry cards placed by the SAT layout solver |
| [`scripts/layout_solver.py`](scripts/layout_solver.py) | AABB min-axis collision solver with locked repulsors + 24 px canvas clamp (telemetry-card placement) |
| [`scripts/blender_runner.py`](scripts/blender_runner.py) | Headless Blender (bpy) per-scene bake: EEVEE/Cycles detection, motion blur, `world_to_camera_view` anchor export; hardware, stellarator, snake, and network topology builders |
| [`assets/fonts/`](assets/fonts/) | Bundled OFL Inter + JetBrains Mono + Cormorant Garamond — captions/HUD/code/poetic faces, SHA-256 pinned, licenses included |
| [`scripts/build_demo.py`](scripts/build_demo.py) | Regenerates `examples/tri_archetype_storyboard.json` |
| [`schemas/`](schemas/) | Draft 2020-12 contracts for the investigation brief, beat script, and storyboard |
| [`references/`](references/) | Priority pipeline specs/licensing, 7-style matrix, CLI/template indexes, archetype field guide, storyboard element catalog, ffmpeg/loudness reference |
| [`tests/`](tests/) | `pytest` suite — unit + rendered-MP4 integration (requires ffmpeg) |
| [`docs/adr/`](docs/adr/) | Architecture decision records |
| [`docs/project-plan.md`](docs/project-plan.md) | Living plan + task status (done vs pending); [`docs/index.md`](docs/index.md) is the docs entrypoint |

## Verification Gates

```bash
python3 -m pytest tests/ -q       # all green, ffmpeg integration included
ruff check --no-cache scripts/ tests/
python3 scripts/storyboard.py examples/tri_archetype_storyboard.json
check-jsonschema --check-metaschema schemas/*.schema.json
python3 scripts/qc_gate.py --video final.mp4 --format 9:16 --preset strict --json qc_report.json
```

Or everything, in one call: `bash scripts/ci_gates.sh`

### Verification (local-first)

- **No hosted CI by choice.** GitHub Actions was billing-locked (jobs never started), so the workflow was removed 2026-11-18 rather than left as a permanent red check. `scripts/ci_gates.sh` is the enforced standard and runs on every change: storyboard validation → ruff → format → `mypy --strict` → full `pytest` suite → schema metaschema → example-vs-schema validation → thumbnail smoke gate → draft render + ffprobe QC → advisory `style_lint` → production-job examples → measured loudness/dead-air/safe-zone audit (12 gates). Run it before pushing; its green exit *is* this repo's quality bar. Install the toolchain with `requirements-dev.txt`.
- `main` is protected on GitHub: required linear history, force-push and branch deletion blocked, enforced for admins too. Direct fast-forward pushes remain allowed (the current flow).
- The decision is recorded in [ADR 0002](docs/adr/0002-local-first-verification.md). An optional GitLab mirror ([`.gitlab-ci.yml`](.gitlab-ci.yml)) executes the identical script once a project is imported: **New project → Import project → Repository by URL** → paste this repo's URL → create. Optionally enable *Settings → Repository → Mirroring* to auto-sync `main`. The mirror is **configured, not verified** — do not treat its presence as a green pipeline until one passes.

## Install as a Skill

```bash
./install_surgical_media.sh [target_dir]   # default: ~/.hermes/skills/creative/surgical-media
./install_surgical_media.sh --all-agents   # sync to Hermes/OpenCode, Antigravity, Agents, Claude, Codex
```

## Security

See [`SECURITY.md`](SECURITY.md). Local/offline by design; report license or
URL-safety issues via GitHub advisories or labeled issues.

## Dependencies & Licensing

- Repo code: **MIT** ([`LICENSE`](LICENSE)). Runtime deps: Pillow ≥ 10.1 + ffmpeg/ffprobe on PATH; audio and geometry are stdlib-only ([ADR 0001](docs/adr/0001-stdlib-first-verified-pipeline.md)).
- **Three.js** (MIT) is optional and installed locally under `scripts/threejs/` (`npm install`), driven offline via headless Chromium over Node ≥ 22 native CDP — zero browser-automation npm dependencies; MIT license unchanged ([ADR 0004](docs/adr/0004-optional-threejs-webgl-backend.md)).
- **Blender** (GNU GPL, Blender Foundation) is optional and invoked only as an external subprocess (`blender -b -P scripts/blender_runner.py`); nothing here imports `bpy` or links Blender, so the MIT footprint is unchanged ([ADR 0003](docs/adr/0003-optional-3d-scene-backends.md)).
- **edge-tts** (LGPL-3.0) is an optional, user-installed extra (`requirements-tts.txt`) for the online voice path only — never bundled; the offline timing path is stdlib.
- Bundled fonts: OFL-1.1 (Inter, JetBrains Mono), licenses verbatim in [`assets/fonts/`](assets/fonts/).

## Design Notes

- **Audio-first or it doesn't render.** Frame counts come from measured VO durations (ffprobe), never estimates baked into a timeline.
- **Nothing ships unverified.** If `tests/` doesn't prove it, the skill doesn't claim it.
- **No numpy dependency.** Audio and geometry are stdlib-only; Pillow is the single rendering dependency. See `docs/adr/0001-stdlib-first-verified-pipeline.md`.
- **Scene-optional parametric 3D.** A scene may carry `scene_spec` + `backend` to route to a 3D pass (exploded hardware, stellarator torus) with motion-tracked HUD telemetry — Blender-optional, stdlib renderer always available. See `docs/adr/0003-optional-3d-scene-backends.md`.
