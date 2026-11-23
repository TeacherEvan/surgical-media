# Changelog

All notable changes to surgical-media. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); releases are
git-tagged (`v1.1.0`, `v1.2.0`, …) and dates are release dates.

Honest status line used throughout: **no hosted CI.** GitHub Actions was
removed 2026-11-18 (billing-locked; jobs never started). Local gates
(`bash scripts/ci_gates.sh`) are the enforced standard; the GitLab mirror
(`.gitlab-ci.yml`) is configured, not verified.

## [v3.2.0] — 2026-11-23

### Image-first (breaking behaviour change)
- **The subject must be on screen.** `fetch_assets.py` downloads were never wired into
  boards; every subject got the same stick rig / COMPUTE chart / EXCHANGE diagram
  plus captions. New `scripts/asset_wire.py` closes the loop: scores manifest plates
  against narration + `visual.query`, strips `placeholder: true` filler, inserts full-bleed
  credited imagery (Ken Burns, 9:16 `backdrop_blur`, safe-zone credit at y≈1060), reuses
  plates round-robin when the pool is small, and never clobbers authored SVG/3D visuals.
- `tts_align.py` gained `--assets-manifest` / `--subject` and passes per-scene `visual`
  hints through; it warns loudly when scenes still show generic filler.
- Beat scripts + boards gained `subject` and `visual` (`image`/`query`/`kind`/`fit`/`note`/
  `attribution`) art-direction, schema-validated in both `script.schema.json` and
  `storyboard.schema.json` (runtime parity preserved).
- `pipeline_preflight.py` gained the hard `subject_imagery` check; `style_lint.py` gained
  `no_subject_imagery`, `placeholder_visual`, `unused_assets` (pass `--manifest`).
  `meta.visual_intent` is the sole opt-out, for genuine showcases/abstract work.
- 3D demoted from implied default to optional accent — `SKILL.md` rewritten as an
  image-first 8-step orchestration (119 lines).
- Added `examples/photo_essay_storyboard.json` (image-first reference with committed
  CC0 fixtures) to CI thumbnail smoke gate; `scripts/elements/media.py` now keeps long
  attributions inside the safe box (ellipsis) and above captions.
- **Per-beat acquisition:** `scripts/fetch_scene_assets.py` derives a distinct query per
  scene (explicit `visual.query` wins, else informative narration words), dedupes, and
  fetches into one shared manifest. `fetch_assets.py` now stamps each plate with its
  originating query — real Commons titles are Latin binomials (`Aptenodytes forsteri`),
  so that provenance is the keyword bridge that keeps "emperor penguin" matching locally.
- **Brief-aware wiring:** `asset_wire.py` / `tts_align.py --brief` use
  `investigation_brief.visual_anchors` as per-scene queries and `visual_assets` as an
  additional plate pool (manifest wins on duplicate filenames).
- **Coverage gate hardened:** one hero photo no longer passes a video. At least 60% of
  scenes must carry subject imagery and no filler-only beat is allowed;
  `low_visual_coverage` added to `style_lint.py`.
- **Live-data hardening:** Openverse payloads were mislabelled `source: "flickr"`, bypassing
  the new relevance filter and producing a Pennsylvania National Guard photo for a penguin
  query. Openverse results are now stamped `source: "openverse"` and free-text plates must
  share a content token with their query (Commons/iNaturalist stay trusted: Latin binomials).
  A beat whose focused query returns nothing retries with the broad subject, so beats get
  distinct relevant plates instead of round-robining the single hero image. Verified end-to-end
  against live Openverse/Commons/iNaturalist.
- 772 → 860 tests; 12/12 local gates green.

## [v3.1.0] — 2026-11-22

