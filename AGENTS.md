# AGENTS.md

Agent instructions for working inside the `surgical-media` skill repository. `README.md` is the human manual, `SKILL.md` the agent manifest — this file exists so you know the technical traps without boxing in your creative work.

## Creative Freedom (Guardrails Protect Correctness, Not Imagination)

- **Do not self-censor creative direction.** The invariants below exist to prevent broken playback, OOM crashes, or schema drift — **not** to restrict visual style, storytelling, or artistic ambition.
- **Mix the full visual arsenal freely:** combine procedural 2D motion graphics (`elements/*`), custom inline or file-backed **SVG vector art & animated line drawings** (`svg` element with `reveal: "draw"`, `pop`, `fade`, neon `glow`, rotation/scale), **Three.js WebGL PBR 3D** (`threejs_hybrid` / `threejs_3d`), **Blender 3D / Workbench plates** (`blender_hybrid` / `blender_3d` / `blender_plate.py`), and photography (`image`).
- **Archetypes are starting palettes, not cages.** `geometry_rig`, `doc_essay`, `code_report`, and `mixed` are creative launchpads — invent custom palettes, layer SVG illustrations over 3D plates, choreograph custom kinetic beats, or author bespoke procedural scenes whenever the subject calls for it.
- **Build what the story needs.** If a subject deserves a custom SVG illustration, a new element painter in `scripts/elements/`, or a new 3D scene generator across `software_3d_projection.py` / `scripts/threejs/scenes.mjs` / `blender_runner.py`, build it and wire its tests rather than settling for a generic placeholder. Design history (`docs/plans/`, `Concept/`) is inspiration and pattern reference, not a fixed asset library.

## Repo shape

- `main` is protected: required linear history, no force-push, no branch deletion, enforced for admins. Fast-forward pushes stay legal — never create merge commits.
- `surgical-media` is a Hermes **skill** (deterministic video pipeline: storyboard → MP4), not a published package. This directory **is** the public repo `github.com/TeacherEvan/surgical-media` (branch `main`, repo-local identity `TeacherEvan <…noreply.github.com>`). Ask before rewriting or force-pushing history.
- **v3.2.0 is the priority pipeline — image-first.** The subject must be on screen: `fetch_assets.py` → `tts_align.py --assets-manifest` / `asset_wire.py` → photo-led board. `pipeline_preflight.py:subject_imagery` and `style_lint.py:{no_subject_imagery,placeholder_visual,unused_assets}` enforce it; 3D is an optional accent, never the default. v3.1.0 merged the `social-media-studio-pro` guidance into this skill. `SKILL.md` is the 8-step orchestration.
- `docs/project-plan.md` is the living plan + task status; `docs/index.md` is the docs entrypoint.
- Runtime deps: **Pillow ≥ 10.1 + ffmpeg/ffprobe on PATH** (`requirements.txt`). `edge-tts` is optional (`requirements-tts.txt`) and **tests never use it** (offline by design). Python audio/geometry stay stdlib-only — no NumPy (`docs/adr/0001-stdlib-first-verified-pipeline.md`).
- `SKILL.md` stays ≤ 120 lines (compact agent manifest). Full element catalog and parameter specs live in `references/storyboard-guide.md`. The merged pro guidance lives in `references/specs-licensing-compliance.md` (platform caps, dual 9:16 safe boxes, 2026 copyright/AI rules, license matrix), `references/style-and-architecture.md` (7-style matrix + single locked timeline), `references/pipeline-scripts.md`, and `references/render-templates.md`.
- For factual/documentary subjects, `scripts/fetch_assets.py --query "<subject>" --out-dir assets --count 3` pulls licensed photos from Openverse + Wikimedia Commons + iNaturalist (`by`/`by-sa`/`cc0`/`pdm`, PIL-verified, https-only) and writes `assets/manifest.json` with ready-to-paste `attribution` strings. Download assets locally rather than hotlinking, and label sources clearly in-frame. For **named real people**, use `scripts/media_harvester.py` — authentic portraits, face-centered reframing (optional OpenCV), subtle safe-zone credit badges, `credits.json` + `CREDITS.md`. A downloaded manifest is **useless until wired**: pass it to `tts_align.py --assets-manifest` (or `scripts/asset_wire.py --board … --manifest … --out …`). `tts_align`'s `DEFAULT_ELEMENTS` are deliberately flagged `placeholder: true`; the wiring step strips them, inserts subject plates with the manifest attribution, and `pipeline_preflight.py:subject_imagery` fails a board with no imagery. `visual.image`/`visual.query` in the beat script art-direct each scene; `kind: svg|3d|procedural` opts out. Only `meta.visual_intent` exempts a genuine abstract showcase. Run `scripts/tts_normalizer.py` before voicing local TTS and `scripts/qc_gate.py` before delivery.

## Commands (all run green locally — the gate *is* local)

```bash
python3 scripts/storyboard.py examples/tri_archetype_storyboard.json   # demo must always validate
python3 scripts/storyboard.py examples/hybrid_3d_storyboard.json      # 3D/HUD showcase must validate too
python3 scripts/storyboard.py examples/threejs_3d_storyboard.json     # Three.js WebGL 3D showcase must validate too
ruff check --no-cache scripts/ tests/
ruff format --check --no-cache scripts/ tests/
python3 -m pytest tests/ -q                                            # 860 tests, all green
check-jsonschema --check-metaschema schemas/*.schema.json
python3 scripts/render_engine.py --demo --thumbnails /tmp/sm_thumbs     # seconds — visual smoke, no ffmpeg needed
python3 scripts/render_engine.py --storyboard examples/hybrid_3d_storyboard.json --thumbnails /tmp/sm_hybrid_thumbs   # software 3D + HUD smoke
python3 scripts/render_engine.py --storyboard examples/threejs_3d_storyboard.json --thumbnails /tmp/sm_threejs_thumbs # Three.js storyboard smoke
python3 scripts/render_engine.py --demo --output /tmp/sm_gate.mp4       # only when render code changed; exit 0 + QC ok:true
```

