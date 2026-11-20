# Surgical Media (`v2.3.0`)

**Deterministic, QC-gated pipeline for turning a topic prompt into a social-ready MP4 — research brief, audio-first timing, storyboard, 2x-supersampled Pillow rendering, ffmpeg H.264/AAC master, ffprobe verification.**

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

Voice an actual script offline or online:

```bash
python3 scripts/tts_align.py --input script.json --output storyboard.json --aspect 9:16
python3 scripts/storyboard.py storyboard.json
python3 scripts/render_engine.py --storyboard storyboard.json --output final.mp4 --quality final
```

## Repository Layout

| Component | Purpose |
| :--- | :--- |
| [`SKILL.md`](SKILL.md) | Agent entrypoint: stages, invariants, quick start, gotchas |
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
| [`assets/fonts/`](assets/fonts/) | Bundled OFL Inter (Regular/SemiBold/Bold) + JetBrains Mono (Regular/Bold) — captions/HUD + code archetype faces, SHA-256 pinned, licenses included |
| [`scripts/build_demo.py`](scripts/build_demo.py) | Regenerates `examples/tri_archetype_storyboard.json` |
| [`schemas/`](schemas/) | Draft 2020-12 contracts for the investigation brief, beat script, and storyboard |
| [`references/`](references/) | Archetype field guide, storyboard element catalog, ffmpeg/loudness reference |
| [`tests/`](tests/) | `pytest` suite — unit + rendered-MP4 integration (requires ffmpeg) |
| [`docs/adr/`](docs/adr/) | Architecture decision records |
| [`docs/project-plan.md`](docs/project-plan.md) | Living plan + task status (done vs pending); [`docs/index.md`](docs/index.md) is the docs entrypoint |

## Verification Gates

```bash
python3 -m pytest tests/ -q       # all green, ffmpeg integration included
ruff check --no-cache scripts/ tests/
python3 scripts/storyboard.py examples/tri_archetype_storyboard.json
check-jsonschema --check-metaschema schemas/*.schema.json
```

Or everything, in one call: `bash scripts/ci_gates.sh`

### Verification (local-first)

- **No hosted CI by choice.** GitHub Actions was billing-locked (jobs never started), so the workflow was removed 2026-11-18 rather than left as a permanent red check. `scripts/ci_gates.sh` is the enforced standard and runs on every change: storyboard validation → ruff → format → `mypy --strict` → 476 tests → schema metaschema → example-vs-schema validation → thumbnail smoke gate → draft render + ffprobe QC (10 gates: the 9 above + advisory `style_lint` on examples). Run it before pushing; its green exit *is* this repo's quality bar. Install the toolchain with `requirements-dev.txt`.
- `main` is protected on GitHub: required linear history, force-push and branch deletion blocked, enforced for admins too. Direct fast-forward pushes remain allowed (the current flow).
- The decision is recorded in [ADR 0002](docs/adr/0002-local-first-verification.md). An optional GitLab mirror ([`.gitlab-ci.yml`](.gitlab-ci.yml)) executes the identical script once a project is imported: **New project → Import project → Repository by URL** → paste this repo's URL → create. Optionally enable *Settings → Repository → Mirroring* to auto-sync `main`. The mirror is **configured, not verified** — do not treat its presence as a green pipeline until one passes.

## Install as a Skill

```bash
./install_surgical_media.sh [target_dir]   # default: ~/.hermes/skills/creative/surgical-media
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