### Security & Reliability
- Hardened `render_engine.py` ffmpeg subprocess lifecycle (pre-render 3D plates before `Popen`, stream `stderr` to `work_dir/ffmpeg_stderr.log`, enforce `wait(timeout=)` + `finally` cleanup + partial MP4 removal), `_safe_child_path` traversal guards, and LRU-bounded `_TRACKS_CACHE`.
- Fixed `monetization_gate.py` inverted `by`/`by-sa` attribution check, stationary zoom motion detection, and scene-level narration scanning.
- Enforced `SCENE_ID_RE` (`^[a-z0-9_-]{1,64}$`) and unique `scene_id` checks in `storyboard.py`, plus `if`/`then` `orbit_radius_start` parity in `schemas/storyboard.schema.json`.
- Added `_HttpsOnlyRedirectHandler` to `fetch_assets.py` and `spec_refresh.py`; hardened `threejs/runner.mjs` against `../` traversal, `URIError`, and CDP hangouts.
- Standardized atomic writes (`tempfile` + `os.fsync` + `os.replace`) across `job_store.py`, `media_harvester.py`, `qc_gate.py`, `audio_dsp.py`, `blender_runner.py`, and `runner.mjs`.

### Rendering, 3D & Audio Upgrades
- `audio_dsp.py`: added `@lru_cache` SFX synthesis, true linear-interpolation resampling, smooth 0.45 s ducking release tail in `mix_timeline`, and single-pass continuous ambient pad + global `duck_envelope` in `build_master_wav`.
- `canvas.py` & `elements/`: added `SupersampledCanvas.final()` bloom fast-path, `bold=False` font weight selection, `default_alpha` color-cache keying, bounded LRU caches + safe `parse_svg_path` in `elements/svg.py`, and painter geometry fixes (`paint_grid`, `paint_leader_arrow`, `paint_scaling_chart`, `paint_map_callout`, `paint_chat_bubble`).
- 3D backends: fixed `PerspectiveCamera3D` gimbal lock (`software_3d_projection.py`), shared `TorusGeometry` and pre-allocated `Vector3`s in `threejs/scenes.mjs`, extracted `compute_camera_location()` in `blender_runner.py`, and proportional 9:16 HUD scaling in `hybrid_compositor.py`.
- `verify_output.py`: fixed passing `width`/`height`/`fps` detail strings (`==` on pass).

### Wave 2 Integration, Testing & Installer
- Wired `investigation_brief` validation into `job_cli.py validate-brief` and `job_cli.py plan --brief`.
- Added `tests/test_tool_probe.py` and `tests/test_audit_regressions.py` (715 → 772 tests, 12/12 CI gates green, surgical audit score 40 → 97/100).
- Upgraded `install_surgical_media.sh` to `v3.1.0` with `--all-agents` multi-agent install, stale `.bak-*` cleanup, and v3.1.0 landing verification.

## [v3.0.1] — 2026-11-22

### Fixed
- **Black text boxes over photos.** The pure-Python SVG painter pre-multiplied RGB by
  `fill-opacity` and drew with `ImageDraw`, which has no alpha blend — so a translucent scrim
  became a solid near-black rectangle that hid the image beneath. `elements/svg.py` now draws
  translucent fills, strokes and text onto a transparent RGBA layer and alpha-composites it in
  place (bounding-box scoped), preserving painter order and letting backdrops show through.
  `_blend_opacity` is retained only for the additive bloom buffer.
- Regression tests added for `fill-opacity` over a backdrop (`tests/test_svg_element.py`).
- `SKILL.md` gotcha now points to the alpha-compositing renderer instead of advising pre-blended panels.

### Changed
- Version 3.0.0 → 3.0.1 (pyproject, SKILL, README, AGENTS, docs, installer banner).
- `install_surgical_media.sh` now verifies the patched SVG painter is present after install and
  stamps an installed version file, so a stale install is detectable. Full suite: 715 tests green.

## [v3.0.0] — 2026-11-21

### Added
- `scripts/spec_refresh.py` — executable Step 2 baseline/live spec refresh (16 baked facts,
  advisory HTTPS probes, exit 3 on drift).
- `scripts/style_apply.py` — writes the 7-style matrix into a timed board: presets, archetype
  rotation for hybrids, intro clamp with rescaled word/SFX times, outro scaffolding; idempotent.
