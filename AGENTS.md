# AGENTS.md

Agent instructions for working inside the `surgical-media` skill repository. `README.md` is the human manual, `SKILL.md` the agent manifest — this file exists so you don't relearn the traps.

## Repo shape

- `main` is protected: required linear history, no force-push, no branch deletion, enforced for admins. Fast-forward pushes stay legal — never create merge commits.
- `surgical-media` is a Hermes **skill** (deterministic video pipeline: storyboard → MP4), not a published package. This directory **is** the public repo `github.com/TeacherEvan/surgical-media` (branch `main`, repo-local identity `TeacherEvan <…noreply.github.com>`). Ask before rewriting or force-pushing history.
- `Concept/` is the input transcript (design history). It is not the contract — code and `tests/` are.
- `docs/project-plan.md` is the living plan + task status; `docs/index.md` is the docs entrypoint. `docs/plans/` holds design history (the multi-engine Gemini conversation behind ADR 0003) — input, not contract, same rule as `Concept/`.
- Runtime deps: **Pillow ≥ 10.1 + ffmpeg/ffprobe on PATH** (`requirements.txt`). `edge-tts` is optional (`requirements-tts.txt`) and **tests never use it** (offline by design). Audio/geometry are stdlib-only — no NumPy (`docs/adr/0001-stdlib-first-verified-pipeline.md`).
- `SKILL.md` must stay ≤ 120 lines (agent manifest: stages/invariants/gotchas). Element catalog and parameter specs live in `references/storyboard-guide.md` — don't duplicate them here or in `SKILL.md`.
- Stage 1 acquires **subject imagery**, not just facts: `scripts/fetch_assets.py --query "<subject>" --out-dir assets --count 3` pulls licensed photos from Openverse + Wikimedia Commons (originals) + iNaturalist (nature) — same `by`/`by-sa`/`cc0`/`pdm` allowlist everywhere, PIL-verified, cross-source deduped, https-only with a 50 MB download cap — and writes `assets/manifest.json` whose `attribution` strings go verbatim into `image` elements. Hotlinking is never acceptable; record the manifest.

## Commands (all run green locally — the gate *is* local)

```bash
python3 scripts/storyboard.py examples/tri_archetype_storyboard.json   # demo must always validate
python3 scripts/storyboard.py examples/hybrid_3d_storyboard.json      # 3D/HUD showcase must validate too
python3 scripts/storyboard.py examples/threejs_3d_storyboard.json     # Three.js WebGL 3D showcase must validate too
ruff check --no-cache scripts/ tests/
ruff format --check --no-cache scripts/ tests/
python3 -m pytest tests/ -q                                            # 316 tests, all green
check-jsonschema --check-metaschema schemas/*.schema.json
python3 scripts/render_engine.py --demo --thumbnails /tmp/sm_thumbs     # seconds — visual smoke, no ffmpeg needed
python3 scripts/render_engine.py --storyboard examples/hybrid_3d_storyboard.json --thumbnails /tmp/sm_hybrid_thumbs   # software 3D + HUD smoke
python3 scripts/render_engine.py --storyboard examples/threejs_3d_storyboard.json --thumbnails /tmp/sm_threejs_thumbs # Three.js storyboard smoke
python3 scripts/render_engine.py --demo --output /tmp/sm_gate.mp4       # only when render code changed; exit 0 + QC ok:true
```