- Single test: `python3 -m pytest "tests/test_visual_smoke.py::test_box_downsample_keeps_thin_lines" -q`
- Verification is **local-first**: `scripts/ci_gates.sh` is the single gate (storyboard → ruff → format → mypy --strict → 860 tests → schema metaschema → all example-vs-schema → thumbnails for 2D + **photo** + hybrid 3D + Three.js 3D → draft render → ffprobe QC → style_lint on examples (report) → production-job examples → measured loudness/dead-air/safe-zone audit; 12 gates). The gate venv is `requirements-dev.txt` (mirrors `[project.optional-dependencies].dev` in `pyproject.toml`).
- **mypy strict is enforced** as gate 4/12: `pyproject.toml` sets `strict = true` and `mypy scripts/` must report zero issues.
- **markdownlint** fails on pre-existing house docs (`references/`, `docs/adr/`) — it is not a gate.
- Before spending a full render: `--estimate` (frame count / audio cost) and `--thumbnails DIR` (one PNG per scene). `final` = crf 18, demo/draft = crf 26.
- `*.mp4`, `*_work/`, `audio/`, `node_modules/`, `.venv/`, `__pycache__/`, `.pytest_cache/` are gitignored artifacts. Never commit rendered outputs.
- **Rendered deliverables go in the open workspace/repo root** (gitignored) and project bundles (brief, script, board, manifests, credits) in a repo subfolder. Keep scratch/temp dirs for intermediates only (`--thumbnails`, temp plates).

## Technical Invariants (What Actually Breaks Things)

- **Audio-first timing.** Frame counts come from measured VO durations (`ffprobe`) or explicit beat durations — never guessed. `words[]` and `sfx_events[].t_sec` are **scene-relative**; `start_sec` is auto-assigned sequentially.
- **Two timing paths** (`scripts/tts_align.py`): online → edge-tts `WordBoundary` events (measured, 100 ns ticks); `--offline` or any TTS failure → syllable-weighted model. Never re-split a joined string to index into `words` — wrap the measured token stream. `--trim-silence` is intentionally a no-op when measured boundaries exist; `build_master_wav` stays tolerant of VO stems shorter than `duration_sec`.
- **Optional 3D backends:** scenes with `scene_spec` always have `software_3d_projection.py` as a stdlib fallback. Three.js WebGL (`threejs_hybrid` / `threejs_3d`, `scripts/threejs_bridge.py` + `scripts/threejs/`, `three` MIT only, offline native CDP over Node ≥ 22 with `RoomEnvironment` IBL, `UnrealBloomPass`, `GLTFLoader`, and bespoke per-project `params.threejs_script` modules) and Blender (`blender_hybrid` / `blender_3d`, `scripts/blender_runner.py`) are both optional — probe once, fall back cleanly on failure. `camera_3d` defaults live once in `scene_router.CAMERA_3D_DEFAULTS`. Built-in categories: `exploded_hardware_3d`, `orbital_or_field_3d`, `organic_serpent_3d`, `network_topology_3d`, `external_asset_3d`.
- **SVG 2.0 element (`elements/svg.py`):** pure-Python stdlib SVG vector engine (paths, shapes, transforms, `reveal: "draw"|"pop"|"fade"`, `glow`, `tint`) always works offline; automatically upgrades static SVGs to `resvg`/`rsvg-convert` or headless Chromium (`scripts/threejs/svg_raster.mjs`) for full SVG 2.0 fidelity (gradients, `<filter>`, `<style>`, `evenodd`, cached RGBA). Rejects unsafe `DOCTYPE`/`ENTITY` declarations.
- **Schema ↔ validator parity:** when `elements` is present it must be a non-empty array even on `scene_spec` scenes (omit the key instead). Unimplemented 3D categories fail at validation.
- **Long renders need heap trimming:** keep `gc.collect()` + `_malloc_trim()` in the frame loop (`render_engine.py`) so RSS stays flat and does not OOM-kill ffmpeg.
- **New element type?** Add painter in `scripts/elements/`, register in `RENDERERS` (`elements/__init__.py`) and `KNOWN_ELEMENTS` (`storyboard.py`), plus tests.
- **yuv420p + H.264 high/4.2 + `+faststart`:** required for iOS/IG/TikTok playback. Audio targets −14 LUFS, −1 dBFS ceiling, 48 kHz stereo; failed ffprobe QC exits 3.
- **RGB canvas buffers:** Pillow `ImageDraw` cannot alpha-blend; pre-blend translucent tones or composite RGBA plates via mask (`cv.image.paste(..., mask)`).
- **Claims = code:** keep docs and test counts in sync with what actually passes `pytest`.
- **Subprocess safety & hygiene:** list-form argv, `timeout=`, `capture_output`/`DEVNULL`, `shutil.which()`, never `shell=True`. Zero PII. Don't edit sibling skills or run `install_surgical_media.sh` without asking. No golden-image PNG tests (use pixel-presence smoke tests). Keep OFL license files verbatim in `assets/fonts/`.

## Demo regeneration

`examples/tri_archetype_storyboard.json` is generated — regenerate via `python3 scripts/build_demo.py` after changing `build_demo.py` or `tts_align.py`, then re-validate and re-run `pytest`.