- `scripts/pipeline_preflight.py` — executable intake/style mapping and structure gate:
  validates the 7-style contract, topic-matched intro/outro, duration cap and the sourced
  brief (originality). `scripts/media_harvester.py` now uses a pure-Pillow skin-tone centroid
  instead of a blind crop anchor when OpenCV is absent.
- **Priority social-video pipeline:** `SKILL.md` rewritten as a 7-step orchestration —
  mandatory Time/Style/Platform intake, live spec refresh, authentic-person research and
  attribution, proactive tooling pitch, audio-first multi-engine production, topic-matched
  intro/outro, and a hard QC gate. `surgical-media` is now the single entry point for future
  surgical-media content generation.
- `scripts/tts_normalizer.py` — stdlib date/number/currency/hashtag/ordinal expansion before
  local TTS; writes a reviewable change report.
- `scripts/media_harvester.py` — real-person portrait fetch (Commons/Wikipedia/Openverse),
  face-centered reframing (optional OpenCV, stdlib fallback), subtle safe-zone credit badges,
  and `credits.json` / `CREDITS.md`.
- `scripts/qc_gate.py` — ebur128 loudness, measured dead-air detection, and two-mask red/amber
  safe-zone audit overlays on Frame 1 / mid / outro; exit 3 on failure.
- References: `specs-licensing-compliance.md` (platform caps, dual 9:16 safe boxes, 2026
  Content ID/originality/C2PA rules, commercial TTS + renderer license matrix),
  `style-and-architecture.md` (7-style execution matrix, single locked timeline, originality
  gate), `pipeline-scripts.md`, `render-templates.md`.

### Changed
- Version 2.3.1 → 3.0.0 (pyproject, SKILL, README, installer, plan). Suite 551 → 713 tests
  (29 tts_normalizer + 37 media_harvester + 31 qc_gate + 14 preflight + 11 style_apply +
  35 spec_refresh); 12/12 local
  gates green.
- `README.md`, `AGENTS.md`, `docs/index.md`, `docs/project-plan.md` synced to the new
  pipeline and gate counts; ADR 0006 records the one-skill merge decision.
- `install_surgical_media.sh` ships the new scripts/references and the referenced
  `examples/jobs/` + `requirements*.txt`; banner refreshed to v3.0.0.
- Fixed and gated the audio master: single-pass loudnorm overshot TP (+0.4 dBTP) and
  drifted on short boards (-15.6 LUFS). `render_engine.py` now uses measured two-pass
  loudnorm, a gentle crest-factor compressor and a -1 dBFS limiter; demo and short
  showcase both pass gate 12 (`qc_gate.py`) at -14 ±1 LUFS / ≤ -1 dBTP.
- `style_apply.py` recomputes `start_sec` after clamping scene durations — an end-to-end
  showcase caught stale timeline offsets producing a 2.5 s A/V drift.

## [v2.3.0]

### Added
- 3.0 production-job layer (Wave 0/1): `scripts/job_model.py`, `job_store.py`,
  `job_director.py`, `job_cli.py`; `schemas/production_job.schema.json`;
  `examples/jobs/horse_tenny.json`; `tests/test_job_layer.py`; ADR 0005;
  `docs/audits/initial-baseline.md`; `references/job-workflow.md`.
- Gate 11/11: production-job examples validate (schema + runtime).
- `tests/test_subprocess_hygiene.py`: AST gate — no `shell=True`, every `subprocess.run/check_output` call has `timeout=`.

### Changed
- `thumbnail_gen._frame_contrast` uses `getextrema()` (removes the Pillow `getdata` deprecation; test warnings 7 → 0; 516 tests).
- Version 2.2.0 → 2.3.0 (pyproject, SKILL, README, project-plan).
- `ci_gates.sh` gate labels corrected (`x/9` → `x/11`); `jobs/` gitignored.

## [v2.3.1] — 2026-11-21