- Single test: `python3 -m pytest "tests/test_visual_smoke.py::test_box_downsample_keeps_thin_lines" -q`
- Verification is **local-first**: `scripts/ci_gates.sh` is the single gate (storyboard → ruff → format → mypy --strict → 316 tests → schema metaschema → all example-vs-schema → thumbnails for 2D + hybrid 3D + Three.js 3D → draft render → ffprobe QC; 9 gates) and is what “green” means for this repo. GitHub Actions was removed 2026-11-18 (billing-locked; permanently red). An optional GitLab mirror (`.gitlab-ci.yml`) runs the same script on import — it has **NOT run** yet; never claim a green pipeline until one passes. Change the script, never the providers. ffmpeg is apt/pip-installed there and integration tests **skip cleanly** without it. The gate venv is `requirements-dev.txt` (mirrors `[project.optional-dependencies].dev` in `pyproject.toml`).
- **mypy strict is enforced** as gate 4/9: `pyproject.toml` sets `strict = true` and `mypy scripts/` must report zero issues — the whole `scripts/` tree is annotated. Pre-commit runs the same check via a local hook.
- **markdownlint** (npm, v0.49.1) fails on *pre-existing* house docs (`references/`, `docs/adr/`: MD022/MD031/MD034/MD060) — it is not a gate. Don't present it as one, and don't add it to CI without fixing those files first.
- Before spending a full render: `--estimate` (frame count / audio cost) and `--thumbnails DIR` (one PNG per scene). `final` = crf 18, demo/draft = crf 26. Rendering is deterministic only per machine/Pillow build — diff frames, not hashes.
- `*.mp4`, `*_work/`, `audio/` (TTS voice stems, written next to the storyboard or `--media-dir`), `__pycache__/`, `.pytest_cache/` are gitignored artifacts. Never commit rendered outputs.
- **Rendered deliverables ALWAYS go in the folder the agent session was opened in (the workspace/repo root).** That folder is the output location, full stop — not scratch, not `/tmp`, not a temp dir suggested by the harness. Copy the final MP4 to the repo root next to `demo_showcase.mp4` / `penguins_vertical.mp4`, and any project bundle (brief, script, board, photo manifests, credits) into a repo subfolder. Scratch/temp dirs are for intermediates only — `--thumbnails`, TTS stems, downloaded plates. Never tell the user a final output path outside the open folder. "Don't commit rendered outputs" means don't `git add` them, not don't store them here.

## Hard-won invariants (do not relearn)