### Added
- **Claim-ID research contract (Wave 2 foundation):** `scripts/investigation_brief.py` — runtime validator mirroring `schemas/investigation_brief.schema.json` with `claim_id`, `claim_type`, `contradictions` cross-references, and full validation for `visual_anchors`, `visual_assets`, `target_format`. `tests/test_investigation_brief.py` — 35 tests including schema/runtime parity for all fields.
- Breaking schema change: `schema_version` = 1.0.0 is now required; `claim_id` (pattern `^claim-[0-9a-f]{8}$`), `claim_type` (enum: factual/statistical/anecdotal/opinion/satire), and `contradictions` (array of claim_ids) are required on every fact. Older briefs will not validate.

### Fixed
- Validator now matches schema on `visual_anchors`, `visual_assets`, `target_format` (previously only validated `facts`; parity test now covers all fields).
- `opencode.json` — reverted accidental Kilo schema URL addition.

## [v2.2.0]

### Added
- **Comedy time: `ui_mockups` painters (Horse Tenny/`ref_horse_tinder.json` genre), `maps` (world clusters, `paint_map_callout`, `paint_map_arrow` leader-arrow). Registered in `RENDERERS` + `KNOWN_ELEMENTS`.
- **Monetization guards (advisory → blocking where required):** `scripts/monetization_gate.py` — commercial-license firewall for `assets/manifest.json` (`LICENSE_ALLOWLIST` + attribution-required), `asset_files_exist` for `image` elements, `adversarial_safe_phrasing` on script narration (fabricated quotes, defamation, election/medical triggers), `retention_static_hold` (ERROR when >3.0 s @9:16 / >6.0 s @16:9 without motion/SFX). Wired into `verify_output.py` via `--manifest`/`--script` (ERRORs fail the export).
- **CTR thumbnails: `scripts/thumbnail_gen.py`** — renders scene thumbnails, scores by contrast (≥4.5:1 proxy) and 168×94 legibility (non-white fraction), writes best JPEG < 2 MB.
- **Tool probe: `scripts/tool_probe.py`** — host capability probe (local GPU, Blender, Three.js/Chromium, local STT/TTS, API-key presence) → `capabilities.json`; drives the "use all available tools" tier decision.
- **Multi-voice casting:** `voices` map in `schemas/script.schema.json` + `tts_align.py` per-scene voice override (priority: scene override > script.voice > CLI --voice).

### Changed
- `SKILL.md` ≤120 (v2.2.0, new pipeline stages, guards in Verification, genre painter catalog, topic→preset table); `references/storyboard-guide.md` gains genre-painter chapter (`ui_mockups`, `maps`).
- `docs/project-plan.md` quotes: 476 tests, 10 gates.

### Fixed
- `tests/test_verify_output.py` — no new tests; existing suite adapted for new wiring (`--manifest/--script`).

### Docs
- New boards `examples/ref_*` already in v2.0.1 are now at 100/100 on `style_lint` (horse card uses `&#183;`, not `&middot;`).

## [v2.0.1]

### Added
- **Monetization & retention gates.** `scripts/monetization_gate.py` — blocking pre-export checks wired into `verify_output.py` (`--manifest`/`--script`): commercial-license firewall (allowlist `cc0`/`pd`/`by`/`by-sa`; hard-block `by-nc*`/`by-nd*`/unknown/missing), asset file existence, adversarial-safe phrasing lint on script text (fabricated quotes, defamation, medical/election misinformation), retention pacing (static holds >3s @9:16 / >6s @16:9 without camera motion or state change) — ERROR fails the export, WARN doesn't. `scripts/thumbnail_gen.py` — high-CTR thumbnail picker from scene thumbnails (≥4.5:1 subject/background contrast, ≥110 px cap height, downscale-legible at 168×94, JPEG < 2 MB). `scripts/tool_probe.py` — environment probe (local GPU/Blender/Three.js/Chromium, local STT/TTS modules, API-key presence) emitting `capabilities.json` so hosts auto-select the "use all available tools" adapter tier. Multi-voice casting: `voices` map in `schemas/script.schema.json` + `tts_align.py` per-scene voice override.

### Changed
- **Packaging hygiene.** Pruned the 113 MB `snakes_friend_project/` scratch from `git`; `.gitignore` blocks the usual scratch (`check_*.png`, `*_probe.json`, `render_final.log`, `thumbs_contact.jpg`, `snakes_friend_project/`). Deleted `Concept/surgical-media-concecpt.txt` (typo) and `docs/plans/Conversation with Gemini.txt` (raw chat transcripts); the roadmap stays in `docs/project-plan.md`.
- **Docs.** `SKILL.md` + `references/storyboard-guide.md` document the probe (Stage 3), new genre painters (`ui_mockups`, `maps`), monetization gates, and voice casting.

### Removed
- Raw chat transcripts, duplicate stock assets (`snakes_friend_project/`), generated render artifacts (26 MB `thumbs/`, 22 MB `assets2/` duplicate, 22 MB `assets/`); `Concept/surgical-media-concecpt.txt`

## [v2.0.0]

### Added
- **Art direction + platform practice (v2.0.0).** Optional `style` + `platform` top-level blocks on every board (the same blocks existed in the validators since v1.5.0; now schema-described via new `schemas/style.schema.json` + updated `schemas/storyboard.schema.json`). `scripts/style.py` — preset loader (`assets/styles/`: `soft_clay`, `punchy_pop`, `newsroom_clean`, `noir_restraint`, `risograph`, `tech_blueprint`), `@role` colour-ref resolution, 3D `style_light` bridge. `scripts/platform_presets.py` — caption styles (`sticker`/`editorial`), safe zones (`canvas.layout_zones`), hook/beat budgets, aspect presets. `scripts/grade.py` — deterministic per-board grain/vignette/halation post-pass (wired into `render_engine.py`). `scripts/composition.py` — thirds + negative-space anchors. Advisory linters: `scripts/style_lint.py` (installed into `ci_gates.sh` as new gate 10, report mode), `scripts/contact_sheet.py`, `scripts/publish_kit.py` (`publish_kit.md`: title/description, long-form chapters, credits from `assets/manifest.json`, AI-disclosure lines, policy links). New reference boards — `examples/ref_horse_tinder.json` (punchy shorts: phone card + sticker captions + swipe lead), `examples/ref_soft_clay_poem.json` (calm poem: orbital rings, soft equalizer), `examples/ref_geopolitics_explainer.json` (neutral newsroom explainer: schematic world map, sourced data chart, source_tag lower-thirds), `examples/ref_true_story_noir.json`, `examples/ref_tech_explainer.json` — all 100/100 on `style_lint`, pixel smoke checks pass. Docs: `references/storyboard-guide.md` gains the "Art direction and platform practice" chapter (style/platform blocks, presets table, topic → preset → board table, policy links); `SKILL.md` ≤120 lines, `README.md`/`AGENTS.md`/`docs/project-plan.md` quotes updated; tests 395 → 439. Design plan: `docs/plans/implementation_plan2.md` (this plan).
- **Creative visuals: personality painters + orbit camera + Visual Grammar docs (v1.5.0).** New deterministic painters — `orb_pulse` (pulsing hero + glow halo), `dot_field` (floating particle swarm on a golden spiral), `orbit_ring` (spinning dot ring), `equalizer` (audio-style bars), `typewriter_text` (progressive glyph reveal + block cursor), `leader_arrow` (animated leader on a polyline) — registered in `RENDERERS` + `KNOWN_ELEMENTS`, frame-motion-tested (`tests/test_visual_creativity.py` + extended painter registries; suite 329 → 375). This was the biggest guard rail behind the "flat videos": the only creative menu was the 13-type catalog + canonical palettes + motionless camera, so nearly every render looked alike. **Camera expansion:** `camera.mode` = `zoom` (default) | `orbit` (center orbits `pivot_x/pivot_y` from `azimuth_start_deg → azimuth_end_deg` by `orbit_radius_start/end`, optional `elevation_deg`, `orbit_easing`) | `static` (frozen zoom); schema updated. **Docs:** `references/storyboard-guide.md` gains a "Visual Grammar" section (layer stack, no-dead-frames rule, one-hero-per-scene, recipe cards: data reveal / character moment / tour / impact beat) and six new painter catalog entries; `references/archetypes.md` gains per-archetype persona palettes + motion-beat ideas (palettes are now the default set, not a law); `SKILL.md`/`README.md`/`pyproject.toml`/`docs/project-plan.md` version-synced to 1.5.0. Design plan: [docs/plans/creative-visual-richness.md](docs/plans/creative-visual-richness.md).
- **Three.js WebGL Studio upgrade (`scripts/threejs/`)**: added `PMREMGenerator` + `RoomEnvironment` IBL reflections, `EffectComposer` + `UnrealBloomPass` HDR bloom, full `three/addons/*` import map, `external_asset_3d` (`GLTFLoader` for `.glb`/`.gltf` in 3-way parity with Blender & software 3D, plus `SVGLoader` + `ExtrudeGeometry` 2D SVG → bevelled 3D PBR mesh extrusion via `params.svg_markup` or `.svg` asset paths), single-frame WebGL `--thumbnails` via `--frame-t`, cinematic camera modes (`orbit`, `dolly`, `crane`, `static`), `params.camera_target`, and **bespoke per-project Three.js scene modules** via `params.threejs_script` (unlimited custom 3D scenes with zero core-repo edits).
- **SVG 2.0 element (`scripts/elements/svg.py` + `scripts/threejs/svg_raster.mjs`)**: inline or file-backed SVG vector art with full stdlib `<path>` (`M/L/H/V/C/S/Q/T/A/Z`), shapes, transforms, styles, `<text>`, animated progressive stroke drawing (`reveal: "draw"`), `pop`/`fade`, neon `glow` (bloom pyramid — supported on both vector and SVG 2.0 raster plates), rotation/scale, `tint`, unsafe `DOCTYPE`/`ENTITY` rejection, plus automatic upgrade to `resvg`/`rsvg-convert` or headless Chromium SVG 2.0 rasterization (full gradients, `<filter>`, `<style>`, `fill-rule="evenodd"`, cached RGBA). 13 new tests (`tests/test_svg_element.py` + `tests/test_threejs_backend.py`); suite: 316 → 329 tests (0 warnings).
- `AGENTS.md`: added an explicit **Creative Freedom** section separating technical invariants from creative direction so agents are encouraged to mix 2D, SVG, Three.js, Blender, and imagery freely.
- **v1.5.0 review-fix pass** — `typewriter_text` cursor now uses seconds (fix: `hold` previously counted glyphs and the cursor never turned off); glyphs are drawn with measured prefix offsets (kerning honored; the `getlength("i")` magic spacing removed); `quote_card` with `alpha < 1` now stays camera-aligned with its text (fix: `_paste_soft_pill` wrote to `cv.image` ignoring the world camera; same pattern as `paint_kinetic_captions`); `paint_background` caches the gradient and vignette mask per `(size, params)` (fix: rebuilt + 4k `putpixel`s + Gaussian blur every frame); `tts_align.py --rate`/`--pitch` now validated against `+N%`/`-N%` and `+NHz`/`-NHz` instead of failing silently inside edge-tts. Recorded: dynamic Three.js timeout (`max(240, 1.5·frames + 90)`, `threejs_bridge.py`), `--pad-tail` (`tts_align.py`), `--reuse-plates` (`render_engine.py`), and scene `transition: "dissolve"` (`render_engine.py`, `VALID_TRANSITIONS`).