- **Design history is a pattern, not an asset library.** `docs/plans/` and `Concept/` teach *how* to build a generator; a new subject gets a NEW generator in `software_3d_projection.py`, `scripts/threejs/scenes.mjs`, AND `blender_runner.py`, plus registration in `scene_router.py`, `storyboard.py` and `schemas/storyboard.schema.json`, tests and docs in the same change. Never reuse the example torus/hardware stack as a stand-in for the requested subject.
- **Deliverables finish in the folder the session opened in.** Final MP4 at the workspace/repo root (gitignored), project bundle in a repo subfolder; scratch only holds intermediates. Check the existing output files before choosing a path.
- **Audio-first timing.** Frame counts come from measured VO durations (ffprobe) or explicit beat durations — never guessed. `words[]` and `sfx_events[].t_sec` are **scene-relative**; `start_sec` is auto-assigned sequentially.
- **Two timing paths** (`scripts/tts_align.py`): online → edge-tts `WordBoundary` events (measured, 100 ns ticks); `--offline` or any TTS failure → syllable-weighted model. **Never re-split a joined string to index into `words`** — a boundary event can carry multiple whitespace-separated words (e.g. `"since 2009"`). Wrap the measured token stream (see `paint_kinetic_captions`, which had exactly this bug).
- **`--trim-silence` is a no-op when measured boundaries exist** (word offsets are relative to the untrimmed stem) and was historically destructive to internal pauses — do not "fix" the missing trim. `build_master_wav` must stay tolerant of VO stems shorter than `duration_sec` (regression-tested).
- **Optional 3D backends:** scenes with `scene_spec` render via `software_3d_projection.py` (stdlib 4×4 look-at; Painter's sort; no numpy, ever). Three.js WebGL (`threejs_hybrid` / `threejs_3d`, `scripts/threejs_bridge.py` + `scripts/threejs/`) and Blender (`blender_hybrid` / `blender_3d`, `scripts/blender_runner.py`) pre-bakes are both optional — probe once, per-scene, fall back to software on any failure. `scripts/threejs/` depends only on `three` (MIT) and drives headless Chromium offline over Node ≥ 22 native CDP with Z-up camera parity. `blender_runner.py` must stay importable without `bpy` and must not import repo modules; Blender 5.x dropped `Scene.node_tree`-style compositing and `FOG_GLOW` — capability probes live there, not in render_engine. Supported categories are `exploded_hardware_3d`, `orbital_or_field_3d`, `organic_serpent_3d`, and `network_topology_3d` — other schema categories are rejected at validation; renderers also raise `NotImplementedError` by design. `camera_3d` defaults live once in `scene_router.CAMERA_3D_DEFAULTS` (shared across software 3D, Three.js, and Blender); only `orbit` mode + two lighting presets ship — do not widen the enums without implementing the render path.
- **Schema ↔ validator parity is exact:** when `elements` is *present* it must be a non-empty array even on `scene_spec` scenes (both validators reject `[]`); omit the key instead. Unimplemented 3D categories must fail at validation, never degrade to a blank stage. Gate 1/6/7 exercise both example boards.
- **Long renders need heap trimming:** the frame loop calls `gc.collect()` + `_malloc_trim()` after each frame (`render_engine.py`); canvas/draw reference cycles otherwise grow RSS until the cgroup OOM-kills the ffmpeg pipe. Don't remove it.
- **New element type?** Painter in the `scripts/elements/` package (new module or existing family) + entry in `RENDERERS` (`elements/__init__.py`) and `KNOWN_ELEMENTS` (`storyboard.py`) + tests, in the same change. Unknown types render as **silent no-ops**; only a `warn` line is printed.
- **yuv420p + H.264 high/4.2 + `+faststart`, or nothing** — anything else breaks iOS/IG/TikTok. Audio targets −14 LUFS, −1 dBFS ceiling, 48 kHz stereo; failed ffprobe QC exits 3.
- **RGB only.** ImageDraw can't alpha-blend: buffers are RGB end-to-end; translucency is pre-blended; scene fades are RGB `Image.blend`s.
- **Claims = code.** SKILL.md/README claims must land as tested code in the same change. The test count is quoted in docs — bump every occurrence (SKILL.md, AGENTS.md, `docs/adr/`).
- **Subprocess discipline:** list-form argv, `timeout=`, `capture_output`/`DEVNULL`, `shutil.which()` before use, never `shell=True`.
- **Zero PII** — synthetic placeholders only.
- **Scope:** don't edit sibling skills (`surgical-audit/`, etc.) from this repo. Don't run `install_surgical_media.sh` (installs to `~/.hermes/skills/creative/surgical-media`) without asking.
- **No golden-image tests** by design (fonts drift across hosts) — CI guards on pixel-presence smoke tests instead. Don't bless PNGs.
- **AI image generation is not a fallback** for imagery (credentials unreliable; dishonest for factual documentary content). Fetch open-licensed photos; label every asset with its source license in-frame.
- Bundled OFL fonts in `assets/fonts/`: Inter (sans) and JetBrains Mono (mono, for the `code_report` archetype) — canvas prefers both over system fonts. OFL text must ship verbatim — never delete `assets/fonts/LICENSE.Inter.txt` or `assets/fonts/LICENSE.JetBrainsMono.txt`.
- `scripts/blender_plate.py` is an **optional** Blender path: headless Workbench 3D plates (`earth`/`iceberg`/`ringed`)—the `image` element composites them like photos. Integration test skips when Blender is absent; CI images don't have it. Never make a Blender feature a hard requirement of the skill.

## Demo regeneration

`examples/tri_archetype_storyboard.json` is generated — **never hand-edited**. After changing `build_demo.py` or `tts_align.py`, run `python3 scripts/build_demo.py`, re-validate the board, and re-run the suite.