## [1.4.0] — 2026-11-19

### Added
- **Headless Three.js WebGL 3D backend (`threejs_hybrid`, `threejs_3d`)**: optional PBR WebGL plate baker (`scripts/threejs/{package.json,runner.mjs,scenes.mjs,stage.html}` + `scripts/threejs_bridge.py`) driving local Chromium/Chrome offline over Node ≥ 22 native CDP with zero browser-automation npm dependencies (`three` only, MIT). Z-up camera and focal-length parity with `software_3d_projection.py` and `blender_runner.py`; automatic software 3D fallback when Node/Chromium/three is absent or fails.
- **`network_topology_3d` category** implemented in 3-way parity across `software_3d_projection.py`, `scripts/threejs/scenes.mjs`, and `blender_runner.py` (hub + 5 regional edge nodes, quadratic-bezier arcs, animated data packets, anchor tracking).
- `examples/threejs_3d_storyboard.json` — 2-scene Three.js hybrid WebGL showcase (`network_topology_3d` + `exploded_hardware_3d`); validated in `scripts/ci_gates.sh` gates 1, 7, and 8.
- `tests/test_threejs_backend.py` — 14 tests covering `probe_threejs_environment`, routing, schema parity, adapter defaults, prerender fallback paths, `network_topology_3d` parity, and a live headless Chromium WebGL integration test (skips cleanly when runtime is absent). Suite: 302 → 316 tests.
- [ADR 0004](docs/adr/0004-optional-threejs-webgl-backend.md) documenting the Three.js WebGL architecture and offline CDP design.
- `.gitattributes` — LF line endings for all text paths; binary markers for images, fonts, audio and video (nothing in the repo is CRLF today; this keeps it that way).
- Pre-commit hooks now scoped: top-level `exclude` protects generated artifacts (`examples/*.json`, archived `snakes_friend_project/`) and the verbatim OFL license texts from whitespace/EOF rewriting — byte-identity of the generated example board stays pinned by `tests/test_build_demo.py`. The mypy hook uses the official isolated mirror pinned to mypy 2.4.1 (the gate venv's version) instead of a PATH-dependent `language: system` hook.
- Docs: trailing-whitespace/EOF normalization in `Concept/`, `docs/plans/`, `docs/index.md`, `docs/project-plan.md` (whitespace only; no content changes).

## [1.3.0] — 2026-11-19

### Added
- `tests/test_fallback_paths.py` — 16 failure-path tests: software-3D exception containment, broken/unusable Blender plates falling back to the software pass, plate pre-render timeout / non-zero exit (never an abort), anchor-track loading & metadata merging, and `blender_runner` pure helpers (hex→linear, ease curve, spine/anchor math).
- `tests/test_build_demo.py` — pins the "example board is never hand-edited" contract: regenerating `examples/tri_archetype_storyboard.json` from `build_demo` must be byte-identical to what is checked in. 285 → 302 tests.
- `requirements-dev.txt` — the verification "gate venv" as code (pytest, pytest-cov, jsonschema, ruff, mypy, check-jsonschema), mirrored by `[project.optional-dependencies].dev`; the GitLab mirror and pre-commit now use it instead of ad-hoc pip installs.
- **mypy strict, enforced**: `scripts/` passes `mypy --strict` (249 errors → 0). New gate 4/9 in `scripts/ci_gates.sh`; pre-commit gains a local mypy hook; the gate runs it as part of every change.
- `pyproject.toml` now declares `dependencies` (`Pillow>=10.1`), `tts`/`dev` extras, and coverage configuration (`[tool.coverage.run] source = ["scripts"]`).
- `.editorconfig`; `.gitignore` now covers coverage, egg-info, `build/`, `dist/`, `.venv/`.
- Project-local `opencode.json` — version-pinned official MCP server for agent-assisted work on this repo: `context7` (docs grounding; sends documentation queries to a remote API). No secrets; removable at any time. (`sequential-thinking` was wired but removed: its npx install times out in this network — see commit history.)
- `organic_serpent_3d` — a genuine parametric snake asset: tapered undulating S-curve body (26×8 polygon tube with jade scale bands, gold head and emissive eyes) in `software_3d_projection.py`, and a headless-bpy curve/bevel builder with per-frame spine animation in `blender_runner.py`. Registered in router, runtime validator and storyboard schema; head/body/tail anchors track the moving spine. 7 new tests; suite now 285.
- SKILL.md/AGENTS.md now state the design-history rule: plans are *templates for creating assets*, never assets to copy; new subjects require new generators in both renderers with tests and docs in the same change.
- **Optional parametric 3D scene backends** (`scene_spec` + `backend` on scenes): procedural `exploded_hardware_3d` and `orbital_or_field_3d` categories rendered by `scripts/software_3d_projection.py` (stdlib 4×4 look-at view matrix, Painter's-algorithm Z sort, diffuse shading, bloom-fed emissives) with normalized 3D→2D anchor tracks — Blender not required.
- `scripts/scene_router.py` — `auto`/`blender_hybrid`/`blender_3d`/`canvas_2d`/`manim_math` routing + Blender ≥3.6 capability probe (version-sniffed EEVEE id; `BLENDER_BIN` override; cached).
- `scripts/blender_runner.py` — optional headless-Blender bake (`blender -b -P`): EEVEE/Cycles selection, motion blur, compositor glare with host-API probes (4.2–4.5/5.x), `world_to_camera_view` anchor export, `anchor_tracks.json` for HUD compositing. Exploded-hardware and stellarator generators only; anything else raises `NotImplementedError`.
- `scripts/hybrid_compositor.py` + `scripts/layout_solver.py` — motion-tracked HUD: reticles, 45° elbow leaders, frosted glass cards; AABB min-axis placement with locked repulsors + 24 px clamp (no numpy).
- `render_engine.py` — `scene_spec` scenes painted 3D/plate → HUD → elements on top; pre-bake with software fallback; `paint_frame` used for both render loop and `--thumbnails`; `--estimate` reports per-scene backend routing.
- Schema + validator: `backend`/`scene_spec` on scenes; `scene_spec` satisfies the elements requirement (`anyOf` — elements-or-scene_spec); `tests/test_scene_spec_integration.py` pins both validators to parity.
- `examples/hybrid_3d_storyboard.json` — 2-scene showcase (CoWoS-style stack, stellarator torus); renders end-to-end with and without Blender.
- ADR 0003 (`docs/adr/0003-optional-3d-scene-backends.md`); `references/storyboard-guide.md` scene-backend section.
- `tests/test_layout_solver.py`, `tests/test_scene_router.py`, `tests/test_blender_runner.py`, `tests/test_software_3d_projection.py`, `tests/test_hybrid_compositor.py` — 59 new tests.
- ADR 0002 (`docs/adr/0002-local-first-verification.md`) — the decision record for removing hosted CI in favor of local-first gates (supersedes the removed GitHub Actions workflow).
- `SECURITY.md` — scope (offline, no network service), license-compliance and URL-safety reporting paths, supported versions.
- `.pre-commit-config.yaml` — optional ruff/format/whitespace hooks; explicitly documented as NOT a replacement for `scripts/ci_gates.sh`.

### Changed
- `main` branch protection enabled on GitHub: required linear history, force-push and deletion blocked, `enforce_admins: true`. Fast-forward pushes unchanged.
- `storyboard.schema.json` scene `required` is now `["scene_id","archetype","duration_sec"]`; scenes require `elements` **or** `scene_spec`.
- `scripts/ci_gates.sh`: gates 1/6 validate **every** `examples/*.json` board (runtime validator + JSON Schema); gate 7 adds a hybrid-3D thumbnail smoke alongside the 2D demo.
- Docs scaffolding: `docs/project-plan.md` (living plan + task status) and `docs/index.md` (docs entrypoint); version metadata synced to 1.3.0 (`pyproject.toml`, installer); README gains a Dependencies & Licensing section (Blender GPL subprocess note).
- 218 → 285 tests; all gates pass locally.

### Fixed
- 9:16 hybrid HUD: telemetry cards now dock in a two-column band above the 3D stage inside Shorts/Reels safe zones (previously the 16:9 gutter layout stranded cards at the canvas edges); regression test added.
- Non-numeric `camera.zoom_start`/`zoom_end`/`pan_x`/`pan_y`/`shake_amplitude_px` values in a board now produce a validation message instead of raising `ValueError` mid-validation (they crashed `validate_storyboard` before).
- `validate_storyboard` decomposed into per-section validators (max complexity 12, was 64); error messages byte-identical, pinned by the schema-parity contract tests.
- **mypy strict enforced** (was advisory-only): entire `scripts/` tree annotated (249 errors → 0). `scripts/ci_gates.sh` gained gate 4/9; pre-commit gained a local mypy hook. No runtime behavior change.
- 302 tests; all gates pass locally (9/9).

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
